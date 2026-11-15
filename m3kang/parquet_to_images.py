#!/usr/bin/env python3
"""Extract selected M3Kang problem images into qualcomm/data/images.

Follows the exact shard, language, and deterministic train/val split logic of
prepare_m3kang.py, saving each image as <id>_<language>.png so it can be
served directly by the web explorer.

Usage:
    python3 laptop/extract_images.py --languages eng,cat
    python3 laptop/extract_images.py --languages eng,cat --only-split val
    python3 laptop/extract_images.py --from-jsonl qualcomm/data/val.jsonl
    python3 laptop/extract_images.py --languages eng,cat,esp --shards all --years 2023,2024
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter

DATASET = "qualcomm/M3Kang"
SHARD = "data/{split}-{index:05d}-of-{total:05d}.parquet"
SHARDS = {"high_quality": 4, "standard": 10}
LETTERS = "ABCDE"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(os.path.dirname(SCRIPT_DIR), "data")
DEFAULT_IMAGES_DIR = os.path.join(DEFAULT_OUT, "images")

def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--split", default="high_quality", choices=sorted(SHARDS))
    p.add_argument(
        "--shards",
        default="0",
        help="comma-separated shard numbers, or 'all'. Shard 0 of high_quality has "
             "eng, cat, fra, esp, ind, deu, swh, vie, tur, zho, kor, arb, jpn, lit",
    )
    p.add_argument("--parquet", nargs="*", help="use local parquet files instead of downloading")
    p.add_argument("--languages", default="eng,cat", help="M3Kang language codes, e.g. eng,cat,esp")
    p.add_argument("--val-fraction", type=float, default=0.15, help="share of problem IDs held out")
    p.add_argument("--val-years", default="", help="hold out these years instead, e.g. 2023,2024")
    p.add_argument(
        "--only-split",
        default="all",
        choices=["all", "train", "val"],
        help="extract images only for 'train', 'val', or 'all' (default: all)",
    )
    p.add_argument("--years", default="", help="optional comma-separated years to keep, e.g. 2022,2023")
    p.add_argument("--levels", default="", help="optional comma-separated levels to keep, e.g. 0,1,2")
    p.add_argument(
        "--from-jsonl",
        default="",
        help="extract only images matching (id, language) entries in this JSONL file (e.g. qualcomm/data/val.jsonl)",
    )
    p.add_argument("--out", default=DEFAULT_OUT, help="base output folder (default: qualcomm/data)")
    p.add_argument(
        "--images-dir",
        default=DEFAULT_IMAGES_DIR,
        help="explicit directory for PNG images (default: <out>/images -> qualcomm/data/images)",
    )
    p.add_argument("--overwrite", action="store_true", help="overwrite existing PNG files")
    p.add_argument("--with-ocr", action="store_true", help="also run RapidOCR to extract options")
    p.add_argument("--write-jsonl", action="store_true", help="also write train.jsonl and val.jsonl in --out")
    p.add_argument("--limit", type=int, default=0, help="only extract the first N matching images")
    return p.parse_args()


def shard_paths(args):
    if args.parquet:
        return args.parquet
    from huggingface_hub import hf_hub_download

    total = SHARDS[args.split]
    indexes = range(total) if args.shards == "all" else [int(s) for s in args.shards.split(",")]
    paths = []
    for i in indexes:
        name = SHARD.format(split=args.split, index=i, total=total)
        print(f"Downloading {name} (cached after the first time)...", flush=True)
        paths.append(hf_hub_download(DATASET, name, repo_type="dataset"))
    return paths


# --- Reading the options from the image (optional, if --with-ocr is passed) ---

MARKER = re.compile(r"^\s*([A-E])\s*([\)）\]:.]?)\s*(.*)$")


def reading_order(boxes):
    """Sort OCR boxes into rows (top to bottom), then left to right."""
    items = []
    for box, text, _score in boxes:
        ys = [pt[1] for pt in box]
        xs = [pt[0] for pt in box]
        items.append({"x": min(xs), "y": (min(ys) + max(ys)) / 2, "h": max(ys) - min(ys), "text": text})
    items.sort(key=lambda it: it["y"])
    rows, current = [], []
    for it in items:
        if current and abs(it["y"] - current[-1]["y"]) > 0.6 * max(it["h"], current[-1]["h"]):
            rows.append(current)
            current = []
        current.append(it)
    if current:
        rows.append(current)
    return [it for row in rows for it in sorted(row, key=lambda it: it["x"])]


def is_marker(text, letter, strict):
    m = MARKER.match(text)
    if not m or m.group(1) != letter:
        return None
    paren, rest = m.group(2), m.group(3)
    if paren:
        return rest
    if strict:
        return None
    if rest == "" or re.match(r"^[-+−\d]", rest):
        return rest
    return None


def parse_options(boxes):
    """Return {"A": "12", ..., "E": "24"}, or {} when the options are not text."""
    items = reading_order(boxes)
    starts = [i for i, it in enumerate(items) if is_marker(it["text"], "A", strict=True) is not None]
    for start in reversed(starts):
        options, current, i = {}, None, start
        expected = iter(LETTERS)
        letter = next(expected)
        while i < len(items):
            text = items[i]["text"]
            rest = is_marker(text, letter, strict=(letter == "A")) if letter else None
            if rest is not None:
                current = letter
                options[current] = rest
                letter = next(expected, None)
            elif current:
                options[current] = (options[current] + " " + text).strip()
            i += 1
        if len(options) == 5:
            cleaned = {k: v.lstrip(")）] ").strip() for k, v in options.items()}
            if all(cleaned.values()):
                return cleaned
            return {}
    return {}


def load_target_keys(jsonl_path):
    """Load exact (id, language) pairs from an existing JSONL file."""
    target = set()
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            target.add((row["id"], row["language"]))
    return target


def main():
    args = parse_args()
    import pyarrow.parquet as pq

    target_keys = load_target_keys(args.from_jsonl) if args.from_jsonl else None
    if target_keys is not None:
        languages = {lang for _, lang in target_keys}
        print(f"Filtering by {len(target_keys)} entries from {args.from_jsonl}", flush=True)
    else:
        languages = {lang.strip() for lang in args.languages.split(",") if lang.strip()}

    val_years = {y.strip() for y in args.val_years.split(",") if y.strip()}
    allowed_years = {int(y.strip()) for y in args.years.split(",") if y.strip()}
    allowed_levels = {int(lv.strip()) for lv in args.levels.split(",") if lv.strip()}

    images_dir = args.images_dir or os.path.join(args.out, "images")
    os.makedirs(images_dir, exist_ok=True)
    if args.write_jsonl or args.with_ocr:
        os.makedirs(args.out, exist_ok=True)

    ocr = None
    cache = {}
    cache_file = None
    if args.with_ocr:
        from rapidocr_onnxruntime import RapidOCR

        ocr = RapidOCR()
        cache_path = os.path.join(args.out, ".ocr_cache.jsonl")
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        cache[row["key"]] = row["options"]
        cache_file = open(cache_path, "a", encoding="utf-8")

    rows = []
    written_images = 0
    skipped_existing = 0
    t0 = time.time()

    meta_cols = ["id", "language", "level", "text_only", "label", "text"]

    for path in shard_paths(args):
        if args.limit and len(rows) >= args.limit:
            break

        # Fast pre-filter on metadata columns before reading heavy image bytes
        meta = pq.read_table(path, columns=["id", "language", "level"])
        ids = meta.column("id").to_pylist()
        langs = meta.column("language").to_pylist()
        levels = meta.column("level").to_pylist()

        wanted = []
        for idx, (pid, lang, lvl) in enumerate(zip(ids, langs, levels)):
            if lang not in languages:
                continue
            if target_keys is not None and (pid, lang) not in target_keys:
                continue
            if allowed_levels and lvl not in allowed_levels:
                continue
            year_str = pid.split("_")[1]
            if allowed_years and int(year_str) not in allowed_years:
                continue
            if val_years:
                split = "val" if year_str in val_years else "train"
            else:
                bucket = int(hashlib.sha256(pid.encode()).hexdigest(), 16) % 1000
                split = "val" if bucket < args.val_fraction * 1000 else "train"
            if args.only_split != "all" and split != args.only_split:
                continue
            wanted.append(idx)

        if not wanted:
            continue

        full = pq.read_table(path, columns=meta_cols + ["image"]).take(wanted)
        for i in range(full.num_rows):
            if args.limit and len(rows) >= args.limit:
                break

            r = {c: full.column(c)[i].as_py() for c in meta_cols}
            key = f"{r['id']}|{r['language']}"
            img_filename = f"{r['id']}_{r['language']}.png"
            img_path = os.path.join(images_dir, img_filename)

            img_cell = full.column("image")[i].as_py()
            img_bytes = img_cell["bytes"] if isinstance(img_cell, dict) else img_cell

            if img_bytes:
                if args.overwrite or not os.path.exists(img_path):
                    with open(img_path, "wb") as f:
                        f.write(img_bytes)
                    written_images += 1
                else:
                    skipped_existing += 1

            if key in cache:
                options = cache[key]
            elif ocr and img_bytes:
                boxes, _ = ocr(img_bytes)
                options = parse_options(boxes or [])
                cache[key] = options
                cache_file.write(json.dumps({"key": key, "options": options}, ensure_ascii=False) + "\n")
            else:
                options = {}

            year = r["id"].split("_")[1]
            if val_years:
                split = "val" if year in val_years else "train"
            else:
                bucket = int(hashlib.sha256(r["id"].encode()).hexdigest(), 16) % 1000
                split = "val" if bucket < args.val_fraction * 1000 else "train"

            rows.append({
                "id": r["id"],
                "language": r["language"],
                "level": r["level"],
                "year": int(year),
                "text_only": r["text_only"],
                "text": r["text"].strip(),
                "options": options,
                "label": r["label"],
                "split": split,
            })

            if len(rows) % 200 == 0:
                rate = len(rows) / max(time.time() - t0, 1e-6)
                print(f"  {len(rows)} problems processed ({written_images} new PNGs), {rate:.1f} rows/s", flush=True)

    if cache_file:
        cache_file.close()

    if args.write_jsonl:
        for split in ("train", "val"):
            out = os.path.join(args.out, f"{split}.jsonl")
            with open(out, "w", encoding="utf-8") as f:
                for r in rows:
                    if r["split"] == split:
                        f.write(json.dumps({k: v for k, v in r.items() if k != "split"}, ensure_ascii=False) + "\n")

    report(rows, images_dir, written_images, skipped_existing, args.write_jsonl, args.out)


def report(rows, images_dir, written_images, skipped_existing, wrote_jsonl, out_dir):
    if not rows:
        sys.exit("No rows matched. Check --languages, --shards, or filter flags.")
    by = Counter((r["split"], r["language"]) for r in rows)
    print()
    print(f"Images directory: {os.path.abspath(images_dir)}")
    print(f"  New PNGs written : {written_images}")
    if skipped_existing:
        print(f"  Already existed  : {skipped_existing} (use --overwrite to rewrite)")
    print(f"  Total matched    : {len(rows)}")
    for (split, lang), n in sorted(by.items()):
        print(f"    {split:5} {lang}: {n}")
    if wrote_jsonl:
        print(f"Wrote {out_dir}/train.jsonl and {out_dir}/val.jsonl")


if __name__ == "__main__":
    main()