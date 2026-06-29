#!/usr/bin/env python3
"""Partizan neural model utilities and tiny deterministic label baselines."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import hashlib
import json
import os
import sys
from typing import Any

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.utils.data import DataLoader, Dataset
    import torch.optim as optim
except ModuleNotFoundError as exc:
    torch = None
    nn = None
    F = None
    DataLoader = None
    Dataset = object
    optim = None
    _TORCH_IMPORT_ERROR = exc
else:
    _TORCH_IMPORT_ERROR = None


SCHEMA_VERSION = "partizan.dataset_label.v0"
EXACT_REJECTED_LABELS = ("exact", "rejected")
SUPPORTED_POSITION_ENCODINGS = {"fen", "cgt_canonical"}
FEN_GATE_POSITION_ENCODING = "fen"
PIECE_VALUES = {
    "P": 1,
    "N": 3,
    "B": 3,
    "R": 5,
    "Q": 9,
    "K": 0,
}


def _require_torch() -> None:
    if torch is None:
        raise ModuleNotFoundError(
            "PyTorch is required for PartizanNet training, but it is not installed."
        ) from _TORCH_IMPORT_ERROR


if torch is not None:

    class ResidualBlock(nn.Module):
        def __init__(self, channels):
            super().__init__()
            self.conv1 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
            self.bn1 = nn.BatchNorm2d(channels)
            self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
            self.bn2 = nn.BatchNorm2d(channels)

        def forward(self, x):
            residual = x
            x = F.relu(self.bn1(self.conv1(x)))
            x = self.bn2(self.conv2(x))
            x += residual
            return F.relu(x)


    class PartizanNet(nn.Module):
        """
        A neural network designed to predict Combinatorial Game Theory values.

        It outputs a move policy, a surreal [mean, temperature] vector, and
        infinitesimal class logits.
        """

        def __init__(self, num_blocks=10, channels=128):
            super().__init__()
            self.conv_input = nn.Conv2d(14, channels, kernel_size=3, padding=1)
            self.bn_input = nn.BatchNorm2d(channels)

            self.res_blocks = nn.ModuleList(
                [ResidualBlock(channels) for _ in range(num_blocks)]
            )

            self.policy_conv = nn.Conv2d(channels, 2, kernel_size=1)
            self.policy_bn = nn.BatchNorm2d(2)
            self.policy_fc = nn.Linear(2 * 8 * 8, 4096)

            self.surreal_conv = nn.Conv2d(channels, 1, kernel_size=1)
            self.surreal_bn = nn.BatchNorm2d(1)
            self.surreal_fc1 = nn.Linear(64, 64)
            self.surreal_fc2 = nn.Linear(64, 2)

            self.infinitesimal_fc = nn.Linear(64, 4)

        def forward(self, x):
            x = F.relu(self.bn_input(self.conv_input(x)))
            for block in self.res_blocks:
                x = block(x)

            p = F.relu(self.policy_bn(self.policy_conv(x)))
            p = p.view(p.size(0), -1)
            policy_logits = self.policy_fc(p)

            s = F.relu(self.surreal_bn(self.surreal_conv(x)))
            s = s.view(s.size(0), -1)
            s_hidden = F.relu(self.surreal_fc1(s))

            surreal_vector = self.surreal_fc2(s_hidden)
            infinitesimal_logits = self.infinitesimal_fc(s_hidden)

            return policy_logits, surreal_vector, infinitesimal_logits


    def surreal_loss(pred_vector, target_vector, alpha=1.0, beta=1.0):
        """Penalize incorrect mean value and temperature."""

        pred_mean, pred_temp = pred_vector[:, 0], pred_vector[:, 1]
        target_mean, target_temp = target_vector[:, 0], target_vector[:, 1]

        mean_loss = F.mse_loss(pred_mean, target_mean)
        temp_loss = F.mse_loss(pred_temp, target_temp)

        return alpha * mean_loss + beta * temp_loss


    def fen_to_tensor(fen: str) -> torch.Tensor:
        """
        Convert a FEN string into a 14x8x8 tensor representation.

        The first 12 channels are piece planes. The final two channels hold
        side-to-move and board-mask features.
        """

        pieces = {
            "P": 0,
            "N": 1,
            "B": 2,
            "R": 3,
            "Q": 4,
            "K": 5,
            "p": 6,
            "n": 7,
            "b": 8,
            "r": 9,
            "q": 10,
            "k": 11,
        }

        tensor = torch.zeros(14, 8, 8)
        board_part = fen.split()[0]

        row, col = 0, 0
        for char in board_part:
            if char == "/":
                row += 1
                col = 0
            elif char.isdigit():
                col += int(char)
            elif char in pieces:
                channel = pieces[char]
                tensor[channel, row, col] = 1.0
                col += 1

        if len(fen.split()) > 1:
            turn = fen.split()[1]
            tensor[12, :, :] = 1.0 if turn == "w" else 0.0
        tensor[13, :, :] = 1.0

        return tensor


    class CGTDataset(Dataset):
        def __init__(self, jsonl_path):
            self.data = []
            with open(jsonl_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if "mean_value" in item and "temperature" in item:
                        self.data.append(item)

        def __len__(self):
            return len(self.data)

        def __getitem__(self, idx):
            item = self.data[idx]
            fen = item["fen"]

            target = torch.tensor(
                [
                    float(item["mean_value"]),
                    float(item["temperature"]),
                ],
                dtype=torch.float32,
            )

            return fen_to_tensor(fen), target

else:

    class ResidualBlock:
        def __init__(self, *args, **kwargs):
            _require_torch()


    class PartizanNet:
        def __init__(self, *args, **kwargs):
            _require_torch()


    class CGTDataset:
        def __init__(self, *args, **kwargs):
            _require_torch()


    def surreal_loss(*args, **kwargs):
        _require_torch()


    def fen_to_tensor(*args, **kwargs):
        _require_torch()


def load_dataset_label_v0_jsonl(jsonl_path: str | Path) -> list[dict[str, Any]]:
    """Load minimally validated partizan.dataset_label.v0 JSONL rows."""

    path = Path(jsonl_path)
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"{path}:{line_number}: blank JSONL rows are invalid")

            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON: {error.msg}"
                ) from error

            _validate_baseline_row(row, path, line_number)
            rows.append(row)

    return rows


def _validate_baseline_row(row: Any, path: Path, line_number: int) -> None:
    if not isinstance(row, dict):
        raise ValueError(f"{path}:{line_number}: row must be a JSON object")
    if row.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"{path}:{line_number}: schema_version must be {SCHEMA_VERSION!r}"
        )

    label_kind = row.get("label_kind")
    if label_kind not in {"exact", "rejected", "heuristic", "prediction"}:
        raise ValueError(f"{path}:{line_number}: unsupported label_kind {label_kind!r}")

    position = row.get("position")
    if not isinstance(position, dict):
        raise ValueError(f"{path}:{line_number}: position must be an object")
    if position.get("encoding") not in SUPPORTED_POSITION_ENCODINGS:
        raise ValueError(
            f"{path}:{line_number}: unsupported position.encoding "
            f"{position.get('encoding')!r}"
        )
    if not isinstance(position.get("text"), str) or not position["text"].strip():
        raise ValueError(f"{path}:{line_number}: position.text must be non-empty")

    if label_kind == "exact" and not isinstance(row.get("exact"), dict):
        raise ValueError(f"{path}:{line_number}: exact row missing exact payload")
    if label_kind == "rejected" and not isinstance(row.get("rejected"), dict):
        raise ValueError(f"{path}:{line_number}: rejected row missing rejected payload")


def split_label_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Separate rows by label kind so exact supervision is never mixed."""

    return {
        "exact": [row for row in rows if row.get("label_kind") == "exact"],
        "rejected": [row for row in rows if row.get("label_kind") == "rejected"],
        "heuristic": [row for row in rows if row.get("label_kind") == "heuristic"],
        "prediction": [row for row in rows if row.get("label_kind") == "prediction"],
    }


def derive_position_features(row: dict[str, Any]) -> dict[str, Any]:
    """Derive simple position features for current baseline smoke tests."""

    encoding = row["position"]["encoding"]
    position_text = row["position"]["text"]
    if encoding != FEN_GATE_POSITION_ENCODING:
        return _non_fen_position_features(encoding, position_text)

    fen = position_text
    fields = fen.split()
    board = fields[0] if fields else ""
    side_to_move = fields[1] if len(fields) > 1 else "?"
    castling = fields[2] if len(fields) > 2 else "?"

    piece_counts: Counter[str] = Counter()
    empty_square_count = 0
    for char in board:
        if char.isdigit():
            empty_square_count += int(char)
        elif char == "/":
            continue
        elif char.isalpha():
            piece_counts[char] += 1

    white_piece_count = sum(count for piece, count in piece_counts.items() if piece.isupper())
    black_piece_count = sum(count for piece, count in piece_counts.items() if piece.islower())
    piece_count = white_piece_count + black_piece_count

    material_balance = 0
    absolute_material = 0
    for piece, count in piece_counts.items():
        value = PIECE_VALUES.get(piece.upper(), 0) * count
        absolute_material += value
        material_balance += value if piece.isupper() else -value

    return {
        "position_encoding": encoding,
        "position_text_length": len(position_text),
        "fen_length": len(fen),
        "fen_space_count": fen.count(" "),
        "board_token_length": len(board),
        "board_slash_count": board.count("/"),
        "rank_count": board.count("/") + 1 if board else 0,
        "side_to_move": side_to_move,
        "castling_token": castling,
        "has_castling_rights": castling not in {"-", "?"},
        "castling_right_count": 0 if castling in {"-", "?"} else len(castling),
        "empty_square_count": empty_square_count,
        "piece_count": piece_count,
        "white_piece_count": white_piece_count,
        "black_piece_count": black_piece_count,
        "king_count": piece_counts["K"] + piece_counts["k"],
        "queen_count": piece_counts["Q"] + piece_counts["q"],
        "rook_count": piece_counts["R"] + piece_counts["r"],
        "bishop_count": piece_counts["B"] + piece_counts["b"],
        "knight_count": piece_counts["N"] + piece_counts["n"],
        "pawn_count": piece_counts["P"] + piece_counts["p"],
        "material_balance": material_balance,
        "absolute_material": absolute_material,
        "piece_counts": dict(sorted(piece_counts.items())),
    }


def _non_fen_position_features(encoding: str, position_text: str) -> dict[str, Any]:
    return {
        "position_encoding": encoding,
        "position_text_length": len(position_text),
        "fen_length": 0,
        "fen_space_count": 0,
        "board_token_length": 0,
        "board_slash_count": 0,
        "rank_count": 0,
        "side_to_move": f"not_{FEN_GATE_POSITION_ENCODING}",
        "castling_token": "?",
        "has_castling_rights": False,
        "castling_right_count": 0,
        "empty_square_count": 0,
        "piece_count": 0,
        "white_piece_count": 0,
        "black_piece_count": 0,
        "king_count": 0,
        "queen_count": 0,
        "rook_count": 0,
        "bishop_count": 0,
        "knight_count": 0,
        "pawn_count": 0,
        "material_balance": 0,
        "absolute_material": 0,
        "piece_counts": {},
    }


def predict_exact_vs_rejected(features: dict[str, Any]) -> str:
    """
    Deterministic Wave 3 gate baseline from FEN features only.

    This intentionally avoids using rejected.reasons. It is a smoke-test rule,
    not a claim about the domain boundary.
    """

    if features["has_castling_rights"]:
        return "rejected"
    if features["king_count"] == 2 and features["piece_count"] <= 2:
        return "rejected"
    return "exact"


def evaluate_label_shard_baseline(jsonl_path: str | Path) -> dict[str, Any]:
    """Evaluate deterministic baselines over a dataset-label v0 JSONL shard."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    splits = split_label_rows(rows)
    features_by_row = [
        {
            "row_id": row.get("row_id"),
            "label_kind": row.get("label_kind"),
            "features": derive_position_features(row),
        }
        for row in rows
    ]

    source_commits = sorted(
        {
            str(row["provenance"]["code_commit"])
            for row in splits["exact"]
            if isinstance(row.get("provenance"), dict)
            and row["provenance"].get("code_commit")
        }
    )
    provenance_random_seeds = sorted(
        {
            row["provenance"]["random_seed"]
            for row in splits["exact"]
            if isinstance(row.get("provenance"), dict)
            and "random_seed" in row["provenance"]
        }
    )

    return {
        "dataset_path": str(path),
        "dataset_sha256": _sha256_file(path),
        "schema_version": SCHEMA_VERSION,
        "commit_or_manifest_id": (
            source_commits[0]
            if len(source_commits) == 1
            else f"sha256:{_sha256_file(path)}"
        ),
        "source_commits": source_commits,
        "randomness": "none",
        "seed": None,
        "provenance_random_seeds": provenance_random_seeds,
        "row_counts": {
            "total": len(rows),
            "exact": len(splits["exact"]),
            "rejected": len(splits["rejected"]),
            "heuristic": len(splits["heuristic"]),
            "prediction": len(splits["prediction"]),
        },
        "feature_summary": _feature_summary(features_by_row),
        "baselines": {
            "exact_vs_rejected": _evaluate_exact_vs_rejected(rows, features_by_row),
            "exact_value_class": _evaluate_exact_value_class(splits["exact"]),
        },
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _feature_summary(features_by_row: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_keys = (
        "position_text_length",
        "fen_length",
        "piece_count",
        "white_piece_count",
        "black_piece_count",
        "king_count",
        "queen_count",
        "rook_count",
        "pawn_count",
        "material_balance",
        "absolute_material",
        "empty_square_count",
        "castling_right_count",
    )
    summary: dict[str, Any] = {}

    for key in numeric_keys:
        values = [entry["features"][key] for entry in features_by_row]
        if not values:
            continue
        summary[key] = {
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / len(values),
        }

    summary["side_to_move_counts"] = dict(
        sorted(Counter(entry["features"]["side_to_move"] for entry in features_by_row).items())
    )
    summary["position_encoding_counts"] = dict(
        sorted(
            Counter(entry["features"]["position_encoding"] for entry in features_by_row).items()
        )
    )
    summary["has_castling_rights_counts"] = {
        str(key).lower(): value
        for key, value in sorted(
            Counter(
                entry["features"]["has_castling_rights"] for entry in features_by_row
            ).items()
        )
    }
    return summary


def _evaluate_exact_vs_rejected(
    rows: list[dict[str, Any]],
    features_by_row: list[dict[str, Any]],
) -> dict[str, Any]:
    eligible = [
        (row, entry["features"])
        for row, entry in zip(rows, features_by_row)
        if row.get("label_kind") in EXACT_REJECTED_LABELS
        and entry["features"]["position_encoding"] == FEN_GATE_POSITION_ENCODING
    ]
    predictions = [predict_exact_vs_rejected(features) for _, features in eligible]
    targets = [row["label_kind"] for row, _ in eligible]

    return {
        "baseline_id": "fen_string_material_gate_v0",
        "target": "label_kind exact-vs-rejected",
        "eligible_label_kinds": list(EXACT_REJECTED_LABELS),
        "excluded_label_kinds": sorted(
            {
                str(row.get("label_kind"))
                for row in rows
                if row.get("label_kind") not in EXACT_REJECTED_LABELS
            }
        ),
        "included_position_encoding": FEN_GATE_POSITION_ENCODING,
        "excluded_position_encodings": sorted(
            {
                entry["features"]["position_encoding"]
                for row, entry in zip(rows, features_by_row)
                if row.get("label_kind") in EXACT_REJECTED_LABELS
                and entry["features"]["position_encoding"] != FEN_GATE_POSITION_ENCODING
            }
        ),
        "support": len(eligible),
        **_classification_metrics(targets, predictions, EXACT_REJECTED_LABELS),
    }


def _classification_metrics(
    targets: list[str],
    predictions: list[str],
    labels: tuple[str, ...],
) -> dict[str, Any]:
    confusion = {
        label: {predicted: 0 for predicted in labels}
        for label in labels
    }
    for target, prediction in zip(targets, predictions):
        confusion[target][prediction] += 1

    correct = sum(1 for target, prediction in zip(targets, predictions) if target == prediction)
    support = len(targets)
    per_class = {}
    for label in labels:
        true_positive = confusion[label][label]
        false_positive = sum(
            confusion[other][label] for other in labels if other != label
        )
        false_negative = sum(
            confusion[label][other] for other in labels if other != label
        )
        precision = _safe_div(true_positive, true_positive + false_positive)
        recall = _safe_div(true_positive, true_positive + false_negative)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": sum(confusion[label].values()),
        }

    return {
        "accuracy": _safe_div(correct, support),
        "confusion_matrix": confusion,
        "per_class": per_class,
    }


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _evaluate_exact_value_class(exact_rows: list[dict[str, Any]]) -> dict[str, Any]:
    value_classes = [
        str(row["exact"].get("value_class"))
        for row in exact_rows
        if isinstance(row.get("exact"), dict) and row["exact"].get("value_class")
    ]
    class_counts = dict(sorted(Counter(value_classes).items()))
    report: dict[str, Any] = {
        "baseline_id": "exact_majority_value_class_v0",
        "target": "exact.value_class",
        "eligible_label_kinds": ["exact"],
        "support": len(value_classes),
        "class_counts": class_counts,
    }

    if len(value_classes) < 2:
        report.update(
            {
                "status": "not_meaningful",
                "reason": "requires at least two exact rows for deterministic holdout metrics",
            }
        )
        return report

    predictions = []
    for index, _target in enumerate(value_classes):
        training_values = value_classes[:index] + value_classes[index + 1 :]
        predictions.append(_majority_label(training_values))

    report.update(
        {
            "status": "evaluated",
            "validation": "leave_one_out_majority",
            **_classification_metrics(
                value_classes,
                predictions,
                tuple(sorted(class_counts)),
            ),
        }
    )
    return report


def _majority_label(labels: list[str]) -> str:
    counts = Counter(labels)
    return sorted(counts, key=lambda label: (-counts[label], label))[0]


def print_baseline_metrics(metrics: dict[str, Any]) -> None:
    print(json.dumps(metrics, indent=2, sort_keys=True))


def evaluate_split_report(jsonl_path: str | Path) -> dict[str, Any]:
    """Build a deterministic split and leakage report for a dataset-label shard."""
    return evaluate_split_report_with_mode(jsonl_path, "position")


def evaluate_split_report_with_mode(
    jsonl_path: str | Path, split_key_mode: str
) -> dict[str, Any]:
    """Build a deterministic split report with the requested split-key policy."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    assignments = split_assignments_for_rows(rows, split_key_mode)

    return split_report_from_assignments(
        path,
        assignments,
        split_report_id_for_mode(split_key_mode, family_holdout=False),
        split_policy_for_mode(split_key_mode, family_holdout=False),
    )


def evaluate_family_holdout_report(
    jsonl_path: str | Path, holdout_family: str
) -> dict[str, Any]:
    """Build a family-held-out split report for a dataset-label shard."""
    return evaluate_family_holdout_report_with_mode(
        jsonl_path, holdout_family, "position"
    )


def evaluate_family_holdout_report_with_mode(
    jsonl_path: str | Path, holdout_family: str, split_key_mode: str
) -> dict[str, Any]:
    """Build a family-held-out split report with the requested split-key policy."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    assignments = family_holdout_assignments_for_rows(
        rows, holdout_family, split_key_mode
    )

    report = split_report_from_assignments(
        path,
        assignments,
        split_report_id_for_mode(split_key_mode, family_holdout=True),
        split_policy_for_mode(
            split_key_mode, family_holdout=True, holdout_family=holdout_family
        ),
    )
    report["holdout_family"] = holdout_family
    return report


def evaluate_split_baseline_report(
    jsonl_path: str | Path,
    split_key_mode: str = "position",
    holdout_family: str | None = None,
) -> dict[str, Any]:
    """Score deterministic baselines per split for a dataset-label shard."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    if holdout_family:
        assignments = family_holdout_assignments_for_rows(
            rows, holdout_family, split_key_mode
        )
        splitter_id = split_report_id_for_mode(split_key_mode, family_holdout=True)
        split_policy = split_policy_for_mode(
            split_key_mode, family_holdout=True, holdout_family=holdout_family
        )
    else:
        assignments = split_assignments_for_rows(rows, split_key_mode)
        splitter_id = split_report_id_for_mode(split_key_mode, family_holdout=False)
        split_policy = split_policy_for_mode(split_key_mode, family_holdout=False)

    features_by_row = [derive_position_features(row) for row in rows]
    split_metrics = {}
    for split in sorted({assignment["split"] for assignment in assignments}):
        split_items = [
            (row, assignment, features)
            for row, assignment, features in zip(rows, assignments, features_by_row)
            if assignment["split"] == split
            and row.get("label_kind") in EXACT_REJECTED_LABELS
            and features["position_encoding"] == FEN_GATE_POSITION_ENCODING
        ]
        targets = [row["label_kind"] for row, _assignment, _features in split_items]
        predictions = [
            predict_exact_vs_rejected(features)
            for _row, _assignment, features in split_items
        ]
        split_metrics[split] = {
            "support": len(split_items),
            "target_counts": dict(sorted(Counter(targets).items())),
            "prediction_counts": dict(sorted(Counter(predictions).items())),
            **_classification_metrics(targets, predictions, EXACT_REJECTED_LABELS),
        }

    report: dict[str, Any] = {
        "dataset_path": str(path),
        "dataset_sha256": _sha256_file(path),
        "schema_version": SCHEMA_VERSION,
        "baseline_id": "fen_string_material_gate_v0",
        "target": "label_kind exact-vs-rejected",
        "eligible_label_kinds": list(EXACT_REJECTED_LABELS),
        "included_position_encoding": FEN_GATE_POSITION_ENCODING,
        "splitter_id": splitter_id,
        "split_policy": split_policy,
        "row_counts": _count_by(assignments, "split"),
        "split_metrics": split_metrics,
    }
    if holdout_family:
        report["holdout_family"] = holdout_family
    return report


def split_assignments_for_rows(
    rows: list[dict[str, Any]], split_key_mode: str
) -> list[dict[str, Any]]:
    assignments = []
    for row in rows:
        family = generator_family(row)
        position_key = position_key_for_row(row)
        symmetry_position_key = symmetry_position_key_for_row(row)
        split_key = split_key_for_mode(
            family, position_key, symmetry_position_key, split_key_mode
        )
        split = split_for_key(split_key)
        assignments.append(
            split_assignment_for_row(
                row,
                split,
                family,
                position_key,
                symmetry_position_key,
                split_key,
            )
        )
    return assignments


def family_holdout_assignments_for_rows(
    rows: list[dict[str, Any]], holdout_family: str, split_key_mode: str
) -> list[dict[str, Any]]:
    assignments = []
    for row in rows:
        family = generator_family(row)
        position_key = position_key_for_row(row)
        symmetry_position_key = symmetry_position_key_for_row(row)
        if family == holdout_family:
            split = "test"
            split_key = f"{family}|{position_key}"
        else:
            split_key = split_key_for_mode(
                family, position_key, symmetry_position_key, split_key_mode
            )
            split = train_dev_split_for_key(split_key)
        assignments.append(
            split_assignment_for_row(
                row,
                split,
                family,
                position_key,
                symmetry_position_key,
                split_key,
            )
        )
    return assignments


def split_assignment_for_row(
    row: dict[str, Any],
    split: str,
    family: str,
    position_key: str,
    symmetry_position_key: str | None,
    split_key: str,
) -> dict[str, Any]:
    exact = row.get("exact", {}) if isinstance(row.get("exact"), dict) else {}
    exact_value = exact.get("value", {}) if isinstance(exact.get("value"), dict) else {}
    return {
        "row_id": str(row.get("row_id")),
        "label_kind": str(row.get("label_kind")),
        "split": split,
        "generator_family": family,
        "position_key": position_key,
        "symmetry_position_key": symmetry_position_key,
        "split_key": split_key,
        "exact_certificate_digest": exact_certificate_digest(row),
        "exact_value_class": str(exact.get("value_class"))
        if exact.get("value_class")
        else None,
        "exact_solver_scope": str(exact_value.get("solver_scope"))
        if exact_value.get("solver_scope")
        else None,
        "frontier_value_class": str(exact_value.get("frontier_value_class"))
        if exact_value.get("frontier_value_class")
        else None,
    }


def split_report_from_assignments(
    path: Path,
    assignments: list[dict[str, Any]],
    splitter_id: str,
    split_policy: dict[str, str],
) -> dict[str, Any]:
    symmetry_assignments = [
        item for item in assignments if item.get("symmetry_position_key")
    ]
    return {
        "splitter_id": splitter_id,
        "dataset_path": str(path),
        "dataset_sha256": _sha256_file(path),
        "schema_version": SCHEMA_VERSION,
        "split_policy": split_policy,
        "row_counts": _count_by(assignments, "split"),
        "label_kind_counts": _nested_count_by(assignments, "split", "label_kind"),
        "generator_family_counts": _nested_count_by(
            assignments, "split", "generator_family"
        ),
        "exact_value_class_counts": _nested_count_by(
            assignments, "split", "exact_value_class"
        ),
        "exact_solver_scope_counts": _nested_count_by(
            assignments, "split", "exact_solver_scope"
        ),
        "frontier_value_class_counts": _nested_count_by(
            assignments, "split", "frontier_value_class"
        ),
        "leakage_checks": {
            "symmetry_position_key_eligible_rows": len(symmetry_assignments),
            "duplicate_row_ids": duplicate_total(
                Counter(item["row_id"] for item in assignments)
            ),
            "duplicate_positions": duplicate_total(
                Counter(item["position_key"] for item in assignments)
            ),
            "duplicate_symmetry_positions": duplicate_total(
                Counter(item["symmetry_position_key"] for item in symmetry_assignments)
            ),
            "duplicate_exact_certificate_digests": duplicate_total(
                Counter(
                    item["exact_certificate_digest"]
                    for item in assignments
                    if item["exact_certificate_digest"]
                )
            ),
            "position_key_cross_split": cross_split_summary(
                assignments, "position_key"
            ),
            "symmetry_position_key_cross_split": cross_split_summary(
                symmetry_assignments, "symmetry_position_key"
            ),
            "exact_certificate_digest_cross_split": cross_split_summary(
                [
                    item
                    for item in assignments
                    if item["exact_certificate_digest"]
                ],
                "exact_certificate_digest",
            ),
        },
    }


def generator_family(row: dict[str, Any]) -> str:
    provenance = row.get("provenance")
    if isinstance(provenance, dict) and provenance.get("generator"):
        return str(provenance["generator"])

    row_id = str(row.get("row_id"))
    if row_id.startswith("astralbase-w6-kqk-frontier-") or row_id.startswith(
        "astralbase-w7-kqk-frontier-"
    ):
        return "astralbase_kqk_frontier_generator"
    if row_id.startswith("astralbase-w7-krk-frontier-"):
        return "astralbase_krk_frontier_generator"
    return "unprovenanced_rejected"


def position_key_for_row(row: dict[str, Any]) -> str:
    position = row["position"]
    return f"{position['encoding']}:{position['text']}"


def symmetry_position_key_for_row(row: dict[str, Any]) -> str | None:
    position = row["position"]
    if position["encoding"] != FEN_GATE_POSITION_ENCODING:
        return None
    return fen_d4_symmetry_key(position["text"])


def fen_d4_symmetry_key(fen: str) -> str | None:
    fields = fen.split()
    if len(fields) < 4:
        return None

    board_token = fields[0]
    castling = fields[2]
    en_passant = fields[3]
    if castling != "-" or en_passant != "-":
        return None

    board = expand_fen_board(board_token)
    if board is None:
        return None

    canonical_board = min(
        compress_fen_board(transform_board(board, transform))
        for transform in D4_TRANSFORMS
    )
    return f"fen_d4:{canonical_board} {' '.join(fields[1:])}"


def expand_fen_board(board_token: str) -> list[list[str]] | None:
    ranks = board_token.split("/")
    if len(ranks) != 8:
        return None

    board: list[list[str]] = []
    for rank in ranks:
        squares: list[str] = []
        for char in rank:
            if char in "12345678":
                squares.extend(["."] * int(char))
            elif char.isalpha():
                squares.append(char)
            else:
                return None
        if len(squares) != 8:
            return None
        board.append(squares)
    return board


def compress_fen_board(board: list[list[str]]) -> str:
    ranks = []
    for row in board:
        rank_parts = []
        empty_count = 0
        for square in row:
            if square == ".":
                empty_count += 1
                continue
            if empty_count:
                rank_parts.append(str(empty_count))
                empty_count = 0
            rank_parts.append(square)
        if empty_count:
            rank_parts.append(str(empty_count))
        ranks.append("".join(rank_parts))
    return "/".join(ranks)


def transform_board(
    board: list[list[str]], transform: tuple[str, Any]
) -> list[list[str]]:
    _name, coordinate_map = transform
    transformed = [["." for _ in range(8)] for _ in range(8)]
    for row_index, row in enumerate(board):
        for col_index, piece in enumerate(row):
            new_row, new_col = coordinate_map(row_index, col_index)
            transformed[new_row][new_col] = piece
    return transformed


D4_TRANSFORMS = (
    ("identity", lambda row, col: (row, col)),
    ("rotate_90", lambda row, col: (col, 7 - row)),
    ("rotate_180", lambda row, col: (7 - row, 7 - col)),
    ("rotate_270", lambda row, col: (7 - col, row)),
    ("mirror_files", lambda row, col: (row, 7 - col)),
    ("mirror_ranks", lambda row, col: (7 - row, col)),
    ("main_diagonal", lambda row, col: (col, row)),
    ("anti_diagonal", lambda row, col: (7 - col, 7 - row)),
)


def split_key_for_mode(
    family: str,
    position_key: str,
    symmetry_position_key: str | None,
    split_key_mode: str,
) -> str:
    if split_key_mode == "position":
        return f"{family}|{position_key}"
    if split_key_mode == "symmetry":
        return f"{family}|{symmetry_position_key or position_key}"
    raise ValueError(f"unsupported split_key_mode {split_key_mode!r}")


def split_report_id_for_mode(split_key_mode: str, family_holdout: bool) -> str:
    if split_key_mode == "position":
        return (
            "family_holdout_generator_position_hash_v0"
            if family_holdout
            else "deterministic_generator_position_hash_v0"
        )
    if split_key_mode == "symmetry":
        return (
            "family_holdout_generator_symmetry_hash_v0"
            if family_holdout
            else "deterministic_generator_symmetry_hash_v0"
        )
    raise ValueError(f"unsupported split_key_mode {split_key_mode!r}")


def split_policy_for_mode(
    split_key_mode: str,
    family_holdout: bool,
    holdout_family: str | None = None,
) -> dict[str, str]:
    split_key = "generator_family|position.encoding:position.text"
    if split_key_mode == "symmetry":
        split_key = (
            "generator_family|fen_d4_canonical(position) for supported FEN rows; "
            "generator_family|position.encoding:position.text otherwise"
        )
    elif split_key_mode != "position":
        raise ValueError(f"unsupported split_key_mode {split_key_mode!r}")

    if family_holdout:
        policy = {
            "train": "family != holdout_family and sha256(split_key) % 100 < 90",
            "dev": "family != holdout_family and sha256(split_key) % 100 >= 90",
            "test": "family == holdout_family",
            "split_key": split_key,
        }
        if holdout_family is not None:
            policy["holdout_family"] = holdout_family
        return policy

    return {
        "train": "sha256(split_key) % 100 < 80",
        "dev": "80 <= sha256(split_key) % 100 < 90",
        "test": "90 <= sha256(split_key) % 100",
        "split_key": split_key,
    }


def exact_certificate_digest(row: dict[str, Any]) -> str | None:
    provenance = row.get("provenance")
    if not isinstance(provenance, dict):
        return None
    certificate = provenance.get("certificate")
    if not isinstance(certificate, dict) or not certificate.get("digest"):
        return None
    return str(certificate["digest"])


def split_for_key(split_key: str) -> str:
    bucket = int(hashlib.sha256(split_key.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "dev"
    return "test"


def train_dev_split_for_key(split_key: str) -> str:
    bucket = int(hashlib.sha256(split_key.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 90:
        return "train"
    return "dev"


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item[key]) for item in items).items()))


def _nested_count_by(
    items: list[dict[str, Any]], outer_key: str, inner_key: str
) -> dict[str, dict[str, int]]:
    outer_values = sorted({str(item[outer_key]) for item in items})
    result: dict[str, dict[str, int]] = {}
    for outer_value in outer_values:
        counter = Counter(
            str(item[inner_key])
            for item in items
            if str(item[outer_key]) == outer_value and item.get(inner_key) is not None
        )
        result[outer_value] = dict(sorted(counter.items()))
    return result


def duplicate_total(counts: Counter[str]) -> int:
    return sum(count - 1 for count in counts.values() if count > 1)


def cross_split_summary(
    items: list[dict[str, Any]], key: str, example_limit: int = 5
) -> dict[str, Any]:
    split_sets: dict[str, set[str]] = {}
    for item in items:
        split_sets.setdefault(str(item[key]), set()).add(str(item["split"]))

    violations = {
        key_value: sorted(splits)
        for key_value, splits in split_sets.items()
        if len(splits) > 1
    }
    return {
        "violation_count": len(violations),
        "examples": [
            {"key": key_value, "splits": splits}
            for key_value, splits in list(sorted(violations.items()))[:example_limit]
        ],
    }


def print_json_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, indent=2, sort_keys=True))


def train_partizan_net(
    dataset_path: str = "cgt_dataset.jsonl",
    epochs: int = 5,
    batch_size: int = 128,
    lr: float = 0.001,
):
    _require_torch()

    print(f"Initializing PartizanNet training loop on {dataset_path}...")

    dataset = CGTDataset(dataset_path)
    if len(dataset) == 0:
        raise ValueError(f"No labeled positions found in {dataset_path}")

    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    print(f"Loaded {len(dataset)} combinatorial game states.")

    device = torch.device(
        "mps"
        if torch.backends.mps.is_available()
        else ("cuda" if torch.cuda.is_available() else "cpu")
    )
    print(f"Utilizing compute device: {device}")

    model = PartizanNet().to(device)
    optimizer = optim.Adam(model.parameters(), lr=lr)

    model.train()
    for epoch in range(epochs):
        total_loss = 0.0
        for features, targets in dataloader:
            features, targets = features.to(device), targets.to(device)

            optimizer.zero_grad()
            _, surreal_pred, _ = model(features)

            loss = surreal_loss(surreal_pred, targets, alpha=1.0, beta=2.0)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()

        avg_loss = total_loss / len(dataloader)
        print(f"Epoch [{epoch + 1}/{epochs}] - Surreal Loss: {avg_loss:.4f}")

    print("Training complete.")
    return model


def _legacy_main() -> int:
    if os.path.exists("cgt_dataset.jsonl"):
        train_partizan_net()
    else:
        print("Waiting for cgt_dataset.jsonl from Modal orchestrator...")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command")

    baseline_parser = subcommands.add_parser(
        "baseline-eval",
        help="Evaluate deterministic baselines over a dataset-label v0 JSONL shard.",
    )
    baseline_parser.add_argument("jsonl_path", type=Path)

    split_parser = subcommands.add_parser(
        "split-report",
        help="Build deterministic train/dev/test split and leakage report.",
    )
    split_parser.add_argument("jsonl_path", type=Path)
    split_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the split report JSON.",
    )
    split_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for split assignment.",
    )

    holdout_parser = subcommands.add_parser(
        "family-holdout-report",
        help="Build a family-held-out split and leakage report.",
    )
    holdout_parser.add_argument("jsonl_path", type=Path)
    holdout_parser.add_argument("--holdout-family", required=True)
    holdout_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the holdout report JSON.",
    )
    holdout_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for train/dev assignment.",
    )

    split_baseline_parser = subcommands.add_parser(
        "split-baseline-report",
        help="Score deterministic baselines per split.",
    )
    split_baseline_parser.add_argument("jsonl_path", type=Path)
    split_baseline_parser.add_argument(
        "--holdout-family",
        help="Optional generator family to hold out as the test split.",
    )
    split_baseline_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for split assignment.",
    )
    split_baseline_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the baseline report JSON.",
    )

    return parser


def cli_main(argv: list[str] | None = None) -> int:
    args_list = sys.argv[1:] if argv is None else argv
    if not args_list:
        return _legacy_main()

    parser = build_parser()
    args = parser.parse_args(args_list)

    if args.command == "baseline-eval":
        metrics = evaluate_label_shard_baseline(args.jsonl_path)
        print_baseline_metrics(metrics)
        return 0
    if args.command == "split-report":
        report = evaluate_split_report_with_mode(
            args.jsonl_path, args.split_key_mode
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print_json_report(report)
        return 0
    if args.command == "family-holdout-report":
        report = evaluate_family_holdout_report_with_mode(
            args.jsonl_path, args.holdout_family, args.split_key_mode
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print_json_report(report)
        return 0
    if args.command == "split-baseline-report":
        report = evaluate_split_baseline_report(
            args.jsonl_path,
            split_key_mode=args.split_key_mode,
            holdout_family=args.holdout_family,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print_json_report(report)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(cli_main())
