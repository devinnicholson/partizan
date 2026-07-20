import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from ml_model import (
    FIXTURE_COMPONENT_SUM_RULE,
    composition_certificate_metadata,
    composition_component_family,
    evaluate_composition_baseline_report,
    evaluate_composition_holdout_report,
    evaluate_composition_topology_benchmark_report,
    evaluate_geometry_probe_report,
    evaluate_family_holdout_report,
    evaluate_family_holdout_report_with_mode,
    evaluate_exact_projection_baseline_report,
    evaluate_frontier_target_report,
    evaluate_heuristic_signature_promotion_report,
    evaluate_heuristic_target_projection_report,
    evaluate_heuristic_target_report,
    evaluate_label_shard_baseline,
    evaluate_split_baseline_report,
    evaluate_split_report,
    evaluate_split_report_with_mode,
    evaluate_signature_profile_contract_report,
    exact_certificate_digest,
    fen_d4_symmetry_key,
    fixture_component_integer_sum,
    generator_family,
    leakage_report_violations,
    report_passes_leakage_gate,
    split_for_key,
    train_dev_split_for_key,
)

try:
    import partizan
except ModuleNotFoundError:
    partizan = None


ROOT = Path(__file__).resolve().parents[1]
WAVE_3_SHARD = ROOT / "agents" / "fixtures" / "label_rows.valid.jsonl"
FRONTIER_WAVE_6_SHARD = ROOT / "artifacts" / "legacy" / "partizan-frontier-wave-06.jsonl"
FAMILY_FRONTIER_WAVE_7_SHARD = (
    ROOT / "artifacts" / "legacy" / "partizan-family-frontier-wave-07.jsonl"
)
EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD = (
    ROOT / "artifacts" / "legacy" / "partizan-expanded-family-frontier-wave-12.jsonl"
)


def run_symmetry_key_smoke():
    fen = "7K/8/8/8/8/8/8/Q5k1 w - - 0 1"
    mirrored_fen = "K7/8/8/8/8/8/8/1k5Q w - - 0 1"
    assert fen_d4_symmetry_key(fen) == fen_d4_symmetry_key(mirrored_fen)
    assert fen_d4_symmetry_key("7K/8/8/8/8/8/8/Q5k1 w K - 0 1") is None


def run_composition_certificate_report_smoke():
    certificate = {
        "kind": "bitmesh-bmcompose-v1+thermograph-exact-value",
        "digest": "sha256:aggregate-composition",
        "decomposition_digest": "sha256:strict-decomposition",
        "composition_digest": "sha256:bmcompose",
        "component_values": {
            "0": "sha256:component-a",
            "63": "sha256:component-b",
        },
        "result_value_digest": "sha256:composed-result",
    }
    legacy_certificate = {
        "kind": "legacy-exact",
        "digest": "sha256:legacy-exact-certificate",
    }
    composition_row = _composition_fixture_row(
        "composition-metadata-row",
        "8/8/8/8/8/8/K7/7k w - - 0 1",
        certificate,
    )
    metadata = composition_certificate_metadata(composition_row)
    assert metadata == {
        "decomposition_digest": "sha256:strict-decomposition",
        "composition_digest": "sha256:bmcompose",
        "component_count": 2,
        "component_family": "count:2|roots:0,63",
        "component_values": {
            "0": "sha256:component-a",
            "63": "sha256:component-b",
        },
        "component_roots": ["0", "63"],
        "component_value_digests": [
            "sha256:component-a",
            "sha256:component-b",
        ],
        "result_value_digest": "sha256:composed-result",
    }

    legacy_row = _composition_fixture_row(
        "legacy-certificate-row",
        "8/8/8/8/8/8/1K6/6k1 w - - 0 1",
        legacy_certificate,
    )
    assert exact_certificate_digest(legacy_row) == "sha256:legacy-exact-certificate"
    assert composition_certificate_metadata(legacy_row) == {
        "decomposition_digest": None,
        "composition_digest": None,
        "component_count": None,
        "component_family": None,
        "component_values": {},
        "component_roots": [],
        "component_value_digests": [],
        "result_value_digest": None,
    }

    train_row = _composition_fixture_row_for_split(
        "composition-train",
        "train",
        certificate,
    )
    test_row = _composition_fixture_row_for_split(
        "composition-test",
        "test",
        certificate,
    )
    legacy_row = _composition_fixture_row_for_split(
        "legacy-dev",
        "dev",
        legacy_certificate,
    )

    with TemporaryDirectory() as temp_dir:
        shard_path = Path(temp_dir) / "composition-smoke.jsonl"
        shard_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in [
                train_row,
                test_row,
                legacy_row,
            ])
            + "\n",
            encoding="utf-8",
        )
        report = evaluate_split_report(shard_path)

    assert report["composition_certificate_counts"]["rows_by_split"] == {
        "test": 1,
        "train": 1,
    }
    assert report["composition_certificate_counts"]["component_count_by_split"] == {
        "test": {"2": 1},
        "train": {"2": 1},
    }
    assert report["composition_certificate_counts"]["component_family_by_split"] == {
        "test": {"count:2|roots:0,63": 1},
        "train": {"count:2|roots:0,63": 1},
    }
    assert report["composition_certificate_counts"][
        "component_root_counts_by_split"
    ] == {
        "test": {"0": 1, "63": 1},
        "train": {"0": 1, "63": 1},
    }

    leakage = report["leakage_checks"]
    assert leakage["exact_certificate_digest_cross_split"]["violation_count"] == 1
    assert leakage["decomposition_digest_cross_split"]["violation_count"] == 1
    assert leakage["composition_digest_cross_split"]["violation_count"] == 1
    assert leakage["result_value_digest_cross_split"]["violation_count"] == 1
    assert leakage["component_root_cross_split"]["violation_count"] == 2
    assert leakage["component_value_digest_cross_split"]["violation_count"] == 2
    assert leakage["component_value_pair_cross_split"]["violation_count"] == 2
    assert not report_passes_leakage_gate(report)
    assert any(
        "composition_digest_cross_split" in violation
        for violation in leakage_report_violations(report)
    )

    with TemporaryDirectory() as temp_dir:
        clean_path = Path(temp_dir) / "composition-clean-smoke.jsonl"
        clean_path.write_text(
            json.dumps(train_row, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        clean_report = evaluate_split_report(clean_path)
    assert report_passes_leakage_gate(clean_report)


def run_composition_holdout_report_smoke():
    shared_count_holdout_certificate = {
        "kind": "bitmesh-bmcompose-v1+thermograph-exact-value",
        "digest": "sha256:shared-count-holdout-certificate",
        "decomposition_digest": "sha256:shared-decomposition",
        "composition_digest": "sha256:shared-composition",
        "component_values": {
            "0": "sha256:shared-component-a",
            "63": "sha256:shared-component-b",
        },
        "result_value_digest": "sha256:shared-result",
    }
    count_only_holdout_certificate = {
        "kind": "bitmesh-bmcompose-v1+thermograph-exact-value",
        "digest": "sha256:count-only-holdout-certificate",
        "decomposition_digest": "sha256:count-only-decomposition",
        "composition_digest": "sha256:count-only-composition",
        "component_values": {
            "1": "sha256:count-only-component-a",
            "62": "sha256:count-only-component-b",
        },
        "result_value_digest": "sha256:count-only-result",
    }
    train_leakage_certificate = {
        "kind": "bitmesh-bmcompose-v1+thermograph-exact-value",
        "digest": "sha256:train-leakage-certificate",
        "decomposition_digest": "sha256:shared-decomposition",
        "composition_digest": "sha256:shared-composition",
        "component_values": {
            "0": "sha256:shared-component-a",
        },
        "result_value_digest": "sha256:shared-result",
    }
    rejected_matching_certificate = {
        "kind": "bitmesh-bmcompose-v1+thermograph-exact-value",
        "digest": "sha256:rejected-matching-certificate",
        "decomposition_digest": "sha256:rejected-decomposition",
        "composition_digest": "sha256:rejected-composition",
        "component_values": {
            "2": "sha256:rejected-component-a",
            "61": "sha256:rejected-component-b",
        },
        "result_value_digest": "sha256:rejected-result",
    }

    rows = [
        _composition_fixture_row(
            "composition-holdout-shared",
            "8/8/8/8/8/8/K7/7k w - - 0 11",
            shared_count_holdout_certificate,
            component_topology_family="fixture-topology-shared",
            composition_spec_source="fixture-curated-source",
        ),
        _composition_fixture_row_for_train_dev_split(
            "composition-holdout-count-only",
            "train",
            count_only_holdout_certificate,
            start_index=1000,
            component_topology_family="fixture-topology-shared",
            composition_spec_source="fixture-generated-source",
        ),
        _composition_fixture_row_for_train_dev_split(
            "composition-train-leakage",
            "train",
            train_leakage_certificate,
            start_index=2000,
            component_topology_family="fixture-topology-other",
            composition_spec_source="fixture-curated-source",
        ),
        _composition_rejected_fixture_row_for_train_dev_split(
            "composition-rejected-matching-count",
            "train",
            rejected_matching_certificate,
            start_index=3000,
        ),
    ]

    with TemporaryDirectory() as temp_dir:
        shard_path = Path(temp_dir) / "composition-holdout-smoke.jsonl"
        shard_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
        )
        component_count_report = evaluate_composition_holdout_report(
            shard_path,
            "component_count",
            2,
        )
        composition_digest_report = evaluate_composition_holdout_report(
            shard_path,
            "composition_digest",
            "sha256:shared-composition",
        )
        result_value_digest_report = evaluate_composition_holdout_report(
            shard_path,
            "result_value_digest",
            "sha256:shared-result",
        )
        component_family_report = evaluate_composition_holdout_report(
            shard_path,
            "component_family",
            composition_component_family({"0": "x", "63": "y"}),
        )
        component_topology_family_report = evaluate_composition_holdout_report(
            shard_path,
            "component_topology_family",
            "fixture-topology-shared",
        )
        composition_spec_source_report = evaluate_composition_holdout_report(
            shard_path,
            "composition_spec_source",
            "fixture-generated-source",
        )

    assert (
        component_count_report["splitter_id"]
        == "composition_holdout_component_count_generator_position_hash_v0"
    )
    assert component_count_report["holdout_selector"] == "component_count"
    assert component_count_report["holdout_value"] == "2"
    assert component_count_report["holdout_label_kind"] == "exact"
    assert component_count_report["row_counts"] == {"test": 2, "train": 2}
    assert component_count_report["label_kind_counts"]["test"] == {"exact": 2}
    assert component_count_report["label_kind_counts"]["train"] == {
        "exact": 1,
        "rejected": 1,
    }
    assert component_count_report["composition_certificate_counts"][
        "component_count_by_split"
    ] == {
        "test": {"2": 2},
        "train": {"1": 1, "2": 1},
    }
    leakage = component_count_report["leakage_checks"]
    assert leakage["composition_digest_cross_split"]["violation_count"] == 1
    assert leakage["result_value_digest_cross_split"]["violation_count"] == 1
    assert leakage["component_root_cross_split"]["violation_count"] == 1
    assert leakage["component_value_digest_cross_split"]["violation_count"] == 1
    assert leakage["component_value_pair_cross_split"]["violation_count"] == 1

    assert composition_digest_report["holdout_selector"] == "composition_digest"
    assert composition_digest_report["row_counts"] == {"test": 2, "train": 2}
    assert composition_digest_report["label_kind_counts"]["test"] == {"exact": 2}

    assert result_value_digest_report["holdout_selector"] == "result_value_digest"
    assert result_value_digest_report["row_counts"] == {"test": 2, "train": 2}
    assert result_value_digest_report["label_kind_counts"]["test"] == {"exact": 2}

    assert component_family_report["holdout_selector"] == "component_family"
    assert component_family_report["row_counts"] == {"test": 1, "train": 3}
    assert component_family_report["label_kind_counts"]["test"] == {"exact": 1}

    assert component_topology_family_report["holdout_selector"] == (
        "component_topology_family"
    )
    assert component_topology_family_report["holdout_value"] == "fixture-topology-shared"
    assert component_topology_family_report["row_counts"] == {
        "test": 2,
        "train": 2,
    }
    assert component_topology_family_report["label_kind_counts"]["test"] == {"exact": 2}
    assert component_topology_family_report["component_topology_family_counts"][
        "test"
    ] == {"fixture-topology-shared": 2}

    assert composition_spec_source_report["holdout_selector"] == (
        "composition_spec_source"
    )
    assert composition_spec_source_report["holdout_value"] == "fixture-generated-source"
    assert composition_spec_source_report["row_counts"] == {"test": 1, "train": 3}
    assert composition_spec_source_report["label_kind_counts"]["test"] == {
        "exact": 1
    }
    assert composition_spec_source_report["composition_spec_source_counts"][
        "test"
    ] == {"fixture-generated-source": 1}


def run_composition_baseline_rejected_exclusion_smoke():
    report = _composition_baseline_fixture_report()

    assert report["row_counts"] == {"test": 1, "train": 2}
    assert report["label_kind_counts"]["train"] == {"exact": 1, "rejected": 1}
    assert report["label_kind_counts"]["test"] == {"exact": 1}
    assert report["excluded_from_target_metrics"] == {
        "non_exact_rows_by_split": {"train": 1},
        "exact_rows_missing_target_by_split": {},
    }
    assert report["exact_target_counts_by_split"] == {
        "test": {"Number(5/2^0)": 1},
        "train": {"Number(1/2^0)": 1},
    }
    assert report["target_support"] == {
        "train_labels": ["Number(1/2^0)"],
        "labels_by_split": {
            "test": ["Number(5/2^0)"],
            "train": ["Number(1/2^0)"],
        },
        "unseen_labels_by_split": {
            "test": ["Number(5/2^0)"],
            "train": [],
        },
    }
    assert report["component_topology_family_diagnostics"][
        "fixture-heldout-topology"
    ] == {
        "support": 1,
        "split_counts": {"test": 1},
        "target_counts": {"Number(5/2^0)": 1},
        "composition_value_rule_counts": {FIXTURE_COMPONENT_SUM_RULE: 1},
        "composition_spec_source_counts": {"__missing__": 1},
        "local_move_totals": {
            "white": {"count": 1, "min": 2, "max": 2, "mean": 2.0},
            "black": {"count": 1, "min": 3, "max": 3, "mean": 3.0},
        },
        "local_move_imbalance": {
            "count": 1,
            "min": -1,
            "max": -1,
            "mean": -1.0,
        },
        "recursive_total_nodes": {
            "count": 1,
            "min": 8,
            "max": 8,
            "mean": 8.0,
        },
    }

    for predictor_report in report["predictors"].values():
        assert predictor_report["support"] == 2
        assert predictor_report["split_metrics"]["train"]["support"] == 1
        assert predictor_report["split_metrics"]["test"]["support"] == 1
        assert predictor_report["component_topology_family_metrics"][
            "fixture-heldout-topology"
        ]["support"] == 1
        assert predictor_report["component_topology_family_metrics"][
            "fixture-train-topology"
        ]["split_counts"] == {"train": 1}


def run_composition_baseline_component_sum_smoke():
    report = _composition_baseline_fixture_report()

    train_majority_test = report["predictors"]["train_majority"]["split_metrics"][
        "test"
    ]
    assert train_majority_test["accuracy"] == 0.0
    assert train_majority_test["prediction_counts"] == {"Number(1/2^0)": 1}

    fixture_component_sum = report["predictors"]["fixture_component_sum"]
    assert fixture_component_sum["fixture_only"] is True
    assert fixture_component_sum["composition_value_rule_counts"] == {
        FIXTURE_COMPONENT_SUM_RULE: 2
    }
    assert fixture_component_sum["verifier_sanity_check"] is True
    fixture_component_sum_test = fixture_component_sum["split_metrics"]["test"]
    assert fixture_component_sum_test["accuracy"] == 1.0
    assert fixture_component_sum_test["prediction_counts"] == {"Number(5/2^0)": 1}


def run_composition_baseline_component_sum_rule_scope_smoke():
    report = _composition_baseline_fixture_report(
        composition_value_rule="component_material_balance_sum_v0"
    )

    fixture_component_sum = report["predictors"]["fixture_component_sum"]
    assert fixture_component_sum["fixture_only"] is False
    assert fixture_component_sum["composition_value_rule_counts"] == {
        "component_material_balance_sum_v0": 2
    }
    assert fixture_component_sum["verifier_sanity_check"] is True
    assert fixture_component_sum["split_metrics"]["test"]["accuracy"] == 1.0


def run_composition_topology_benchmark_report_smoke():
    rows = [
        _composition_fixture_row_for_train_dev_split(
            "composition-topology-family-a",
            "train",
            _composition_fixture_certificate("family-a", {"0": "sha256:a0"}),
            start_index=0,
            canonical_serialization="Number(1/2^0)",
            digest="sha256:family-a-result",
            component_values_summary="0=Number(1/2^0)",
            component_topology_family="fixture-topology-a",
            composition_spec_source="fixture-curated-source",
            component_local_move_totals="white:1,black:0",
            component_local_move_imbalance="1",
            component_recursive_total_nodes="3",
        ),
        _composition_fixture_row_for_train_dev_split(
            "composition-topology-family-b",
            "train",
            _composition_fixture_certificate(
                "family-b",
                {"0": "sha256:b0", "1": "sha256:b1"},
            ),
            start_index=1000,
            canonical_serialization="Number(5/2^0)",
            digest="sha256:family-b-result",
            component_values_summary="0=Number(2/2^0),1=Number(3/2^0)",
            component_topology_family="fixture-topology-b",
            composition_spec_source="fixture-generated-source",
            component_local_move_totals="white:2,black:3",
            component_local_move_imbalance="-1",
            component_recursive_total_nodes="8",
        ),
        _composition_fixture_row_for_train_dev_split(
            "composition-topology-family-c",
            "train",
            _composition_fixture_certificate(
                "family-c",
                {"0": "sha256:c0", "1": "sha256:c1"},
            ),
            start_index=2000,
            canonical_serialization="Number(9/2^0)",
            digest="sha256:family-c-result",
            component_values_summary="0=Number(4/2^0),1=Number(5/2^0)",
            component_topology_family="fixture-topology-c",
            composition_spec_source="fixture-generated-source",
            component_local_move_totals="white:4,black:5",
            component_local_move_imbalance="-1",
            component_recursive_total_nodes="12",
        ),
    ]

    with TemporaryDirectory() as temp_dir:
        shard_path = Path(temp_dir) / "composition-topology-benchmark-smoke.jsonl"
        shard_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
        )
        report = evaluate_composition_topology_benchmark_report(shard_path)
        min_support_report = evaluate_composition_topology_benchmark_report(
            shard_path, min_family_support=2
        )

    assert report["benchmark_id"] == "composition_topology_family_holdout_benchmark_v0"
    assert report["holdout_selector"] == "component_topology_family"
    assert report["family_count"] == 3
    assert report["families"] == [
        "fixture-topology-a",
        "fixture-topology-b",
        "fixture-topology-c",
    ]
    assert report["leakage_gate_passed"] is True
    assert report["leakage_checks"] == {
        "family_leakage_gate_failures": {
            "violation_count": 0,
            "examples": [],
        }
    }
    assert min_support_report["family_count"] == 0

    reports_by_family = {
        family_report["holdout_value"]: family_report
        for family_report in report["family_reports"]
    }
    assert reports_by_family["fixture-topology-b"]["holdout_support"] == 1
    assert reports_by_family["fixture-topology-b"]["holdout_split_counts"] == {
        "test": 1
    }
    assert reports_by_family["fixture-topology-b"][
        "holdout_recursive_total_nodes"
    ] == {
        "count": 1,
        "min": 8,
        "max": 8,
        "mean": 8.0,
    }
    assert reports_by_family["fixture-topology-b"]["holdout_spec_source_counts"] == {
        "fixture-generated-source": 1
    }
    for family_report in report["family_reports"]:
        assert family_report["leakage_gate_passed"] is True
        assert family_report["leakage_violations"] == []
        assert family_report["predictors"]["fixture_component_sum"]["accuracy"] == 1.0
        assert family_report["predictors"]["fixture_component_sum"][
            "abstention_count"
        ] == 0

    assert report["predictor_accuracy_by_family"]["fixture_component_sum"] == {
        "fixture-topology-a": 1.0,
        "fixture-topology-b": 1.0,
        "fixture-topology-c": 1.0,
    }


def run_composition_component_sum_parser_scope_smoke():
    assert (
        fixture_component_integer_sum("9=Number(4/2^0),13=Number(-3/2^0)")
        == 1
    )
    assert fixture_component_integer_sum("9=Up,13=Down") is None
    assert fixture_component_integer_sum("9=GameTree(L[Star,Up];R[Down]),13=Down") is None


def run_signature_profile_contract_report_smoke():
    assert generator_family({"row_id": "diagnostic-row", "label_kind": "heuristic"}) == (
        "unprovenanced_heuristic"
    )

    families = [
        "dfile_two_component_depth2_local_move_v0",
        "dfile_two_component_depth2_asymmetric_fan_v0",
        "dfile_two_component_depth2_pawn_phalanx_v0",
    ]
    candidates = []
    for family in families:
        for offset in range(2):
            index = len(candidates)
            left_signature = (
                f"value:left-{index};material:{index + 1};"
                f"moves:white:{offset + 1},black:0"
            )
            right_signature = (
                f"value:right-{index};material:-{index + 1};"
                f"moves:white:0,black:{offset + 1}"
            )
            candidates.append(
                {
                    "row_number": index + 1,
                    "topology_family": family,
                    "left_component_signature": left_signature,
                    "right_component_signature": right_signature,
                    "result_signature_key": (
                        f"{family};left:{left_signature};right:{right_signature}"
                    ),
                }
            )

    signature_report = {
        "source": "fixture_signature_source_v0",
        "component_signature_rule": (
            "depth2_value_digest_plus_material_balance_plus_local_move_counts_v0"
        ),
        "rows_per_family_target": 2,
        "left_signature_profile_count": 6,
        "right_signature_profile_count": 6,
        "candidate_pair_counts_by_topology_family": {
            family: 12 for family in families
        },
        "selected_counts_by_topology_family": {family: 2 for family in families},
        "selected_row_count": 6,
        "rejection_counts": {
            "component_signature_reuse_before_materialization": 3,
        },
        "candidates": candidates,
    }

    with TemporaryDirectory() as temp_dir:
        report_path = Path(temp_dir) / "signature-profile-report.json"
        report_path.write_text(
            json.dumps(signature_report, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        contract_report = evaluate_signature_profile_contract_report(
            report_path,
            rows_per_family_target=2,
        )

        duplicate_report = json.loads(json.dumps(signature_report))
        duplicate_report["candidates"][1]["left_component_signature"] = (
            duplicate_report["candidates"][0]["left_component_signature"]
        )
        duplicate_report_path = Path(temp_dir) / "signature-profile-duplicate.json"
        duplicate_report_path.write_text(
            json.dumps(duplicate_report, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        duplicate_contract_report = evaluate_signature_profile_contract_report(
            duplicate_report_path,
            rows_per_family_target=2,
        )

    assert contract_report["report_id"] == "signature_profile_target_contract_report_v0"
    assert contract_report["support_gate"]["passed"] is True
    assert contract_report["support_gate"]["selected_row_count"] == 6
    assert contract_report["support_gate"]["selected_counts_by_topology_family"] == {
        family: 2 for family in families
    }
    assert contract_report["reuse_checks"] == {
        "duplicate_component_signatures": 0,
        "duplicate_result_signature_keys": 0,
    }
    assert contract_report["contract"]["supervision_eligible"] is False
    assert contract_report["promotion_gate"]["passed"] is False
    assert contract_report["contract_status"] == (
        "support_gate_passed_promotion_blocked"
    )

    assert duplicate_contract_report["support_gate"]["passed"] is False
    assert duplicate_contract_report["reuse_checks"]["duplicate_component_signatures"] == 1
    assert any(
        "reuse component signatures" in error
        for error in duplicate_contract_report["support_gate"]["validation_errors"]
    )


def run_heuristic_target_report_smoke():
    rows = [
        _heuristic_fixture_row_for_split(
            "heuristic-train-a",
            "train",
            "signature-a",
            start_index=0,
        ),
        _heuristic_fixture_row_for_split(
            "heuristic-train-b",
            "train",
            "signature-b",
            start_index=1000,
        ),
        _heuristic_fixture_row_for_split(
            "heuristic-dev",
            "dev",
            "signature-dev",
            start_index=2000,
        ),
        _heuristic_fixture_row_for_split(
            "heuristic-test",
            "test",
            "signature-test",
            start_index=3000,
        ),
    ]
    with TemporaryDirectory() as temp_dir:
        shard_path = Path(temp_dir) / "heuristic-target-smoke.jsonl"
        shard_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
        )
        report = evaluate_heuristic_target_report(
            shard_path,
            "result_signature_key",
            heuristic_method="signature_profile_target_diagnostic",
        )

    assert report["report_id"] == "heuristic_target_train_majority_report_v0"
    assert report["target"] == "heuristic.outputs.result_signature_key"
    assert report["included_target_count"] == 4
    assert report["excluded_from_target_metrics"] == {}
    assert report["train_majority_prediction"] == "signature-a"
    assert report["split_metrics"]["train"]["support"] == 2
    assert report["split_metrics"]["train"]["accuracy"] == 0.5
    assert report["split_metrics"]["dev"]["accuracy"] == 0.0
    assert report["split_metrics"]["test"]["accuracy"] == 0.0
    assert report["target_support_coverage"]["unseen_labels_by_split"]["dev"] == [
        "signature-dev"
    ]
    assert report["target_support_coverage"]["unseen_labels_by_split"]["test"] == [
        "signature-test"
    ]


def run_heuristic_target_projection_report_smoke():
    rows = [
        _heuristic_fixture_row_for_split(
            "heuristic-projection-train-a",
            "train",
            "signature-train-a",
            start_index=4000,
            topology="topology-a",
            left_digest="left-a",
            right_digest="right-a",
            left_material=1,
            right_material=-1,
        ),
        _heuristic_fixture_row_for_split(
            "heuristic-projection-train-b",
            "train",
            "signature-train-b",
            start_index=5000,
            topology="topology-b",
            left_digest="left-b",
            right_digest="right-b",
            left_material=2,
            right_material=-2,
        ),
        _heuristic_fixture_row_for_split(
            "heuristic-projection-dev",
            "dev",
            "signature-dev",
            start_index=6000,
            topology="topology-a",
            left_digest="left-a",
            right_digest="right-a",
            left_material=1,
            right_material=-1,
        ),
        _heuristic_fixture_row_for_split(
            "heuristic-projection-test",
            "test",
            "signature-test",
            start_index=7000,
            topology="topology-c",
            left_digest="left-c",
            right_digest="right-c",
            left_material=3,
            right_material=-1,
        ),
    ]
    with TemporaryDirectory() as temp_dir:
        shard_path = Path(temp_dir) / "heuristic-projection-smoke.jsonl"
        shard_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
        )
        report = evaluate_heuristic_target_projection_report(
            shard_path,
            heuristic_method="signature_profile_target_diagnostic",
        )

    assert report["report_id"] == "heuristic_signature_target_projection_report_v0"
    projections = {
        projection["projection_id"]: projection for projection in report["projections"]
    }
    topology = projections["component_topology_family"]
    assert topology["target_label_count"] == 3
    assert topology["train_majority_prediction"] == "topology-a"
    assert topology["split_metrics"]["dev"]["majority_accuracy"] == 1.0
    assert topology["split_metrics"]["test"]["majority_accuracy"] == 0.0
    assert topology["split_metrics"]["test"]["unseen_labels"] == ["topology-c"]

    material = projections["component_material_pair"]
    assert material["split_metrics"]["dev"]["unseen_label_count"] == 0
    assert material["split_metrics"]["test"]["unseen_label_count"] == 1
    assert projections["net_material_balance"]["target_counts"] == {
        "net:0": 3,
        "net:2": 1,
    }


def run_exact_projection_baseline_report_smoke():
    rows = [
        _exact_projection_fixture_row_for_split(
            "exact-projection-train-a",
            "train",
            start_index=11000,
            topology="topology-a",
            left_digest="left-a",
            right_digest="right-a",
            left_material=1,
            right_material=-1,
        ),
        _exact_projection_fixture_row_for_split(
            "exact-projection-train-b",
            "train",
            start_index=12000,
            topology="topology-b",
            left_digest="left-b",
            right_digest="right-b",
            left_material=2,
            right_material=0,
        ),
        _exact_projection_fixture_row_for_split(
            "exact-projection-dev",
            "dev",
            start_index=13000,
            topology="topology-a",
            left_digest="left-a",
            right_digest="right-a",
            left_material=1,
            right_material=-1,
        ),
        _exact_projection_fixture_row_for_split(
            "exact-projection-test",
            "test",
            start_index=14000,
            topology="topology-c",
            left_digest="left-c",
            right_digest="right-c",
            left_material=3,
            right_material=-1,
        ),
    ]
    with TemporaryDirectory() as temp_dir:
        shard_path = Path(temp_dir) / "exact-projection-baseline-smoke.jsonl"
        shard_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
        )
        report = evaluate_exact_projection_baseline_report(
            shard_path,
            epochs=10,
        )

    assert report["report_id"] == "exact_projection_baseline_report_v0"
    assert report["target_projection_count"] == 2
    projections = {
        projection["projection_id"]: projection
        for projection in report["target_projections"]
    }
    topology = projections["component_topology_family"]
    assert topology["target_label_count"] == 3
    assert topology["train_majority_prediction"] == "topology-a"
    assert topology["unseen_labels_by_split"]["test"] == ["topology-c"]
    assert [predictor["predictor_id"] for predictor in topology["predictors"]] == [
        "train_majority",
        "fen_material_feature_majority",
        "signature_metadata_feature_majority",
        "fen_material_multiclass_logistic_probe",
        "signature_metadata_multiclass_logistic_probe",
    ]

    net_material = projections["net_material_balance"]
    assert net_material["target_counts"] == {"net:0": 2, "net:2": 2}
    assert net_material["predictors"][0]["split_metrics"]["train"]["support"] == 2


def run_heuristic_signature_promotion_report_smoke():
    specs = [
        ("heuristic-promotion-train", "train", 8000, "topology-a", "left-a", "right-a", 1, -1),
        ("heuristic-promotion-dev", "dev", 9000, "topology-b", "left-b", "right-b", 2, -2),
        ("heuristic-promotion-test", "test", 10000, "topology-c", "left-c", "right-c", 3, -3),
    ]
    rows = []
    for row_id, split, start_index, topology, left_digest, right_digest, left_material, right_material in specs:
        target = _heuristic_signature_target(
            topology,
            left_digest,
            right_digest,
            left_material,
            right_material,
        )
        rows.append(
            _heuristic_fixture_row_for_split(
                row_id,
                split,
                target,
                start_index=start_index,
                topology=topology,
                left_digest=left_digest,
                right_digest=right_digest,
                left_material=left_material,
                right_material=right_material,
            )
        )

    with TemporaryDirectory() as temp_dir:
        shard_path = Path(temp_dir) / "heuristic-promotion-smoke.jsonl"
        shard_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
        )
        report = evaluate_heuristic_signature_promotion_report(
            shard_path,
            heuristic_method="signature_profile_target_diagnostic",
        )

        bad_rows = json.loads(json.dumps(rows))
        del bad_rows[0]["heuristic"]["outputs"]["target_contract_id"]
        bad_rows[1]["heuristic"]["outputs"]["left_component_signature"] = (
            "value:left-b;material:2"
        )
        bad_path = Path(temp_dir) / "heuristic-promotion-bad.jsonl"
        bad_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in bad_rows) + "\n",
            encoding="utf-8",
        )
        bad_report = evaluate_heuristic_signature_promotion_report(
            bad_path,
            heuristic_method="signature_profile_target_diagnostic",
        )

    assert report["report_id"] == "heuristic_signature_promotion_readiness_report_v0"
    assert report["included_row_count"] == 3
    assert report["row_contract_gate"]["passed"] is True
    assert report["row_contract_gate"]["validation_errors"] == []
    assert report["row_contract_gate"]["target_status_counts"] == {
        "diagnostic_only": 3
    }
    assert report["row_contract_gate"]["supervision_eligible_counts"] == {
        "false": 3
    }
    assert report["reuse_checks"]["duplicate_component_signatures"] == 0
    assert report["reuse_checks"]["duplicate_result_signature_keys"] == 0
    assert report["promotion_gate"]["passed"] is False
    assert report["promotion_gate"]["blocker_counts"][
        "versioned_exact_value_rule_missing"
    ] == 3
    assert report["contract_status"] == "row_contract_passed_promotion_blocked"

    assert bad_report["row_contract_gate"]["passed"] is False
    assert any(
        "missing output field target_contract_id" in error
        for error in bad_report["row_contract_gate"]["validation_errors"]
    )
    assert any(
        "component signatures" in error
        for error in bad_report["row_contract_gate"]["validation_errors"]
    )


def _heuristic_signature_target(
    topology: str,
    left_digest: str,
    right_digest: str,
    left_material: int,
    right_material: int,
    left_moves: str = "white:1,black:0",
    right_moves: str = "white:0,black:1",
) -> str:
    left_signature = f"value:{left_digest};material:{left_material};moves:{left_moves}"
    right_signature = f"value:{right_digest};material:{right_material};moves:{right_moves}"
    return f"{topology};left:{left_signature};right:{right_signature}"


def _heuristic_fixture_row_for_split(
    row_id: str,
    target_split: str,
    target: str,
    start_index: int = 0,
    topology: str = "topology-a",
    left_digest: str = "left-digest-a",
    right_digest: str = "right-digest-a",
    left_material: int = 1,
    right_material: int = -1,
    left_moves: str = "white:1,black:0",
    right_moves: str = "white:0,black:1",
) -> dict[str, object]:
    for index in range(start_index, start_index + 1000):
        fen = f"8/8/8/8/8/8/K7/7k w - - 0 {index + 1}"
        split_key = f"unprovenanced_heuristic|fen:{fen}"
        if split_for_key(split_key) == target_split:
            return {
                "schema_version": "partizan.dataset_label.v0",
                "row_id": row_id,
                "domain": "formal_domain:bitmesh_composed_board_material:v0",
                "position": {"encoding": "fen", "text": fen},
                "label_kind": "heuristic",
                "heuristic": {
                    "method": "signature_profile_target_diagnostic",
                    "method_version": "v0",
                    "outputs": {
                        "component_signature_rule": (
                            "depth2_value_digest_plus_material_balance_plus_local_move_counts_v0"
                        ),
                        "component_topology_family": topology,
                        "composition_spec_source": "signature_profile_target_diagnostic_v0",
                        "current_result_value_digest": f"result-{row_id}",
                        "left_component_signature": (
                            f"value:{left_digest};material:{left_material};"
                            f"moves:{left_moves}"
                        ),
                        "left_component_value_digest": left_digest,
                        "left_profile_index": "0",
                        "promotion_blockers": (
                            "versioned_exact_value_rule_missing;"
                            "replay_compatible_provenance_missing;"
                            "split_semantics_missing;"
                            "deterministic_and_model_baselines_missing"
                        ),
                        "result_signature_key": target,
                        "right_component_signature": (
                            f"value:{right_digest};material:{right_material};"
                            f"moves:{right_moves}"
                        ),
                        "right_component_value_digest": right_digest,
                        "right_profile_index": "1",
                        "row_number": row_id,
                        "supervision_eligible": "false",
                        "target_contract_id": (
                            "depth2_material_mobility_signature_target_contract_v0"
                        ),
                        "target_status": "diagnostic_only",
                        "total_recursive_nodes": "47",
                    },
                },
            }
    raise AssertionError(f"could not find heuristic FEN for split {target_split!r}")


def _exact_projection_fixture_row_for_split(
    row_id: str,
    target_split: str,
    start_index: int = 0,
    topology: str = "topology-a",
    left_digest: str = "left-digest-a",
    right_digest: str = "right-digest-a",
    left_material: int = 1,
    right_material: int = -1,
    left_moves: str = "white:1,black:0",
    right_moves: str = "white:0,black:1",
) -> dict[str, object]:
    for index in range(start_index, start_index + 1000):
        fen = f"8/8/8/8/8/8/K7/7k w - - 0 {index + 1}"
        split_key = f"unprovenanced_exact|fen:{fen}"
        if split_for_key(split_key) == target_split:
            return {
                "schema_version": "partizan.dataset_label.v0",
                "row_id": row_id,
                "domain": "formal_domain:bitmesh_composed_board_material:v0",
                "position": {"encoding": "fen", "text": fen},
                "label_kind": "exact",
                "exact": {
                    "value": {
                        "component_local_move_imbalance": "0",
                        "component_recursive_total_nodes": "47",
                        "component_signature_rule": (
                            "depth2_value_digest_plus_material_balance_plus_local_move_counts_v0"
                        ),
                        "component_topology_family": topology,
                        "component_value_classes": "0=game_tree,1=game_tree",
                        "left_component_signature": (
                            f"value:{left_digest};material:{left_material};"
                            f"moves:{left_moves}"
                        ),
                        "left_component_value_digest": left_digest,
                        "left_profile_index": "0",
                        "right_component_signature": (
                            f"value:{right_digest};material:{right_material};"
                            f"moves:{right_moves}"
                        ),
                        "right_component_value_digest": right_digest,
                        "right_profile_index": "1",
                        "result_signature_key": _heuristic_signature_target(
                            topology,
                            left_digest,
                            right_digest,
                            left_material,
                            right_material,
                            left_moves=left_moves,
                            right_moves=right_moves,
                        ),
                        "signature_target_rule": (
                            "depth2_material_mobility_signature_exact_metadata_v0"
                        ),
                        "total_recursive_nodes": "47",
                        "value_class": "game_tree",
                    }
                },
            }
    raise AssertionError(f"could not find exact FEN for split {target_split!r}")


def _composition_fixture_certificate(
    name: str, component_values: dict[str, str]
) -> dict[str, object]:
    return {
        "kind": "bitmesh-bmcompose-v1+thermograph-exact-value+fixture-sum",
        "digest": f"sha256:{name}-certificate",
        "decomposition_digest": f"sha256:{name}-decomposition",
        "composition_digest": f"sha256:{name}-composition",
        "component_values": component_values,
        "result_value_digest": f"sha256:{name}-result",
    }


def _composition_baseline_fixture_report(
    composition_value_rule: str | None = FIXTURE_COMPONENT_SUM_RULE,
) -> dict[str, object]:
    train_certificate = {
        "kind": "bitmesh-bmcompose-v1+thermograph-exact-value+fixture-sum",
        "digest": "sha256:baseline-train-certificate",
        "decomposition_digest": "sha256:baseline-train-decomposition",
        "composition_digest": "sha256:baseline-train-composition",
        "component_values": {
            "0": "sha256:baseline-component-one",
        },
        "result_value_digest": "sha256:baseline-train-result",
    }
    heldout_certificate = {
        "kind": "bitmesh-bmcompose-v1+thermograph-exact-value+fixture-sum",
        "digest": "sha256:baseline-heldout-certificate",
        "decomposition_digest": "sha256:baseline-heldout-decomposition",
        "composition_digest": "sha256:baseline-heldout-composition",
        "component_values": {
            "0": "sha256:baseline-component-two",
            "1": "sha256:baseline-component-three",
        },
        "result_value_digest": "sha256:baseline-heldout-result",
    }
    rejected_matching_certificate = {
        "kind": "bitmesh-bmcompose-v1+thermograph-exact-value+fixture-sum",
        "digest": "sha256:baseline-rejected-certificate",
        "decomposition_digest": "sha256:baseline-rejected-decomposition",
        "composition_digest": "sha256:baseline-rejected-composition",
        "component_values": {
            "0": "sha256:baseline-rejected-component-two",
            "1": "sha256:baseline-rejected-component-three",
        },
        "result_value_digest": "sha256:baseline-rejected-result",
    }

    rows = [
        _composition_fixture_row_for_train_dev_split(
            "composition-baseline-train-exact",
            "train",
            train_certificate,
            canonical_serialization="Number(1/2^0)",
            digest="sha256:baseline-train-result",
            component_values_summary="0=Number(1/2^0)",
            composition_value_rule=composition_value_rule,
            component_topology_family="fixture-train-topology",
            component_local_move_totals="white:1,black:0",
            component_local_move_imbalance="1",
            component_recursive_total_nodes="3",
        ),
        _composition_fixture_row(
            "composition-baseline-heldout-exact",
            "8/8/8/8/8/8/K7/7k w - - 0 99",
            heldout_certificate,
            canonical_serialization="Number(5/2^0)",
            digest="sha256:baseline-heldout-result",
            component_values_summary="0=Number(2/2^0),1=Number(3/2^0)",
            composition_value_rule=composition_value_rule,
            component_topology_family="fixture-heldout-topology",
            component_local_move_totals="white:2,black:3",
            component_local_move_imbalance="-1",
            component_recursive_total_nodes="8",
        ),
        _composition_rejected_fixture_row_for_train_dev_split(
            "composition-baseline-rejected-matching-count",
            "train",
            rejected_matching_certificate,
            start_index=1000,
        ),
    ]

    with TemporaryDirectory() as temp_dir:
        shard_path = Path(temp_dir) / "composition-baseline-smoke.jsonl"
        shard_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
            encoding="utf-8",
        )
        return evaluate_composition_baseline_report(
            shard_path,
            "component_count",
            2,
        )


def _composition_fixture_row(
    row_id: str,
    fen: str,
    certificate: dict[str, object],
    canonical_serialization: str = "Number(0/2^0)",
    digest: str = "sha256:composed-result",
    component_values_summary: str | None = None,
    composition_value_rule: str | None = FIXTURE_COMPONENT_SUM_RULE,
    component_topology_family: str | None = None,
    composition_spec_source: str | None = None,
    component_local_move_totals: str | None = None,
    component_local_move_imbalance: str | None = None,
    component_recursive_total_nodes: str | None = None,
) -> dict[str, object]:
    exact_value = {
        "digest": digest,
        "canonical_serialization": canonical_serialization,
    }
    if component_values_summary is not None:
        exact_value["component_values"] = component_values_summary
        if composition_value_rule is not None:
            exact_value["composition_value_rule"] = composition_value_rule
    if component_topology_family is not None:
        exact_value["component_topology_family"] = component_topology_family
    if composition_spec_source is not None:
        exact_value["composition_spec_source"] = composition_spec_source
    if component_local_move_totals is not None:
        exact_value["component_local_move_totals"] = component_local_move_totals
    if component_local_move_imbalance is not None:
        exact_value["component_local_move_imbalance"] = component_local_move_imbalance
    if component_recursive_total_nodes is not None:
        exact_value["component_recursive_total_nodes"] = component_recursive_total_nodes

    return {
        "schema_version": "partizan.dataset_label.v0",
        "row_id": row_id,
        "domain": "formal_domain:composition_fixture:v0",
        "position": {"encoding": "fen", "text": fen},
        "label_kind": "exact",
        "exact": {
            "status": "verified",
            "value": exact_value,
            "value_class": "number",
        },
        "provenance": {
            "code_commit": "fixture-commit",
            "generator": "fixture_composition_generator",
            "generator_config_hash": "sha256:fixture-config",
            "random_seed": 0,
            "domain_definition": "docs/formal_domain.md#composition-fixture",
            "verifier": "fixture_composition_verifier",
            "verifier_version": "0.0.1",
            "certificate": certificate,
        },
    }


def _composition_fixture_row_for_split(
    row_id: str,
    target_split: str,
    certificate: dict[str, object],
    canonical_serialization: str = "Number(0/2^0)",
    digest: str = "sha256:composed-result",
    component_values_summary: str | None = None,
    composition_value_rule: str | None = FIXTURE_COMPONENT_SUM_RULE,
    component_topology_family: str | None = None,
    composition_spec_source: str | None = None,
    component_local_move_totals: str | None = None,
    component_local_move_imbalance: str | None = None,
    component_recursive_total_nodes: str | None = None,
) -> dict[str, object]:
    for index in range(1000):
        fen = f"8/8/8/8/8/8/K7/7k w - - 0 {index + 1}"
        split_key = f"fixture_composition_generator|fen:{fen}"
        if split_for_key(split_key) == target_split:
            return _composition_fixture_row(
                row_id,
                fen,
                certificate,
                canonical_serialization=canonical_serialization,
                digest=digest,
                component_values_summary=component_values_summary,
                composition_value_rule=composition_value_rule,
                component_topology_family=component_topology_family,
                composition_spec_source=composition_spec_source,
                component_local_move_totals=component_local_move_totals,
                component_local_move_imbalance=component_local_move_imbalance,
                component_recursive_total_nodes=component_recursive_total_nodes,
            )
    raise AssertionError(f"could not find fixture FEN for split {target_split!r}")


def _composition_fixture_row_for_train_dev_split(
    row_id: str,
    target_split: str,
    certificate: dict[str, object],
    start_index: int = 0,
    canonical_serialization: str = "Number(0/2^0)",
    digest: str = "sha256:composed-result",
    component_values_summary: str | None = None,
    composition_value_rule: str | None = FIXTURE_COMPONENT_SUM_RULE,
    component_topology_family: str | None = None,
    composition_spec_source: str | None = None,
    component_local_move_totals: str | None = None,
    component_local_move_imbalance: str | None = None,
    component_recursive_total_nodes: str | None = None,
) -> dict[str, object]:
    for index in range(start_index, start_index + 1000):
        fen = f"8/8/8/8/8/8/K7/7k w - - 0 {index + 1}"
        split_key = f"fixture_composition_generator|fen:{fen}"
        if train_dev_split_for_key(split_key) == target_split:
            return _composition_fixture_row(
                row_id,
                fen,
                certificate,
                canonical_serialization=canonical_serialization,
                digest=digest,
                component_values_summary=component_values_summary,
                composition_value_rule=composition_value_rule,
                component_topology_family=component_topology_family,
                composition_spec_source=composition_spec_source,
                component_local_move_totals=component_local_move_totals,
                component_local_move_imbalance=component_local_move_imbalance,
                component_recursive_total_nodes=component_recursive_total_nodes,
            )
    raise AssertionError(f"could not find fixture FEN for train/dev split {target_split!r}")


def _composition_rejected_fixture_row(
    row_id: str,
    fen: str,
    certificate: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "partizan.dataset_label.v0",
        "row_id": row_id,
        "domain": "formal_domain:composition_fixture:v0",
        "position": {"encoding": "fen", "text": fen},
        "label_kind": "rejected",
        "rejected": {
            "status": "excluded",
            "reasons": ["synthetic composition holdout negative"],
        },
        "provenance": {
            "code_commit": "fixture-commit",
            "generator": "fixture_composition_generator",
            "generator_config_hash": "sha256:fixture-config",
            "random_seed": 0,
            "domain_definition": "docs/formal_domain.md#composition-fixture",
            "verifier": "fixture_composition_verifier",
            "verifier_version": "0.0.1",
            "certificate": certificate,
        },
    }


def _composition_rejected_fixture_row_for_train_dev_split(
    row_id: str,
    target_split: str,
    certificate: dict[str, object],
    start_index: int = 0,
) -> dict[str, object]:
    for index in range(start_index, start_index + 1000):
        fen = f"8/8/8/8/8/8/K7/7k w - - 0 {index + 1}"
        split_key = f"fixture_composition_generator|fen:{fen}"
        if train_dev_split_for_key(split_key) == target_split:
            return _composition_rejected_fixture_row(row_id, fen, certificate)
    raise AssertionError(f"could not find fixture FEN for train/dev split {target_split!r}")


def run_baseline_smoke():
    if not WAVE_3_SHARD.exists():
        raise FileNotFoundError(f"required fixture not found: {WAVE_3_SHARD}")

    metrics = evaluate_label_shard_baseline(WAVE_3_SHARD)
    assert metrics["row_counts"] == {
        "total": 6,
        "exact": 3,
        "rejected": 1,
        "heuristic": 1,
        "prediction": 1,
    }
    exact_rejected = metrics["baselines"]["exact_vs_rejected"]
    assert exact_rejected["support"] == 2
    assert exact_rejected["excluded_position_encodings"] == ["cgt_canonical"]
    assert exact_rejected["accuracy"] == 0.5
    value_class = metrics["baselines"]["exact_value_class"]
    assert value_class["support"] == 3
    assert value_class["status"] == "evaluated"
    assert value_class["class_counts"] == {
        "game_tree": 1,
        "integer": 1,
        "switch": 1,
    }
    assert value_class["accuracy"] == 0.0
    print(
        "Baseline smoke ok: "
        f"{metrics['dataset_path']} rows={metrics['row_counts']['total']} "
        f"exact-vs-rejected accuracy={exact_rejected['accuracy']:.3f}"
    )


def run_frontier_baseline_smoke():
    if not FRONTIER_WAVE_6_SHARD.exists():
        raise FileNotFoundError(
            f"requested optional integration artifact not found: {FRONTIER_WAVE_6_SHARD}"
        )

    metrics = evaluate_label_shard_baseline(FRONTIER_WAVE_6_SHARD)
    assert metrics["row_counts"] == {
        "total": 1000,
        "exact": 200,
        "rejected": 800,
        "heuristic": 0,
        "prediction": 0,
    }
    exact_rejected = metrics["baselines"]["exact_vs_rejected"]
    assert exact_rejected["support"] == 1000
    assert exact_rejected["accuracy"] == 0.2
    assert exact_rejected["confusion_matrix"]["rejected"] == {
        "exact": 800,
        "rejected": 0,
    }
    value_class = metrics["baselines"]["exact_value_class"]
    assert value_class["support"] == 200
    assert value_class["class_counts"] == {"number": 200}

    split_report = evaluate_split_report(FRONTIER_WAVE_6_SHARD)
    assert split_report["row_counts"] == {"dev": 91, "test": 93, "train": 816}
    assert split_report["label_kind_counts"]["train"] == {
        "exact": 172,
        "rejected": 644,
    }
    assert split_report["label_kind_counts"]["dev"] == {
        "exact": 14,
        "rejected": 77,
    }
    assert split_report["label_kind_counts"]["test"] == {
        "exact": 14,
        "rejected": 79,
    }
    assert split_report["leakage_checks"]["position_key_cross_split"][
        "violation_count"
    ] == 0
    assert (
        split_report["leakage_checks"]["symmetry_position_key_eligible_rows"] == 1000
    )
    assert split_report["leakage_checks"]["duplicate_symmetry_positions"] == 235
    assert split_report["leakage_checks"]["symmetry_position_key_cross_split"][
        "violation_count"
    ] == 70
    assert split_report["leakage_checks"]["exact_certificate_digest_cross_split"][
        "violation_count"
    ] == 0

    symmetry_split_report = evaluate_split_report_with_mode(
        FRONTIER_WAVE_6_SHARD,
        "symmetry",
    )
    assert symmetry_split_report["row_counts"] == {
        "dev": 90,
        "test": 93,
        "train": 817,
    }
    assert symmetry_split_report["label_kind_counts"]["train"] == {
        "exact": 165,
        "rejected": 652,
    }
    assert symmetry_split_report["label_kind_counts"]["dev"] == {
        "exact": 15,
        "rejected": 75,
    }
    assert symmetry_split_report["label_kind_counts"]["test"] == {
        "exact": 20,
        "rejected": 73,
    }
    assert symmetry_split_report["leakage_checks"][
        "symmetry_position_key_cross_split"
    ]["violation_count"] == 0
    print(
        "Frontier baseline smoke ok: "
        f"{metrics['dataset_path']} rows={metrics['row_counts']['total']} "
        f"exact-vs-rejected accuracy={exact_rejected['accuracy']:.3f}"
    )


def run_family_frontier_baseline_smoke():
    if not FAMILY_FRONTIER_WAVE_7_SHARD.exists():
        raise FileNotFoundError(
            "requested optional integration artifact not found: "
            f"{FAMILY_FRONTIER_WAVE_7_SHARD}"
        )

    metrics = evaluate_label_shard_baseline(FAMILY_FRONTIER_WAVE_7_SHARD)
    assert metrics["row_counts"] == {
        "total": 2000,
        "exact": 400,
        "rejected": 1600,
        "heuristic": 0,
        "prediction": 0,
    }
    exact_rejected = metrics["baselines"]["exact_vs_rejected"]
    assert exact_rejected["support"] == 2000
    assert exact_rejected["accuracy"] == 0.2
    assert exact_rejected["confusion_matrix"]["rejected"] == {
        "exact": 1600,
        "rejected": 0,
    }

    split_report = evaluate_split_report(FAMILY_FRONTIER_WAVE_7_SHARD)
    assert split_report["row_counts"] == {"dev": 201, "test": 194, "train": 1605}
    assert split_report["generator_family_counts"]["train"] == {
        "astralbase_kqk_frontier_generator": 816,
        "astralbase_krk_frontier_generator": 789,
    }
    assert split_report["generator_family_counts"]["dev"] == {
        "astralbase_kqk_frontier_generator": 91,
        "astralbase_krk_frontier_generator": 110,
    }
    assert split_report["generator_family_counts"]["test"] == {
        "astralbase_kqk_frontier_generator": 93,
        "astralbase_krk_frontier_generator": 101,
    }
    assert split_report["leakage_checks"]["position_key_cross_split"][
        "violation_count"
    ] == 0
    assert (
        split_report["leakage_checks"]["symmetry_position_key_eligible_rows"] == 2000
    )
    assert split_report["leakage_checks"]["duplicate_symmetry_positions"] == 414
    assert split_report["leakage_checks"]["symmetry_position_key_cross_split"][
        "violation_count"
    ] == 137

    symmetry_split_report = evaluate_split_report_with_mode(
        FAMILY_FRONTIER_WAVE_7_SHARD,
        "symmetry",
    )
    assert symmetry_split_report["row_counts"] == {
        "dev": 183,
        "test": 206,
        "train": 1611,
    }
    assert symmetry_split_report["generator_family_counts"]["train"] == {
        "astralbase_kqk_frontier_generator": 817,
        "astralbase_krk_frontier_generator": 794,
    }
    assert symmetry_split_report["generator_family_counts"]["dev"] == {
        "astralbase_kqk_frontier_generator": 90,
        "astralbase_krk_frontier_generator": 93,
    }
    assert symmetry_split_report["generator_family_counts"]["test"] == {
        "astralbase_kqk_frontier_generator": 93,
        "astralbase_krk_frontier_generator": 113,
    }
    assert symmetry_split_report["leakage_checks"][
        "symmetry_position_key_cross_split"
    ]["violation_count"] == 0

    holdout_report = evaluate_family_holdout_report(
        FAMILY_FRONTIER_WAVE_7_SHARD,
        "astralbase_krk_frontier_generator",
    )
    assert holdout_report["row_counts"] == {"dev": 93, "test": 1000, "train": 907}
    assert holdout_report["generator_family_counts"]["train"] == {
        "astralbase_kqk_frontier_generator": 907
    }
    assert holdout_report["generator_family_counts"]["dev"] == {
        "astralbase_kqk_frontier_generator": 93
    }
    assert holdout_report["generator_family_counts"]["test"] == {
        "astralbase_krk_frontier_generator": 1000
    }
    assert holdout_report["leakage_checks"]["position_key_cross_split"][
        "violation_count"
    ] == 0
    assert holdout_report["leakage_checks"]["symmetry_position_key_cross_split"][
        "violation_count"
    ] == 38

    symmetry_holdout_report = evaluate_family_holdout_report_with_mode(
        FAMILY_FRONTIER_WAVE_7_SHARD,
        "astralbase_krk_frontier_generator",
        "symmetry",
    )
    assert symmetry_holdout_report["row_counts"] == {
        "dev": 93,
        "test": 1000,
        "train": 907,
    }
    assert symmetry_holdout_report["label_kind_counts"]["train"] == {
        "exact": 180,
        "rejected": 727,
    }
    assert symmetry_holdout_report["label_kind_counts"]["dev"] == {
        "exact": 20,
        "rejected": 73,
    }
    assert symmetry_holdout_report["label_kind_counts"]["test"] == {
        "exact": 200,
        "rejected": 800,
    }
    assert symmetry_holdout_report["leakage_checks"][
        "symmetry_position_key_cross_split"
    ]["violation_count"] == 0

    baseline_report = evaluate_split_baseline_report(
        FAMILY_FRONTIER_WAVE_7_SHARD,
        split_key_mode="symmetry",
        holdout_family="astralbase_krk_frontier_generator",
    )
    assert baseline_report["splitter_id"] == "family_holdout_generator_symmetry_hash_v0"
    assert baseline_report["row_counts"] == {
        "dev": 93,
        "test": 1000,
        "train": 907,
    }
    assert baseline_report["split_metrics"]["train"]["accuracy"] == 180 / 907
    assert baseline_report["split_metrics"]["dev"]["accuracy"] == 20 / 93
    assert baseline_report["split_metrics"]["test"]["accuracy"] == 0.2
    assert baseline_report["split_metrics"]["test"]["confusion_matrix"]["rejected"] == {
        "exact": 800,
        "rejected": 0,
    }

    geometry_probe_report = evaluate_geometry_probe_report(
        FAMILY_FRONTIER_WAVE_7_SHARD,
        split_key_mode="symmetry",
        holdout_family="astralbase_krk_frontier_generator",
    )
    assert (
        geometry_probe_report["splitter_id"]
        == "family_holdout_generator_symmetry_hash_v0"
    )
    assert geometry_probe_report["split_metrics"]["train"]["accuracy"] == 854 / 907
    assert geometry_probe_report["split_metrics"]["dev"]["accuracy"] == 87 / 93
    assert geometry_probe_report["split_metrics"]["test"]["accuracy"] == 0.928
    assert geometry_probe_report["split_metrics"]["test"]["confusion_matrix"] == {
        "exact": {"exact": 200, "rejected": 0},
        "rejected": {"exact": 72, "rejected": 728},
    }
    print(
        "Family frontier baseline smoke ok: "
        f"{metrics['dataset_path']} rows={metrics['row_counts']['total']} "
        f"exact-vs-rejected accuracy={exact_rejected['accuracy']:.3f}"
    )


def run_expanded_family_frontier_baseline_smoke():
    if not EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD.exists():
        raise FileNotFoundError(
            "requested optional integration artifact not found: "
            f"{EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD}"
        )

    metrics = evaluate_label_shard_baseline(EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD)
    assert metrics["row_counts"] == {
        "total": 4000,
        "exact": 800,
        "rejected": 3200,
        "heuristic": 0,
        "prediction": 0,
    }
    exact_rejected = metrics["baselines"]["exact_vs_rejected"]
    assert exact_rejected["support"] == 4000
    assert exact_rejected["accuracy"] == 0.2

    split_report = evaluate_split_report(EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD)
    assert split_report["row_counts"] == {"dev": 375, "test": 424, "train": 3201}
    assert split_report["leakage_checks"]["duplicate_symmetry_positions"] == 917
    assert split_report["leakage_checks"]["symmetry_position_key_cross_split"][
        "violation_count"
    ] == 269

    symmetry_split_report = evaluate_split_report_with_mode(
        EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD,
        "symmetry",
    )
    assert symmetry_split_report["row_counts"] == {
        "dev": 384,
        "test": 396,
        "train": 3220,
    }
    assert symmetry_split_report["generator_family_counts"]["train"] == {
        "astralbase_kbk_frontier_generator": 831,
        "astralbase_knk_frontier_generator": 778,
        "astralbase_kqk_frontier_generator": 817,
        "astralbase_krk_frontier_generator": 794,
    }
    assert symmetry_split_report["leakage_checks"][
        "symmetry_position_key_cross_split"
    ]["violation_count"] == 0

    holdout_report = evaluate_family_holdout_report_with_mode(
        EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD,
        "astralbase_knk_frontier_generator",
        "symmetry",
    )
    assert holdout_report["row_counts"] == {
        "dev": 279,
        "test": 1000,
        "train": 2721,
    }
    assert holdout_report["generator_family_counts"]["test"] == {
        "astralbase_knk_frontier_generator": 1000
    }
    assert holdout_report["leakage_checks"]["symmetry_position_key_cross_split"][
        "violation_count"
    ] == 0

    baseline_report = evaluate_split_baseline_report(
        EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD,
        split_key_mode="symmetry",
        holdout_family="astralbase_knk_frontier_generator",
    )
    assert baseline_report["split_metrics"]["test"]["accuracy"] == 0.2

    geometry_probe_report = evaluate_geometry_probe_report(
        EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD,
        split_key_mode="symmetry",
        holdout_family="astralbase_knk_frontier_generator",
    )
    assert geometry_probe_report["split_metrics"]["test"]["accuracy"] == 1.0
    assert geometry_probe_report["split_metrics"]["test"]["confusion_matrix"] == {
        "exact": {"exact": 200, "rejected": 0},
        "rejected": {"exact": 0, "rejected": 800},
    }

    krk_holdout_report = evaluate_family_holdout_report_with_mode(
        EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD,
        "astralbase_krk_frontier_generator",
        "symmetry",
    )
    assert krk_holdout_report["row_counts"] == {
        "dev": 283,
        "test": 1000,
        "train": 2717,
    }
    assert krk_holdout_report["generator_family_counts"]["test"] == {
        "astralbase_krk_frontier_generator": 1000
    }

    frontier_mean_report = evaluate_frontier_target_report(
        EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD,
        "frontier_mean",
        split_key_mode="symmetry",
        holdout_family="astralbase_krk_frontier_generator",
    )
    assert frontier_mean_report["train_majority_prediction"] == "1"
    assert frontier_mean_report["split_metrics"]["test"]["accuracy"] == 0.22
    assert frontier_mean_report["split_metrics"]["test"]["target_counts"] == {
        "1": 44,
        "2": 156,
    }
    assert frontier_mean_report["target_support_coverage"]["unseen_labels_by_split"][
        "test"
    ] == ["2"]
    print(
        "Expanded family frontier baseline smoke ok: "
        f"{metrics['dataset_path']} rows={metrics['row_counts']['total']} "
        f"exact-vs-rejected accuracy={exact_rejected['accuracy']:.3f}"
    )


def run_rust_engine_smoke():
    if partizan is None:
        raise RuntimeError(
            "required Python extension module 'partizan' is not installed; "
            "install the project before running required tests"
        )

    fen = "7k/5KQ1/8/8/8/8/8/8 b - - 0 1"
    locked_squares = partizan.find_locked_pawns(fen)
    is_decomposable, components = partizan.analyze_subsystems(fen)
    results = partizan.evaluate_position(fen)
    assert locked_squares == []
    assert isinstance(is_decomposable, bool)
    assert isinstance(components, int)
    assert results["mean_value"] == -1.0
    assert results["temperature"] == -1.0
    assert results["expanded_nodes"] == 50
    print("Rust/Python extension smoke ok (terminal plumbing only; no chess-temperature claim)")


def main(argv=None):
    global FRONTIER_WAVE_6_SHARD
    global FAMILY_FRONTIER_WAVE_7_SHARD
    global EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD

    parser = argparse.ArgumentParser(description="Run required Partizan Python smokes.")
    parser.add_argument(
        "--legacy-artifact-dir",
        type=Path,
        help=(
            "Also run the historical Wave 6/7/12 integration smokes. All three "
            "large artifacts are required when this option is supplied."
        ),
    )
    args = parser.parse_args(argv)
    if args.legacy_artifact_dir is not None:
        FRONTIER_WAVE_6_SHARD = args.legacy_artifact_dir / "partizan-frontier-wave-06.jsonl"
        FAMILY_FRONTIER_WAVE_7_SHARD = (
            args.legacy_artifact_dir / "partizan-family-frontier-wave-07.jsonl"
        )
        EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD = (
            args.legacy_artifact_dir / "partizan-expanded-family-frontier-wave-12.jsonl"
        )

    run_symmetry_key_smoke()
    run_composition_certificate_report_smoke()
    run_composition_holdout_report_smoke()
    run_composition_baseline_rejected_exclusion_smoke()
    run_composition_baseline_component_sum_smoke()
    run_composition_baseline_component_sum_rule_scope_smoke()
    run_composition_topology_benchmark_report_smoke()
    run_composition_component_sum_parser_scope_smoke()
    run_signature_profile_contract_report_smoke()
    run_heuristic_target_report_smoke()
    run_heuristic_target_projection_report_smoke()
    run_exact_projection_baseline_report_smoke()
    run_heuristic_signature_promotion_report_smoke()
    run_baseline_smoke()
    if args.legacy_artifact_dir is not None:
        run_frontier_baseline_smoke()
        run_family_frontier_baseline_smoke()
        run_expanded_family_frontier_baseline_smoke()
    run_rust_engine_smoke()


if __name__ == "__main__":
    main()
