from pathlib import Path

from ml_model import (
    evaluate_geometry_probe_report,
    evaluate_family_holdout_report,
    evaluate_family_holdout_report_with_mode,
    evaluate_frontier_target_report,
    evaluate_label_shard_baseline,
    evaluate_split_baseline_report,
    evaluate_split_report,
    evaluate_split_report_with_mode,
    fen_d4_symmetry_key,
)

try:
    import partizan
except ModuleNotFoundError:
    partizan = None


WAVE_3_SHARD = Path("/private/tmp/partizan-wave-03.jsonl")
FRONTIER_WAVE_6_SHARD = Path("/private/tmp/partizan-frontier-wave-06.jsonl")
FAMILY_FRONTIER_WAVE_7_SHARD = Path("/private/tmp/partizan-family-frontier-wave-07.jsonl")
EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD = Path(
    "/private/tmp/partizan-expanded-family-frontier-wave-12.jsonl"
)


def run_symmetry_key_smoke():
    fen = "7K/8/8/8/8/8/8/Q5k1 w - - 0 1"
    mirrored_fen = "K7/8/8/8/8/8/8/1k5Q w - - 0 1"
    assert fen_d4_symmetry_key(fen) == fen_d4_symmetry_key(mirrored_fen)
    assert fen_d4_symmetry_key("7K/8/8/8/8/8/8/Q5k1 w K - 0 1") is None


def run_baseline_smoke():
    if not WAVE_3_SHARD.exists():
        print(f"Baseline smoke skipped; shard not found: {WAVE_3_SHARD}")
        return

    metrics = evaluate_label_shard_baseline(WAVE_3_SHARD)
    assert metrics["row_counts"] == {
        "total": 5,
        "exact": 3,
        "rejected": 2,
        "heuristic": 0,
        "prediction": 0,
    }
    exact_rejected = metrics["baselines"]["exact_vs_rejected"]
    assert exact_rejected["support"] == 4
    assert exact_rejected["excluded_position_encodings"] == ["cgt_canonical"]
    assert exact_rejected["accuracy"] == 1.0
    value_class = metrics["baselines"]["exact_value_class"]
    assert value_class["support"] == 3
    assert value_class["status"] == "evaluated"
    assert value_class["class_counts"] == {"number": 2, "switch": 1}
    assert value_class["accuracy"] == 2 / 3
    print(
        "Baseline smoke ok: "
        f"{metrics['dataset_path']} rows={metrics['row_counts']['total']} "
        f"exact-vs-rejected accuracy={exact_rejected['accuracy']:.3f}"
    )


def run_frontier_baseline_smoke():
    if not FRONTIER_WAVE_6_SHARD.exists():
        print(f"Frontier baseline smoke skipped; shard not found: {FRONTIER_WAVE_6_SHARD}")
        return

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
        print(
            "Family frontier baseline smoke skipped; "
            f"shard not found: {FAMILY_FRONTIER_WAVE_7_SHARD}"
        )
        return

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
        print(
            "Expanded family frontier baseline smoke skipped; "
            f"shard not found: {EXPANDED_FAMILY_FRONTIER_WAVE_12_SHARD}"
        )
        return

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
    print(
        "Expanded family frontier baseline smoke ok: "
        f"{metrics['dataset_path']} rows={metrics['row_counts']['total']} "
        f"exact-vs-rejected accuracy={exact_rejected['accuracy']:.3f}"
    )


def run_rust_engine_smoke():
    if partizan is None:
        print("Rust engine smoke skipped; Python extension module 'partizan' is not installed.")
        return

    # A position with a heavily locked pawn center (French Defense Advance style)
    fen = "rnbqkbnr/pp3ppp/4p3/2ppP3/3P4/8/PPP2PPP/RNBQKBNR w KQkq - 0 4"
    print(f"Original FEN: {fen}")
    
    try:
        locked_squares = partizan.find_locked_pawns(fen)
        print(f"Locked pawns found at squares: {locked_squares}")
        
        is_decomposable, components = partizan.analyze_subsystems(fen)
        print(f"Is Decomposable: {is_decomposable}")
        print(f"Number of Independent Sub-games: {components}")
        
        print("\n--- Running comprehensive evaluation ---")
        results = partizan.evaluate_position(fen)
        print(f"Bitmesh partitions: {results['components']}")
        print(f"Thermograph temperature: {results['temperature']}")
        print(f"Thermograph mean value: {results['mean_value']}")
        print(f"Astralbase retrograde expansions: {results['expanded_nodes']}")
        
    except Exception as e:
        print(f"Rust engine error: {e}")


def main():
    run_symmetry_key_smoke()
    run_baseline_smoke()
    run_frontier_baseline_smoke()
    run_family_frontier_baseline_smoke()
    run_expanded_family_frontier_baseline_smoke()
    run_rust_engine_smoke()


if __name__ == "__main__":
    main()
