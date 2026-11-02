"""Detect resume sections and extract entities from untagged regions.

Rule-based section header detection + heuristic entity extraction for
sections where NER model has gaps (especially SKILLS, CERTIFICATIONS,
LANGUAGES, and EDUCATION).

Runs AFTER NER inference and BEFORE structured post-processing.
Fills in entities the model missed by using section context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from training.structured_postprocess import Span

SECTION_PATTERNS: dict[str, list[str]] = {
    "skills": [
        "skills", "technical skills", "core competencies", "competencies",
        "areas of expertise", "areas of excellence", "proficiencies",
        "technical proficiencies", "key skills", "professional skills",
        "summary of qualifications", "qualifications", "tools & technologies",
        "tools and technologies", "technologies", "tech stack",
        "devops tools & technologies", "devops tools",
    ],
    "experience": [
        "experience", "work experience", "professional experience",
        "employment history", "work history", "career history",
        "professional background", "clinical experience", "teaching experience",
    ],
    "education": [
        "education", "academic background", "academic qualifications",
        "educational background", "academic history",
    ],
    "certifications": [
        "certifications", "licenses & certifications", "licenses",
        "professional certifications", "credentials",
        "certifications & licenses", "awards & certifications",
    ],
    "languages": [
        "languages", "language skills", "linguistic skills",
    ],
    "projects": [
        "projects", "personal projects", "key projects", "selected projects",
    ],
}


@dataclass
class Section:
    name: str
    start: int
    end: int
    text: str


def detect_sections(text: str) -> list[Section]:
    """Find section boundaries using header keywords."""
    lines = text.split("\n")
    sections: list[Section] = []
    char_pos = 0
    line_positions = []
    for line in lines:
        line_positions.append(char_pos)
        char_pos += len(line) + 1

    header_lines: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        stripped = line.strip().rstrip(":").lower()
        stripped = re.sub(r"[^a-z\s&]", "", stripped).strip()
        if not stripped or len(stripped) > 60:
            continue
        for section_name, patterns in SECTION_PATTERNS.items():
            if stripped in patterns:
                header_lines.append((i, section_name))
                break

    for idx, (line_idx, section_name) in enumerate(header_lines):
        start = line_positions[line_idx]
        if idx + 1 < len(header_lines):
            end = line_positions[header_lines[idx + 1][0]]
        else:
            end = len(text)
        section_text = text[start:end]
        sections.append(Section(name=section_name, start=start, end=end, text=section_text))

    return sections


def _extract_list_items(text: str) -> list[str]:
    """Extract items from bullet lists, comma/dash/pipe-separated text, or Category: items format."""
    items = []
    for line in text.split("\n"):
        line = line.strip()
        line = re.sub(r"^[-●•▪■▸►‣⁃]\s*", "", line)
        if not line or len(line) > 120:
            continue
        # Strip "Category:" prefix if present
        colon_match = re.match(r"^[A-Za-z\s&/()-]+:\s*(.+)$", line)
        if colon_match:
            line = colon_match.group(1)
        # Split by comma, pipe, dash (but not inside words like "C++")
        parts = re.split(r"\s*[,|]\s*|\s+-\s+|\s+\+\s+", line)
        for part in parts:
            part = part.strip().rstrip(".,;:")
            if 2 < len(part) < 50 and not part[0].islower():
                items.append(part)
            elif 2 < len(part) < 50:
                items.append(part)
        # Also handle single bullet items
        if len(parts) == 1 and len(line) < 50 and not line.endswith("."):
            clean = line.strip().rstrip(".,;:")
            if 2 < len(clean) < 50 and clean not in items:
                items.append(clean)
    return items


def _is_tagged(start: int, end: int, existing_spans: list[Span]) -> bool:
    """Check if a character range overlaps any existing span."""
    for span in existing_spans:
        if span.start < end and span.end > start:
            return True
    return False


def fill_missing_entities(
    text: str,
    spans: list[Span],
    sections: list[Section] | None = None,
) -> list[Span]:
    """Add entities from detected sections that NER model missed.

    Runs after NER inference. For each detected section, extracts
    candidate entities using heuristics and adds them if the model
    didn't tag that text region.
    """
    if sections is None:
        sections = detect_sections(text)

    added: list[Span] = []

    for section in sections:
        if section.name == "skills":
            items = _extract_list_items(section.text)
            first_line = section.text.split("\n")[0]
            for item in items:
                if item.lower() in first_line.lower():
                    continue
                idx = text.find(item, section.start)
                if idx == -1:
                    continue
                if not _is_tagged(idx, idx + len(item), spans):
                    added.append(Span(
                        label="SKILL", text=item,
                        start=idx, end=idx + len(item),
                        bio="B", score=0.8,
                    ))

        elif section.name == "certifications":
            for line in section.text.split("\n"):
                line = line.strip()
                line = re.sub(r"^[-●•▪■]\s*", "", line)
                if not line or len(line) < 5 or len(line) > 100:
                    continue
                stripped_lower = re.sub(r"[^a-z\s&]", "", line.lower()).strip()
                is_header = any(stripped_lower == p for p in SECTION_PATTERNS["certifications"])
                if is_header:
                    continue
                idx = text.find(line, section.start)
                if idx == -1:
                    continue
                if not _is_tagged(idx, idx + len(line), spans):
                    added.append(Span(
                        label="CERT", text=line,
                        start=idx, end=idx + len(line),
                        bio="B", score=0.8,
                    ))

        elif section.name == "languages":
            for line in section.text.split("\n"):
                line = line.strip()
                line = re.sub(r"^[-●•▪■]\s*", "", line)
                if not line or len(line) < 3 or len(line) > 60:
                    continue
                stripped_lower = re.sub(r"[^a-z\s]", "", line.lower()).strip()
                if stripped_lower in ("languages", "language skills", "linguistic skills"):
                    continue
                lang_match = re.match(r"^([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", line)
                if lang_match:
                    lang = lang_match.group(1)
                    idx = text.find(lang, section.start)
                    if idx != -1 and not _is_tagged(idx, idx + len(lang), spans):
                        added.append(Span(
                            label="LANGUAGE", text=lang,
                            start=idx, end=idx + len(lang),
                            bio="B", score=0.8,
                        ))

    all_spans = spans + added
    all_spans.sort(key=lambda s: s.start)
    return all_spans
