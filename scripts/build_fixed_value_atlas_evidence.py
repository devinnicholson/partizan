#!/usr/bin/env python3
"""Build the browser atlas from the independently replayed order-7 study."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "partizan.fixed_value_atlas.v1"
HERO_SCHEMA_VERSION = "partizan.fixed_value_fiber_193.v1"
TARGETS = ("0", "*", "{0|1}")
TARGET_LABELS = {"0": "0", "*": "*", "{0|1}": "1/2"}
DEFAULT_OUTPUT = Path("visualizer/public/evidence/fixed-value-atlas.json.gz")
DEFAULT_HERO_OUTPUT = Path("visualizer/public/evidence/fixed-value-fiber-193.json")
DEFAULT_HERO_MANIFEST = Path(
    "visualizer/public/evidence/fixed-value-fiber-193.manifest.json"
)
DEFAULT_MANIFEST = Path("visualizer/public/evidence/fixed-value-atlas.manifest.json")
PUBLICATION_URL = (
    "https://devinnicholson.github.io/partizan-reproducibility/"
    "evidence/fixed-value-atlas.json.gz"
)
HERO_PUBLICATION_URL = (
    "https://devinnicholson.github.io/partizan-reproducibility/"
    "evidence/fixed-value-fiber-193.json"
)
HERO_EXPECTED_TARGET = "{0|1}"
HERO_EXPECTED_LITERAL_SHA256 = (
    "830ef59c3454d13324e6841d466a702ef3e168bab7615bb4043d6e6d58e8fd66"
)
HERO_EXPECTED_QUOTIENT_FORMS = 193
DESCRIPTORS = (
    "graph_arc_count",
    "blue_vertex_count",
    "red_vertex_count",
    "distinct_game_tree_node_count",
    "distinct_game_tree_edge_count",
    "game_birthday",
    "root_dominated_option_count",
    "root_reversible_option_count",
    "root_simplification_count",
)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def declared_self_hash(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    declared = payload.pop(field, None)
    if not isinstance(declared, str):
        raise ValueError(f"missing declared self-hash {field}")
    observed = hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    if observed != declared:
        raise ValueError(f"{field} mismatch: {observed} != {declared}")
    return declared


def adjacency_hex(candidate: dict[str, Any]) -> str:
    order = int(candidate["order"])
    if order != 7:
        raise ValueError(f"atlas expects order 7, observed {order}")
    bits = 0
    for source, target in candidate["arcs"]:
        bits |= 1 << (int(source) * order + int(target))
    return f"{bits:013x}"


def blue_mask(candidate: dict[str, Any]) -> int:
    mask = 0
    for vertex in candidate["blue_vertices"]:
        mask |= 1 << int(vertex)
    return mask


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def accepted_heldout(event: dict[str, Any]) -> bool:
    decision = event.get("exact_decision") or {}
    retention = event.get("retention") or {}
    return bool(
        event.get("target") in TARGETS
        and event.get("weakly_connected") is True
        and event.get("leakage_collision") is False
        and decision.get("equal") is True
        and event.get("quotient")
        and event.get("measurements")
        and retention.get("inserted") is True
    )


def representative_set_sha256(
    representatives: dict[tuple[str, str], dict[str, Any]],
) -> str:
    ordered = []
    for target in TARGETS:
        rows = [
            event
            for (event_target, _), event in representatives.items()
            if event_target == target
        ]
        for event in sorted(rows, key=lambda row: row["quotient"]["quotient_sha256"]):
            measurements = event["measurements"]
            ordered.append(
                {
                    "target": target,
                    "candidate_sha256": event["candidate_sha256"],
                    "descriptor_cell": measurements["descriptor_cell"],
                    "descriptors": {key: measurements[key] for key in DESCRIPTORS},
                    "first_global_event_index": event["global_event_index"],
                    "literal_game_sha256": event["exact_decision"][
                        "candidate_root_game_sha256"
                    ],
                    "quotient_sha256": event["quotient"]["quotient_sha256"],
                }
            )
    return hashlib.sha256(
        json.dumps(
            ordered, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def literal_dag(source: Path, event: dict[str, Any]) -> dict[str, Any]:
    derivation_ref = event["retention"]["sidecars"]["derivation"]
    derivation_path = source / derivation_ref["path"]
    if file_sha256(derivation_path) != derivation_ref["sha256"]:
        raise ValueError(f"{derivation_path}: derivation hash mismatch")
    derivation = load_json(derivation_path)

    node_rows: dict[str, dict[str, Any]] = {}
    edges: set[tuple[str, str, str]] = set()
    for state in derivation["states"]:
        digest = state["literal_game_sha256"]
        node_rows.setdefault(
            digest,
            {
                "d": digest,
                "s": state["literal_serialization"],
                "x": bool(state["terminal"]),
            },
        )
        edges.update((digest, option, "L") for option in state["left_option_game_sha256"])
        edges.update((digest, option, "R") for option in state["right_option_game_sha256"])

    root = derivation["root"]["literal_game_sha256"]
    depths = {root: 0}
    frontier = [root]
    while frontier:
        parent = frontier.pop(0)
        for source_digest, target_digest, _ in edges:
            if source_digest != parent:
                continue
            next_depth = depths[parent] + 1
            if target_digest not in depths or next_depth < depths[target_digest]:
                depths[target_digest] = next_depth
                frontier.append(target_digest)

    ordered_digests = sorted(node_rows, key=lambda digest: (depths.get(digest, 99), digest))
    index = {digest: item_index for item_index, digest in enumerate(ordered_digests)}
    return {
        "derivation_sha256": derivation_ref["sha256"],
        "root": index[root],
        "state_count": len(derivation["states"]),
        "nodes": [
            {**node_rows[digest], "r": depths.get(digest, 99)}
            for digest in ordered_digests
        ],
        "edges": [
            {"f": index[parent], "p": player, "t": index[option]}
            for parent, option, player in sorted(
                edges, key=lambda row: (index[row[0]], index[row[1]], row[2])
            )
        ],
    }


def add_layout(items: list[dict[str, Any]], groups: list[dict[str, Any]]) -> None:
    """Attach deterministic integer coordinates for the three identity layers."""

    target_centres = (1700, 5000, 8300)
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    target_items = {
        target: [index for index, item in enumerate(items) if item["t"] == target]
        for target in range(len(TARGETS))
    }
    target_groups = {
        target: [index for index, group in enumerate(groups) if group["t"] == target]
        for target in range(len(TARGETS))
    }
    group_members: dict[int, list[int]] = {index: [] for index in range(len(groups))}
    for index, item in enumerate(items):
        group_members[item["l"]].append(index)

    graph_positions: dict[int, tuple[int, int]] = {}
    literal_positions: dict[int, tuple[int, int]] = {}
    value_positions: dict[int, tuple[int, int]] = {}

    for target, indexes in target_items.items():
        arcs = [items[index]["a"] for index in indexes]
        nodes = [items[index]["n"] for index in indexes]
        min_arc, max_arc = min(arcs), max(arcs)
        min_node, max_node = min(nodes), max(nodes)
        node_span = math.log1p(max_node) - math.log1p(min_node)

        for rank, index in enumerate(indexes):
            item = items[index]
            jitter_x = int(item["q"][0:4], 16) % 41 - 20
            jitter_y = int(item["q"][4:8], 16) % 41 - 20
            arc_fraction = (item["a"] - min_arc) / max(1, max_arc - min_arc)
            node_fraction = (
                (math.log1p(item["n"]) - math.log1p(min_node)) / node_span
                if node_span
                else 0.5
            )
            graph_positions[index] = (
                round(target_centres[target] - 1220 + arc_fraction * 2440 + jitter_x),
                round(8500 - node_fraction * 7000 + jitter_y),
            )

            angle = rank * golden_angle
            radius = math.sqrt((rank + 0.5) / len(indexes))
            value_positions[index] = (
                round(target_centres[target] + math.cos(angle) * radius * 250),
                round(5000 + math.sin(angle) * radius * 250),
            )

        groups_for_target = target_groups[target]
        group_centres: dict[int, tuple[float, float]] = {}
        for rank, group_index in enumerate(groups_for_target):
            angle = rank * golden_angle
            radius = math.sqrt((rank + 0.5) / len(groups_for_target))
            group_centres[group_index] = (
                target_centres[target] + math.cos(angle) * radius * 1200,
                5000 + math.sin(angle) * radius * 3450,
            )

        for group_index in groups_for_target:
            members = group_members[group_index]
            centre_x, centre_y = group_centres[group_index]
            groups[group_index]["p"] = [round(centre_x), round(centre_y)]
            for member_rank, item_index in enumerate(members):
                if len(members) == 1:
                    local_x = local_y = 0.0
                else:
                    angle = member_rank * golden_angle
                    radius = math.sqrt((member_rank + 0.5) / len(members))
                    local_x = math.cos(angle) * radius * min(92, 11 * math.sqrt(len(members)))
                    local_y = math.sin(angle) * radius * min(180, 20 * math.sqrt(len(members)))
                literal_positions[item_index] = (
                    round(centre_x + local_x),
                    round(centre_y + local_y),
                )

    for index, item in enumerate(items):
        item["p"] = [
            *graph_positions[index],
            *literal_positions[index],
            *value_positions[index],
        ]


def build_hero(
    source: Path,
    atlas: dict[str, Any],
    ordered_events: list[dict[str, Any]],
    literal_counts: dict[tuple[str, str], int],
) -> dict[str, Any]:
    """Build the small, independently checkable landing payload."""

    ranked_literal_keys = sorted(
        literal_counts,
        key=lambda key: (-literal_counts[key], TARGETS.index(key[0]), key[1]),
    )
    hero_target, hero_literal = ranked_literal_keys[0]
    hero_count = literal_counts[(hero_target, hero_literal)]
    largest_group_tie_count = sum(
        count == hero_count for count in literal_counts.values()
    )
    expected = (
        HERO_EXPECTED_TARGET,
        HERO_EXPECTED_LITERAL_SHA256,
        HERO_EXPECTED_QUOTIENT_FORMS,
    )
    observed = (hero_target, hero_literal, hero_count)
    if observed != expected:
        raise ValueError(f"largest observed literal-game group changed: {observed}")
    if largest_group_tie_count != 1:
        raise ValueError("the largest observed literal-game group is no longer unique")

    hero_events = sorted(
        (
            event
            for event in ordered_events
            if event["target"] == hero_target
            and event["exact_decision"]["candidate_root_game_sha256"]
            == hero_literal
        ),
        key=lambda event: event["quotient"]["quotient_sha256"],
    )
    if len(hero_events) != hero_count:
        raise ValueError("hero event count does not match its literal-game group")
    hero_quotients = {
        event["quotient"]["quotient_sha256"] for event in hero_events
    }
    if len(hero_quotients) != hero_count:
        raise ValueError("hero graph quotients are not pairwise distinct")
    if len({event["candidate_sha256"] for event in hero_events}) != hero_count:
        raise ValueError("hero candidate digraphs are not pairwise distinct")

    records: list[dict[str, Any]] = []
    for event in hero_events:
        if not accepted_heldout(event):
            raise ValueError(
                "hero member falls outside the checked population predicate"
            )
        declared_self_hash(event, "event_sha256")
        candidate_sha256 = hashlib.sha256(
            json.dumps(
                event["candidate"],
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if candidate_sha256 != event["candidate_sha256"]:
            raise ValueError("hero candidate hash does not match its digraph")
        quotient_sha256 = hashlib.sha256(
            event["quotient"]["canonical_code"].encode("utf-8")
        ).hexdigest()
        if quotient_sha256 != event["quotient"]["quotient_sha256"]:
            raise ValueError("hero quotient hash does not match its canonical code")
        measurement = event["measurements"]
        decision = event["exact_decision"]
        if not (
            len(event["candidate"]["arcs"]) == measurement["graph_arc_count"]
            and len(event["candidate"]["blue_vertices"])
            == measurement["blue_vertex_count"]
            and decision["game_birthday"] == measurement["game_birthday"]
            and decision["distinct_game_tree_node_count"]
            == measurement["distinct_game_tree_node_count"]
            and event["transition"]["candidate_literal_game_sha256"]
            == hero_literal
            and event["retention"]["sidecars"]["candidate_root_game_sha256"]
            == hero_literal
        ):
            raise ValueError("hero event measurements or literal bindings changed")
        records.append(
            {
                "a": int(measurement["graph_arc_count"]),
                "b": int(measurement["game_birthday"]),
                "c": event["candidate_sha256"],
                "e": event["event_sha256"],
                "g": adjacency_hex(event["candidate"]),
                "i": int(event["global_event_index"]),
                "m": blue_mask(event["candidate"]),
                "n": int(measurement["distinct_game_tree_node_count"]),
                "q": event["quotient"]["quotient_sha256"],
            }
        )

    if len({(record["g"], record["m"]) for record in records}) != hero_count:
        raise ValueError("hero adjacency/color encodings are not pairwise distinct")

    arc_values = sorted({record["a"] for record in records})
    arc_histogram = []
    for arc_rank, arc_count in enumerate(arc_values):
        members = sorted(
            (record for record in records if record["a"] == arc_count),
            key=lambda record: record["q"],
        )
        x = round(800 + arc_rank / max(1, len(arc_values) - 1) * 8400)
        for member_rank, record in enumerate(members):
            record["p"] = [
                x,
                round(700 + (member_rank + 0.5) / len(members) * 8600),
            ]
        arc_histogram.append([arc_count, len(members)])

    literal_game_dag = literal_dag(source, hero_events[0])
    if literal_game_dag["nodes"][literal_game_dag["root"]]["d"] != hero_literal:
        raise ValueError(
            "hero derivation root does not match the selected literal game"
        )

    payload = {
        "schema_version": HERO_SCHEMA_VERSION,
        "source": {
            **atlas["source"],
            "atlas_sha256": atlas["atlas_sha256"],
        },
        "selection": {
            "population_count": atlas["counts"]["quotient_forms"],
            "population_rule": (
                "For each target, retain the first accepted held-out event for "
                "every distinct graph-quotient SHA-256."
            ),
            "group_identity": "(target, candidate_root_game_sha256)",
            "rule": (
                "Choose the observed literal-game group with the most "
                "quotient-distinct representatives; break ties by target order "
                "0, *, {0|1}, then literal-game SHA-256."
            ),
            "target_formal": hero_target,
            "target_label": TARGET_LABELS[hero_target],
            "literal_game_sha256": hero_literal,
            "observed_quotient_forms": hero_count,
            "largest_group_tie_count": largest_group_tie_count,
        },
        "measurements": {
            "graph_arc_range": [arc_values[0], arc_values[-1]],
            "graph_arc_histogram": arc_histogram,
            "game_birthday_values": sorted({record["b"] for record in records}),
            "complete_game_node_values": sorted(
                {record["n"] for record in records}
            ),
            "blue_vertex_count_values": sorted(
                {record["m"].bit_count() for record in records}
            ),
            "observed_distinct_adjacency_colorings": len(
                {(record["g"], record["m"]) for record in records}
            ),
        },
        "encoding": {
            "g": "49 adjacency bits in source-major order, lower-case hexadecimal",
            "m": "seven-bit blue-vertex mask; unset vertices are red",
            "item_keys": {
                "a": "graph arc count",
                "b": "game birthday",
                "c": "candidate sha256",
                "e": "source event sha256",
                "g": "adjacency encoding",
                "i": "source global event index",
                "m": "blue-vertex mask",
                "n": "distinct complete-game node count",
                "p": "hero layout coordinate",
                "q": "graph quotient sha256",
            },
            "layout": {
                "coordinate_extent": [0, 10000],
                "x": "directed-arc count, 17 through 27",
                "y": "quotient-digest order within each arc-count column",
                "distance_boundary": (
                    "Only x encodes a measurement; y order and distance do not "
                    "measure graph or aesthetic similarity."
                ),
                "version": "partizan.fixed_value_atlas.hero.layout.v1",
            },
        },
        "claim_boundary": {
            "scope": (
                "Largest literal-game group in the frozen observed population "
                "of quotient-unique held-out exact matches."
            ),
            "total_mathematical_fiber_size": "not_estimated",
            "population_prevalence": "not_estimated",
            "aesthetic_preference": "not_measured",
            "human_preference": "not_measured",
        },
        "literal_game_dag": literal_game_dag,
        "items": records,
    }
    return {
        **payload,
        "hero_sha256": hashlib.sha256(canonical_bytes(payload)).hexdigest(),
    }


def build_artifacts(source: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path = source / "manifest.json"
    summary_path = source / "summary.json"
    events_path = source / "events.jsonl"
    verification_path = source / "independent_verification.json"
    completion_path = source / "RUN_COMPLETE.json"
    negative_tests_path = source / "negative_tests.json"
    report_path = source / "STUDY_REPORT.md"
    descriptor_atlas_path = source / "descriptor_atlas_v1.json"

    manifest = load_json(manifest_path)
    summary = load_json(summary_path)
    verification = load_json(verification_path)
    completion = load_json(completion_path)
    negative_tests = load_json(negative_tests_path)
    descriptor_atlas = load_json(descriptor_atlas_path)

    manifest_sha256 = declared_self_hash(manifest, "manifest_sha256")
    summary_sha256 = declared_self_hash(summary, "summary_sha256")
    verification_sha256 = declared_self_hash(verification, "verification_sha256")
    completion_sha256 = declared_self_hash(completion, "completion_sha256")
    negative_tests_sha256 = declared_self_hash(
        negative_tests, "negative_tests_sha256"
    )
    descriptor_atlas_sha256 = declared_self_hash(descriptor_atlas, "atlas_sha256")
    if verification.get("status") != "PASS":
        raise ValueError("the source study has not passed independent replay")
    required_completion = {
        "status": "GO",
        "evidence_eligible": True,
        "independent_replay_pass": True,
        "negative_tests_pass": True,
        "paper_evidence": True,
        "scientific_gate_pass": True,
    }
    for key, expected in required_completion.items():
        if completion.get(key) != expected:
            raise ValueError(
                f"source completion gate {key}={completion.get(key)!r}; expected {expected!r}"
            )
    if negative_tests.get("status") != "PASS":
        raise ValueError("the source corruption tests did not pass")
    rejected_tests = sum(test.get("rejected") is True for test in negative_tests["tests"])
    required_test_count = int(negative_tests["required_family_count"])
    rejected_test_count = int(negative_tests["rejected_family_count"])
    if not (
        rejected_tests == rejected_test_count == required_test_count
        and len(negative_tests["tests"]) == required_test_count
    ):
        raise ValueError("the corruption-family rejection contract is incomplete")
    if summary.get("event_count") != 73_728:
        raise ValueError("the source event count no longer matches the frozen study")

    bound_files = {
        "events_file_sha256": events_path,
        "manifest_file_sha256": manifest_path,
        "negative_tests_file_sha256": negative_tests_path,
        "report_file_sha256": report_path,
        "summary_file_sha256": summary_path,
        "verification_file_sha256": verification_path,
    }
    for field, path in bound_files.items():
        observed = file_sha256(path)
        if completion.get(field) != observed:
            raise ValueError(
                f"completion binding {field} mismatch: {observed} != {completion.get(field)}"
            )
    descriptor_source = descriptor_atlas.get("source") or {}
    expected_descriptor_source = {
        "event_count": summary["event_count"],
        "events_sha256": file_sha256(events_path),
        "independent_replay_pass": True,
        "independent_verification_sha256": file_sha256(verification_path),
        "run_complete_sha256": file_sha256(completion_path),
        "run_complete_status": "GO",
        "summary_declared_sha256": summary_sha256,
        "summary_sha256": file_sha256(summary_path),
    }
    for key, expected in expected_descriptor_source.items():
        if descriptor_source.get(key) != expected:
            raise ValueError(
                f"descriptor atlas source binding {key} mismatch: "
                f"{descriptor_source.get(key)!r} != {expected!r}"
            )

    representatives: dict[tuple[str, str], dict[str, Any]] = {}
    event_count = 0
    with events_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            event_count += 1
            event = json.loads(line)
            if event["global_event_index"] != line_number - 1:
                raise ValueError(f"event index discontinuity at line {line_number}")
            if not accepted_heldout(event):
                continue
            quotient = event["quotient"]["quotient_sha256"]
            representatives.setdefault((event["target"], quotient), event)

    if event_count != summary["event_count"]:
        raise ValueError("events.jsonl does not match summary event_count")

    expected_by_target = {
        target: summary["target_unions"][target]["counts"]
        ["heldout_quotient_unique_representatives"]
        for target in TARGETS
    }
    observed_by_target = {
        target: sum(key[0] == target for key in representatives) for target in TARGETS
    }
    if observed_by_target != expected_by_target:
        raise ValueError(
            f"representative union mismatch: {observed_by_target} != {expected_by_target}"
        )
    observed_representative_sha = representative_set_sha256(representatives)
    if observed_representative_sha != descriptor_atlas["representative_set_sha256"]:
        raise ValueError("representative population no longer matches descriptor atlas")

    ordered_events = sorted(
        representatives.values(),
        key=lambda row: (
            TARGETS.index(row["target"]),
            row["global_event_index"],
            row["quotient"]["quotient_sha256"],
        ),
    )

    literal_keys = sorted(
        {
            (event["target"], event["exact_decision"]["candidate_root_game_sha256"])
            for event in ordered_events
        },
        key=lambda row: (TARGETS.index(row[0]), row[1]),
    )
    literal_index = {key: index for index, key in enumerate(literal_keys)}
    literal_counts = {key: 0 for key in literal_keys}
    for event in ordered_events:
        key = (event["target"], event["exact_decision"]["candidate_root_game_sha256"])
        literal_counts[key] += 1

    groups = [
        {
            "c": literal_counts[key],
            "d": key[1],
            "t": TARGETS.index(key[0]),
        }
        for key in literal_keys
    ]

    items: list[dict[str, Any]] = []
    candidate_to_item: dict[str, int] = {}
    for index, event in enumerate(ordered_events):
        candidate = event["candidate"]
        measurement = event["measurements"]
        literal = event["exact_decision"]["candidate_root_game_sha256"]
        record = {
            "a": int(measurement["graph_arc_count"]),
            "b": int(measurement["game_birthday"]),
            "g": adjacency_hex(candidate),
            "i": int(event["global_event_index"]),
            "l": literal_index[(event["target"], literal)],
            "m": blue_mask(candidate),
            "n": int(measurement["distinct_game_tree_node_count"]),
            "q": event["quotient"]["quotient_sha256"],
            "t": TARGETS.index(event["target"]),
        }
        items.append(record)
        candidate_to_item[event["candidate_sha256"]] = index

    add_layout(items, groups)

    motif_candidates = {
        "A": "cb1ffa7f8405ffac7e9cdb28f2da6276adfb403ae131e8bc28450bf5b14210e3",
        "B": "a09060e0145f2b2e8ec37474790955aed9a4ebb3ac272f8e22b47c4065cbee53",
        "C": "6d3e2117b482af4a7054103291ba33ae269b6294220afc68fbe1ce6d25fb6555",
    }
    motif = {label: candidate_to_item[digest] for label, digest in motif_candidates.items()}
    motif_events = {
        label: next(
            event for event in ordered_events if event["candidate_sha256"] == digest
        )
        for label, digest in motif_candidates.items()
    }
    motif_dags = {
        "A": literal_dag(source, motif_events["A"]),
        "B": literal_dag(source, motif_events["B"]),
    }
    motif_literals = {
        label: event["exact_decision"]["candidate_root_game_sha256"]
        for label, event in motif_events.items()
    }
    motif_quotients = {
        label: event["quotient"]["quotient_sha256"]
        for label, event in motif_events.items()
    }
    if set(event["target"] for event in motif_events.values()) != {"0"}:
        raise ValueError("the A/B/C motif no longer lies inside target value zero")
    if len(set(motif_quotients.values())) != 3:
        raise ValueError("the A/B/C graph quotients are no longer pairwise distinct")
    if not (
        motif_literals["A"] != motif_literals["B"] == motif_literals["C"]
    ):
        raise ValueError("the A/B/C literal-game crossing no longer holds")
    if [
        motif_events[label]["measurements"]["distinct_game_tree_node_count"]
        for label in "ABC"
    ] != [19, 15, 15]:
        raise ValueError("the A/B/C complete-game node counts changed")
    motif_arcs = {
        label: {tuple(arc) for arc in event["candidate"]["arcs"]}
        for label, event in motif_events.items()
    }
    if not (
        motif_arcs["A"] - motif_arcs["B"] == {(2, 3)}
        and not motif_arcs["B"] - motif_arcs["A"]
        and motif_arcs["C"] - motif_arcs["B"] == {(6, 0)}
        and not motif_arcs["B"] - motif_arcs["C"]
    ):
        raise ValueError("the certified A→B→C one-arc transitions changed")
    for label in ("A", "B"):
        dag = motif_dags[label]
        if dag["nodes"][dag["root"]]["d"] != motif_literals[label]:
            raise ValueError(f"the {label} derivation root does not match its event")

    literal_by_target = {
        target: sum(key[0] == target for key in literal_keys) for target in TARGETS
    }
    expected_literals = {
        target: summary["target_unions"][target]["counts"]["heldout_literal_game_digests"]
        for target in TARGETS
    }
    if literal_by_target != expected_literals:
        raise ValueError(
            f"literal-game union mismatch: {literal_by_target} != {expected_literals}"
        )
    motif_group_counts = {
        label: groups[items[index]["l"]]["c"] for label, index in motif.items()
    }
    if motif_group_counts != {"A": 32, "B": 54, "C": 54}:
        raise ValueError(f"the A/B/C observed island sizes changed: {motif_group_counts}")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "completion_file_sha256": file_sha256(completion_path),
            "completion_sha256": completion_sha256,
            "descriptor_atlas_file_sha256": file_sha256(descriptor_atlas_path),
            "descriptor_atlas_sha256": descriptor_atlas_sha256,
            "events_file_sha256": file_sha256(events_path),
            "independent_replay": completion["independent_replay_pass"],
            "manifest_file_sha256": file_sha256(manifest_path),
            "manifest_sha256": manifest_sha256,
            "negative_tests_file_sha256": file_sha256(negative_tests_path),
            "negative_tests_sha256": negative_tests_sha256,
            "negative_test_families_rejected": rejected_test_count,
            "proposal_count": event_count,
            "report_file_sha256": file_sha256(report_path),
            "summary_file_sha256": file_sha256(summary_path),
            "summary_sha256": summary_sha256,
            "verification_file_sha256": file_sha256(verification_path),
            "verification_sha256": verification_sha256,
            "representative_set_sha256": observed_representative_sha,
        },
        "counts": {
            "exact_values": len(TARGETS),
            "literal_games": len(groups),
            "quotient_forms": len(items),
        },
        "targets": [
            {
                "formal": target,
                "label": TARGET_LABELS[target],
                "literal_games": literal_by_target[target],
                "quotient_forms": observed_by_target[target],
                "graph_arc_range": [
                    min(
                        item["a"]
                        for item in items
                        if item["t"] == TARGETS.index(target)
                    ),
                    max(
                        item["a"]
                        for item in items
                        if item["t"] == TARGETS.index(target)
                    ),
                ],
                "complete_game_node_range": [
                    min(
                        item["n"]
                        for item in items
                        if item["t"] == TARGETS.index(target)
                    ),
                    max(
                        item["n"]
                        for item in items
                        if item["t"] == TARGETS.index(target)
                    ),
                ],
            }
            for target in TARGETS
        ],
        "encoding": {
            "g": "49 adjacency bits in source-major order, lower-case hexadecimal",
            "m": "seven-bit blue-vertex mask; unset vertices are red",
            "item_keys": {
                "a": "graph arc count",
                "b": "game birthday",
                "g": "adjacency encoding",
                "i": "source global event index",
                "l": "literal-game group index",
                "m": "blue-vertex mask",
                "n": "distinct complete-game node count",
                "q": "graph quotient sha256",
                "t": "target index",
            },
            "group_keys": {
                "c": "number of quotient forms in the literal-game group",
                "d": "literal-game sha256",
                "p": "complete-game layer centre in the declared coordinate extent",
                "t": "target index",
            },
            "layout": {
                "coordinate_extent": [0, 10000],
                "graph_form": "x is directed-arc count; y is log complete-game node count; deterministic digest jitter separates ties",
                "complete_game": "digest-ordered deterministic packing by literal-game identity; distance between islands does not measure similarity",
                "exact_value": "target-separated deterministic packing",
                "version": "partizan.fixed_value_atlas.layout.v1",
            },
        },
        "motif": motif,
        "motif_dags": {**motif_dags, "C": "B"},
        "groups": groups,
        "items": items,
    }
    atlas = {
        **payload,
        "atlas_sha256": hashlib.sha256(canonical_bytes(payload)).hexdigest(),
    }
    return atlas, build_hero(source, atlas, ordered_events, literal_counts)


def build_atlas(source: Path) -> dict[str, Any]:
    """Compatibility wrapper for callers that only need the complete atlas."""

    atlas, _ = build_artifacts(source)
    return atlas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--hero-output", type=Path, default=DEFAULT_HERO_OUTPUT)
    parser.add_argument("--hero-manifest", type=Path, default=DEFAULT_HERO_MANIFEST)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    atlas, hero = build_artifacts(args.source)
    payload = canonical_bytes(atlas)
    hero_payload = canonical_bytes(hero)
    compressed = gzip.compress(payload, compresslevel=9, mtime=0)
    hero_manifest = canonical_bytes(
        {
            "schema_version": "partizan.fixed_value_fiber_193.publication.v1",
            "artifact": {
                "bytes": len(hero_payload),
                "content_type": "application/json",
                "file": args.hero_output.name,
                "sha256": hashlib.sha256(hero_payload).hexdigest(),
            },
            "hero_sha256": hero["hero_sha256"],
            "publication_url": HERO_PUBLICATION_URL,
            "selection": {
                "literal_game_sha256": hero["selection"][
                    "literal_game_sha256"
                ],
                "observed_quotient_forms": hero["selection"][
                    "observed_quotient_forms"
                ],
                "target_formal": hero["selection"]["target_formal"],
                "target_label": hero["selection"]["target_label"],
            },
            "source": {
                "atlas_sha256": atlas["atlas_sha256"],
                "completion_sha256": atlas["source"]["completion_sha256"],
                "representative_set_sha256": atlas["source"][
                    "representative_set_sha256"
                ],
            },
        }
    )
    manifest = canonical_bytes(
        {
            "schema_version": "partizan.fixed_value_atlas.publication.v1",
            "artifact": {
                "content_encoding": "gzip",
                "content_type": "application/json",
                "decoded_bytes": len(payload),
                "decoded_sha256": hashlib.sha256(payload).hexdigest(),
                "file": args.output.name,
                "gzip_bytes": len(compressed),
                "gzip_sha256": hashlib.sha256(compressed).hexdigest(),
            },
            "atlas_sha256": atlas["atlas_sha256"],
            "counts": atlas["counts"],
            "hero": {
                "bytes": len(hero_payload),
                "content_type": "application/json",
                "file": args.hero_output.name,
                "hero_sha256": hero["hero_sha256"],
                "literal_game_sha256": hero["selection"]["literal_game_sha256"],
                "observed_quotient_forms": hero["selection"][
                    "observed_quotient_forms"
                ],
                "publication_url": HERO_PUBLICATION_URL,
                "sha256": hashlib.sha256(hero_payload).hexdigest(),
                "target_formal": hero["selection"]["target_formal"],
                "target_label": hero["selection"]["target_label"],
            },
            "publication_url": PUBLICATION_URL,
            "source": {
                "completion_sha256": atlas["source"]["completion_sha256"],
                "representative_set_sha256": atlas["source"]
                ["representative_set_sha256"],
            },
        }
    )
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != compressed:
            raise SystemExit(f"{args.output}: generated atlas is stale")
        if (
            not args.hero_output.is_file()
            or args.hero_output.read_bytes() != hero_payload
        ):
            raise SystemExit(f"{args.hero_output}: generated hero evidence is stale")
        if (
            not args.hero_manifest.is_file()
            or args.hero_manifest.read_bytes() != hero_manifest
        ):
            raise SystemExit(f"{args.hero_manifest}: generated hero manifest is stale")
        if not args.manifest.is_file() or args.manifest.read_bytes() != manifest:
            raise SystemExit(f"{args.manifest}: generated manifest is stale")
        print(f"{args.output}: compressed atlas evidence is current")
        print(f"{args.hero_output}: hero evidence is current")
        print(f"{args.hero_manifest}: hero manifest is current")
        print(f"{args.manifest}: publication manifest is current")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.hero_output.parent.mkdir(parents=True, exist_ok=True)
    args.hero_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(compressed)
    args.hero_output.write_bytes(hero_payload)
    args.hero_manifest.write_bytes(hero_manifest)
    args.manifest.write_bytes(manifest)
    print(
        f"{args.output}: wrote {len(compressed)} compressed bytes "
        f"({len(payload)} decoded)"
    )
    print(f"{args.hero_output}: wrote {len(hero_payload)} bytes")
    print(f"{args.hero_manifest}: wrote {len(hero_manifest)} bytes")
    print(f"{args.manifest}: wrote {len(manifest)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
