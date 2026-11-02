from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Span:
    label: str
    text: str
    start: int
    end: int
    bio: str = "B"
    score: float = 1.0


class StructuredPostProcessor:
    def __init__(self, model_dir: str | Path):
        self.model_dir = Path(model_dir)
        with open(self.model_dir / "resume_config.json", encoding="utf-8") as fh:
            self.config = json.load(fh)
        companies_path = self.model_dir / "companies.json"
        self.companies = set()
        if companies_path.exists():
            with open(companies_path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.companies = {company.lower() for companies in data.values() for company in companies}
        self.multi_word_skills = {skill.lower() for skill in self.config.get("multi_word_skills", [])}

        pp = self.config.get("post_processing", {})
        self.span_merge_max_gap = pp.get("span_merge_max_gap", 3)
        self.span_merge_labels = set(pp.get("span_merge_labels", ["TITLE", "COMPANY"]))
        self.entity_rules = pp.get("entity_rules", {})
        self.skill_aliases = self.entity_rules.get("SKILL", {}).get("aliases", {})
        self.cert_aliases = self.entity_rules.get("CERT", {}).get("aliases", {})
        self.date_words = set(pp.get("date_words", []))
        self.present_words = set(pp.get("present_words", ["present", "current"]))
        self.gazetteer_match_max_words = pp.get("company_gazetteer_match_max_words", 3)
        self.title_company_separators = pp.get("title_company_separators", [" at "])
        self.max_experience_months = pp.get("max_experience_months", 600)
        self.space_collapse_pairs = pp.get("space_collapse_pairs", [])
        self.country_name_aliases = self.config.get("country_name_aliases", {})
        self.seniority_by_exp_count = self.config.get("seniority_by_experience_count", {"Senior": 4, "Mid": 2, "Junior": 0})

        self.city_country_map = {}
        ccm_file = self.config.get("city_country_map_file")
        if ccm_file:
            ccm_path = self.model_dir / ccm_file
            if ccm_path.exists():
                with open(ccm_path) as fh:
                    data = json.load(fh)
                for region in data.values():
                    self.city_country_map.update(region)
        if not self.city_country_map:
            self.city_country_map = self.config.get("city_country_map", {})

    def build_structured_resume_from_spans(self, spans: list[Span], raw_text: str = "") -> dict:
        spans = [Span(**{**span.__dict__, "text": self.clean_entity(span.label, span.text) or ""}) for span in spans]
        spans = [span for span in spans if span.text]
        spans = self.apply_post_processing(spans)
        grouped = self.group_into_entries(spans)
        years = self.compute_years(grouped["experience"])
        seniority = self.infer_seniority(grouped["experience"], years)
        country = self.infer_country(grouped["personal"].get("location"), grouped["personal"].get("phone"))
        return {
            "personal": {
                **grouped["personal"],
                "name": self.clean_spaces(grouped["personal"].get("name")) if grouped["personal"].get("name") else None,
            },
            "experience": grouped["experience"],
            "education": grouped["education"],
            "skills": [self.clean_spaces(skill) for skill in grouped["skills"]],
            "certifications": grouped["certifications"],
            "seniority": seniority,
            "country": country,
            "experience_years": years,
            "_rawText": raw_text,
        }

    @staticmethod
    def _merge_same_label_neighbors(spans: list[Span], labels: set[str], max_gap: int = 3) -> list[Span]:
        merged: list[Span] = []
        for span in spans:
            if merged and span.label in labels and merged[-1].label == span.label and span.start - merged[-1].end <= max_gap:
                merged[-1] = Span(
                    label=merged[-1].label,
                    text=f"{merged[-1].text} {span.text}",
                    start=merged[-1].start,
                    end=span.end,
                    bio=merged[-1].bio,
                    score=max(merged[-1].score, span.score),
                )
            else:
                merged.append(span)
        return merged

    def clean_entity(self, label: str, raw: str) -> str | None:
        cleaned = re.sub(r"\s+", " ", raw).strip()
        cleaned = re.sub(r"^[,.;:|/\-\s]+|[,.;:|/\-\s]+$", "", cleaned)
        if not cleaned or (len(cleaned) == 1 and not re.search(r"[a-zA-Z]", cleaned)):
            return None
        if re.fullmatch(r"[\W_]+", cleaned):
            return None

        rules = self.entity_rules.get(label, {})

        if label == "EMAIL":
            cleaned = re.sub(r"\s+", "", cleaned)
            for prefix in rules.get("strip_prefixes", []):
                cleaned = re.sub(rf"^{re.escape(prefix)}\s*", "", cleaned, flags=re.I)
            cleaned = re.sub(r"^[^a-zA-Z0-9]+", "", cleaned)
            if rules.get("require") and rules["require"] not in cleaned:
                return None
            for pattern in rules.get("reject_patterns", []):
                if pattern.lower() in cleaned.lower():
                    return None
        elif label == "SKILL":
            cleaned = re.sub(r"[,.;:]+$", "", cleaned)
        elif label == "COMPANY":
            if rules.get("strip_trailing_state_code"):
                cleaned = re.sub(r",?\s+[A-Z]{2}$", "", cleaned).strip()
        elif label == "DATE":
            cleaned = re.sub(r"^[| ]+|[| ]+$", "", cleaned)

        if not cleaned:
            return None

        min_len = rules.get("min_length", 2)
        exceptions = {e.lower() for e in rules.get("exceptions", [])}
        blocked = {w.lower() for w in rules.get("blocked_words", [])}

        if cleaned.lower() in blocked:
            return None

        if cleaned.lower() in exceptions:
            return cleaned

        if len(cleaned) < min_len:
            if rules.get("gazetteer_bypass") and cleaned.lower() in self.companies:
                return cleaned
            if rules.get("uppercase_bypass") and cleaned.isupper():
                return cleaned
            return None

        return cleaned

    def apply_post_processing(self, spans: list[Span]) -> list[Span]:
        spans = self._merge_same_label_neighbors(spans, self.span_merge_labels, self.span_merge_max_gap)
        result = [Span(**{**span.__dict__, "label": "COMPANY"}) if span.label == "TITLE" and span.text.lower().strip() in self.companies else span for span in spans]

        stripped = []
        for span in result:
            if span.label != "COMPANY":
                stripped.append(span)
                continue
            words = span.text.split()
            while len(words) > 1 and (words[-1].lower() in self.date_words or re.fullmatch(r"\d{4}", words[-1])):
                words.pop()
            stripped.append(Span(**{**span.__dict__, "text": " ".join(words)}))

        result = []
        for span in stripped:
            if span.label != "TITLE":
                result.append(span)
                continue
            words = span.text.split()
            split_done = False
            for length in range(min(self.gazetteer_match_max_words, len(words)), 0, -1):
                prefix = " ".join(words[:length])
                if prefix.lower() in self.companies:
                    result.append(Span(**{**span.__dict__, "label": "COMPANY", "text": prefix}))
                    suffix = " ".join(words[length:])
                    if len(suffix) > 1:
                        result.append(Span(**{**span.__dict__, "label": "TITLE", "text": suffix}))
                    split_done = True
                    break
            if not split_done:
                result.append(span)

        merged = []
        i = 0
        while i < len(result):
            current = result[i]
            if current.label == "SKILL" and i + 1 < len(result) and result[i + 1].label == "SKILL":
                combined = f"{current.text} {result[i + 1].text}".rstrip(",.")
                if combined.lower() in self.multi_word_skills:
                    merged.append(Span(**{**current.__dict__, "text": combined, "end": result[i + 1].end}))
                    i += 2
                    continue
            merged.append(current)
            i += 1
        return merged

    def normalize_skill(self, text: str) -> str:
        normalized = self.clean_spaces(text.strip().rstrip(",."))
        alias = self.skill_aliases.get(normalized.lower())
        return alias if alias else normalized

    def normalize_certification(self, text: str) -> str:
        normalized = self.clean_spaces(text.strip().rstrip(",."))
        normalized = re.sub(r"^the\s+", "", normalized, flags=re.I)
        alias = self.cert_aliases.get(normalized.lower())
        return alias if alias else normalized

    @staticmethod
    def _dedupe_dict_items(items: list[dict]) -> list[dict]:
        seen = set()
        deduped = []
        for item in items:
            key = tuple(sorted((k, v) for k, v in item.items() if v))
            if key and key not in seen:
                seen.add(key)
                deduped.append(item)
        return deduped

    def clean_experiences(self, experiences: list[dict]) -> list[dict]:
        cleaned = []
        for exp in experiences:
            exp = {k: self.clean_spaces(v) if isinstance(v, str) else v for k, v in exp.items() if v}
            if "title" in exp and "company" not in exp:
                for sep in self.title_company_separators:
                    if sep.lower() in exp["title"].lower():
                        title, company = re.split(re.escape(sep.strip()), exp["title"], maxsplit=1, flags=re.I)
                        exp["title"] = self.clean_spaces(title)
                        exp["company"] = self.clean_spaces(company)
                        break
            cleaned.append(exp)
        if any(exp.get("company") or exp.get("start_date") for exp in cleaned[1:]):
            while cleaned and cleaned[0].get("title") and not cleaned[0].get("company") and not cleaned[0].get("start_date"):
                cleaned.pop(0)
        return self._dedupe_dict_items(cleaned)

    def clean_education(self, education: list[dict]) -> list[dict]:
        cleaned = []
        for edu in education:
            item = {k: self.clean_spaces(v) if isinstance(v, str) else v for k, v in edu.items() if v}
            if item:
                cleaned.append(item)
        return self._dedupe_dict_items(cleaned)

    def group_into_entries(self, spans: list[Span]) -> dict:
        personal = {"name": None, "email": None, "phone": None, "location": None}
        for span in spans:
            if span.label == "NAME" and not personal["name"]:
                personal["name"] = span.text
            elif span.label == "EMAIL" and not personal["email"]:
                cleaned = self.clean_entity("EMAIL", span.text)
                if cleaned:
                    personal["email"] = cleaned
            elif span.label == "PHONE" and not personal["phone"]:
                personal["phone"] = self.clean_phone(span.text)
            elif span.label == "LOCATION" and not personal["location"]:
                personal["location"] = self.clean_spaces(span.text)

        exp_spans = sorted([span for span in spans if span.label in {"TITLE", "COMPANY", "DATE"}], key=lambda span: span.start)
        experiences = []
        current = {}
        for span in exp_spans:
            if span.label == "TITLE":
                if current.get("title") and (current.get("company") or current.get("start_date")):
                    experiences.append(current)
                    current = {}
                current["title"] = self.clean_spaces(span.text)
            elif span.label == "COMPANY":
                if current.get("company") and (current.get("title") or current.get("start_date")):
                    experiences.append(current)
                    current = {}
                current["company"] = self.clean_spaces(self.clean_entity("COMPANY", span.text) or "")
            elif span.label == "DATE":
                date_text = re.sub(r"^[| ]+|[| ]+$", "", span.text)
                if not date_text:
                    continue
                present_pattern = "|".join(re.escape(w) for w in self.present_words)
                present_match = re.match(rf"^(.+?)\s+({present_pattern})$", date_text, flags=re.I)
                if present_match and not current.get("start_date"):
                    current["start_date"] = present_match.group(1).strip()
                    current["end_date"] = present_match.group(2)
                    continue
                if current.get("start_date") and not current.get("end_date") and re.fullmatch(r"[a-zA-Z]+", current["start_date"]) and re.match(r"^\d{4}", date_text):
                    year_match = re.match(r"^(\d{4})\s*(.*)", date_text)
                    if year_match:
                        current["start_date"] = f"{current['start_date']} {year_match.group(1)}"
                        if year_match.group(2):
                            current["end_date"] = year_match.group(2).strip()
                        continue
                if current.get("start_date") and current.get("end_date"):
                    if current.get("title") or current.get("company"):
                        experiences.append(current)
                        current = {}
                if not current.get("start_date"):
                    current["start_date"] = date_text
                elif not current.get("end_date"):
                    current["end_date"] = date_text
        if current.get("title") or current.get("company"):
            experiences.append(current)
        experiences = self.clean_experiences(experiences)

        edu_spans = sorted([span for span in spans if span.label in {"DEGREE", "FIELD", "INSTITUTION"}], key=lambda span: span.start)
        education = []
        current_edu = {}
        for span in edu_spans:
            if span.label == "DEGREE":
                if current_edu.get("degree"):
                    education.append(current_edu)
                    current_edu = {}
                current_edu["degree"] = self.clean_spaces(span.text)
            elif span.label == "FIELD":
                current_edu["field"] = self.clean_spaces(span.text)
            elif span.label == "INSTITUTION":
                current_edu["institution"] = re.sub(r",?\s*\d{4}\s*$", "", self.clean_spaces(span.text))
                education.append(current_edu)
                current_edu = {}
        if current_edu.get("degree") or current_edu.get("institution"):
            education.append(current_edu)
        education = self.clean_education(education)

        skill_rules = self.entity_rules.get("SKILL", {})
        skill_min = skill_rules.get("min_length", 2)
        skills = []
        seen = set()
        for span in spans:
            if span.label != "SKILL":
                continue
            for part in re.split(r",\s*", span.text):
                clean = self.normalize_skill(part)
                if not clean or clean.lower() in seen:
                    continue
                if len(clean) < skill_min and not clean.isupper() and clean.lower() not in {e.lower() for e in skill_rules.get("exceptions", [])}:
                    continue
                seen.add(clean.lower())
                skills.append(clean)

        certifications = []
        cert_seen = set()
        for span in spans:
            if span.label != "CERT":
                continue
            clean = self.normalize_certification(span.text)
            if len(clean) > 1 and clean.lower() not in cert_seen:
                cert_seen.add(clean.lower())
                certifications.append(clean)
        return {"personal": personal, "experience": experiences, "education": education, "skills": skills, "certifications": certifications}

    def infer_seniority(self, experiences: list[dict], years: int | None) -> str:
        keywords = self.config["seniority_keywords"]
        titles = [(exp.get("title") or "").lower() for exp in experiences if exp.get("title")]
        for level, level_keywords in keywords.items():
            for title in titles:
                for keyword in level_keywords:
                    if keyword in title:
                        return level
        if years is not None:
            bounds = self.config["seniority_by_years"]
            if years >= bounds["Staff"]:
                return "Staff"
            if years >= bounds["Senior"]:
                return "Senior"
            if years >= bounds["Mid"]:
                return "Mid"
            return "Junior"
        for level, min_count in sorted(self.seniority_by_exp_count.items(), key=lambda x: -x[1]):
            if len(experiences) >= min_count:
                return level
        return "Junior"

    def infer_country(self, location: str | None, phone: str | None) -> str | None:
        if phone:
            clean = re.sub(r"[\s\-()]", "", phone)
            for prefix, country in self.config["phone_country_prefixes"].items():
                if clean.startswith(prefix):
                    return country
        if location:
            loc = location.lower()
            for alias, country in self.country_name_aliases.items():
                if alias in loc:
                    return country
            for city, country in self.city_country_map.items():
                if city in loc:
                    return country
            for part in loc.replace(",", " ").split():
                if part.upper() in self.config["us_states"]:
                    return "United States"
        return None

    def compute_years(self, experiences: list[dict]) -> int | None:
        total_months = 0
        now = datetime.now()
        present_re = "|".join(re.escape(w) for w in self.present_words)
        for exp in experiences:
            if not exp.get("start_date"):
                continue
            start = self.parse_date(exp["start_date"])
            if not start:
                continue
            if not exp.get("end_date") or re.search(present_re, exp["end_date"], flags=re.I):
                end = now
            else:
                end = self.parse_date(exp["end_date"])
                if not end:
                    continue
            months = (end.year - start.year) * 12 + (end.month - start.month)
            if 0 < months < self.max_experience_months:
                total_months += months
        return total_months // 12 if total_months > 0 else None

    @staticmethod
    def parse_date(text: str) -> datetime | None:
        months = {
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12, "jan": 1, "feb": 2, "mar": 3,
            "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        lower = text.lower().strip()
        for name, month in months.items():
            match = re.search(rf"{name}\s+(\d{{4}})", lower)
            if match:
                return datetime(int(match.group(1)), month, 1)
        year_match = re.search(r"\b(19|20)\d{2}\b", text)
        if year_match:
            return datetime(int(year_match.group(0)), 6, 1)
        return None

    def clean_spaces(self, text: str) -> str:
        result = text
        for old, new in self.space_collapse_pairs:
            result = result.replace(old, new)
        return result.rstrip(",").strip()

    @staticmethod
    def clean_phone(phone: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"\+\s+", "+", re.sub(r"\s+-\s+", "-", re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", phone))))).strip()


def build_text_and_spans(tokens: list[str], ner_tags: list[int], id2label: dict[int, str]) -> tuple[str, list[Span]]:
    text = ""
    positions = []
    for token in tokens:
        start = len(text)
        text += (" " if text else "") + token
        real_start = start + (1 if start else 0)
        positions.append((real_start, real_start + len(token)))
    spans = []
    current = None
    for i, token in enumerate(tokens):
        label = id2label[ner_tags[i]]
        if label == "O":
            if current:
                spans.append(current)
                current = None
            continue
        bio, base = label.split("-", 1)
        start, end = positions[i]
        if current is None or bio == "B" or current.label != base:
            if current:
                spans.append(current)
            current = Span(label=base, text=token, start=start, end=end, bio=bio, score=1.0)
        else:
            current.text += f" {token}"
            current.end = end
    if current:
        spans.append(current)
    return text, spans
