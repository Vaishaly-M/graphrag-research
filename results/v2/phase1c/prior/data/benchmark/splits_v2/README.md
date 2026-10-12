# Frozen evaluation splits

This is the single human-readable split count table.

| Split | Questions |
| --- | ---: |
| development | 29 |
| validation | 29 |
| hidden-test | 242 |
| human-test | 100 |
| router-tuning | 70 |

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

## Router-tuning (tuning-only; overlap-contaminated diagnostic)

The existing 70-question set was generated with seed `20261009` (original benchmark seed: `42`).
SHA-256: `fee8bab59925109abfff7d7b579fa1df92800962403200116fd329f2ce539aa8`.
It has ten questions in each of seven categories. Repository counts are openmrs/openmrs-core 20,
spring-projects/spring-petclinic 16, mlflow/mlflow 14, dotnet/eShop 13, synthetic-org/platform 7.
apache/airflow is absent by the recorded generation policy. No category is missing.

The original manifest claims disjoint normalized questions and complete expected-entity sets;
those claims do not establish primary-entity disjointness. The Phase 1B audit found zero identical
normalized questions but subject overlaps with development, validation and hidden-test.
The full read-only exclusion check is `results/v2/phase1b/disjointness.json`; rerun it with
`python -B scripts/audit_phase1b.py`. It exits nonzero on overlap. Human subjects are unannotated;
literal matching cannot prove semantic disjointness. Repository scope alone is not a subject
except for repository-wide questions; code/doc fragments use returned file identities.

The user explicitly authorized diagnostic route outcomes despite overlap. This set is not a
disjoint evaluation set or paper result. Its gold, membership, seed and bytes were preserved.
Any future replacement requires a separately versioned split and an explicit decision.
