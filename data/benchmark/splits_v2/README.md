# Frozen evaluation splits

This is the single human-readable split count table.

| Split | Questions |
| --- | ---: |
| development | 29 |
| validation | 29 |
| hidden-test | 242 |
| human-test | 100 |
| router-tuning (v2) | 140 |
| router-tuning_v1 (archived) | 70 |

Development is the original tuning set. The separate router-tuning set is tuning-only.
Validation is for a locked selection check, not iterative tuning.
Hidden-test is the existing held-out template membership, with its unchanged gold key.
Human-test is never used for tuning; its gold and answerability annotations are missing.
The original four splits are byte-identical copies of their source CSVs. Original IDs are retained.
The run harness sends only question text to systems. Oracle's existing template-label lookup remains unchanged;
human questions have no such labels. Missing human gold is N/A, never an invented answer or zero accuracy.

The old category table describes the entire benchmark; the main table describes hidden-test after
development and validation exclusions. Those denominators must be labeled explicitly in the paper.
Airflow is absent from development and validation; this denotes the split policy, not proof that later
code changes were blind to Airflow. Development/validation also lack structure and code_retrieval categories;
do not repair this imbalance by moving questions after viewing their results.

No saved paraphrased question set was found; none is generated in Phase 1.
Manifest hashes bind the frozen files. The separate results/v2/human_gold_needed.csv worksheet lists
missing annotation fields. Editing that worksheet does not change frozen gold; a later reviewed version
must be explicitly frozen before human scoring.

## Archived router-tuning v1 (tuning-only; overlap-contaminated diagnostic)

The archived 70-question set was generated with seed `20261009` (original benchmark seed: `42`).
SHA-256: `fee8bab59925109abfff7d7b579fa1df92800962403200116fd329f2ce539aa8`.
It has ten questions in each of seven categories. Repository counts are openmrs/openmrs-core 20,
spring-projects/spring-petclinic 16, mlflow/mlflow 14, dotnet/eShop 13, synthetic-org/platform 7.
apache/airflow is absent by the recorded generation policy. No category is missing.

The original manifest claims disjoint normalized questions and complete expected-entity sets;
those claims do not establish primary-entity disjointness. The Phase 1B audit found zero identical
normalized questions but subject overlaps with development, validation and hidden-test.
The preserved original exclusion check is `results/v2/phase1b/disjointness.json`. Human subjects are unannotated;
literal matching cannot prove semantic disjointness. Repository scope alone is not a subject
except for repository-wide questions; code/doc fragments use returned file identities.

The user explicitly authorized diagnostic route outcomes despite overlap. This set is not a
disjoint evaluation set or paper result. Its gold, membership, seed and bytes were preserved.
Any future replacement requires a separately versioned split and an explicit decision.

## Router-tuning v2 and post-hoc audit rule change — 2026-10-12

The user authorized this replacement after the Phase 1B audit failed. **This is a post-hoc rule
change, not a preregistered clean-split claim.** A repository alone is no longer a primary subject:
the real repositories are intentionally shared across splits. Primary subjects are commit hashes,
issue numbers, PR numbers, file paths, developer identities and code/doc fragments. Directories,
repository names and generic issue-search keywords alone are not primary subjects. Issue-title
lookups use their generated issue-number identity; code/doc lookups use the actual fragment,
not the returned file. Files, numbers and fragments are repository-scoped; commits and developers
are global. Matching uses casefold/whitespace normalization and commit prefixes of at least seven
characters. Human metadata supports only detectable literal subjects, not semantic guarantees.

Re-auditing v1 under this rule leaves one overlapping question:
`router-tuning-c6dc0e1b1b05a2df` shares developer `choonghee.lee@hotmail.com` with development
`developer_activity-006`. Only that question was removed. The other 69 v1 rows retain their gold
and metadata. `router-tuning_v1.csv` is a byte-identical archive of the original split.

The new `router-tuning.csv` adds 71 graph-verified questions using seed `20261012`, yielding
140 questions, exactly 20 in each category. It is **tuning-only**, not a held-out result.
SHA-256: `b46e373f1b9ac2ce3a868ca62cab09589f0540cac6089f713c493fd083d634f6`.
Repository counts: apache/airflow 23, dotnet/eShop 28, mlflow/mlflow 26,
openmrs/openmrs-core 24, spring-projects/spring-petclinic 24, synthetic-org/platform 15.
Airflow is now included under the user's explicit Phase 1C authorization; its prior exclusion
was a generation-script policy, not a generator limitation. No protected split was changed.

The requested size was reached; no disjointness-limited shortfall occurred. Generation used at
most 600 candidate attempts per category; reaching the target does not establish the mathematical
maximum size of a disjoint set. Checkpoints, rejections, seed and config are under
`results/v2/phase1c/split_generation/`. New audits are under `results/v2/phase1c/`:
`v1_reaudit.json` and `disjointness.json`. Rerun the current check with
`python -B scripts/audit_phase1b.py`; it never overwrites the old Phase 1B audit.
