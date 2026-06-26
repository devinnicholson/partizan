#!/usr/bin/env python3
"""Inspect and validate the Partizan research agent network."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_NETWORK = ROOT / "research_network.json"


class NetworkError(ValueError):
    """Raised when the network definition is internally inconsistent."""


def load_network(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _agent_ids(network: dict[str, Any]) -> set[str]:
    return {agent["id"] for agent in network["agents"]}


def validate_network(network: dict[str, Any]) -> list[str]:
    required_top_level = {
        "program",
        "mission",
        "operating_principles",
        "global_gates",
        "agents",
        "phases",
        "first_sprint",
    }
    missing = required_top_level - network.keys()
    if missing:
        raise NetworkError(f"missing top-level keys: {', '.join(sorted(missing))}")

    agents = network["agents"]
    agent_ids = _agent_ids(network)
    if len(agent_ids) != len(agents):
        raise NetworkError("agent ids must be unique")

    warnings: list[str] = []

    for agent in agents:
        for field in ["id", "mission", "owns", "deliverables", "verification"]:
            if field not in agent:
                raise NetworkError(f"agent {agent.get('id', '<unknown>')} missing {field}")

    for phase in network["phases"]:
        lead = phase["lead"]
        if lead not in agent_ids:
            raise NetworkError(f"phase {phase['id']} has unknown lead {lead}")
        for task in phase["tasks"]:
            owner = task["owner"]
            if owner not in agent_ids:
                raise NetworkError(
                    f"phase task {task['id']} has unknown owner {owner}"
                )

    for task in network["first_sprint"]:
        owner = task["owner"]
        if owner not in agent_ids:
            raise NetworkError(f"first sprint task {task['id']} has unknown owner {owner}")

    gate_ids = {gate["id"] for gate in network["global_gates"]}
    if len(gate_ids) != len(network["global_gates"]):
        raise NetworkError("global gate ids must be unique")

    if "label_integrity" not in gate_ids:
        warnings.append("label_integrity gate is missing")
    if "ood_integrity" not in gate_ids:
        warnings.append("ood_integrity gate is missing")

    return warnings


def print_summary(network: dict[str, Any]) -> None:
    print(network["program"])
    print("=" * len(network["program"]))
    print(network["mission"])
    print()

    print("Agents")
    for agent in network["agents"]:
        print(f"- {agent['id']}: {agent['mission']}")

    print()
    print("Phases")
    for phase in network["phases"]:
        print(f"- {phase['id']} ({phase['timebox']}), lead={phase['lead']}")

    print()
    print("Global Gates")
    for gate in network["global_gates"]:
        print(f"- {gate['id']}: {gate['standard']}")


def print_first_sprint(network: dict[str, Any]) -> None:
    print("First Sprint")
    print("============")
    for task in network["first_sprint"]:
        print(f"- {task['id']} [{task['owner']}]")
        print(f"  Task: {task['task']}")
        print(f"  Success: {task['success_signal']}")


def print_agent(network: dict[str, Any], agent_id: str) -> None:
    agents = {agent["id"]: agent for agent in network["agents"]}
    if agent_id not in agents:
        raise NetworkError(f"unknown agent: {agent_id}")

    agent = agents[agent_id]
    print(agent["id"])
    print("=" * len(agent["id"]))
    print(agent["mission"])
    print()
    print("Owns")
    for item in agent["owns"]:
        print(f"- {item}")
    print()
    print("Deliverables")
    for item in agent["deliverables"]:
        print(f"- {item}")
    print()
    print("Verification")
    for item in agent["verification"]:
        print(f"- {item}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--network",
        type=Path,
        default=DEFAULT_NETWORK,
        help="Path to the research_network.json definition.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("validate")
    subcommands.add_parser("summary")
    subcommands.add_parser("first-sprint")
    agent_parser = subcommands.add_parser("agent")
    agent_parser.add_argument("agent_id")

    args = parser.parse_args()
    network = load_network(args.network)
    warnings = validate_network(network)

    if args.command == "validate":
        print("network: ok")
        for warning in warnings:
            print(f"warning: {warning}")
    elif args.command == "summary":
        print_summary(network)
    elif args.command == "first-sprint":
        print_first_sprint(network)
    elif args.command == "agent":
        print_agent(network, args.agent_id)


if __name__ == "__main__":
    main()
