# Data

`sample_problems.jsonl` holds five made-up problems in the M3Kang format, for smoke tests.

`laptop/prepare_m3kang.py` writes `train.jsonl` and `val.jsonl` here. Don't commit them: M3Kang is licensed for research use only. See the [dataset card](https://huggingface.co/datasets/qualcomm/M3Kang).

One problem per line:

```json
{"id": "lvl-0_2015_13", "language": "eng", "level": 0, "year": 2015, "text_only": true,
 "text": "13. For 3 days, the cat Joy has been catching mice. ...",
 "options": {"A": "12", "B": "15", "C": "18", "D": "20", "E": "24"}, "label": "C"}
```

`options` is `{}` when OCR couldn't read five text options, for example when the options are pictures.
