from __future__ import annotations

import argparse
import json

import numpy as np
import torch
from optimum.onnxruntime import ORTModelForTokenClassification
from transformers import AutoModelForTokenClassification, AutoTokenizer

ALLOWED_INPUTS = {"input_ids", "attention_mask"}
DEFAULT_TEXT = "Rajesh Kumar worked at Infosys in Bangalore from April 2020 to Present using Python and AWS."


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate ONNX logits against PyTorch logits")
    parser.add_argument("--model-dir", default="training/output/resume-ner/distilbert/best")
    parser.add_argument("--onnx-dir", default="onnx")
    parser.add_argument("--file-name", default=None)
    parser.add_argument("--text", default=DEFAULT_TEXT)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model_dir)
    pt_model = AutoModelForTokenClassification.from_pretrained(args.model_dir)
    pt_model.eval()
    ort_kwargs = {"file_name": args.file_name} if args.file_name else {}
    ort_model = ORTModelForTokenClassification.from_pretrained(args.onnx_dir, **ort_kwargs)

    inputs_pt = {k: v for k, v in tokenizer(args.text, return_tensors="pt", truncation=True).items() if k in ALLOWED_INPUTS}
    inputs_np = {k: v for k, v in tokenizer(args.text, return_tensors="np", truncation=True).items() if k in ALLOWED_INPUTS}

    with torch.no_grad():
        pt_logits = pt_model(**inputs_pt).logits.cpu().numpy()
    ort_logits = ort_model(**inputs_np).logits

    result = {
        "pt_shape": tuple(pt_logits.shape),
        "ort_shape": tuple(ort_logits.shape),
        "max_abs_diff": float(np.max(np.abs(pt_logits - ort_logits))),
        "allclose": bool(np.allclose(pt_logits, ort_logits, rtol=1e-3, atol=1e-5)),
        "argmax_equal": bool(np.array_equal(pt_logits.argmax(axis=-1), ort_logits.argmax(axis=-1))),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
