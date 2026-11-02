# ONNX export

This repo uses **split environments**:

- main env: latest training stack (`transformers` 5.x)
- ONNX env: exporter-compatible stack from `training/requirements-export.txt`

Reason: current `optimum-onnx` release still requires `transformers <4.58`, while training uses latest `transformers 5.x`.

## Why split env is acceptable

For stable architectures like DistilBERT token classification, exporting from a separately loaded saved checkpoint is normal practice. Safety comes from validating exported ONNX outputs against PyTorch outputs.

## Training

```bash
uv sync
python -m training.train_ner
```

Best checkpoint is saved under:

```text
training/output/resume-ner/distilbert/best
```

## ONNX export environment

```bash
uv venv .venv-onnx-export
uv pip install --python .venv-onnx-export/bin/python -r training/requirements-export.txt
source .venv-onnx-export/bin/activate
```

## Export command

```bash
optimum-cli export onnx \
  --model training/output/resume-ner/distilbert/best \
  --task token-classification \
  onnx/
```

This writes:

- `onnx/model.onnx`
- tokenizer/config files in `onnx/`

## Quantization

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

This writes:

- `onnx/model_quantized.onnx`

## Validation

Checked-in helper scripts:

- `python -m training.export_onnx`
- `python -m training.validate_onnx`
- `python -m training.quantize_onnx`
- `python -m training.benchmark_structured --model-dir .` — internal structured benchmark


Always compare PyTorch vs ONNX on same tokenized input.

Recommended checks:

1. output shape match
2. `np.allclose(..., rtol=1e-3, atol=1e-5)` for non-quantized ONNX
3. `argmax_equal=True`
4. quantized ONNX at least preserves argmax predictions on smoke test inputs

Minimal validation example:

```python
import numpy as np
import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer
from optimum.onnxruntime import ORTModelForTokenClassification

model_dir = "training/output/resume-ner/distilbert/best"
text = "Rajesh Kumar worked at Infosys in Bangalore from April 2020 to Present using Python and AWS."

tokenizer = AutoTokenizer.from_pretrained(model_dir)
pt_model = AutoModelForTokenClassification.from_pretrained(model_dir)
pt_model.eval()
ort_model = ORTModelForTokenClassification.from_pretrained("onnx")

inputs_pt = {k: v for k, v in tokenizer(text, return_tensors="pt", truncation=True).items() if k in {"input_ids", "attention_mask"}}
inputs_np = {k: v for k, v in tokenizer(text, return_tensors="np", truncation=True).items() if k in {"input_ids", "attention_mask"}}

with torch.no_grad():
    pt_logits = pt_model(**inputs_pt).logits.cpu().numpy()
ort_logits = ort_model(**inputs_np).logits

print(np.allclose(pt_logits, ort_logits, rtol=1e-3, atol=1e-5))
print(np.array_equal(pt_logits.argmax(-1), ort_logits.argmax(-1)))
```

## Hugging Face artifact policy

Upload both:

### Root
- `model.safetensors`
- `config.json`
- tokenizer files
- `companies.json`
- `label_config.json`
- `resume_config.json`

### `onnx/`
- `model.onnx`
- `model_quantized.onnx`
- ONNX tokenizer/config files

This keeps repo usable for:
- Transformers users
- ONNX users
- future re-export or debugging
