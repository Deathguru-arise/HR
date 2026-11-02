from __future__ import annotations

import re


def classify_resume_noise(text: str) -> dict[str, object]:
    lower = text.lower()
    signals: list[str] = []

    if "indeed.com/r/" in lower or "authorized to work in" in lower or "willing to relocate" in lower:
        signals.append("job_board_scrape")
    if lower.count("work experience") > 1 or lower.count("experience") >= 3 and lower.count("experience") / max(len(lower.split()), 1) > 0.02:
        signals.append("repeated_sections")
    if re.search(r"\b[a-z]{2,}\s+[a-z]{2,}\s+[a-z]{2,}\b", lower) and any(token in lower for token in [" to present", " octoberober ", " novemberember ", " junee ", " februaryruary "]):
        signals.append("ocr_like_dates")
    if re.search(r'"[^"]+"\s+internship', lower) or re.search(r'"[^"]+"', lower):
        signals.append("quoted_fragments")
    if re.search(r"\bhttps?://|www\.", lower):
        signals.append("embedded_urls")
    if len(re.findall(r"\|", text)) >= 4:
        signals.append("dense_delimiters")
    if re.search(r"\b[a-z]+/[a-z]+/[a-z]+\b", lower) or re.search(r"\b[a-z]+&[a-z]+\b", lower):
        signals.append("compound_tokens")
    if re.search(r"\bco\s+septembertember\b|\btx\s+may\b|\bto\s+present\b", lower):
        signals.append("span_noise")

    noisy = len(signals) >= 2 or "job_board_scrape" in signals or "ocr_like_dates" in signals
    bucket = "noisy" if noisy else "clean"
    return {"bucket": bucket, "signals": signals}
