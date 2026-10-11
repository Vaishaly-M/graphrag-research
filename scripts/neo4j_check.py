import os
from dotenv import dotenv_values
from neo4j import GraphDatabase

file_vals = dotenv_values(".env")
keys = sorted({k for k in file_vals if "NEO4J" in k.upper()} |
              {k for k in os.environ if "NEO4J" in k.upper()})


def show(k, v):
    if v is None:
        return "not set"
    if "PASSWORD" in k.upper():
        return f"length={len(v)}, starts/ends with space or quote: " \
               f"{v != v.strip() or v[:1] in '\"\'' or v[-1:] in '\"\''}"
    return repr(v)


print("Keys found:", keys)
for k in keys:
    f, e = file_vals.get(k), os.environ.get(k)
    print(f"\n{k}\n  .env file : {show(k, f)}\n  shell env : {show(k, e)}")
    if f is not None and e is not None and f != e:
        print("  >>> DIFFERENT: the shell value overrides the .env file")


def try_login(label, uri, user, pwd):
    if not (uri and user and pwd):
        print(f"\n[{label}] skipped, missing value")
        return
    try:
        with GraphDatabase.driver(uri, auth=(user, pwd)) as d:
            d.verify_connectivity()
        print(f"\n[{label}] LOGIN OK")
    except Exception as ex:
        print(f"\n[{label}] FAILED: {type(ex).__name__}: {str(ex)[:150]}")


uri = file_vals.get("NEO4J_URI")
try_login(".env values", uri,
          file_vals.get("NEO4J_USERNAME") or file_vals.get("NEO4J_USER"),
          file_vals.get("NEO4J_PASSWORD"))
try_login("shell env values", os.environ.get("NEO4J_URI"),
          os.environ.get("NEO4J_USERNAME") or os.environ.get("NEO4J_USER"),
          os.environ.get("NEO4J_PASSWORD"))