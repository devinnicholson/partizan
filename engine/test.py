import sys
import cgt_chess_engine

def main():
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    print(f"Original FEN: {fen}")
    result = cgt_chess_engine.process_fen(fen)
    print(f"Result from Rust: {result}")

if __name__ == "__main__":
    main()
