import copy
import unittest
import tempfile
from pathlib import Path

from src.ingest.snapshots import allowed_path, decode_text, GitHubSnapshot
from src.kg.build import build, synthetic, DIRECTIONS
from analysis.validate_data_layer import validate
from src.retrieval.build_indexes import chunks, tokens


class DataLayerTests(unittest.TestCase):
    def test_exclusions_preserve_source(self):
        for name in ['build/output.py','src/node_modules/a.js','yarn.lock','Cargo.lock','src/a.min.js','src/a_pb2.py','../bad.py']:
            self.assertFalse(allowed_path(name),name)
        self.assertTrue(allowed_path('src/service.py'))
        self.assertIsNone(decode_text(b'abc\x00def'))
        self.assertIsNone(decode_text(b'// Automatically generated\nvalue=1'))
        self.assertEqual(decode_text(b'print(1)\r\n'),'print(1)\n')

    def test_direction_and_orphan_checks(self):
        nodes=[dict(id='r',label='Repository',repo='a/b',snapshot='sha',commit_date='2026-01-01T00:00:00+00:00'),
               dict(id='f',label='File',repo='a/b',snapshot='sha',path='src/a.py')]
        edges=[dict(id='e',type='CONTAINS_FILE',start='r',end='f',repo='a/b')]
        self.assertEqual(validate(nodes,edges),[])
        reverse=[dict(edges[0],start='f',end='r')]
        self.assertTrue(any('direction' in e for e in validate(nodes,reverse)))
        orphan=[dict(edges[0],end='missing')]
        self.assertTrue(any('orphan' in e for e in validate(nodes,orphan)))
        bad=copy.deepcopy(nodes);bad[0]['commit_date']='not-a-date'
        self.assertTrue(any('bad date' in e for e in validate(bad,edges)))

    def test_chunks_have_identical_provenance(self):
        node=dict(id='f',label='File',repo='a/b',snapshot='pinned',path='src/a.py',content='x'*3000)
        docs=list(chunks([node]))
        self.assertGreater(len(docs),1)
        self.assertTrue(all(d['snapshot']=='pinned' and d['commit']=='pinned' and d['path']=='src/a.py' for d in docs))
        self.assertTrue(all(len(d['text'])<=1200 for d in docs))

    def test_family_config_is_globally_disjoint(self):
        import yaml
        from src.ingest.storage import ROOT
        c=yaml.safe_load((ROOT/'configs/splits.yaml').read_text())
        groups=[set(c[s]['families']) for s in ['development','validation','test']]
        self.assertFalse(groups[0]&groups[1] or groups[0]&groups[2] or groups[1]&groups[2])
        for s in ['development','validation']:
            self.assertNotIn('apache/airflow',c[s]['repos'])

    def test_api_cursor_resume_and_dedupe(self):
        class Response:
            status_code=200
            headers={}
            def __init__(self,rows,links):self.rows,self.links=rows,links
            def json(self):return self.rows
            def raise_for_status(self):pass
        issue=dict(id=1,number=1,title='One',user=None)
        second=dict(id=2,number=2,title='Two',user=None)
        responses=[Response([dict(id=99,pull_request={}),issue],{'next':{'url':'https://api.github.com/repositories/123/issues?after=cursor'}}),Response([issue,second],{})]
        class Session:
            headers={}
            def get(self,url,**kwargs):return responses.pop(0)
        with tempfile.TemporaryDirectory() as directory:
            client=GitHubSnapshot(Path(directory));client.session=Session()
            self.assertEqual([r['number'] for r in client.collect('a/b','issues',2)],[1,2])
            # No responses remain: second pass must be entirely checkpointed.
            self.assertEqual([r['number'] for r in client.collect('a/b','issues',2)],[1,2])

    def test_bm25_does_not_use_unseen_repo_statistics(self):
        from src.retrieval.snapshot_index import SnapshotIndex
        index=SnapshotIndex.__new__(SnapshotIndex)
        index.docs=[dict(repo='known/repo',id='a'),dict(repo='known/repo',id='b')]
        index.bm=dict(k1=1.5,b=0.75,lengths=[2,3],postings={'word':[[0,2]]})
        baseline=index.bm25('word','known/repo')
        index.docs.append(dict(repo='apache/airflow',id='test'))
        index.bm['lengths'].append(1000);index.bm['postings']['word'].append([2,900])
        self.assertEqual(index.bm25('word','known/repo'),baseline)


if __name__=='__main__':unittest.main()
