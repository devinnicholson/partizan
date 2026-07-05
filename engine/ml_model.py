#!/usr/bin/env python3
"""Partizan neural model utilities and tiny deterministic label baselines."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import hashlib
import json
import math
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
    "composition_spec_source",
    "composition_digest",
    "result_value_digest",
)
SUPPORTED_POSITION_ENCODINGS = {"fen", "cgt_canonical"}
FEN_GATE_POSITION_ENCODING = "fen"
HEURISTIC_SIGNATURE_TARGET_PROJECTIONS = (
    {
        "projection_id": "result_signature_key",
        "target": "heuristic.outputs.result_signature_key",
        "description": "Full diagnostic signature target key.",
    },
    {
        "projection_id": "component_topology_family",
        "target": "heuristic.outputs.component_topology_family",
        "description": "Generated depth-two topology family only.",
    },
    {
        "projection_id": "component_value_digest_pair",
        "target": "heuristic.outputs.left_component_value_digest + right_component_value_digest",
        "description": "Ordered pair of left and right component value digests.",
    },
    {
        "projection_id": "component_material_pair",
        "target": "material fields parsed from component signatures",
        "description": "Ordered pair of left and right component material balances.",
    },
    {
        "projection_id": "component_mobility_pair",
        "target": "moves fields parsed from component signatures",
        "description": "Ordered pair of left and right local move-count signatures.",
    },
    {
        "projection_id": "net_material_balance",
        "target": "sum of parsed component material fields",
        "description": "Net material balance after composing both components.",
    },
    {
        "projection_id": "topology_material_pair",
        "target": "component_topology_family + component_material_pair",
        "description": "Topology family joined with the component material pair.",
    },
    {
        "projection_id": "topology_mobility_pair",
        "target": "component_topology_family + component_mobility_pair",
        "description": "Topology family joined with the component mobility pair.",
    },
    {
        "projection_id": "topology_material_mobility_pair",
        "target": "component_topology_family + component_material_pair + component_mobility_pair",
        "description": "Topology family joined with component material and mobility signatures, excluding value digests.",
    },
)
EXACT_SIGNATURE_TARGET_PROJECTIONS = tuple(
    {
        **definition,
        "target": str(definition["target"]).replace("heuristic.outputs", "exact.value"),
    }
    for definition in HEURISTIC_SIGNATURE_TARGET_PROJECTIONS
)
DEFAULT_EXACT_PROJECTION_BASELINE_TARGETS = (
    "component_topology_family",
    "net_material_balance",
)
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
MISSING_COMPOSITION_SPEC_SOURCE = "__missing__"
SIGNATURE_PROFILE_CONTRACT_ID = "depth2_material_mobility_signature_target_contract_v0"
SIGNATURE_PROFILE_REQUIRED_FIELDS = (
    "source",
    "component_signature_rule",
    "rows_per_family_target",
    "left_signature_profile_count",
    "right_signature_profile_count",
    "candidate_pair_counts_by_topology_family",
    "selected_counts_by_topology_family",
    "selected_row_count",
    "rejection_counts",
    "candidates",
)
SIGNATURE_PROFILE_CANDIDATE_REQUIRED_FIELDS = (
    "row_number",
    "topology_family",
    "left_component_signature",
    "right_component_signature",
    "result_signature_key",
)
SIGNATURE_PROFILE_PROMOTION_BLOCKERS = (
    "versioned exact value rule is not defined",
    "replay-compatible provenance is not defined",
    "split and leakage semantics for the signature target are not defined",
    "deterministic floors and learned-model baselines are not implemented",
)
HEURISTIC_SIGNATURE_REQUIRED_OUTPUT_FIELDS = (
    "component_signature_rule",
    "component_topology_family",
    "composition_spec_source",
    "current_result_value_digest",
    "left_component_signature",
    "left_component_value_digest",
    "promotion_blockers",
    "result_signature_key",
    "right_component_signature",
    "right_component_value_digest",
    "supervision_eligible",
    "target_contract_id",
    "target_status",
)
HEURISTIC_SIGNATURE_PROMOTION_BLOCKER_IDS = (
    "versioned_exact_value_rule_missing",
    "replay_compatible_provenance_missing",
    "split_semantics_missing",
    "deterministic_and_model_baselines_missing",
)


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
        "holdout_spec_source_counts": diagnostics.get(
            "composition_spec_source_counts", {}
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
            "composition_spec_source_counts": _count_by(
                family_examples, "composition_spec_source"
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

FEN_MATERIAL_PROBE_FEATURE_NAMES = (
    "bias",
    "empty_square_count",
    "piece_count",
    "white_piece_count",
    "black_piece_count",
    "king_count",
    "queen_count",
    "rook_count",
    "bishop_count",
    "knight_count",
    "pawn_count",
    "material_balance",
    "absolute_material",
    "side_to_move_is_white",
)

SIGNATURE_METADATA_PROBE_FEATURE_NAMES = (
    *FEN_MATERIAL_PROBE_FEATURE_NAMES,
    "left_component_material",
    "right_component_material",
    "net_component_material",
    "left_white_local_moves",
    "left_black_local_moves",
    "right_white_local_moves",
    "right_black_local_moves",
    "total_white_local_moves",
    "total_black_local_moves",
    "component_local_move_imbalance",
    "component_recursive_total_nodes",
    "total_recursive_nodes",
    "left_profile_index",
    "right_profile_index",
)

COMPONENT_MATERIAL_ABLATION_FEATURE_NAMES = (
    "bias",
    "left_component_material",
    "right_component_material",
    "net_component_material",
)
COMPONENT_MOBILITY_ABLATION_FEATURE_NAMES = (
    "bias",
    "left_white_local_moves",
    "left_black_local_moves",
    "right_white_local_moves",
    "right_black_local_moves",
    "total_white_local_moves",
    "total_black_local_moves",
    "component_local_move_imbalance",
)
COMPONENT_NODES_ABLATION_FEATURE_NAMES = (
    "bias",
    "component_recursive_total_nodes",
    "total_recursive_nodes",
)
COMPONENT_PROFILE_INDEX_ABLATION_FEATURE_NAMES = (
    "bias",
    "left_profile_index",
    "right_profile_index",
)
COMPONENT_MATERIAL_MOBILITY_ABLATION_FEATURE_NAMES = (
    *COMPONENT_MATERIAL_ABLATION_FEATURE_NAMES,
    *COMPONENT_MOBILITY_ABLATION_FEATURE_NAMES[1:],
)
COMPONENT_METADATA_NO_FEN_NO_PROFILE_ABLATION_FEATURE_NAMES = (
    *COMPONENT_MATERIAL_MOBILITY_ABLATION_FEATURE_NAMES,
    *COMPONENT_NODES_ABLATION_FEATURE_NAMES[1:],
)
COMPONENT_METADATA_NO_FEN_FULL_ABLATION_FEATURE_NAMES = (
    *COMPONENT_METADATA_NO_FEN_NO_PROFILE_ABLATION_FEATURE_NAMES,
    *COMPONENT_PROFILE_INDEX_ABLATION_FEATURE_NAMES[1:],
)
SIGNATURE_METADATA_NO_PROFILE_ABLATION_FEATURE_NAMES = (
    *FEN_MATERIAL_PROBE_FEATURE_NAMES,
    *COMPONENT_METADATA_NO_FEN_NO_PROFILE_ABLATION_FEATURE_NAMES[1:],
)
EXACT_PROJECTION_ABLATION_FEATURE_GROUPS = (
    {
        "feature_group_id": "fen_material",
        "description": "Full-board FEN material/count control.",
        "control_scope": "board material control",
        "feature_names": FEN_MATERIAL_PROBE_FEATURE_NAMES,
    },
    {
        "feature_group_id": "component_material",
        "description": "Parsed component material balances only.",
        "control_scope": "component material ablation",
        "feature_names": COMPONENT_MATERIAL_ABLATION_FEATURE_NAMES,
    },
    {
        "feature_group_id": "component_mobility",
        "description": "Parsed component local-move counts only.",
        "control_scope": "component mobility ablation",
        "feature_names": COMPONENT_MOBILITY_ABLATION_FEATURE_NAMES,
    },
    {
        "feature_group_id": "component_nodes",
        "description": "Component recursive-node counts only.",
        "control_scope": "component size ablation",
        "feature_names": COMPONENT_NODES_ABLATION_FEATURE_NAMES,
    },
    {
        "feature_group_id": "component_profile_indices",
        "description": "Generator profile indices only; diagnostic for source-order leakage.",
        "control_scope": "generator metadata diagnostic",
        "feature_names": COMPONENT_PROFILE_INDEX_ABLATION_FEATURE_NAMES,
    },
    {
        "feature_group_id": "component_material_mobility",
        "description": "Component material and local-move counts without board FEN features.",
        "control_scope": "component signature ablation",
        "feature_names": COMPONENT_MATERIAL_MOBILITY_ABLATION_FEATURE_NAMES,
    },
    {
        "feature_group_id": "component_metadata_no_fen_no_profile",
        "description": "Component material, mobility, and recursive-node counts without board FEN features or profile indices.",
        "control_scope": "component metadata ablation without generator indices",
        "feature_names": COMPONENT_METADATA_NO_FEN_NO_PROFILE_ABLATION_FEATURE_NAMES,
    },
    {
        "feature_group_id": "component_metadata_no_fen_full",
        "description": "All parsed component metadata without board FEN features.",
        "control_scope": "component metadata ablation",
        "feature_names": COMPONENT_METADATA_NO_FEN_FULL_ABLATION_FEATURE_NAMES,
    },
    {
        "feature_group_id": "signature_metadata_no_profile",
        "description": "Board FEN plus parsed component metadata excluding generator profile indices.",
        "control_scope": "signature metadata ablation without generator indices",
        "feature_names": SIGNATURE_METADATA_NO_PROFILE_ABLATION_FEATURE_NAMES,
    },
    {
        "feature_group_id": "signature_metadata_full",
        "description": "Existing board FEN plus component signature metadata probe.",
        "control_scope": "full signature metadata control",
        "feature_names": SIGNATURE_METADATA_PROBE_FEATURE_NAMES,
    },
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


def evaluate_heuristic_target_report(
    jsonl_path: str | Path,
    target_field: str,
    split_key_mode: str = "position",
    heuristic_method: str | None = None,
) -> dict[str, Any]:
    """Evaluate heuristic-output targets with a train majority floor."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    assignments = split_assignments_for_rows(rows, split_key_mode)
    splitter_id = split_report_id_for_mode(split_key_mode, family_holdout=False)
    split_policy = split_policy_for_mode(split_key_mode, family_holdout=False)
    examples, excluded = heuristic_target_examples(
        rows,
        assignments,
        target_field,
        heuristic_method=heuristic_method,
    )
    train_targets = [
        example["target"] for example in examples if example["split"] == "train"
    ]
    if not train_targets:
        raise ValueError("heuristic target report requires train heuristic targets")

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

    return {
        "report_id": "heuristic_target_train_majority_report_v0",
        "dataset_path": str(path),
        "dataset_sha256": _sha256_file(path),
        "schema_version": SCHEMA_VERSION,
        "baseline_id": "heuristic_train_majority_target_v0",
        "target": f"heuristic.outputs.{target_field}",
        "eligible_label_kinds": ["heuristic"],
        "heuristic_method": heuristic_method,
        "splitter_id": splitter_id,
        "split_policy": split_policy,
        "row_counts": _count_by(assignments, "split"),
        "included_target_count": len(examples),
        "excluded_from_target_metrics": excluded,
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


def evaluate_heuristic_target_projection_report(
    jsonl_path: str | Path,
    split_key_mode: str = "position",
    heuristic_method: str | None = None,
) -> dict[str, Any]:
    """Screen candidate projections of heuristic signature targets."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    assignments = split_assignments_for_rows(rows, split_key_mode)
    splitter_id = split_report_id_for_mode(split_key_mode, family_holdout=False)
    split_policy = split_policy_for_mode(split_key_mode, family_holdout=False)
    split_names = sorted({str(assignment["split"]) for assignment in assignments})
    projection_reports = []
    for definition in HEURISTIC_SIGNATURE_TARGET_PROJECTIONS:
        examples, excluded = heuristic_projection_examples(
            rows,
            assignments,
            str(definition["projection_id"]),
            heuristic_method=heuristic_method,
        )
        projection_reports.append(
            heuristic_projection_report_entry(
                definition,
                examples,
                excluded,
                split_names,
            )
        )

    return {
        "report_id": "heuristic_signature_target_projection_report_v0",
        "dataset_path": str(path),
        "dataset_sha256": _sha256_file(path),
        "schema_version": SCHEMA_VERSION,
        "eligible_label_kinds": ["heuristic"],
        "heuristic_method": heuristic_method,
        "splitter_id": splitter_id,
        "split_policy": split_policy,
        "row_counts": _count_by(assignments, "split"),
        "projection_count": len(projection_reports),
        "projections": projection_reports,
    }


def evaluate_exact_target_projection_report(
    jsonl_path: str | Path,
    split_key_mode: str = "position",
) -> dict[str, Any]:
    """Screen candidate projections of exact signature metadata targets."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    assignments = split_assignments_for_rows(rows, split_key_mode)
    splitter_id = split_report_id_for_mode(split_key_mode, family_holdout=False)
    split_policy = split_policy_for_mode(split_key_mode, family_holdout=False)
    split_names = sorted({str(assignment["split"]) for assignment in assignments})
    projection_reports = []
    for definition in EXACT_SIGNATURE_TARGET_PROJECTIONS:
        examples, excluded = exact_projection_examples(
            rows,
            assignments,
            str(definition["projection_id"]),
        )
        projection_reports.append(
            heuristic_projection_report_entry(
                definition,
                examples,
                excluded,
                split_names,
            )
        )

    return {
        "report_id": "exact_signature_target_projection_report_v0",
        "dataset_path": str(path),
        "dataset_sha256": _sha256_file(path),
        "schema_version": SCHEMA_VERSION,
        "eligible_label_kinds": ["exact"],
        "splitter_id": splitter_id,
        "split_policy": split_policy,
        "row_counts": _count_by(assignments, "split"),
        "projection_count": len(projection_reports),
        "projections": projection_reports,
    }


def evaluate_exact_projection_baseline_report(
    jsonl_path: str | Path,
    target_projections: list[str] | None = None,
    split_key_mode: str = "position",
    epochs: int = 1_000,
    learning_rate: float = 0.05,
    l2: float = 0.001,
) -> dict[str, Any]:
    """Score deterministic and small learned baselines for exact projections."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    assignments = split_assignments_for_rows(rows, split_key_mode)
    splitter_id = split_report_id_for_mode(split_key_mode, family_holdout=False)
    split_policy = split_policy_for_mode(split_key_mode, family_holdout=False)
    return exact_projection_baseline_report_from_assignments(
        path,
        rows,
        assignments,
        splitter_id,
        split_policy,
        target_projections=target_projections,
        epochs=epochs,
        learning_rate=learning_rate,
        l2=l2,
    )


def evaluate_exact_projection_topology_balanced_baseline_report(
    jsonl_path: str | Path,
    target_projections: list[str] | None = None,
    split_key_mode: str = "position",
    epochs: int = 1_000,
    learning_rate: float = 0.05,
    l2: float = 0.001,
) -> dict[str, Any]:
    """Score exact projection baselines on a topology-balanced split."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    assignments = topology_balanced_assignments_for_rows(rows, split_key_mode)
    split_key = split_policy_for_mode(split_key_mode, family_holdout=False)[
        "split_key"
    ]
    split_policy = {
        "train": "first 2/3 of rows by sha256(split_key), within exact.value.component_topology_family",
        "dev": "next 1/6 of rows by sha256(split_key), within exact.value.component_topology_family",
        "test": "remaining rows by sha256(split_key), within exact.value.component_topology_family",
        "split_key": split_key,
        "balance_key": "exact.value.component_topology_family",
    }
    return exact_projection_baseline_report_from_assignments(
        path,
        rows,
        assignments,
        "component_topology_balanced_position_hash_v0"
        if split_key_mode == "position"
        else "component_topology_balanced_symmetry_hash_v0",
        split_policy,
        target_projections=target_projections,
        epochs=epochs,
        learning_rate=learning_rate,
        l2=l2,
    )


def exact_projection_baseline_report_from_assignments(
    path: Path,
    rows: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    splitter_id: str,
    split_policy: dict[str, str],
    target_projections: list[str] | None,
    epochs: int,
    learning_rate: float,
    l2: float,
) -> dict[str, Any]:
    projections = target_projections or list(DEFAULT_EXACT_PROJECTION_BASELINE_TARGETS)
    projection_reports = []
    for projection_id in projections:
        examples, excluded = exact_projection_model_examples(
            rows,
            assignments,
            projection_id,
        )
        projection_reports.append(
            exact_projection_baseline_entry(
                projection_id,
                examples,
                excluded,
                epochs=epochs,
                learning_rate=learning_rate,
                l2=l2,
            )
        )

    return {
        "report_id": "exact_projection_baseline_report_v0",
        "dataset_path": str(path),
        "dataset_sha256": _sha256_file(path),
        "schema_version": SCHEMA_VERSION,
        "eligible_label_kinds": ["exact"],
        "splitter_id": splitter_id,
        "split_policy": split_policy,
        "row_counts": _count_by(assignments, "split"),
        "target_projection_count": len(projection_reports),
        "target_projections": projection_reports,
    }


def evaluate_exact_projection_topology_balanced_ablation_report(
    jsonl_path: str | Path,
    target_projections: list[str] | None = None,
    split_key_mode: str = "position",
    epochs: int = 1_000,
    learning_rate: float = 0.05,
    l2: float = 0.001,
) -> dict[str, Any]:
    """Score exact projection feature-group ablations on a topology-balanced split."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    assignments = topology_balanced_assignments_for_rows(rows, split_key_mode)
    split_key = split_policy_for_mode(split_key_mode, family_holdout=False)[
        "split_key"
    ]
    split_policy = {
        "train": "first 2/3 of rows by sha256(split_key), within exact.value.component_topology_family",
        "dev": "next 1/6 of rows by sha256(split_key), within exact.value.component_topology_family",
        "test": "remaining rows by sha256(split_key), within exact.value.component_topology_family",
        "split_key": split_key,
        "balance_key": "exact.value.component_topology_family",
    }
    splitter_id = (
        "component_topology_balanced_position_hash_v0"
        if split_key_mode == "position"
        else "component_topology_balanced_symmetry_hash_v0"
    )
    projections = target_projections or list(DEFAULT_EXACT_PROJECTION_BASELINE_TARGETS)
    projection_reports = []
    for projection_id in projections:
        examples, excluded = exact_projection_ablation_examples(
            rows,
            assignments,
            projection_id,
        )
        projection_reports.append(
            exact_projection_ablation_entry(
                projection_id,
                examples,
                excluded,
                epochs=epochs,
                learning_rate=learning_rate,
                l2=l2,
            )
        )

    return {
        "report_id": "exact_projection_feature_ablation_report_v0",
        "dataset_path": str(path),
        "dataset_sha256": _sha256_file(path),
        "schema_version": SCHEMA_VERSION,
        "eligible_label_kinds": ["exact"],
        "splitter_id": splitter_id,
        "split_policy": split_policy,
        "row_counts": _count_by(assignments, "split"),
        "feature_group_count": len(EXACT_PROJECTION_ABLATION_FEATURE_GROUPS),
        "feature_groups": [
            {
                "feature_group_id": str(group["feature_group_id"]),
                "description": str(group["description"]),
                "control_scope": str(group["control_scope"]),
                "feature_names": list(group["feature_names"]),
            }
            for group in EXACT_PROJECTION_ABLATION_FEATURE_GROUPS
        ],
        "target_projection_count": len(projection_reports),
        "target_projections": projection_reports,
    }


def evaluate_exact_projection_topology_balanced_ablation_sweep_report(
    jsonl_path: str | Path,
    target_projection: str = "component_topology_family",
    split_key_mode: str = "position",
    sweep_epochs: list[int] | None = None,
    sweep_learning_rates: list[float] | None = None,
    sweep_l2: list[float] | None = None,
) -> dict[str, Any]:
    """Sweep feature-group probe hyperparameters on the topology-balanced split."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    assignments = topology_balanced_assignments_for_rows(rows, split_key_mode)
    split_key = split_policy_for_mode(split_key_mode, family_holdout=False)[
        "split_key"
    ]
    split_policy = {
        "train": "first 2/3 of rows by sha256(split_key), within exact.value.component_topology_family",
        "dev": "next 1/6 of rows by sha256(split_key), within exact.value.component_topology_family",
        "test": "remaining rows by sha256(split_key), within exact.value.component_topology_family",
        "split_key": split_key,
        "balance_key": "exact.value.component_topology_family",
    }
    splitter_id = (
        "component_topology_balanced_position_hash_v0"
        if split_key_mode == "position"
        else "component_topology_balanced_symmetry_hash_v0"
    )
    examples, excluded = exact_projection_ablation_examples(
        rows,
        assignments,
        target_projection,
    )
    train_examples = [example for example in examples if example["split"] == "train"]
    if not train_examples:
        return {
            "report_id": "exact_projection_feature_ablation_sweep_report_v0",
            "status": "no_train_support",
            "dataset_path": str(path),
            "dataset_sha256": _sha256_file(path),
            "schema_version": SCHEMA_VERSION,
            "eligible_label_kinds": ["exact"],
            "splitter_id": splitter_id,
            "split_policy": split_policy,
            "row_counts": _count_by(assignments, "split"),
            "target_projection": target_projection,
            "excluded_from_target_metrics": excluded,
        }

    epochs_values = sweep_epochs or [250, 1_000]
    learning_rate_values = sweep_learning_rates or [0.02, 0.05, 0.1]
    l2_values = sweep_l2 or [0.0, 0.001, 0.01]
    target_labels = tuple(sorted({example["target"] for example in examples}))
    train_labels = tuple(sorted({example["target"] for example in train_examples}))
    train_targets = [example["target"] for example in train_examples]
    majority_prediction = _majority_label(train_targets)
    majority_predictions = [majority_prediction for _example in examples]
    majority_metrics = exact_projection_accuracy_by_split(examples, majority_predictions)
    majority_dev_accuracy = majority_metrics.get("dev", {}).get("accuracy", 0.0)
    majority_test_accuracy = majority_metrics.get("test", {}).get("accuracy", 0.0)

    feature_group_summaries = []
    all_trials = []
    for group in EXACT_PROJECTION_ABLATION_FEATURE_GROUPS:
        group_id = str(group["feature_group_id"])
        group_trials = []
        for epoch_count in epochs_values:
            for learning_rate in learning_rate_values:
                for l2 in l2_values:
                    model = train_multiclass_logistic_probe(
                        [
                            example["feature_groups"][group_id]
                            for example in train_examples
                        ],
                        train_targets,
                        labels=train_labels,
                        epochs=epoch_count,
                        learning_rate=learning_rate,
                        l2=l2,
                    )
                    predictions = [
                        multiclass_logistic_predict(
                            model,
                            example["feature_groups"][group_id],
                        )
                        for example in examples
                    ]
                    split_metrics = exact_projection_accuracy_by_split(
                        examples,
                        predictions,
                    )
                    dev_accuracy = split_metrics.get("dev", {}).get("accuracy", 0.0)
                    test_accuracy = split_metrics.get("test", {}).get("accuracy", 0.0)
                    trial = {
                        "feature_group_id": group_id,
                        "epochs": epoch_count,
                        "learning_rate": learning_rate,
                        "l2": l2,
                        "split_metrics": split_metrics,
                        "beats_majority_on_dev_and_test": (
                            dev_accuracy > majority_dev_accuracy
                            and test_accuracy > majority_test_accuracy
                        ),
                        "model_summary": multiclass_model_summary(model),
                    }
                    group_trials.append(trial)
                    all_trials.append(trial)

        best_by_dev_then_test = max(
            group_trials,
            key=lambda trial: exact_projection_sweep_sort_key(
                trial,
                primary_split="dev",
                secondary_split="test",
            ),
        )
        best_by_test_then_dev = max(
            group_trials,
            key=lambda trial: exact_projection_sweep_sort_key(
                trial,
                primary_split="test",
                secondary_split="dev",
            ),
        )
        claim_candidates = [
            trial for trial in group_trials if trial["beats_majority_on_dev_and_test"]
        ]
        claim_candidates.sort(
            key=lambda trial: exact_projection_sweep_sort_key(
                trial,
                primary_split="dev",
                secondary_split="test",
            ),
            reverse=True,
        )
        feature_group_summaries.append(
            {
                "feature_group_id": group_id,
                "description": str(group["description"]),
                "control_scope": str(group["control_scope"]),
                "feature_names": list(group["feature_names"]),
                "trial_count": len(group_trials),
                "claim_candidate_count": len(claim_candidates),
                "best_by_dev_then_test": best_by_dev_then_test,
                "best_by_test_then_dev": best_by_test_then_dev,
                "claim_candidates": claim_candidates[:5],
            }
        )

    claim_candidate_count = sum(
        summary["claim_candidate_count"] for summary in feature_group_summaries
    )

    return {
        "report_id": "exact_projection_feature_ablation_sweep_report_v0",
        "status": "evaluated",
        "dataset_path": str(path),
        "dataset_sha256": _sha256_file(path),
        "schema_version": SCHEMA_VERSION,
        "eligible_label_kinds": ["exact"],
        "splitter_id": splitter_id,
        "split_policy": split_policy,
        "row_counts": _count_by(assignments, "split"),
        "target_projection": target_projection,
        "target": exact_projection_definition_target(target_projection),
        "included_target_count": len(examples),
        "excluded_from_target_metrics": excluded,
        "target_label_count": len(target_labels),
        "target_counts": dict(sorted(Counter(example["target"] for example in examples).items())),
        "train_label_count": len(train_labels),
        "train_labels": list(train_labels),
        "unseen_labels_by_split": unseen_labels_by_split(examples, set(train_labels)),
        "hyperparameter_grid": {
            "epochs": epochs_values,
            "learning_rates": learning_rate_values,
            "l2": l2_values,
            "trial_count_per_feature_group": (
                len(epochs_values) * len(learning_rate_values) * len(l2_values)
            ),
            "optimizer": "full_batch_gradient_descent",
            "standardization": "train_split_mean_std_except_bias",
        },
        "majority_predictor": {
            "prediction": majority_prediction,
            "split_metrics": majority_metrics,
        },
        "claim_rule": "claim candidate iff dev and test accuracy both exceed train-majority on the same split",
        "claim_candidate_count": claim_candidate_count,
        "feature_group_summaries": feature_group_summaries,
    }


def evaluate_heuristic_signature_promotion_report(
    jsonl_path: str | Path,
    split_key_mode: str = "position",
    heuristic_method: str | None = None,
) -> dict[str, Any]:
    """Audit whether heuristic signature rows are contract-complete but blocked."""

    path = Path(jsonl_path)
    rows = load_dataset_label_v0_jsonl(path)
    assignments = split_assignments_for_rows(rows, split_key_mode)
    splitter_id = split_report_id_for_mode(split_key_mode, family_holdout=False)
    split_policy = split_policy_for_mode(split_key_mode, family_holdout=False)

    included: list[dict[str, Any]] = []
    excluded: dict[str, Counter[str]] = {
        "non_heuristic_rows_by_split": Counter(),
        "method_mismatch_rows_by_split": Counter(),
        "missing_outputs_rows_by_split": Counter(),
    }
    missing_output_fields: Counter[str] = Counter()
    target_status_counts: Counter[str] = Counter()
    supervision_eligible_counts: Counter[str] = Counter()
    contract_id_counts: Counter[str] = Counter()
    signature_rule_counts: Counter[str] = Counter()
    topology_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    component_signatures: list[str] = []
    result_signature_keys: list[str] = []
    current_result_value_digests: list[str] = []
    malformed_component_signature_rows: list[str] = []
    result_signature_key_mismatch_rows: list[str] = []
    missing_required_blockers_by_row: dict[str, list[str]] = {}

    for row, assignment in zip(rows, assignments):
        split = str(assignment["split"])
        heuristic = row.get("heuristic")
        if row.get("label_kind") != "heuristic" or not isinstance(heuristic, dict):
            excluded["non_heuristic_rows_by_split"][split] += 1
            continue
        method = str(heuristic.get("method") or "")
        if heuristic_method is not None and method != heuristic_method:
            excluded["method_mismatch_rows_by_split"][split] += 1
            continue
        outputs = heuristic.get("outputs")
        if not isinstance(outputs, dict):
            excluded["missing_outputs_rows_by_split"][split] += 1
            continue

        row_id = str(row.get("row_id"))
        included.append(row)
        for field in HEURISTIC_SIGNATURE_REQUIRED_OUTPUT_FIELDS:
            if _nonempty_output_string(outputs, field) is None:
                missing_output_fields[field] += 1

        target_status = _nonempty_output_string(outputs, "target_status") or "__missing__"
        supervision_eligible = (
            _nonempty_output_string(outputs, "supervision_eligible") or "__missing__"
        )
        contract_id = _nonempty_output_string(outputs, "target_contract_id") or "__missing__"
        signature_rule = (
            _nonempty_output_string(outputs, "component_signature_rule") or "__missing__"
        )
        topology = (
            _nonempty_output_string(outputs, "component_topology_family") or "__missing__"
        )
        target_status_counts[target_status] += 1
        supervision_eligible_counts[supervision_eligible] += 1
        contract_id_counts[contract_id] += 1
        signature_rule_counts[signature_rule] += 1
        topology_counts[topology] += 1

        left_signature = _nonempty_output_string(outputs, "left_component_signature")
        right_signature = _nonempty_output_string(outputs, "right_component_signature")
        if left_signature is not None:
            component_signatures.append(left_signature)
        if right_signature is not None:
            component_signatures.append(right_signature)
        result_signature_key = _nonempty_output_string(outputs, "result_signature_key")
        if result_signature_key is not None:
            result_signature_keys.append(result_signature_key)
        result_value_digest = _nonempty_output_string(
            outputs, "current_result_value_digest"
        )
        if result_value_digest is not None:
            current_result_value_digests.append(result_value_digest)

        left_parts = _component_signature_parts(outputs, "left")
        right_parts = _component_signature_parts(outputs, "right")
        if not _component_signature_has_required_parts(
            left_parts
        ) or not _component_signature_has_required_parts(right_parts):
            malformed_component_signature_rows.append(row_id)
        if (
            topology != "__missing__"
            and left_signature is not None
            and right_signature is not None
            and result_signature_key is not None
        ):
            expected_key = (
                f"{topology};left:{left_signature};right:{right_signature}"
            )
            if result_signature_key != expected_key:
                result_signature_key_mismatch_rows.append(row_id)

        blockers = _promotion_blocker_ids(outputs)
        blocker_counts.update(blockers)
        missing_blockers = sorted(
            set(HEURISTIC_SIGNATURE_PROMOTION_BLOCKER_IDS) - set(blockers)
        )
        if missing_blockers:
            missing_required_blockers_by_row[row_id] = missing_blockers

    duplicate_component_signatures = duplicate_total(Counter(component_signatures))
    duplicate_result_signature_keys = duplicate_total(Counter(result_signature_keys))
    row_contract_errors = heuristic_signature_row_contract_errors(
        included_count=len(included),
        missing_output_fields=missing_output_fields,
        target_status_counts=target_status_counts,
        supervision_eligible_counts=supervision_eligible_counts,
        contract_id_counts=contract_id_counts,
        malformed_component_signature_rows=malformed_component_signature_rows,
        result_signature_key_mismatch_rows=result_signature_key_mismatch_rows,
        duplicate_component_signatures=duplicate_component_signatures,
        duplicate_result_signature_keys=duplicate_result_signature_keys,
        missing_required_blockers_by_row=missing_required_blockers_by_row,
    )
    row_contract_passed = not row_contract_errors

    return {
        "report_id": "heuristic_signature_promotion_readiness_report_v0",
        "dataset_path": str(path),
        "dataset_sha256": _sha256_file(path),
        "schema_version": SCHEMA_VERSION,
        "eligible_label_kinds": ["heuristic"],
        "heuristic_method": heuristic_method,
        "splitter_id": splitter_id,
        "split_policy": split_policy,
        "row_counts": _count_by(assignments, "split"),
        "included_row_count": len(included),
        "excluded_from_contract_metrics": {
            key: dict(sorted(counter.items()))
            for key, counter in excluded.items()
            if counter
        },
        "row_contract_gate": {
            "passed": row_contract_passed,
            "contract_id": SIGNATURE_PROFILE_CONTRACT_ID,
            "required_output_fields": list(HEURISTIC_SIGNATURE_REQUIRED_OUTPUT_FIELDS),
            "missing_output_fields": dict(sorted(missing_output_fields.items())),
            "target_status_counts": dict(sorted(target_status_counts.items())),
            "supervision_eligible_counts": dict(
                sorted(supervision_eligible_counts.items())
            ),
            "contract_id_counts": dict(sorted(contract_id_counts.items())),
            "component_signature_rule_counts": dict(
                sorted(signature_rule_counts.items())
            ),
            "component_topology_family_counts": dict(sorted(topology_counts.items())),
            "malformed_component_signature_rows": sorted(
                malformed_component_signature_rows
            ),
            "result_signature_key_mismatch_rows": sorted(
                result_signature_key_mismatch_rows
            ),
            "missing_required_blockers_by_row": missing_required_blockers_by_row,
            "validation_errors": row_contract_errors,
        },
        "reuse_checks": {
            "duplicate_component_signatures": duplicate_component_signatures,
            "duplicate_result_signature_keys": duplicate_result_signature_keys,
            "duplicate_current_result_value_digests": duplicate_total(
                Counter(current_result_value_digests)
            ),
            "component_signature_count": len(component_signatures),
            "result_signature_key_count": len(result_signature_keys),
            "current_result_value_digest_count": len(current_result_value_digests),
        },
        "promotion_gate": {
            "passed": False,
            "required_blocker_ids": list(HEURISTIC_SIGNATURE_PROMOTION_BLOCKER_IDS),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "blockers": list(SIGNATURE_PROFILE_PROMOTION_BLOCKERS),
            "next_required_evidence": [
                "versioned exact value rule",
                "replay-compatible provenance checker",
                "split and leakage semantics for promoted targets",
                "deterministic floors and learned-model baselines on the promoted split",
            ],
        },
        "contract_status": (
            "row_contract_passed_promotion_blocked"
            if row_contract_passed
            else "row_contract_failed_promotion_blocked"
        ),
    }


def evaluate_signature_profile_contract_report(
    report_json_path: str | Path,
    rows_per_family_target: int = 10,
) -> dict[str, Any]:
    """Validate a signature-profile search report as a diagnostic target contract."""

    path = Path(report_json_path)
    source_report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(source_report, dict):
        raise ValueError("signature profile report must be a JSON object")

    validation_errors = signature_profile_report_validation_errors(
        source_report,
        rows_per_family_target=rows_per_family_target,
    )
    selected_counts = _string_int_dict(
        source_report.get("selected_counts_by_topology_family")
    )
    candidate_pair_counts = _string_int_dict(
        source_report.get("candidate_pair_counts_by_topology_family")
    )
    candidates = source_report.get("candidates")
    if not isinstance(candidates, list):
        candidates = []
    component_signatures = [
        str(candidate[signature_field])
        for candidate in candidates
        if isinstance(candidate, dict)
        for signature_field in ("left_component_signature", "right_component_signature")
        if isinstance(candidate.get(signature_field), str)
    ]
    result_signature_keys = [
        str(candidate["result_signature_key"])
        for candidate in candidates
        if isinstance(candidate, dict)
        and isinstance(candidate.get("result_signature_key"), str)
    ]
    candidate_topology_counts = dict(
        sorted(
            Counter(
                str(candidate.get("topology_family"))
                for candidate in candidates
                if isinstance(candidate, dict)
                and isinstance(candidate.get("topology_family"), str)
            ).items()
        )
    )

    support_gate_passed = not validation_errors
    selected_row_count = source_report.get("selected_row_count")
    return {
        "report_id": "signature_profile_target_contract_report_v0",
        "source_report_path": str(path),
        "source_report_sha256": _sha256_file(path),
        "source": source_report.get("source"),
        "component_signature_rule": source_report.get("component_signature_rule"),
        "contract": {
            "contract_id": SIGNATURE_PROFILE_CONTRACT_ID,
            "diagnostic_only": True,
            "supervision_eligible": False,
            "target_field": "result_signature_key",
            "target_semantics": (
                "depth-two component value digest plus material balance plus "
                "local move counts; diagnostic support only"
            ),
        },
        "support_gate": {
            "passed": support_gate_passed,
            "rows_per_family_target": rows_per_family_target,
            "topology_family_count": len(selected_counts),
            "selected_row_count": selected_row_count,
            "selected_counts_by_topology_family": selected_counts,
            "candidate_pair_counts_by_topology_family": candidate_pair_counts,
            "candidate_topology_counts": candidate_topology_counts,
            "left_signature_profile_count": source_report.get(
                "left_signature_profile_count"
            ),
            "right_signature_profile_count": source_report.get(
                "right_signature_profile_count"
            ),
            "validation_errors": validation_errors,
        },
        "reuse_checks": {
            "duplicate_component_signatures": duplicate_total(
                Counter(component_signatures)
            ),
            "duplicate_result_signature_keys": duplicate_total(
                Counter(result_signature_keys)
            ),
        },
        "rejection_counts": _string_int_dict(source_report.get("rejection_counts")),
        "promotion_gate": {
            "passed": False,
            "blockers": list(SIGNATURE_PROFILE_PROMOTION_BLOCKERS),
        },
        "contract_status": (
            "support_gate_passed_promotion_blocked"
            if support_gate_passed
            else "support_gate_failed"
        ),
    }


def signature_profile_report_validation_errors(
    report: dict[str, Any],
    rows_per_family_target: int,
) -> list[str]:
    errors: list[str] = []
    for field in SIGNATURE_PROFILE_REQUIRED_FIELDS:
        if field not in report:
            errors.append(f"missing required field {field}")

    if rows_per_family_target < 1:
        errors.append("rows_per_family_target must be >= 1")

    rule = report.get("component_signature_rule")
    if not isinstance(rule, str) or not rule:
        errors.append("component_signature_rule must be a non-empty string")
    elif not rule.endswith("_v0"):
        errors.append("component_signature_rule must be versioned with _v0")

    report_target = report.get("rows_per_family_target")
    if report_target != rows_per_family_target:
        errors.append(
            "rows_per_family_target mismatch: "
            f"report={report_target!r} expected={rows_per_family_target!r}"
        )

    selected_counts = _string_int_dict(report.get("selected_counts_by_topology_family"))
    candidate_pair_counts = _string_int_dict(
        report.get("candidate_pair_counts_by_topology_family")
    )
    selected_row_count = report.get("selected_row_count")
    if not isinstance(selected_row_count, int):
        errors.append("selected_row_count must be an integer")
    elif selected_row_count != sum(selected_counts.values()):
        errors.append(
            "selected_row_count must equal sum(selected_counts_by_topology_family)"
        )

    if not selected_counts:
        errors.append("selected_counts_by_topology_family must be non-empty")
    for family, count in selected_counts.items():
        if count < rows_per_family_target:
            errors.append(
                f"topology family {family} has selected count {count}, "
                f"below target {rows_per_family_target}"
            )
        if candidate_pair_counts.get(family, 0) < count:
            errors.append(
                f"topology family {family} has fewer candidate pairs than selections"
            )

    for count_field in ("left_signature_profile_count", "right_signature_profile_count"):
        count = report.get(count_field)
        if not isinstance(count, int) or count <= 0:
            errors.append(f"{count_field} must be a positive integer")

    candidates = report.get("candidates")
    if not isinstance(candidates, list):
        errors.append("candidates must be a list")
        candidates = []
    if isinstance(selected_row_count, int) and len(candidates) != selected_row_count:
        errors.append("candidate count must equal selected_row_count")

    component_signatures: list[str] = []
    result_signature_keys: list[str] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append(f"candidate {index} must be an object")
            continue
        for field in SIGNATURE_PROFILE_CANDIDATE_REQUIRED_FIELDS:
            value = candidate.get(field)
            if value is None or value == "":
                errors.append(f"candidate {index} missing required field {field}")
        left_signature = candidate.get("left_component_signature")
        right_signature = candidate.get("right_component_signature")
        result_signature = candidate.get("result_signature_key")
        if isinstance(left_signature, str):
            component_signatures.append(left_signature)
        if isinstance(right_signature, str):
            component_signatures.append(right_signature)
        if isinstance(result_signature, str):
            result_signature_keys.append(result_signature)

    duplicate_component_signatures = duplicate_total(Counter(component_signatures))
    if duplicate_component_signatures:
        errors.append(
            "selected candidates must not reuse component signatures: "
            f"duplicates={duplicate_component_signatures}"
        )
    duplicate_result_signatures = duplicate_total(Counter(result_signature_keys))
    if duplicate_result_signatures:
        errors.append(
            "selected candidates must not reuse result signature keys: "
            f"duplicates={duplicate_result_signatures}"
        )

    return errors


def heuristic_signature_row_contract_errors(
    included_count: int,
    missing_output_fields: Counter[str],
    target_status_counts: Counter[str],
    supervision_eligible_counts: Counter[str],
    contract_id_counts: Counter[str],
    malformed_component_signature_rows: list[str],
    result_signature_key_mismatch_rows: list[str],
    duplicate_component_signatures: int,
    duplicate_result_signature_keys: int,
    missing_required_blockers_by_row: dict[str, list[str]],
) -> list[str]:
    errors = []
    if included_count < 1:
        errors.append("no eligible heuristic signature rows")
    if missing_output_fields:
        for field, count in sorted(missing_output_fields.items()):
            errors.append(f"missing output field {field} on {count} row(s)")
    if target_status_counts != Counter({"diagnostic_only": included_count}):
        errors.append("target_status must be diagnostic_only for every included row")
    if supervision_eligible_counts != Counter({"false": included_count}):
        errors.append("supervision_eligible must be false for every included row")
    if contract_id_counts != Counter({SIGNATURE_PROFILE_CONTRACT_ID: included_count}):
        errors.append(f"target_contract_id must be {SIGNATURE_PROFILE_CONTRACT_ID}")
    if malformed_component_signature_rows:
        errors.append("component signatures must parse into value/material/moves fields")
    if result_signature_key_mismatch_rows:
        errors.append(
            "result_signature_key must equal topology plus left/right signatures"
        )
    if duplicate_component_signatures:
        errors.append("component signatures must not be reused")
    if duplicate_result_signature_keys:
        errors.append("result_signature_key values must not be reused")
    if missing_required_blockers_by_row:
        errors.append("promotion_blockers must include every required blocker id")
    return errors


def _promotion_blocker_ids(outputs: dict[str, Any]) -> list[str]:
    raw_blockers = outputs.get("promotion_blockers")
    if isinstance(raw_blockers, list):
        return [
            str(blocker).strip()
            for blocker in raw_blockers
            if str(blocker).strip()
        ]
    if raw_blockers is None:
        return []
    return [
        blocker.strip()
        for blocker in str(raw_blockers).split(";")
        if blocker.strip()
    ]


def _string_int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, count in value.items():
        if isinstance(count, bool):
            continue
        if isinstance(count, int):
            result[str(key)] = count
    return dict(sorted(result.items()))


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


def heuristic_target_examples(
    rows: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    target_field: str,
    heuristic_method: str | None = None,
) -> tuple[list[dict[str, str]], dict[str, dict[str, int]]]:
    examples = []
    excluded: dict[str, Counter[str]] = {
        "non_heuristic_rows_by_split": Counter(),
        "method_mismatch_rows_by_split": Counter(),
        "heuristic_rows_missing_target_by_split": Counter(),
    }
    for row, assignment in zip(rows, assignments):
        split = str(assignment["split"])
        heuristic = row.get("heuristic")
        if row.get("label_kind") != "heuristic" or not isinstance(heuristic, dict):
            excluded["non_heuristic_rows_by_split"][split] += 1
            continue
        method = str(heuristic.get("method") or "")
        if heuristic_method is not None and method != heuristic_method:
            excluded["method_mismatch_rows_by_split"][split] += 1
            continue
        outputs = heuristic.get("outputs")
        if not isinstance(outputs, dict) or target_field not in outputs:
            excluded["heuristic_rows_missing_target_by_split"][split] += 1
            continue
        target = str(outputs[target_field])
        if not target:
            excluded["heuristic_rows_missing_target_by_split"][split] += 1
            continue
        examples.append(
            {
                "split": split,
                "target": target,
                "heuristic_method": method,
                "row_id": str(row.get("row_id")),
            }
        )
    return examples, {
        key: dict(sorted(counter.items()))
        for key, counter in excluded.items()
        if counter
    }


def heuristic_projection_examples(
    rows: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    projection_id: str,
    heuristic_method: str | None = None,
) -> tuple[list[dict[str, str]], dict[str, dict[str, int]]]:
    examples = []
    excluded: dict[str, Counter[str]] = {
        "non_heuristic_rows_by_split": Counter(),
        "method_mismatch_rows_by_split": Counter(),
        "projection_missing_rows_by_split": Counter(),
    }
    for row, assignment in zip(rows, assignments):
        split = str(assignment["split"])
        heuristic = row.get("heuristic")
        if row.get("label_kind") != "heuristic" or not isinstance(heuristic, dict):
            excluded["non_heuristic_rows_by_split"][split] += 1
            continue
        method = str(heuristic.get("method") or "")
        if heuristic_method is not None and method != heuristic_method:
            excluded["method_mismatch_rows_by_split"][split] += 1
            continue
        outputs = heuristic.get("outputs")
        if not isinstance(outputs, dict):
            excluded["projection_missing_rows_by_split"][split] += 1
            continue
        target = heuristic_projection_value(outputs, projection_id)
        if target is None:
            excluded["projection_missing_rows_by_split"][split] += 1
            continue
        examples.append(
            {
                "split": split,
                "target": target,
                "heuristic_method": method,
                "row_id": str(row.get("row_id")),
            }
        )
    return examples, {
        key: dict(sorted(counter.items()))
        for key, counter in excluded.items()
        if counter
    }


def exact_projection_examples(
    rows: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    projection_id: str,
) -> tuple[list[dict[str, str]], dict[str, dict[str, int]]]:
    examples = []
    excluded: dict[str, Counter[str]] = {
        "non_exact_rows_by_split": Counter(),
        "projection_missing_rows_by_split": Counter(),
    }
    for row, assignment in zip(rows, assignments):
        split = str(assignment["split"])
        if row.get("label_kind") != "exact":
            excluded["non_exact_rows_by_split"][split] += 1
            continue
        value = exact_value_payload(row)
        if not value:
            excluded["projection_missing_rows_by_split"][split] += 1
            continue
        target = exact_projection_value(value, projection_id)
        if target is None:
            excluded["projection_missing_rows_by_split"][split] += 1
            continue
        examples.append(
            {
                "split": split,
                "target": target,
                "row_id": str(row.get("row_id")),
            }
        )
    return examples, {
        key: dict(sorted(counter.items()))
        for key, counter in excluded.items()
        if counter
    }


def exact_projection_model_examples(
    rows: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    projection_id: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    examples: list[dict[str, Any]] = []
    excluded: dict[str, Counter[str]] = {
        "non_exact_rows_by_split": Counter(),
        "projection_missing_rows_by_split": Counter(),
        "fen_feature_missing_rows_by_split": Counter(),
        "signature_feature_missing_rows_by_split": Counter(),
    }
    for row, assignment in zip(rows, assignments):
        split = str(assignment["split"])
        if row.get("label_kind") != "exact":
            excluded["non_exact_rows_by_split"][split] += 1
            continue
        value = exact_value_payload(row)
        if not value:
            excluded["projection_missing_rows_by_split"][split] += 1
            continue
        target = exact_projection_value(value, projection_id)
        if target is None:
            excluded["projection_missing_rows_by_split"][split] += 1
            continue

        fen_features = fen_material_probe_features(row)
        signature_features = signature_metadata_probe_features(row)
        if fen_features is None:
            excluded["fen_feature_missing_rows_by_split"][split] += 1
            continue
        if signature_features is None:
            excluded["signature_feature_missing_rows_by_split"][split] += 1
            continue

        examples.append(
            {
                "row": row,
                "row_id": str(row.get("row_id")),
                "split": split,
                "target": target,
                "fen_material_feature_key": fen_material_feature_key(
                    derive_position_features(row)
                ),
                "signature_metadata_feature_key": signature_metadata_feature_key(
                    value
                ),
                "fen_material_features": fen_features,
                "signature_metadata_features": signature_features,
            }
        )
    return examples, {
        key: dict(sorted(counter.items()))
        for key, counter in excluded.items()
        if counter
    }


def exact_projection_ablation_examples(
    rows: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    projection_id: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    examples: list[dict[str, Any]] = []
    excluded: dict[str, Counter[str]] = {
        "non_exact_rows_by_split": Counter(),
        "projection_missing_rows_by_split": Counter(),
        "ablation_feature_missing_rows_by_split": Counter(),
    }
    for row, assignment in zip(rows, assignments):
        split = str(assignment["split"])
        if row.get("label_kind") != "exact":
            excluded["non_exact_rows_by_split"][split] += 1
            continue
        value = exact_value_payload(row)
        if not value:
            excluded["projection_missing_rows_by_split"][split] += 1
            continue
        target = exact_projection_value(value, projection_id)
        if target is None:
            excluded["projection_missing_rows_by_split"][split] += 1
            continue

        feature_groups = exact_projection_ablation_feature_groups(row)
        if feature_groups is None:
            excluded["ablation_feature_missing_rows_by_split"][split] += 1
            continue

        examples.append(
            {
                "row_id": str(row.get("row_id")),
                "split": split,
                "target": target,
                "feature_groups": feature_groups,
            }
        )
    return examples, {
        key: dict(sorted(counter.items()))
        for key, counter in excluded.items()
        if counter
    }


def exact_projection_baseline_entry(
    projection_id: str,
    examples: list[dict[str, Any]],
    excluded: dict[str, dict[str, int]],
    epochs: int,
    learning_rate: float,
    l2: float,
) -> dict[str, Any]:
    train_examples = [example for example in examples if example["split"] == "train"]
    if not train_examples:
        return {
            "projection_id": projection_id,
            "status": "no_train_support",
            "included_target_count": len(examples),
            "excluded_from_target_metrics": excluded,
        }

    target_labels = tuple(sorted({example["target"] for example in examples}))
    train_labels = tuple(sorted({example["target"] for example in train_examples}))
    train_targets = [example["target"] for example in train_examples]
    majority_prediction = _majority_label(train_targets)
    predictors = [
        exact_projection_predictor_report(
            "train_majority",
            "Predicts the most common train target for every row.",
            examples,
            [majority_prediction for _example in examples],
            target_labels,
            {"train_majority_prediction": majority_prediction},
        ),
        exact_projection_predictor_report(
            "fen_material_feature_majority",
            "Predicts the train majority label for an exact FEN/material feature key, falling back to train-majority.",
            examples,
            keyed_majority_predictions(
                examples,
                "fen_material_feature_key",
                majority_prediction,
            ),
            target_labels,
            {"fallback_prediction": majority_prediction},
        ),
        exact_projection_predictor_report(
            "signature_metadata_feature_majority",
            "Predicts the train majority label for a component-signature metadata key, falling back to train-majority.",
            examples,
            keyed_majority_predictions(
                examples,
                "signature_metadata_feature_key",
                majority_prediction,
            ),
            target_labels,
            {
                "fallback_prediction": majority_prediction,
                "control_scope": "uses exact metadata fields; interpret as a structured control, not a no-decomposition model",
            },
        ),
    ]

    for predictor_id, feature_key, feature_names, control_scope in (
        (
            "fen_material_multiclass_logistic_probe",
            "fen_material_features",
            FEN_MATERIAL_PROBE_FEATURE_NAMES,
            "full-board FEN/material control",
        ),
        (
            "signature_metadata_multiclass_logistic_probe",
            "signature_metadata_features",
            SIGNATURE_METADATA_PROBE_FEATURE_NAMES,
            "component-signature metadata control",
        ),
    ):
        model = train_multiclass_logistic_probe(
            [example[feature_key] for example in train_examples],
            [example["target"] for example in train_examples],
            labels=train_labels,
            epochs=epochs,
            learning_rate=learning_rate,
            l2=l2,
        )
        predictions = [
            multiclass_logistic_predict(model, example[feature_key])
            for example in examples
        ]
        predictors.append(
            exact_projection_predictor_report(
                predictor_id,
                "Small deterministic multiclass logistic probe trained on the train split.",
                examples,
                predictions,
                target_labels,
                {
                    "feature_names": list(feature_names),
                    "control_scope": control_scope,
                    "training": {
                        "train_split": "train",
                        "epochs": epochs,
                        "learning_rate": learning_rate,
                        "l2": l2,
                        "optimizer": "full_batch_gradient_descent",
                        "standardization": "train_split_mean_std_except_bias",
                        "train_label_count": len(train_labels),
                    },
                    "model_summary": multiclass_model_summary(model),
                },
            )
        )

    return {
        "projection_id": projection_id,
        "status": "evaluated",
        "target": exact_projection_definition_target(projection_id),
        "included_target_count": len(examples),
        "excluded_from_target_metrics": excluded,
        "target_label_count": len(target_labels),
        "target_counts": dict(sorted(Counter(example["target"] for example in examples).items())),
        "train_label_count": len(train_labels),
        "train_labels": list(train_labels),
        "train_majority_prediction": majority_prediction,
        "unseen_labels_by_split": unseen_labels_by_split(examples, set(train_labels)),
        "predictors": predictors,
    }


def exact_projection_ablation_entry(
    projection_id: str,
    examples: list[dict[str, Any]],
    excluded: dict[str, dict[str, int]],
    epochs: int,
    learning_rate: float,
    l2: float,
) -> dict[str, Any]:
    train_examples = [example for example in examples if example["split"] == "train"]
    if not train_examples:
        return {
            "projection_id": projection_id,
            "status": "no_train_support",
            "included_target_count": len(examples),
            "excluded_from_target_metrics": excluded,
        }

    target_labels = tuple(sorted({example["target"] for example in examples}))
    train_labels = tuple(sorted({example["target"] for example in train_examples}))
    train_targets = [example["target"] for example in train_examples]
    majority_prediction = _majority_label(train_targets)
    predictors = [
        exact_projection_predictor_report(
            "train_majority",
            "Predicts the most common train target for every row.",
            examples,
            [majority_prediction for _example in examples],
            target_labels,
            {"train_majority_prediction": majority_prediction},
        )
    ]

    for group in EXACT_PROJECTION_ABLATION_FEATURE_GROUPS:
        group_id = str(group["feature_group_id"])
        model = train_multiclass_logistic_probe(
            [example["feature_groups"][group_id] for example in train_examples],
            train_targets,
            labels=train_labels,
            epochs=epochs,
            learning_rate=learning_rate,
            l2=l2,
        )
        predictions = [
            multiclass_logistic_predict(model, example["feature_groups"][group_id])
            for example in examples
        ]
        predictors.append(
            exact_projection_predictor_report(
                f"{group_id}_multiclass_logistic_probe",
                "Small deterministic multiclass logistic probe trained on one feature group.",
                examples,
                predictions,
                target_labels,
                {
                    "feature_group_id": group_id,
                    "feature_names": list(group["feature_names"]),
                    "control_scope": str(group["control_scope"]),
                    "training": {
                        "train_split": "train",
                        "epochs": epochs,
                        "learning_rate": learning_rate,
                        "l2": l2,
                        "optimizer": "full_batch_gradient_descent",
                        "standardization": "train_split_mean_std_except_bias",
                        "train_label_count": len(train_labels),
                    },
                    "model_summary": multiclass_model_summary(model),
                },
            )
        )

    return {
        "projection_id": projection_id,
        "status": "evaluated",
        "target": exact_projection_definition_target(projection_id),
        "included_target_count": len(examples),
        "excluded_from_target_metrics": excluded,
        "target_label_count": len(target_labels),
        "target_counts": dict(sorted(Counter(example["target"] for example in examples).items())),
        "train_label_count": len(train_labels),
        "train_labels": list(train_labels),
        "train_majority_prediction": majority_prediction,
        "unseen_labels_by_split": unseen_labels_by_split(examples, set(train_labels)),
        "predictors": predictors,
    }


def exact_projection_predictor_report(
    predictor_id: str,
    description: str,
    examples: list[dict[str, Any]],
    predictions: list[str],
    labels: tuple[str, ...],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    split_metrics = {}
    for split in sorted({example["split"] for example in examples}):
        split_indices = [
            index
            for index, example in enumerate(examples)
            if example["split"] == split
        ]
        targets = [examples[index]["target"] for index in split_indices]
        split_predictions = [predictions[index] for index in split_indices]
        split_metrics[split] = {
            "support": len(split_indices),
            "target_counts": dict(sorted(Counter(targets).items())),
            "prediction_counts": dict(sorted(Counter(split_predictions).items())),
            **_classification_metrics(targets, split_predictions, labels),
        }

    report = {
        "predictor_id": predictor_id,
        "description": description,
        "split_metrics": split_metrics,
    }
    if metadata:
        report.update(metadata)
    return report


def exact_projection_accuracy_by_split(
    examples: list[dict[str, Any]],
    predictions: list[str],
) -> dict[str, dict[str, Any]]:
    split_metrics = {}
    for split in sorted({example["split"] for example in examples}):
        split_indices = [
            index
            for index, example in enumerate(examples)
            if example["split"] == split
        ]
        targets = [examples[index]["target"] for index in split_indices]
        split_predictions = [predictions[index] for index in split_indices]
        correct = sum(
            1
            for target, prediction in zip(targets, split_predictions)
            if target == prediction
        )
        split_metrics[split] = {
            "support": len(split_indices),
            "accuracy": _safe_div(correct, len(split_indices)),
            "target_counts": dict(sorted(Counter(targets).items())),
            "prediction_counts": dict(sorted(Counter(split_predictions).items())),
        }
    return split_metrics


def exact_projection_sweep_sort_key(
    trial: dict[str, Any],
    primary_split: str,
    secondary_split: str,
) -> tuple[float, float, float, int, float, float]:
    split_metrics = trial["split_metrics"]
    return (
        float(split_metrics.get(primary_split, {}).get("accuracy", 0.0)),
        float(split_metrics.get(secondary_split, {}).get("accuracy", 0.0)),
        float(split_metrics.get("train", {}).get("accuracy", 0.0)),
        int(trial["epochs"]),
        -float(trial["l2"]),
        -float(trial["learning_rate"]),
    )


def keyed_majority_predictions(
    examples: list[dict[str, Any]],
    key_field: str,
    fallback_prediction: str,
) -> list[str]:
    train_targets_by_key: dict[str, list[str]] = {}
    for example in examples:
        if example["split"] != "train":
            continue
        train_targets_by_key.setdefault(str(example[key_field]), []).append(
            example["target"]
        )

    predictions = []
    for example in examples:
        matching_train_targets = train_targets_by_key.get(str(example[key_field]), [])
        if matching_train_targets:
            predictions.append(_majority_label(matching_train_targets))
        else:
            predictions.append(fallback_prediction)
    return predictions


def unseen_labels_by_split(
    examples: list[dict[str, Any]],
    train_labels: set[str],
) -> dict[str, list[str]]:
    unseen = {}
    for split in sorted({example["split"] for example in examples}):
        split_labels = {example["target"] for example in examples if example["split"] == split}
        unseen[split] = sorted(split_labels - train_labels)
    return unseen


def heuristic_projection_report_entry(
    definition: dict[str, str],
    examples: list[dict[str, str]],
    excluded: dict[str, dict[str, int]],
    split_names: list[str],
) -> dict[str, Any]:
    target_counts = Counter(example["target"] for example in examples)
    train_targets = [
        example["target"] for example in examples if example["split"] == "train"
    ]
    train_labels = set(train_targets)
    majority_prediction = _majority_label(train_targets) if train_targets else None
    split_metrics = {}
    for split in split_names:
        split_targets = [
            example["target"] for example in examples if example["split"] == split
        ]
        split_target_counts = Counter(split_targets)
        split_labels = set(split_targets)
        correct = (
            sum(1 for target in split_targets if target == majority_prediction)
            if majority_prediction is not None
            else 0
        )
        unseen_labels = sorted(split_labels - train_labels)
        split_metrics[split] = {
            "support": len(split_targets),
            "target_label_count": len(split_labels),
            "target_counts": dict(sorted(split_target_counts.items())),
            "majority_accuracy": (
                _safe_div(correct, len(split_targets))
                if majority_prediction is not None
                else None
            ),
            "unseen_label_count": len(unseen_labels),
            "unseen_labels": unseen_labels,
        }

    return {
        "projection_id": definition["projection_id"],
        "target": definition["target"],
        "description": definition["description"],
        "status": "evaluated" if train_targets else "no_train_support",
        "included_target_count": len(examples),
        "excluded_from_target_metrics": excluded,
        "target_label_count": len(target_counts),
        "target_counts": dict(sorted(target_counts.items())),
        "train_majority_prediction": majority_prediction,
        "split_metrics": split_metrics,
    }


def heuristic_projection_value(
    outputs: dict[str, Any],
    projection_id: str,
) -> str | None:
    if projection_id in ("result_signature_key", "component_topology_family"):
        return _nonempty_output_string(outputs, projection_id)
    if projection_id == "component_value_digest_pair":
        return _projection_pair(
            _nonempty_output_string(outputs, "left_component_value_digest"),
            _nonempty_output_string(outputs, "right_component_value_digest"),
        )

    topology = _nonempty_output_string(outputs, "component_topology_family")
    material_pair = _component_material_pair(outputs)
    mobility_pair = _component_mobility_pair(outputs)
    if projection_id == "component_material_pair":
        return material_pair
    if projection_id == "component_mobility_pair":
        return mobility_pair
    if projection_id == "net_material_balance":
        return _net_material_balance(outputs)
    if projection_id == "topology_material_pair":
        return _projection_join(topology, material_pair)
    if projection_id == "topology_mobility_pair":
        return _projection_join(topology, mobility_pair)
    if projection_id == "topology_material_mobility_pair":
        return _projection_join(topology, material_pair, mobility_pair)
    return None


def exact_projection_value(
    value: dict[str, Any],
    projection_id: str,
) -> str | None:
    return heuristic_projection_value(value, projection_id)


def exact_projection_definition_target(projection_id: str) -> str:
    for definition in EXACT_SIGNATURE_TARGET_PROJECTIONS:
        if definition["projection_id"] == projection_id:
            return str(definition["target"])
    return f"exact.value.{projection_id}"


def fen_material_probe_features(row: dict[str, Any]) -> list[float] | None:
    features = derive_position_features(row)
    if features["position_encoding"] != FEN_GATE_POSITION_ENCODING:
        return None
    return [
        1.0,
        float(features["empty_square_count"]),
        float(features["piece_count"]),
        float(features["white_piece_count"]),
        float(features["black_piece_count"]),
        float(features["king_count"]),
        float(features["queen_count"]),
        float(features["rook_count"]),
        float(features["bishop_count"]),
        float(features["knight_count"]),
        float(features["pawn_count"]),
        float(features["material_balance"]),
        float(features["absolute_material"]),
        1.0 if features["side_to_move"] == "w" else 0.0,
    ]


def signature_metadata_probe_parts(row: dict[str, Any]) -> dict[str, Any] | None:
    value = exact_value_payload(row)
    fen_features = fen_material_probe_features(row)
    if fen_features is None or not value:
        return None

    left_parts = _component_signature_parts(value, "left")
    right_parts = _component_signature_parts(value, "right")
    if left_parts is None or right_parts is None:
        return None
    left_material = parse_int_metadata(left_parts.get("material"))
    right_material = parse_int_metadata(right_parts.get("material"))
    left_moves = parse_component_local_move_totals(left_parts.get("moves"))
    right_moves = parse_component_local_move_totals(right_parts.get("moves"))
    if (
        left_material is None
        or right_material is None
        or left_moves is None
        or right_moves is None
    ):
        return None

    total_white_moves = left_moves["white"] + right_moves["white"]
    total_black_moves = left_moves["black"] + right_moves["black"]
    return {
        "fen_material": fen_features,
        "left_component_material": float(left_material),
        "right_component_material": float(right_material),
        "net_component_material": float(left_material + right_material),
        "left_white_local_moves": float(left_moves["white"]),
        "left_black_local_moves": float(left_moves["black"]),
        "right_white_local_moves": float(right_moves["white"]),
        "right_black_local_moves": float(right_moves["black"]),
        "total_white_local_moves": float(total_white_moves),
        "total_black_local_moves": float(total_black_moves),
        "component_local_move_imbalance": float(
            parse_int_metadata(value.get("component_local_move_imbalance")) or 0
        ),
        "component_recursive_total_nodes": float(
            parse_int_metadata(value.get("component_recursive_total_nodes")) or 0
        ),
        "total_recursive_nodes": float(
            parse_int_metadata(value.get("total_recursive_nodes")) or 0
        ),
        "left_profile_index": float(
            parse_int_metadata(value.get("left_profile_index")) or 0
        ),
        "right_profile_index": float(
            parse_int_metadata(value.get("right_profile_index")) or 0
        ),
    }


def signature_metadata_probe_features(row: dict[str, Any]) -> list[float] | None:
    parts = signature_metadata_probe_parts(row)
    if parts is None:
        return None
    return [
        *parts["fen_material"],
        parts["left_component_material"],
        parts["right_component_material"],
        parts["net_component_material"],
        parts["left_white_local_moves"],
        parts["left_black_local_moves"],
        parts["right_white_local_moves"],
        parts["right_black_local_moves"],
        parts["total_white_local_moves"],
        parts["total_black_local_moves"],
        parts["component_local_move_imbalance"],
        parts["component_recursive_total_nodes"],
        parts["total_recursive_nodes"],
        parts["left_profile_index"],
        parts["right_profile_index"],
    ]


def exact_projection_ablation_feature_groups(
    row: dict[str, Any],
) -> dict[str, list[float]] | None:
    parts = signature_metadata_probe_parts(row)
    if parts is None:
        return None

    component_material = [
        1.0,
        parts["left_component_material"],
        parts["right_component_material"],
        parts["net_component_material"],
    ]
    component_mobility = [
        1.0,
        parts["left_white_local_moves"],
        parts["left_black_local_moves"],
        parts["right_white_local_moves"],
        parts["right_black_local_moves"],
        parts["total_white_local_moves"],
        parts["total_black_local_moves"],
        parts["component_local_move_imbalance"],
    ]
    component_nodes = [
        1.0,
        parts["component_recursive_total_nodes"],
        parts["total_recursive_nodes"],
    ]
    component_profile_indices = [
        1.0,
        parts["left_profile_index"],
        parts["right_profile_index"],
    ]
    component_material_mobility = [
        *component_material,
        *component_mobility[1:],
    ]
    component_metadata_no_fen_no_profile = [
        *component_material_mobility,
        *component_nodes[1:],
    ]
    component_metadata_no_fen_full = [
        *component_metadata_no_fen_no_profile,
        *component_profile_indices[1:],
    ]
    signature_metadata_no_profile = [
        *parts["fen_material"],
        *component_metadata_no_fen_no_profile[1:],
    ]
    return {
        "fen_material": list(parts["fen_material"]),
        "component_material": component_material,
        "component_mobility": component_mobility,
        "component_nodes": component_nodes,
        "component_profile_indices": component_profile_indices,
        "component_material_mobility": component_material_mobility,
        "component_metadata_no_fen_no_profile": component_metadata_no_fen_no_profile,
        "component_metadata_no_fen_full": component_metadata_no_fen_full,
        "signature_metadata_no_profile": signature_metadata_no_profile,
        "signature_metadata_full": [
            *parts["fen_material"],
            *component_metadata_no_fen_full[1:],
        ],
    }


def signature_metadata_feature_key(value: dict[str, Any]) -> str:
    signature = {
        "component_signature_rule": _nonempty_output_string(
            value, "component_signature_rule"
        )
        or "__missing__",
        "component_material_pair": _component_material_pair(value) or "__missing__",
        "component_mobility_pair": _component_mobility_pair(value) or "__missing__",
        "component_recursive_total_nodes": str(
            value.get("component_recursive_total_nodes", "__missing__")
        ),
        "component_value_classes": str(
            value.get("component_value_classes", "__missing__")
        ),
        "signature_target_rule": str(value.get("signature_target_rule", "__missing__")),
    }
    return json.dumps(signature, sort_keys=True, separators=(",", ":"))


def train_multiclass_logistic_probe(
    features: list[list[float]],
    targets: list[str],
    labels: tuple[str, ...],
    epochs: int,
    learning_rate: float,
    l2: float,
) -> dict[str, Any]:
    if not features:
        raise ValueError("multiclass logistic probe requires training features")
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
        scale_probe_features(vector, means, scales) for vector in features
    ]
    label_to_index = {label: index for index, label in enumerate(labels)}
    weights = [[0.0] * feature_count for _label in labels]
    for _epoch in range(epochs):
        gradients = [[0.0] * feature_count for _label in labels]
        for vector, target in zip(scaled_features, targets):
            probabilities = softmax(
                [
                    sum(weight * value for weight, value in zip(label_weights, vector))
                    for label_weights in weights
                ]
            )
            target_index = label_to_index[target]
            for label_index, probability in enumerate(probabilities):
                error = probability - (1.0 if label_index == target_index else 0.0)
                for feature_index, value in enumerate(vector):
                    gradients[label_index][feature_index] += error * value
        for label_index, label_weights in enumerate(weights):
            for feature_index in range(feature_count):
                regularization = (
                    0.0
                    if feature_index == 0
                    else l2 * label_weights[feature_index]
                )
                label_weights[feature_index] -= learning_rate * (
                    gradients[label_index][feature_index] / len(scaled_features)
                    + regularization
                )

    return {
        "labels": list(labels),
        "weights": weights,
        "means": means,
        "scales": scales,
    }


def multiclass_logistic_predict(model: dict[str, Any], features: list[float]) -> str:
    probabilities = multiclass_logistic_probabilities(model, features)
    labels = list(model["labels"])
    best_index = max(range(len(labels)), key=lambda index: probabilities[index])
    return labels[best_index]


def multiclass_logistic_probabilities(
    model: dict[str, Any],
    features: list[float],
) -> list[float]:
    scaled = scale_probe_features(features, model["means"], model["scales"])
    return softmax(
        [
            sum(weight * value for weight, value in zip(label_weights, scaled))
            for label_weights in model["weights"]
        ]
    )


def multiclass_model_summary(model: dict[str, Any]) -> dict[str, Any]:
    weights = [
        abs(weight)
        for label_weights in model["weights"]
        for weight in label_weights
    ]
    return {
        "label_count": len(model["labels"]),
        "feature_count": len(model["weights"][0]) if model["weights"] else 0,
        "max_abs_weight": max(weights) if weights else 0.0,
    }


def scale_probe_features(
    features: list[float], means: list[float], scales: list[float]
) -> list[float]:
    return [
        features[0],
        *[
            (features[index] - means[index]) / scales[index]
            for index in range(1, len(features))
        ],
    ]


def softmax(logits: list[float]) -> list[float]:
    if not logits:
        return []
    max_logit = max(logits)
    exponentials = [
        math.exp(max(-40.0, min(40.0, logit - max_logit)))
        for logit in logits
    ]
    total = sum(exponentials)
    if total == 0.0:
        return [1.0 / len(logits) for _logit in logits]
    return [value / total for value in exponentials]


def _nonempty_output_string(outputs: dict[str, Any], field: str) -> str | None:
    value = outputs.get(field)
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _component_material_pair(outputs: dict[str, Any]) -> str | None:
    left_parts = _component_signature_parts(outputs, "left")
    right_parts = _component_signature_parts(outputs, "right")
    if left_parts is None or right_parts is None:
        return None
    return _projection_pair(left_parts.get("material"), right_parts.get("material"))


def _component_mobility_pair(outputs: dict[str, Any]) -> str | None:
    left_parts = _component_signature_parts(outputs, "left")
    right_parts = _component_signature_parts(outputs, "right")
    if left_parts is None or right_parts is None:
        return None
    return _projection_pair(left_parts.get("moves"), right_parts.get("moves"))


def _net_material_balance(outputs: dict[str, Any]) -> str | None:
    left_parts = _component_signature_parts(outputs, "left")
    right_parts = _component_signature_parts(outputs, "right")
    if left_parts is None or right_parts is None:
        return None
    try:
        net = int(str(left_parts.get("material"))) + int(str(right_parts.get("material")))
    except ValueError:
        return None
    return f"net:{net}"


def _component_signature_parts(
    outputs: dict[str, Any],
    side: str,
) -> dict[str, str] | None:
    signature = _nonempty_output_string(outputs, f"{side}_component_signature")
    if signature is None:
        return None
    parts = {}
    for part in signature.split(";"):
        if ":" not in part:
            return None
        key, value = part.split(":", 1)
        if not key or not value:
            return None
        parts[key] = value
    return parts


def _component_signature_has_required_parts(parts: dict[str, str] | None) -> bool:
    if parts is None:
        return False
    return all(parts.get(key) for key in ("value", "material", "moves"))


def _projection_pair(left: str | None, right: str | None) -> str | None:
    if left is None or right is None:
        return None
    return f"left:{left};right:{right}"


def _projection_join(*parts: str | None) -> str | None:
    if any(part is None for part in parts):
        return None
    return "|".join(str(part) for part in parts)


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
                "composition_spec_source": composition_spec_source(row)
                or MISSING_COMPOSITION_SPEC_SOURCE,
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


def composition_spec_source(row: dict[str, Any]) -> str | None:
    source = exact_value_payload(row).get("composition_spec_source")
    if not isinstance(source, str):
        return None
    source = source.strip()
    return source or None


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


def topology_balanced_assignments_for_rows(
    rows: list[dict[str, Any]], split_key_mode: str
) -> list[dict[str, Any]]:
    grouped: dict[str, list[tuple[int, dict[str, Any], str, str, str | None, str]]] = {}
    for index, row in enumerate(rows):
        family = generator_family(row)
        position_key = position_key_for_row(row)
        symmetry_position_key = symmetry_position_key_for_row(row)
        split_key = split_key_for_mode(
            family, position_key, symmetry_position_key, split_key_mode
        )
        balance_key = (
            composition_topology_family(row)
            or f"__{str(row.get('label_kind') or 'unknown')}_missing_topology__"
        )
        grouped.setdefault(balance_key, []).append(
            (index, row, family, position_key, symmetry_position_key, split_key)
        )

    assignments: list[dict[str, Any] | None] = [None] * len(rows)
    for group_entries in grouped.values():
        ordered = sorted(
            group_entries,
            key=lambda entry: (
                hashlib.sha256(entry[5].encode("utf-8")).hexdigest(),
                str(entry[1].get("row_id")),
            ),
        )
        train_count = (len(ordered) * 2) // 3
        dev_count = len(ordered) // 6
        for rank, (index, row, family, position_key, symmetry_position_key, split_key) in enumerate(
            ordered
        ):
            if rank < train_count:
                split = "train"
            elif rank < train_count + dev_count:
                split = "dev"
            else:
                split = "test"
            assignments[index] = split_assignment_for_row(
                row,
                split,
                family,
                position_key,
                symmetry_position_key,
                split_key,
            )

    return [assignment for assignment in assignments if assignment is not None]


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
        "composition_spec_source": _optional_non_empty_str(
            exact_value.get("composition_spec_source")
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
        "composition_spec_source_counts": _nested_count_by(
            assignments, "split", "composition_spec_source"
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
    label_kind = str(row.get("label_kind") or "unknown")
    return f"unprovenanced_{label_kind}"


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
    if holdout_selector == "composition_spec_source":
        return _optional_non_empty_str(
            exact_value_payload(row).get("composition_spec_source")
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

    heuristic_target_parser = subcommands.add_parser(
        "heuristic-target-report",
        help="Evaluate heuristic output targets per split with a train majority floor.",
    )
    heuristic_target_parser.add_argument("jsonl_path", type=Path)
    heuristic_target_parser.add_argument("--target-field", required=True)
    heuristic_target_parser.add_argument(
        "--heuristic-method",
        help="Optional heuristic.method filter.",
    )
    heuristic_target_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for split assignment.",
    )
    heuristic_target_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the heuristic target report JSON.",
    )

    heuristic_projection_parser = subcommands.add_parser(
        "heuristic-target-projection-report",
        help="Screen candidate projections of heuristic signature targets.",
    )
    heuristic_projection_parser.add_argument("jsonl_path", type=Path)
    heuristic_projection_parser.add_argument(
        "--heuristic-method",
        help="Optional heuristic.method filter.",
    )
    heuristic_projection_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for split assignment.",
    )
    heuristic_projection_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the heuristic projection report JSON.",
    )

    exact_projection_parser = subcommands.add_parser(
        "exact-target-projection-report",
        help="Screen candidate projections of exact signature metadata targets.",
    )
    exact_projection_parser.add_argument("jsonl_path", type=Path)
    exact_projection_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for split assignment.",
    )
    exact_projection_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the exact projection report JSON.",
    )

    exact_projection_baseline_parser = subcommands.add_parser(
        "exact-projection-baseline-report",
        help="Score deterministic and learned baselines for exact projection targets.",
    )
    exact_projection_baseline_parser.add_argument("jsonl_path", type=Path)
    exact_projection_baseline_parser.add_argument(
        "--target-projection",
        action="append",
        choices=tuple(
            definition["projection_id"]
            for definition in EXACT_SIGNATURE_TARGET_PROJECTIONS
        ),
        help=(
            "Projection id to score. Repeat for multiple projections. "
            "Defaults to compact Wave 53 targets."
        ),
    )
    exact_projection_baseline_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for split assignment.",
    )
    exact_projection_baseline_parser.add_argument(
        "--epochs",
        type=int,
        default=1000,
        help="Training epochs for multiclass logistic probes.",
    )
    exact_projection_baseline_parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.05,
        help="Learning rate for multiclass logistic probes.",
    )
    exact_projection_baseline_parser.add_argument(
        "--l2",
        type=float,
        default=0.001,
        help="L2 regularization for multiclass logistic probes.",
    )
    exact_projection_baseline_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the exact projection baseline report JSON.",
    )

    exact_projection_topology_balanced_parser = subcommands.add_parser(
        "exact-projection-topology-balanced-baseline-report",
        help="Score exact projection baselines on a topology-balanced split.",
    )
    exact_projection_topology_balanced_parser.add_argument("jsonl_path", type=Path)
    exact_projection_topology_balanced_parser.add_argument(
        "--target-projection",
        action="append",
        choices=tuple(
            definition["projection_id"]
            for definition in EXACT_SIGNATURE_TARGET_PROJECTIONS
        ),
        help=(
            "Projection id to score. Repeat for multiple projections. "
            "Defaults to compact Wave 53 targets."
        ),
    )
    exact_projection_topology_balanced_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for ordering rows within each topology.",
    )
    exact_projection_topology_balanced_parser.add_argument(
        "--epochs",
        type=int,
        default=1000,
        help="Training epochs for multiclass logistic probes.",
    )
    exact_projection_topology_balanced_parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.05,
        help="Learning rate for multiclass logistic probes.",
    )
    exact_projection_topology_balanced_parser.add_argument(
        "--l2",
        type=float,
        default=0.001,
        help="L2 regularization for multiclass logistic probes.",
    )
    exact_projection_topology_balanced_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the topology-balanced baseline report JSON.",
    )

    exact_projection_topology_ablation_parser = subcommands.add_parser(
        "exact-projection-topology-balanced-ablation-report",
        help="Score feature-group ablations for exact projections on a topology-balanced split.",
    )
    exact_projection_topology_ablation_parser.add_argument("jsonl_path", type=Path)
    exact_projection_topology_ablation_parser.add_argument(
        "--target-projection",
        action="append",
        choices=tuple(
            definition["projection_id"]
            for definition in EXACT_SIGNATURE_TARGET_PROJECTIONS
        ),
        help=(
            "Projection id to score. Repeat for multiple projections. "
            "Defaults to compact Wave 53 targets."
        ),
    )
    exact_projection_topology_ablation_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for ordering rows within each topology.",
    )
    exact_projection_topology_ablation_parser.add_argument(
        "--epochs",
        type=int,
        default=1000,
        help="Training epochs for multiclass logistic probes.",
    )
    exact_projection_topology_ablation_parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.05,
        help="Learning rate for multiclass logistic probes.",
    )
    exact_projection_topology_ablation_parser.add_argument(
        "--l2",
        type=float,
        default=0.001,
        help="L2 regularization for multiclass logistic probes.",
    )
    exact_projection_topology_ablation_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the topology-balanced ablation report JSON.",
    )

    exact_projection_topology_sweep_parser = subcommands.add_parser(
        "exact-projection-topology-balanced-ablation-sweep-report",
        help="Sweep feature-group probe hyperparameters on a topology-balanced split.",
    )
    exact_projection_topology_sweep_parser.add_argument("jsonl_path", type=Path)
    exact_projection_topology_sweep_parser.add_argument(
        "--target-projection",
        choices=tuple(
            definition["projection_id"]
            for definition in EXACT_SIGNATURE_TARGET_PROJECTIONS
        ),
        default="component_topology_family",
        help="Projection id to sweep. Defaults to component_topology_family.",
    )
    exact_projection_topology_sweep_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for ordering rows within each topology.",
    )
    exact_projection_topology_sweep_parser.add_argument(
        "--sweep-epoch",
        action="append",
        type=int,
        help="Epoch count to include in the sweep. Repeat for multiple values.",
    )
    exact_projection_topology_sweep_parser.add_argument(
        "--sweep-learning-rate",
        action="append",
        type=float,
        help="Learning rate to include in the sweep. Repeat for multiple values.",
    )
    exact_projection_topology_sweep_parser.add_argument(
        "--sweep-l2",
        action="append",
        type=float,
        help="L2 regularization value to include in the sweep. Repeat for multiple values.",
    )
    exact_projection_topology_sweep_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the topology-balanced sweep report JSON.",
    )

    heuristic_signature_promotion_parser = subcommands.add_parser(
        "heuristic-signature-promotion-report",
        help="Audit heuristic signature rows for promotion readiness and blockers.",
    )
    heuristic_signature_promotion_parser.add_argument("jsonl_path", type=Path)
    heuristic_signature_promotion_parser.add_argument(
        "--heuristic-method",
        help="Optional heuristic.method filter.",
    )
    heuristic_signature_promotion_parser.add_argument(
        "--split-key-mode",
        choices=("position", "symmetry"),
        default="position",
        help="Position key policy used for split assignment.",
    )
    heuristic_signature_promotion_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the promotion-readiness report JSON.",
    )
    heuristic_signature_promotion_parser.add_argument(
        "--fail-on-row-contract",
        action="store_true",
        help="Exit nonzero when heuristic signature row contract checks fail.",
    )

    signature_contract_parser = subcommands.add_parser(
        "signature-profile-contract-report",
        help="Validate a signature-profile search report as a diagnostic target contract.",
    )
    signature_contract_parser.add_argument("report_json_path", type=Path)
    signature_contract_parser.add_argument(
        "--rows-per-family-target",
        type=int,
        default=10,
        help="Minimum selected diagnostic rows required per topology family.",
    )
    signature_contract_parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the contract report JSON.",
    )
    signature_contract_parser.add_argument(
        "--fail-on-support-gate",
        action="store_true",
        help="Exit nonzero when the signature support gate does not pass.",
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

    if args.command == "heuristic-target-report":
        try:
            report = evaluate_heuristic_target_report(
                args.jsonl_path,
                args.target_field,
                split_key_mode=args.split_key_mode,
                heuristic_method=args.heuristic_method,
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
        return 0

    if args.command == "heuristic-target-projection-report":
        report = evaluate_heuristic_target_projection_report(
            args.jsonl_path,
            split_key_mode=args.split_key_mode,
            heuristic_method=args.heuristic_method,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print_json_report(report)
        return 0

    if args.command == "exact-target-projection-report":
        report = evaluate_exact_target_projection_report(
            args.jsonl_path,
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

    if args.command == "exact-projection-baseline-report":
        report = evaluate_exact_projection_baseline_report(
            args.jsonl_path,
            target_projections=args.target_projection,
            split_key_mode=args.split_key_mode,
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

    if args.command == "exact-projection-topology-balanced-baseline-report":
        report = evaluate_exact_projection_topology_balanced_baseline_report(
            args.jsonl_path,
            target_projections=args.target_projection,
            split_key_mode=args.split_key_mode,
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

    if args.command == "exact-projection-topology-balanced-ablation-report":
        report = evaluate_exact_projection_topology_balanced_ablation_report(
            args.jsonl_path,
            target_projections=args.target_projection,
            split_key_mode=args.split_key_mode,
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

    if args.command == "exact-projection-topology-balanced-ablation-sweep-report":
        report = evaluate_exact_projection_topology_balanced_ablation_sweep_report(
            args.jsonl_path,
            target_projection=args.target_projection,
            split_key_mode=args.split_key_mode,
            sweep_epochs=args.sweep_epoch,
            sweep_learning_rates=args.sweep_learning_rate,
            sweep_l2=args.sweep_l2,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print_json_report(report)
        return 0

    if args.command == "heuristic-signature-promotion-report":
        report = evaluate_heuristic_signature_promotion_report(
            args.jsonl_path,
            split_key_mode=args.split_key_mode,
            heuristic_method=args.heuristic_method,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print_json_report(report)
        if args.fail_on_row_contract and not report["row_contract_gate"]["passed"]:
            for error in report["row_contract_gate"]["validation_errors"]:
                print(f"signature row-contract violation: {error}", file=sys.stderr)
            return 1
        return 0

    if args.command == "signature-profile-contract-report":
        try:
            report = evaluate_signature_profile_contract_report(
                args.report_json_path,
                rows_per_family_target=args.rows_per_family_target,
            )
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print_json_report(report)
        if args.fail_on_support_gate and not report["support_gate"]["passed"]:
            for error in report["support_gate"]["validation_errors"]:
                print(f"signature support violation: {error}", file=sys.stderr)
            return 1
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
