from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Export trained model to ONNX using optimum-cli")
    parser.add_argument("--model-dir", default="training/output/resume-ner/distilbert/best")
    parser.add_argument("--output-dir", default="onnx")
    parser.add_argument("--task", default="token-classification")
    args = parser.parse_args()

    cmd = [
        "optimum-cli",
        "export",
        "onnx",
        "--model",
        args.model_dir,
        "--task",
        args.task,
        args.output_dir,
    ]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
