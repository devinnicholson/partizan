from pathlib import Path

from ml_model import evaluate_label_shard_baseline, evaluate_split_report

try:
    import partizan
except ModuleNotFoundError:
    partizan = None


WAVE_3_SHARD = Path("/private/tmp/partizan-wave-03.jsonl")
FRONTIER_WAVE_6_SHARD = Path("/private/tmp/partizan-frontier-wave-06.jsonl")
FAMILY_FRONTIER_WAVE_7_SHARD = Path("/private/tmp/partizan-family-frontier-wave-07.jsonl")


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
    assert split_report["leakage_checks"]["exact_certificate_digest_cross_split"][
        "violation_count"
    ] == 0
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
    print(
        "Family frontier baseline smoke ok: "
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
    run_baseline_smoke()
    run_frontier_baseline_smoke()
    run_family_frontier_baseline_smoke()
    run_rust_engine_smoke()


if __name__ == "__main__":
    main()
