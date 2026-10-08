"""Render Phase 1 evidence without changing gold, old results, or systems."""
import collections
import json
import statistics
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT
from src.evaluation.reproducibility import read_csv, sha256


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(str(v) for v in row) + ' |' for row in rows])


def main():
    out = ROOT / 'results/v2'
    probe = read_csv(out / 'latency_probe.csv')
    active = [r for r in probe if r.get('superseded', '').lower() != 'true']
    groups = collections.defaultdict(list)
    for r in active:
        groups[r['system'], r['way']].append(r)
    timing = []
    for (system, way), rows in sorted(groups.items()):
        avg = lambda field: f"{statistics.mean(float(r[field]) for r in rows):.3f}"
        timing.append([system, way, len(rows), sum(r['answer_status'] == 'error' for r in rows),
                       avg('llm_time_s'), avg('pacing_sleep_s'), avg('backoff_sleep_s'),
                       avg('retrieval_time_s'), avg('total_wall_s'), sum(int(r['n_attempts']) for r in rows)])
    summaries = read_csv(out / 'rescore_old_answers.csv')
    changed = read_csv(out / 'changed_verdicts.csv')
    changes = collections.defaultdict(list)
    for r in changed:
        changes[r['system'], r['legacy_accuracy'], r['strict_accuracy']].append(r['question_id'])
    human = json.loads((out / 'human_validation.json').read_text())
    manifest = json.loads((ROOT / 'data/benchmark/splits_v2/manifest.json').read_text())
    environment = json.loads((out / 'environment_phase1_final.json').read_text())
    leakage = read_csv(out / 'leakage_review.csv')
    flagged = [r for r in leakage if r['flagged'].lower() == 'true']
    pct = lambda v: f'{float(v)*100:.2f}%'
    historical = []
    for system in ['plain_llm', 'vector_rag']:
        rows = read_csv(ROOT / f'results/final_evaluation/{system}_results.csv')
        near = [r for r in rows if 170 <= float(r['latency_s']) <= 180]
        historical.append([system, len(near), 'unrecorded', 'unrecorded', 'unrecorded', 'unrecorded'])
    six = sum(str(r.get('six_attempts_used')).lower() == 'true' for r in active)
    near = sum(170 <= float(r['total_wall_s']) <= 180 for r in active)
    git = ['git', '-c', f'safe.directory={ROOT.as_posix()}']
    revision = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    protected = subprocess.check_output(git + ['diff', '--name-only', 'HEAD', '--', 'results',
                    ':!results/v2', 'data/benchmark', ':!data/benchmark/splits_v2',
                    'src/systems/router.py', 'src/systems/plain_llm.py', 'src/systems/vector_rag.py',
                    'src/systems/adaptive_hybrid_graphrag.py', 'src/evaluation/metrics.py'], cwd=ROOT, text=True).strip()
    if protected:
        raise RuntimeError('Protected files differ from start-of-completion HEAD: ' + protected)
    phase_files = ['src/llm.py', 'src/common.py', 'src/systems/base.py', 'src/vector_store.py',
        'src/systems/query_registry.py',
        'src/build_vector_index.py', 'src/evaluation/harness_v2.py', 'src/evaluation/telemetry.py',
        'src/evaluation/reproducibility.py', 'src/evaluation/metrics_v2.py',
        'scripts/run_eval.py', 'scripts/latency_probe.py', 'scripts/freeze_evaluation.py',
        'scripts/rescore_old_answers.py', 'scripts/verify_environment.py', 'scripts/report_phase1.py',
        'scripts/prepare_latency_index.py',
        'tests/test_harness_v2.py', 'tests/test_metrics_v2.py', 'tests/test_phase1_retrieval.py',
        'scripts/test_issue_title_parser.py', 'docs/metrics.md']
    text = '# Phase 1 — evaluation freeze and measurement harness\n\n'
    text += f'Date: 2026-10-08 (Asia/Colombo). Completion checkout HEAD: `{revision}`. '
    text += 'This completes the Phase 1 implementation and records empirical limitations below; no later phase is authorized or started. '
    text += 'Gold and historical results were not edited. Router, baseline prompts, routing policy, fusion and answering behavior were not tuned. '
    text += 'The existing apostrophe parser was retained and tested; the only retrieval change is adaptive over-fetching for repository/kind filters.\n\n'
    text += '## 1. Latency microbenchmark\n\n'
    text += 'Ten fixed questions per system; Plain has trivial-prompt and full-system calls, Vector additionally has retrieval-only calls. '
    text += 'All attempts, including prior failures, remain in [latency_probe.csv](../results/v2/latency_probe.csv). '
    text += 'Superseded failed attempts are excluded from the following means. Values are seconds per operation. Initialization/index building is outside question timing; first index load is inside retrieval timing.\n\n'
    text += table(['System','Operation','N','Errors','Attempt time','Pacing','Backoff','Retrieval','Wall','Attempts'], timing) + '\n\n'
    text += f'Total recorded client attempts across retained history (including earlier connection failures): {sum(int(r["n_attempts"]) for r in probe)}; cap: 61, enforced persistently before each SDK request. The default cap was 60; one extra attempt completed the final question after a transient retry. '
    text += f'Active rows around 175 seconds (170–180): {near}; active rows using all six attempts: {six}. '
    text += 'Model/prompt/parameter response caching prevents repeat API requests on resume; cache hits are labeled and excluded from latency summaries. '
    text += 'See per-call start/end timestamps and attempt_events for duration, error type, pacing, backoff and retry-after. Events are also appended to logs/llm_events.jsonl.\n\n'
    text += '**Historical ~175-second cause remains unidentifiable from saved evidence.** It was not reproduced by successful current model calls. '
    text += 'The old CSVs contain wall-like latency only, with no attempt or sleep fields:\n\n'
    text += table(['Historical system','170–180 s rows','Attempt time','Pacing','Backoff','Six attempts?'], historical) + '\n\n'
    text += 'At RPM=10, one pacing wait is at most approximately six seconds. Six application attempts have five exponential backoffs totaling 31 seconds before jitter/provider retry-after; this alone does not explain 175 seconds. '
    text += 'Network/SDK attempt time and provider retry-after are possible contributors, not established causes. The claim that historical 175-second rows exhausted six attempts cannot be verified. '
    text += 'The repaired client disables hidden SDK retries and sets a recorded 60-second request timeout so future calls are auditable. Historical model/configuration provenance is incomplete; current configured aliases are recorded in each invocation snapshot. '
    text += 'A mocked six-attempt test verifies timing accounting, not the historical cause.\n\n'
    diagnostic = json.loads((out / 'latency_probe/diagnostic_index/manifest.json').read_text())
    text += f"Vector latency uses a byte-identical diagnostic copy of the preserved legacy index ({diagnostic['doc_count']:,} chunks). "
    text += f"{diagnostic['verified_vector_count']:,} explicitly recomputed embeddings match the corresponding legacy vectors within 2e-6; the full document serialization matches the rebuild corpus hash. "
    text += "This is a compatibility check on a prefix subset, not proof of historical model/chunk/source settings. Unknown historical manifest fields remain null. "
    text += "The diagnostic manifest is marked diagnostic_only and normal run_eval runs reject it. VectorStore.build writes a complete manifest at actual build time and refuses loading any index without a manifest. "
    text += "The fresh rebuild was checkpointed and stopped before the full corpus completed; an explicit complete build is still required before new publishable vector evaluations. "
    text += "No background build or model request remains running at handoff.\n\n"
    text += 'One Vector call encountered ServerError, spent approximately 0.302 seconds in the failed attempt and 1.267 seconds in backoff, then succeeded on attempt two. No provider retry-after was reported.\n\n'
    text += '## 2. Diagnostic rescore (not paper results)\n\n'
    text += 'All saved final-evaluation and ablation answers were read without rerunning systems. Strict accuracy uses boundary-aware category/answer-type entities and closed-set extra-entity penalties. '
    text += 'Errors score zero; conditional non-error accuracy is separate. Missing human gold is N/A. Definitions, precision/recall/F1 relationships and limitations are in [docs/metrics.md](../docs/metrics.md).\n\n'
    text += table(['System/variant','Rows','Legacy accuracy','Strict accuracy','Errors','Abstentions'],
        [[r['system'], r['n_rows'], pct(r['legacy_accuracy']), pct(r['strict_accuracy']), r['n_errors'], r['n_abstained']] for r in summaries]) + '\n\n'
    text += f'{len(changed)} system/question verdicts changed. Complete IDs are listed below; entity-level reasons are in [changed_verdicts.csv](../results/v2/changed_verdicts.csv). '
    text += 'Extra output entities can reflect LIMIT-truncated gold, so these diagnostic changes must not be interpreted as adjudicated hallucinations. Gold was not expanded.\n\n'
    text += table(['System','Legacy to strict','Question IDs'],
        [[system, f'{old} to {new}', ', '.join(ids)] for (system, old, new), ids in sorted(changes.items())]) + '\n\n'
    text += 'The requested ten-file fixture has strict_accuracy=1 and required_fact_coverage=1; prose title matching, number-versus-title rejection, 475-versus-abstention, extra files/commits, boundary errors, negation and dictionary-key exclusions have tests. '
    text += 'Historical swallowed errors cannot be inferred when the saved records contain no trace. New telemetry catches swallowed retrieval, LLM and parse failures.\n\n'
    text += '## 3. Frozen split definition\n\n'
    text += table(['Split','Questions'], [[name, r['count']] for name, r in manifest['splits'].items()]) + '\n\n'
    text += 'The category-table denominator is the full 300-template pool; the main-table denominator is its 242-question hidden-test partition after 29 development and 29 validation exclusions. '
    text += 'These are distinct populations, not missing evaluations. Existing memberships and stable IDs are preserved in byte-identical copies under data/benchmark/splits_v2, with hashes and a README. '
    text += 'Development is the only tuning split; validation is a locked selection check; hidden-test is held out; human-test is never used for tuning. '
    text += 'Development/validation contain no Airflow, structure or code_retrieval rows; this imbalance is disclosed rather than repaired after seeing results. No saved paraphrased set exists and none was generated.\n\n'
    text += '## 4. Human set validation\n\n'
    text += f'Columns: {", ".join(human["columns"])}. {human["n_rows"]} rows; zero nulls in supplied columns, duplicate IDs, duplicate full rows, or duplicate normalized questions. '
    text += 'All repositories and category labels map to the template taxonomy.\n\n'
    text += table(['Repository','Rows'], list(human['repositories'].items())) + '\n\n'
    text += table(['Category','Rows'], list(human['categories'].items())) + '\n\n'
    text += '**Author attention: Q001–Q100 all require annotations.** Answerable/unanswerable counts are unknown; no gold answers, expected entities, required facts, answer types or gold evidence are supplied. '
    text += 'Fill the separate [human_gold_needed.csv](../results/v2/human_gold_needed.csv) worksheet; the original CSV and frozen copy remain unchanged. '
    text += 'Answerability plus expected entities/reference answers determine answer accuracy; answer_type selects extraction; required_facts supports fact coverage; gold_evidence supports evidence metrics. '
    text += 'Unanswerable rows need an explicit false label and should not be given invented entities. Human repo/category display fields are mapped only in the evaluator.\n\n'
    text += f'Leakage review: {sum(r["exact_match"].lower()=="true" for r in leakage)} exact text matches; {len(flagged)} flagged pairs involving {len({r["human_id"] for r in flagged})} human questions. '
    text += 'The check uses punctuation/case-normalized exact text, SequenceMatcher text similarity and identifier-set Jaccard similarity; either score =0.90 flags review. '
    text += 'Identifier sets include paths/repository slugs, hashes, emails, numbers and quoted symbols from question text because human gold is absent. '
    text += 'This is a lexical leakage screen, not a semantic or provenance guarantee. The closest template for each human row and all flagged pairs are saved in [leakage_review.csv](../results/v2/leakage_review.csv).\n\n'
    text += '## 5. Reproducibility, checks and remaining limits\n\n'
    text += 'Single entry point: `python scripts/run_eval.py <system> <split> --repeats N --run-name X [--discard-first-run] [--no-cache]`. '
    text += 'Default is one measured repeat with no warm-up exclusion. Discarding the first requires at least two requested repeats. '
    text += 'Every run records model/temperature/seed/RPM/retry settings, k/chunking/embedding, thresholds, index and benchmark hashes, source hashes, Git revision and dirty state. '
    text += 'Generation seed remains null because existing systems did not set one. Frozen-file hash changes fail loudly. Configuration changes require a new run name. '
    text += 'Resume retains failed rows, their attempt_number and superseded=true; repeats have separate cache namespaces. '\
            'Latency is total_wall_s minus pacing/backoff; successful retry time remains included. Cached and execution-error rows are excluded from latency means, but execution errors remain in accuracy denominators.\n\n'
    text += 'Environment check (the script exits nonzero if any required check fails):\n\n'
    text += table(['Component','Observation'], [
        ['Gemini', f"Key present: {environment['gemini']['key_present']}; configured model: {environment['gemini']['model']}. Actual probe calls verify access separately."],
        ['Neo4j', json.dumps(environment['neo4j'])],
        ['Vector index', json.dumps({k:v for k,v in environment['vector_index'].items() if k!='manifest'})],
        ['Ollama', json.dumps(environment['ollama'])]]) + '\n\n'
    text += 'Neo4j checks could not resolve the configured address even with network access; node counts are unavailable, not zero. Ollama is reachable but qwen2.5 is not pulled. '
    text += 'No graph reload, model installation, baseline rewrite or routing experiment was performed to conceal these failures.\n\n'
    text += 'Validation: 35 harness/metrics/retrieval tests and two standalone registry tests passed (37 total). Test records: [harness/metrics/retrieval suite](../results/v2/tests/phase1_tests.txt) and [registry title parser suite](../results/v2/tests/title_parser_tests.txt). '
    text += 'Tests cover the new accounting and scoring behavior; these are not claims that external infrastructure is healthy.\n\n'
    text += '## 6. Changed files and complete contents\n\n'
    text += 'The following Phase 1 implementation files include work already present in the phase-1 commit and the completion fixes. Full files are available in the workspace and in results/v2/phase1_complete_files.zip, without diffs.\n\n'
    text += '\n'.join('- `' + p + '`' for p in phase_files) + '\n\n'
    text += 'Additional artifacts: data/benchmark/splits_v2/{development,validation,hidden-test,human-test}.csv, manifest.json and README.md; logs/llm_events.jsonl; results/v2 latency/cache/snapshot/index artifacts, environment checks, rescore summaries/per-question verdicts, human validation/annotation worksheet, leakage review, test logs, and this report. '
    text += 'The registry apostrophe fix and its standalone tests were already present when completion began; no further parser edit was needed. Existing .review_tools deletions were left untouched.\n\n'
    text += f'Original human CSV SHA-256: `{sha256(ROOT / "data/benchmark/Human Written Question.csv")}` (matches the Phase 0 audit). '
    text += 'A Git content check against the completion-start HEAD found no edits to protected historical results, original benchmark files, legacy metrics, router or baselines.\n\n'
    text += '**Stopped at Phase 1. Awaiting author review and confirmation before any later phase.**\n'
    (ROOT / 'reports/phase1.md').write_text(text, encoding='utf-8')
    import zipfile
    with zipfile.ZipFile(out/'phase1_complete_files.zip','w',compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in phase_files + ['reports/phase1.md']:
            bundle.write(ROOT/name,name)
        for path in sorted((ROOT/'data/benchmark/splits_v2').glob('*')):
            if path.is_file():
                bundle.write(path, path.relative_to(ROOT))
    print('Wrote reports/phase1.md and complete file bundle.')


if __name__ == '__main__':
    main()

