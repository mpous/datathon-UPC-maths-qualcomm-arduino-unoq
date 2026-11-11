"""Read config.env, the settings file shared with the board scripts."""
import os
import shlex

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path=os.path.join(ROOT, "config.env")):
    values = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw = line.split("=", 1)
            parts = shlex.split(raw, comments=True)
            values[key.strip()] = os.path.expanduser(parts[0]) if parts else ""
    # Environment variables win, so you can try a setting without editing the file
    for key in values:
        if key in os.environ:
            values[key] = os.environ[key]
    return values


CONFIG = load()
