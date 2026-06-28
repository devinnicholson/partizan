from pathlib import Path

from ml_model import evaluate_label_shard_baseline

try:
    import partizan
except ModuleNotFoundError:
    partizan = None


WAVE_3_SHARD = Path("/private/tmp/partizan-wave-03.jsonl")


def run_baseline_smoke():
    if not WAVE_3_SHARD.exists():
        print(f"Baseline smoke skipped; shard not found: {WAVE_3_SHARD}")
        return

    metrics = evaluate_label_shard_baseline(WAVE_3_SHARD)
    assert metrics["row_counts"] == {
        "total": 3,
        "exact": 1,
        "rejected": 2,
        "heuristic": 0,
        "prediction": 0,
    }
    exact_rejected = metrics["baselines"]["exact_vs_rejected"]
    assert exact_rejected["support"] == 3
    assert exact_rejected["accuracy"] == 1.0
    assert metrics["baselines"]["exact_value_class"]["status"] == "not_meaningful"
    print(
        "Baseline smoke ok: "
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
    run_rust_engine_smoke()


if __name__ == "__main__":
    main()
