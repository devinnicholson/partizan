"use client";

import {
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import elkiesJson from "../public/evidence/elkies-study.json";
import motifJson from "../public/evidence/fixed-value-motif.json";
import repertoireJson from "../public/evidence/repertoire-browser.json";

type Phase = 0 | 1 | 2 | 3;

type WitnessFrame = {
  capture: boolean;
  checkmate: boolean;
  fen: string;
  in_check: boolean;
  legal_move_count: number;
  move_display: string | null;
  move_san: string | null;
  move_uci: string | null;
  ply: number;
  promotion: boolean;
  stalemate: boolean;
  turn: "white" | "black";
};

type HistoricalEvidence = {
  schema_version: string;
  evidence_sha256: string;
  title: string;
  claim: string;
  source: {
    author: string;
    title: string;
    venue: string;
    year: number;
    pages: string;
    figure: string;
    url: string;
    historical_attribution: string;
  };
  scope: {
    legal_replay: string;
    line_origin: string;
    line_optimality: string;
    forcedness: string;
    cgt_value: string;
  };
  position: {
    name: string;
    initial_piece_count: number;
    final_piece_count: number;
  };
  witness: {
    native_witness_version: string;
    move_count: number;
    frames: WitnessFrame[];
  };
  motifs: {
    at_ply: number;
    name: string;
    move_san: string;
  }[];
};

type GraphPosition = {
  label: "A" | "B" | "C";
  name: string;
  candidate_sha256: string;
  quotient_sha256: string;
  literal_game_sha256: string;
  blue_vertices: number[];
  arcs: [number, number][];
  graph_arc_count: number;
  literal_game_nodes: number;
  literal_game_edges: number;
  birthday: number;
  first_global_event_index: number;
};

type MotifTransition = {
  from: "A" | "B";
  to: "B" | "C";
  operation: string;
  arc: [number, number];
  class: "literal_game_crossing" | "embodiment_only";
  headline: string;
  detail: string;
  event_sha256: string;
};

type FixedValueMotif = {
  schema_version: string;
  claim: string;
  completion_sha256: string;
  run: {
    proposal_count: number;
    linked_motif_count: number;
    independent_replay: boolean;
    negative_test_families_rejected: number;
  };
  comparison: {
    exact_value: string;
    relation: string;
    statement: string;
    literal_statement: string;
    quotient_statement: string;
  };
  positions: GraphPosition[];
  transitions: MotifTransition[];
  atlas: {
    quotient_unique_representatives: number;
    targets: {
      label: string;
      quotients: number;
      literal_games: number;
    }[];
  };
  scope: {
    domain: string;
    claim_kind: string;
    fiber_size: string;
    aesthetic_ranking: string;
    unrestricted_chess: string;
  };
};

type TargetLabel = "0" | "*" | "1/2";

type PolicyResult = {
  policy_id: string;
  policy_label: string;
  policy_family: "classical_search" | "learned_ranker";
  target: TargetLabel;
  formal_target: string;
  budget: {
    unit: "raw_proposal" | "exact_verifier_call";
    count: number;
  };
  status: "verified" | "awaiting_certified_result" | "failed_integrity_gate";
  completion_sha256: string;
  independent_replay: boolean;
  quotient_unique_representatives: number;
  literal_game_digests: number;
  representative_view: "linked_motif" | "aggregate_only";
  representative_labels: ("A" | "B" | "C")[];
};

type RepresentativeProvenance = {
  label: "A" | "B" | "C";
  global_event_index: number;
  event_sha256: string;
  candidate_sha256: string;
  equality_certificate_sha256: string;
  equality_sidecar_sha256: string;
  derivation_sidecar_sha256: string;
  artifact_sidecar_sha256: string;
};

type RepertoireBrowserEvidence = {
  schema_version: string;
  study: {
    domain: string;
    status: "GO";
    evidence_eligible: boolean;
    policy: {
      policy_id: string;
      label: string;
      family: "classical_search";
      status: "verified";
      streams_per_target: number;
      proposals_per_stream: number;
    };
    result_contract: {
      schema_version: string;
      required_fields: string[];
      allowed_statuses: string[];
    };
  };
  projection: {
    symbol: "q(x)" | "ℓ(x)" | "v(x)";
    label: string;
    definition: string;
  }[];
  results: PolicyResult[];
  representative_provenance: RepresentativeProvenance[];
  bindings: {
    completion_sha256: string;
    run_complete_file_sha256: string;
    manifest_file_sha256: string;
    events_file_sha256: string;
    summary_file_sha256: string;
    independent_verification_file_sha256: string;
    negative_tests_file_sha256: string;
  };
  claim_boundary: {
    fiber_size: "not_estimated";
    aesthetic_ranking: "not_measured";
    human_preference: "not_measured";
    policy_optimality: "not_tested";
  };
};

type Piece = {
  id: string;
  color: "white" | "black";
  kind: string;
  square: string;
};

const elkies = elkiesJson as HistoricalEvidence;
const motif = motifJson as FixedValueMotif;
const repertoire = repertoireJson as RepertoireBrowserEvidence;
const files = "abcdefgh";
const phaseLabels = ["Receive", "Cross literal game", "Change embodiment", "Certify"] as const;
const witnessLandmarks = [0, 3, 7, 10, 12, 13] as const;
const graphCoordinates = [
  { x: 50, y: 8 },
  { x: 82, y: 25 },
  { x: 88, y: 58 },
  { x: 65, y: 88 },
  { x: 35, y: 88 },
  { x: 12, y: 58 },
  { x: 18, y: 25 },
] as const;

const glyphs: Record<string, string> = {
  K: "♔",
  Q: "♕",
  R: "♖",
  B: "♗",
  N: "♘",
  P: "♙",
  k: "♚",
  q: "♛",
  r: "♜",
  b: "♝",
  n: "♞",
  p: "♟",
};

function parseFen(fen: string): Piece[] {
  const board = fen.split(" ")[0];
  const counts: Record<string, number> = {};
  const pieces: Piece[] = [];

  board.split("/").forEach((rankText, row) => {
    let file = 0;
    for (const symbol of rankText) {
      if (/\d/.test(symbol)) {
        file += Number(symbol);
        continue;
      }
      counts[symbol] = (counts[symbol] ?? 0) + 1;
      pieces.push({
        id: `${symbol}-${counts[symbol]}`,
        color: symbol === symbol.toUpperCase() ? "white" : "black",
        kind: symbol,
        square: `${files[file]}${8 - row}`,
      });
      file += 1;
    }
  });

  return pieces;
}

function uciSquares(move: string | null): { from: string; to: string } | null {
  if (!move || !/^[a-h][1-8][a-h][1-8][qrbn]?$/.test(move)) return null;
  return { from: move.slice(0, 2), to: move.slice(2, 4) };
}

function squarePosition(square: string) {
  return { file: files.indexOf(square[0]), row: 8 - Number(square[1]) };
}

function shortHash(value: string) {
  const digest = value.includes(":") ? value.split(":").at(-1) : value;
  return digest?.slice(0, 10);
}

function GraphEdge({
  from,
  to,
  emphasis,
}: {
  from: number;
  to: number;
  emphasis?: "removed" | "added";
}) {
  const start = graphCoordinates[from];
  const end = graphCoordinates[to];
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const distance = Math.hypot(dx, dy);
  const angle = Math.atan2(dy, dx) * (180 / Math.PI);
  const reverseExists = motif.positions.some((position) =>
    position.arcs.some(([candidateFrom, candidateTo]) =>
      candidateFrom === to && candidateTo === from,
    ),
  );
  const offset = reverseExists ? (from < to ? -1.5 : 1.5) : 0;

  return (
    <span
      className={[
        "graph-edge",
        emphasis ? `graph-edge-${emphasis}` : "",
      ].join(" ")}
      style={{
        "--edge-x": `${start.x}%`,
        "--edge-y": `${start.y}%`,
        "--edge-length": `${distance}%`,
        "--edge-angle": `${angle}deg`,
        "--edge-offset": `${offset}px`,
      } as CSSProperties}
      aria-hidden="true"
    />
  );
}

function DigraphBoard({
  position,
  phase,
}: {
  position: GraphPosition;
  phase: Phase;
}) {
  const positionIndex = motif.positions.findIndex(
    (candidate) => candidate.label === position.label,
  );
  const revealed = phase >= positionIndex || phase === 3;

  return (
    <div
      className={[
        "digraph-board",
        revealed ? "revealed" : "veiled",
        `digraph-${position.label.toLowerCase()}`,
      ].join(" ")}
      aria-label={`${position.name}: seven-vertex Digraph Placement graph with exact value zero`}
    >
      <div className="graph-orbit" aria-hidden="true" />
      {position.arcs.map(([from, to]) => {
        const removed =
          position.label === "A" && from === 2 && to === 3 && phase >= 1;
        const added =
          position.label === "C" && from === 6 && to === 0 && phase >= 2;
        return (
          <GraphEdge
            from={from}
            to={to}
            emphasis={removed ? "removed" : added ? "added" : undefined}
            key={`${from}-${to}`}
          />
        );
      })}
      {graphCoordinates.map((coordinate, vertex) => {
        const leftVertex = position.blue_vertices.includes(vertex);
        return (
          <span
            className={`graph-node ${leftVertex ? "left-vertex" : "right-vertex"}`}
            key={vertex}
            style={{
              "--node-x": `${coordinate.x}%`,
              "--node-y": `${coordinate.y}%`,
            } as CSSProperties}
            aria-hidden="true"
          >
            {vertex}
          </span>
        );
      })}
      <div className="graph-value-mark" aria-live="polite">
        <span>{phase === 3 ? "exact value" : "target"}</span>
        <strong>{phase === 3 ? "0" : "?"}</strong>
      </div>
    </div>
  );
}

function MotifCard({
  position,
  phase,
  index,
}: {
  position: GraphPosition;
  phase: Phase;
  index: number;
}) {
  const status =
    phase === 3
      ? "value 0 certified"
      : phase >= index
        ? index === 0
          ? "held-out position"
          : index === 1
            ? "literal crossing"
            : "embodiment change"
        : "awaiting edit";
  const provenance = repertoire.representative_provenance.find(
    (record) => record.label === position.label,
  );

  return (
    <article className={`motif-card motif-card-${position.label.toLowerCase()}`}>
      <header className="card-heading">
        <div>
          <span className="roman">{position.label}</span>
          <p>{position.name}</p>
        </div>
        <div className="status-readout" aria-live="polite">
          <span className="status-light" />
          {status}
        </div>
      </header>

      <DigraphBoard position={position} phase={phase} />

      <div className="motif-invariants">
        <span>graph quotient</span>
        <strong>{shortHash(position.quotient_sha256)}</strong>
        <span>literal game</span>
        <strong>{shortHash(position.literal_game_sha256)}</strong>
      </div>

      <dl className="measurements motif-measurements">
        <div>
          <dt>directed arcs</dt>
          <dd>{position.graph_arc_count}</dd>
        </div>
        <div>
          <dt>literal nodes</dt>
          <dd>{position.literal_game_nodes}</dd>
        </div>
        <div>
          <dt>literal edges</dt>
          <dd>{position.literal_game_edges}</dd>
        </div>
      </dl>

      <details className="certificate">
        <summary>Admission record</summary>
        <dl className="admission-record">
          <div>
            <dt>Candidate</dt>
            <dd>
              <code
                title={position.candidate_sha256}
                aria-label={position.candidate_sha256}
              >
                {shortHash(position.candidate_sha256)}
              </code>
            </dd>
          </div>
          <div>
            <dt>Held-out event</dt>
            <dd>{position.first_global_event_index}</dd>
          </div>
          <div>
            <dt>Birthday</dt>
            <dd>{position.birthday}</dd>
          </div>
          {provenance && (
            <>
              <div>
                <dt>Event digest</dt>
                <dd>
                  <code
                    title={provenance.event_sha256}
                    aria-label={provenance.event_sha256}
                  >
                    {shortHash(provenance.event_sha256)}
                  </code>
                </dd>
              </div>
              <div>
                <dt>Equality certificate</dt>
                <dd>
                  <code
                    title={provenance.equality_certificate_sha256}
                    aria-label={provenance.equality_certificate_sha256}
                  >
                    {shortHash(provenance.equality_certificate_sha256)}
                  </code>
                </dd>
              </div>
              <div>
                <dt>Equality sidecar</dt>
                <dd>
                  <code
                    title={provenance.equality_sidecar_sha256}
                    aria-label={provenance.equality_sidecar_sha256}
                  >
                    {shortHash(provenance.equality_sidecar_sha256)}
                  </code>
                </dd>
              </div>
              <div>
                <dt>Derivation sidecar</dt>
                <dd>
                  <code
                    title={provenance.derivation_sidecar_sha256}
                    aria-label={provenance.derivation_sidecar_sha256}
                  >
                    {shortHash(provenance.derivation_sidecar_sha256)}
                  </code>
                </dd>
              </div>
              <div>
                <dt>Artifact sidecar</dt>
                <dd>
                  <code
                    title={provenance.artifact_sidecar_sha256}
                    aria-label={provenance.artifact_sidecar_sha256}
                  >
                    {shortHash(provenance.artifact_sidecar_sha256)}
                  </code>
                </dd>
              </div>
            </>
          )}
        </dl>
      </details>
    </article>
  );
}

function RepertoireBrowser() {
  const [selectedTarget, setSelectedTarget] = useState<TargetLabel>("0");
  const result =
    repertoire.results.find((item) => item.target === selectedTarget) ??
    repertoire.results[0];
  const hasLinkedMotif = result.representative_view === "linked_motif";
  const bindingRows = [
    ["run completion", repertoire.bindings.run_complete_file_sha256],
    ["study manifest", repertoire.bindings.manifest_file_sha256],
    ["event ledger", repertoire.bindings.events_file_sha256],
    ["study summary", repertoire.bindings.summary_file_sha256],
    [
      "independent replay",
      repertoire.bindings.independent_verification_file_sha256,
    ],
    ["negative tests", repertoire.bindings.negative_tests_file_sha256],
  ] as const;

  return (
    <section
      className="repertoire-browser"
      aria-labelledby="repertoire-browser-title"
    >
      <header className="repertoire-heading">
        <div>
          <span>Certified repertoire browser</span>
          <p>{repertoire.study.domain}</p>
        </div>
        <h2 id="repertoire-browser-title">
          Choose the value.
          <em> Keep the proof in view.</em>
        </h2>
        <p>
          Each target opens a result from the same frozen study. Counts describe
          observed sampled trajectories. Representative comparison appears only
          where the checked browser evidence contains the underlying records.
        </p>
      </header>

      <div
        className="target-selector"
        role="tablist"
        aria-label="Select an exact target value"
      >
        {repertoire.results.map((item) => (
          <button
            type="button"
            role="tab"
            id={`target-tab-${item.target === "*" ? "star" : item.target === "1/2" ? "half" : "zero"}`}
            aria-controls="selected-repertoire-panel"
            aria-selected={item.target === selectedTarget}
            tabIndex={item.target === selectedTarget ? 0 : -1}
            className={item.target === selectedTarget ? "active" : ""}
            key={item.target}
            onClick={() => setSelectedTarget(item.target)}
            onKeyDown={(event) => {
              if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
                return;
              }
              event.preventDefault();
              const tabs = Array.from(
                event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>(
                  '[role="tab"]',
                ) ?? [],
              );
              const currentIndex = tabs.indexOf(event.currentTarget);
              const nextIndex =
                event.key === "Home"
                  ? 0
                  : event.key === "End"
                    ? tabs.length - 1
                    : (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) %
                      tabs.length;
              tabs[nextIndex]?.focus();
              tabs[nextIndex]?.click();
            }}
          >
            <span>target</span>
            <strong>{item.target}</strong>
            <small>{item.quotient_unique_representatives.toLocaleString("en-US")} q</small>
          </button>
        ))}
      </div>

      <div className="repertoire-dashboard">
        <article
          className="selected-repertoire"
          role="tabpanel"
          id="selected-repertoire-panel"
          aria-labelledby={`target-tab-${result.target === "*" ? "star" : result.target === "1/2" ? "half" : "zero"}`}
          tabIndex={0}
        >
          <div className="result-status">
            <span className="verified-dot" />
            independently replayed
          </div>
          <span className="result-kicker">exact target</span>
          <h3>{result.target}</h3>
          <p className="formal-target">
            formal game <code>{result.formal_target}</code>
          </p>
          <dl>
            <div>
              <dt>q(x)</dt>
              <dd>{result.quotient_unique_representatives.toLocaleString("en-US")}</dd>
              <span>quotient-unique representatives</span>
            </div>
            <div>
              <dt>ℓ(x)</dt>
              <dd>{result.literal_game_digests.toLocaleString("en-US")}</dd>
              <span>complete literal-game digests</span>
            </div>
            <div>
              <dt>{result.budget.unit.replaceAll("_", " ")}</dt>
              <dd>{result.budget.count.toLocaleString("en-US")}</dd>
              <span>twelve fixed streams</span>
            </div>
          </dl>
          {hasLinkedMotif ? (
            <a className="repertoire-action" href="#motif-replay">
              Replay A → B → C
              <span aria-hidden="true">↓</span>
            </a>
          ) : (
            <p className="aggregate-boundary">
              Aggregate evidence is loaded for this target. Representative
              panel status: awaiting checked records.
            </p>
          )}
        </article>

        <div className="projection-ledger" aria-label="Representation projections">
          <span className="result-kicker">What each digest fixes</span>
          {repertoire.projection.map((projection, index) => (
            <div className="projection-row" key={projection.symbol}>
              <strong>{projection.symbol}</strong>
              <div>
                <h3>{projection.label}</h3>
                <p>{projection.definition}</p>
              </div>
              {index < repertoire.projection.length - 1 && (
                <span className="projection-arrow" aria-hidden="true">↓</span>
              )}
            </div>
          ))}
        </div>

        <aside className="policy-record" aria-label="Search policy record">
          <span className="result-kicker">Proposal policy</span>
          <h3>{repertoire.study.policy.label}</h3>
          <p>
            One frozen classical search policy generated every result currently
            shown in this browser.
          </p>
          <dl>
            <div>
              <dt>policy id</dt>
              <dd>{repertoire.study.policy.policy_id}</dd>
            </div>
            <div>
              <dt>family</dt>
              <dd>{repertoire.study.policy.family.replace("_", " ")}</dd>
            </div>
            <div>
              <dt>result status</dt>
              <dd>{result.status}</dd>
            </div>
          </dl>
          <div className="policy-result-slot">
            <span>{repertoire.study.result_contract.schema_version}</span>
            <strong>Comparable policy-result slot</strong>
            <p>Learned-policy result: awaiting certification.</p>
          </div>
        </aside>
      </div>

      <details className="study-provenance">
        <summary>
          <span>Study provenance</span>
          completion {shortHash(repertoire.bindings.completion_sha256)}
        </summary>
        <div className="provenance-chain">
          {bindingRows.map(([label, digest]) => (
            <div key={label}>
              <span>{label}</span>
              <code title={digest}>{digest}</code>
            </div>
          ))}
        </div>
        <p>
          Current evidence scope: observed sampled trajectories, exact-value
          certification, and independent replay. Fiber size, aesthetic ranking,
          human preference, and policy optimality remain unmeasured.
        </p>
      </details>
    </section>
  );
}

function WitnessBoard({ frame }: { frame: WitnessFrame }) {
  const pieces = useMemo(() => parseFen(frame.fen), [frame.fen]);
  const move = uciSquares(frame.move_uci);
  const from = move ? squarePosition(move.from) : null;
  const to = move ? squarePosition(move.to) : null;
  const vectorStyle =
    from && to
      ? ({
          "--vector-x": `${(from.file + 0.5) * 12.5}%`,
          "--vector-y": `${(from.row + 0.5) * 12.5}%`,
          "--vector-length": `${Math.hypot(
            (to.file - from.file) * 12.5,
            (to.row - from.row) * 12.5,
          )}%`,
          "--vector-angle": `${Math.atan2(
            (to.row - from.row) * 12.5,
            (to.file - from.file) * 12.5,
          ) * (180 / Math.PI)}deg`,
        } as CSSProperties)
      : undefined;

  return (
    <div
      className={`chessboard witness-board ${
        frame.in_check ? "witness-check" : ""
      }`}
      aria-label={`Elkies historical witness at ply ${frame.ply}: ${frame.fen}`}
    >
      <div className="squares" aria-hidden="true">
        {Array.from({ length: 64 }, (_, index) => {
          const row = Math.floor(index / 8);
          const file = index % 8;
          const square = `${files[file]}${8 - row}`;
          return (
            <div
              className={[
                "square",
                (row + file) % 2 === 0 ? "light" : "dark",
                move?.from === square ? "witness-from" : "",
                move?.to === square ? "witness-to" : "",
              ].join(" ")}
              key={square}
            >
              {file === 0 && <span className="rank-label">{8 - row}</span>}
              {row === 7 && <span className="file-label">{files[file]}</span>}
            </div>
          );
        })}
      </div>
      {vectorStyle && (
        <div className="witness-vector" style={vectorStyle} aria-hidden="true" />
      )}
      {pieces.map((piece) => {
        const position = squarePosition(piece.square);
        return (
          <span
            className={`piece ${piece.color}`}
            key={`${frame.ply}-${piece.id}-${piece.square}`}
            style={{
              "--file": position.file,
              "--row": position.row,
            } as CSSProperties}
            aria-hidden="true"
          >
            {glyphs[piece.kind]}
          </span>
        );
      })}
      <div className="board-vignette" aria-hidden="true" />
      <div className="witness-board-readout" aria-live="polite">
        <span>{frame.ply === 0 ? "opening form" : `ply ${frame.ply} / 13`}</span>
        <strong>{frame.move_san ?? "position"}</strong>
      </div>
      {frame.ply === 13 && (
        <div className="kernel-mark" aria-live="polite">
          kernel reached
        </div>
      )}
    </div>
  );
}

function historicalNote(ply: number) {
  if (ply === 0) {
    return {
      eyebrow: "The composed entrance",
      title: "The kernel is hidden.",
      body: "Eight pieces, two pawns on the edge of promotion, and no visible resemblance to the six-piece ending ahead.",
    };
  }
  const motif = elkies.motifs.find((item) => item.at_ply === ply);
  if (motif) {
    const notes: Record<number, { title: string; body: string }> = {
      3: {
        title: "The first queen arrives.",
        body: "White promotes without check. The board grows more complicated before it becomes spare.",
      },
      7: {
        title: "The bishop enters the line.",
        body: "Bc6 invites its own removal. The sacrifice clears the geometry that the final position requires.",
      },
      10: {
        title: "A second promotion answers.",
        body: "Black’s pawn becomes a queen with check. Material symmetry appears through opposite journeys.",
      },
      12: {
        title: "The smallest move turns the key.",
        body: "Kh1 carries no capture or promotion. It prepares the exact burden of the position to come.",
      },
      13: {
        title: "Qfg8. The kernel appears.",
        body: "Queens and kings remain. The published line has reached Stiller’s computer-found mutual-zugzwang form, rotated on the board.",
      },
    };
    return {
      eyebrow: motif.name,
      title: notes[ply].title,
      body: notes[ply].body,
    };
  }
  return {
    eyebrow: "Published continuation",
    title: elkies.witness.frames[ply].move_san ?? `Ply ${ply}`,
    body: "Each move is checked against the legal moves of the preceding position before the next frame is admitted.",
  };
}

function HistoricalPrelude() {
  const [ply, setPly] = useState(0);
  const [playing, setPlaying] = useState(false);
  const sectionRef = useRef<HTMLElement>(null);
  const frame = elkies.witness.frames[ply];
  const note = historicalNote(ply);

  const selectPly = useCallback((nextPly: number) => {
    setPlaying(false);
    setPly(Math.max(0, Math.min(elkies.witness.move_count, nextPly)));
  }, []);

  const togglePlayback = useCallback(() => {
    if (playing) {
      setPlaying(false);
      return;
    }
    if (ply === elkies.witness.move_count) setPly(0);
    setPlaying(true);
  }, [playing, ply]);

  useEffect(() => {
    if (!playing || ply >= elkies.witness.move_count) return;
    const timer = window.setTimeout(() => {
      const nextPly = Math.min(elkies.witness.move_count, ply + 1);
      setPly(nextPly);
      if (nextPly === elkies.witness.move_count) setPlaying(false);
    }, 1_050);
    return () => window.clearTimeout(timer);
  }, [playing, ply]);

  useEffect(() => {
    const node = sectionRef.current;
    if (!node) return;
    const handleKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("button, a")) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        selectPly(ply + 1);
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        selectPly(ply - 1);
      }
    };
    node.addEventListener("keydown", handleKey);
    return () => node.removeEventListener("keydown", handleKey);
  }, [ply, selectPly]);

  return (
    <section
      className="historical-prelude"
      aria-labelledby="prelude-title"
      ref={sectionRef}
      tabIndex={0}
    >
      <header className="prelude-heading">
        <div>
          <span>Historical prelude · 1996</span>
          <p>Stiller / Elkies</p>
        </div>
        <h2 id="prelude-title">
          A machine found the kernel.
          <em> Elkies composed the encounter.</em>
        </h2>
        <p>
          The six-piece mutual zugzwang came first. Noam Elkies placed it at the
          end of a thirteen-ply approach whose opening position seems to belong
          to another problem entirely.
        </p>
      </header>

      <div className="prelude-instrument">
        <div className="witness-stage">
          <div
            className="witness-stage-index"
            style={
              {
                "--witness-progress": (ply / elkies.witness.move_count) * 100,
              } as CSSProperties
            }
            aria-hidden="true"
          >
            <span>{String(ply).padStart(2, "0")}</span>
            <i />
            <span>13</span>
          </div>
          <WitnessBoard frame={frame} />
          <div className="witness-controls">
            <button
              type="button"
              onClick={() => selectPly(ply - 1)}
              disabled={ply === 0}
              aria-label="Previous move"
            >
              ←
            </button>
            <button
              className="witness-play"
              type="button"
              onClick={togglePlayback}
              aria-label={playing ? "Pause historical line" : "Play historical line"}
            >
              <span
                className={playing ? "pause-mark" : "play-mark"}
                aria-hidden="true"
              />
              {playing ? "Pause" : ply === 13 ? "Replay line" : "Play 13 plies"}
            </button>
            <button
              type="button"
              onClick={() => selectPly(ply + 1)}
              disabled={ply === elkies.witness.move_count}
              aria-label="Next move"
            >
              →
            </button>
          </div>
        </div>

        <div className="witness-reading">
          <div className="witness-note" key={`${ply}-${note.title}`}>
            <span>{note.eyebrow}</span>
            <h3>{note.title}</h3>
            <p>{note.body}</p>
          </div>

          <ol className="witness-score" aria-label="Published thirteen-ply line">
            {elkies.witness.frames.slice(1).map((item) => (
              <li key={item.ply}>
                <button
                  type="button"
                  className={[
                    item.ply === ply ? "current" : "",
                    item.ply < ply ? "passed" : "",
                    witnessLandmarks.includes(
                      item.ply as (typeof witnessLandmarks)[number],
                    )
                      ? "landmark"
                      : "",
                  ].join(" ")}
                  onClick={() => selectPly(item.ply)}
                  aria-current={item.ply === ply ? "step" : undefined}
                  title={`Ply ${item.ply}: ${item.move_san}`}
                >
                  <span>{String(item.ply).padStart(2, "0")}</span>
                  <strong>{item.move_san}</strong>
                </button>
              </li>
            ))}
          </ol>

          <div className="witness-boundary">
            <div>
              <span className="verified-dot" />
              legal replay machine-verified
            </div>
            <div>line from published analysis</div>
            <div>CGT value unasserted here</div>
          </div>

          <a
            className="primary-source"
            href={elkies.source.url}
            target="_blank"
            rel="noreferrer"
          >
            <span>Primary source</span>
            {elkies.source.title}, pp. {elkies.source.pages} ↗
          </a>
        </div>
      </div>

      <div className="prelude-thesis">
        <span>The transformation</span>
        <p>
          The final position is compact enough to name. The route gives that
          position tension, delay, sacrifice, and surprise.
        </p>
      </div>
    </section>
  );
}

export function PartizanExperience() {
  const [phase, setPhase] = useState<Phase>(0);
  const [playing, setPlaying] = useState(false);
  const [run, setRun] = useState(0);

  const begin = useCallback(() => {
    setPhase(0);
    setPlaying(true);
    setRun((current) => current + 1);
  }, []);

  useEffect(() => {
    if (!playing) return;
    const timers = [
      window.setTimeout(() => setPhase(1), 850),
      window.setTimeout(() => setPhase(2), 2_350),
      window.setTimeout(() => setPhase(3), 4_650),
      window.setTimeout(() => setPlaying(false), 7_100),
    ];
    return () => timers.forEach(window.clearTimeout);
  }, [playing, run]);

  const selectPhase = useCallback((next: Phase) => {
    setPlaying(false);
    setPhase(next);
  }, []);

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target?.closest(
          "button, a, summary, input, textarea, select, .historical-prelude",
        )
      )
        return;
      if (event.key === " ") {
        event.preventDefault();
        begin();
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        selectPhase(Math.min(3, phase + 1) as Phase);
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        selectPhase(Math.max(0, phase - 1) as Phase);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [begin, phase, selectPhase]);

  return (
    <main className={`experience phase-${phase}`}>
      <div className="ambient ambient-one" aria-hidden="true" />
      <div className="ambient ambient-two" aria-hidden="true" />
      <header className="masthead">
        <a className="wordmark" href="#top" aria-label="Partizan home">
          <span className="wordmark-glyph">P</span>
          <span>PARTIZAN</span>
        </a>
        <div className="live-certificate">
          <span />
          exact-value instrument
        </div>
      </header>

      <section className="hero" id="top">
        <div className="hero-kicker">
          <span>Partizan · search within correctness</span>
          <span>73,728 proposals · independently replayed</span>
        </div>
        <h1>
          <span>One value.</span>
          <em>Three forms.</em>
        </h1>
        <p className="hero-claim">{motif.claim}</p>
        <div className="hero-controls">
          <button className="begin-button" type="button" onClick={begin}>
            <span className={playing ? "pause-mark" : "play-mark"} aria-hidden="true" />
            {playing
              ? "Crossing the fiber"
              : phase === 3
                ? "Traverse again"
                : "Enter the fiber"}
          </button>
          <p>
            Space to replay
            <span aria-hidden="true"> · </span>
            arrows to examine
          </p>
        </div>
      </section>

      <HistoricalPrelude />

      <div className="crossing-intro">
        <div>
          <span>Partizan motif 01</span>
          <p>Order-7 Digraph Placement · exact value 0</p>
        </div>
        <h2>
          Correctness is the entrance.
          <em> The search continues inside.</em>
        </h2>
        <p>
          Two single-arc edits cross different layers of representation. The
          first changes the complete game. The second changes only its
          embodiment. Exact value remains zero throughout.
        </p>
      </div>

      <RepertoireBrowser />

      <nav className="phase-line" aria-label="Proof stages">
        {phaseLabels.map((label, index) => (
          <button
            type="button"
            className={phase >= index ? "active" : ""}
            key={label}
            onClick={() => selectPhase(index as Phase)}
            aria-current={phase === index ? "step" : undefined}
          >
            <span>0{index + 1}</span>
            {label}
          </button>
        ))}
        <div className="phase-progress" style={{ width: `${(phase / 3) * 100}%` }} />
      </nav>

      <section
        className="motif-crossing"
        id="motif-replay"
        aria-label="Certified fixed-value motif"
      >
        <div className="motif-route" aria-label="Two single-arc transitions">
          <span className="route-position">A</span>
          {motif.transitions.map((transition, index) => (
            <div
              className={[
                "route-transition",
                phase >= index + 1 ? "active" : "",
                `route-${transition.class.replaceAll("_", "-")}`,
              ].join(" ")}
              key={transition.event_sha256}
            >
              <i aria-hidden="true" />
              <strong>{transition.operation.replace("->", "→")}</strong>
              <span>{transition.headline}</span>
              <small
                title={transition.event_sha256}
                aria-label={`Event SHA-256 ${transition.event_sha256}`}
              >
                event {shortHash(transition.event_sha256)}
              </small>
            </div>
          ))}
          <span className="route-position route-position-b">B</span>
          <span className="route-position route-position-c">C</span>
        </div>

        <div className="motif-grid">
          {motif.positions.map((position, index) => (
            <MotifCard
              position={position}
              index={index}
              phase={phase}
              key={position.candidate_sha256}
            />
          ))}
        </div>
      </section>

      <section className="residual-field" aria-label="Two layers of residual structure">
        <div className={`residual-panel ${phase >= 1 ? "active" : ""}`}>
          <span>A → B · literal-game crossing</span>
          <h3>{motif.transitions[0].headline}</h3>
          <p>{motif.transitions[0].detail}</p>
          <div className="residual-equation">
            <strong>ℓ(A) ≠ ℓ(B)</strong>
            <small>19/18 → 15/14 nodes/edges</small>
          </div>
        </div>

        <div className="equality-axis motif-equality-axis">
          <span className="axis-rule" aria-hidden="true" />
          <p>Conway comparison</p>
          <div className="value-seal" aria-live="polite">
            <span>certified value</span>
            <strong>{phase === 3 ? "0 = 0 = 0" : "?"}</strong>
            <small>{motif.comparison.statement}</small>
          </div>
          <p>{phase === 3 ? "identical in value" : "comparison pending"}</p>
          <span className="axis-rule" aria-hidden="true" />
        </div>

        <div className={`residual-panel ${phase >= 2 ? "active" : ""}`}>
          <span>B → C · embodiment only</span>
          <h3>{motif.transitions[1].headline}</h3>
          <p>{motif.transitions[1].detail}</p>
          <div className="residual-equation">
            <strong>ℓ(B) = ℓ(C)</strong>
            <small>byte-identical complete game</small>
          </div>
        </div>
      </section>

      <section className="atlas-field" aria-labelledby="atlas-title">
        <div>
          <span>Frozen structural atlas</span>
          <h2 id="atlas-title">
            One motif inside
            <em> 21,697 certified forms.</em>
          </h2>
          <p>
            The held-out study found both transition classes for every target.
            These are observed unions from dependent sampled trajectories.
          </p>
        </div>
        <dl>
          {motif.atlas.targets.map((target) => (
            <div key={target.label}>
              <dt>value {target.label}</dt>
              <dd>{target.quotients.toLocaleString("en-US")}</dd>
              <span>
                graph quotients · {target.literal_games.toLocaleString("en-US")} literal games
              </span>
            </div>
          ))}
        </dl>
      </section>

      <section className="conclusion" aria-live="polite">
        <p>Mathematical identity</p>
        <h2>
          {phase === 3 ? (
            <>
              The value is settled.
              <br />
              <em>The encounter remains open.</em>
            </>
          ) : (
            <>
              Three forms wait
              <br />
              <em>inside one value.</em>
            </>
          )}
        </h2>
        <div className="conclusion-metrics">
          <span>
            <b>3</b> certified forms
          </span>
          <span>
            <b>2</b> single-arc edits
          </span>
          <span>
            <b>1</b> exact value
          </span>
        </div>
      </section>

      <footer className="provenance">
        <div>
          <span>Partizan</span>
          <p>Search within correctness.</p>
        </div>
        <dl>
          <div>
            <dt>Completion</dt>
            <dd>{motif.completion_sha256.slice(0, 12)}</dd>
          </div>
          <div>
            <dt>Replay</dt>
            <dd>{motif.run.proposal_count.toLocaleString("en-US")} events</dd>
          </div>
          <div>
            <dt>Relation</dt>
            <dd>fixed-value motif</dd>
          </div>
        </dl>
        <a
          href="https://github.com/devinnicholson/partizan"
          target="_blank"
          rel="noreferrer"
        >
          Source ↗
        </a>
      </footer>
    </main>
  );
}
