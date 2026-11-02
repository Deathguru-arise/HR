"""Noise augmentation for training data to improve OCR robustness.

Generates noisy variants of clean training examples by applying
random perturbations that mimic real-world OCR and PDF extraction
artifacts. Each augmented example preserves BIO tag alignment.

Usage:
    from training.noise_augment import augment_examples
    noisy = augment_examples(clean_examples, multiplier=2)
"""

from __future__ import annotations

import random
import re
import string


def _swap_separator(token: str) -> str:
    """Randomly swap separator characters: | + - ●"""
    seps = {"|": ["+", "-", "●", "•"], "+": ["|", "-", "•"], "-": ["|", "+"], "●": ["|", "+", "•"], "•": ["|", "+", "●"]}
    if token in seps:
        return random.choice(seps[token])
    return token


def _corrupt_char(token: str) -> str:
    """Drop, swap, or insert a random character to mimic OCR errors."""
    if len(token) < 3:
        return token
    i = random.randint(0, len(token) - 1)
    action = random.choice(["drop", "swap", "insert"])
    if action == "drop":
        return token[:i] + token[i + 1:]
    elif action == "swap" and i < len(token) - 1:
        return token[:i] + token[i + 1] + token[i] + token[i + 2:]
    else:
        c = random.choice(string.ascii_lowercase)
        return token[:i] + c + token[i:]


def _merge_tokens(tokens: list[str], labels: list[str], idx: int) -> bool:
    """Merge token at idx with next token (remove space between them)."""
    if idx >= len(tokens) - 1:
        return False
    if labels[idx] != "O" or labels[idx + 1] != "O":
        return False
    tokens[idx] = tokens[idx] + tokens[idx + 1]
    tokens.pop(idx + 1)
    labels.pop(idx + 1)
    return True


def augment_one(tokens: list[str], labels: list[str], seed: int | None = None) -> tuple[list[str], list[str]]:
    """Create one noisy variant of a training example.

    Applies random subset of noise operations while preserving
    BIO tag alignment. Only modifies O-tagged tokens for safety,
    except separator swaps which can happen anywhere.
    """
    if seed is not None:
        random.seed(seed)

    tok = list(tokens)
    lab = list(labels)

    # 1. Swap separators (20% per separator token)
    for i in range(len(tok)):
        if tok[i] in ("|", "+", "-", "●", "•") and random.random() < 0.2:
            tok[i] = _swap_separator(tok[i])

    # 2. Corrupt characters in O-tagged tokens (5% chance per token)
    for i in range(len(tok)):
        if lab[i] == "O" and len(tok[i]) >= 3 and random.random() < 0.05:
            tok[i] = _corrupt_char(tok[i])

    # 3. Corrupt characters in entity tokens (3% chance — lower rate to keep most entities clean)
    for i in range(len(tok)):
        if lab[i] != "O" and len(tok[i]) >= 4 and random.random() < 0.03:
            tok[i] = _corrupt_char(tok[i])

    # 4. Merge adjacent O tokens (3% chance per pair)
    i = 0
    while i < len(tok) - 1:
        if random.random() < 0.03:
            _merge_tokens(tok, lab, i)
        else:
            i += 1

    # 5. Random case change on O tokens (5% chance)
    for i in range(len(tok)):
        if lab[i] == "O" and random.random() < 0.05:
            if random.random() < 0.5:
                tok[i] = tok[i].upper()
            else:
                tok[i] = tok[i].lower()

    # 6. Insert random line-break token between O tokens (2% chance)
    inserts = []
    for i in range(len(tok) - 1):
        if lab[i] == "O" and lab[i + 1] == "O" and random.random() < 0.02:
            inserts.append(i + 1)
    for offset, idx in enumerate(inserts):
        tok.insert(idx + offset, "\n")
        lab.insert(idx + offset, "O")

    return tok, lab


def augment_examples(
    examples: list[dict],
    multiplier: int = 2,
    seed: int = 42,
) -> list[dict]:
    """Generate noisy variants of training examples.

    Args:
        examples: list of {"tokens": [...], "ner_tags": [...], ...}
        multiplier: how many noisy copies per clean example
        seed: random seed for reproducibility

    Returns:
        List of augmented examples (does NOT include originals)
    """
    try:
        from training.labels import ID2LABEL, LABEL2ID
    except ModuleNotFoundError:
        from labels import ID2LABEL, LABEL2ID

    random.seed(seed)
    augmented = []

    for ex_idx, example in enumerate(examples):
        tokens = example["tokens"]
        labels = [ID2LABEL[tag] for tag in example["ner_tags"]]

        for copy_idx in range(multiplier):
            aug_tokens, aug_labels = augment_one(
                tokens, labels,
                seed=seed + ex_idx * 1000 + copy_idx,
            )
            aug_example = {
                "tokens": aug_tokens,
                "ner_tags": [LABEL2ID[l] for l in aug_labels],
            }
            if "metadata" in example:
                meta = dict(example["metadata"])
                meta["source_id"] = f"{meta.get('source_id', '')}:aug{copy_idx}"
                meta["group_id"] = meta.get("group_id", "")
                aug_example["metadata"] = meta
            augmented.append(aug_example)

    return augmented
