"""Text preprocessing for resume text before NER inference.

Normalizes PDF extraction artifacts: CRLF, em-dashes, bullet characters,
flattened two-column tables, and multi-space runs. All rules driven by
resume_config.json pre_processing section.

Usage:
    from training.text_preprocess import preprocess_resume_text
    clean = preprocess_resume_text(raw_text)

    # Or with explicit config:
    from training.text_preprocess import ResumeTextPreprocessor
    pp = ResumeTextPreprocessor(".")
    clean = pp.preprocess(raw_text)
"""

from __future__ import annotations

import json
import re
from pathlib import Path


class ResumeTextPreprocessor:
    def __init__(self, config_dir: str | Path):
        config_path = Path(config_dir) / "resume_config.json"
        with open(config_path) as f:
            full_config = json.load(f)
        self.config = full_config.get("pre_processing", {})
        self._build_category_pattern()

    def _build_category_pattern(self):
        categories = self.config.get("skill_table_categories", [])
        if categories:
            sorted_cats = sorted(categories, key=len, reverse=True)
            pattern_str = r"^(" + "|".join(re.escape(c) for c in sorted_cats) + r")\s+([A-Za-z0-9#.+].+)$"
            self._category_re = re.compile(pattern_str, re.IGNORECASE)
        else:
            self._category_re = None

    def preprocess(self, text: str) -> str:
        text = self._normalize_whitespace(text)
        if self.config.get("normalize_dashes", True):
            text = self._normalize_dashes(text)
        if self.config.get("normalize_bullets", True):
            text = self._normalize_bullets(text)
        text = self._strip_labels(text)
        if self.config.get("expand_skill_tables", True):
            text = self._expand_flattened_table(text)
        if self.config.get("collapse_multi_spaces", True):
            text = self._collapse_multi_spaces(text)
        return text.strip()

    def _normalize_whitespace(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return "\n".join(line.rstrip() for line in text.split("\n"))

    def _normalize_dashes(self, text: str) -> str:
        for old, new in self.config.get("dash_replacements", {"–": "-", "—": "-"}).items():
            text = text.replace(old, new)
        return text

    def _normalize_bullets(self, text: str) -> str:
        chars = self.config.get("bullet_chars", ["●", "•", "▪", "■", "▸", "►", "‣", "⁃"])
        replacement = self.config.get("bullet_replacement", "- ")
        if chars:
            pattern = r"^[" + re.escape("".join(chars)) + r"]\s*"
            text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
        return text

    def _strip_labels(self, text: str) -> str:
        for label in self.config.get("strip_labels", []):
            text = re.sub(r"(?i)\b" + re.escape(label) + r"\s*", "", text)
        return text

    def _expand_flattened_table(self, text: str) -> str:
        if not self._category_re:
            return text
        max_prose_words = self.config.get("table_prose_max_words", 15)
        max_cont_chars = self.config.get("table_continuation_max_chars", 60)

        lines = text.split("\n")
        result = []
        i = 0
        while i < len(lines):
            line = lines[i]
            match = self._category_re.match(line.strip())
            if not match:
                ms = re.match(r"^([A-Za-z][A-Za-z\s&/()-]{2,40}?)\s{2,}([A-Za-z0-9#.+].+)$", line)
                if ms and "," in ms.group(2):
                    match = ms
            if match:
                category = match.group(1).strip()
                items = match.group(2).strip()
                if len(items.split()) > max_prose_words or ("," not in items and len(items.split()) > 5):
                    result.append(line)
                    i += 1
                    continue
                while i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    is_continuation = (
                        re.match(r"^\s{2,}[A-Za-z0-9#.+]", lines[i + 1])
                        or (
                            next_line
                            and next_line[0].isupper()
                            and "," in next_line
                            and not self._category_re.match(next_line)
                            and len(next_line) < max_cont_chars
                        )
                    )
                    if is_continuation:
                        i += 1
                        items += " " + next_line
                    else:
                        break
                items = re.sub(r"\s*,\s*", ", ", items).rstrip(",").strip()
                result.append(f"{category}: {items}")
            else:
                result.append(line)
            i += 1
        return "\n".join(result)

    @staticmethod
    def _collapse_multi_spaces(text: str) -> str:
        return re.sub(r"  +", " ", text)


_default_preprocessor: ResumeTextPreprocessor | None = None


def preprocess_resume_text(text: str, config_dir: str | Path = ".") -> str:
    """Convenience function using default config from current directory."""
    global _default_preprocessor
    if _default_preprocessor is None:
        _default_preprocessor = ResumeTextPreprocessor(config_dir)
    return _default_preprocessor.preprocess(text)
