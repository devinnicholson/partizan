from __future__ import annotations

import unittest

import partizan


ELKIES_FEN = "5Q2/5P1b/8/7K/8/1q4k1/1p4B1/8 w - - 0 1"
ELKIES_LINE = [
    "f8g7",
    "g3h2",
    "f7f8q",
    "b3b5",
    "h5h6",
    "b5b6",
    "g2c6",
    "b6c6",
    "h6h7",
    "b2b1q",
    "h7h8",
    "h2h1",
    "f8g8",
]


class ChessWitnessTests(unittest.TestCase):
    def test_elkies_line_replays_to_the_recorded_kernel(self) -> None:
        record = partizan.replay_chess_witness(ELKIES_FEN, ELKIES_LINE)

        self.assertEqual(
            record["native_witness_version"],
            "partizan.chess_witness.native.v0.1",
        )
        self.assertEqual(record["move_count"], 13)
        self.assertEqual(len(record["frames"]), 14)
        self.assertEqual(
            [frame["move_san"] for frame in record["frames"][1:]],
            [
                "Qg7+",
                "Kh2",
                "f8=Q",
                "Qb5+",
                "Kh6",
                "Qb6+",
                "Bc6",
                "Qxc6+",
                "Kxh7",
                "b1=Q+",
                "Kh8",
                "Kh1",
                "Qfg8",
            ],
        )
        self.assertEqual(
            record["frames"][-1]["fen"],
            "6QK/6Q1/2q5/8/8/8/8/1q5k b - - 3 7",
        )

    def test_illegal_move_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "Illegal UCI move at ply 1"):
            partizan.replay_chess_witness(ELKIES_FEN, ["a1a8"])


if __name__ == "__main__":
    unittest.main()
