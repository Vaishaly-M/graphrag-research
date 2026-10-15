PYTHON ?= python
.NOTPARALLEL:

.PHONY: all snapshots graph indexes splits validate test benchmark-stats eval-dryrun phase5 vector-tuning selected-vector systems-smoke systems-dryrun
all: snapshots graph indexes splits validate

snapshots:
	$(PYTHON) -B -m src.ingest.synthetic_snapshot
	$(PYTHON) -B -m src.ingest.snapshots

graph:
	$(PYTHON) -B -m src.kg.build
	$(PYTHON) -B -m src.kg.neo4j_store

indexes:
	$(PYTHON) -B -m src.retrieval.build_indexes

splits:
	$(PYTHON) -B -m analysis.build_splits

validate:
	$(PYTHON) -B -m analysis.validate_data_layer --live
	$(PYTHON) -B -m analysis.validate_indexes
	$(PYTHON) -B -m analysis.report_data_layer

test:
	$(PYTHON) -B -m pytest tests

phase5: vector-tuning selected-vector systems-smoke

vector-tuning:
	$(PYTHON) -B -m analysis.tune_vector_rebuild

selected-vector:
	$(PYTHON) -B -m analysis.publish_selected_vector

systems-smoke:
	$(PYTHON) -B -m src.systems.rebuild.smoke --run-id phase5-live-1

systems-dryrun:
	$(PYTHON) -B -m src.systems.rebuild.smoke --dry-run --run-id phase5-dry-final

benchmark-stats:
	$(PYTHON) -B -m analysis.benchmark_stats --require-complete

eval-dryrun:
	$(PYTHON) -B -m src.eval.harness --questions data/benchmark/template/development.jsonl --output runs/dryrun/phase4/plain.jsonl --run-id phase4-dev-1 --system plain_llm --dry-run --limit 10
	$(PYTHON) -B -m src.eval.harness --questions data/benchmark/template/development.jsonl --output runs/dryrun/phase4/stub.jsonl --run-id phase4-dev-1 --system stub --dry-run --limit 10
