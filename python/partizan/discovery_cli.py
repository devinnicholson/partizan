"""Command-line validation for Partizan discovery contracts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .discovery import (
    build_ranker_input,
    canonical_jsonl_bytes,
    load_json,
    load_jsonl,
    validate_candidate_pool_manifest,
    validate_candidate_pool_manifest_v3,
    validate_candidate_proposal,
    validate_discovery_bundle,
    validate_discovery_run,
    validate_generation_receipt,
    validate_generation_receipt_v2,
    validate_target_spec,
    validate_verifier_result,
)


def _report(errors: list[str]) -> int:
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("discovery contract: ok")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    target = commands.add_parser("validate-target")
    target.add_argument("target", type=Path)

    proposals = commands.add_parser("validate-proposals")
    proposals.add_argument("--target", type=Path, required=True)
    proposals.add_argument("proposals", type=Path)

    results = commands.add_parser("validate-results")
    results.add_argument("--target", type=Path, required=True)
    results.add_argument("--proposals", type=Path, required=True)
    results.add_argument("results", type=Path)

    pool = commands.add_parser("validate-pool")
    pool.add_argument("--target", type=Path, required=True)
    pool.add_argument("--proposals", type=Path, required=True)
    pool.add_argument("pool", type=Path)
    pool.add_argument("--repository-root", type=Path, default=Path.cwd())

    receipt = commands.add_parser("validate-generation-receipt")
    receipt.add_argument("--target", type=Path, required=True)
    receipt.add_argument("--proposals", type=Path, required=True)
    receipt.add_argument("receipt", type=Path)
    receipt.add_argument("--repository-root", type=Path, default=Path.cwd())

    run = commands.add_parser("validate-run")
    run.add_argument("--target", type=Path, required=True)
    run.add_argument("--proposals", type=Path, required=True)
    run.add_argument("--results", type=Path, required=True)
    run.add_argument("--pool", type=Path, required=True)
    run.add_argument("run", type=Path)

    bundle = commands.add_parser("validate-bundle")
    bundle.add_argument("--target", type=Path, required=True)
    bundle.add_argument("--proposals", type=Path, required=True)
    bundle.add_argument("--results", type=Path, required=True)
    bundle.add_argument("--pool", type=Path, required=True)
    bundle.add_argument("--run", type=Path, required=True)
    bundle.add_argument("--repository-root", type=Path, default=Path.cwd())

    ranker = commands.add_parser("ranker-inputs")
    ranker.add_argument("--target", type=Path, required=True)
    ranker.add_argument("--proposals", type=Path, required=True)
    ranker.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        target = load_json(args.target)
        if args.command == "validate-target":
            return _report(validate_target_spec(target))

        proposals = load_jsonl(args.proposals)
        if args.command == "validate-proposals":
            errors = validate_target_spec(target)
            for index, proposal in enumerate(proposals):
                errors.extend(
                    f"proposals[{index}]: {error}"
                    for error in validate_candidate_proposal(proposal, target)
                )
            return _report(errors)

        if args.command == "validate-generation-receipt":
            receipt = load_json(args.receipt)
            if receipt.get("schema_version") == (
                "partizan.candidate_generation_receipt.v0.2"
            ):
                return _report(
                    validate_target_spec(target)
                    + validate_generation_receipt_v2(
                        receipt, target, proposals, args.repository_root
                    )
                )
            return _report(
                validate_target_spec(target)
                + validate_generation_receipt(receipt, target, proposals)
            )

        if args.command == "validate-pool":
            pool = load_json(args.pool)
            if pool.get("schema_version") == (
                "partizan.candidate_pool_manifest.v0.3"
            ):
                return _report(
                    validate_target_spec(target)
                    + validate_candidate_pool_manifest_v3(
                        pool, target, proposals, args.repository_root
                    )
                )
            return _report(
                validate_target_spec(target)
                + validate_candidate_pool_manifest(
                    pool,
                    target,
                    proposals,
                    args.proposals,
                    repository_root=args.repository_root,
                )
            )

        results = load_jsonl(args.results)
        proposals_by_id = {
            proposal.get("proposal_id"): proposal for proposal in proposals
        }
        if args.command == "validate-results":
            errors = validate_target_spec(target)
            for index, result in enumerate(results):
                proposal = proposals_by_id.get(result.get("proposal_id"))
                if proposal is None:
                    errors.append(f"results[{index}]: unknown proposal_id")
                else:
                    errors.extend(
                        f"results[{index}]: {error}"
                        for error in validate_verifier_result(
                            result, target, proposal
                        )
                    )
            return _report(errors)

        if args.command == "validate-run":
            pool = load_json(args.pool)
            run = load_json(args.run)
            return _report(
                validate_discovery_run(
                    run, target, pool, proposals, results
                )
            )

        if args.command == "validate-bundle":
            return _report(
                validate_discovery_bundle(
                    args.target,
                    args.proposals,
                    args.results,
                    args.pool,
                    args.run,
                    repository_root=args.repository_root,
                )
            )

        if args.command == "ranker-inputs":
            errors = validate_target_spec(target)
            for proposal in proposals:
                errors.extend(validate_candidate_proposal(proposal, target))
            if errors:
                return _report(errors)
            payload = canonical_jsonl_bytes(
                build_ranker_input(target, proposal) for proposal in proposals
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(payload)
            print(f"ranker inputs: ok ({args.output}, rows={len(proposals)})")
            return 0
    except (OSError, ValueError) as error:
        print(f"partizan-discovery: {error}", file=sys.stderr)
        return 1

    raise AssertionError(f"unhandled command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
