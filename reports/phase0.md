# Phase 0 ? diagnosis only

Audit date: 2026-10-06 (Asia/Colombo). Current HEAD: `45f8ac56c66d0232f3a05312e58015a1efbc94cd`. No experiment, graph/index rebuild, code fix, gold edit, or split change was performed. This report is the only file created. Existing `.review_tools` deletions were already present. The human CSV is present at `data/benchmark/Human Written Question.csv`; its validation is reserved for Phase 1.

The reviewer's numerical results match `results/final_evaluation_metrics/summary_metrics.csv`, backed by `results/final_evaluation/*_results.csv`. Other results folders are different experiments and must not be pooled. For example, `results/summary_metrics.csv` mixes hundreds of rows with missing references and has different denominators. Source citations below refer to the current checkout; saved rows are historical observations, not proof that today's code generated them. CSV record numbers are data records excluding the header; question IDs are the stable locator when quoted fields contain newlines.

## Findings ranked by impact

1. **Critical ? the main result does not establish the adaptive-routing claim.** Vector is unreachable under the default router; all adaptive answers in the main run are deterministic graph answers. Adaptive and Fixed Hybrid return exactly the same answers. Their 96.69% metric checks identifier containment, not all required facts or contradictions.
2. **Critical ? execution accounting and latency are not auditable.** Timing combines retrieval, API time and sleeps; retries have no event log; resumed runs erase previous error rows; summary metrics exclude failed rows. No run-bound configuration snapshot establishes the settings of the quoted results.
3. **High ? ?Oracle? is not an oracle upper bound.** It routes by labels plus template overrides, does not compare route outcomes, and lacks adaptive graph recovery. Its single deficit to Fixed Hybrid is explained by a historical apostrophe parser error and missing recovery.
4. **High ? entity/fact metrics are inconsistent with the accuracy construct.** Regex extraction misses bare issue numbers/titles and breaks composite entities; fact matching compares whole answers against each fact. Equal F1 can mask different answers and errors.
5. **High ? ablations mostly bypass the mechanisms being tested.** Templates directly supply answers; fixed-hop hints and fusion changes often cannot affect them. The ?all variants? premise has one exception: no-graph scores differently.
6. **High ? framework baseline names are unsupported by their implementations.** Both are custom Cypher-QA pipelines without framework calls.
7. **Medium ? vector retrieval has candidate-filtering and provenance limitations.** It uses repository text, not a graph dump, but filters only the global top 50 and includes synthetic documents. Actual embedding-build provenance is absent.
8. **Medium ? scalability does not support monotonic scaling conclusions.** Two sizes, five repeats of the same query, no saved plans/raw timings, and no end-to-end generation or memory measurements.
9. **Reporting correction ? expected regression failures are already separate from passes in the current report.** A successful process exit is not a 100% pass rate.

## 1. Router: why vector is never selected

Code path: `adaptive_hybrid_graphrag.py:204-207` calls `classify(question)` then `_resolve_route`; `router.py:96-143` calls the query registry before keyword heuristics; `router.py:146-178` applies the confidence policy. Registered templates receive 0.95; their routes in `query_registry.py:46-383` are exclusively graph/hybrid. Fragment/documentation templates explicitly return hybrid (`query_registry.py:63-81`). Multi-hop cues receive 0.75 and hybrid; both keyword families 0.65 and hybrid; a vector-only keyword signal receives 0.55. The configured high threshold is 0.85 and medium threshold 0.60 (`config/experiment.yaml`, router section). Anything below 0.85 becomes hybrid; below 0.60 also enables strict validation.

Thus **vector is unreachable through the default classifier**, not merely absent by chance. The vector execution branch exists and can be forced by the no-graph ablation (`adaptive_hybrid_graphrag.py:193-202`) or made reachable by changing policy/configuration later. Medium threshold only affects validation, not a vector confidence band.

Saved adaptive rows: graph 127, hybrid 115, vector 0. All 242 have `answer_generation_mode=deterministic_graph`. Example `code_retrieval-026` has a fragment template and takes hybrid despite its benchmark vector label. The reported 100% routing accuracy is additionally inflated by `metrics.py:1504-1520`: for code_retrieval and documentation_lookup it accepts all three routes as correct. Thus all 71 vector-labelled cases count as route-correct despite selecting hybrid. Literal label agreement is only 171/242 (70.66%). This metric cannot establish vector routing or cheapest-correct routing on human questions.

## 2. Oracle routes, retriever, fallback and deficit

`oracle_hybrid_rag.py:58-76` loads benchmark labels; `:97-120` widens a label to hybrid when the registered template is hybrid. Saved pairs are graph?graph 127, vector?hybrid 71, hybrid?hybrid 44. **All 71 vector-labelled questions actually use hybrid.**

It uses the same `VectorStore.search` implementation as Vector RAG: Oracle calls `run_vector_query` (`retrieval_core.py:146-155`), while `vector_rag.py:10` calls it directly, k=10. Both derive the repository from ?repository owner/name?. Error handling differs: the wrapper catches exceptions into `retrieval_errors`; the baseline lets exceptions reach the runner. Oracle then fuses graph/vector evidence and preferentially returns graph `answer` fields (`oracle_hybrid_rag.py:131-170`); the baseline passes raw vector result dictionaries to an LLM. Same retriever does not mean same answering pipeline.

Oracle has no empty-template?LLM-Cypher recovery ladder. `graph_side` chooses either the template or generated Cypher; empty rows do not trigger a second query. Unknown-label default-hybrid is a lookup default, not evidence-triggered recovery. Adaptive has actual recovery (`adaptive_hybrid_graphrag.py:119-167`, `:214-232`).

The only answer difference between Fixed Hybrid and Oracle is `issue_pr_analysis-030`: ?What is the issue number for 'Can't find API Getway project' in repository dotnet/eShop?? Oracle saved parameters `{"repo":"dotnet/eShop","title":"Can"}`, zero graph rows, zero vector rows, and `Insufficient repository evidence.` Fixed Hybrid saved the same bad title, retrieved 10 vector rows, and answered `475`. Adaptive logged an invalid empty registered-template attempt followed by valid LLM Cypher, and answered `475`. Thus Fixed Hybrid has 234/242 legacy-correct answers and Oracle 233/242.

The current title parser (`query_registry.py:235-259`) anchors the final delimiter to the repository clause and handles the apostrophe. This is demonstrable source/result drift; no additional parser fix was made in Phase 0. Oracle still is not a per-question outcome maximum. Its comment that hybrid is a strict superset does not guarantee answer dominance: fusion truncates to 16 evidence items (`retrieval_core.py:208-253`) and answer generation can change.

## 3. Raw answers, error status and timing

The first ten raw answers for each baseline are printed verbatim in Appendix A. Neither baseline has empty answers or answers beginning with Error/Timeout/Exception/Traceback in this main CSV; both have zero populated `error` fields. Plain's first ten are epistemic abstentions, not transport errors. Vector has 209 exact `Insufficient repository evidence.` answers and 33 other answers. The stored abstention classifier marks 241 Plain answers and 209 Vector answers as abstentions. Its labeling is heuristic, not human adjudication.

Plain's prompt explicitly prohibits invented repository-specific details and asks it to state insufficient information (`plain_llm.py:26-41`); a very low answer rate is unsurprising for questions requiring private snapshot details. Vector's weak performance is mostly abstention, not empty/error text. One early positive example is `documentation_lookup-029`, answered `airflow-core/newsfragments/62487.significant.rst`.

`BaseSystem.run` times the entire `self.answer()` call (`base.py:420-453`). This includes query embedding, first-search disk index loading, graph/vector retrieval, LLM generation, pacing sleeps (`llm.py:97-103`) and application retries (`llm.py:120-127`; `common.py:212-268`). Construction/model loading happens before this timer. Current retry defaults are six total attempts, exponential delay 1/2/4/8/16 seconds plus jitter before the last attempt, with larger provider retry-after honored. Current RPM=10 implies up to six seconds pacing; that alone does not explain ~175-second rows. There is no per-call stage timing, retry count or SDK-attempt trace to attribute the historical ~95/~177-second means.

Searched available `.log`/`.txt` files in results for retry/rate-limit/timeout/error evidence. `results/llamaindex_run_log.txt:106-117` records terminal `RemoteProtocolError: Server disconnected without sending a response.` for several questions, including documentation_lookup-015 and structure-017. Its matching current main CSV has no errors. This establishes differing execution histories, not a measured retry count. Ablation stderr contains model-loading/HF warnings; no usable Plain/Vector per-attempt retry trace was found. **Retries/sleeps may be included; their contribution cannot be recovered from these artifacts.**

Failure bugs: `llm.py:115` converts missing response text to an empty string without raising. `base.py:433` marks a returned empty answer error-free. `base.py:343-356` deletes prior failed rows on resume. `metrics.py:1539-1548` recognizes only the top-level error field; swallowed retrieval errors can become an abstention. `metrics.py:1824-1885` averages accuracy and latency over successful rows, excluding failures rather than counting their zero accuracy. These violate the requested future protocol. Exception text is stored separately from answer in the runner; this part is correct.

The runner has repeats but defaults to one, does not discard warm-up, and writes no required run-bound config snapshot. All main CSV rows have run_id=1. `results/environment_manifest.json` is a separate environment artifact with null git_commit; it does not bind model, seed, thresholds and index provenance to each run. Its model is gemini-3.1-flash-lite-preview and RPM is 10, but those cannot be asserted as verified settings for every saved call.

## 4. What the vector index contains

`vector_store.py:9-22`: chunks are **1200 characters**, overlap 180 characters, after whitespace normalization (not 1200 tokens). Default k=10. `:25-45`: model defaults to `sentence-transformers/all-MiniLM-L6-v2` with EMBEDDING_MODEL override; normalized embeddings in FAISS IndexFlatIP. It serializes Repository/Path/Number/Title/Author metadata plus content/message/body from `files.jsonl`, `commits.jsonl`, `issues.jsonl`, `pulls.jsonl`. It prefers nonempty data/processed over data/raw and additionally includes data/synthetic. This is repository artifact text, not a flattened graph dump. Graph loading also defaults to processed input (`kg_construction/load_graph.py:998-1017`), but synthetic inclusion policies differ; identical corpus membership is not established.

The persisted docs.json currently has 131,179 chunks: 116,923 file, 6,308 pull_request, 4,559 commit, 3,389 issue. Repository counts: apache/airflow 72,800; mlflow/mlflow 38,847; openmrs/openmrs-core 12,427; dotnet/eShop 4,707; spring-projects/spring-petclinic 2,098; synthetic-org/platform 300. First document is `apache/airflow:file:asf.yaml:chunk:0`, with license/YAML source text. These are current document counts, not a historical build manifest.

`search` (`:48-58`) embeds each question, searches global top min(k*5, corpus size), then applies repo/kind filtering. For k=10 only 50 global candidates are considered, so the repository filter can return fewer than 10 or none even when the requested repo has relevant documents. The regex filter only recognizes the literal repository clause; other wording may run globally. No BM25/reranker is implemented here.

**No per-query index rebuilding:** `src/build_vector_index.py:1-2` builds explicitly; `search` lazily loads the persisted index once per VectorStore instance and then reuses it. Query embedding is per-query. The stored index lacks a build-settings manifest, so current code/default model cannot prove its historical model/chunk settings.

## 5. Accuracy, entity F1 and required-fact coverage

Appendix B contains the exact current scoring functions, extraction regexes, and call-site wiring. Accuracy checks that **all expected entity strings occur somewhere in the answer**, not that required facts are present or that conflicting entities are absent. It first uses substring containment, which also weakens boundary checking. F1 instead compares exact normalized entity sets from a regex extractor (or explicit predicted_entities). Required-fact coverage independently uses bidirectional containment, token-subset and overlap heuristics, comparing each fact with the whole answer. It is a lexical heuristic despite its semantic wording.

Adaptive's 234/242 = 96.69% accuracy and 50% mean fact coverage measure different conditions. Example `dependency_analysis-040`: the answer lists all ten expected file paths and receives accuracy=1, entity F1=1, fact coverage=0. Each fact also names the commit/repository. Comparing a ten-path answer with one individual fact misses both concise-answer shortcuts and dilutes overlap. This is a scoring inconsistency; it is not grounds to edit the gold facts. `issue_pr_analysis-004` gets accuracy=1 but entity F1=0 and fact coverage=0: prose issue titles are not handled as complete entities by the extractor.

Across Adaptive, Fixed Graph, Fixed Hybrid and Oracle, extracted entity lists are identical on all 242 questions. Adaptive and Fixed Hybrid have identical raw answers on all 242; Fixed Graph and Oracle match Adaptive on 241. The remaining question is issue_pr_analysis-030: `extract_entities("475") == []`, just as for the abstention. This fully explains their equal 51.354593% F1 without assuming metrics were copied.

Entity extraction has **no variant argument or branch** (`metrics.py:553-576`, `:1348-1351`); it depends on answer text unless explicit predicted_entities is supplied. These raw CSVs do not supply that field. Bare numbers, full issue titles and typed composite IDs are poorly aligned with the expected-entity schema. SYMBOL_RE can additionally treat quoted dictionary keys as entities.

Ablations: all variants except no_graph have 36.781609% F1; no_graph has 10.344828%. Most variants return exactly the same 29 answers as full_system, all in deterministic_graph mode. no_templates returns only 11 identical answers and 14 identical extracted lists, but its per-question F1 still matches on every question: changed extractions mostly remain wrong against the exact gold sets. Example issue_pr_analysis-028 returns `2157` instead of the gold title `Entity relationships should be modeled with fetch type LAZY`; both the baseline title extraction and bare-number extraction yield F1=0, masking the new error. no_templates accuracy drops to 25/29 despite unchanged F1.

Fixed-hop only changes a generated-Cypher prompt hint (`adaptive_hybrid_graphrag.py:89`); successful template Cypher bypasses it. Direct graph answers are selected before fused LLM answering (`:247-259`), so fusion weights and removing vector retrieval often cannot alter answers. `scripts/run_ablations.ps1:12-14` defaults to the dev split. These runs do not test held-out ablation performance.

Plain LLM evidence precision/recall/MRR are saved as zero, although retrieval is structurally absent. `metrics.py:820-882` has no system-applicability gate. They should be N/A under the requested protocol, not failures of retrieval.

## 6. Framework baselines

`langchain_graphrag.py:1-49` imports the project's Graph/Gemini/retrieval helpers and runs LLM-generated Cypher followed by LLM answering. `llamaindex_graphrag.py:1-53` does the same with a property-graph preamble and different evidence keys. Neither imports or calls LangChain/LlamaIndex APIs. Installed packages in an environment manifest are not evidence of use. These are custom Cypher-QA baselines with misleading system names; rename or implement real integrations in Phase 3.

## 7. Regression accounting

`regression_check.py:143-155` labels failures in expected-fail systems as EXPECTED_FAIL, increments total_failures, and increments unexpected_failures only for other failures. `:178-187` exits nonzero only for unexpected failures. The saved report has **43 PASS, 13 EXPECTED_FAIL, 0 FAIL**, out of 56 checks. Expected failures are not passes and must not be included in a claimed pass count. Current JSON does not count them as PASS; interpreting exit code zero as all checks passed would be the reporting bug. Plain accounts for seven expected failures, Vector for six; Vector passes issue_pr_analysis-009. Broad system-level expected-failure exemption also risks hiding unrelated failures.

## 8. Scalability anomaly

`results/scalability.csv` records 1-hop median 0.2435894 s at size 1000 and 0.1748003 s at 5000; IQRs are 0.0395298 and 0.0257853 s. A larger graph being faster in these measurements is observed, but **the cause cannot be uniquely determined** without raw times, plans and server state. Connection/server cache/load and sequential-size warm-up are plausible explanations, not proven findings. The environment manifest identifies Neo4j Aura; no run-bound manifest proves the exact deployment for this CSV.

Current code creates id indexes on all four synthetic labels (`generate_and_measure.py:58-70`) and runs one discarded warm-up plus five measured repetitions (`:44-45`, `:133-143`). It does not explicitly await indexes or save EXPLAIN/PROFILE plans, so actual index use in the historical run is unverified. The 1-hop query starts at Repository id=0, traverses CONTAINS_FILE, and filters f.bucket=42; bucket itself is not indexed. Each size repeats one query of each shape, not 30+ diverse queries. Ascending sizes share a driver and runtime (`:298-309`).

The `nodes` field actually names the file count. Total synthetic nodes are size + size//20 commits + size//200 developers + 1 repository: 1,056 and 5,276 here. The measured vector workload uses random 384-dimensional vectors, not repository embedding/generation. Query timers include graph round trip/materialization but no LLM generation, and no memory metric is recorded. These results cannot establish end-to-end scalability or an inverse size/latency trend.

## Phase boundary

Phase 0 is complete. No fixes or new experiment runs have been performed. Phase 1 is pending explicit user confirmation. Gold answers remain untouched.


## Appendix A ? 10 unmodified raw answers per baseline

### plain_llm

Source: `results/final_evaluation/plain_llm_results.csv`, first ten data records. Fences contain exact answer values.

Record 1; question `dependency_analysis-002`; latency 169.834561 s; error field empty.

```text
The available information is insufficient to determine which files were modified by commit `apache/airflow:commit:fce0bf3cb2b181d0f826b74500cd94d8e6feabc6`, as repository retrieval and external evidence are not accessible.
```

Record 2; question `documentation_lookup-022`; latency 175.714724 s; error field empty.

```text
Based on the provided information, the available information is insufficient to determine which documentation file in the repository apache/airflow contains the specified text.
```

Record 3; question `code_retrieval-026`; latency 175.703545 s; error field empty.

```text
Based on the provided information, the available information is insufficient to determine which source file in the `apache/airflow` repository contains the specified code fragment, as no repository retrieval or source-code search tools are accessible.
```

Record 4; question `dependency_analysis-040`; latency 175.450734 s; error field empty.

```text
The available information is insufficient to determine which files were modified by commit openmrs/openmrs-core:commit:9b451fb6549852aa0f11a2362820a34f83427d18.
```

Record 5; question `dependency_analysis-027`; latency 175.442149 s; error field empty.

```text
Based on the provided information, the available information is insufficient to determine which files were modified by commit `apache/airflow:commit:e6f5eed3ec9499aa1a91d5918ece2c9632526e73`.
```

Record 6; question `code_retrieval-024`; latency 175.785443 s; error field empty.

```text
Based on the provided information and general knowledge, the available information is insufficient to identify the specific source file in the `apache/airflow` repository containing the code fragment `batch_op.add_column(sa.Column("triggering_user_name", sa.String(length=512), nullable=True))`.
```

Record 7; question `dependency_analysis-012`; latency 176.389994 s; error field empty.

```text
The available information is insufficient to determine which files were modified by commit `742a5808659e72889e08eb719a0ef3d4f690f0bd` in repository `openmrs/openmrs-core`.
```

Record 8; question `issue_pr_analysis-004`; latency 175.481771 s; error field empty.

```text
The available information is insufficient to provide the titles of the open issues in the `apache/airflow` repository, as I do not have real-time access to external repositories or the internet.
```

Record 9; question `documentation_lookup-029`; latency 175.535257 s; error field empty.

```text
Based on the provided information, the available information is insufficient to determine which documentation file in the repository apache/airflow contains the specified text.
```

Record 10; question `code_retrieval-012`; latency 175.434805 s; error field empty.

```text
Based on the provided information and general knowledge, the available information is insufficient to identify the specific source file in the `apache/airflow` repository containing that exact code fragment.
```

### vector_rag

Source: `results/final_evaluation/vector_rag_results.csv`, first ten data records. Fences contain exact answer values.

Record 1; question `dependency_analysis-002`; latency 173.088645 s; error field empty.

```text
Insufficient repository evidence.
```

Record 2; question `documentation_lookup-022`; latency 176.843184 s; error field empty.

```text
Insufficient repository evidence.
```

Record 3; question `code_retrieval-026`; latency 176.332419 s; error field empty.

```text
Insufficient repository evidence.
```

Record 4; question `dependency_analysis-040`; latency 176.127186 s; error field empty.

```text
Insufficient repository evidence.
```

Record 5; question `dependency_analysis-027`; latency 176.039492 s; error field empty.

```text
Insufficient repository evidence.
```

Record 6; question `code_retrieval-024`; latency 176.011306 s; error field empty.

```text
Insufficient repository evidence.
```

Record 7; question `dependency_analysis-012`; latency 176.03333 s; error field empty.

```text
Insufficient repository evidence.
```

Record 8; question `issue_pr_analysis-004`; latency 176.017508 s; error field empty.

```text
Insufficient repository evidence.
```

Record 9; question `documentation_lookup-029`; latency 176.484422 s; error field empty.

```text
airflow-core/newsfragments/62487.significant.rst
```

Record 10; question `code_retrieval-012`; latency 176.269816 s; error field empty.

```text
Insufficient repository evidence.
```

## Appendix B ? exact scoring code

Source excerpts are verbatim, without diff markers. The call-site excerpt shows which inputs feed each metric; normalization is included to make exact-set comparison interpretable.

Exact source: `src/evaluation/metrics.py:173-193`

```python
PATH_RE = re.compile(
    r"(?<![\w.-])"
    r"(?:[\w.@+\-]+[\\/])+"
    r"[\w.@+\-]+"
    r"(?:\.[A-Za-z0-9]+)?"
)

ISSUE_RE = re.compile(
    r"(?<!\w)#\d+\b"
)

COMMIT_RE = re.compile(
    r"\b[a-f0-9]{7,40}\b",
    re.I,
)

SYMBOL_RE = re.compile(
    r"[`'\"]"
    r"([A-Za-z_][A-Za-z0-9_.$:< >\-]*)"
    r"[`'\"]"
)

```

Exact source: `src/evaluation/metrics.py:202-225`

```python
def text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, float) and math.isnan(value):
        return ""

    return str(value).strip()


def norm(value: Any) -> str:
    value_text = text(value).lower()
    value_text = value_text.replace("\\", "/")
    value_text = re.sub(r"\s+", " ", value_text)
    value_text = re.sub(
        r"\s*([:/#=><|])\s*",
        r"\1",
        value_text,
    )

    return value_text.strip(
        " \t\r\n.,;:!?\"'`()[]{}"
    )

```

Exact source: `src/evaluation/metrics.py:295-364`

```python
def uniq(items: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()

    for item in items:
        normalized = norm(item)

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)
        output.append(normalized)

    return output


def safe_div(
    numerator: float,
    denominator: float,
) -> float:
    if not denominator:
        return 0.0

    return float(numerator / denominator)


def tokens(value: Any) -> list[str]:
    return WORD_RE.findall(norm(value))


def set_prf(
    expected: Iterable[Any],
    predicted: Iterable[Any],
) -> tuple[float, float, float]:
    expected_set = set(uniq(expected))
    predicted_set = set(uniq(predicted))

    if not expected_set and not predicted_set:
        return 1.0, 1.0, 1.0

    if not expected_set:
        return 0.0, 1.0, 0.0

    if not predicted_set:
        return 0.0, 0.0, 0.0

    overlap = len(
        expected_set & predicted_set
    )

    precision = safe_div(
        overlap,
        len(predicted_set),
    )

    recall = safe_div(
        overlap,
        len(expected_set),
    )

    f1 = safe_div(
        2 * precision * recall,
        precision + recall,
    )

    return precision, recall, f1

```

Exact source: `src/evaluation/metrics.py:403-597`

```python
def contained(
    answer: str,
    expected_item: str,
) -> bool:
    normalized_answer = norm(answer)
    normalized_item = norm(expected_item)

    if not normalized_item:
        return False

    if normalized_item in normalized_answer:
        return True

    return bool(
        re.search(
            rf"(?<![a-z0-9_])"
            rf"{re.escape(normalized_item)}"
            rf"(?![a-z0-9_])",
            normalized_answer,
        )
    )


def coverage(
    answer: str,
    expected: Iterable[Any],
) -> tuple[float, float, int, int]:
    expected_items = uniq(expected)

    if not expected_items:
        return math.nan, math.nan, 0, 0

    matched = sum(
        contained(answer, item)
        for item in expected_items
    )

    coverage_value = safe_div(
        matched,
        len(expected_items),
    )

    accuracy = float(
        matched == len(expected_items)
    )

    return (
        accuracy,
        coverage_value,
        matched,
        len(expected_items),
    )


FACT_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for",
    "from", "has", "in", "is", "it", "of", "on", "or", "that",
    "the", "this", "to", "was", "were", "which", "with",
}


def content_tokens(value: Any) -> set[str]:
    """Return meaningful normalized tokens for fact comparison."""
    return {
        token
        for token in tokens(value)
        if token not in FACT_STOPWORDS
    }


def fact_matches_answer(
    fact: str,
    answer: str,
    recall_threshold: float = 0.60,
    f1_threshold: float = 0.55,
) -> bool:
    """Return True when the answer expresses the required fact.

    Repository answers are often deliberately concise. For example, the
    benchmark fact may be "The requested file is src/app.py" while the system
    correctly returns only "src/app.py". Matching is therefore bidirectional
    and also supports meaningful-token overlap without accepting unrelated text.
    """
    normalized_fact = norm(fact)
    normalized_answer = norm(answer)

    if not normalized_fact or not normalized_answer:
        return False

    # Full fact in answer, or concise answer in a longer benchmark statement.
    if contained(answer, fact) or contained(fact, answer):
        return True

    fact_tokens = content_tokens(fact)
    answer_tokens = content_tokens(answer)

    if not fact_tokens or not answer_tokens:
        return False

    overlap = fact_tokens & answer_tokens

    # A concise identifier-only answer is valid when every meaningful answer
    # token is contained in the validated fact. Require at least one
    # repository-specific token to avoid matching generic prose.
    identifier_like = any(
        any(marker in token for marker in ("/", "#", ":", ".", "@"))
        or re.fullmatch(r"[a-f0-9]{7,40}", token, flags=re.I)
        or token.isdigit()
        for token in answer_tokens
    )
    if identifier_like and answer_tokens.issubset(fact_tokens):
        return True

    if fact_tokens.issubset(answer_tokens):
        return True

    fact_recall = safe_div(len(overlap), len(fact_tokens))
    answer_precision = safe_div(len(overlap), len(answer_tokens))
    semantic_f1 = safe_div(
        2 * fact_recall * answer_precision,
        fact_recall + answer_precision,
    )

    if fact_recall >= recall_threshold and semantic_f1 >= f1_threshold:
        return True

    _, token_recall, token_f1 = token_prf(fact, answer)
    return token_recall >= recall_threshold and token_f1 >= f1_threshold

def fact_coverage(
    answer: str,
    expected_facts: Iterable[Any],
) -> tuple[float, int, int]:
    facts = uniq(expected_facts)

    if not facts:
        return math.nan, 0, 0

    matched = sum(
        fact_matches_answer(fact, answer)
        for fact in facts
    )

    return (
        safe_div(matched, len(facts)),
        matched,
        len(facts),
    )


def extract_entities(answer: str) -> list[str]:
    found: list[str] = []

    found.extend(
        PATH_RE.findall(answer)
    )

    found.extend(
        ISSUE_RE.findall(answer)
    )

    found.extend(
        COMMIT_RE.findall(answer)
    )

    found.extend(
        item.replace(" ", "")
        for item in SYMBOL_RE.findall(answer)
    )

    return uniq(
        item.rstrip(".,;:!?)]}")
        for item in found
    )


def expected_entities(
    row: pd.Series,
) -> list[str]:
    explicit = flatten(
        row.get("expected_entities")
    )

    if explicit:
        return explicit

    expected_answer = text(
        row.get("expected_answer")
    )

    if expected_answer:
        return flatten(expected_answer)

    return []

```

Exact source: `src/evaluation/metrics.py:1333-1417`

```python
def evaluate_row(
    row: pd.Series,
    system: str,
    k: int,
) -> dict[str, Any]:
    answer = text(row.get("answer"))
    reference = text(
        row.get("expected_answer")
    )
    error = text(row.get("error"))

    expected_entity_values = expected_entities(
        row
    )

    predicted_entity_values = (
        flatten(row.get("predicted_entities"))
        or extract_entities(answer)
    )

    required_fact_values = flatten(
        row.get("required_facts")
    )

    # A benchmark may omit a separate required_facts column. In that case,
    # use the validated reference answer (or explicit expected entities) so the
    # metric remains defined and comparable across all systems.
    if not required_fact_values:
        if reference:
            required_fact_values = [reference]
        else:
            required_fact_values = list(expected_entity_values)

    expected_relation_values = relations(
        row.get("expected_relations")
    )

    predicted_relation_values = relations(
        row.get("predicted_relations")
    )

    expected_path_values = flatten(
        row.get("expected_path")
    )

    predicted_path_values = flatten(
        row.get("predicted_path")
    )

    gold_evidence_values = flatten(
        row.get("gold_evidence")
    )

    retrieved_evidence_values = flatten(
        row.get("retrieved_evidence")
    )

    (
        answer_accuracy,
        ground_truth_coverage,
        matched_entities,
        expected_entity_count,
    ) = coverage(
        answer,
        expected_entity_values,
    )

    (
        entity_precision,
        entity_recall,
        entity_f1,
    ) = set_prf(
        expected_entity_values,
        predicted_entity_values,
    )

    (
        required_fact_coverage,
        matched_fact_count,
        required_fact_count,
    ) = fact_coverage(
        answer,
        required_fact_values,
    )

```

Exact source: `src/evaluation/metrics.py:324-325` and `:366-400` (token helper used by fact scoring).

```python
def tokens(value: Any) -> list[str]:
    return WORD_RE.findall(norm(value))

def token_prf(
    reference: str,
    prediction: str,
) -> tuple[float, float, float]:
    reference_tokens = Counter(
        tokens(reference)
    )

    prediction_tokens = Counter(
        tokens(prediction)
    )

    overlap = sum(
        (
            reference_tokens
            & prediction_tokens
        ).values()
    )

    precision = safe_div(
        overlap,
        sum(prediction_tokens.values()),
    )

    recall = safe_div(
        overlap,
        sum(reference_tokens.values()),
    )

    f1 = safe_div(
        2 * precision * recall,
        precision + recall,
    )

    return precision, recall, f1
```

## Appendix C ? read-only evidence checks

CSV parsing used the standard library with an increased field limit for long quoted evidence fields. Entity comparisons invoked the existing metrics.extract_entities function with Python -B; no output metrics were overwritten. No external API or database was called. Counts and answer comparisons were calculated directly from the files cited above. Exact SHA-256 fingerprints below bind the principal inputs to this audit (not to their original execution settings).

- `data/benchmark/Human Written Question.csv`: `1f7dad16b56f10924233d2c728ef776401be24bc9cf4cd8a420dd3cd023ce390`

- `data/benchmark/splits/hidden_test_answer_key.csv`: `42b776aa59bc63bff3bd21641c7238b2f61136469438332832ce3b52aa7d8e15`

- `results/final_evaluation_metrics/summary_metrics.csv`: `d909f52ab2ddcddc28b8a24a53b336a8da6c97f0bd6f833efb4bbab514e88058`

- `src/evaluation/metrics.py`: `4a2a74b85ca0aef70d6ece761037f9f3906bc60a013cdadfac9c80e20fa98e4d`

- `src/systems/router.py`: `8db2f221b4c43a0352545320a747252240becd33c64589af7766f6e0ad37532b`

- `src/systems/oracle_hybrid_rag.py`: `10d1d3fdd62cb3d4ee7b285454a1e5527d91a2c44d3ca66b747987599a221e87`
