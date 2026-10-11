import unittest
from scripts.prepare_router_tuning import RepositoryCandidates
class CandidateTests(unittest.TestCase):
    def test_scope_and_reference(self):
        class Fake:
            def __init__(self): self.calls=[]
            def query(self, query, **params):
                self.calls.append((query,params)); return [{'repo':'example/repo'}]
        graph=Fake(); scoped=RepositoryCandidates(graph,'example/repo')
        discovery='MATCH (r:Repository) RETURN r.id AS repo LIMIT 2'
        scoped.query(discovery); scoped.query(discovery)
        self.assertEqual(len(graph.calls),1)
        self.assertIn('(r:Repository {id:$tuning_repo})',graph.calls[0][0])
        reference='MATCH (:Repository {id:$repo}) RETURN 1 AS answer'
        scoped.query(reference,repo='example/repo')
        self.assertEqual(graph.calls[1],(reference,{'repo':'example/repo'}))
if __name__=='__main__': unittest.main()
