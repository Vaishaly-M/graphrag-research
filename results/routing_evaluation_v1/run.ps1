$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research'
python -m scripts.prepare_routing_evaluation --verify --output-root 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1'
if ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }
python -m scripts.record_environment
if ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }
python -m src.systems.llamaindex_graphrag --benchmark-file 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\questions.csv' --output-dir 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\raw' --repeats 1
if ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }
python -m src.systems.fixed_graph_rag --benchmark-file 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\questions.csv' --output-dir 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\raw' --repeats 1
if ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }
python -m src.systems.oracle_hybrid_rag --benchmark-file 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\oracle_questions.csv' --output-dir 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\raw' --repeats 1
if ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }
python -m src.systems.adaptive_hybrid_graphrag --benchmark-file 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\questions.csv' --output-dir 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\raw' --repeats 1
if ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }
python -m src.systems.langchain_graphrag --benchmark-file 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\questions.csv' --output-dir 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\raw' --repeats 1
if ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }
python -m src.systems.fixed_hybrid_rag --benchmark-file 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\questions.csv' --output-dir 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\raw' --repeats 1
if ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }
python -m src.systems.plain_llm --benchmark-file 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\questions.csv' --output-dir 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\raw' --repeats 1
if ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }
python -m src.systems.vector_rag --benchmark-file 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\questions.csv' --output-dir 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\raw' --repeats 1
if ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }
python -m src.evaluation.routing_diagnostics --results-dir 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\raw' --output-dir 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\metrics' --repeats 1 --require-no-errors
if ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }
python -m src.evaluation.metrics --input-dir 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\raw' --output-dir 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\metrics' --benchmark-file data/benchmark/splits/hidden_test_answer_key.csv
if ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }
python -m src.evaluation.statistics --input 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\metrics\per_question_metrics.csv' --output-dir 'C:\Users\ADMIN\Documents\Sem\4-Research\My Research\Experiment\graphrag-research-starter\graphrag-research\results\routing_evaluation_v1\metrics'
if ($LASTEXITCODE -ne 0) { throw "Experiment step failed" }
