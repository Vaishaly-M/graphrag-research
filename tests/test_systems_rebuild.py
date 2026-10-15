import json
import pytest
from src.eval.latency import Timing
from src.eval.metrics import score
from src.systems.rebuild.shared import scoped_cypher,fuse
from src.systems.rebuild.engine import System,NAMES,configuration,best_of_three
from src.systems.rebuild.smoke import FixtureLLM,FixtureGraph,FixtureVector


@pytest.mark.parametrize('name',NAMES)
def test_five_question_smoke_each_system(name):
    from src.ingest.storage import ROOT,read_rows
    questions=read_rows(ROOT/'data/benchmark/template/development.jsonl')[:5]
    system=System(name,FixtureGraph(),FixtureVector(),FixtureLLM(),config=configuration(name),
                  router=lambda question,repo:'hybrid',
                  oracle_routes={(q['repo'],q['question']):q['gold_route'] for q in questions},
                  adaptive_evidence={(q['repo'],q['question']):[] for q in questions})
    for q in questions:
        answer=system.answer(q['question'],q['repo'],timing=Timing(retries=0))
        assert isinstance(answer['answer'],str)
        assert answer['abstained'] is True
        assert 'config_yaml' in answer
        if name=='langchain_graphrag':assert 'langchain:GraphCypherQAChain' in answer['retrieval_path']
        if name=='llamaindex_graphrag':assert 'llamaindex:TextToCypherRetriever' in answer['retrieval_path']


@pytest.mark.parametrize('query',[
    'MATCH (n:DLFile) DELETE n RETURN n',
    'MATCH (n:DLFile) RETURN n UNION MATCH (m:DLFile) RETURN m',
    'MATCH (n) RETURN n',
    'MATCH (n:DLFile {repo:"other"}) RETURN n',
    'MATCH (n:DLFile)-[*]->(m:DLFile) RETURN n',
    'MATCH (n:DLFile) WITH n MATCH (m:DLFile) RETURN m',
    'MATCH (n:DLFile) RETURN n LIMIT 1000',
])
def test_cypher_scope_rejects_unsupported_queries(query):
    with pytest.raises(ValueError):scoped_cypher(query)


def test_cypher_scopes_every_node_and_accepts_prefix():
    result=scoped_cypher('MATCH (c:DLCommit)-[:DL_MODIFIED_FILE]->(f:DLFile) WHERE c.sha STARTS WITH $sha RETURN f LIMIT 10')
    assert result.count('{repo:$repo, dataset:$dataset}')==2


def test_fusion_retains_distinct_chunks_for_same_entity():
    a=dict(id='file',text='first chunk');b=dict(id='file',text='second chunk')
    assert fuse([a],[b,a])==[a,b]


def test_fixed_graph_never_falls_back_and_hybrid_calls_both():
    class EmptyGraph(FixtureGraph):
        def execute(self,*args,**kwargs):return []
    class Vector(FixtureVector):
        calls=0
        def retrieve(self,*args,**kwargs):self.calls+=1;return super().retrieve(*args,**kwargs)
    vector=Vector()
    system=System('fixed_graph_rag',EmptyGraph(),vector,FixtureLLM(),config=configuration('fixed_graph_rag'))
    system.answer('unknown question','example/repo');assert vector.calls==0
    system=System('fixed_hybrid_rag',EmptyGraph(),vector,FixtureLLM(),config=configuration('fixed_hybrid_rag'))
    system.answer('unknown question','example/repo');assert vector.calls==1


def test_oracle_covers_adaptive_evidence_without_claiming_accuracy():
    graph,vector,llm=FixtureGraph(),FixtureVector(),FixtureLLM()
    adaptive=System('adaptive_hybrid_graphrag',graph,vector,llm,config=configuration('adaptive_hybrid_graphrag'),router=lambda question,repo:'hybrid')
    a=adaptive.answer('q','repo')
    # Include evidence from a stochastic Adaptive query not reproduced by the fixture.
    a['retrieved_evidence'].append(dict(id='extra',text='additional fact',repo='repo',source='graph'))
    a['ranked_evidence_ids'].append('extra')
    oracle=System('oracle_hybrid_rag',graph,vector,llm,config=configuration('oracle_hybrid_rag'),router=lambda question,repo:'hybrid',oracle_routes={('repo','q'):'graph'},adaptive_evidence={('repo','q'):a['retrieved_evidence']})
    o=oracle.answer('q','repo')
    assert set(a['ranked_evidence_ids'])<=set(o['ranked_evidence_ids'])
    assert o['oracle_adaptive_evidence_replay'] and o['route']=='hybrid'


def test_posthoc_oracle_ge_each_cached_candidate_including_adaptive_route():
    q=dict(question_set='T',gold_complete=True,answerable=True,gold_entities=['a'],gold_evidence_ids=['e'])
    def record(entities):return dict(predicted_entities=entities,abstained=False,ranked_evidence_ids=[],errors=[])
    candidates={'graph':record(['bad']),'vector':record(['a']),'hybrid':record(['a','extra'])}
    result=best_of_three(q,candidates)
    assert result['selected_route']=='vector'
    # Mathematical bound applies only when Adaptive reuses an exact candidate;
    # fresh stochastic generations are deliberately not asserted to be dominated.
    for candidate in candidates.values():
        assert result['metrics']['strict_accuracy']>=score(q,candidate)['strict_accuracy']
