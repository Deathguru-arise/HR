from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path

try:
    from training.labels import ID2LABEL, build_meta
except ModuleNotFoundError:
    from labels import ID2LABEL, build_meta


def set_global_seed(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except Exception:
        pass
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


def example_key(example: dict) -> tuple[tuple[str, ...], tuple[int, ...]]:
    return tuple(example["tokens"]), tuple(example["ner_tags"])


def dedupe_examples(examples: list[dict]) -> tuple[list[dict], int]:
    seen = set()
    unique = []
    removed = 0
    for example in examples:
        key = example_key(example)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        unique.append(example)
    return unique, removed


def example_group_id(example: dict) -> str:
    metadata = example.get("metadata") or {}
    return metadata.get("group_id") or metadata.get("source_id") or " ".join(example["tokens"])


def stable_split_examples(examples: list[dict], train_ratio: float = 0.85) -> tuple[list[dict], list[dict]]:
    grouped = {}
    for example in examples:
        grouped.setdefault(example_group_id(example), []).append(example)

    train, val = [], []
    threshold = int(train_ratio * 10_000)
    for group_id, group_examples in grouped.items():
        bucket = int(hashlib.sha256(group_id.encode("utf-8")).hexdigest()[:8], 16) % 10_000
        (train if bucket < threshold else val).extend(group_examples)

    if not train or not val:
        ordered_groups = list(grouped.values())
        pivot = max(1, int(len(ordered_groups) * train_ratio))
        train = [example for group in ordered_groups[:pivot] for example in group]
        val = [example for group in ordered_groups[pivot:] for example in group]
    return train, val


def dataset_stats(examples: list[dict]) -> dict:
    lengths = [len(example["tokens"]) for example in examples]
    label_counts = Counter()
    for example in examples:
        for tag_id in example["ner_tags"]:
            label = ID2LABEL[tag_id]
            if label != "O":
                label_counts[label[2:]] += 1
    return {
        "examples": len(examples),
        "avg_tokens": round(sum(lengths) / len(lengths), 2) if lengths else 0,
        "max_tokens": max(lengths) if lengths else 0,
        "truncated_512": sum(1 for length in lengths if length == 512),
        "label_counts": dict(label_counts),
    }


def write_dataset(train: list[dict], val: list[dict], data_dir: Path, manifest: dict | None = None) -> None:
    meta = build_meta()
    with open(data_dir / "ner_train.json", "w") as f:
        json.dump({"data": train, "meta": meta}, f)
    with open(data_dir / "ner_val.json", "w") as f:
        json.dump({"data": val, "meta": meta}, f)
    if manifest is not None:
        manifest = {
            **manifest,
            "train": dataset_stats(train),
            "val": dataset_stats(val),
        }
        with open(data_dir / "dataset_manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)
