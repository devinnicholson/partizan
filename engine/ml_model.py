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
COMPOSITION_HOLDOUT_SELECTORS = (
    "component_count",
    "component_family",
    "component_topology_family",
    "composition_digest",
    "result_value_digest",
)
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
FIXTURE_COMPONENT_SUM_RULE = "component_index_integer_sum_fixture_v0"
MISSING_COMPOSITION_VALUE_RULE = "__missing__"
MISSING_COMPONENT_TOPOLOGY_FAMILY = "__missing__"


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


def composition_exact_result_metrics(
    targets: list[str],
    predictions: list[str],
) -> dict[str, Any]:
    correct = sum(1 for target, prediction in zip(targets, predictions) if target == prediction)
    return {
        "accuracy": _safe_div(correct, len(targets)),
        "correct": correct,
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


def evaluate_composition_holdout_report(
    jsonl_path: str | Path,
    holdout_selector: str,
    holdout_value: Any,
) -> dict[str, Any]:
    """Build an exact-composition-held-out split report for a shard."""
    return evaluate_composition_holdout_report_with_mode(
        jsonl_path, holdout_selector, holdout_value, "position"
    )


def evaluate_composition_holdout_report_with_mode(
    jsonl_path: str | Path,
    holdout_selector: str,
    holdout_value: Any,
    split_key_mode: str,
) -> dict[str, Any]:
    """Build an exact-composition-held-out report with train/dev hashing."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    assignments = composition_holdout_assignments_for_rows(
        rows, holdout_selector, holdout_value, split_key_mode
    )

    report = split_report_from_assignments(
        path,
        assignments,
        composition_holdout_report_id_for_mode(split_key_mode, holdout_selector),
        composition_holdout_policy_for_mode(
            split_key_mode, holdout_selector, holdout_value
        ),
    )
    report["holdout_selector"] = holdout_selector
    report["holdout_value"] = str(holdout_value)
    report["holdout_label_kind"] = "exact"
    return report


def evaluate_composition_baseline_report(
    jsonl_path: str | Path,
    holdout_selector: str,
    holdout_value: Any,
    split_key_mode: str = "position",
) -> dict[str, Any]:
    """Score deterministic exact-result baselines on a composition holdout split."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    assignments = composition_holdout_assignments_for_rows(
        rows, holdout_selector, holdout_value, split_key_mode
    )
    split_metadata = split_report_from_assignments(
        path,
        assignments,
        composition_holdout_report_id_for_mode(split_key_mode, holdout_selector),
        composition_holdout_policy_for_mode(
            split_key_mode, holdout_selector, holdout_value
        ),
    )

    target_field = "canonical_serialization"
    examples, excluded = composition_baseline_examples(
        rows, assignments, target_field
    )
    train_targets = [
        example["target"] for example in examples if example["split"] == "train"
    ]
    if not train_targets:
        raise ValueError("composition baseline report requires train exact targets")

    majority_prediction = _majority_label(train_targets)
    material_predictions = composition_material_feature_predictions(
        examples, majority_prediction
    )
    fixture_predictions = [
        fixture_component_sum_prediction(example["row"]) for example in examples
    ]
    component_sum_rule_counts = composition_value_rule_counts(examples)

    split_metadata.update(
        {
            "baseline_id": "composition_exact_result_baselines_v0",
            "target": f"exact.value.{target_field}",
            "eligible_label_kinds": ["exact"],
            "holdout_selector": holdout_selector,
            "holdout_value": str(holdout_value),
            "holdout_label_kind": "exact",
            "exact_target_counts_by_split": _nested_count_by(
                examples, "split", "target"
            ),
            "target_support": composition_target_support_report(examples),
            "component_topology_family_diagnostics": (
                composition_topology_family_diagnostics(examples)
            ),
            "excluded_from_target_metrics": excluded,
            "predictors": {
                "train_majority": composition_predictor_report(
                    examples,
                    [majority_prediction for _example in examples],
                    {
                        "baseline_id": "composition_train_majority_exact_result_v0",
                        "description": (
                            "Predicts the most common exact target among exact train rows."
                        ),
                        "uses_decomposition_metadata": False,
                        "train_majority_prediction": majority_prediction,
                    },
                ),
                "fen_material_feature_majority": composition_predictor_report(
                    examples,
                    material_predictions,
                    {
                        "baseline_id": (
                            "composition_fen_material_feature_majority_v0"
                        ),
                        "description": (
                            "Uses deterministic FEN material/count features from "
                            "exact train rows, falling back to train_majority."
                        ),
                        "uses_decomposition_metadata": False,
                        "fallback_prediction": majority_prediction,
                    },
                ),
                "fixture_component_sum": composition_predictor_report(
                    examples,
                    fixture_predictions,
                    {
                        "baseline_id": "fixture_component_integer_sum_v0",
                        "description": (
                            "Parses exact.value.component_values summaries and "
                            "sums integer component values. fixture_only is true "
                            "only when all scored rows use the fixture index-sum "
                            "composition rule. This is not evidence of learned "
                            "decomposition."
                        ),
                        "uses_decomposition_metadata": True,
                        "composition_value_rule_counts": component_sum_rule_counts,
                        "fixture_only": set(component_sum_rule_counts)
                        <= {FIXTURE_COMPONENT_SUM_RULE},
                        "verifier_sanity_check": True,
                    },
                ),
            },
        }
    )
    return split_metadata


def evaluate_composition_topology_benchmark_report(
    jsonl_path: str | Path,
    split_key_mode: str = "position",
    min_family_support: int = 1,
) -> dict[str, Any]:
    """Run composition topology-family holdout baselines for every eligible family."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    families = composition_topology_families(rows, min_family_support)
    family_reports = []
    for family in families:
        baseline_report = evaluate_composition_baseline_report(
            path,
            "component_topology_family",
            family,
            split_key_mode=split_key_mode,
        )
        family_reports.append(
            composition_topology_family_benchmark_summary(family, baseline_report)
        )

    leakage_checks = composition_topology_benchmark_leakage_checks(family_reports)
    predictor_names = sorted(
        {
            predictor_name
            for family_report in family_reports
            for predictor_name in family_report["predictors"]
        }
    )
    return {
        "benchmark_id": "composition_topology_family_holdout_benchmark_v0",
        "dataset_path": str(path),
        "dataset_sha256": _sha256_file(path),
        "schema_version": SCHEMA_VERSION,
        "split_key_mode": split_key_mode,
        "holdout_selector": "component_topology_family",
        "min_family_support": min_family_support,
        "family_count": len(families),
        "families": families,
        "leakage_gate_passed": leakage_checks["family_leakage_gate_failures"][
            "violation_count"
        ]
        == 0,
        "leakage_checks": leakage_checks,
        "family_reports": family_reports,
        "predictor_accuracy_by_family": {
            predictor_name: {
                family_report["holdout_value"]: family_report["predictors"][
                    predictor_name
                ]["accuracy"]
                for family_report in family_reports
                if predictor_name in family_report["predictors"]
            }
            for predictor_name in predictor_names
        },
    }


def composition_topology_benchmark_leakage_checks(
    family_reports: list[dict[str, Any]]
) -> dict[str, Any]:
    failing_reports = [
        family_report
        for family_report in family_reports
        if family_report["leakage_violations"]
    ]
    return {
        "family_leakage_gate_failures": {
            "violation_count": len(failing_reports),
            "examples": [
                {
                    "holdout_value": family_report["holdout_value"],
                    "leakage_violations": family_report["leakage_violations"],
                }
                for family_report in failing_reports[:5]
            ],
        }
    }


def composition_topology_families(
    rows: list[dict[str, Any]], min_family_support: int
) -> list[str]:
    if min_family_support < 1:
        raise ValueError("min_family_support must be >= 1")
    counts = Counter(
        family
        for row in rows
        if row.get("label_kind") == "exact"
        if (family := composition_topology_family(row)) is not None
    )
    return [
        family
        for family, count in sorted(counts.items())
        if count >= min_family_support
    ]


def composition_topology_family_benchmark_summary(
    family: str, baseline_report: dict[str, Any]
) -> dict[str, Any]:
    leakage_violations = leakage_report_violations(baseline_report)
    diagnostics = baseline_report["component_topology_family_diagnostics"].get(
        family, {}
    )
    return {
        "holdout_value": family,
        "row_counts": baseline_report["row_counts"],
        "label_kind_counts": baseline_report["label_kind_counts"],
        "leakage_gate_passed": not leakage_violations,
        "leakage_violations": leakage_violations,
        "holdout_support": diagnostics.get("support", 0),
        "holdout_split_counts": diagnostics.get("split_counts", {}),
        "holdout_target_counts": diagnostics.get("target_counts", {}),
        "holdout_local_move_totals": diagnostics.get("local_move_totals", {}),
        "holdout_local_move_imbalance": diagnostics.get(
            "local_move_imbalance", {}
        ),
        "holdout_recursive_total_nodes": diagnostics.get(
            "recursive_total_nodes", {}
        ),
        "unseen_test_labels": baseline_report["target_support"][
            "unseen_labels_by_split"
        ].get("test", []),
        "predictors": {
            predictor_name: {
                "accuracy": metrics["accuracy"],
                "support": metrics["support"],
                "abstention_count": metrics["abstention_count"],
                "prediction_counts": metrics["prediction_counts"],
            }
            for predictor_name, predictor_report in baseline_report[
                "predictors"
            ].items()
            if (
                metrics := predictor_report[
                    "component_topology_family_metrics"
                ].get(family)
            )
            is not None
        },
    }


def composition_target_support_report(examples: list[dict[str, Any]]) -> dict[str, Any]:
    train_target_labels = {
        str(example["target"]) for example in examples if example["split"] == "train"
    }
    split_target_labels: dict[str, set[str]] = {}
    for example in examples:
        split_target_labels.setdefault(str(example["split"]), set()).add(
            str(example["target"])
        )

    return {
        "train_labels": sorted(train_target_labels),
        "labels_by_split": {
            split: sorted(labels) for split, labels in sorted(split_target_labels.items())
        },
        "unseen_labels_by_split": {
            split: sorted(labels - train_target_labels)
            for split, labels in sorted(split_target_labels.items())
        },
    }


def composition_topology_family_diagnostics(
    examples: list[dict[str, Any]]
) -> dict[str, Any]:
    diagnostics = {}
    for family in sorted({example["component_topology_family"] for example in examples}):
        family_examples = [
            example
            for example in examples
            if example["component_topology_family"] == family
        ]
        white_moves = [
            totals["white"]
            for example in family_examples
            if (totals := example["component_local_move_totals"]) is not None
        ]
        black_moves = [
            totals["black"]
            for example in family_examples
            if (totals := example["component_local_move_totals"]) is not None
        ]
        imbalances = [
            imbalance
            for example in family_examples
            if (imbalance := example["component_local_move_imbalance"]) is not None
        ]
        recursive_nodes = [
            nodes
            for example in family_examples
            if (nodes := example["component_recursive_total_nodes"]) is not None
        ]
        diagnostics[family] = {
            "support": len(family_examples),
            "split_counts": _count_by(family_examples, "split"),
            "target_counts": dict(
                sorted(Counter(example["target"] for example in family_examples).items())
            ),
            "composition_value_rule_counts": _count_by(
                family_examples, "composition_value_rule"
            ),
            "local_move_totals": {
                "white": numeric_summary(white_moves),
                "black": numeric_summary(black_moves),
            },
            "local_move_imbalance": numeric_summary(imbalances),
            "recursive_total_nodes": numeric_summary(recursive_nodes),
        }
    return diagnostics


def numeric_summary(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
    }


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


GEOMETRY_PROBE_FEATURE_NAMES = (
    "bias",
    "white_king_row",
    "white_king_col",
    "black_king_row",
    "black_king_col",
    "attacker_row",
    "attacker_col",
    "white_black_chebyshev_distance",
    "attacker_black_chebyshev_distance",
    "white_attacker_chebyshev_distance",
    "white_black_manhattan_distance",
    "attacker_black_manhattan_distance",
    "black_king_on_edge",
    "black_king_in_corner",
    "attacker_same_rank_as_black_king",
    "attacker_same_file_as_black_king",
    "attacker_same_diagonal_as_black_king",
    "attacker_attacks_black_king",
    "attacker_piece_value",
    "attacker_is_queen",
    "attacker_is_rook",
    "attacker_is_bishop",
    "attacker_is_knight",
    "attacker_is_pawn",
)


def evaluate_geometry_probe_report(
    jsonl_path: str | Path,
    split_key_mode: str = "position",
    holdout_family: str | None = None,
    epochs: int = 2_000,
    learning_rate: float = 0.05,
    l2: float = 0.001,
) -> dict[str, Any]:
    """Train a small deterministic FEN-geometry logistic probe per split."""

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

    examples = geometry_probe_examples(rows, assignments)
    train_examples = [example for example in examples if example["split"] == "train"]
    if not train_examples:
        raise ValueError("geometry probe requires at least one train example")

    model = train_geometry_logistic_probe(
        [example["features"] for example in train_examples],
        [example["target"] for example in train_examples],
        epochs=epochs,
        learning_rate=learning_rate,
        l2=l2,
    )

    split_metrics = {}
    for split in sorted({example["split"] for example in examples}):
        split_examples = [example for example in examples if example["split"] == split]
        targets = [
            "exact" if example["target"] == 1 else "rejected"
            for example in split_examples
        ]
        probabilities = [
            geometry_probe_probability(model, example["features"])
            for example in split_examples
        ]
        predictions = [
            "exact" if probability >= 0.5 else "rejected"
            for probability in probabilities
        ]
        split_metrics[split] = {
            "support": len(split_examples),
            "target_counts": dict(sorted(Counter(targets).items())),
            "prediction_counts": dict(sorted(Counter(predictions).items())),
            "mean_exact_probability": (
                sum(probabilities) / len(probabilities) if probabilities else 0.0
            ),
            "brier_score": brier_score(
                [example["target"] for example in split_examples],
                probabilities,
            ),
            **_classification_metrics(targets, predictions, EXACT_REJECTED_LABELS),
        }

    report: dict[str, Any] = {
        "dataset_path": str(path),
        "dataset_sha256": _sha256_file(path),
        "schema_version": SCHEMA_VERSION,
        "baseline_id": "fen_geometry_logistic_probe_v0",
        "target": "label_kind exact-vs-rejected",
        "eligible_label_kinds": list(EXACT_REJECTED_LABELS),
        "included_position_encoding": FEN_GATE_POSITION_ENCODING,
        "splitter_id": splitter_id,
        "split_policy": split_policy,
        "row_counts": _count_by(assignments, "split"),
        "feature_names": list(GEOMETRY_PROBE_FEATURE_NAMES),
        "training": {
            "train_split": "train",
            "epochs": epochs,
            "learning_rate": learning_rate,
            "l2": l2,
            "optimizer": "full_batch_gradient_descent",
            "threshold": 0.5,
            "standardization": "train_split_mean_std_except_bias",
        },
        "split_metrics": split_metrics,
    }
    if holdout_family:
        report["holdout_family"] = holdout_family
    return report


def evaluate_frontier_target_report(
    jsonl_path: str | Path,
    target_field: str,
    split_key_mode: str = "position",
    holdout_family: str | None = None,
) -> dict[str, Any]:
    """Evaluate exact-only frontier metadata targets with a train majority floor."""

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

    examples = frontier_target_examples(rows, assignments, target_field)
    train_targets = [
        example["target"] for example in examples if example["split"] == "train"
    ]
    if not train_targets:
        raise ValueError("frontier target report requires train exact targets")
    majority_prediction = _majority_label(train_targets)
    labels = tuple(sorted({example["target"] for example in examples}))
    train_target_labels = set(train_targets)
    split_target_labels = {
        split: {
            example["target"]
            for example in examples
            if example["split"] == split
        }
        for split in sorted({example["split"] for example in examples})
    }

    split_metrics = {}
    for split in sorted({example["split"] for example in examples}):
        split_targets = [
            example["target"] for example in examples if example["split"] == split
        ]
        predictions = [majority_prediction for _target in split_targets]
        split_metrics[split] = {
            "support": len(split_targets),
            "target_counts": dict(sorted(Counter(split_targets).items())),
            "prediction_counts": dict(sorted(Counter(predictions).items())),
            **_classification_metrics(split_targets, predictions, labels),
        }

    report: dict[str, Any] = {
        "dataset_path": str(path),
        "dataset_sha256": _sha256_file(path),
        "schema_version": SCHEMA_VERSION,
        "baseline_id": "exact_train_majority_frontier_target_v0",
        "target": f"exact.value.{target_field}",
        "eligible_label_kinds": ["exact"],
        "splitter_id": splitter_id,
        "split_policy": split_policy,
        "row_counts": _count_by(assignments, "split"),
        "target_labels": list(labels),
        "train_majority_prediction": majority_prediction,
        "target_support_coverage": {
            "train_labels": sorted(train_target_labels),
            "split_labels": {
                split: sorted(targets)
                for split, targets in split_target_labels.items()
            },
            "unseen_labels_by_split": {
                split: sorted(targets - train_target_labels)
                for split, targets in split_target_labels.items()
            },
        },
        "split_metrics": split_metrics,
    }
    if holdout_family:
        report["holdout_family"] = holdout_family
    return report


def frontier_target_examples(
    rows: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    target_field: str,
) -> list[dict[str, str]]:
    examples = []
    for row, assignment in zip(rows, assignments):
        if row.get("label_kind") != "exact":
            continue
        exact = row.get("exact", {})
        value = exact.get("value", {}) if isinstance(exact, dict) else {}
        target = value.get(target_field) if isinstance(value, dict) else None
        if target is None:
            continue
        examples.append({"split": assignment["split"], "target": str(target)})
    return examples


def composition_baseline_examples(
    rows: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    target_field: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    examples: list[dict[str, Any]] = []
    non_exact_by_split: Counter[str] = Counter()
    missing_target_by_split: Counter[str] = Counter()

    for row, assignment in zip(rows, assignments):
        split = str(assignment["split"])
        if row.get("label_kind") != "exact":
            non_exact_by_split[split] += 1
            continue

        target = exact_result_target(row, target_field)
        if target is None:
            missing_target_by_split[split] += 1
            continue

        exact_value = exact_value_payload(row)
        features = derive_position_features(row)
        examples.append(
            {
                "row": row,
                "row_id": str(row.get("row_id")),
                "split": split,
                "target": target,
                "fen_material_feature_key": fen_material_feature_key(features),
                "component_topology_family": composition_topology_family(row)
                or MISSING_COMPONENT_TOPOLOGY_FAMILY,
                "composition_value_rule": composition_value_rule(row)
                or MISSING_COMPOSITION_VALUE_RULE,
                "component_local_move_totals": parse_component_local_move_totals(
                    exact_value.get("component_local_move_totals")
                ),
                "component_local_move_imbalance": parse_int_metadata(
                    exact_value.get("component_local_move_imbalance")
                ),
                "component_recursive_total_nodes": parse_int_metadata(
                    exact_value.get("component_recursive_total_nodes")
                ),
            }
        )

    return examples, {
        "non_exact_rows_by_split": dict(sorted(non_exact_by_split.items())),
        "exact_rows_missing_target_by_split": dict(
            sorted(missing_target_by_split.items())
        ),
    }


def exact_result_target(row: dict[str, Any], target_field: str) -> str | None:
    exact_value = exact_value_payload(row)
    target = exact_value.get(target_field)
    if target is None:
        return None
    target_text = str(target)
    if not target_text:
        return None
    return target_text


def exact_value_payload(row: dict[str, Any]) -> dict[str, Any]:
    exact = row.get("exact")
    if not isinstance(exact, dict):
        return {}
    value = exact.get("value")
    if not isinstance(value, dict):
        return {}
    return value


def composition_value_rule(row: dict[str, Any]) -> str | None:
    rule = exact_value_payload(row).get("composition_value_rule")
    if not isinstance(rule, str):
        return None
    rule = rule.strip()
    return rule or None


def composition_topology_family(row: dict[str, Any]) -> str | None:
    family = exact_value_payload(row).get("component_topology_family")
    if not isinstance(family, str):
        return None
    family = family.strip()
    return family or None


def parse_int_metadata(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_component_local_move_totals(value: Any) -> dict[str, int] | None:
    if not isinstance(value, str):
        return None
    totals: dict[str, int] = {}
    for part in value.split(","):
        if ":" not in part:
            return None
        side, count_text = part.split(":", 1)
        side = side.strip()
        if side not in {"white", "black"}:
            return None
        count = parse_int_metadata(count_text)
        if count is None:
            return None
        totals[side] = count
    if set(totals) != {"white", "black"}:
        return None
    return totals


def composition_value_rule_counts(examples: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(
        composition_value_rule(example["row"]) or MISSING_COMPOSITION_VALUE_RULE
        for example in examples
    )
    return dict(sorted(counts.items()))


def fen_material_feature_key(features: dict[str, Any]) -> str:
    if features["position_encoding"] != FEN_GATE_POSITION_ENCODING:
        return f"{features['position_encoding']}:non_fen"

    signature = {
        "position_encoding": features["position_encoding"],
        "side_to_move": features["side_to_move"],
        "piece_counts": features["piece_counts"],
        "piece_count": features["piece_count"],
        "white_piece_count": features["white_piece_count"],
        "black_piece_count": features["black_piece_count"],
        "material_balance": features["material_balance"],
        "absolute_material": features["absolute_material"],
    }
    return json.dumps(signature, sort_keys=True, separators=(",", ":"))


def composition_material_feature_predictions(
    examples: list[dict[str, Any]], fallback_prediction: str
) -> list[str]:
    train_targets_by_key: dict[str, list[str]] = {}
    for example in examples:
        if example["split"] != "train":
            continue
        train_targets_by_key.setdefault(
            example["fen_material_feature_key"], []
        ).append(example["target"])

    predictions = []
    for example in examples:
        matching_train_targets = train_targets_by_key.get(
            example["fen_material_feature_key"], []
        )
        if matching_train_targets:
            predictions.append(_majority_label(matching_train_targets))
        else:
            predictions.append(fallback_prediction)
    return predictions


def fixture_component_sum_prediction(row: dict[str, Any]) -> str | None:
    exact_value = exact_value_payload(row)
    component_sum = fixture_component_integer_sum(
        exact_value.get("component_values")
    )
    if component_sum is None:
        return None
    return f"Number({component_sum}/2^0)"


def fixture_component_integer_sum(component_values_summary: Any) -> int | None:
    if not isinstance(component_values_summary, str):
        return None

    total = 0
    saw_component = False
    for component_summary in component_values_summary.split(","):
        component_summary = component_summary.strip()
        if not component_summary or "=" not in component_summary:
            return None
        _component_root, component_value = component_summary.split("=", 1)
        integer_value = parse_fixture_integer_number(component_value.strip())
        if integer_value is None:
            return None
        total += integer_value
        saw_component = True

    return total if saw_component else None


def parse_fixture_integer_number(value_text: str) -> int | None:
    if not value_text.startswith("Number(") or not value_text.endswith(")"):
        return None

    inner = value_text[len("Number("):-1].strip()
    if "/2^" in inner:
        numerator_text, denominator_power_text = inner.split("/2^", 1)
        if denominator_power_text.strip() != "0":
            return None
    else:
        numerator_text = inner

    try:
        return int(numerator_text.strip())
    except ValueError:
        return None


def composition_predictor_report(
    examples: list[dict[str, Any]],
    raw_predictions: list[str | None],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    predictions = [
        prediction if prediction is not None else "__abstained__"
        for prediction in raw_predictions
    ]
    targets = [example["target"] for example in examples]

    report = dict(metadata)
    report.update(
        {
            "support": len(examples),
            "target_counts": dict(sorted(Counter(targets).items())),
            "prediction_counts": dict(sorted(Counter(predictions).items())),
            "abstention_count": sum(
                1 for prediction in raw_predictions if prediction is None
            ),
            **composition_exact_result_metrics(targets, predictions),
            "split_metrics": {},
            "component_topology_family_metrics": (
                composition_predictor_group_metrics(
                    examples,
                    predictions,
                    raw_predictions,
                    "component_topology_family",
                )
            ),
        }
    )

    for split in sorted({example["split"] for example in examples}):
        split_targets = [
            target
            for target, example in zip(targets, examples)
            if example["split"] == split
        ]
        split_predictions = [
            prediction
            for prediction, example in zip(predictions, examples)
            if example["split"] == split
        ]
        split_raw_predictions = [
            prediction
            for prediction, example in zip(raw_predictions, examples)
            if example["split"] == split
        ]
        report["split_metrics"][split] = {
            "support": len(split_targets),
            "target_counts": dict(sorted(Counter(split_targets).items())),
            "prediction_counts": dict(sorted(Counter(split_predictions).items())),
            "abstention_count": sum(
                1 for prediction in split_raw_predictions if prediction is None
            ),
            **composition_exact_result_metrics(split_targets, split_predictions),
        }

    return report


def composition_predictor_group_metrics(
    examples: list[dict[str, Any]],
    predictions: list[str],
    raw_predictions: list[str | None],
    group_field: str,
) -> dict[str, Any]:
    metrics = {}
    for group in sorted({example[group_field] for example in examples}):
        group_targets = [
            example["target"]
            for example in examples
            if example[group_field] == group
        ]
        group_predictions = [
            prediction
            for prediction, example in zip(predictions, examples)
            if example[group_field] == group
        ]
        group_raw_predictions = [
            prediction
            for prediction, example in zip(raw_predictions, examples)
            if example[group_field] == group
        ]
        metrics[group] = {
            "support": len(group_targets),
            "split_counts": _count_by(
                [
                    example
                    for example in examples
                    if example[group_field] == group
                ],
                "split",
            ),
            "target_counts": dict(sorted(Counter(group_targets).items())),
            "prediction_counts": dict(sorted(Counter(group_predictions).items())),
            "abstention_count": sum(
                1 for prediction in group_raw_predictions if prediction is None
            ),
            **composition_exact_result_metrics(group_targets, group_predictions),
        }
    return metrics


def geometry_probe_examples(
    rows: list[dict[str, Any]], assignments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    examples = []
    for row, assignment in zip(rows, assignments):
        if row.get("label_kind") not in EXACT_REJECTED_LABELS:
            continue
        if row["position"]["encoding"] != FEN_GATE_POSITION_ENCODING:
            continue
        features = fen_geometry_features(row["position"]["text"])
        if features is None:
            continue
        examples.append(
            {
                "split": assignment["split"],
                "features": features,
                "target": 1 if row["label_kind"] == "exact" else 0,
            }
        )
    return examples


def fen_geometry_features(fen: str) -> list[float] | None:
    board = expand_fen_board(fen.split()[0]) if fen.split() else None
    if board is None:
        return None

    piece_squares = piece_squares_from_board(board)
    white_king = first_square(piece_squares, "K")
    black_king = first_square(piece_squares, "k")
    attacker_piece, attacker_square = first_white_attacker(piece_squares)
    if white_king is None or black_king is None or attacker_square is None:
        return None

    white_black_chebyshev = chebyshev_distance(white_king, black_king)
    attacker_black_chebyshev = chebyshev_distance(attacker_square, black_king)
    white_attacker_chebyshev = chebyshev_distance(white_king, attacker_square)
    white_black_manhattan = manhattan_distance(white_king, black_king)
    attacker_black_manhattan = manhattan_distance(attacker_square, black_king)
    black_row, black_col = black_king
    attacker_row, attacker_col = attacker_square
    piece_value = PIECE_VALUES.get(attacker_piece, 0)

    return [
        1.0,
        white_king[0] / 7,
        white_king[1] / 7,
        black_king[0] / 7,
        black_king[1] / 7,
        attacker_row / 7,
        attacker_col / 7,
        white_black_chebyshev / 7,
        attacker_black_chebyshev / 7,
        white_attacker_chebyshev / 7,
        white_black_manhattan / 14,
        attacker_black_manhattan / 14,
        float(black_row in {0, 7} or black_col in {0, 7}),
        float(black_row in {0, 7} and black_col in {0, 7}),
        float(attacker_row == black_row),
        float(attacker_col == black_col),
        float(abs(attacker_row - black_row) == abs(attacker_col - black_col)),
        float(attacker_attacks_square(attacker_piece, attacker_square, black_king)),
        piece_value / 9,
        float(attacker_piece == "Q"),
        float(attacker_piece == "R"),
        float(attacker_piece == "B"),
        float(attacker_piece == "N"),
        float(attacker_piece == "P"),
    ]


def piece_squares_from_board(board: list[list[str]]) -> dict[str, list[tuple[int, int]]]:
    squares: dict[str, list[tuple[int, int]]] = {}
    for row_index, row in enumerate(board):
        for col_index, piece in enumerate(row):
            if piece != ".":
                squares.setdefault(piece, []).append((row_index, col_index))
    return squares


def first_square(
    piece_squares: dict[str, list[tuple[int, int]]], piece: str
) -> tuple[int, int] | None:
    squares = piece_squares.get(piece)
    if not squares:
        return None
    return sorted(squares)[0]


def first_white_attacker(
    piece_squares: dict[str, list[tuple[int, int]]]
) -> tuple[str, tuple[int, int] | None]:
    for piece in ("Q", "R", "B", "N", "P"):
        squares = piece_squares.get(piece)
        if squares:
            return piece, sorted(squares)[0]
    return "?", None


def chebyshev_distance(left: tuple[int, int], right: tuple[int, int]) -> int:
    return max(abs(left[0] - right[0]), abs(left[1] - right[1]))


def manhattan_distance(left: tuple[int, int], right: tuple[int, int]) -> int:
    return abs(left[0] - right[0]) + abs(left[1] - right[1])


def attacker_attacks_square(
    piece: str, attacker_square: tuple[int, int], target_square: tuple[int, int]
) -> bool:
    row_delta = target_square[0] - attacker_square[0]
    col_delta = target_square[1] - attacker_square[1]
    abs_delta = sorted((abs(row_delta), abs(col_delta)))
    if piece == "Q":
        return (
            row_delta == 0
            or col_delta == 0
            or abs(row_delta) == abs(col_delta)
        )
    if piece == "R":
        return row_delta == 0 or col_delta == 0
    if piece == "B":
        return abs(row_delta) == abs(col_delta)
    if piece == "N":
        return abs_delta == [1, 2]
    if piece == "P":
        return row_delta == -1 and abs(col_delta) == 1
    return False


def train_geometry_logistic_probe(
    features: list[list[float]],
    targets: list[int],
    epochs: int,
    learning_rate: float,
    l2: float,
) -> dict[str, Any]:
    feature_count = len(features[0])
    means = [0.0] * feature_count
    scales = [1.0] * feature_count
    for index in range(1, feature_count):
        means[index] = sum(vector[index] for vector in features) / len(features)
        variance = sum(
            (vector[index] - means[index]) ** 2 for vector in features
        ) / len(features)
        scales[index] = variance ** 0.5 or 1.0

    scaled_features = [
        scale_geometry_features(vector, means, scales) for vector in features
    ]
    weights = [0.0] * feature_count
    for _epoch in range(epochs):
        gradients = [0.0] * feature_count
        for vector, target in zip(scaled_features, targets):
            probability = sigmoid(sum(weight * value for weight, value in zip(weights, vector)))
            error = probability - target
            for index, value in enumerate(vector):
                gradients[index] += error * value
        for index in range(feature_count):
            regularization = 0.0 if index == 0 else l2 * weights[index]
            weights[index] -= learning_rate * (
                gradients[index] / len(scaled_features) + regularization
            )

    return {
        "weights": weights,
        "means": means,
        "scales": scales,
    }


def geometry_probe_probability(model: dict[str, Any], features: list[float]) -> float:
    scaled = scale_geometry_features(features, model["means"], model["scales"])
    return sigmoid(
        sum(weight * value for weight, value in zip(model["weights"], scaled))
    )


def scale_geometry_features(
    features: list[float], means: list[float], scales: list[float]
) -> list[float]:
    return [
        features[0],
        *[
            (features[index] - means[index]) / scales[index]
            for index in range(1, len(features))
        ],
    ]


def sigmoid(value: float) -> float:
    bounded = max(-40.0, min(40.0, value))
    return 1 / (1 + pow(2.718281828459045, -bounded))


def brier_score(targets: list[int], probabilities: list[float]) -> float:
    if not targets:
        return 0.0
    return sum(
        (probability - target) ** 2
        for target, probability in zip(targets, probabilities)
    ) / len(targets)


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


def composition_holdout_assignments_for_rows(
    rows: list[dict[str, Any]],
    holdout_selector: str,
    holdout_value: Any,
    split_key_mode: str,
) -> list[dict[str, Any]]:
    if holdout_selector not in COMPOSITION_HOLDOUT_SELECTORS:
        raise ValueError(f"unsupported composition holdout selector {holdout_selector!r}")

    target_value = str(holdout_value)
    assignments = []
    for row in rows:
        family = generator_family(row)
        position_key = position_key_for_row(row)
        symmetry_position_key = symmetry_position_key_for_row(row)
        split_key = split_key_for_mode(
            family, position_key, symmetry_position_key, split_key_mode
        )
        composition_metadata = composition_certificate_metadata(row)
        selector_value = composition_holdout_value(row, composition_metadata, holdout_selector)
        if row.get("label_kind") == "exact" and selector_value == target_value:
            split = "test"
        else:
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
    composition_metadata = composition_certificate_metadata(row)
    return {
        "row_id": str(row.get("row_id")),
        "label_kind": str(row.get("label_kind")),
        "split": split,
        "generator_family": family,
        "position_key": position_key,
        "symmetry_position_key": symmetry_position_key,
        "split_key": split_key,
        "exact_certificate_digest": exact_certificate_digest(row),
        "decomposition_digest": composition_metadata["decomposition_digest"],
        "composition_digest": composition_metadata["composition_digest"],
        "component_count": composition_metadata["component_count"],
        "component_family": composition_metadata["component_family"],
        "component_roots": composition_metadata["component_roots"],
        "component_value_digests": composition_metadata["component_value_digests"],
        "component_values": composition_metadata["component_values"],
        "result_value_digest": composition_metadata["result_value_digest"],
        "component_topology_family": _optional_non_empty_str(
            exact_value.get("component_topology_family")
        ),
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
    composition_assignments = [
        item for item in assignments if item_has_composition_certificate_metadata(item)
    ]
    component_value_items = composition_component_value_items(composition_assignments)
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
        "component_topology_family_counts": _nested_count_by(
            assignments, "split", "component_topology_family"
        ),
        "frontier_value_class_counts": _nested_count_by(
            assignments, "split", "frontier_value_class"
        ),
        "composition_certificate_counts": {
            "rows_by_split": _count_by(composition_assignments, "split"),
            "component_count_by_split": _nested_count_by(
                composition_assignments, "split", "component_count"
            ),
            "component_family_by_split": _nested_count_by(
                composition_assignments, "split", "component_family"
            ),
            "component_root_counts_by_split": _nested_count_by(
                component_value_items, "split", "component_root"
            ),
            "component_value_digest_counts_by_split": _nested_count_by(
                component_value_items, "split", "component_value_digest"
            ),
        },
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
            "duplicate_decomposition_digests": duplicate_total(
                Counter(
                    item["decomposition_digest"]
                    for item in assignments
                    if item["decomposition_digest"]
                )
            ),
            "duplicate_composition_digests": duplicate_total(
                Counter(
                    item["composition_digest"]
                    for item in assignments
                    if item["composition_digest"]
                )
            ),
            "duplicate_component_roots": duplicate_total(
                Counter(item["component_identity"] for item in component_value_items)
            ),
            "duplicate_component_value_digests": duplicate_total(
                Counter(
                    item["component_value_digest"] for item in component_value_items
                )
            ),
            "duplicate_component_value_pairs": duplicate_total(
                Counter(
                    item["component_value_identity"] for item in component_value_items
                )
            ),
            "duplicate_result_value_digests": duplicate_total(
                Counter(
                    item["result_value_digest"]
                    for item in assignments
                    if item["result_value_digest"]
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
            "decomposition_digest_cross_split": cross_split_summary(
                [
                    item
                    for item in assignments
                    if item["decomposition_digest"]
                ],
                "decomposition_digest",
            ),
            "composition_digest_cross_split": cross_split_summary(
                [
                    item
                    for item in assignments
                    if item["composition_digest"]
                ],
                "composition_digest",
            ),
            "component_root_cross_split": cross_split_summary(
                component_value_items,
                "component_identity",
            ),
            "component_value_digest_cross_split": cross_split_summary(
                component_value_items,
                "component_value_digest",
            ),
            "component_value_pair_cross_split": cross_split_summary(
                component_value_items,
                "component_value_identity",
            ),
            "result_value_digest_cross_split": cross_split_summary(
                [
                    item
                    for item in assignments
                    if item["result_value_digest"]
                ],
                "result_value_digest",
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
    if row_id.startswith("astralbase-w12-kbk-frontier-"):
        return "astralbase_kbk_frontier_generator"
    if row_id.startswith("astralbase-w12-knk-frontier-"):
        return "astralbase_knk_frontier_generator"
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


def composition_holdout_report_id_for_mode(
    split_key_mode: str, holdout_selector: str
) -> str:
    if holdout_selector not in COMPOSITION_HOLDOUT_SELECTORS:
        raise ValueError(f"unsupported composition holdout selector {holdout_selector!r}")
    if split_key_mode == "position":
        return f"composition_holdout_{holdout_selector}_generator_position_hash_v0"
    if split_key_mode == "symmetry":
        return f"composition_holdout_{holdout_selector}_generator_symmetry_hash_v0"
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


def composition_holdout_policy_for_mode(
    split_key_mode: str,
    holdout_selector: str,
    holdout_value: Any,
) -> dict[str, str]:
    if holdout_selector not in COMPOSITION_HOLDOUT_SELECTORS:
        raise ValueError(f"unsupported composition holdout selector {holdout_selector!r}")

    base_policy = split_policy_for_mode(split_key_mode, family_holdout=False)
    return {
        "train": (
            "not (label_kind == exact and composition_holdout."
            f"{holdout_selector} == holdout_value) "
            "and sha256(split_key) % 100 < 90"
        ),
        "dev": (
            "not (label_kind == exact and composition_holdout."
            f"{holdout_selector} == holdout_value) "
            "and sha256(split_key) % 100 >= 90"
        ),
        "test": (
            "label_kind == exact and composition_holdout."
            f"{holdout_selector} == holdout_value"
        ),
        "split_key": base_policy["split_key"],
        "holdout_selector": holdout_selector,
        "holdout_value": str(holdout_value),
        "holdout_label_kind": "exact",
    }


def exact_certificate_digest(row: dict[str, Any]) -> str | None:
    provenance = row.get("provenance")
    if not isinstance(provenance, dict):
        return None
    certificate = provenance.get("certificate")
    if not isinstance(certificate, dict) or not certificate.get("digest"):
        return None
    return str(certificate["digest"])


def composition_certificate_metadata(row: dict[str, Any]) -> dict[str, Any]:
    provenance = row.get("provenance")
    if not isinstance(provenance, dict):
        return empty_composition_certificate_metadata()
    certificate = provenance.get("certificate")
    if not isinstance(certificate, dict):
        return empty_composition_certificate_metadata()

    raw_component_values = certificate.get("component_values")
    component_values: dict[str, str] = {}
    if isinstance(raw_component_values, dict):
        for component_root, value_digest in raw_component_values.items():
            if component_root is None or value_digest is None:
                continue
            root_text = str(component_root)
            digest_text = str(value_digest)
            if root_text and digest_text:
                component_values[root_text] = digest_text
        component_values = dict(sorted(component_values.items()))

    component_value_digests = [
        value_digest for _component_root, value_digest in component_values.items()
    ]

    return {
        "decomposition_digest": _optional_non_empty_str(
            certificate.get("decomposition_digest")
        ),
        "composition_digest": _optional_non_empty_str(
            certificate.get("composition_digest")
        ),
        "component_count": len(component_values)
        if isinstance(raw_component_values, dict)
        else None,
        "component_family": composition_component_family(component_values)
        if isinstance(raw_component_values, dict)
        else None,
        "component_values": component_values,
        "component_roots": list(component_values),
        "component_value_digests": component_value_digests,
        "result_value_digest": _optional_non_empty_str(
            certificate.get("result_value_digest")
        ),
    }


def empty_composition_certificate_metadata() -> dict[str, Any]:
    return {
        "decomposition_digest": None,
        "composition_digest": None,
        "component_count": None,
        "component_family": None,
        "component_values": {},
        "component_roots": [],
        "component_value_digests": [],
        "result_value_digest": None,
    }


def composition_component_family(component_values: dict[str, str]) -> str | None:
    """Return a stable coarse family key for component-root topology."""

    if not component_values:
        return None
    roots = ",".join(component_values)
    return f"count:{len(component_values)}|roots:{roots}"


def composition_holdout_value(
    row: dict[str, Any],
    composition_metadata: dict[str, Any],
    holdout_selector: str,
) -> str | None:
    if holdout_selector not in COMPOSITION_HOLDOUT_SELECTORS:
        raise ValueError(f"unsupported composition holdout selector {holdout_selector!r}")
    if holdout_selector == "component_topology_family":
        return _optional_non_empty_str(
            exact_value_payload(row).get("component_topology_family")
        )
    value = composition_metadata.get(holdout_selector)
    if value is None:
        return None
    return str(value)


def _optional_non_empty_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    return text


def item_has_composition_certificate_metadata(item: dict[str, Any]) -> bool:
    return any(
        (
            item.get("decomposition_digest"),
            item.get("composition_digest"),
            item.get("component_values"),
            item.get("result_value_digest"),
        )
    )


def composition_component_value_items(
    assignments: list[dict[str, Any]]
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for assignment in assignments:
        component_values = assignment.get("component_values")
        if not isinstance(component_values, dict):
            continue
        decomposition_digest = str(assignment.get("decomposition_digest") or "")
        for component_root, value_digest in component_values.items():
            root_text = str(component_root)
            digest_text = str(value_digest)
            component_identity = f"{decomposition_digest}:{root_text}"
            items.append(
                {
                    "split": str(assignment["split"]),
                    "component_root": root_text,
                    "component_identity": component_identity,
                    "component_value_digest": digest_text,
                    "component_value_pair": f"{root_text}={digest_text}",
                    "component_value_identity": (
                        f"{component_identity}={digest_text}"
                    ),
                }
            )
    return items


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


def leakage_report_violations(report: dict[str, Any]) -> list[str]:
    """Return report leakage failures that should block benchmark promotion."""

    leakage_checks = report.get("leakage_checks")
    if not isinstance(leakage_checks, dict):
        return ["leakage_checks: missing or not an object"]

    violations: list[str] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            violation_count = value.get("violation_count")
            if isinstance(violation_count, int) and violation_count > 0:
                violations.append(f"{path}.violation_count={violation_count}")
            for key, nested_value in value.items():
                visit(nested_value, f"{path}.{key}")
            return

        key = path.rsplit(".", 1)[-1]
        if key.startswith("duplicate_") and isinstance(value, int) and value > 0:
            violations.append(f"{path}={value}")

    visit(leakage_checks, "leakage_checks")
    return violations


def report_passes_leakage_gate(report: dict[str, Any]) -> bool:
    return not leakage_report_violations(report)


def print_leakage_violations(violations: list[str]) -> None:
    for violation in violations:
        print(f"leakage violation: {violation}", file=sys.stderr)


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
    split_parser.add_argument(
        "--fail-on-leakage",
        action="store_true",
        help="Exit nonzero when leakage_checks contain duplicate or cross-split violations.",
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
    holdout_parser.add_argument(
        "--fail-on-leakage",
        action="store_true",
        help="Exit nonzero when leakage_checks contain duplicate or cross-split violations.",
    )

    composition_holdout_parser = subcommands.add_parser(
        "composition-holdout-report",
        help="Build an exact-composition-held-out split and leakage report.",
    )
    composition_holdout_parser.add_argument("jsonl_path", type=Path)
    composition_holdout_parser.add_argument(
        "--holdout-selector",
        choices=COMPOSITION_HOLDOUT_SELECTORS,
        required=True,
    )
    composition_holdout_parser.add_argument("--holdout-value", required=True)
    composition_holdout_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the holdout report JSON.",
    )
    composition_holdout_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for train/dev assignment.",
    )
    composition_holdout_parser.add_argument(
        "--fail-on-leakage",
        action="store_true",
        help="Exit nonzero when leakage_checks contain duplicate or cross-split violations.",
    )

    composition_baseline_parser = subcommands.add_parser(
        "composition-baseline-report",
        help="Score deterministic exact-result baselines on a composition holdout split.",
    )
    composition_baseline_parser.add_argument("jsonl_path", type=Path)
    composition_baseline_parser.add_argument(
        "--holdout-selector",
        choices=COMPOSITION_HOLDOUT_SELECTORS,
        required=True,
    )
    composition_baseline_parser.add_argument("--holdout-value", required=True)
    composition_baseline_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the baseline report JSON.",
    )
    composition_baseline_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for train/dev assignment.",
    )

    composition_topology_benchmark_parser = subcommands.add_parser(
        "composition-topology-benchmark-report",
        help="Run composition topology-family holdout baselines for every eligible family.",
    )
    composition_topology_benchmark_parser.add_argument("jsonl_path", type=Path)
    composition_topology_benchmark_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the benchmark report JSON.",
    )
    composition_topology_benchmark_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for train/dev assignment.",
    )
    composition_topology_benchmark_parser.add_argument(
        "--min-family-support",
        type=int,
        default=1,
        help="Minimum exact-row count required for a topology family benchmark.",
    )
    composition_topology_benchmark_parser.add_argument(
        "--fail-on-leakage",
        action="store_true",
        help="Exit nonzero when any per-family benchmark has leakage violations.",
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

    geometry_probe_parser = subcommands.add_parser(
        "geometry-probe-report",
        help="Train and score a deterministic FEN-geometry logistic probe.",
    )
    geometry_probe_parser.add_argument("jsonl_path", type=Path)
    geometry_probe_parser.add_argument(
        "--holdout-family",
        help="Optional generator family to hold out as the test split.",
    )
    geometry_probe_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for split assignment.",
    )
    geometry_probe_parser.add_argument("--epochs", type=int, default=2_000)
    geometry_probe_parser.add_argument("--learning-rate", type=float, default=0.05)
    geometry_probe_parser.add_argument("--l2", type=float, default=0.001)
    geometry_probe_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the probe report JSON.",
    )

    frontier_target_parser = subcommands.add_parser(
        "frontier-target-report",
        help="Evaluate exact-only frontier metadata targets per split.",
    )
    frontier_target_parser.add_argument("jsonl_path", type=Path)
    frontier_target_parser.add_argument("--target-field", required=True)
    frontier_target_parser.add_argument(
        "--holdout-family",
        help="Optional generator family to hold out as the test split.",
    )
    frontier_target_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for split assignment.",
    )
    frontier_target_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the frontier target report JSON.",
    )

    validate_report_parser = subcommands.add_parser(
        "validate-report",
        help="Validate a saved JSON report and optionally enforce leakage gates.",
    )
    validate_report_parser.add_argument("report_json_path", type=Path)
    validate_report_parser.add_argument(
        "--fail-on-leakage",
        action="store_true",
        help="Exit nonzero when leakage_checks contain duplicate or cross-split violations.",
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
        if args.fail_on_leakage:
            violations = leakage_report_violations(report)
            if violations:
                print_leakage_violations(violations)
                return 1
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
        if args.fail_on_leakage:
            violations = leakage_report_violations(report)
            if violations:
                print_leakage_violations(violations)
                return 1
        return 0
    if args.command == "composition-holdout-report":
        report = evaluate_composition_holdout_report_with_mode(
            args.jsonl_path,
            args.holdout_selector,
            args.holdout_value,
            args.split_key_mode,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print_json_report(report)
        if args.fail_on_leakage:
            violations = leakage_report_violations(report)
            if violations:
                print_leakage_violations(violations)
                return 1
        return 0
    if args.command == "composition-baseline-report":
        report = evaluate_composition_baseline_report(
            args.jsonl_path,
            args.holdout_selector,
            args.holdout_value,
            split_key_mode=args.split_key_mode,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
        )
        print_json_report(report)
        return 0
    if args.command == "composition-topology-benchmark-report":
        try:
            report = evaluate_composition_topology_benchmark_report(
                args.jsonl_path,
                split_key_mode=args.split_key_mode,
                min_family_support=args.min_family_support,
            )
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print_json_report(report)
        if args.fail_on_leakage and not report["leakage_gate_passed"]:
            for family_report in report["family_reports"]:
                if family_report["leakage_violations"]:
                    print(
                        f"leakage violation: holdout_value={family_report['holdout_value']}",
                        file=sys.stderr,
                    )
                    print_leakage_violations(
                        family_report["leakage_violations"]
                    )
            return 1
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
    if args.command == "geometry-probe-report":
        report = evaluate_geometry_probe_report(
            args.jsonl_path,
            split_key_mode=args.split_key_mode,
            holdout_family=args.holdout_family,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            l2=args.l2,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print_json_report(report)
        return 0
    if args.command == "frontier-target-report":
        report = evaluate_frontier_target_report(
            args.jsonl_path,
            args.target_field,
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

    if args.command == "validate-report":
        try:
            report = json.loads(args.report_json_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            print(f"report not found: {args.report_json_path}", file=sys.stderr)
            return 1
        except json.JSONDecodeError as error:
            print(
                f"{args.report_json_path}: invalid JSON: {error.msg}",
                file=sys.stderr,
            )
            return 1
        if not isinstance(report, dict):
            print(f"{args.report_json_path}: report must be a JSON object", file=sys.stderr)
            return 1

        violations = leakage_report_violations(report)
        if args.fail_on_leakage and violations:
            print_leakage_violations(violations)
            return 1
        if violations:
            print(
                f"report: ok ({len(violations)} leakage violation(s) present)",
                file=sys.stderr,
            )
        else:
            print("report: ok (no leakage violations)")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(cli_main())
