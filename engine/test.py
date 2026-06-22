import sys
import partizan

def main():
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

if __name__ == "__main__":
    main()
