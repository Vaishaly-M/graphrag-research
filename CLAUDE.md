# Project: Adaptive Hybrid GraphRAG for repository-aware QA (revision v2)

## Goal
Redo the whole experiment from the beginning to address peer-review comments. Hypothesis under test:
"Query-level adaptive routing between graph, vector and hybrid retrieval is better than fixed single-strategy
retrieval and other compared systems." This is a hypothesis to TEST, not a result to force. Report whatever the
data shows. If Adaptive does not beat a baseline on a metric, we write that honestly and discuss it.

## Stack
Neo4j (AuraDB for the main graph; local Docker Neo4j for scalability), Gemini 2.5 Flash as the main generator,
FAISS + sentence-transformers, BM25, LangChain, LlamaIndex, PyDriller, a second open model (qwen2.5:14b via Ollama).
Five repos: Spring PetClinic, OpenMRS Core, eShop (eShopOnContainers), Apache Airflow, MLflow, plus one controlled
synthetic repo. Airflow is the UNSEEN repository: never used for development, tuning or router training.

## The 8 systems (all behind one interface: answer(question, repo) -> AnswerRecord)
1 Plain LLM  2 Vector RAG (tuned)  3 LangChain GraphRAG (real LangChain graph QA chain)
4 LlamaIndex GraphRAG (real LlamaIndex graph/Text2Cypher retriever)  5 Fixed Graph RAG
6 Fixed Hybrid RAG  7 Oracle Hybrid RAG  8 Adaptive Hybrid GraphRAG

## Non-negotiable rules
- Fairness: Fixed Graph, Fixed Hybrid, Oracle and Adaptive share the SAME graph retriever (templates + LLM-generated
  read-only Cypher + validation), the SAME vector retriever, the SAME evidence fusion, the SAME prompt and the SAME
  LLM settings (temperature 0.2, max 1024 tokens). The ONLY difference is the routing policy.
- Splits: development / validation / test are fixed once (seed 42), counts are stated once, and EVERY table is
  computed on the same test set unless a table explicitly says otherwise. No tuning on test. No peeking.
- Question sets are reported separately, never merged: (T) template-generated, (P) paraphrased,
  (H) human-written by 5 independent people. Gold answers for H are verified by humans, not trusted from an LLM.
- Freeze rule: before any test-set run, commit and `git tag freeze-v2`. After the tag, code that affects results
  may not change. If a bug is found, fix it, bump the tag (freeze-v2.1) and rerun everything affected.
- Every run writes raw per-question JSONL (question id, system, route, retrieved evidence ids, answer, tokens,
  timings, retries, errors, config hash, seed, model name). Metrics are computed only from these files by scripts.
- Cache LLM and retrieval outputs keyed by (system, model, config hash, question id, run id) so reruns are cheap and
  threshold/ablation sweeps replay cached outputs instead of calling the API again.
- Never hand-edit result numbers. Every number in the paper must be produced by a script in /analysis and be
  reproducible with one command (make all).
- Never print or commit API keys. Read them from .env.
- When uncertain about a design choice, write the options and your recommendation in DECISIONS.md and ask me
  before proceeding.
- Honest reporting: log every deviation in DECISIONS.md.

## Repo layout to create
configs/  data/{snapshots,graph_exports,benchmark/{template,paraphrase,human},annotations}/  src/{ingest,kg,retrieval,
routing,systems,eval,scalability}/  runs/{gemini,qwen}/  analysis/  reports/  tests/  DECISIONS.md  AUDIT.md  Makefile