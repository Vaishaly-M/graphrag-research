"""Post-hoc Phase 1C subject audit; historical Phase 1B audit outputs stay read-only."""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT
from src.evaluation.metrics_v2 import items, PATH, HASH, EMAIL
from src.evaluation.reproducibility import read_csv, sha256

SPLITS = ROOT / "data/benchmark/splits_v2"
EXCLUDED = ("development", "validation", "hidden-test", "human-test")
RULE = dict(version="primary-subject-v2", changed_on="2026-10-12", post_hoc=True,
    reason="User-requested correction after Phase 1B failed: repository sharing is not primary-subject leakage.",
    subjects=["commit hash", "issue number", "PR number", "file path", "developer identity", "code/doc fragment"],
    excluded_subjects=["repository alone", "directory alone", "issue search keyword", "issue title alone"],
    normalization="Unicode text casefold and whitespace collapse; paths normalize backslashes; commit prefixes match at >=7 characters",
    scope="Files, issue/PR numbers and fragments are repository-scoped; commit hashes and developer identities are global.",
    limitations="Human subjects lack annotations; only identifiable literal subjects can be checked. Not proof of semantic/paraphrase disjointness.")


def norm(text):
    return re.sub(r"\s+", " ", str(text).casefold()).strip()


def anchors(row):
    """The explicitly post-hoc v2 rule, never repository identity alone."""
    raw = row.get("params") or {}
    params = json.loads(raw) if isinstance(raw, str) else raw
    found = set()
    for key, kind in (("path", "path"), ("commit", "commit"), ("developer", "developer"),
                      ("issue_number", "issue"), ("pr_number", "pr"), ("pull_request_number", "pr")):
        if params.get(key) is not None:
            value = norm(params[key]).removeprefix("email:").replace("\\", "/")
            if kind == "commit":
                value = value.rsplit(":commit:", 1)[-1]
            if kind in {"issue", "pr"}:
                value = str(int(value.lstrip("#")))
            found.add((kind, value))
    category = norm(row.get("category", "")).replace(" ", "_")
    if params.get("fragment") and category in {"code_retrieval", "documentation_lookup"}:
        found.add(("fragment", norm(params["fragment"])))
    # A title lookup identifies an issue; its generated numeric identity is exclusion metadata.
    if params.get("title") and row.get("answer_type") == "issue_number":
        found.update(("issue", str(int(v.lstrip("#")))) for v in items(row.get("expected_entities")) if v.lstrip("#").isdigit())
    if not params:  # Human/text-only metadata: never consult answers or gold.
        text = row["question"]
        repo = norm(row.get("source_repo") or row.get("repo") or "")
        found.update(("commit", norm(v)) for v in HASH.findall(text))
        found.update(("developer", norm(v).removeprefix("email:")) for v in EMAIL.findall(text))
        found.update(("path", norm(m.group()).replace("\\", "/").rstrip(".,;:")) for m in PATH.finditer(text)
                     if norm(m.group()).rstrip(".,;:") != repo and not m.group().endswith("/"))
        for match in re.finditer(r"\b(issue|pr|pull request)\s*#?\s*(\d+)\b", text, re.I):
            found.add(("issue" if match[1].lower() == "issue" else "pr", str(int(match[2]))))
        if category in {"code_retrieval", "documentation_lookup"}:
            found.update(("fragment", norm(m[1])) for m in re.finditer(r'"([^"\n]{15,})"', text))
    return sorted(found)


def overlaps(tuning, others):
    found = []
    prepared = [(b, set(anchors(b)), norm(b["question"]), norm(b.get("source_repo") or b.get("repo") or "")) for b in others]
    for a in tuning:
        repo = norm(a.get("source_repo") or a.get("repo") or "")
        subjects = anchors(a)
        for b, other_subjects, text, other_repo in prepared:
            aid, bid = a.get("question_id") or a.get("id"), b.get("question_id") or b.get("id")
            if norm(a["question"]) == text:
                found.append(dict(question_id=aid, other_question_id=bid, check="normalized_text", entity=None))
            for kind, entity in subjects:
                if kind not in {"commit", "developer"} and repo != other_repo:
                    continue
                match = (kind, entity) in other_subjects
                if kind == "commit":
                    match |= any(k == kind and min(len(v),len(entity)) >= 7 and (v.startswith(entity) or entity.startswith(v)) for k,v in other_subjects)
                # Literal text match catches structured identifiers in unannotated questions.
                if kind not in {"issue", "pr"}:
                    match |= bool(re.search(r"(?<![\w])"+re.escape(entity)+r"(?![\w])", text))
                if match:
                    found.append(dict(question_id=aid, other_question_id=bid, check="primary_entity",
                                      entity_type=kind, entity=entity, repository=repo))
    return found


def exclusion_rows():
    manifest = json.loads((SPLITS / "manifest.json").read_text())
    groups = {}
    for name in EXCLUDED:
        path = SPLITS / (name+".csv")
        if sha256(path) != manifest["splits"][name]["sha256"]:
            raise RuntimeError("Protected split hash mismatch: " + name)
        groups[name] = read_csv(path)
    return groups


def audit(rows):
    checks = {}
    for name, others in exclusion_rows().items():
        matches = overlaps(rows, others)
        checks[name] = dict(status="FAIL" if matches else "PASS_DETECTABLE_SUBJECTS",
            text_overlaps=sum(m["check"] == "normalized_text" for m in matches),
            primary_entity_overlaps=sum(m["check"] == "primary_entity" for m in matches), overlaps=matches)
    return dict(status="FAIL" if any(c["overlaps"] for c in checks.values()) else "PASS_DETECTABLE_SUBJECTS",
                rule=RULE, checks=checks, count=len(rows), categories=Counter(r["category"] for r in rows),
                repositories=Counter(r["source_repo"] for r in rows),
                hashes={n:sha256(SPLITS/(n+".csv")) for n in ("router-tuning",*EXCLUDED)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["router-tuning", "router-tuning_v1"], default="router-tuning")
    parser.add_argument("--output", default="results/v2/phase1c/disjointness.json")
    args = parser.parse_args()
    output = ROOT / args.output
    if not output.resolve().is_relative_to((ROOT/"results/v2/phase1c").resolve()):
        parser.error("Keep Phase 1B audit immutable; output must be under results/v2/phase1c")
    result = audit(read_csv(SPLITS/(args.split+".csv")))
    result.update(audited_split=args.split, audited_split_sha256=sha256(SPLITS/(args.split+".csv")))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    for name, check in result["checks"].items():
        print(name, check["status"], "text", check["text_overlaps"], "primary subjects", check["primary_entity_overlaps"])
        for match in check["overlaps"]:
            print(json.dumps(match))
    return int(result["status"] == "FAIL")


if __name__ == "__main__":
    sys.exit(main())
