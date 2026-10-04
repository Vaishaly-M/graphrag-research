from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase

from .common import config_get


load_dotenv(override=True)


class Graph:
    """Small Neo4j connection wrapper."""

    def __init__(self) -> None:
        uri = os.getenv("NEO4J_URI")
        username = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")
        self.database = os.getenv("NEO4J_DATABASE", "neo4j")

        missing = [
            name
            for name, value in {
                "NEO4J_URI": uri,
                "NEO4J_USERNAME": username,
                "NEO4J_PASSWORD": password,
            }.items()
            if not value
        ]

        if missing:
            raise RuntimeError(
                "Missing Neo4j environment variables: "
                + ", ".join(missing)
            )
        
          # Safe diagnostic output
        print("Neo4j URI:", repr(uri))
        print("Neo4j username:", repr(username))
        print("Neo4j database:", repr(self.database))

        self.driver = GraphDatabase.driver(
            uri,
            auth=(username, password),
            connection_timeout=float(
                config_get("neo4j.connection_timeout_s", 60.0)
            ),

            # Disable long automatic retries during bulk loading.
            # load_graph.py performs controlled retries and batch splitting.
            max_transaction_retry_time=0.0,

            liveness_check_timeout=float(
                config_get("neo4j.liveness_check_timeout_s", 30.0)
            ),
            keep_alive=True,
            max_connection_pool_size=int(
                config_get("neo4j.max_connection_pool_size", 10)
            ),
        )

        self.driver.verify_connectivity()

    def query(
        self,
        cypher: str,
        **params: Any,
    ) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            cypher,
            parameters_=params,
            database_=self.database,
        )

        return [record.data() for record in records]

    def execute(
        self,
        cypher: str,
        **params: Any,
    ) -> None:
        self.driver.execute_query(
            cypher,
            parameters_=params,
            database_=self.database,
        )

    def close(self) -> None:
        self.driver.close()

    def __enter__(self) -> "Graph":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()