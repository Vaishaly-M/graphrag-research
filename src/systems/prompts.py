from src.common import config_get

# Shared generation settings for every system's final answer call (Guide
# Section 9.2: "the only intentional difference should be the retrieval
# strategy"). Every system in src/systems/ must pass these two values
# explicitly on its answer-generation call -- never rely on
# GeminiClient.generate()'s own defaults there, since a future default
# change would silently reintroduce drift between systems.
ANSWER_TEMPERATURE = float(config_get("llm.temperature_deterministic", 0.0))
ANSWER_MAX_OUTPUT_TOKENS = int(config_get("llm.max_output_tokens_answer", 1024))

ANSWER = """You answer questions about a software repository.

Use only the supplied repository evidence. Do not use general knowledge to
invent repository-specific facts, files, commits, issues, developers, or
values that are not present in the evidence.

Preserve repository IDs, file paths, commit IDs, issue numbers,
pull-request numbers, extensions, punctuation, and email addresses exactly
as they appear in the evidence.

For list questions:
- return every entity the evidence supports;
- do not add an entity that is not present in the evidence;
- return one item per line.

For explanation questions:
- distinguish facts directly supported by the evidence from interpretation;
- do not claim a relationship between entities unless the evidence shows it explicitly.

Return only the answer, with no preamble or explanation of these rules.
If the evidence does not contain the answer, return exactly:
Insufficient repository evidence.

QUESTION:
{question}

EVIDENCE:
{evidence}
"""

CYPHER = """Generate one read-only Neo4j Cypher query for the repository question.

Schema:
(:Repository {{id, name}})
(:File {{id, repo, path, extension, content}})
(:Developer {{id, name, email}})
(:Commit {{id, repo, sha, message, timestamp}})
(:Issue {{id, repo, number, title, body, state}})
(:PullRequest {{id, repo, number, title, body, state, merged}})

Relationships:
(:Repository)-[:CONTAINS_FILE]->(:File)
(:Developer)-[:AUTHORED_COMMIT]->(:Commit)
(:Commit)-[:COMMITTED_TO]->(:Repository)
(:Commit)-[:MODIFIED_FILE]->(:File)
(:Repository)-[:HAS_ISSUE]->(:Issue)
(:Issue)-[:ASSIGNED_TO]->(:Developer)
(:Repository)-[:HAS_PR]->(:PullRequest)
(:Developer)-[:AUTHORED_PR]->(:PullRequest)
(:PullRequest)-[:MERGED_AS]->(:Commit)

Rules:
- Return the requested value with alias answer.
- Use exact identifiers from the question.
- Preserve filename extensions.
- Use Repository.id for repository identifiers.
- Produce one read-only query with no markdown or explanation.

QUESTION:
{question}
"""

ADAPTIVE_FINAL_ANSWER = ANSWER
