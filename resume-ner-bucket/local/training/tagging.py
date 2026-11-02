from __future__ import annotations

from training.labels import LABEL2ID
from training.structured_postprocess import Span


def normalize_token(text: str) -> str:
    return text.strip().rstrip(",.;:|")


def find_span_in_tokens(tokens: list[str], target: str, start_from: int = 0, max_window: int = 50) -> tuple[int, int] | None:
    target_lower = target.lower().strip()
    if not target_lower:
        return None

    for i in range(start_from, len(tokens)):
        combined = ""
        for j in range(i, min(i + max_window, len(tokens))):
            combined = f"{combined} {tokens[j]}".strip()
            combined_clean = combined.lower().strip()
            if combined_clean == target_lower:
                return i, j
            if target_lower in combined_clean and len(combined_clean) <= len(target_lower) + 5:
                return i, j
            if len(combined_clean) > len(target_lower) + 20:
                break
    return None


def annotate_span(tokens: list[str], labels: list[str], target: str, label_type: str, start_from: int = 0) -> int:
    span = find_span_in_tokens(tokens, target, start_from)
    if span is None:
        return start_from

    start, end = span
    for idx in range(start, end + 1):
        if labels[idx] == "O":
            labels[idx] = f"B-{label_type}" if idx == start else f"I-{label_type}"
    return end + 1


def tag_exact_words(tokens: list[str], labels: list[str], text: str, label_type: str, start_from: int = 0) -> int:
    words = text.split()
    if not words:
        return start_from
    for i in range(start_from, len(tokens) - len(words) + 1):
        matched = True
        for j, word in enumerate(words):
            if normalize_token(tokens[i + j]).lower().lstrip("-") != normalize_token(word).lower().lstrip("-"):
                matched = False
                break
        if matched:
            for j in range(len(words)):
                idx = i + j
                if labels[idx] == "O":
                    labels[idx] = f"B-{label_type}" if j == 0 else f"I-{label_type}"
            return i + len(words)
    return start_from


def spans_to_bio(tokens: list[str], spans: list[Span], text: str) -> list[int]:
    labels = [0] * len(tokens)
    char_to_token = {}
    pos = 0
    for i, tok in enumerate(tokens):
        idx = text.find(tok, pos)
        if idx == -1:
            idx = pos
        for char_idx in range(idx, idx + len(tok)):
            char_to_token[char_idx] = i
        pos = idx + len(tok)

    for span in spans:
        token_indices = sorted({char_to_token[char_idx] for char_idx in range(span.start, span.end) if char_idx in char_to_token})
        if not token_indices:
            continue
        b_label = LABEL2ID.get(f"B-{span.label}", 0)
        i_label = LABEL2ID.get(f"I-{span.label}", 0)
        for offset, token_idx in enumerate(token_indices):
            if labels[token_idx] == 0:
                labels[token_idx] = b_label if offset == 0 else i_label

    return labels
