from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import partizan
from partizan.cli import main as cli_main


TERMINAL_FEN = "7k/5KQ1/8/8/8/8/8/8 b - - 0 1"


class EventStreamTests(unittest.TestCase):
    def test_stream_is_deterministic_and_claim_scoped(self) -> None:
        first = partizan.canonical_event_bytes(partizan.build_event_stream(TERMINAL_FEN))
        second = partizan.canonical_event_bytes(partizan.build_event_stream(TERMINAL_FEN))
        self.assertEqual(first, second)
        payload = json.loads(first)
        self.assertEqual(
            [item["claim_id"] for item in payload["claim_boundaries"]],
            ["P01", "P02", "P03", "P04", "P05"],
        )
        self.assertEqual(
            payload["position"]["sha256"],
            hashlib.sha256(TERMINAL_FEN.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(partizan.validate_event_stream(payload), [])

    def test_validator_rejects_digest_corruption(self) -> None:
        payload = partizan.build_event_stream(TERMINAL_FEN)
        payload["position"]["sha256"] = "0" * 64
        errors = partizan.validate_event_stream(payload)
        self.assertIn("position.sha256 does not match position.text", errors)

    def test_cli_generates_and_validates(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "event.json"
            self.assertEqual(
                cli_main(["from-fen", "--fen", TERMINAL_FEN, "--output", str(output)]),
                0,
            )
            self.assertEqual(cli_main(["validate", str(output)]), 0)

    def test_native_terminal_smoke_is_explicitly_scoped(self) -> None:
        result = partizan.evaluate_position(TERMINAL_FEN)
        self.assertEqual(result["mean_value"], -1.0)
        self.assertEqual(result["temperature"], -1.0)
        with self.assertRaisesRegex(ValueError, "supports only terminal"):
            partizan.evaluate_position(
                "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
            )


if __name__ == "__main__":
    unittest.main()
