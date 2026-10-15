"""Idempotent isolated Neo4j load; never delete historical graph data."""
import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

from src.ingest.storage import ROOT, read_rows
from .build import DIRECTIONS, LABELS

LOOKUPS = {'Repository': ['name', 'repo', 'snapshot'],
           'File': ['repo', 'path', 'extension', 'snapshot', 'blob_sha'],
           'Commit': ['repo', 'sha', 'timestamp', 'snapshot'],
           'Issue': ['repo', 'number', 'state', 'title', 'created_at', 'snapshot'],
           'PullRequest': ['repo', 'number', 'state', 'title', 'created_at', 'snapshot'],
           'Developer': ['repo', 'email', 'login', 'name', 'snapshot']}


def connect():
    load_dotenv(ROOT/'.env')
    return GraphDatabase.driver(os.environ['NEO4J_URI'],
        auth=(os.environ.get('NEO4J_USERNAME', 'neo4j'), os.environ['NEO4J_PASSWORD']),
        connection_timeout=20, max_transaction_retry_time=30)


def query(driver, text, **params):
    return driver.execute_query(text, parameters_=params, database_=os.getenv('NEO4J_DATABASE', 'neo4j')).records


def schema(driver):
    for label in LABELS:
        query(driver, f'CREATE CONSTRAINT dl_{label}_id IF NOT EXISTS FOR (n:DL{label}) REQUIRE n.id IS UNIQUE')
        for field in ['canonical_id', 'dataset'] + LOOKUPS[label]:
            query(driver, f'CREATE INDEX dl_{label}_{field} IF NOT EXISTS FOR (n:DL{label}) ON (n.{field})')
        if label in {'File', 'Issue', 'PullRequest', 'Commit'}:
            key = {'File':'path', 'Issue':'number', 'PullRequest':'number', 'Commit':'sha'}[label]
            query(driver, f'CREATE INDEX dl_{label}_scope IF NOT EXISTS FOR (n:DL{label}) ON (n.dataset,n.repo,n.{key})')
    query(driver, 'CREATE FULLTEXT INDEX dl_text IF NOT EXISTS FOR (n:DLFile|DLIssue|DLPullRequest|DLCommit) ON EACH [n.content,n.title,n.body,n.message]')
    query(driver, 'CALL db.awaitIndexes(120)')


def load(directory):
    nodes = read_rows(directory/'nodes.jsonl'); edges = read_rows(directory/'relationships.jsonl')
    with connect() as driver:
        driver.verify_connectivity(); schema(driver)
        for label in LABELS:
            rows = [r for r in nodes if r['label'] == label]
            for start in range(0, len(rows), 250):
                query(driver, f'UNWIND $rows AS row MERGE (n:DL{label} {{id:row.id}}) SET n = row', rows=rows[start:start+250])
            print('Loaded', label, len(rows), flush=True)
        for kind, (source, target) in DIRECTIONS.items():
            rows = [r for r in edges if r['type'] == kind]
            for start in range(0, len(rows), 500):
                result = query(driver, f'UNWIND $rows AS row MATCH (a:DL{source} {{id:row.start}}), (b:DL{target} {{id:row.end}}) '
                    f'MERGE (a)-[r:DL_{kind} {{id:row.id}}]->(b) SET r = row RETURN count(r) AS n', rows=rows[start:start+500])
                if result[0]['n'] != len(rows[start:start+500]):
                    raise ValueError('Relationship endpoint missing during load')
            print('Loaded', kind, len(rows), flush=True)


if __name__ == '__main__':
    import yaml
    config = yaml.safe_load((ROOT/'configs/snapshots.yaml').read_text())
    load(ROOT/'data/graph_exports'/config['dataset_id'])
