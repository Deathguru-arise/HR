from __future__ import annotations

LABEL_LIST = [
    "O",
    "B-NAME", "I-NAME",
    "B-EMAIL", "I-EMAIL",
    "B-PHONE", "I-PHONE",
    "B-LOCATION", "I-LOCATION",
    "B-COMPANY", "I-COMPANY",
    "B-TITLE", "I-TITLE",
    "B-DATE", "I-DATE",
    "B-DEGREE", "I-DEGREE",
    "B-INSTITUTION", "I-INSTITUTION",
    "B-FIELD", "I-FIELD",
    "B-SKILL", "I-SKILL",
    "B-CERT", "I-CERT",
    "B-LANGUAGE", "I-LANGUAGE",
]

LABEL2ID = {label: i for i, label in enumerate(LABEL_LIST)}
ID2LABEL = {i: label for i, label in enumerate(LABEL_LIST)}


def build_meta() -> dict:
    return {
        "label_list": LABEL_LIST,
        "label2id": LABEL2ID,
        "id2label": ID2LABEL,
    }
