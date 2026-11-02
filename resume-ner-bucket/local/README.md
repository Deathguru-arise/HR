---
language: en
license: apache-2.0
tags:
  - resume-parsing
  - ner
  - token-classification
  - onnx
  - distilbert
  - resume
  - cv
  - information-extraction
datasets:
  - datasetmaster/resumes
metrics:
  - f1
  - precision
  - recall
pipeline_tag: token-classification
library_name: transformers
---

# Resume NER — Structured Resume Information Extraction

Fine-tuned DistilBERT model for extracting structured information from resume text. Raw model output is token-level BIO tags. Included post-processing turns those spans into structured resume fields.

## Status

- Base model: `distilbert-base-cased`
- Task: token classification / NER
- Labels: `NAME`, `EMAIL`, `PHONE`, `LOCATION`, `COMPANY`, `TITLE`, `DATE`, `DEGREE`, `FIELD`, `INSTITUTION`, `SKILL`, `CERT`, `LANGUAGE`
- Max context: 512 tokens
- PyTorch artifact: `model.safetensors`
- ONNX artifacts: `onnx/model.onnx`, `onnx/model_quantized.onnx`

## Latest NER benchmark

Latest retrain on RTX 3080 with noise-augmented data + Kaggle silver labels (25 epochs):

- entity F1: **97.77%**
- structured micro F1: **97.88%**
- clean resume F1: **99.18%**
- noisy resume F1: **69.24%** (OCR/scraped text)

These numbers come from entity-level exact-match evaluation with `seqeval` and the structured extraction benchmark.

## Metric note

Older versions of this repo reported token-level F1. Training now uses **entity-level exact-match F1** via `seqeval`, which is stricter and more useful for NER quality.

## Quick start

### Transformers

```python
from transformers import pipeline

ner = pipeline("token-classification", model="oksomu/resume-ner", aggregation_strategy="simple")
results = ner(resume_text)
```

### ONNX Runtime via Optimum

```python
from optimum.onnxruntime import ORTModelForTokenClassification
from transformers import AutoTokenizer, pipeline

model = ORTModelForTokenClassification.from_pretrained("oksomu/resume-ner", file_name="onnx/model.onnx")
tokenizer = AutoTokenizer.from_pretrained("oksomu/resume-ner")
ner = pipeline("token-classification", model=model, tokenizer=tokenizer, aggregation_strategy="simple")
```

### Full structured extraction

```typescript
import { parseResume, computeATSScore } from "resume-extract";

const result = await parseResume(resumeText, "./model");
const ats = computeATSScore(result);
```

npm: [`resume-extract`](https://www.npmjs.com/package/resume-extract) | GitHub: [`somus/resume-extract`](https://github.com/somus/resume-extract)

## Usage
Model predicts these entity types:

- `NAME`
- `EMAIL`
- `PHONE`
- `LOCATION`
- `COMPANY`
- `TITLE`
- `DATE`
- `DEGREE`
- `FIELD`
- `INSTITUTION`
- `SKILL`
- `CERT`
- `LANGUAGE`

## Pre-processing

`resume_config.json` `pre_processing` section defines text normalization applied before NER inference:

- normalize CRLF, em-dashes, bullet characters
- strip `Phone:`/`Email:` labels from contact lines
- expand flattened two-column skill tables (`Category Skills` → `Category: Skills`)
- collapse multi-space runs

All rules are config-driven — any language implementation can apply the same preprocessing from the JSON config.

## Post-processing

`resume_config.json` `post_processing` section contains rule-based cleanup applied after NER:

- entity-specific min lengths, exceptions, and blocked words
- merge adjacent same-label spans (configurable labels + gap)
- group flat spans into experience / education entries
- infer seniority from titles + years
- infer country from location + phone prefix (317 cities in `city_country_map.json`)
- compute experience years from date ranges
- fix company names with gazetteer (`companies.json`)
- normalize skills and certifications via aliases
- merge multi-word skills

Section detection (`training/section_detector.py`) fills entities the NER model missed by using resume section context (SKILLS, CERTIFICATIONS, LANGUAGES sections).

All post-processing rules are config-driven for cross-language portability.

For a detailed implementation walkthrough of the full pipeline, see [`docs/implementation_guide.md`](docs/implementation_guide.md).

## Training data

Current checked-in dataset snapshot in `training/data/` was built from mixed sources:

- DataTurks annotated resumes
- generated examples from `datasetmaster/resumes`
- 12 manual resume templates across tech and non-tech domains
- 50 hand-crafted long resumes (>512 tokens) for chunked inference training
- 93 gold-labeled resume-resource PDFs (hand-annotated, 100% match rate)
- 2,483 Kaggle resumes with Gemini-extracted silver labels + BIO tagging
- 2x noise augmentation for OCR robustness (separator swaps, char corruption, case changes)

Data layout:

```
training/data/
├── ner_train.json          # Main training set
├── ner_val.json            # Validation split
├── kaggle_train.json       # Kaggle BIO training (silver + noise-augmented)
├── gold/                   # Hand-annotated evaluation data
├── sources/                # Raw source data (CSV, JSONL, etc.)
└── resume_resource/        # Source PDFs
```

Current public rebuild path uses:

- `training/generate_from_structured.py` — orchestrates all sources + augmentation
- `training/manual_resumes.py` — short manual templates
- `training/build_gold_labels.py` — gold-labeled PDF resumes
- `training/noise_augment.py` — noise augmentation for OCR robustness

## Training

Use Python 3.11+.

Install training stack:

```bash
uv sync
```

Create separate ONNX export env:

```bash
uv venv .venv-onnx-export
uv pip install --python .venv-onnx-export/bin/python -r training/requirements-export.txt
```

Train:

```bash
python -m training.train_ner
python -m training.train_ner --base-model deberta
```

Rebuild dataset from public/synthetic sources:

```bash
python -m training.generate_from_structured
```

Run tests:

```bash
python -m unittest discover -s tests
```

Run structured benchmark:

```bash
python -m training.benchmark_structured --model-dir .
```

Latest internal structured benchmark on current validation set:

- overall micro F1: **97.88%**
- macro field F1: **98.47%**
- clean-resume micro F1: **99.18%**
- noisy-resume micro F1: **69.24%**

This benchmark uses in-repo structured post-processing for both gold spans and model predictions. Section-aware chunked inference handles resumes exceeding the 512-token context window. These numbers are intended for internal regression tracking, not external leaderboard claims.

## Export workflow

Train in main env. Export in separate ONNX env:

```bash
python -m training.train_ner

source .venv-onnx-export/bin/activate
optimum-cli export onnx --model training/output/resume-ner/distilbert/best --task token-classification onnx/
```

Quantize ONNX model:

```bash
python - <<'PY'
from optimum.onnxruntime import ORTModelForTokenClassification, ORTQuantizer
from optimum.onnxruntime.configuration import AutoQuantizationConfig

model = ORTModelForTokenClassification.from_pretrained("onnx")
quantizer = ORTQuantizer.from_pretrained(model)
qconfig = AutoQuantizationConfig.arm64(is_static=False, per_channel=False)
quantizer.quantize(save_dir="onnx", quantization_config=qconfig)
PY
```

Full details: [`docs/export.md`](docs/export.md)

## Artifact layout

- root `config.json`, `model.safetensors`, tokenizer files — canonical PyTorch / Hugging Face checkpoint
- root `companies.json` — company gazetteer used by post-processing
- root `city_country_map.json` — 317 cities for country inference
- `label_config.json` — explicit label metadata used by training/inference tooling
- `onnx/model.onnx` — exported ONNX model
- `onnx/model_quantized.onnx` — quantized ONNX model for smaller CPU deployment
- `resume_config.json` — pre-processing, post-processing, and inference rules (single config for all languages)

## ONNX validation

Current ONNX export was validated against PyTorch on same sample input:

- PyTorch vs ONNX logits: `allclose=True` (max diff: 0.000013)
- PyTorch vs ONNX predictions: `argmax_equal=True`
- PyTorch vs quantized ONNX predictions: minor diff (expected for INT8)

This is main safety check when training and export happen in separate environments.

## Repo layout

- `training/train_ner.py` — training loop
- `training/generate_from_structured.py` — dataset builder orchestrating all sources + augmentation
- `training/build_gold_labels.py` — gold-labeled PDF resume builder
- `training/manual_resumes.py` — short manual templates
- `training/noise_augment.py` — noise augmentation for OCR robustness
- `training/labels.py` — shared label definitions
- `training/dataset_utils.py` — dedupe / split / manifest helpers
- `training/tagging.py` — span tagging helpers
- `training/text_preprocess.py` — config-driven text preprocessing
- `training/structured_postprocess.py` — config-driven post-processing and grouping
- `training/section_detector.py` — section-aware entity extraction
- `training/benchmark_structured.py` — structured benchmark with chunked inference
- `training/analyze_structured_errors.py` — per-resume error analysis
- `training/synthetic_assets.py` — synthetic source assets/helpers
- `training/synthetic_formats.py` — 8 resume format builders (A-H)
- `training/export_onnx.py` — CLI wrapper for ONNX export
- `training/validate_onnx.py` — PyTorch vs ONNX parity check
- `training/quantize_onnx.py` — ONNX quantization helper
- `training/requirements-export.txt` — separate ONNX export env
- `run_inference.py` — single-resume inference script
- `docs/implementation_guide.md` — detailed pre/post processing implementation guide
- `docs/export.md` — ONNX export and validation notes

## Limitations

- English resumes only
- max 512 tokens per chunk (section-aware chunking handles longer resumes)
- image-based/scanned PDFs require OCR before text extraction
- two-column PDF layouts may flatten during text extraction

## License

Apache 2.0
