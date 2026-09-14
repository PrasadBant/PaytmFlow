"""Lightweight DL classification candidate vs the TF-IDF+LogisticRegression
baseline - mission Phase 8. Fine-tunes DistilBERT (66M params, the
standard "lightweight" distilled-transformer baseline, Apache-2.0,
https://huggingface.co/distilbert-base-uncased) as a document classifier
on the SAME frozen train/val/test/unseen_template splits and the SAME
OCR'd text the TF-IDF baseline was trained/evaluated on - a fair,
apples-to-apples comparison, not a different task.

Hardware note: runs on CPU only. This machine's GPU (RTX 3050, 4GB VRAM)
was not used - no CUDA-enabled PyTorch build was installed for this
comparison (the CPU wheel from pytorch.org was used, matching the
project's realistic "GPU may not be available" posture), so no VRAM
number is reported for this run; only CPU RAM and latency are measured.

Run in the isolated `.venv-ocr-bench` environment:
    .venv-ocr-bench/Scripts/python.exe app/docai/bench_dl_classifier.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import torch  # noqa: E402
from torch.utils.data import DataLoader, Dataset  # noqa: E402
from transformers import AutoModelForSequenceClassification, AutoTokenizer  # noqa: E402

from app.docai.dataset.generate import DATASET_ROOT  # noqa: E402

MODEL_NAME = "distilbert-base-uncased"
MAX_LEN = 256
BATCH_SIZE = 8
EPOCHS = 8
LR = 2e-5


def _load_split(split: str) -> tuple[list[str], list[str]]:
    split_dir = DATASET_ROOT / split
    labels = {}
    with (split_dir / "labels.jsonl").open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            labels[rec["sample_id"]] = rec
    ocr = {}
    with (split_dir / "ocr_cache.jsonl").open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            ocr[rec["sample_id"]] = rec
    texts, doc_types = [], []
    for sid, label in labels.items():
        if sid not in ocr or label["doc_type"] == "UNREADABLE":
            continue
        texts.append(ocr[sid]["text"])
        doc_types.append(label["doc_type"])
    return texts, doc_types


class TextDataset(Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels = labels

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx])
        return item


def run() -> dict:
    t_start = time.time()
    train_texts, train_labels_raw = _load_split("train")
    val_texts, val_labels_raw = _load_split("val")
    test_texts, test_labels_raw = _load_split("test")
    unseen_texts, unseen_labels_raw = _load_split("unseen_template")

    label_names = sorted(set(train_labels_raw))
    label_to_id = {name: i for i, name in enumerate(label_names)}

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=len(label_names)
    )
    device = torch.device("cpu")
    model.to(device)

    def _encode(texts):
        return tokenizer(
            texts, truncation=True, padding="max_length", max_length=MAX_LEN, return_tensors="pt"
        )

    train_ds = TextDataset(_encode(train_texts), [label_to_id[y] for y in train_labels_raw])
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    model.train()
    train_start = time.time()
    for epoch in range(EPOCHS):
        epoch_loss = 0.0
        for batch in train_loader:
            optimizer.zero_grad()
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)
            loss = outputs.loss
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
        print(f"epoch {epoch + 1}/{EPOCHS} loss={epoch_loss / len(train_loader):.4f}")
    train_seconds = time.time() - train_start

    def _evaluate(split_name: str, texts: list[str], labels_raw: list[str]) -> dict:
        if not texts:
            return {"split": split_name, "n": 0}
        model.eval()
        enc = _encode(texts)
        preds = []
        latencies = []
        with torch.no_grad():
            for i in range(len(texts)):
                item = {k: v[i : i + 1].to(device) for k, v in enc.items()}
                t0 = time.time()
                out = model(**item)
                latencies.append(time.time() - t0)
                pred_id = out.logits.argmax(dim=-1).item()
                preds.append(label_names[pred_id])
        labels_true = labels_raw
        correct = sum(1 for p, t in zip(preds, labels_true, strict=True) if p == t)
        n = len(texts)
        return {
            "split": split_name,
            "n": n,
            "accuracy": round(correct / n, 4),
            "mean_latency_seconds": round(sum(latencies) / len(latencies), 4),
        }

    results = {
        "val": _evaluate("val", val_texts, val_labels_raw),
        "test": _evaluate("test", test_texts, test_labels_raw),
        "unseen_template": _evaluate("unseen_template", unseen_texts, unseen_labels_raw),
    }

    import psutil

    process_rss_mb = round(psutil.Process().memory_info().rss / (1024 * 1024), 1)

    out = {
        "model": MODEL_NAME,
        "params": sum(p.numel() for p in model.parameters()),
        "epochs": EPOCHS,
        "train_n": len(train_texts),
        "train_seconds": round(train_seconds, 1),
        "total_seconds": round(time.time() - t_start, 1),
        "process_rss_mb": process_rss_mb,
        "device": "cpu",
        "results": results,
    }
    reports_dir = DATASET_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "dl_classifier_bench.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    out = run()
    print(f"\nmodel={out['model']} params={out['params']:,} train_seconds={out['train_seconds']}")
    print(f"process_rss_mb={out['process_rss_mb']}")
    for split, res in out["results"].items():
        if res.get("n"):
            print(
                f"{split:16s} n={res['n']:3d}  accuracy={res['accuracy']:.4f}  "
                f"mean_latency_s={res['mean_latency_seconds']:.4f}"
            )
