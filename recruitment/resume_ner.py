"""Offline inference wrapper for the downloaded resume DistilBERT model."""

import json
import os
from functools import lru_cache
from pathlib import Path

MODEL_DIR = Path(os.environ.get(
    "RESUME_NER_MODEL_DIR",
    Path(__file__).resolve().parent.parent / "resume-ner-bucket" / "local",
))
QUANTIZED_MODEL = MODEL_DIR / "onnx" / "model_quantized.onnx"
LABEL_CONFIG = MODEL_DIR / "label_config.json"


@lru_cache(maxsize=1)
def _load_runtime():
    import numpy as np
    import onnxruntime as ort
    from transformers import AutoTokenizer

    if not QUANTIZED_MODEL.is_file():
        return None
    config = json.loads(LABEL_CONFIG.read_text(encoding="utf-8"))
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR), local_files_only=True)
    session = ort.InferenceSession(str(QUANTIZED_MODEL), providers=["CPUExecutionProvider"])
    return np, tokenizer, session, config["label_list"]


def extract_entities(text):
    """Return entity spans from local ONNX inference, or [] if unavailable."""
    try:
        runtime = _load_runtime()
        if not runtime:
            return []
        np, tokenizer, session, labels = runtime
        encoded = tokenizer(
            text, return_tensors="np", return_offsets_mapping=True,
            truncation=True, max_length=512, stride=64,
            return_overflowing_tokens=True,
        )
        offsets = encoded.pop("offset_mapping")
        encoded.pop("overflow_to_sample_mapping", None)
        inputs = {item.name for item in session.get_inputs()}
        spans = []
        for row, offset_row in enumerate(offsets):
            feed = {name: encoded[name][row:row + 1].astype(np.int64) for name in inputs if name in encoded}
            logits = session.run(None, feed)[0][0]
            current = None
            for (start, end), label_id, score in zip(offset_row, logits.argmax(axis=-1), logits.max(axis=-1)):
                start, end = int(start), int(end)
                if start == end:
                    continue
                tag = labels[int(label_id)]
                if tag == "O":
                    if current:
                        spans.append(current)
                        current = None
                    continue
                prefix, _, entity_type = tag.partition("-")
                if not entity_type:
                    continue
                if current and prefix == "I" and current["label"] == entity_type and start <= current["end"] + 2:
                    current["end"] = end
                    current["scores"].append(float(score))
                else:
                    if current:
                        spans.append(current)
                    current = {"label": entity_type, "start": start, "end": end, "scores": [float(score)]}
            if current:
                spans.append(current)

        # Sliding windows overlap. Deduplicate spans by label and character range.
        unique = {}
        for span in spans:
            key = (span["label"], span["start"], span["end"])
            previous = unique.get(key)
            confidence = sum(span["scores"]) / len(span["scores"])
            if previous is None or confidence > previous["confidence"]:
                unique[key] = {"label": span["label"], "start": span["start"],
                               "end": span["end"], "text": text[span["start"]:span["end"]],
                               "confidence": round(confidence, 4)}
        return sorted(unique.values(), key=lambda item: (item["start"], item["end"]))
    except Exception:
        # Resume analysis must remain available if the optional local model is
        # missing, incompatible, or unable to load its artifact.
        return []


def graduation_year_from_entities(text, entities):
    """Prefer a year in education context; otherwise leave the rule result intact."""
    import re

    years = []
    for entity in entities:
        if entity["label"] != "DATE":
            continue
        year_match = re.search(r"\b(?:19|20)\d{2}\b", entity["text"])
        if not year_match:
            continue
        year = int(year_match.group())
        context = text[max(0, entity["start"] - 180):min(len(text), entity["end"] + 180)].lower()
        if any(word in context for word in ("education", "graduat", "bachelor", "master", "degree", "university", "college", "b.tech", "b.e.")):
            years.append((year, entity["confidence"]))
    if not years:
        return None
    return max(years, key=lambda item: (item[1], item[0]))[0]


def model_status():
    if not QUANTIZED_MODEL.is_file():
        return {"enabled": False, "model": "resume-ner-distilbert-onnx-int8", "message": "Resume extraction model files are missing."}
    return {"enabled": True, "model": "resume-ner-distilbert-onnx-int8", "message": "Local resume field extraction is enabled (ONNX INT8)."}
