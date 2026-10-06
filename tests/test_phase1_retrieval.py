import tempfile
import unittest
from pathlib import Path
import numpy as np
import faiss
from src.systems.query_registry import match_registered_query
from src.vector_store import VectorStore


class Encoder:
    def encode(self, *args, **kwargs):
        return np.array([[1.0, 0.0]], dtype="float32")


class RetrievalTests(unittest.TestCase):
    def test_apostrophe_registry(self):
        match = match_registered_query("What is the issue number for 'Can't find API Getway project' in repository dotnet/eShop?")
        self.assertEqual(match.params["title"], "Can't find API Getway project")
        self.assertEqual(match.params["repo"], "dotnet/eShop")

    def test_airflow_heavy_index(self):
        store = VectorStore.__new__(VectorStore)
        store.model = Encoder()
        store.index = faiss.IndexFlatIP(2)
        store.index.add(np.array([[1., 0.]]*100+[[.8, .6]]*12, dtype="float32"))
        store.docs = [dict(id=str(i), repo="apache/airflow" if i < 100 else "dotnet/eShop", kind="file") for i in range(112)]
        rows = store.search("query", k=10, repository="dotnet/eShop")
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(r["repo"] == "dotnet/eShop" for r in rows))
        self.assertGreater(store.last_search_stats["unique_global_candidates_examined"], 50)
        self.assertEqual(store.search("q", repository="absent/repo"), [])

    def test_manifest_required(self):
        with tempfile.TemporaryDirectory() as directory:
            store = VectorStore.__new__(VectorStore)
            store.dir = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "manifest missing"):
                store.load()


if __name__ == "__main__":
    unittest.main()
