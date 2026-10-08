# scripts\neo4j_user_test.py
from dotenv import dotenv_values
from neo4j import GraphDatabase

v = dotenv_values(".env")
uri, pwd = v["NEO4J_URI"], v["NEO4J_PASSWORD"]
instance_id = uri.split("//")[1].split(".")[0]

for user in ["neo4j", instance_id]:
    try:
        with GraphDatabase.driver(uri, auth=(user, pwd)) as d:
            d.verify_connectivity()
        print(f"LOGIN OK with username={user!r}")
        break
    except Exception as ex:
        print(f"username={user!r}: {type(ex).__name__}")