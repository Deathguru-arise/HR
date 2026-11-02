"""Build gold-labeled training data from hand-annotated resume resource PDFs.

Merges batch annotation files, fuzzy-matches entity spans against
extracted text, converts to BIO tags, and writes training JSON.

Run: python -m training.build_gold_labels
"""

import json
import re
from collections import Counter
from pathlib import Path

try:
    from training.labels import LABEL2ID
    from training.tagging import tag_exact_words
except ModuleNotFoundError:
    from labels import LABEL2ID
    from tagging import tag_exact_words


def load_all_annotations() -> dict:
    import importlib
    all_annotations = {}
    for i in range(1, 5):
        mod = importlib.import_module(f"training.gold_labels_batch{i}")
        all_annotations.update(mod.ANNOTATIONS)
    return all_annotations


def normalize_for_matching(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def find_span_in_text(span_text: str, full_text: str) -> bool:
    if span_text in full_text:
        return True
    normalized_span = normalize_for_matching(span_text)
    normalized_text = normalize_for_matching(full_text)
    if normalized_span in normalized_text:
        return True
    return False


def main():
    texts = json.load(open(Path(__file__).parent / "data" / "sources" / "resume_resource_texts.json"))
    annotations = load_all_annotations()

    print(f"Resumes: {len(annotations)}")

    examples = []
    total_entities = 0
    matched_entities = 0
    unmatched_entities = 0
    unmatched_log = []

    for name in sorted(annotations.keys()):
        if name not in texts:
            print(f"  SKIP {name}: not in extracted texts")
            continue

        text = texts[name]
        normalized_text = normalize_for_matching(text)
        tokens = text.split()
        labels = ["O"] * len(tokens)

        for span_text, label_type in annotations[name]:
            total_entities += 1
            tagged = tag_exact_words(tokens, labels, span_text, label_type)
            if tagged > 0:
                matched_entities += 1
                continue

            norm_span = normalize_for_matching(span_text)
            tagged = tag_exact_words(tokens, labels, norm_span, label_type)
            if tagged > 0:
                matched_entities += 1
                continue

            unmatched_entities += 1
            if len(unmatched_log) < 50:
                unmatched_log.append((name, label_type, span_text[:80]))

        tagged_count = sum(1 for l in labels if l != "O")
        if tagged_count >= 3:
            examples.append({
                "tokens": tokens,
                "ner_tags": [LABEL2ID[l] for l in labels],
                "metadata": {
                    "source": "resume_resource_gold",
                    "source_id": f"rr_gold:{name}",
                    "group_id": f"rr_gold:{name}",
                },
            })

    print(f"\nEntities: {total_entities} total, {matched_entities} matched ({100*matched_entities/total_entities:.1f}%), {unmatched_entities} unmatched")
    print(f"Examples built: {len(examples)}")

    if unmatched_log:
        print(f"\nFirst {len(unmatched_log)} unmatched:")
        for name, label, text in unmatched_log:
            print(f"  [{name}] {label}: {text!r}")

    token_counts = [len(e["tokens"]) for e in examples]
    print(f"\nToken counts: min={min(token_counts)}, max={max(token_counts)}, avg={sum(token_counts)//len(token_counts)}")

    label_counts = Counter()
    for e in examples:
        for tag in e["ner_tags"]:
            from training.labels import ID2LABEL
            label = ID2LABEL[tag]
            if label != "O":
                label_counts[label[2:]] += 1
    print("\nLabel distribution:")
    for label, count in label_counts.most_common():
        print(f"  {label:15s}: {count}")

    out_path = Path(__file__).parent / "data" / "gold" / "resume_resource_gold.json"
    with open(out_path, "w") as f:
        json.dump({"data": examples}, f)
    print(f"\nWrote {len(examples)} examples to {out_path}")


if __name__ == "__main__":
    main()
