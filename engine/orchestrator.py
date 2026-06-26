import modal
import os
import json

app = modal.App("partizan-cgt-evaluator")

# Define the container environment
# We need Rust, Cargo, and Maturin to compile our PyO3 engine in the cloud
partizan_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("curl", "libssl-dev", "pkg-config")
    .run_commands("curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y")
    .env({"PATH": "/root/.cargo/bin:$PATH"})
    .pip_install("maturin")
    # To satisfy the Cargo.toml relative path dependencies (../../) we must mount the libraries accordingly:
    # We put the engine in /root/partizan/engine so that ../../ resolves to /root
    .add_local_dir(".", remote_path="/root/partizan/engine", copy=True)
    .add_local_dir("../../thermograph", remote_path="/root/thermograph", copy=True)
    .add_local_dir("../../bitmesh", remote_path="/root/bitmesh", copy=True)
    .add_local_dir("../../astralbase", remote_path="/root/astralbase", copy=True)
    # Compile the PyO3 module and install the wheel globally in the container
    .run_commands("rm -rf /root/partizan/engine/.venv && cd /root/partizan/engine && maturin build --release && pip install target/wheels/partizan*.whl")
)

@app.function(image=partizan_image)
def evaluate_fens_batch(fens: list[str]):
    """
    This function runs in the cloud on thousands of parallel containers.
    It takes a batch of FENs and processes them through our Rust engine.
    """
    import sys
    sys.path.append("/root/partizan/engine")
    import partizan

    results = []
    for fen in fens:
        try:
            # Our new PyO3 hook processes Bitmesh, Thermograph, and Astralbase at once
            data = partizan.evaluate_position(fen)
            results.append({
                "fen": fen,
                "components": data["components"],
                "temperature": data["temperature"],
                "mean_value": data["mean_value"],
                "expanded_nodes": data["expanded_nodes"]
            })
        except Exception as e:
            pass # Ignore invalid FENs during bulk processing
            
    return results

@app.local_entrypoint()
def main():
    print("🚀 Booting up the Partizan Modal Orchestrator...")
    
    # In a real scenario, we generate billions of FENs.
    # Here we simulate a large batch to demonstrate the cloud pipeline.
    dummy_fens = [
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", 
        "rnbqkbnr/pp3ppp/4p3/2ppP3/3P4/8/PPP2PPP/RNBQKBNR w KQkq - 0 4", 
        "4k3/p1pppp1p/1p4p1/8/8/1P4P1/P1PPPP1P/4K3 w - - 0 1" 
    ] * 1000 # 3,000 FENs
    
    batch_size = 100
    batches = [dummy_fens[i:i + batch_size] for i in range(0, len(dummy_fens), batch_size)]
    
    print(f"📦 Distributing {len(dummy_fens)} positions across {len(batches)} Modal containers...")
    
    evaluated_positions = []
    
    for result_batch in evaluate_fens_batch.map(batches):
        evaluated_positions.extend(result_batch)
        
    print(f"✅ Processing complete! Evaluated {len(evaluated_positions)} positions.")
    
    dataset_path = "cgt_dataset.jsonl"
    with open(dataset_path, "w") as f:
        for pos in evaluated_positions:
            f.write(json.dumps(pos) + "\n")
            
    print(f"💾 Saved raw dataset to {dataset_path} for PartizanNet training!")
