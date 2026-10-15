import json
import math

import pytest

from src.eval.metrics import Normalization, correctness, normalize, retrieval, summarize
from src.eval.stats import continuous, holm, mcnemar
from src.eval.latency import RetryableError, Timing
from src.eval.faithfulness import evaluate
from src.eval.harness import read_log, run
from src.eval.systems import PlainLLM, Stub, fixture_transport


@pytest.mark.parametrize('pred,gold,answerable,abstained,kind,p,r,f,strict,lenient', [
    (['a','b','c','d'], ['a','b'], True, False, 'set', .5, 1, 2/3, 0, 1),
    (['a','b','c','d','e'], ['a','b','c','d'], True, False, 'set', .8, 1, 8/9, 1, 1),
    (['a','extra'], ['a'], True, False, 'single', .5, 1, 2/3, 0, 1),
    ([], [], False, True, 'set', None, None, None, 1, 1),
    ([], ['a'], True, True, 'set', 0, 0, 0, 0, 0),
])
def test_worked_examples(pred,gold,answerable,abstained,kind,p,r,f,strict,lenient):
    result = correctness(pred,gold,answerable=answerable,abstained=abstained,answer_kind=kind)
    for key, expected in [('entity_precision',p),('entity_recall',r),('entity_f1',f)]:
        assert result[key] is None if expected is None else result[key] == pytest.approx(expected)
    assert result['strict_accuracy'] == strict
    assert result['lenient_coverage'] == lenient


def test_normalization_and_threshold():
    assert normalize(' Issue #0012 ') == normalize('#12') == normalize('12')
    assert normalize(r'.\src\Owner.java') == 'src/Owner.java'
    assert normalize('Owner.java') != normalize('owner.java')
    assert normalize('Owner',Normalization(case_sensitive=False)) == 'owner'
    sha='abcdef012345'+'0'*28
    assert normalize(sha) == normalize(sha[:12].upper())
    assert normalize(sha[:7]) != normalize(sha)
    with pytest.raises(ValueError,match='Ambiguous'):
        correctness([sha], ['abcdef012345'+'1'*28], answerable=True)
    assert correctness(['a','a'],['a'],answerable=True)['entity_precision'] == 1
    assert correctness(['a','b'],['a'],answerable=True,precision_threshold=.5)['strict_accuracy'] == 1
    assert correctness([],[],answerable=True)['strict_accuracy'] == 1
    assert correctness([],[],answerable=True,abstained=True)['strict_accuracy'] == 0
    assert correctness([],[],answerable=False)['strict_accuracy'] == 0
    with pytest.raises(ValueError):
        correctness([],[],answerable=None)


def test_ranked_retrieval():
    result=retrieval(['wrong','a','a','b'],['a','b'],k=2)
    assert result['evidence_recall@2'] == .5
    assert result['mrr'] == .5
    assert result['ndcg@10'] == pytest.approx((1/math.log2(3)+.5)/(1+1/math.log2(3)))
    assert retrieval([],['a'])['mrr'] == 0
    assert retrieval(None,['a'])['mrr'] is None
    assert retrieval(['a'],[])['mrr'] is None


def test_statistics():
    assert mcnemar([1,1,1,1],[0,0,0,0])['p_value'] == .125
    assert mcnemar([1],[1])['p_value'] == 1
    assert holm([.01,.04,.03]) == pytest.approx([.03,.06,.06])
    result=continuous([2,3,4,5,6,7],[1,2,3,4,5,6])
    assert result['rank_biserial'] == 1
    assert result['bootstrap_ci'] == [1,1]
    assert result['resamples'] == 2000
    assert continuous([1,2],[1,2])['wilcoxon_p'] == 1
    assert continuous([1,1],[2,2])['rank_biserial'] == -1
    with pytest.raises(ValueError):
        continuous([1],[1,2])


def test_retry_wait_not_in_stage_timing():
    now=[0.0]; events=[]; attempts=[]
    timing=Timing(clock=lambda:now[0],sleep=lambda s:now.__setitem__(0,now[0]+s),
                  retries=1,backoff=10,event_sink=events.append)
    def operation():
        now[0]+=2
        attempts.append(1)
        if len(attempts)==1:
            raise RetryableError('redacted',status=429)
        return 'ok'
    assert timing.call('generation',operation)=='ok'
    result=timing.result(now[0])
    assert result['generation_seconds']==result['end_to_end_seconds']==4
    assert result['wall_seconds']==14
    assert result['retry_count']==1 and result['contaminated'] and result['rate_limit']
    assert len(events)==1 and events[0]['retry_scheduled']


def test_timeout_contaminates_without_retry():
    timing=Timing(retries=0)
    with pytest.raises(TimeoutError):
        timing.call('generation',lambda:(_ for _ in ()).throw(TimeoutError()))
    assert timing.result(0)['contaminated']
    assert timing.result(0)['timeout']


def question():
    return dict(question_id='dev-1',question='List files',question_set='T',repo='example/repo',
                split='development',gold_complete=True,answerable=True,
                gold_entities=['a'],gold_evidence_ids=['e'])


def test_resume_and_configuration_guard(tmp_path):
    path=tmp_path/'raw.jsonl'
    kwargs=dict(run_id='one',split='development',question_set='T',dry_run=True)
    run(Stub(),[question()],path,**kwargs)
    with path.open('ab') as stream:stream.write(b'{"partial":')
    run(Stub(),[question()],path,**kwargs)
    assert len(read_log(path))==1
    assert path.with_suffix('.metrics.md').exists()
    with pytest.raises(ValueError,match='another configuration'):
        run(Stub(),[question()],path,**dict(kwargs,run_id='two'))
    with pytest.raises(ValueError,match='Held-out'):
        run(Stub(),[dict(question(),repo='apache/airflow')],tmp_path/'bad',**kwargs)
    with pytest.raises(ValueError,match='Unverified'):
        run(Stub(),[dict(question(),gold_complete=False)],tmp_path/'bad',**kwargs)


def test_plain_adapter_gets_no_gold(tmp_path):
    prompts=[]
    def transport(prompt,**settings):
        prompts.append(prompt)
        return fixture_transport(prompt,**settings)
    q=dict(question(),gold_entities=['secret-gold-marker'])
    run(PlainLLM(transport,'fixture'),[q],tmp_path/'plain.jsonl',run_id='x',
        split='development',question_set='T',dry_run=True)
    assert 'secret-gold-marker' not in prompts[0]


def test_contaminated_kept_for_accuracy():
    base=dict(metrics={'strict_accuracy':1},answerable=False,abstained=True,errors=[],
              timings=dict(contaminated=True,retrieval_seconds=1,generation_seconds=2,end_to_end_seconds=3))
    summary=summarize([base])
    assert summary['strict_accuracy']==1
    assert summary['not_found_rate']==1
    assert summary['end_to_end_seconds'] is None
    assert summary['latency_excluded_count']==1
    replay=dict(base,oracle_adaptive_evidence_replay=True,
                timings=dict(base['timings'],contaminated=False))
    assert summarize([replay])['latency_clean_count']==0
    assert summarize([replay])['strict_accuracy']==1


def test_judge_family_and_missing_hooks():
    assert evaluate('answer',[])['faithfulness'] is None
    class Extractor:
        def extract(self,answer):return [answer]
    class Judge:
        model_family='gemini'
        def judge(self,claim,evidence):return {'label':'supported'}
    with pytest.raises(ValueError):
        evaluate('answer',[],extractor=Extractor(),judge=Judge(),generator_families=['Gemini','Qwen'])
