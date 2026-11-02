from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

from training.benchmark_structured import ALLOWED_INPUTS, flatten_resume, predicted_spans_from_text
from training.benchmark_utils import classify_resume_noise
from training.labels import ID2LABEL
from training.structured_postprocess import StructuredPostProcessor, build_text_and_spans


def counter_diff_size(gold: list[str], pred: list[str]) -> tuple[int, int, int]:
    gold_counter = Counter(gold)
    pred_counter = Counter(pred)
    overlap = gold_counter & pred_counter
    tp = sum(overlap.values())
    fp = sum((pred_counter - overlap).values())
    fn = sum((gold_counter - overlap).values())
    return tp, fp, fn


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze per-resume structured extraction errors and outliers")
    parser.add_argument("--model-dir", default=".")
    parser.add_argument("--val-path", default="training/data/ner_val.json")
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    payload = json.load(open(args.val_path))
    examples = payload["data"]
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir)
    model = AutoModelForTokenClassification.from_pretrained(args.model_dir)
    model.eval()
    postprocessor = StructuredPostProcessor(args.model_dir)

    per_resume = []
    field_error_counts = Counter()
    bucket_counts = Counter()
    total_fp = 0
    total_fn = 0
    total_tp = 0

    for idx, example in enumerate(examples):
        gold_text, gold_spans = build_text_and_spans(example["tokens"], example["ner_tags"], ID2LABEL)
        gold_structured = postprocessor.build_structured_resume_from_spans(gold_spans, gold_text)
        bucket_info = classify_resume_noise(gold_text)
        bucket_counts[str(bucket_info["bucket"])] += 1

        tokenized = tokenizer(gold_text, return_tensors="pt", return_offsets_mapping=True, truncation=True, max_length=512)
        encoded = {k: v for k, v in tokenized.items() if k in ALLOWED_INPUTS}
        with torch.no_grad():
            pred_ids = model(**encoded).logits.argmax(dim=-1).squeeze(0).cpu().tolist()

        offsets = [tuple(pair) for pair in tokenized["offset_mapping"].squeeze(0).cpu().tolist()][1:-1]
        pred_text, pred_spans = predicted_spans_from_text(gold_text, offsets, pred_ids[1:-1])
        pred_structured = postprocessor.build_structured_resume_from_spans(pred_spans, pred_text)

        gold_flat = flatten_resume(gold_structured)
        pred_flat = flatten_resume(pred_structured)
        resume_fp = 0
        resume_fn = 0
        mismatched_fields = []

        for field in sorted(set(gold_flat) | set(pred_flat)):
            tp, fp, fn = counter_diff_size(gold_flat.get(field, []), pred_flat.get(field, []))
            total_tp += tp
            total_fp += fp
            total_fn += fn
            resume_fp += fp
            resume_fn += fn
            if fp or fn:
                field_error_counts[field] += fp + fn
                mismatched_fields.append(
                    {
                        "field": field,
                        "gold": gold_flat.get(field, []),
                        "pred": pred_flat.get(field, []),
                        "fp": fp,
                        "fn": fn,
                    }
                )

        per_resume.append(
            {
                "index": idx,
                "text_preview": gold_text[:300],
                "bucket": bucket_info["bucket"],
                "noise_signals": bucket_info["signals"],
                "gold_field_count": sum(len(v) for v in gold_flat.values()),
                "pred_field_count": sum(len(v) for v in pred_flat.values()),
                "tp": sum(min(Counter(gold_flat.get(f, []))[k], Counter(pred_flat.get(f, []))[k]) for f in set(gold_flat) | set(pred_flat) for k in (Counter(gold_flat.get(f, [])) & Counter(pred_flat.get(f, [])))),
                "fp": resume_fp,
                "fn": resume_fn,
                "errors": resume_fp + resume_fn,
                "mismatched_fields": mismatched_fields,
            }
        )

    error_values = [item["errors"] for item in per_resume]
    avg_errors = sum(error_values) / len(error_values) if error_values else 0.0
    median_errors = sorted(error_values)[len(error_values) // 2] if error_values else 0
    zero_error = sum(1 for value in error_values if value == 0)
    one_or_less = sum(1 for value in error_values if value <= 1)
    three_or_more = sum(1 for value in error_values if value >= 3)
    outliers = sorted(per_resume, key=lambda item: (-item["errors"], item["index"]))[: args.top_k]

    summary = {
        "examples": len(per_resume),
        "avg_errors_per_resume": avg_errors,
        "median_errors_per_resume": median_errors,
        "zero_error_resumes": zero_error,
        "zero_error_rate": zero_error / len(per_resume) if per_resume else 0.0,
        "one_or_less_error_resumes": one_or_less,
        "one_or_less_error_rate": one_or_less / len(per_resume) if per_resume else 0.0,
        "three_or_more_error_resumes": three_or_more,
        "three_or_more_error_rate": three_or_more / len(per_resume) if per_resume else 0.0,
        "micro": {
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
        },
        "bucket_counts": dict(bucket_counts),
        "top_error_fields": field_error_counts.most_common(10),
        "outliers": outliers,
        "note": "errors = fp + fn over flattened structured fields per resume",
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
