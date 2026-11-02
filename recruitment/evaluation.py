"""
Evaluation metrics & benchmark framework for measuring agreement between
Placement Intelligence and real HR recruiters.

Metrics computed:
1. Skill Extraction: Precision, Recall, F1 score against HR ground truth
2. Shortlist Overlap: Top-K intersection ratio
3. Ranking Agreement: Spearman's rank correlation coefficient
4. Band Agreement: Cohen's Kappa for triage priority (High/Medium/Low vs Shortlist/Hold/Reject)
"""

import csv
import io
import math
from typing import Dict, List, Any


def compute_skill_metrics(predicted_skills: List[str], ground_truth_skills: List[str]) -> Dict[str, float]:
    """Compute Precision, Recall, and F1 score for extracted skills."""
    pred_set = {s.strip().lower() for s in predicted_skills if s.strip()}
    truth_set = {s.strip().lower() for s in ground_truth_skills if s.strip()}

    if not truth_set and not pred_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 0, "fp": 0, "fn": 0}
    if not truth_set:
        return {"precision": 0.0, "recall": 1.0, "f1": 0.0, "tp": 0, "fp": len(pred_set), "fn": 0}
    if not pred_set:
        return {"precision": 1.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": len(truth_set)}

    tp = len(pred_set & truth_set)
    fp = len(pred_set - truth_set)
    fn = len(truth_set - pred_set)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp, "fp": fp, "fn": fn,
    }


def compute_top_k_overlap(predicted_ranked_ids: List[Any], hr_ranked_ids: List[Any], k: int = 5) -> float:
    """Compute top-k overlap ratio (intersection over k)."""
    if k <= 0:
        return 0.0
    pred_top_k = set(predicted_ranked_ids[:k])
    hr_top_k = set(hr_ranked_ids[:k])
    actual_k = min(k, len(predicted_ranked_ids), len(hr_ranked_ids))
    if actual_k == 0:
        return 1.0
    overlap = len(pred_top_k & hr_top_k)
    return round(overlap / actual_k, 4)


def compute_spearman_correlation(ranks_x: List[float], ranks_y: List[float]) -> float:
    """
    Compute Spearman's rank correlation coefficient (rho) in pure Python.
    Handles tied ranks via fractional ranking.
    """
    n = len(ranks_x)
    if n < 2 or len(ranks_y) != n:
        return 0.0

    def _rankify(values):
        indexed = sorted(enumerate(values), key=lambda x: x[1])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(indexed):
            j = i
            while j < len(indexed) and indexed[j][1] == indexed[i][1]:
                j += 1
            avg_rank = (i + 1 + j) / 2.0
            for k_idx in range(i, j):
                ranks[indexed[k_idx][0]] = avg_rank
            i = j
        return ranks

    rx = _rankify(ranks_x)
    ry = _rankify(ranks_y)

    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n

    num = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    den_x = math.sqrt(sum((rx[i] - mean_rx) ** 2 for i in range(n)))
    den_y = math.sqrt(sum((ry[i] - mean_ry) ** 2 for i in range(n)))

    if den_x == 0 or den_y == 0:
        return 0.0
    return round(num / (den_x * den_y), 4)


def compute_cohens_kappa(labels_pred: List[str], labels_truth: List[str], categories: List[str] = None) -> float:
    """
    Compute Cohen's Kappa for inter-rater agreement between system band and HR verdict.
    """
    if len(labels_pred) != len(labels_truth) or not labels_pred:
        return 0.0

    if categories is None:
        categories = sorted(list(set(labels_pred) | set(labels_truth)))

    n = len(labels_pred)
    cat_to_idx = {c: i for i, c in enumerate(categories)}
    num_cats = len(categories)

    # Build confusion matrix
    matrix = [[0] * num_cats for _ in range(num_cats)]
    for p, t in zip(labels_pred, labels_truth):
        matrix[cat_to_idx[p]][cat_to_idx[t]] += 1

    # Observed agreement
    po = sum(matrix[i][i] for i in range(num_cats)) / n

    # Chance agreement
    pe = 0.0
    for i in range(num_cats):
        row_sum = sum(matrix[i][j] for j in range(num_cats))
        col_sum = sum(matrix[j][i] for j in range(num_cats))
        pe += (row_sum * col_sum) / (n * n)

    if pe == 1.0:
        return 1.0
    kappa = (po - pe) / (1.0 - pe)
    return round(kappa, 4)


def generate_hr_labeling_csv_template() -> str:
    """Produce CSV headers and sample row for HR evaluation labeling."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "candidate_id",
        "candidate_name",
        "role_title",
        "hr_shortlist_decision",  # shortlist, hold, reject
        "hr_priority_band",       # High, Medium, Low
        "hr_marked_skills",       # Comma-separated
        "hr_red_flags",           # Notes on gaps or concerns
        "hr_notes"
    ])
    writer.writerow([
        "101", "Sample Candidate", "Junior Backend Dev",
        "shortlist", "High", "Python, Django, PostgreSQL, Docker",
        "None", "Strong GitHub project evidence"
    ])
    return output.getvalue()

