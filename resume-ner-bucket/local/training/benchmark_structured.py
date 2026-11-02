from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

from training.benchmark_utils import classify_resume_noise
from training.labels import ID2LABEL
from training.structured_postprocess import StructuredPostProcessor, build_text_and_spans

ALLOWED_INPUTS = {"input_ids", "attention_mask"}


def predicted_spans_from_text(text: str, offset_mapping: list[tuple[int, int]], pred_ids: list[int]) -> tuple[str, list]:
    spans = []
    current = None
    for (start, end), tag_id in zip(offset_mapping, pred_ids):
        if start == end:
            continue
        label = ID2LABEL[tag_id]
        if label == "O":
            if current:
                spans.append(current)
                current = None
            continue
        bio, base = label.split("-", 1)
        piece = text[start:end]
        if current is None or bio == "B" or current.label != base:
            if current:
                spans.append(current)
            from training.structured_postprocess import Span

            current = Span(label=base, text=piece, start=start, end=end, bio=bio, score=1.0)
        else:
            gap = text[current.end:start]
            current.text += gap + piece
            current.end = end
    if current:
        spans.append(current)
    return text, spans


def _split_into_sections(text: str) -> list[str]:
    """Split resume text at double-newline boundaries into paragraph blocks."""
    return [block for block in re.split(r"\n{2,}", text) if block.strip()]


def chunked_predicted_spans(
    text: str,
    model,
    tokenizer,
    max_length: int = 512,
) -> tuple[str, list]:
    """Run inference with section-aware chunking for texts exceeding max_length.

    Splits at paragraph boundaries so entities are never cut mid-span.
    Each chunk is a group of consecutive sections that fits within max_length.
    Character offsets are mapped back to the original text.
    """
    num_tokens = len(tokenizer(text, truncation=False)["input_ids"])

    if num_tokens <= max_length:
        tokenized = tokenizer(text, return_tensors="pt", return_offsets_mapping=True, truncation=True, max_length=max_length)
        encoded = {k: v for k, v in tokenized.items() if k in ALLOWED_INPUTS}
        with torch.no_grad():
            pred_ids = model(**encoded).logits.argmax(dim=-1).squeeze(0).cpu().tolist()
        offsets = [tuple(pair) for pair in tokenized["offset_mapping"].squeeze(0).cpu().tolist()][1:-1]
        return predicted_spans_from_text(text, offsets, pred_ids[1:-1])

    sections = _split_into_sections(text)

    chunks: list[str] = []
    chunk_offsets: list[int] = []
    current_sections: list[str] = []
    current_offset = 0

    for section in sections:
        candidate = "\n\n".join(current_sections + [section]) if current_sections else section
        tok_len = len(tokenizer(candidate, truncation=False)["input_ids"])
        if tok_len > max_length and current_sections:
            chunk_text = "\n\n".join(current_sections)
            chunks.append(chunk_text)
            chunk_offsets.append(current_offset)
            current_offset = text.index(section, current_offset)
            current_sections = [section]
        else:
            if not current_sections:
                current_offset = text.index(section, current_offset)
            current_sections.append(section)

    if current_sections:
        chunks.append("\n\n".join(current_sections))
        chunk_offsets.append(current_offset)

    all_spans = []
    for chunk_text, char_offset in zip(chunks, chunk_offsets):
        tokenized = tokenizer(chunk_text, return_tensors="pt", return_offsets_mapping=True, truncation=True, max_length=max_length)
        encoded = {k: v for k, v in tokenized.items() if k in ALLOWED_INPUTS}
        with torch.no_grad():
            pred_ids = model(**encoded).logits.argmax(dim=-1).squeeze(0).cpu().tolist()
        offsets = [tuple(pair) for pair in tokenized["offset_mapping"].squeeze(0).cpu().tolist()][1:-1]
        _, spans = predicted_spans_from_text(chunk_text, offsets, pred_ids[1:-1])

        for span in spans:
            from training.structured_postprocess import Span

            all_spans.append(Span(
                label=span.label,
                text=span.text,
                start=span.start + char_offset,
                end=span.end + char_offset,
                bio=span.bio,
                score=span.score,
            ))

    return text, all_spans


def normalize_value(field: str, value: str | None) -> str | None:
    if not value:
        return None
    normalized = " ".join(value.lower().split()).strip()
    if not normalized:
        return None
    if "phone" in field:
        normalized = normalized.replace("+", "plus")
        normalized = "".join(ch for ch in normalized if ch.isdigit() or ch.isalpha())
    if "email" in field:
        normalized = normalized.replace(" ", "")
    if "date" in field:
        month_map = {
            "jan": "january",
            "feb": "february",
            "mar": "march",
            "apr": "april",
            "jun": "june",
            "jul": "july",
            "aug": "august",
            "sep": "september",
            "oct": "october",
            "nov": "november",
            "dec": "december",
        }
        for short, full in month_map.items():
            normalized = normalized.replace(short, full)
        normalized = normalized.replace(" - ", "-")
    return normalized.strip(" ,.;:|/-")


def flatten_resume(parsed: dict) -> dict[str, list[str]]:
    flat: dict[str, list[str]] = defaultdict(list)

    def push(field: str, value: str | None) -> None:
        normalized = normalize_value(field, value)
        if normalized:
            flat[field].append(normalized)

    personal = parsed["personal"]
    push("personal.name", personal.get("name"))
    push("personal.email", personal.get("email"))
    push("personal.phone", personal.get("phone"))
    push("personal.location", personal.get("location"))

    for exp in parsed["experience"]:
        push("experience.title", exp.get("title"))
        push("experience.company", exp.get("company"))
        push("experience.start_date", exp.get("start_date"))
        push("experience.end_date", exp.get("end_date"))

    for edu in parsed["education"]:
        push("education.degree", edu.get("degree"))
        push("education.field", edu.get("field"))
        push("education.institution", edu.get("institution"))

    for skill in parsed["skills"]:
        push("skills", skill)
    for cert in parsed["certifications"]:
        push("certifications", cert)
    push("country", parsed.get("country"))
    push("seniority", parsed.get("seniority"))
    return flat


def score_field(gold: list[str], pred: list[str]) -> Counter:
    gold_counter = Counter(gold)
    pred_counter = Counter(pred)
    overlap = gold_counter & pred_counter
    return Counter(
        tp=sum(overlap.values()),
        fp=sum((pred_counter - overlap).values()),
        fn=sum((gold_counter - overlap).values()),
    )


def metrics_from_counts(counts: Counter) -> dict[str, float]:
    tp = counts["tp"]
    fp = counts["fp"]
    fn = counts["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Structured extraction benchmark using in-repo post-processing. Better than raw span proxy, still internal-facing."
    )
    parser.add_argument("--model-dir", default=".")
    parser.add_argument("--val-path", default="training/data/ner_val.json")
    args = parser.parse_args()

    payload = json.load(open(args.val_path))
    examples = payload["data"]
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir)
    model = AutoModelForTokenClassification.from_pretrained(args.model_dir)
    model.eval()
    postprocessor = StructuredPostProcessor(args.model_dir)

    totals_by_field: dict[str, Counter] = {}
    bucket_totals: dict[str, Counter] = defaultdict(lambda: Counter(tp=0, fp=0, fn=0, examples=0))
    for example in examples:
        gold_text, gold_spans = build_text_and_spans(example["tokens"], example["ner_tags"], ID2LABEL)
        gold_structured = postprocessor.build_structured_resume_from_spans(gold_spans, gold_text)
        bucket_info = classify_resume_noise(gold_text)
        bucket = str(bucket_info["bucket"])
        bucket_totals[bucket]["examples"] += 1

        pred_text, pred_spans = chunked_predicted_spans(gold_text, model, tokenizer)
        pred_structured = postprocessor.build_structured_resume_from_spans(pred_spans, pred_text)

        gold_flat = flatten_resume(gold_structured)
        pred_flat = flatten_resume(pred_structured)
        for field in sorted(set(gold_flat) | set(pred_flat)):
            counts = score_field(gold_flat.get(field, []), pred_flat.get(field, []))
            totals_by_field.setdefault(field, Counter(tp=0, fp=0, fn=0)).update(counts)
            bucket_totals[bucket].update(counts)

    micro = Counter(tp=0, fp=0, fn=0)
    macro_f1 = 0.0
    per_field = {}
    for field in sorted(totals_by_field):
        counts = totals_by_field[field]
        micro.update(counts)
        metrics = metrics_from_counts(counts)
        macro_f1 += metrics["f1"]
        per_field[field] = {**counts, **metrics}

    output = {
        "examples": len(examples),
        "micro": {**micro, **metrics_from_counts(micro)},
        "macro_f1": macro_f1 / len(per_field) if per_field else 0.0,
        "by_bucket": {
            bucket: {
                "examples": counts["examples"],
                "tp": counts["tp"],
                "fp": counts["fp"],
                "fn": counts["fn"],
                **metrics_from_counts(counts),
            }
            for bucket, counts in sorted(bucket_totals.items())
        },
        "per_field": per_field,
        "note": "Uses in-repo structured post-processing for gold spans and predictions. Better than raw span matching, but still internal regression metric.",
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
