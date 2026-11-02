# Resume NER: Pre and Post Processing Implementation Guide

This document explains the full inference pipeline from raw resume text to structured output, covering all pre-processing, model inference, and post-processing steps driven by `resume_config.json`.

## Pipeline Overview

```
Raw PDF/Text
    |
    v
[1. Pre-processing]  ← resume_config.json → pre_processing
    |
    v
[2. Tokenization]    ← distilbert-base-cased tokenizer
    |
    v
[3. NER Inference]   ← DistilBERT token classification (27 labels)
    |
    v
[4. Span Assembly]   ← BIO → character-offset spans
    |
    v
[5. Section Detection]  ← Rule-based gap-filling for SKILLS, CERTS, LANGUAGES
    |
    v
[6. Post-processing]  ← resume_config.json → post_processing
    |
    v
Structured JSON output
```

---

## 1. Pre-processing (`text_preprocess.py`)

Config section: `resume_config.json → pre_processing`

Normalizes raw PDF extraction artifacts before the model sees the text. All rules are config-driven.

### Steps (in order):

1. **CRLF normalization** - Convert `\r\n` and `\r` to `\n`

2. **Dash normalization** (`normalize_dashes: true`)
   - Replace em-dash `—` and en-dash `–` with hyphen `-`
   - Configured via `dash_replacements` map

3. **Bullet normalization** (`normalize_bullets: true`)
   - Replace unicode bullets (`●`, `•`, `▪`, `■`, `▸`, `►`, `‣`, `⁃`) with `"- "`
   - Characters listed in `bullet_chars`, replacement in `bullet_replacement`

4. **Multi-space collapse** (`collapse_multi_spaces: true`)
   - Reduce runs of 2+ spaces to single space

5. **Label stripping** (`strip_labels: ["Phone:", "Email:"]`)
   - Remove literal prefixes like "Phone:" or "Email:" that add noise

6. **Skill table expansion** (`expand_skill_tables: true`)
   - Detects two-column "Category: skill1, skill2" tables common in resumes
   - Expands them into flat lists for better NER tagging
   - Recognizes categories from `skill_table_categories` list
   - Limits: `table_prose_max_words: 15`, `table_continuation_max_chars: 60`

### Usage:

```python
from training.text_preprocess import preprocess_resume_text

# Uses resume_config.json from current directory
clean_text = preprocess_resume_text(raw_text)

# Or with explicit config path:
from training.text_preprocess import ResumeTextPreprocessor
pp = ResumeTextPreprocessor("/path/to/model_dir")
clean_text = pp.preprocess(raw_text)
```

---

## 2. Tokenization & Chunking

Model max sequence length: **512 tokens** (DistilBERT).

For resumes exceeding 512 tokens, section-aware chunking is used (`benchmark_structured.py → chunked_predicted_spans`):

1. Split text at `\n\n` (paragraph) boundaries
2. Greedily group consecutive sections into chunks that fit within 512 tokens
3. Run inference on each chunk independently
4. Map character offsets back to original text

This preserves entity context within natural resume sections (Experience, Education, Skills).

---

## 3. NER Inference

Model: `distilbert-base-cased` fine-tuned for token classification.

**27 BIO labels:**

| Entity | B-tag | I-tag | Description |
|--------|-------|-------|-------------|
| NAME | 1 | 2 | Person's full name |
| EMAIL | 3 | 4 | Email address |
| PHONE | 5 | 6 | Phone number |
| LOCATION | 7 | 8 | City, state, country |
| COMPANY | 9 | 10 | Employer name |
| TITLE | 11 | 12 | Job title |
| DATE | 13 | 14 | Employment/education dates |
| DEGREE | 15 | 16 | Academic degree |
| INSTITUTION | 17 | 18 | School/university |
| FIELD | 19 | 20 | Field of study |
| SKILL | 21 | 22 | Technical/professional skill |
| CERT | 23 | 24 | Certification |
| LANGUAGE | 25 | 26 | Spoken language |

Tag `0` = O (outside any entity).

### Subword alignment:

The tokenizer splits words into subword tokens. During training:
- First subword of a word: gets the word's BIO label
- Continuation subwords: B-X converts to I-X, other labels propagate
- Special tokens ([CLS], [SEP], [PAD]): label = -100 (ignored in loss)

---

## 4. Span Assembly

Convert BIO predictions back to character-offset spans:

```python
@dataclass
class Span:
    label: str      # Entity type (NAME, COMPANY, etc.)
    text: str       # Extracted text
    start: int      # Character offset start
    end: int        # Character offset end
    score: float    # Confidence (1.0 for argmax)
```

Rules:
- B-X starts a new span
- I-X continues the current span (including whitespace gaps between subwords)
- O or different entity type closes the current span

---

## 5. Section Detection (`section_detector.py`)

Rule-based gap-filling that runs AFTER NER. Catches entities the model missed using section context:

- Detects section headers (SKILLS, CERTIFICATIONS, LANGUAGES, EDUCATION) by keyword matching
- Within detected sections, extracts untagged text as entities
- Especially useful for skills lists that the model partially tags

---

## 6. Post-processing (`structured_postprocess.py`)

Config section: `resume_config.json → post_processing`

Transforms raw spans into clean structured JSON.

### 6.1 Span Merging

```json
"span_merge_max_gap": 3,
"span_merge_labels": ["TITLE", "COMPANY"]
```

Adjacent spans of same type (TITLE or COMPANY) separated by <= 3 characters are merged. Handles cases where the model splits "Senior Software Engineer" into multiple spans.

### 6.2 Entity Validation Rules

Each entity type has validation rules in `entity_rules`:

**COMPANY:**
- `min_length: 4` — reject spans shorter than 4 chars
- `gazetteer_bypass: true` — known companies from `companies.json` skip length check
- `strip_trailing_state_code: true` — remove trailing US state codes ("Acme Inc. CA" → "Acme Inc.")

**TITLE:**
- `min_length: 2`
- `exceptions: ["VP", "PA", "RN", "MD", "DO", "QA"]` — short titles that are valid

**SKILL:**
- `min_length: 4`
- `uppercase_bypass: true` — short all-caps skills (AWS, GCP) pass
- `exceptions: ["Go", "R", "C", "C#", "F#", "D"]` — valid short skills
- `blocked_words` — language proficiency descriptors ("native", "fluent", "bilingual") filtered out
- `aliases` — normalize variants ("nodejs" → "node.js", "cpp" → "c++")

**EMAIL:**
- `require: "@"` — must contain @
- `reject_patterns: ["//", "www."]` — filter URLs misclassified as emails
- `strip_prefixes: ["Esq.", "Dr.", ...]` — remove honorifics attached by OCR

**DATE:**
- `min_length: 3`
- `date_words` list validates month names
- `present_words: ["present", "current"]` — recognized as end-date markers

### 6.3 Text Cleanup

```json
"space_collapse_pairs": [
  [" . ", "."],
  [" + + ", "++"],
  [" # ", "#"],
  [" ,", ","]
]
```

Fixes tokenizer-induced spacing artifacts in extracted text (e.g., "C + +" → "C++").

### 6.4 Seniority Inference

Determines career level from title keywords and experience duration:

```json
"seniority_keywords": {
  "Executive": ["cto", "ceo", ...],
  "Senior": ["senior", "sr.", "lead", "director", ...],
  "Junior": ["junior", "intern", "trainee", ...]
}
```

Fallback by years of experience:
```json
"seniority_by_years": { "Staff": 15, "Senior": 8, "Mid": 3, "Junior": 0 }
```

### 6.5 Country Detection

1. Phone prefix matching (`phone_country_prefixes`)
2. Location span matching against `city_country_map.json` (317 cities)
3. US state code detection (`us_states` list)
4. Country name aliases ("usa" → "United States")

### 6.6 Experience Years Calculation

- Parse start/end dates from DATE spans
- `max_experience_months: 600` — cap at 50 years
- `present_words` treated as current date

---

## Structured Output Format

```json
{
  "personal": {
    "name": "string",
    "email": "string",
    "phone": "string",
    "location": "string"
  },
  "experience": [
    {
      "title": "string",
      "company": "string",
      "start_date": "string",
      "end_date": "string"
    }
  ],
  "education": [
    {
      "degree": "string",
      "field": "string",
      "institution": "string"
    }
  ],
  "skills": ["string"],
  "certifications": ["string"],
  "seniority": "Executive|Principal|Staff|Senior|Mid|Junior",
  "country": "string",
  "experience_years": number
}
```

---

## Training Configuration

| Parameter | Value |
|-----------|-------|
| Base model | `distilbert-base-cased` |
| Max sequence length | 512 |
| Epochs | 25 |
| Batch size | 8 |
| Learning rate | 3e-5 |
| Weight decay | 0.01 |
| Warmup steps | 20 |
| Metric for best model | entity_f1 |
| Noise augmentation | 2x multiplier |

### Training Data Sources

| File | Records | Description |
|------|---------|-------------|
| `ner_train.json` | ~3,647 | Synthetic + manual + DataTurks (with noise augmentation) |
| `kaggle_train.json` | ~7,449 | Kaggle resumes: 2,483 clean + 4,966 noise-augmented |

### Evaluation

| File | Records | Description |
|------|---------|-------------|
| `ner_val.json` | 652 | Validation split |
| `gold/resume_resource_gold.json` | 93 | Hand-annotated gold standard |

---

## Quick Start: Running Inference

```python
import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer
from training.benchmark_structured import chunked_predicted_spans
from training.structured_postprocess import StructuredPostProcessor

# Load model
tokenizer = AutoTokenizer.from_pretrained("path/to/model")
model = AutoModelForTokenClassification.from_pretrained("path/to/model")
model.eval()
postprocessor = StructuredPostProcessor("path/to/model")

# Run pipeline
from training.text_preprocess import ResumeTextPreprocessor
pp = ResumeTextPreprocessor("path/to/model")
clean_text = pp.preprocess(raw_resume_text)

_, spans = chunked_predicted_spans(clean_text, model, tokenizer)
result = postprocessor.build_structured_resume_from_spans(spans, clean_text)
```

---

## File Reference

| File | Role |
|------|------|
| `resume_config.json` | All pre/post processing rules |
| `label_config.json` | Label ↔ ID mappings |
| `city_country_map.json` | City → country lookup |
| `training/data/companies.json` | Company name gazetteer |
| `training/data/titles.json` | Job title gazetteer |
