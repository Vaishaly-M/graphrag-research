"""Compare retained v1 on the same validation questions, never test/H."""
import yaml
from analysis.devval_inputs import input_path
from analysis.train_router_rebuild import validate_split
from analysis.routing_evaluation import routing_metrics
from src.routing.router import RouterV1
from src.ingest.storage import ROOT,read_rows,save,write_rows,digest


def main():
    config=yaml.safe_load((ROOT/'configs/splits.yaml').read_text())
    path=input_path(config,'T','validation');questions=read_rows(path)
    validate_split(questions,'validation',config)
    router=RouterV1();rows=[]
    for q in questions:
        rows.append(dict(question_id=q['question_id'],category=q['category'],gold_route=q['gold_route'],
                         repo=q['repo'],split='validation',question_set='T',**router.decide(q['question'],q['repo'])))
    write_rows(ROOT/'runs/router_v1/validation.jsonl',rows)
    result=routing_metrics(rows)
    save(ROOT/'runs/router_v1/validation_metrics.json',dict(result,source_sha256=digest(path)))
    print(result)


if __name__=='__main__':main()
