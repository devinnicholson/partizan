from __future__ import annotations

import importlib.util
import gzip
import hashlib
import json
import unittest
from pathlib import Path

import partizan

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_visualizer_evidence.py"
EVIDENCE = ROOT / "visualizer" / "public" / "evidence" / "crossing.json"
ATLAS = ROOT / "visualizer" / "public" / "evidence" / "fixed-value-atlas.json.gz"
ATLAS_MANIFEST = (
    ROOT
    / "visualizer"
    / "public"
    / "evidence"
    / "fixed-value-atlas.manifest.json"
)
FIBER_193 = (
    ROOT / "visualizer" / "public" / "evidence" / "fixed-value-fiber-193.json"
)
FIBER_193_MANIFEST = (
    ROOT
    / "visualizer"
    / "public"
    / "evidence"
    / "fixed-value-fiber-193.manifest.json"
)
SPEC = importlib.util.spec_from_file_location("partizan_visualizer_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
visualizer_evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(visualizer_evidence)


class VisualizerEvidenceTests(unittest.TestCase):
    def test_committed_crossing_is_a_clean_native_rebuild(self) -> None:
        rebuilt = visualizer_evidence.build_evidence()
        self.assertEqual(
            EVIDENCE.read_bytes(),
            partizan.canonical_json_bytes(rebuilt),
        )
        self.assertEqual(
            [item["statistics"]["literal_game_nodes"] for item in rebuilt["realizations"]],
            [19, 11],
        )
        self.assertEqual(
            [item["witness"]["move"] for item in rebuilt["realizations"]],
            ["Qg1-g7", "Qg6-g7"],
        )
        self.assertEqual(rebuilt["comparison"]["equal_to_value"], [True, True])
        self.assertTrue(rebuilt["comparison"]["equal_to_each_other"])
        self.assertIn(
            "literal_game_crossing",
            rebuilt["comparison"]["transition_kinds"],
        )

    def test_fixed_value_atlas_has_a_self_consistent_authority(self) -> None:
        compressed = ATLAS.read_bytes()
        decoded = gzip.decompress(compressed)
        atlas = json.loads(decoded)
        manifest = json.loads(ATLAS_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["schema_version"],
            "partizan.fixed_value_atlas.publication.v1",
        )
        self.assertEqual(manifest["artifact"]["file"], ATLAS.name)
        self.assertEqual(manifest["artifact"]["gzip_bytes"], len(compressed))
        self.assertEqual(
            manifest["artifact"]["gzip_sha256"],
            hashlib.sha256(compressed).hexdigest(),
        )
        self.assertEqual(manifest["artifact"]["decoded_bytes"], len(decoded))
        self.assertEqual(
            manifest["artifact"]["decoded_sha256"],
            hashlib.sha256(decoded).hexdigest(),
        )
        self.assertEqual(
            manifest["publication_url"],
            "https://devinnicholson.github.io/partizan-reproducibility/"
            "evidence/fixed-value-atlas.json.gz",
        )
        self.assertEqual(manifest["hero"]["file"], FIBER_193.name)
        self.assertEqual(manifest["hero"]["observed_quotient_forms"], 193)
        self.assertEqual(manifest["hero"]["target_formal"], "{0|1}")
        atlas_sha256 = atlas.pop("atlas_sha256")
        self.assertEqual(manifest["atlas_sha256"], atlas_sha256)
        self.assertEqual(
            hashlib.sha256(partizan.canonical_json_bytes(atlas)).hexdigest(),
            atlas_sha256,
        )
        self.assertEqual(
            atlas["counts"],
            {"exact_values": 3, "literal_games": 16120, "quotient_forms": 21697},
        )
        self.assertEqual(len(atlas["items"]), 21697)
        self.assertEqual(len(atlas["groups"]), 16120)
        self.assertEqual(
            atlas["source"]["representative_set_sha256"],
            "54488c811edd8a09155864fd1af3c469c7daba334c62788a86882e0e9c404a02",
        )
        self.assertTrue(atlas["source"]["independent_replay"])
        self.assertEqual(atlas["source"]["proposal_count"], 73728)
        self.assertEqual(atlas["source"]["negative_test_families_rejected"], 15)
        self.assertRegex(atlas["source"]["completion_file_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(atlas["source"]["negative_tests_file_sha256"], r"^[0-9a-f]{64}$")
        a = atlas["items"][atlas["motif"]["A"]]
        b = atlas["items"][atlas["motif"]["B"]]
        c = atlas["items"][atlas["motif"]["C"]]
        self.assertEqual([a["t"], b["t"], c["t"]], [0, 0, 0])
        self.assertEqual(len({a["q"], b["q"], c["q"]}), 3)
        self.assertEqual([a["n"], b["n"], c["n"]], [19, 15, 15])
        self.assertEqual(atlas["groups"][a["l"]]["c"], 32)
        self.assertEqual(atlas["groups"][b["l"]]["c"], 54)
        self.assertEqual(b["l"], c["l"])
        self.assertNotEqual(a["l"], b["l"])
        self.assertTrue(all(len(item["p"]) == 6 for item in atlas["items"]))
        self.assertTrue(all(len(group["p"]) == 2 for group in atlas["groups"]))

        def arcs(item: dict[str, object]) -> set[tuple[int, int]]:
            bits = int(str(item["g"]), 16)
            return {
                (source, target)
                for source in range(7)
                for target in range(7)
                if bits & (1 << (source * 7 + target))
            }

        a_arcs, b_arcs, c_arcs = arcs(a), arcs(b), arcs(c)
        self.assertEqual(a_arcs - b_arcs, {(2, 3)})
        self.assertFalse(b_arcs - a_arcs)
        self.assertEqual(c_arcs - b_arcs, {(6, 0)})
        self.assertFalse(b_arcs - c_arcs)
        for label in ("A", "B"):
            dag = atlas["motif_dags"][label]
            item = atlas["items"][atlas["motif"][label]]
            group = atlas["groups"][item["l"]]
            self.assertEqual(dag["nodes"][dag["root"]]["d"], group["d"])

    def test_fixed_value_fiber_193_is_a_small_bound_first_load_asset(self) -> None:
        encoded = FIBER_193.read_bytes()
        hero = json.loads(encoded)
        manifest = json.loads(FIBER_193_MANIFEST.read_text(encoding="utf-8"))

        self.assertLess(len(encoded), 100_000)
        self.assertEqual(hero["schema_version"], "partizan.fixed_value_fiber_193.v1")
        self.assertEqual(
            manifest["schema_version"],
            "partizan.fixed_value_fiber_193.publication.v1",
        )
        self.assertEqual(manifest["artifact"]["file"], FIBER_193.name)
        self.assertEqual(manifest["artifact"]["bytes"], len(encoded))
        self.assertEqual(
            manifest["artifact"]["sha256"], hashlib.sha256(encoded).hexdigest()
        )

        hero_sha256 = hero.pop("hero_sha256")
        self.assertEqual(manifest["hero_sha256"], hero_sha256)
        self.assertEqual(
            hashlib.sha256(partizan.canonical_json_bytes(hero)).hexdigest(),
            hero_sha256,
        )
        selection = hero["selection"]
        self.assertEqual(selection["target_formal"], "{0|1}")
        self.assertEqual(selection["target_label"], "1/2")
        self.assertEqual(
            selection["literal_game_sha256"],
            "830ef59c3454d13324e6841d466a702ef3e168bab7615bb4043d6e6d58e8fd66",
        )
        self.assertEqual(selection["observed_quotient_forms"], 193)
        self.assertEqual(selection["largest_group_tie_count"], 1)
        self.assertEqual(selection["population_count"], 21_697)
        self.assertEqual(
            manifest["selection"],
            {
                "literal_game_sha256": selection["literal_game_sha256"],
                "observed_quotient_forms": 193,
                "target_formal": "{0|1}",
                "target_label": "1/2",
            },
        )

        items = hero["items"]
        self.assertEqual(len(items), 193)
        for key in ("c", "e", "i", "q"):
            self.assertEqual(len({item[key] for item in items}), 193)
        self.assertEqual(len({(item["g"], item["m"]) for item in items}), 193)
        self.assertTrue(all(item["b"] == 3 for item in items))
        self.assertTrue(all(item["n"] == 20 for item in items))
        self.assertTrue(all(item["m"].bit_count() == 4 for item in items))
        self.assertTrue(all(len(item["g"]) == 13 for item in items))
        self.assertTrue(
            all(
                len(item["p"]) == 2
                and all(0 <= coordinate <= 10_000 for coordinate in item["p"])
                for item in items
            )
        )
        self.assertEqual(
            hero["measurements"]["graph_arc_histogram"],
            [
                [17, 1],
                [18, 1],
                [19, 4],
                [20, 14],
                [21, 21],
                [22, 28],
                [23, 44],
                [24, 33],
                [25, 24],
                [26, 17],
                [27, 6],
            ],
        )
        self.assertEqual(hero["measurements"]["graph_arc_range"], [17, 27])
        self.assertEqual(
            hero["measurements"]["observed_distinct_adjacency_colorings"], 193
        )
        dag = hero["literal_game_dag"]
        self.assertEqual(
            dag["nodes"][dag["root"]]["d"], selection["literal_game_sha256"]
        )
        self.assertEqual(hero["claim_boundary"]["aesthetic_preference"], "not_measured")
        self.assertEqual(
            hero["claim_boundary"]["total_mathematical_fiber_size"],
            "not_estimated",
        )
        self.assertEqual(
            manifest["source"]["atlas_sha256"], hero["source"]["atlas_sha256"]
        )


if __name__ == "__main__":
    unittest.main()
