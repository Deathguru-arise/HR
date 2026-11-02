"""
Train token classification NER model for resume extraction.

Usage:
    python -m training.train_ner
    python -m training.train_ner --base-model deberta --epochs 10
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
from datasets import Dataset
from seqeval.metrics import f1_score, precision_score, recall_score
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    Trainer,
    TrainingArguments,
)

try:
    from training.dataset_utils import set_global_seed
except ModuleNotFoundError:
    from dataset_utils import set_global_seed

os.environ["TOKENIZERS_PARALLELISM"] = "false"

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent / "output" / "resume-ner"

BASE_MODELS = {
    "distilbert": "distilbert-base-cased",
    "deberta": "microsoft/deberta-v3-small",
}


def load_ner_data(split: str, extra_train_files: list[str] | None = None) -> tuple[list, dict]:
    path = DATA_DIR / f"ner_{split}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Generate training data first.")
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    data = payload["data"]
    meta = payload["meta"]

    if split == "train" and extra_train_files:
        for extra in extra_train_files:
            extra_path = DATA_DIR / extra
            if extra_path.exists():
                with open(extra_path, encoding="utf-8") as f:
                    extra_payload = json.load(f)
                data.extend(extra_payload["data"])
                print(f"  + {extra}: {len(extra_payload['data'])} records")

    return data, meta


def tokenize_and_align(examples, tokenizer, label_list, max_length=512):
    all_input_ids = []
    all_attention_masks = []
    all_labels = []

    for tokens, ner_tags in zip(examples["tokens"], examples["ner_tags"]):
        encoding = tokenizer(
            tokens,
            is_split_into_words=True,
            truncation=True,
            max_length=max_length,
            padding=False,
        )

        aligned_labels = []
        prev_word_id = None
        for word_id in encoding.word_ids():
            if word_id is None:
                aligned_labels.append(-100)
            elif word_id != prev_word_id:
                aligned_labels.append(ner_tags[word_id])
            else:
                label = ner_tags[word_id]
                label_name = label_list[label]
                aligned_labels.append(label_list.index("I-" + label_name[2:]) if label_name.startswith("B-") else label)
            prev_word_id = word_id

        all_input_ids.append(encoding["input_ids"])
        all_attention_masks.append(encoding["attention_mask"])
        all_labels.append(aligned_labels)

    return {
        "input_ids": all_input_ids,
        "attention_mask": all_attention_masks,
        "labels": all_labels,
    }


def compute_metrics(eval_preds, label_list):
    predictions, labels = eval_preds
    predictions = np.argmax(predictions, axis=2)

    true_sequences = []
    pred_sequences = []
    token_true = []
    token_pred = []

    for pred_seq, label_seq in zip(predictions, labels):
        seq_true = []
        seq_pred = []
        for pred_id, label_id in zip(pred_seq, label_seq):
            if label_id == -100:
                continue
            true_label = label_list[label_id]
            pred_label = label_list[pred_id]
            seq_true.append(true_label)
            seq_pred.append(pred_label)
            token_true.append(true_label)
            token_pred.append(pred_label)
        true_sequences.append(seq_true)
        pred_sequences.append(seq_pred)

    token_accuracy = sum(1 for pred, true in zip(token_pred, token_true) if pred == true) / len(token_true)
    entity_precision = precision_score(true_sequences, pred_sequences)
    entity_recall = recall_score(true_sequences, pred_sequences)
    entity_f1 = f1_score(true_sequences, pred_sequences)

    return {
        "token_accuracy": token_accuracy,
        "entity_precision": entity_precision,
        "entity_recall": entity_recall,
        "entity_f1": entity_f1,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", choices=sorted(BASE_MODELS), default="distilbert")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--extra-train", nargs="*", default=["kaggle_train.json"],
                        help="Extra training JSON files in data/ dir")
    args = parser.parse_args()

    set_global_seed(args.seed)

    model_name = BASE_MODELS[args.base_model]
    output_dir = OUTPUT_DIR / args.base_model

    train_data, meta = load_ner_data("train", extra_train_files=args.extra_train)
    val_data, _ = load_ner_data("val")
    label_list = meta["label_list"]
    label2id = {label: idx for idx, label in enumerate(label_list)}
    id2label = {idx: label for idx, label in enumerate(label_list)}

    print(f"Model: {model_name}")
    print(f"Train: {len(train_data)}, Val: {len(val_data)}")
    print(f"Labels: {len(label_list)}")
    print(f"Max length: {args.max_length}")
    print(f"Seed: {args.seed}")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    train_ds = Dataset.from_list(train_data)
    val_ds = Dataset.from_list(val_data)

    train_dataset = Dataset.from_dict(tokenize_and_align(train_ds, tokenizer, label_list, args.max_length))
    val_dataset = Dataset.from_dict(tokenize_and_align(val_ds, tokenizer, label_list, args.max_length))

    model = AutoModelForTokenClassification.from_pretrained(
        model_name,
        num_labels=len(label_list),
        id2label=id2label,
        label2id=label2id,
    )

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size * 2,
        learning_rate=args.lr,
        weight_decay=0.01,
        warmup_steps=20,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="entity_f1",
        greater_is_better=True,
        save_total_limit=3,
        logging_steps=10,
        report_to="none",
        fp16=False,
        seed=args.seed,
        data_seed=args.seed,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        processing_class=tokenizer,
        data_collator=DataCollatorForTokenClassification(tokenizer=tokenizer),
        compute_metrics=lambda preds: compute_metrics(preds, label_list),
    )

    print("\nTraining...")
    trainer.train()

    print("\nFinal evaluation:")
    metrics = trainer.evaluate()
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")

    best_dir = output_dir / "best"
    trainer.save_model(str(best_dir))
    tokenizer.save_pretrained(str(best_dir))

    with open(best_dir / "label_config.json", "w") as f:
        json.dump({"label_list": label_list, "label2id": label2id, "id2label": id2label}, f, indent=2)

    print(f"\nModel saved to {best_dir}")
    print(f"Model size: {sum(param.numel() for param in model.parameters()) / 1e6:.1f}M params")


if __name__ == "__main__":
    main()
