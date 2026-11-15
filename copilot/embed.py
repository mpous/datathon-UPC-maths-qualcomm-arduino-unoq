"""Turn text into vectors with the embedding server."""
import math

from .config import CONFIG
from .client import post

URL = f"http://127.0.0.1:{CONFIG['EMBED_PORT']}/v1/embeddings"
# About 3.5 characters per token keeps a text inside the 512-token context
MAX_CHARS = 1400


def embed(texts, query=False, timeout=60):
    """Return one unit-length vector per text. Set query=True for search questions."""
    prefix = CONFIG["EMBED_QUERY_PREFIX"] if query else ""
    response = post(URL, {"input": [(prefix + t)[:MAX_CHARS] for t in texts]}, timeout=timeout)
    vectors = [item["embedding"] for item in sorted(response["data"], key=lambda d: d["index"])]
    return [normalize(v) for v in vectors]


def normalize(vector):
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]
