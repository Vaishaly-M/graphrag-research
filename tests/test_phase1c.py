import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from scripts.audit_phase1b import anchors, overlaps
from scripts.derive_oracle_routes import ForcedRouter, derive, atomic_json
from src.common import ROOT
from src.systems.adaptive_hybrid_graphrag import AblationConfig
from src.systems.adaptive_hybrid_graphrag_v2 import System
from src.systems.prompts import ANSWER_TEMPERATURE, ANSWER_MAX_OUTPUT_TOKENS


class Phase1CTests(unittest.TestCase):
    def test_transient_windows_checkpoint_lock_retries_rename(self):
        base=ROOT/"results/v2/tests"
        base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp, patch.object(Path,"replace",
                side_effect=[PermissionError("sharing violation"),None]) as replace, patch("scripts.derive_oracle_routes.time.sleep"):
            atomic_json(Path(tmp)/"progress.json",dict(status="test"))
            self.assertEqual(replace.call_count,2)

    def system(self, route, no_templates=True):
        system=System.__new__(System)
        system.ablation=AblationConfig(no_templates=no_templates)
        system.minimum_vector_score=.3
        system.enable_safety_fallback=False
        system.router=ForcedRouter(route)
        system.graph=SimpleNamespace(query=Mock(return_value=[dict(answer="graph-shortcut-value")]))
        system.vector_store=SimpleNamespace(search=Mock(return_value=[dict(id="v", text="vector evidence",score=.8)]))
        def generate(prompt, **params):
            if prompt.startswith("Generate one read-only"):
                return "MATCH (:Repository {id:'example/repo'})-[:CONTAINS_FILE]->(f:File) RETURN f.path AS answer"
            return "LLM synthesized answer"
        system.llm=SimpleNamespace(generate=Mock(side_effect=generate))
        return system

    def test_no_template_functions_or_hybrid_shortcut(self):
        for route in ("graph","vector","hybrid"):
            with self.subTest(route=route), patch("src.systems.adaptive_hybrid_graphrag_v2.match_registered_query",
                    side_effect=AssertionError("template lookup called")), patch(
                    "src.systems.adaptive_hybrid_graphrag_v2.direct_answers",side_effect=AssertionError("shortcut called")):
                system=self.system(route)
                result=system.answer("List files in repository example/repo")
                self.assertEqual(result["answer"],"LLM synthesized answer")
                self.assertEqual(result["answer_generation_mode"],"grounded_llm")
                self.assertFalse(result["templates_enabled"])
                self.assertTrue(all(a["rung"]=="llm_cypher" for a in result["graph_attempts"]))
                call=system.llm.generate.call_args
                self.assertEqual(call.kwargs,dict(temperature=ANSWER_TEMPERATURE,max_output_tokens=ANSWER_MAX_OUTPUT_TOKENS))
                if route=="hybrid":
                    self.assertIn("vector evidence",call.args[0])
                    self.assertIn("graph-shortcut-value",call.args[0])
                self.assertEqual(system.graph.query.call_count,0 if route=="vector" else 1)

    def test_with_templates_preserves_original_shortcut(self):
        system=self.system("hybrid",False)
        result=system.answer("List files in repository example/repo")
        self.assertEqual(result["answer"],"graph-shortcut-value")
        self.assertEqual(result["answer_generation_mode"],"deterministic_graph")
        self.assertEqual(system.llm.generate.call_count,1)  # Cypher only; no answer synthesis.

    def test_same_prompt_template_and_budget_all_routes(self):
        prefixes=[]
        for route in ("graph","vector","hybrid"):
            system=self.system(route)
            system.answer("List files in repository example/repo")
            prompt=system.llm.generate.call_args.args[0]
            prefixes.append(prompt.split('"rank"')[0])
        self.assertEqual(len(set(prefixes)),1)

    def test_repository_is_not_subject_and_fragments_are(self):
        a=dict(question_id="a",question="repo question",source_repo="r",params='{"repo":"r"}')
        b=dict(question_id="b",question="different",source_repo="r",params='{"repo":"r"}')
        self.assertEqual(anchors(a),[])
        self.assertEqual(overlaps([a],[b]),[])
        for row in (a,b):
            row.update(category="code_retrieval",params='{"repo":"r","fragment":"same code fragment"}')
        self.assertEqual(overlaps([a],[b])[0]["entity_type"],"fragment")

    def test_pr_and_issue_separate_and_commit_prefix_global(self):
        a=dict(question_id="a",question="first",source_repo="a",params='{"commit":"a:commit:abcdef0123456789"}')
        b=dict(question_id="b",question="second",source_repo="b",params='{"commit":"abcdef0"}')
        self.assertEqual(overlaps([a],[b])[0]["entity_type"],"commit")
        a.update(source_repo="r",params='{"issue_number":12}')
        b.update(source_repo="r",params='{"pr_number":12}')
        self.assertEqual(overlaps([a],[b]),[])

    def test_unknown_strict_oracle_is_na(self):
        rows=[dict(question_id="q",route=r,recall_accuracy=1,strict_accuracy=None,is_error=False,latency_s=1)
              for r in ("graph","vector","hybrid")]
        self.assertIsNone(derive(rows)[0]["oracle_best_strict_accuracy"])


if __name__=="__main__":
    unittest.main()
