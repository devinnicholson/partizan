"use client";

import {
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import evidenceJson from "../public/evidence/crossing.json";

type Phase = 0 | 1 | 2 | 3;

type Statistics = {
  visited_position_nodes: number;
  legal_edges: number;
  duplicate_literal_options_removed: number;
  horizon_leaves: number;
  checkmate_leaves: number;
  stalemate_leaves: number;
  max_depth_reached: number;
  literal_game_nodes: number;
};

type Realization = {
  label: string;
  name: string;
  fen: string;
  adapter_id: string;
  move_state_key: string;
  witness: { move: string; result: string; plies: number };
  statistics: Statistics;
  literal_game_sha256: string;
  thermograph_identity_sha256: string;
};

type CrossingEvidence = {
  schema_version: string;
  evidence_sha256: string;
  claim: string;
  projection: {
    domain_id: string;
    rule: string;
    max_plies: number;
    node_budget: number;
  };
  comparison: {
    exact_value: string;
    canonical_game: string;
    proof: string;
    equal_to_value: boolean[];
    equal_to_each_other: boolean;
    transition_kinds: string[];
    repertoire_id: string;
    admitted_count: number;
  };
  realizations: Realization[];
};

type Piece = {
  id: string;
  color: "white" | "black";
  kind: string;
  square: string;
};

type TreeNode = { x: number; y: number; parent?: number };

const evidence = evidenceJson as CrossingEvidence;
const files = "abcdefgh";
const phaseLabels = ["Receive", "Distinguish", "Move", "Certify"] as const;

const treeNineteen: TreeNode[] = [
  { x: 50, y: 7 },
  { x: 13, y: 29, parent: 0 },
  { x: 36, y: 29, parent: 0 },
  { x: 61, y: 29, parent: 0 },
  { x: 86, y: 29, parent: 0 },
  { x: 7, y: 54, parent: 1 },
  { x: 18, y: 54, parent: 1 },
  { x: 30, y: 54, parent: 2 },
  { x: 42, y: 54, parent: 2 },
  { x: 55, y: 54, parent: 3 },
  { x: 67, y: 54, parent: 3 },
  { x: 82, y: 54, parent: 4 },
  { x: 93, y: 54, parent: 4 },
  { x: 5, y: 82, parent: 5 },
  { x: 20, y: 82, parent: 6 },
  { x: 37, y: 82, parent: 8 },
  { x: 59, y: 82, parent: 10 },
  { x: 79, y: 82, parent: 11 },
  { x: 95, y: 82, parent: 12 },
];

const treeEleven: TreeNode[] = [
  { x: 50, y: 7 },
  { x: 20, y: 32, parent: 0 },
  { x: 50, y: 32, parent: 0 },
  { x: 80, y: 32, parent: 0 },
  { x: 12, y: 59, parent: 1 },
  { x: 32, y: 59, parent: 1 },
  { x: 62, y: 59, parent: 2 },
  { x: 84, y: 59, parent: 3 },
  { x: 27, y: 84, parent: 5 },
  { x: 59, y: 84, parent: 6 },
  { x: 87, y: 84, parent: 7 },
];

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

function moveSquares(move: string): { from: string; to: string } {
  const match = move.match(/([a-h][1-8])[-x]([a-h][1-8])/);
  if (!match) throw new Error(`Unsupported visual witness move: ${move}`);
  return { from: match[1], to: match[2] };
}

function squarePosition(square: string) {
  return { file: files.indexOf(square[0]), row: 8 - Number(square[1]) };
}

function displayMove(move: string) {
  return move.replace("-", "–");
}

function shortHash(value: string) {
  const digest = value.includes(":") ? value.split(":").at(-1) : value;
  return digest?.slice(0, 10);
}

function ChessBoard({
  realization,
  phase,
}: {
  realization: Realization;
  phase: Phase;
}) {
  const pieces = useMemo(() => parseFen(realization.fen), [realization.fen]);
  const move = moveSquares(realization.witness.move);
  const from = squarePosition(move.from);
  const to = squarePosition(move.to);
  const movedPieces = pieces.map((piece) =>
    phase >= 2 && piece.square === move.from ? { ...piece, square: move.to } : piece,
  );
  const capturedIds = new Set(
    phase >= 2
      ? pieces
          .filter((piece) => piece.square === move.to && piece.square !== move.from)
          .map((piece) => piece.id)
      : [],
  );
  const dx = (to.file - from.file) * 12.5;
  const dy = (to.row - from.row) * 12.5;
  const distance = Math.sqrt(dx * dx + dy * dy);
  const angle = Math.atan2(dy, dx) * (180 / Math.PI);
  const vectorStyle = {
    "--vector-x": `${(from.file + 0.5) * 12.5}%`,
    "--vector-y": `${(from.row + 0.5) * 12.5}%`,
    "--vector-length": `${distance}%`,
    "--vector-angle": `${angle}deg`,
  } as CSSProperties;

  return (
    <div
      className={`chessboard phase-${phase}`}
      aria-label={`${realization.name}: ${realization.fen}`}
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
                square === move.from ? "move-from" : "",
                square === move.to ? "move-to" : "",
              ].join(" ")}
              key={square}
            >
              {file === 0 && <span className="rank-label">{8 - row}</span>}
              {row === 7 && <span className="file-label">{files[file]}</span>}
            </div>
          );
        })}
      </div>
      <div className="trajectory" style={vectorStyle} aria-hidden="true" />
      <div
        className="arrival-ring"
        style={{ "--file": to.file, "--row": to.row } as CSSProperties}
        aria-hidden="true"
      />
      {movedPieces.map((piece) => {
        const position = squarePosition(piece.square);
        return (
          <span
            className={`piece ${piece.color} ${
              capturedIds.has(piece.id) ? "captured" : ""
            }`}
            key={piece.id}
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
      {phase === 3 && (
        <div className="mate-mark" aria-live="polite">
          <span>checkmate</span>
          <strong>#</strong>
        </div>
      )}
    </div>
  );
}

function TreeConstellation({
  nodes,
  phase,
  label,
}: {
  nodes: TreeNode[];
  phase: Phase;
  label: string;
}) {
  return (
    <div
      className={`tree-constellation phase-${phase}`}
      aria-label={`${label}, ${nodes.length} literal game nodes`}
    >
      {nodes.map((node, index) => {
        if (node.parent === undefined) return null;
        const parent = nodes[node.parent];
        const dx = node.x - parent.x;
        const dy = node.y - parent.y;
        const length = Math.sqrt(dx * dx + dy * dy);
        const angle = Math.atan2(dy, dx) * (180 / Math.PI);
        return (
          <span
            className="tree-edge"
            key={`edge-${index}`}
            style={{
              "--x": `${parent.x}%`,
              "--y": `${parent.y}%`,
              "--length": `${length}%`,
              "--angle": `${angle}deg`,
              "--delay": `${index * 38}ms`,
            } as CSSProperties}
          />
        );
      })}
      {nodes.map((node, index) => (
        <span
          className={`tree-node ${index === 0 ? "root" : ""}`}
          key={`node-${index}`}
          style={{
            "--x": `${node.x}%`,
            "--y": `${node.y}%`,
            "--delay": `${index * 42}ms`,
          } as CSSProperties}
        />
      ))}
    </div>
  );
}

function RealizationCard({
  realization,
  index,
  phase,
}: {
  realization: Realization;
  index: number;
  phase: Phase;
}) {
  return (
    <article className={`realization-card realization-${index + 1}`}>
      <header className="card-heading">
        <div>
          <span className="roman">{realization.label}</span>
          <p>{realization.name}</p>
        </div>
        <div className="status-readout" aria-live="polite">
          <span className="status-light" />
          {phase === 0 && "position received"}
          {phase === 1 && "witness selected"}
          {phase === 2 && displayMove(realization.witness.move)}
          {phase === 3 && "mate certified"}
        </div>
      </header>

      <ChessBoard realization={realization} phase={phase} />

      <div className="notation-row">
        <span>chosen witness</span>
        <strong>
          {displayMove(realization.witness.move)}
          <sup>#</sup>
        </strong>
        <span>one ply</span>
      </div>

      <dl className="measurements">
        <div>
          <dt>literal nodes</dt>
          <dd>{realization.statistics.literal_game_nodes}</dd>
        </div>
        <div>
          <dt>legal edges searched</dt>
          <dd>{realization.statistics.legal_edges.toLocaleString("en-US")}</dd>
        </div>
        <div>
          <dt>positions visited</dt>
          <dd>{realization.statistics.visited_position_nodes.toLocaleString("en-US")}</dd>
        </div>
      </dl>

      <details className="certificate">
        <summary>Certificate</summary>
        <dl>
          <div>
            <dt>Adapter</dt>
            <dd>{shortHash(realization.adapter_id)}</dd>
          </div>
          <div>
            <dt>Literal game</dt>
            <dd>{shortHash(realization.literal_game_sha256)}</dd>
          </div>
          <div>
            <dt>Structure</dt>
            <dd>{shortHash(realization.thermograph_identity_sha256)}</dd>
          </div>
        </dl>
      </details>
    </article>
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
      if (target?.closest("button, a, summary, input, textarea, select")) return;
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
          <span>Checked crossing 01</span>
          <span>KQK · four-ply horizon</span>
        </div>
        <h1>
          <span>One value.</span>
          <em>Two encounters.</em>
        </h1>
        <p className="hero-claim">{evidence.claim}</p>
        <div className="hero-controls">
          <button className="begin-button" type="button" onClick={begin}>
            <span className={playing ? "pause-mark" : "play-mark"} aria-hidden="true" />
            {playing
              ? "Proof in motion"
              : phase === 3
                ? "Witness again"
                : "Begin the proof"}
          </button>
          <p>
            Space to replay
            <span aria-hidden="true"> · </span>
            arrows to examine
          </p>
        </div>
      </section>

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

      <section className="crossing" aria-label="Certified chess realizations">
        {evidence.realizations.map((realization, index) => (
          <RealizationCard
            realization={realization}
            index={index}
            phase={phase}
            key={realization.adapter_id}
          />
        ))}
      </section>

      <section className="identity-field" aria-label="Literal game comparison">
        <div className="tree-panel">
          <header>
            <span>literal game I</span>
            <strong>19 nodes</strong>
          </header>
          <TreeConstellation nodes={treeNineteen} phase={phase} label="Literal game I" />
          <p>97062b248c</p>
        </div>

        <div className="equality-axis">
          <span className="axis-rule" aria-hidden="true" />
          <p>Conway order</p>
          <div className="value-seal" aria-live="polite">
            <span>certified value</span>
            <strong>{phase === 3 ? "1 = 1" : "?"}</strong>
            <small>{evidence.comparison.canonical_game}</small>
          </div>
          <p>{phase === 3 ? "equivalent" : "comparison pending"}</p>
          <span className="axis-rule" aria-hidden="true" />
        </div>

        <div className="tree-panel">
          <header>
            <span>literal game II</span>
            <strong>11 nodes</strong>
          </header>
          <TreeConstellation nodes={treeEleven} phase={phase} label="Literal game II" />
          <p>81c4acda47</p>
        </div>
      </section>

      <section className="conclusion" aria-live="polite">
        <p>Mathematical identity</p>
        <h2>
          {phase === 3 ? (
            <>
              The distance closes.
              <br />
              <em>The difference remains.</em>
            </>
          ) : (
            <>
              Two forms wait
              <br />
              <em>for judgment.</em>
            </>
          )}
        </h2>
        <div className="conclusion-metrics">
          <span>
            <b>{evidence.comparison.admitted_count}</b> realizations
          </span>
          <span>
            <b>{evidence.projection.max_plies}</b> ply horizon
          </span>
          <span>
            <b>{evidence.projection.node_budget.toLocaleString("en-US")}</b> node budget
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
            <dt>Evidence</dt>
            <dd>{evidence.evidence_sha256.slice(0, 12)}</dd>
          </div>
          <div>
            <dt>Proof</dt>
            <dd>recursive order</dd>
          </div>
          <div>
            <dt>Relation</dt>
            <dd>literal crossing</dd>
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
