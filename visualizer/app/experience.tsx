"use client";

import {
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import evidenceJson from "../public/evidence/crossing.json";
import elkiesJson from "../public/evidence/elkies-study.json";

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

type Piece = {
  id: string;
  color: "white" | "black";
  kind: string;
  square: string;
};

type TreeNode = { x: number; y: number; parent?: number };

const evidence = evidenceJson as CrossingEvidence;
const elkies = elkiesJson as HistoricalEvidence;
const files = "abcdefgh";
const phaseLabels = ["Receive", "Distinguish", "Move", "Certify"] as const;
const witnessLandmarks = [0, 3, 7, 10, 12, 13] as const;

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

function uciSquares(move: string | null): { from: string; to: string } | null {
  if (!move || !/^[a-h][1-8][a-h][1-8][qrbn]?$/.test(move)) return null;
  return { from: move.slice(0, 2), to: move.slice(2, 4) };
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
          <span>Partizan · forms under constraint</span>
          <span>Historical witness + checked crossing</span>
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

      <HistoricalPrelude />

      <div className="crossing-intro">
        <div>
          <span>Partizan crossing 01</span>
          <p>KQK · exact bounded value</p>
        </div>
        <h2>
          Here the question becomes exact:
          <em> what remains when correctness is fixed?</em>
        </h2>
        <p>
          Partizan generates two literal chess games, certifies each against
          the same target value, and preserves the differences that equality
          leaves behind.
        </p>
      </div>

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
