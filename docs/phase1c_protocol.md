# Phase 1C diagnostic protocol

Recorded 2026-10-12, before route execution. Phase 2 is not authorized.

The primary-subject audit was changed post hoc after Phase 1B failed, at the user's request.
The exact versioned rule is in `scripts/audit_phase1b.py`, the split README and manifest.
All four protected split CSVs and existing gold stay unchanged. Only the authorized tuning
split is versioned and enlarged; its v1 bytes and the old audit are preserved.

Both modes force graph, vector and hybrid through the same production retrieval, fusion and
answering paths. The generator is the configured Gemini model (snapshot records the alias).
Every evidence-based answer uses `ADAPTIVE_FINAL_ANSWER`, temperature 0, max output tokens 1024,
and the same final evidence limit of 16 items. Existing retrieval limits are 100 graph rows and
10 vector items. There is no separate context-token cap in the existing code; that is recorded
explicitly, not claimed as token-budget matching. Fusion weights remain 0.72 retrieval,
0.20 lexical and 0.08 graph bonus. All routes share these settings.

With-templates preserves Phase 1B behavior, including the deterministic graph shortcut. The
shortcut can answer from validated graph rows before the LLM; this component remains a limitation
of that track. Retained v1 outcomes are imported with source checks and provenance, rather than
rerun. Removed questions are omitted. New questions run through the same template-enabled code.

No-templates disables registered-template lookup and deterministic graph-answer extraction for
every route. Graph uses LLM-generated read-only Cypher against the existing schema prompt,
existing safety/evidence validation, and LLM synthesis from graph evidence. Vector uses vector
evidence and the same answer prompt. Hybrid fuses both sources and always uses LLM synthesis
when evidence exists. No-evidence cases use the existing explicit abstention. Cross-route
fallback is disabled so forced-route outcomes remain interpretable.

Cypher generation uses the same model and temperature 0 with the existing 700-token Cypher
budget; final answers use 1024 tokens in all routes. Successful responses are cached by model,
parameters and prompt SHA-256, shared across tracks and routes. Cache hits are labelled and
excluded from clean-latency means. Pacing and backoff are always subtracted. This can leave clean
latency unavailable for a route whose calls were cached; missing timing is not zero. Retained
v1 timings describe their original execution and are explicitly marked imported.

Recall accuracy includes every scorable question, with errors incorrect. Main strict accuracy
is defined only on `gold_complete=true` rows; other rows are N/A, including strict oracle maxima.
Raw frozen-set strict scores are retained separately for audit. The oracle picks the first
recall-correct route in graph < vector < hybrid; it does not optimize measured latency. All
three outcomes must exist to derive a question's oracle. Every route checkpoints its outcome,
so every completed question is saved. Quota failure stops after the existing retry budget;
the failed attempt stays logged and can be replaced on resume.

The human-test statistic is a single descriptive boolean template-match rate with category and
repository breakdowns. Only question text is passed to the registry. No answers, gold, scores,
models or tuning are involved. The five explicitly requested historical flips are reviewed
against exact fragment matches in the current graph, without altering gold or re-evaluating a
held-out split. Current graph checks cannot establish historical snapshot equivalence.
