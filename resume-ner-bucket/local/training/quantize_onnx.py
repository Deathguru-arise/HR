from __future__ import annotations

import argparse

from optimum.onnxruntime import ORTModelForTokenClassification, ORTQuantizer
from optimum.onnxruntime.configuration import AutoQuantizationConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Quantize exported ONNX token classification model")
    parser.add_argument("--onnx-dir", default="onnx")
    parser.add_argument("--arch", default="arm64", choices=["arm64", "avx2", "avx512", "avx512_vnni"])
    args = parser.parse_args()

    model = ORTModelForTokenClassification.from_pretrained(args.onnx_dir)
    quantizer = ORTQuantizer.from_pretrained(model)
    config_factory = getattr(AutoQuantizationConfig, args.arch)
    qconfig = config_factory(is_static=False, per_channel=False)
    quantizer.quantize(save_dir=args.onnx_dir, quantization_config=qconfig)
    print("quantized")


if __name__ == "__main__":
    main()
