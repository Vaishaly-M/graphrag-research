from dotenv import dotenv_values
from neo4j import GraphDatabase

v = dotenv_values(".env")
uri, pwd = v["NEO4J_URI"], v["NEO4J_PASSWORD"]
user = "f57c1e74"

for db in ["neo4j", "f57c1e74"]:
    try:
        with GraphDatabase.driver(uri, auth=(user, pwd)) as d:
            with d.session(database=db) as s:
                n = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        print(f"database={db!r}: OK, {n} nodes")
    except Exception as ex:
        print(f"database={db!r}: {type(ex).__name__}: {str(ex)[:100]}")