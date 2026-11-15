"""Convert M3Kang problem images (..\data\images) into JSON/JSONL using RapidOCR.

Reuses the reading_order, is_marker, and parse_options OCR pipeline from
parquet_to_images.py / parquet_to_jsons.py to extract options A..E (and question
text when building standalone JSONL records from images).

Usage:
    python image_to_json.py
    python image_to_json.py --languages eng,cat --out ..\data\val.jsonl
    python image_to_json.py --out ..\data\problems.json
    python image_to_json.py --update-jsonl ..\data\val.jsonl
    python image_to_json.py --image ..\data\images\lvl-0_2015_13_eng.png
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter

LETTERS = "ABCDE"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")
DEFAULT_IMAGES_DIR = os.path.join(DEFAULT_DATA_DIR, "images")
DEFAULT_OUT_FILE = os.path.join(DEFAULT_DATA_DIR, "ocr_problems.jsonl")

FILENAME_RE = re.compile(
    r"^(?P<id>lvl-(?P<level>\d+)_(?P<year>\d{4})_(?P<num>[^_]+))_(?P<language>[a-z]{2,3})$",
    re.IGNORECASE,
)


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--images-dir",
        default=DEFAULT_IMAGES_DIR,
        help="folder containing problem images (default: ..\\data\\images)",
    )
    p.add_argument(
        "--image",
        default="",
        help="process a single image file instead of scanning --images-dir",
    )
    p.add_argument(
        "--out",
        default=DEFAULT_OUT_FILE,
        help="output .jsonl or .json path (default: ..\\data\\ocr_problems.jsonl)",
    )
    p.add_argument(
        "--update-jsonl",
        default="",
        help="existing JSONL file (e.g. ..\\data\\val.jsonl) to enrich with OCR options from --images-dir",
    )
    p.add_argument(
        "--only-empty-options",
        action="store_true",
        help="with --update-jsonl, only run OCR on rows that currently have empty options",
    )
    p.add_argument(
        "--languages",
        default="",
        help="optional comma-separated language filter, e.g. eng,cat",
    )
    p.add_argument(
        "--default-language",
        default="eng",
        help="fallback language if filename does not end with _<lang> (default: eng)",
    )
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore .ocr_cache.jsonl and re-run OCR on every image",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="only process the first N images/records",
    )
    return p.parse_args()


# --- Reading the options from the image (from parquet_to_images.py / parquet_to_jsons.py) ---

MARKER = re.compile(r"^\s*([A-E])\s*([\)）\]:.]?)\s*(.*)$")


def group_rows(boxes):
    """Group OCR boxes into horizontal rows (top to bottom), sorted left to right."""
    items = []
    for box, text, _score in boxes:
        ys = [pt[1] for pt in box]
        xs = [pt[0] for pt in box]
        items.append({
            "x": min(xs),
            "y": (min(ys) + max(ys)) / 2,
            "h": max(ys) - min(ys),
            "text": text,
        })
    items.sort(key=lambda it: it["y"])
    rows, current = [], []
    for it in items:
        if current and abs(it["y"] - current[-1]["y"]) > 0.6 * max(it["h"], current[-1]["h"]):
            rows.append(current)
            current = []
        current.append(it)
    if current:
        rows.append(current)
    return [sorted(row, key=lambda it: it["x"]) for row in rows]


def reading_order(boxes):
    """Sort OCR boxes into rows (top to bottom), then left to right."""
    return [it for row in group_rows(boxes) for it in row]


def is_marker(text, letter, strict):
    m = MARKER.match(text)
    if not m or m.group(1) != letter:
        return None
    paren, rest = m.group(2), m.group(3)
    if paren:
        return rest
    if strict:
        return None
    # Without a parenthesis, only accept "C" alone or "E16"-style values,
    # so words such as "ADA" or figure labels with text are not markers.
    if rest == "" or re.match(r"^[-+−\d]", rest):
        return rest
    return None


def parse_options_with_start(boxes):
    """Return (options_dict, start_item_index) for the last A..E sequence."""
    items = reading_order(boxes)
    starts = [i for i, it in enumerate(items) if is_marker(it["text"], "A", strict=True) is not None]
    for start in reversed(starts):  # the options are the last A..E sequence
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
                return cleaned, start
            return {}, start  # five markers, but the options are pictures
    return {}, len(items)


def parse_options(boxes):
    """Return {"A": "12", ..., "E": "24"}, or {} when the options are not text."""
    options, _ = parse_options_with_start(boxes)
    return options


def extract_text_and_options(boxes):
    """Extract both the statement text (above the options) and the A..E options."""
    rows = group_rows(boxes)
    items = [it for row in rows for it in row]
    options, start_idx = parse_options_with_start(boxes)

    # Map each item back to its visual line to reconstruct readable question text
    item_to_row = {}
    flat_idx = 0
    for row_idx, row in enumerate(rows):
        for _ in row:
            item_to_row[flat_idx] = row_idx
            flat_idx += 1

    statement_rows = {}
    for idx in range(start_idx):
        r_idx = item_to_row[idx]
        statement_rows.setdefault(r_idx, []).append(items[idx]["text"].strip())

    lines = [" ".join(tok for tok in statement_rows[r] if tok) for r in sorted(statement_rows)]
    text = "\n".join(line for line in lines if line).strip()
    return text, options


def parse_filename(filename, default_language="eng"):
    """Extract id, language, level, and year from <id>_<language>.png."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    m = FILENAME_RE.match(stem)
    if m:
        return {
            "id": m.group("id"),
            "language": m.group("language").lower(),
            "level": int(m.group("level")),
            "year": int(m.group("year")),
        }
    if "_" in stem:
        maybe_id, maybe_lang = stem.rsplit("_", 1)
        if 2 <= len(maybe_lang) <= 3 and maybe_lang.isalpha():
            parts = maybe_id.split("_")
            level = int(parts[0].replace("lvl-", "")) if parts[0].startswith("lvl-") and parts[0][4:].isdigit() else 0
            year = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            return {
                "id": maybe_id,
                "language": maybe_lang.lower(),
                "level": level,
                "year": year,
            }
    return {
        "id": stem,
        "language": default_language,
        "level": 0,
        "year": None,
    }


def load_cache(cache_path):
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    cache[row["key"]] = {
                        "options": row.get("options", {}),
                        "text": row.get("text", ""),
                    }
    return cache


def write_records(records, out_path):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    if out_path.lower().endswith(".json"):
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
            f.write("\n")
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_ocr_on_image(ocr, img_path):
    with open(img_path, "rb") as f:
        img_bytes = f.read()
    boxes, _ = ocr(img_bytes)
    return extract_text_and_options(boxes or [])


def main():
    args = parse_args()
    from rapidocr_onnxruntime import RapidOCR

    languages = {l.strip().lower() for l in args.languages.split(",") if l.strip()}
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)

    cache_path = os.path.join(out_dir, ".ocr_cache.jsonl")
    cache = {} if args.no_cache else load_cache(cache_path)
    cache_file = open(cache_path, "a", encoding="utf-8")

    ocr = RapidOCR()
    records = []
    t0 = time.time()

    if args.update_jsonl:
        if not os.path.exists(args.update_jsonl):
            sys.exit(f"Input JSONL not found: {args.update_jsonl}")
        with open(args.update_jsonl, encoding="utf-8") as f:
            source_rows = [json.loads(line) for line in f if line.strip()]

        missing_images = 0
        for row in source_rows:
            if args.limit and len(records) >= args.limit:
                break
            if languages and row.get("language", "").lower() not in languages:
                continue

            key = f"{row['id']}|{row['language']}"
            img_path = os.path.join(args.images_dir, f"{row['id']}_{row['language']}.png")

            if args.only_empty_options and row.get("options"):
                records.append(row)
                continue

            if key in cache and not args.no_cache:
                options = cache[key]["options"]
                ocr_text = cache[key]["text"]
            elif os.path.exists(img_path):
                ocr_text, options = run_ocr_on_image(ocr, img_path)
                cache[key] = {"options": options, "text": ocr_text}
                cache_file.write(
                    json.dumps({"key": key, "options": options, "text": ocr_text}, ensure_ascii=False) + "\n"
                )
            else:
                missing_images += 1
                options = row.get("options", {})
                ocr_text = ""

            updated = dict(row)
            updated["options"] = options
            if not updated.get("text") and ocr_text:
                updated["text"] = ocr_text
            records.append(updated)

            if len(records) % 100 == 0:
                rate = len(records) / max(time.time() - t0, 1e-6)
                print(f"  {len(records)} rows processed, {rate:.1f} rows/s", flush=True)

        cache_file.close()
        out_path = args.out if args.out != DEFAULT_OUT_FILE else args.update_jsonl
        write_records(records, out_path)
        report(records, out_path, missing_images)
        return

    # Mode 2: Build JSON/JSONL directly from image files
    if args.image:
        if not os.path.exists(args.image):
            sys.exit(f"Image not found: {args.image}")
        image_paths = [args.image]
    else:
        if not os.path.isdir(args.images_dir):
            sys.exit(f"Images directory not found: {args.images_dir}")
        image_paths = [
            os.path.join(args.images_dir, name)
            for name in sorted(os.listdir(args.images_dir))
            if os.path.splitext(name)[1].lower() in IMAGE_EXTS
        ]

    for img_path in image_paths:
        if args.limit and len(records) >= args.limit:
            break
        meta = parse_filename(img_path, default_language=args.default_language)
        if languages and meta["language"] not in languages:
            continue

        key = f"{meta['id']}|{meta['language']}"
        if key in cache and not args.no_cache:
            options = cache[key]["options"]
            text = cache[key]["text"]
        else:
            text, options = run_ocr_on_image(ocr, img_path)
            cache[key] = {"options": options, "text": text}
            cache_file.write(
                json.dumps({"key": key, "options": options, "text": text}, ensure_ascii=False) + "\n"
            )

        rec = {
            "id": meta["id"],
            "language": meta["language"],
            "level": meta["level"],
        }
        if meta["year"] is not None:
            rec["year"] = meta["year"]
        rec.update({
            "text_only": bool(options),
            "text": text,
            "options": options,
            "label": "",
        })
        records.append(rec)

        if len(records) % 100 == 0:
            rate = len(records) / max(time.time() - t0, 1e-6)
            print(f"  {len(records)} images processed, {rate:.1f} img/s", flush=True)

    cache_file.close()
    write_records(records, args.out)
    report(records, args.out, missing_images=0)


def report(records, out_path, missing_images):
    if not records:
        sys.exit("No images/records matched. Check --images-dir or --languages.")
    by_lang = Counter(r.get("language", "?") for r in records)
    with_options = sum(1 for r in records if r.get("options"))
    print()
    print(f"Wrote {len(records)} records to {os.path.abspath(out_path)}")
    for lang, n in sorted(by_lang.items()):
        print(f"  {lang}: {n}")
    print(f"Options read from image: {with_options}/{len(records)} ({100 * with_options / len(records):.0f}%)")
    if missing_images:
        print(f"Missing image files: {missing_images}")


if __name__ == "__main__":
    main()