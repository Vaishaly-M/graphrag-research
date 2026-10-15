import pytest
from analysis.devval_inputs import input_path
from analysis.devval_supplement import FAMILIES
from analysis.benchmark_gold import TEMPLATES


def test_supplement_families_are_distinct_and_routes_fixed():
    dev=set(FAMILIES['development']);val=set(FAMILIES['validation'])
    assert not dev & val
    assert not (dev|val) & set(TEMPLATES)
    assert FAMILIES['development']['commit_file_tail'][2]=='hybrid'
    assert {v[2] for v in FAMILIES['validation'].values()}=={'vector','hybrid'}


def test_input_resolver_rejects_heldout_inputs():
    for label,split in [('H','development'),('T','test'),('P','test')]:
        with pytest.raises(ValueError):input_path({},label,split)
    path=input_path({'devval_supplement':{'directory':'data/benchmark/devval-supplement-1'}},'P','validation')
    assert path.as_posix().endswith('devval-supplement-1/paraphrase/validation.jsonl')
