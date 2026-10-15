import numpy as np
import pytest
from src.routing.features import features,NAMES,question_text
from src.routing.router import policy,probabilities,RouterV1
from analysis.train_router_rebuild import validate_split,train
from analysis.routing_evaluation import replay,TAUS,routing_metrics


def test_features_are_question_only_and_remove_repo_slug():
    f=features('Who changed src/main.py in commit abcdef123456 across modules?','example/repo')
    assert list(f)==list(NAMES)
    assert f['sha']==f['file_path']==f['who']==1
    assert f['multi_hop_keywords']>0
    assert 'example/repo' not in question_text('in example/repo','example/repo')
    assert features('Find code in example/repo','example/repo')['file_path']==0


def test_policy_all_routes_and_threshold_boundary():
    for route in ['graph','vector','hybrid']:
        p={r:.1 for r in ['graph','vector','hybrid']};p[route]=.8
        assert policy(p,.8)['chosen_route']==route
        assert policy(p,.85)['chosen_route']=='hybrid'
    with pytest.raises(ValueError):policy({'graph':1},.5)


def test_missing_class_is_explicit_not_fabricated():
    artifact=dict(mean=[0],scale=[1],coef=[[2]],intercept=[0],classes=['graph','vector'],temperature=1)
    p=probabilities(np.array([[0.0]]),artifact)[0]
    assert p=={'graph':.5,'vector':.5,'hybrid':0}
    assert policy(p,.55)['chosen_route']=='hybrid'


def test_rejects_airflow_test_human_and_wrong_family():
    config=dict(unseen_repo='apache/airflow',development=dict(repos=['example/repo'],families=['dev']))
    row=dict(question_id='q',question_set='T',repo='example/repo',split='development',template_family='dev',gold_route='graph')
    validate_split([row],'development',config)
    for change in [dict(repo='apache/airflow'),dict(split='test'),dict(question_set='H'),dict(template_family='heldout')]:
        with pytest.raises(ValueError):validate_split([dict(row,**change)],'development',config)


def test_grouped_calibration_only_uses_training_rows():
    rows=[dict(question_id=f'd-{repo}-{route}',repo=repo,gold_route=route,category='unit')
          for repo in ['a','b','c','d'] for route in ['graph','vector','hybrid']]
    x=np.tile(np.eye(3),(4,1))
    val=[dict(question_id=f'v-{route}',repo='a',gold_route=route,category='unit') for route in ['graph','vector','hybrid']]
    selected,grid,missing=train(x,rows,np.eye(3),val)
    assert not missing and len(grid)==27
    assert selected['tau'] in TAUS
    for fold in selected['folds']:
        assert not set(fold['fit_ids'])&set(fold['calibration_ids'])
        assert all(i.startswith('d-') for i in fold['fit_ids']+fold['calibration_ids'])
    with pytest.raises(ValueError,match='Missing'):
        train(x[:2],rows[:2],np.eye(3),val)


def test_cached_sweep_uses_only_saved_answers_and_validates_alignment():
    q=dict(question_id='q',repo='example/repo',split='validation',question_set='T',category='unit',gold_route='graph',
           gold_complete=True,answerable=True,gold_entities=['answer'],gold_evidence_ids=['e'])
    decision=dict(question_id='q',probabilities={'graph':.7,'vector':.2,'hybrid':.1})
    shared=dict(model='fixture',temperature=.2,max_output_tokens=1024,answer_prompt_sha256='hash',dataset='unit',vector={},graph={},fusion='union')
    def row(system,entities):return dict(question_id='q',repo=q['repo'],split='validation',question_set='T',system=system,
        model='fixture',run_id='unit',dry_run=True,config={'system_config':shared},predicted_entities=entities,
        abstained=False,ranked_evidence_ids=[],errors=[])
    caches={'graph':[row('fixed_graph_rag',['answer'])],'vector':[row('vector_rag',['wrong'])],
            'hybrid':[row('fixed_hybrid_rag',['wrong'])]}
    results=replay([q],[decision],caches)
    assert len(results)==9 and results[0]['strict_accuracy']==1 and results[-1]['strict_accuracy']==0
    with pytest.raises(ValueError):replay([q],[decision],dict(caches,hybrid=[]))


def test_confusion_and_absent_support_are_not_hidden():
    report=routing_metrics([dict(gold_route='graph',chosen_route='hybrid',category='unit')])
    assert report['accuracy']==0 and report['confusion_matrix']['graph']['hybrid']==1
    assert report['confusion_matrix']['vector']=={'graph':0,'vector':0,'hybrid':0}


def test_v1_remains_the_original_rule_implementation():
    from src.systems.router import classify
    text='Explain a function'
    decision=RouterV1().decide(text,'repo')
    assert decision['chosen_route']==classify(text).retrieval_plan
    assert decision['probabilities'] is None


def test_adaptive_logs_router_decision():
    from src.systems.rebuild.engine import System,configuration
    from src.systems.rebuild.smoke import FixtureLLM,FixtureGraph,FixtureVector
    class Router:
        def decide(self,question,repo):
            return dict(features={'who':1},probabilities={'graph':.8,'vector':.1,'hybrid':.1},
                        chosen_route='graph',predicted_route='graph',tau=.55)
    system=System('adaptive_hybrid_graphrag',FixtureGraph(),FixtureVector(),FixtureLLM(),
                  config=configuration('adaptive_hybrid_graphrag'),router=Router())
    result=system.answer('Who changed this?','repo')
    assert result['routing']['tau']==.55
    assert result['routing']['probabilities']['graph']==.8
    assert result['route']=='graph'
