"""Pull only the non-image columns of M3Kang (both splits) via HTTP range reads.

    uv run --with duckdb python3 -I fetch_text.py OUT_DIR
Writes OUT_DIR/m3kang_text.parquet (id, language, level, text_only, label, text, split).
"""
import sys, duckdb

out = sys.argv[1]
con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")
q = """
COPY (
  SELECT id, language, level, text_only, label, text,
         regexp_extract(filename, '(high_quality|standard)', 1) AS split
  FROM read_parquet('hf://datasets/qualcomm/M3Kang/data/*.parquet', filename=true)
) TO '{out}/m3kang_text.parquet' (FORMAT parquet)
""".format(out=out)
con.execute(q)
print(con.execute(f"SELECT split, count(*) FROM '{out}/m3kang_text.parquet' GROUP BY 1").fetchall())
