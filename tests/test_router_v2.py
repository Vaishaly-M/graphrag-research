import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from src.systems.router_v2 import RouterV2, EntityCatalog, ROUTES, FEATURES, EXEMPLARS, retrieve_with_fallback, train_artifact, load_frozen
from scripts.derive_oracle_routes import derive


class Encoder:
    def encode(self, texts, **kwargs):
        return np.zeros((len(texts),3))


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.catalog=EntityCatalog([dict(id="org/repo"),dict(id="org/repo:commit:abcdef0123")])
        self.router=RouterV2(self.catalog,Encoder(),tau=.55)

    def test_three_routes_reachable(self):
        cases={"graph":"Count issues assigned in org/repo", "vector":"Explain how this function implementation works", "hybrid":"Trace the dependency path across dependencies"}
        for route,question in cases.items():
            self.assertEqual(self.router.classify(question).retrieval_plan,route)

    def test_confidence_below_tau_escalates(self):
        self.router.tau=.95
        decision=self.router.classify("unknown question")
        self.assertEqual(decision.retrieval_plan,"hybrid")
        self.assertLess(decision.confidence,.95)

    def test_kg_entity_count_is_resolved_not_guessed(self):
        f,_,_=self.router.features_for("List org/repo and missing/repo")
        self.assertEqual(f["resolved_entities"],1)

    def test_vector_empty_escalates(self):
        calls=[]
        r=retrieve_with_fallback("vector",lambda:calls.append("graph") or [{"answer":"a"}],lambda:[])
        self.assertEqual(r["executed_route"],"hybrid")
        self.assertEqual(calls,["graph"])
        self.assertEqual(r["fallback_reason"],"empty_vector_evidence")

    def test_low_vector_and_empty_graph(self):
        r=retrieve_with_fallback("vector",lambda:[{"answer":"a"}],lambda:[{"score":.1}])
        self.assertEqual(r["fallback_reason"],"low_confidence_vector_evidence")
        r=retrieve_with_fallback("graph",lambda:[],lambda:[{"score":.9}])
        self.assertTrue(r["fallback_used"])

    def test_no_fallback_ablation(self):
        r=retrieve_with_fallback("vector",lambda:self.fail("disabled graph called"),lambda:[],enabled=False)
        self.assertFalse(r["fallback_used"])

    def test_llm_parse_failure_raises(self):
        self.router.variant="llm"
        self.router.llm=SimpleNamespace(generate=lambda *a,**k:'not JSON')
        with self.assertRaisesRegex(ValueError,"parse failure"):
            self.router.classify("x")

    def test_knn_and_logistic(self):
        features=[{k:float(i==j) for j,k in enumerate(FEATURES)} for i in range(6)]
        labels=["graph","vector","hybrid"]*2
        embeddings=np.eye(6)
        for variant in ["knn","logistic"]:
            artifact=train_artifact(variant,features,embeddings,labels)
            self.router.variant=variant
            self.router.artifact=artifact
            scores=self.router.scores_for("q",features[0],embeddings[0])
            self.assertAlmostEqual(float(sum(scores)),1.)
            self.assertTrue(np.isfinite(scores).all())

    def test_frozen_checksum_and_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"router.json"
            config=dict(selected=True,tuning_split_sha256="test-only",variant="rule",tau=.75,
                        catalog_fingerprint=self.catalog.fingerprint,feature_names=list(FEATURES),exemplars=EXEMPLARS)
            raw=json.dumps(config).encode()
            path.write_bytes(raw)
            path.with_suffix('.sha256').write_text(hashlib.sha256(raw).hexdigest())
            self.assertEqual(load_frozen(path,self.catalog,Encoder()).tau,.75)
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError,"checksum"):
                load_frozen(path,self.catalog,Encoder())

    def test_oracle_is_maximum_and_cheapest(self):
        records=[dict(question_id="q",route=route,recall_accuracy=1,strict_accuracy=1,
                      is_error=False,latency_eligible=True,latency_s=cost) for route,cost in zip(ROUTES,[2,1,3])]
        result=derive(records)[0]
        self.assertEqual(result["oracle_route"],"graph")
        self.assertEqual(result["oracle_best_accuracy"],1)
        with self.assertRaises(ValueError):
            derive(records[:2])


if __name__ == "__main__":
    unittest.main()
