#!/usr/bin/env python3
"""Inspect and validate the Partizan research agent network."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_NETWORK = ROOT / "research_network.json"
DEFAULT_WAVE = ROOT / "waves" / "wave_03_vertical_slice.json"


class NetworkError(ValueError):
    """Raised when the network definition is internally inconsistent."""


def load_network(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_wave_plan(path: Path) -> dict[str, Any]:
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


def validate_wave_plan(
    wave_plan: dict[str, Any], network: dict[str, Any]
) -> list[str]:
    required_top_level = {
        "wave_id",
        "objective",
        "non_negotiables",
        "dispatch_order",
        "tasks",
        "integration_gates",
    }
    missing = required_top_level - wave_plan.keys()
    if missing:
        raise NetworkError(f"wave missing top-level keys: {', '.join(sorted(missing))}")

    warnings: list[str] = []
    agent_ids = _agent_ids(network)
    tasks = wave_plan["tasks"]
    task_ids = {task["id"] for task in tasks}
    if len(task_ids) != len(tasks):
        raise NetworkError("wave task ids must be unique")

    required_task_fields = {
        "id",
        "agent",
        "repo",
        "write_scope",
        "depends_on",
        "prompt",
        "outputs",
        "commands",
        "acceptance",
    }
    for task in tasks:
        missing_task_fields = required_task_fields - task.keys()
        if missing_task_fields:
            raise NetworkError(
                f"wave task {task.get('id', '<unknown>')} missing fields: "
                + ", ".join(sorted(missing_task_fields))
            )
        if task["agent"] not in agent_ids:
            raise NetworkError(
                f"wave task {task['id']} has unknown agent {task['agent']}"
            )
        if not task["write_scope"]:
            raise NetworkError(f"wave task {task['id']} has empty write_scope")
        if not task["outputs"]:
            raise NetworkError(f"wave task {task['id']} has empty outputs")
        if not task["commands"]:
            warnings.append(f"wave task {task['id']} has no verification commands")
        if not task["acceptance"]:
            raise NetworkError(f"wave task {task['id']} has empty acceptance")
        for dep in task["depends_on"]:
            if dep not in task_ids:
                raise NetworkError(
                    f"wave task {task['id']} depends on unknown task {dep}"
                )
            if dep == task["id"]:
                raise NetworkError(f"wave task {task['id']} depends on itself")

    task_deps = {task["id"]: set(task["depends_on"]) for task in tasks}
    dispatched: set[str] = set()
    seen: set[str] = set()
    for index, group in enumerate(wave_plan["dispatch_order"], start=1):
        parallel = group.get("parallel")
        if not isinstance(parallel, list) or not parallel:
            raise NetworkError(f"dispatch group {index} must have non-empty parallel list")
        for task_id in parallel:
            if task_id not in task_ids:
                raise NetworkError(f"dispatch group {index} references unknown task {task_id}")
            if task_id in seen:
                raise NetworkError(f"wave task {task_id} appears in dispatch_order twice")
            missing_deps = task_deps[task_id] - dispatched
            if missing_deps:
                raise NetworkError(
                    f"wave task {task_id} is dispatched before dependencies: "
                    + ", ".join(sorted(missing_deps))
                )
            seen.add(task_id)
        dispatched.update(parallel)

    if seen != task_ids:
        missing_dispatch = task_ids - seen
        raise NetworkError(
            "wave tasks missing from dispatch_order: "
            + ", ".join(sorted(missing_dispatch))
        )

    for gate in wave_plan["integration_gates"]:
        for field in ["id", "command", "success_signal"]:
            if field not in gate:
                raise NetworkError(
                    f"integration gate {gate.get('id', '<unknown>')} missing {field}"
                )

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


def print_wave_plan(wave_plan: dict[str, Any]) -> None:
    print(wave_plan["wave_id"])
    print("=" * len(wave_plan["wave_id"]))
    print(wave_plan["objective"])
    print()

    print("Dispatch Order")
    for index, group in enumerate(wave_plan["dispatch_order"], start=1):
        print(f"- Group {index}: {', '.join(group['parallel'])}")

    print()
    print("Tasks")
    for task in wave_plan["tasks"]:
        deps = ", ".join(task["depends_on"]) if task["depends_on"] else "none"
        print(f"- {task['id']} [{task['agent']}] repo={task['repo']} deps={deps}")

    print()
    print("Integration Gates")
    for gate in wave_plan["integration_gates"]:
        print(f"- {gate['id']}: {gate['command']}")


def print_wave_task(wave_plan: dict[str, Any], task_id: str) -> None:
    tasks = {task["id"]: task for task in wave_plan["tasks"]}
    if task_id not in tasks:
        raise NetworkError(f"unknown wave task: {task_id}")

    task = tasks[task_id]
    print(task["id"])
    print("=" * len(task["id"]))
    print(f"Agent: {task['agent']}")
    print(f"Repo: {task['repo']}")
    print(f"Depends on: {', '.join(task['depends_on']) if task['depends_on'] else 'none'}")
    print()
    print("Prompt")
    print(task["prompt"])
    print()
    print("Write Scope")
    for item in task["write_scope"]:
        print(f"- {item}")
    print()
    print("Outputs")
    for item in task["outputs"]:
        print(f"- {item}")
    print()
    print("Commands")
    for item in task["commands"]:
        print(f"- {item}")
    print()
    print("Acceptance")
    for item in task["acceptance"]:
        print(f"- {item}")


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
    validate_wave_parser = subcommands.add_parser("validate-wave")
    validate_wave_parser.add_argument(
        "wave",
        nargs="?",
        type=Path,
        default=DEFAULT_WAVE,
        help="Path to a wave plan JSON file.",
    )
    wave_plan_parser = subcommands.add_parser("wave-plan")
    wave_plan_parser.add_argument(
        "wave",
        nargs="?",
        type=Path,
        default=DEFAULT_WAVE,
        help="Path to a wave plan JSON file.",
    )
    wave_task_parser = subcommands.add_parser("wave-task")
    wave_task_parser.add_argument("task_id")
    wave_task_parser.add_argument(
        "--wave",
        type=Path,
        default=DEFAULT_WAVE,
        help="Path to a wave plan JSON file.",
    )

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
    elif args.command == "validate-wave":
        wave_plan = load_wave_plan(args.wave)
        wave_warnings = validate_wave_plan(wave_plan, network)
        print(f"wave: ok ({args.wave})")
        for warning in wave_warnings:
            print(f"warning: {warning}")
    elif args.command == "wave-plan":
        wave_plan = load_wave_plan(args.wave)
        validate_wave_plan(wave_plan, network)
        print_wave_plan(wave_plan)
    elif args.command == "wave-task":
        wave_plan = load_wave_plan(args.wave)
        validate_wave_plan(wave_plan, network)
        print_wave_task(wave_plan, args.task_id)


if __name__ == "__main__":
    main()
