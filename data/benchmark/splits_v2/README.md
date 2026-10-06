# Frozen evaluation splits

This is the single human-readable split count table.

| Split | Questions |
| --- | ---: |
| development | 29 |
| validation | 29 |
| hidden-test | 242 |
| human-test | 100 |

Development is the only tuning set. Validation is for a locked selection check, not iterative tuning.
Hidden-test is the existing held-out template membership, with its unchanged gold key.
Human-test is never used for tuning; its gold and answerability annotations are missing.
All files are byte-identical copies of their source CSVs. Original IDs are retained.
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
