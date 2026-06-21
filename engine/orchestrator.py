import modal
import os

# Define the Modal App
app = modal.App("partizan-cgt-evaluator")

# Define the container environment
# We need Rust, Cargo, and Maturin to compile our PyO3 engine in the cloud
partizan_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("cargo", "rustc", "libssl-dev", "pkg-config")
    .pip_install("maturin")
    # Copy the local Rust engine code into the Modal image
    .add_local_dir(".", remote_path="/root/engine")
    # Compile the PyO3 module during the container build phase
    .run_commands("cd /root/engine && maturin develop --release")
)

@app.function(image=partizan_image)
def evaluate_fens_batch(fens: list[str]):
    """
    This function runs in the cloud on thousands of parallel containers.
    It takes a batch of FENs and processes them through our Rust engine.
    """
    # We must append the engine path so Python can find the compiled partizan module
    import sys
    sys.path.append("/root/engine")
    import partizan

    results = []
    for fen in fens:
        try:
            is_decomposable, components = partizan.analyze_subsystems(fen)
            if is_decomposable:
                results.append({"fen": fen, "components": components, "status": "Decomposable"})
        except Exception as e:
            pass # Ignore invalid FENs during bulk processing
            
    return results

@app.local_entrypoint()
def main():
    print("🚀 Booting up the Partizan Modal Orchestrator...")
    
    # In a real scenario, this would be billions of FENs generated via retrograde analysis.
    # For now, we simulate a massive workload.
    dummy_fens = [
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", # Standard start
        "rnbqkbnr/pp3ppp/4p3/2ppP3/3P4/8/PPP2PPP/RNBQKBNR w KQkq - 0 4", # French Defense
        "4k3/p1pppp1p/1p4p1/8/8/1P4P1/P1PPPP1P/4K3 w - - 0 1" # A heavily locked custom FEN
    ] * 1000 # Simulate 3,000 FENs
    
    # Chunk the FENs into batches of 100 to maximize container efficiency and reduce network overhead
    batch_size = 100
    batches = [dummy_fens[i:i + batch_size] for i in range(0, len(dummy_fens), batch_size)]
    
    print(f"📦 Distributing {len(dummy_fens)} positions across {len(batches)} Modal containers...")
    
    decomposable_positions = []
    
    # Modal's .map() automatically spins up containers and parallelizes the workload
    for result_batch in evaluate_fens_batch.map(batches):
        decomposable_positions.extend(result_batch)
        
    print(f"✅ Processing complete! Found {len(decomposable_positions)} decomposable positions out of {len(dummy_fens)}.")
    
    if decomposable_positions:
        print("Example decomposable position:")
        print(decomposable_positions[0])
