"""Small, offline TF-IDF skill retriever trained from this app's skill taxonomy.

The index is a discovery aid only. It never changes the rubric score or makes a
selection recommendation; recruiters can inspect every suggestion in context.
"""

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .services import ALIASES, SKILL_VOCAB

MODEL_PATH = Path(__file__).resolve().parent / "data" / "skill_model.json"
TOKEN_RE = re.compile(r"[a-z0-9]+(?:[+#.][a-z0-9]+)*", re.IGNORECASE)
STOP_WORDS = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "with"}


def _tokens(text):
    return [token.lower() for token in TOKEN_RE.findall(text) if token.lower() not in STOP_WORDS]


def train_skill_model(path=MODEL_PATH):
    """Fit a taxonomy-specific TF-IDF index and save its compact local artifact."""
    aliases_by_skill = {}
    for alias, canonical in ALIASES.items():
        aliases_by_skill.setdefault(canonical.lower(), []).append(alias)

    documents = []
    for skill in SKILL_VOCAB:
        aliases = aliases_by_skill.get(skill.lower(), [])
        # Phrase repetitions give multiword skill names and known aliases a
        # stable representation without importing third-party model packages.
        text = " ".join([skill] * 3 + aliases)
        terms = Counter(_tokens(text))
        documents.append({"skill": skill, "terms": dict(terms)})

    doc_count = max(1, len(documents))
    document_frequency = Counter(
        term for document in documents for term in document["terms"]
    )
    idf = {
        term: round(math.log((1 + doc_count) / (1 + frequency)) + 1, 8)
        for term, frequency in document_frequency.items()
    }
    artifact = {
        "format": 1,
        "model": "placement-skill-tfidf-v1",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_documents": len(documents),
        "training_source": "built-in skill taxonomy and alias vocabulary",
        "idf": idf,
        "skills": documents,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact


def load_skill_model(path=MODEL_PATH):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def suggest_skills(text, already_found=(), limit=8, path=MODEL_PATH):
    """Return high-confidence taxonomy neighbors without affecting scoring."""
    artifact = load_skill_model(path)
    if not artifact:
        return []
    idf = artifact.get("idf", {})
    query_counts = Counter(_tokens(text))
    query = {term: count * idf.get(term, 0) for term, count in query_counts.items()}
    query_norm = math.sqrt(sum(weight * weight for weight in query.values()))
    if not query_norm:
        return []

    excluded = {skill.lower() for skill in already_found}
    matches = []
    for document in artifact.get("skills", []):
        skill = document["skill"]
        if skill.lower() in excluded:
            continue
        vector = {term: count * idf.get(term, 0) for term, count in document["terms"].items()}
        norm = math.sqrt(sum(weight * weight for weight in vector.values()))
        if not norm:
            continue
        similarity = sum(weight * query.get(term, 0) for term, weight in vector.items()) / (norm * query_norm)
        if similarity >= 0.20:
            matches.append({"skill": skill, "similarity": round(similarity, 3)})
    return sorted(matches, key=lambda item: (-item["similarity"], item["skill"]))[:limit]
