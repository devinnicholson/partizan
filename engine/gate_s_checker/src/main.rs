//! Target-free Wave 69-R Gate S checker.
//!
//! This binary intentionally has no dependency on Astralbase, Thermograph, a
//! target contract, or Partizan's evaluator. It parses only the board field of
//! a FEN and asks the pinned Bitmesh proof API for conservative legal
//! independence.

use std::io::{self, BufRead, Write};
use std::panic::{self, AssertUnwindSafe};
use std::str::FromStr;

use bitmesh::{
    ConservativeLegalIndependenceError, ConservativeLegalIndependenceProof,
    DecompositionCertificateValidationError, DecompositionStatus,
    certify_conservative_legal_independence,
};
use serde::{Deserialize, Serialize};
use shakmaty::Board;

const REQUEST_SCHEMA: &str = "partizan.wave69r_structural_supply_request.v0.1";
const RESULT_SCHEMA: &str = "partizan.wave69r_structural_supply_result.v0.1";
const CHECKER_NAME: &str = "partizan_gate_s_checker";
const CHECKER_VERSION: &str = "0.1.0";
const BITMESH_CRATE_VERSION: &str = "0.1.0";
const BITMESH_SOURCE_COMMIT: &str = "ade3417a007b9c8392d8a153abc4b3ed23edf0aa";
const PROOF_API: &str = "bitmesh:conservative_legal_independence:v0";

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    schema_version: String,
    board_id: String,
    board_fen: String,
}

#[derive(Debug, Serialize)]
struct ResultRow {
    schema_version: &'static str,
    board_id: String,
    checker: CheckerProvenance,
    outcome: Outcome,
    certification: Option<Certification>,
    failure_code: Option<&'static str>,
    predicates: Predicates,
    internal_error: bool,
}

#[derive(Debug, Serialize)]
struct CheckerProvenance {
    name: &'static str,
    version: &'static str,
    bitmesh_crate_version: &'static str,
    bitmesh_source_commit: &'static str,
    proof_api: &'static str,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum Outcome {
    Pass,
    Fail,
    Error,
}

#[derive(Debug, Serialize)]
struct Certification {
    proof_kind: &'static str,
    decomposition_sha256: String,
    component_count: u8,
    barrier_squares: Vec<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum PredicateState {
    Pass,
    Fail,
    NotEvaluated,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
struct Predicates {
    frozen_barrier: PredicateState,
    non_capturable_barrier: PredicateState,
    strict_exactly_two_components: PredicateState,
    no_cross_component_entry: PredicateState,
}

impl Predicates {
    const fn all(state: PredicateState) -> Self {
        Self {
            frozen_barrier: state,
            non_capturable_barrier: state,
            strict_exactly_two_components: state,
            no_cross_component_entry: state,
        }
    }
}

impl CheckerProvenance {
    const fn pinned() -> Self {
        Self {
            name: CHECKER_NAME,
            version: CHECKER_VERSION,
            bitmesh_crate_version: BITMESH_CRATE_VERSION,
            bitmesh_source_commit: BITMESH_SOURCE_COMMIT,
            proof_api: PROOF_API,
        }
    }
}

impl ResultRow {
    fn base(board_id: String) -> Self {
        Self {
            schema_version: RESULT_SCHEMA,
            board_id,
            checker: CheckerProvenance::pinned(),
            outcome: Outcome::Error,
            certification: None,
            failure_code: None,
            predicates: Predicates::all(PredicateState::NotEvaluated),
            internal_error: false,
        }
    }

    fn invalid_board(board_id: String) -> Self {
        let mut row = Self::base(board_id);
        row.outcome = Outcome::Fail;
        row.failure_code = Some("input.invalid_board_fen");
        row
    }

    fn internal_error(board_id: String) -> Self {
        let mut row = Self::base(board_id);
        row.failure_code = Some("checker.internal_error");
        row.internal_error = true;
        row
    }

    fn from_proof(board_id: String, proof: ConservativeLegalIndependenceProof) -> Self {
        let exactly_two = proof.component_count == 2;
        Self {
            schema_version: RESULT_SCHEMA,
            board_id,
            checker: CheckerProvenance::pinned(),
            outcome: if exactly_two {
                Outcome::Pass
            } else {
                Outcome::Fail
            },
            certification: Some(Certification {
                proof_kind: proof.proof_kind,
                decomposition_sha256: proof.decomposition_digest.to_hex(),
                component_count: proof.component_count,
                barrier_squares: proof
                    .barrier
                    .into_iter()
                    .map(|square| square.to_string())
                    .collect(),
            }),
            failure_code: if exactly_two {
                None
            } else {
                Some("structure.component_count_not_two")
            },
            predicates: Predicates {
                frozen_barrier: PredicateState::Pass,
                non_capturable_barrier: PredicateState::Pass,
                strict_exactly_two_components: if exactly_two {
                    PredicateState::Pass
                } else {
                    PredicateState::Fail
                },
                no_cross_component_entry: PredicateState::Pass,
            },
            internal_error: false,
        }
    }

    fn from_failure(board_id: String, error: &ConservativeLegalIndependenceError) -> Self {
        let mut row = Self::base(board_id);
        row.outcome = Outcome::Fail;
        row.failure_code = Some(failure_code(error));
        row.predicates = predicate_results(error);
        row
    }
}

fn decomposition_validation_code(error: &DecompositionCertificateValidationError) -> &'static str {
    use DecompositionCertificateValidationError as Error;
    match error {
        Error::StrictStatusMismatch { .. } => "strict_status_mismatch",
        Error::ComponentIntersectsBarrier { .. } => "component_intersects_barrier",
        Error::ActiveMaskOutsideComponent { .. } => "active_mask_outside_component",
        Error::ActiveComponentCountMismatch { .. } => "active_component_count_mismatch",
        Error::StrictWithTooFewActiveComponents { .. } => "strict_with_too_few_active_components",
        Error::StrictWithoutBarrier => "strict_without_barrier",
        Error::StrictWithRejectionReason { .. } => "strict_with_rejection_reason",
        Error::RejectedWithoutRejectionReason => "rejected_without_rejection_reason",
        Error::NoLockedBarrierRejectionWithBarrier => "no_locked_barrier_rejection_with_barrier",
        Error::NoLockedBarrierRejectionWithMultipleActiveComponents { .. } => {
            "no_locked_barrier_rejection_with_multiple_active_components"
        }
        Error::LessThanTwoActiveComponentsRejectionWithoutBarrier => {
            "less_than_two_active_components_rejection_without_barrier"
        }
        Error::LessThanTwoActiveComponentsRejectionWithTooManyActiveComponents { .. } => {
            "less_than_two_active_components_rejection_with_too_many_active_components"
        }
        Error::EmptyComponentMask { .. } => "empty_component_mask",
        Error::ComponentWithoutActiveSquares { .. } => "component_without_active_squares",
        Error::ComponentRootOutsideMask { .. } => "component_root_outside_mask",
        Error::ComponentMasksOverlap { .. } => "component_masks_overlap",
        Error::DuplicateComponentRoot { .. } => "duplicate_component_root",
        Error::CrossComponentAdjacency { .. } => "cross_component_adjacency",
        Error::StrictComponentMaskNotClosed { .. } => "strict_component_mask_not_closed",
    }
}

fn failure_code(error: &ConservativeLegalIndependenceError) -> &'static str {
    use ConservativeLegalIndependenceError as Error;
    match error {
        Error::InvalidDecompositionCertificate { error } => {
            match decomposition_validation_code(error) {
                "strict_status_mismatch" => "bitmesh.invalid_certificate.strict_status_mismatch",
                "component_intersects_barrier" => {
                    "bitmesh.invalid_certificate.component_intersects_barrier"
                }
                "active_mask_outside_component" => {
                    "bitmesh.invalid_certificate.active_mask_outside_component"
                }
                "active_component_count_mismatch" => {
                    "bitmesh.invalid_certificate.active_component_count_mismatch"
                }
                "strict_with_too_few_active_components" => {
                    "bitmesh.invalid_certificate.strict_with_too_few_active_components"
                }
                "strict_without_barrier" => "bitmesh.invalid_certificate.strict_without_barrier",
                "strict_with_rejection_reason" => {
                    "bitmesh.invalid_certificate.strict_with_rejection_reason"
                }
                "rejected_without_rejection_reason" => {
                    "bitmesh.invalid_certificate.rejected_without_rejection_reason"
                }
                "no_locked_barrier_rejection_with_barrier" => {
                    "bitmesh.invalid_certificate.no_locked_barrier_rejection_with_barrier"
                }
                "no_locked_barrier_rejection_with_multiple_active_components" => {
                    "bitmesh.invalid_certificate.no_locked_barrier_rejection_with_multiple_active_components"
                }
                "less_than_two_active_components_rejection_without_barrier" => {
                    "bitmesh.invalid_certificate.less_than_two_active_components_rejection_without_barrier"
                }
                "less_than_two_active_components_rejection_with_too_many_active_components" => {
                    "bitmesh.invalid_certificate.less_than_two_active_components_rejection_with_too_many_active_components"
                }
                "empty_component_mask" => "bitmesh.invalid_certificate.empty_component_mask",
                "component_without_active_squares" => {
                    "bitmesh.invalid_certificate.component_without_active_squares"
                }
                "component_root_outside_mask" => {
                    "bitmesh.invalid_certificate.component_root_outside_mask"
                }
                "component_masks_overlap" => "bitmesh.invalid_certificate.component_masks_overlap",
                "duplicate_component_root" => {
                    "bitmesh.invalid_certificate.duplicate_component_root"
                }
                "cross_component_adjacency" => {
                    "bitmesh.invalid_certificate.cross_component_adjacency"
                }
                "strict_component_mask_not_closed" => {
                    "bitmesh.invalid_certificate.strict_component_mask_not_closed"
                }
                _ => unreachable!("every pinned validation code is mapped"),
            }
        }
        Error::RequiresStrictDecomposition { .. } => "bitmesh.requires_strict_decomposition",
        Error::BarrierSquareIsEmpty { .. } => "bitmesh.barrier_square_is_empty",
        Error::BarrierSquareIsNotPawn { .. } => "bitmesh.barrier_square_is_not_pawn",
        Error::BarrierPawnNotFrozen { .. } => "bitmesh.barrier_pawn_not_frozen",
        Error::BarrierPawnCanCapture { .. } => "bitmesh.barrier_pawn_can_capture",
        Error::ActivePieceOutsideCertifiedComponent { .. } => {
            "bitmesh.active_piece_outside_certified_component"
        }
        Error::BarrierPieceCanBeCaptured { .. } => "bitmesh.barrier_piece_can_be_captured",
        Error::PieceCanEnterOtherComponent { .. } => "bitmesh.piece_can_enter_other_component",
        Error::PieceCanEnterUncertifiedFreeSquare { .. } => {
            "bitmesh.piece_can_enter_uncertified_free_square"
        }
    }
}

fn predicate_results(error: &ConservativeLegalIndependenceError) -> Predicates {
    use ConservativeLegalIndependenceError as Error;
    use PredicateState::{Fail, NotEvaluated, Pass};

    match error {
        Error::InvalidDecompositionCertificate { .. }
        | Error::RequiresStrictDecomposition { .. } => Predicates {
            frozen_barrier: NotEvaluated,
            non_capturable_barrier: NotEvaluated,
            strict_exactly_two_components: Fail,
            no_cross_component_entry: NotEvaluated,
        },
        Error::BarrierSquareIsEmpty { .. }
        | Error::BarrierSquareIsNotPawn { .. }
        | Error::BarrierPawnNotFrozen { .. } => Predicates {
            frozen_barrier: Fail,
            non_capturable_barrier: NotEvaluated,
            // The failure proves that Bitmesh reached a strict certificate,
            // which means at least two components, but the error does not
            // carry the component count needed to claim exactly two.
            strict_exactly_two_components: NotEvaluated,
            no_cross_component_entry: NotEvaluated,
        },
        Error::BarrierPawnCanCapture { .. } => Predicates {
            // Bitmesh interleaves per-pawn frozen and capture checks. A first
            // capture failure can precede later frozen checks.
            frozen_barrier: NotEvaluated,
            non_capturable_barrier: Fail,
            strict_exactly_two_components: NotEvaluated,
            no_cross_component_entry: NotEvaluated,
        },
        Error::BarrierPieceCanBeCaptured { .. } => Predicates {
            frozen_barrier: Pass,
            non_capturable_barrier: Fail,
            strict_exactly_two_components: NotEvaluated,
            no_cross_component_entry: NotEvaluated,
        },
        Error::ActivePieceOutsideCertifiedComponent { .. }
        | Error::PieceCanEnterOtherComponent { .. }
        | Error::PieceCanEnterUncertifiedFreeSquare { .. } => Predicates {
            frozen_barrier: Pass,
            // Active-piece destinations are visited in board order; an early
            // confinement failure can precede a later barrier-capture check.
            non_capturable_barrier: NotEvaluated,
            strict_exactly_two_components: NotEvaluated,
            no_cross_component_entry: Fail,
        },
    }
}

fn valid_board_id(value: &str) -> bool {
    value.strip_prefix("board-sha256:").is_some_and(|digest| {
        digest.len() == 64
            && digest
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    })
}

fn check(request: Request) -> ResultRow {
    let board = match Board::from_str(&request.board_fen) {
        Ok(board) => board,
        Err(_) => return ResultRow::invalid_board(request.board_id),
    };

    match panic::catch_unwind(AssertUnwindSafe(|| {
        certify_conservative_legal_independence(&board)
    })) {
        Ok(Ok(proof)) => ResultRow::from_proof(request.board_id, proof),
        Ok(Err(error)) => ResultRow::from_failure(request.board_id, &error),
        Err(_) => ResultRow::internal_error(request.board_id),
    }
}

fn run() -> Result<(), String> {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut output = stdout.lock();

    for (index, line) in stdin.lock().lines().enumerate() {
        let line_number = index + 1;
        let line =
            line.map_err(|error| format!("line {line_number}: input read failed: {error}"))?;
        if line.is_empty() {
            return Err(format!(
                "line {line_number}: blank JSONL rows are forbidden"
            ));
        }
        let request: Request = serde_json::from_str(&line)
            .map_err(|error| format!("line {line_number}: invalid strict request: {error}"))?;
        if request.schema_version != REQUEST_SCHEMA {
            return Err(format!(
                "line {line_number}: unsupported request schema version"
            ));
        }
        if !valid_board_id(&request.board_id) {
            return Err(format!("line {line_number}: invalid typed board id"));
        }
        serde_json::to_writer(&mut output, &check(request))
            .map_err(|error| format!("line {line_number}: output serialization failed: {error}"))?;
        output
            .write_all(b"\n")
            .map_err(|error| format!("line {line_number}: output write failed: {error}"))?;
    }
    output
        .flush()
        .map_err(|error| format!("output flush failed: {error}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("partizan-gate-s-checker: {error}");
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepted_board_reports_four_passes() {
        let request = Request {
            schema_version: REQUEST_SCHEMA.to_owned(),
            board_id: format!("board-sha256:{}", "0".repeat(64)),
            board_fen: "3p3n/3P4/3p4/3P4/3p4/3P4/3p4/N2P4".to_owned(),
        };
        let row = check(request);
        assert_eq!(row.outcome, Outcome::Pass);
        assert_eq!(row.predicates.frozen_barrier, PredicateState::Pass);
        assert_eq!(row.predicates.non_capturable_barrier, PredicateState::Pass);
        assert_eq!(
            row.predicates.strict_exactly_two_components,
            PredicateState::Pass
        );
        assert_eq!(
            row.predicates.no_cross_component_entry,
            PredicateState::Pass
        );
        assert_eq!(row.certification.unwrap().component_count, 2);
    }

    #[test]
    fn kingless_board_field_is_accepted_by_parser() {
        assert!(Board::from_str("3p3n/3P4/3p4/3P4/3p4/3P4/3p4/N2P4").is_ok());
    }

    #[test]
    fn full_fen_is_rejected_by_board_only_parser() {
        let row = check(Request {
            schema_version: REQUEST_SCHEMA.to_owned(),
            board_id: format!("board-sha256:{}", "1".repeat(64)),
            board_fen: "8/8/8/8/8/8/8/8 w - - 0 1".to_owned(),
        });
        assert_eq!(row.failure_code, Some("input.invalid_board_fen"));
        assert_eq!(
            row.predicates.strict_exactly_two_components,
            PredicateState::NotEvaluated
        );
    }

    #[test]
    fn non_strict_board_stops_after_strict_predicate() {
        let row = check(Request {
            schema_version: REQUEST_SCHEMA.to_owned(),
            board_id: format!("board-sha256:{}", "2".repeat(64)),
            board_fen: "8/8/8/8/8/8/8/N6n".to_owned(),
        });
        assert_eq!(
            row.failure_code,
            Some("bitmesh.requires_strict_decomposition")
        );
        assert_eq!(
            row.predicates.strict_exactly_two_components,
            PredicateState::Fail
        );
        assert_eq!(row.predicates.frozen_barrier, PredicateState::NotEvaluated);
    }

    #[test]
    fn request_denies_unknown_fields() {
        let result = serde_json::from_str::<Request>(
            r#"{"schema_version":"partizan.wave69r_structural_supply_request.v0.1","board_id":"board-sha256:0000000000000000000000000000000000000000000000000000000000000000","board_fen":"8/8/8/8/8/8/8/8","target_id":"forbidden"}"#,
        );
        assert!(result.is_err());
    }

    #[test]
    fn board_id_validation_is_lowercase_and_fixed_width() {
        assert!(valid_board_id(&format!("board-sha256:{}", "a0".repeat(32))));
        assert!(!valid_board_id(&format!(
            "board-sha256:{}",
            "A0".repeat(32)
        )));
        assert!(!valid_board_id(&format!("board-sha256:{}", "0".repeat(63))));
    }

    #[test]
    fn every_top_level_bitmesh_error_has_a_stable_code() {
        let errors = [
            ConservativeLegalIndependenceError::RequiresStrictDecomposition {
                status: DecompositionStatus::Rejected,
            },
            ConservativeLegalIndependenceError::BarrierSquareIsEmpty {
                square: shakmaty::Square::D1,
            },
            ConservativeLegalIndependenceError::BarrierSquareIsNotPawn {
                square: shakmaty::Square::D1,
                role: shakmaty::Role::Knight,
            },
            ConservativeLegalIndependenceError::BarrierPawnNotFrozen {
                square: shakmaty::Square::D1,
                forward_square: Some(shakmaty::Square::D2),
            },
            ConservativeLegalIndependenceError::BarrierPawnCanCapture {
                square: shakmaty::Square::D2,
                target: shakmaty::Square::C1,
            },
            ConservativeLegalIndependenceError::ActivePieceOutsideCertifiedComponent {
                square: shakmaty::Square::A1,
            },
            ConservativeLegalIndependenceError::BarrierPieceCanBeCaptured {
                attacker_square: shakmaty::Square::C3,
                barrier_square: shakmaty::Square::D1,
            },
            ConservativeLegalIndependenceError::PieceCanEnterOtherComponent {
                from: shakmaty::Square::C1,
                to: shakmaty::Square::E1,
                from_component: 0,
                to_component: 1,
            },
            ConservativeLegalIndependenceError::PieceCanEnterUncertifiedFreeSquare {
                from: shakmaty::Square::A1,
                to: shakmaty::Square::A2,
                from_component: 0,
            },
        ];
        for error in errors {
            assert!(failure_code(&error).starts_with("bitmesh."));
        }
    }

    #[test]
    fn every_pinned_certificate_validation_error_has_a_distinct_code() {
        use bitmesh::{
            DecompositionCertificateValidationError as ValidationError,
            DecompositionRejectionReason,
        };
        let validation_errors = [
            ValidationError::StrictStatusMismatch {
                strict: true,
                status: DecompositionStatus::Rejected,
            },
            ValidationError::ComponentIntersectsBarrier { component_index: 0 },
            ValidationError::ActiveMaskOutsideComponent { component_index: 0 },
            ValidationError::ActiveComponentCountMismatch {
                declared: 1,
                actual: 2,
            },
            ValidationError::StrictWithTooFewActiveComponents {
                active_component_count: 1,
            },
            ValidationError::StrictWithoutBarrier,
            ValidationError::StrictWithRejectionReason {
                rejection_reason: DecompositionRejectionReason::NoLockedBarrier,
            },
            ValidationError::RejectedWithoutRejectionReason,
            ValidationError::NoLockedBarrierRejectionWithBarrier,
            ValidationError::NoLockedBarrierRejectionWithMultipleActiveComponents {
                active_component_count: 2,
            },
            ValidationError::LessThanTwoActiveComponentsRejectionWithoutBarrier,
            ValidationError::LessThanTwoActiveComponentsRejectionWithTooManyActiveComponents {
                active_component_count: 2,
            },
            ValidationError::EmptyComponentMask { component_index: 0 },
            ValidationError::ComponentWithoutActiveSquares { component_index: 0 },
            ValidationError::ComponentRootOutsideMask {
                component_index: 0,
                root: 0,
            },
            ValidationError::ComponentMasksOverlap {
                first_component_index: 0,
                second_component_index: 1,
            },
            ValidationError::DuplicateComponentRoot {
                first_component_index: 0,
                second_component_index: 1,
                root: 0,
            },
            ValidationError::CrossComponentAdjacency {
                first_component_index: 0,
                second_component_index: 1,
                first_square: shakmaty::Square::A1,
                second_square: shakmaty::Square::B1,
            },
            ValidationError::StrictComponentMaskNotClosed {
                component_index: 0,
                square: shakmaty::Square::A1,
                omitted_square: shakmaty::Square::A2,
            },
        ];
        let mut codes = std::collections::BTreeSet::new();
        for error in validation_errors {
            let wrapped =
                ConservativeLegalIndependenceError::InvalidDecompositionCertificate { error };
            let code = failure_code(&wrapped);
            assert!(code.starts_with("bitmesh.invalid_certificate."));
            assert!(codes.insert(code), "duplicate failure code: {code}");
        }
        assert_eq!(codes.len(), 19);
    }
}
