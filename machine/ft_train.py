#!/usr/bin/env python3
"""Fine-tune Qwen3.5 0.8B to answer M3Kang problems with one letter (runs on a rented GPU).

    python3 ft_train.py --name train-only --train-splits train --epochs 30 --save-at 1,3,10,30
    python3 ft_train.py --name full-bank  --train-splits train,val --epochs 40 --save-at 5,10,20,40

Each example is the exact prompt llama-server builds (make_ft_data.py) and the loss is on the one
answer token. After every epoch it reports accuracy on the organisers' train and val splits, so
"problems it has studied" and "problems it has not" are always separate numbers.
"""
import argparse
import json
import os
import random
import shutil
import time

import torch
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer

BASE = "Qwen/Qwen3.5-0.8B"
REV = "2fc06364715b967f1860aea9cf38778875588b17"
LETTERS = "ABCDE"


def load_model(path):
    import transformers
    for cls in ("AutoModelForImageTextToText", "AutoModelForCausalLM"):
        try:
            return getattr(transformers, cls).from_pretrained(path, torch_dtype=torch.bfloat16)
        except Exception as error:  # noqa: BLE001
            print(f"{cls} failed: {str(error)[:200]}", flush=True)
    raise SystemExit("could not load the model")


def last_logits(model, enc):
    """Logits for the answer position only (full-sequence logits over the vocabulary do not fit in memory)."""
    hidden = model.model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"]).last_hidden_state
    return model.lm_head(hidden[:, -1, :])


def batches(rows, tok, size, shuffle):
    order = list(range(len(rows)))
    if shuffle:
        random.shuffle(order)
    for i in range(0, len(order), size):
        chunk = [rows[j] for j in order[i:i + size]]
        enc = tok([r["prompt"] for r in chunk], return_tensors="pt", padding=True, add_special_tokens=False)
        yield chunk, enc


@torch.no_grad()
def evaluate(model, tok, rows, letter_ids, size=16):
    model.eval()
    right = total = 0
    by = {}
    for chunk, enc in batches(rows, tok, size, False):
        enc = {k: v.cuda() for k, v in enc.items()}
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits = last_logits(model, enc)
        pred = logits[:, letter_ids].argmax(-1).tolist()
        for r, p in zip(chunk, pred):
            ok = LETTERS[p] == r["label"]
            right += ok
            total += 1
            k = (r["split"], r["language"])
            by[k] = [by.get(k, [0, 0])[0] + ok, by.get(k, [0, 0])[1] + 1]
    model.train()
    return right / max(total, 1), {f"{s}/{lang}": round(100 * a / n, 1) for (s, lang), (a, n) in sorted(by.items())}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--data", default="/workspace/bank.jsonl")
    p.add_argument("--train-splits", default="train")
    p.add_argument("--langs", default="eng,cat,esp")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--save-at", default="")
    p.add_argument("--lr", type=float, default=1e-5)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--out", default="/workspace/ckpt")
    args = p.parse_args()
    random.seed(0)
    torch.manual_seed(0)

    base_dir = snapshot_download(BASE, revision=REV)
    tok = AutoTokenizer.from_pretrained(base_dir)
    tok.padding_side = "left"  # so the answer position is always the last token
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    letter_ids = [tok.encode(c, add_special_tokens=False) for c in LETTERS]
    assert all(len(x) == 1 for x in letter_ids), letter_ids
    letter_ids = [x[0] for x in letter_ids]

    rows = [json.loads(line) for line in open(args.data)]
    langs = set(args.langs.split(","))
    rows = [r for r in rows if r["language"] in langs]
    train = [r for r in rows if r["split"] in args.train_splits.split(",")]
    print(f"{args.name}: {len(train)} training examples, {len(rows)} evaluated", flush=True)

    model = load_model(base_dir).cuda()
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.0)
    steps = args.epochs * ((len(train) + args.batch - 1) // args.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps, pct_start=0.05)
    save_at = {int(x) for x in args.save_at.split(",") if x}
    log = open(f"/workspace/{args.name}.log.jsonl", "a")

    acc, by = evaluate(model, tok, rows, letter_ids)
    print(f"epoch 0: {by}", flush=True)
    log.write(json.dumps({"name": args.name, "epoch": 0, "acc": by}) + "\n")
    log.flush()
    t0 = time.time()
    for epoch in range(1, args.epochs + 1):
        total = n = 0
        for chunk, enc in batches(train, tok, args.batch, True):
            enc = {k: v.cuda() for k, v in enc.items()}
            target = torch.tensor([letter_ids[LETTERS.index(r["label"])] for r in chunk]).cuda()
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = last_logits(model, enc)
            loss = torch.nn.functional.cross_entropy(logits.float(), target)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            total += loss.item()
            n += 1
        acc, by = evaluate(model, tok, rows, letter_ids)
        print(f"epoch {epoch}: loss {total / n:.3f} {by} ({time.time() - t0:.0f} s)", flush=True)
        log.write(json.dumps({"name": args.name, "epoch": epoch, "loss": total / n, "acc": by}) + "\n")
        log.flush()
        if epoch in save_at:
            out = f"{args.out}/{args.name}-e{epoch}"
            shutil.copytree(base_dir, out, dirs_exist_ok=True, symlinks=False)  # tokenizer, configs
            for f in os.listdir(out):
                if f.endswith(".safetensors") or f == "model.safetensors.index.json":
                    os.remove(os.path.join(out, f))
            model.save_pretrained(out, safe_serialization=True)
            print(f"saved {out}", flush=True)
    print("TRAIN_DONE", flush=True)


if __name__ == "__main__":
    main()
