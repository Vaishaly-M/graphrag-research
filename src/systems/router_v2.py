"""Explicit three-route scores. Training and configuration freezing live outside inference."""
from __future__ import annotations
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
import numpy as np
from src.common import config_get

ROUTES = ("graph", "vector", "hybrid")
EXEMPLARS = {
    "graph": ["List all files changed by a commit", "Count the issues assigned to a developer", "Who authored this commit?"],
    "vector": ["Explain how this function works", "Find documentation describing authentication", "What does this code fragment implement?"],
    "hybrid": ["Explain the impact of a developer's changes across dependencies", "Which contributors changed the implementation and why?", "Trace the dependency path and explain the affected code"],
}
FEATURES = ("resolved_entities", "relation", "multi_hop", "aggregation", "explanatory", "semantic",
            "exemplar_graph", "exemplar_vector", "exemplar_hybrid")


def norm(text):
    return re.sub(r"\s+", " ", str(text).casefold()).strip()


class EntityCatalog:
    """Exact aliases exported from the KG, with an inverted index for question matching."""
    def __init__(self, records):
        self.fingerprint = hashlib.sha256(json.dumps(records, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.aliases = {}
        self.inverted = {}
        for record in records:
            identity = str(record["id"])
            for alias in [identity, record.get("path"), record.get("name"), record.get("title")]:
                if not alias or len(str(alias)) < 3:
                    continue
                alias = norm(alias)
                self.aliases.setdefault(alias, set()).add(identity)
                tokens = re.findall(r"[\w]+", alias)
                if tokens:
                    # The longest token is selective; all matches still require the full alias.
                    key = max(tokens, key=len)
                    self.inverted.setdefault(key, set()).add(alias)

    def resolve(self, question):
        text = norm(question)
        candidates = set()
        for token in re.findall(r"[\w]+", text):
            candidates.update(self.inverted.get(token, ()))
        resolved = set()
        for alias in candidates:
            if re.search(r"(?<![\w])"+re.escape(alias)+r"(?![\w])", text):
                resolved.update(self.aliases[alias])
        return sorted(resolved)


def softmax(logits):
    values = np.asarray(logits, dtype=float)
    values = np.exp(values - values.max())
    return values / values.sum()


@dataclass(frozen=True)
class Decision:
    retrieval_plan: str
    preferred_route: str
    confidence: float
    scores: dict
    features: dict
    resolved_entities: list
    variant: str
    tau: float
    intent: str = "router_v2"
    hops: int = 1
    answer_type: str = "multiple_entities"
    matched_template: str = ""
    strict_validation: bool = False

    def to_dict(self):
        return asdict(self)


class RouterV2:
    def __init__(self, catalog, encoder, *, variant="rule", tau=None, artifact=None, llm=None, knn_k=3):
        tau = float(config_get("router_v2.tau", .75)) if tau is None else tau
        if variant not in {"rule", "knn", "logistic", "llm"}:
            raise ValueError("Unknown router variant")
        if not .0 <= tau <= 1.0:
            raise ValueError("tau must be between zero and one")
        self.catalog, self.encoder = catalog, encoder
        self.variant, self.tau, self.artifact, self.llm, self.knn_k = variant, tau, artifact, llm, knn_k
        self.exemplar_embeddings = self._encode([s for r in ROUTES for s in EXEMPLARS[r]])

    def _encode(self, texts):
        array = np.asarray(self.encoder.encode(texts, normalize_embeddings=True), dtype=float)
        if array.ndim != 2 or not np.isfinite(array).all():
            raise ValueError("Invalid router embeddings")
        return array

    def features_for(self, question):
        text = norm(question)
        resolved = self.catalog.resolve(question)
        vector = self._encode([question])[0]
        similarities = (self.exemplar_embeddings @ vector).reshape(3, 3).max(axis=1)
        contains = lambda words: int(any(re.search(r"\b"+re.escape(w)+r"\b", text) for w in words))
        f = dict(resolved_entities=float(min(len(resolved), 5)),
                 relation=float(contains(["authored", "modified", "assigned", "merged", "depends", "commit", "issue", "contributor"])),
                 multi_hop=float(contains(["modified through commits authored", "authored commits that modified", "dependency path", "impact", "across dependencies"])),
                 aggregation=float(contains(["count", "how many", "most", "top", "list all", "highest", "lowest", "which files"])),
                 explanatory=float(contains(["why", "how", "explain", "what does"])),
                 semantic=float(contains(["code fragment", "contains the text", "documentation", "readme", "implementation", "function", "snippet"])))
        f.update({"exemplar_"+r: float(v) for r, v in zip(ROUTES, similarities)})
        return f, resolved, vector

    @staticmethod
    def rule_scores(f):
        g = 2.0*f["relation"] + 1.5*f["aggregation"] + .8*f["resolved_entities"] + .7*f["exemplar_graph"]
        v = .5 + 2.1*f["explanatory"] + 2.2*f["semantic"] - .8*f["relation"] - .6*f["aggregation"] + .7*f["exemplar_vector"]
        h = 3.5*f["multi_hop"] + 1.2*f["relation"]*f["explanatory"] + .7*f["exemplar_hybrid"]
        return softmax([g, v, h])

    def scores_for(self, question, f, embedding):
        if self.variant == "rule":
            return self.rule_scores(f)
        if self.variant in {"knn", "logistic"} and not self.artifact:
            raise RuntimeError("Router requires a trained, split-bound artifact")
        if self.variant == "knn":
            similarities = np.asarray(self.artifact["embeddings"]) @ embedding
            nearest = np.argsort(-similarities, kind="stable")[:self.knn_k]
            weights = np.exp(8*(similarities[nearest]-similarities[nearest].max()))
            scores = np.zeros(3)
            for index, weight in zip(nearest, weights):
                scores[ROUTES.index(self.artifact["labels"][index])] += weight
            return scores / scores.sum()
        if self.variant == "logistic":
            x = np.array([f[k] for k in FEATURES])
            x = (x-np.asarray(self.artifact["mean"]))/np.asarray(self.artifact["scale"])
            return softmax(np.asarray(self.artifact["weights"])@x+np.asarray(self.artifact["intercept"]))
        if self.llm is None:
            raise RuntimeError("LLM router requires a configured client")
        prompt = ("Choose repository retrieval. Graph: exact entities, relations, counts. Vector: code or prose meaning. "
                  "Hybrid: combined relations and explanation. Return ONLY a JSON object with graph, vector, hybrid "
                  "probabilities (nonnegative numbers summing to one).\nFeatures: "+json.dumps(f)+"\nQuestion: "+question)
        raw = self.llm.generate(prompt, temperature=0.0, max_output_tokens=200)
        try:
            obj = json.loads(raw)
            if set(obj) != set(ROUTES):
                raise ValueError("Router JSON must contain exactly the three routes")
            scores = np.array([obj[r] for r in ROUTES], dtype=float)
            if not np.isfinite(scores).all() or (scores<0).any() or not math.isclose(float(scores.sum()), 1., abs_tol=.02):
                raise ValueError("Invalid router probabilities")
            return scores / scores.sum()
        except (ValueError, TypeError) as exc:
            raise ValueError("LLM router parse failure") from exc

    def classify(self, question):
        f, resolved, embedding = self.features_for(question)
        scores = self.scores_for(question, f, embedding)
        preferred = ROUTES[int(np.argmax(scores))]
        confidence = float(max(scores))
        route = preferred if confidence >= self.tau else "hybrid"
        return Decision(route, preferred, confidence, dict(zip(ROUTES, map(float, scores))), f,
                        resolved, self.variant, self.tau, hops=3 if f["multi_hop"] else 1,
                        strict_validation=confidence < self.tau)


def train_artifact(variant, feature_rows, embeddings, labels):
    if not labels or not set(labels) <= set(ROUTES):
        raise ValueError("Training requires empirical labels")
    if variant == "knn":
        return dict(embeddings=np.asarray(embeddings).tolist(), labels=list(labels))
    if variant != "logistic":
        raise ValueError("Only knn/logistic have supervised artifacts")
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    if len(set(labels)) < 2:
        raise ValueError("Logistic training requires at least two observed route classes")
    x = np.array([[f[k] for k in FEATURES] for f in feature_rows])
    scaler = StandardScaler().fit(x)
    model = LogisticRegression(C=1., max_iter=2000, random_state=20261009).fit(scaler.transform(x), labels)
    # Preserve a slot for unseen classes without manufacturing training observations.
    weights = np.zeros((3, len(FEATURES)))
    intercept = np.full(3, -1e9)
    if len(model.classes_) == 2:
        for label, sign in zip(model.classes_, [-.5, .5]):
            index = ROUTES.index(label)
            weights[index] = sign*model.coef_[0]
            intercept[index] = sign*model.intercept_[0]
    else:
        for i, label in enumerate(model.classes_):
            weights[ROUTES.index(label)] = model.coef_[i]
            intercept[ROUTES.index(label)] = model.intercept_[i]
    return dict(weights=weights.tolist(), intercept=intercept.tolist(), mean=scaler.mean_.tolist(),
                scale=scaler.scale_.tolist(), classes=model.classes_.tolist())


def load_frozen(path, catalog, encoder, llm=None):
    path = Path(path)
    raw = path.read_bytes()
    expected = path.with_suffix(".sha256").read_text().strip()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Frozen router config checksum mismatch")
    config = json.loads(raw)
    if not config.get("selected") or not config.get("tuning_split_sha256"):
        raise ValueError("Router is not selected and frozen")
    if config.get("catalog_fingerprint") != catalog.fingerprint or config.get("feature_names") != list(FEATURES):
        raise ValueError("Frozen router feature/catalog mismatch")
    if config.get("exemplars") != EXEMPLARS:
        raise ValueError("Frozen router exemplar mismatch")
    if config["variant"] == "llm":
        from src.systems.ollama_router_client import OllamaRouterClient
        llm = OllamaRouterClient(config["llm_model"])
    return RouterV2(catalog, encoder, variant=config["variant"], tau=config["tau"],
                    artifact=config.get("artifact"), llm=llm, knn_k=config.get("knn_k", 3))


def retrieve_with_fallback(route, graph_retrieve, vector_retrieve, *, minimum_vector_score=.3, enabled=True):
    if route not in ROUTES:
        raise ValueError("Invalid retrieval route")
    graph = graph_retrieve() if route in {"graph", "hybrid"} else []
    vector = vector_retrieve() if route in {"vector", "hybrid"} else []
    reason = None
    if enabled and route == "graph" and not graph:
        reason = "empty_or_invalid_graph_evidence"
        vector = vector_retrieve()
    elif enabled and route == "vector" and (not vector or max(float(v.get("score", 0)) for v in vector) < minimum_vector_score):
        reason = "empty_vector_evidence" if not vector else "low_confidence_vector_evidence"
        graph = graph_retrieve()
    return dict(graph=graph, vector=vector, selected_route=route,
                executed_route="hybrid" if reason else route, fallback_used=reason is not None, fallback_reason=reason)
