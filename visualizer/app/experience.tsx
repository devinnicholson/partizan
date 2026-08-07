"use client";

import { type CSSProperties, useMemo, useState } from "react";
import elkiesJson from "../public/evidence/elkies-study.json";
import motifJson from "../public/evidence/fixed-value-motif.json";

type Label = "A" | "B" | "C";
type PairKey = "A:B" | "B:C" | "A:C";
type Stage = 0 | 1 | 2;

type GraphPosition = {
  label: Label;
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

type FixedValueMotif = {
  completion_sha256: string;
  run: {
    proposal_count: number;
    linked_motif_count: number;
    independent_replay: boolean;
    negative_test_families_rejected: number;
  };
  comparison: {
    exact_value: string;
    statement: string;
    literal_statement: string;
    quotient_statement: string;
  };
  positions: GraphPosition[];
  atlas: {
    quotient_unique_representatives: number;
  };
};

type HistoricalEvidence = {
  source: {
    title: string;
    url: string;
  };
};

const motif = motifJson as FixedValueMotif;
const elkies = elkiesJson as HistoricalEvidence;

const pairOptions: { key: PairKey; left: Label; right: Label }[] = [
  { key: "B:C", left: "B", right: "C" },
  { key: "A:B", left: "A", right: "B" },
  { key: "A:C", left: "A", right: "C" },
];

const graphCoordinates = [
  { x: 50, y: 7 },
  { x: 82, y: 25 },
  { x: 88, y: 59 },
  { x: 65, y: 88 },
  { x: 35, y: 88 },
  { x: 12, y: 59 },
  { x: 18, y: 25 },
] as const;

function getPosition(label: Label) {
  const position = motif.positions.find((item) => item.label === label);
  if (!position) throw new Error(`Missing form ${label}`);
  return position;
}

function arcKey([from, to]: [number, number]) {
  return `${from}→${to}`;
}

function shortHash(value: string) {
  return value.slice(0, 12);
}

function compareForms(left: GraphPosition, right: GraphPosition) {
  const leftKeys = new Set(left.arcs.map(arcKey));
  const rightKeys = new Set(right.arcs.map(arcKey));
  const onlyLeft = left.arcs.filter((arc) => !rightKeys.has(arcKey(arc)));
  const onlyRight = right.arcs.filter((arc) => !leftKeys.has(arcKey(arc)));

  return {
    onlyLeft,
    onlyRight,
    sameLiteralGame: left.literal_game_sha256 === right.literal_game_sha256,
    sameGraphQuotient: left.quotient_sha256 === right.quotient_sha256,
  };
}

function GraphEdge({
  from,
  to,
  unique,
  side,
}: {
  from: number;
  to: number;
  unique: boolean;
  side: "left" | "right";
}) {
  const start = graphCoordinates[from];
  const end = graphCoordinates[to];
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const distance = Math.hypot(dx, dy);
  const angle = Math.atan2(dy, dx) * (180 / Math.PI);

  return (
    <span
      className={`graph-edge ${unique ? `unique ${side}` : "shared"}`}
      style={
        {
          "--edge-x": `${start.x}%`,
          "--edge-y": `${start.y}%`,
          "--edge-length": `${distance}%`,
          "--edge-angle": `${angle}deg`,
        } as CSSProperties
      }
      aria-hidden="true"
    />
  );
}

function GraphFigure({
  position,
  counterpart,
  side,
  changedVertices,
}: {
  position: GraphPosition;
  counterpart: GraphPosition;
  side: "left" | "right";
  changedVertices: Set<number>;
}) {
  const counterpartArcs = new Set(counterpart.arcs.map(arcKey));

  return (
    <figure
      className={`graph-figure ${side}`}
      aria-label={`Form ${position.label}, a seven-vertex Digraph Placement position with ${position.graph_arc_count} directed arcs.`}
    >
      <figcaption>
        <span>Form {position.label}</span>
        <strong>{position.name}</strong>
      </figcaption>

      <div className="graph-field">
        {position.arcs.map(([from, to]) => (
          <GraphEdge
            from={from}
            to={to}
            unique={!counterpartArcs.has(arcKey([from, to]))}
            side={side}
            key={`${from}-${to}`}
          />
        ))}

        {graphCoordinates.map((coordinate, vertex) => (
          <span
            className={`graph-node ${
              position.blue_vertices.includes(vertex) ? "blue" : "red"
            } ${changedVertices.has(vertex) ? "changed" : ""}`}
            key={vertex}
            style={
              {
                "--node-x": `${coordinate.x}%`,
                "--node-y": `${coordinate.y}%`,
              } as CSSProperties
            }
            aria-hidden="true"
          >
            {vertex}
          </span>
        ))}
      </div>

      <footer>
        <span>{position.graph_arc_count} arcs</span>
        <span>{position.literal_game_nodes} game nodes</span>
      </footer>
    </figure>
  );
}

function IdentityPlate({
  left,
  right,
  sameLiteralGame,
  visible,
}: {
  left: GraphPosition;
  right: GraphPosition;
  sameLiteralGame: boolean;
  visible: boolean;
}) {
  return (
    <div className="identity-plate" aria-hidden={!visible}>
      <p className="identity-kicker">Exact comparison</p>
      <h2>
        {sameLiteralGame
          ? "One complete game."
          : "One exact value."}
      </h2>
      <div className="identity-stack">
        <div>
          <span>Graph quotient</span>
          <code>q({left.label}) ≠ q({right.label})</code>
          <strong>different</strong>
        </div>
        <div className={sameLiteralGame ? "identity-focus" : ""}>
          <span>Complete game</span>
          <code>
            ℓ({left.label}) {sameLiteralGame ? "=" : "≠"} ℓ({right.label})
          </code>
          <strong>{sameLiteralGame ? "same" : "different"}</strong>
        </div>
        <div className="identity-focus">
          <span>Exact value</span>
          <code>v({left.label}) = v({right.label}) = 0</code>
          <strong>same</strong>
        </div>
      </div>
    </div>
  );
}

function CrossingTheater() {
  const [pairKey, setPairKey] = useState<PairKey>("B:C");
  const [stage, setStage] = useState<Stage>(0);
  const [copyState, setCopyState] = useState("Copy evidence JSON");
  const pair = pairOptions.find((option) => option.key === pairKey) ?? pairOptions[0];
  const left = getPosition(pair.left);
  const right = getPosition(pair.right);
  const comparison = useMemo(() => compareForms(left, right), [left, right]);

  const changedVertices = useMemo(
    () =>
      new Set(
        [...comparison.onlyLeft, ...comparison.onlyRight].flatMap(([from, to]) => [
          from,
          to,
        ]),
      ),
    [comparison],
  );

  const payload = useMemo(
    () => ({
      schema_version: "partizan.visual_comparison.v1",
      source_completion_sha256: motif.completion_sha256,
      exact_relation: `v(${left.label}) = v(${right.label}) = 0`,
      same_graph_quotient: comparison.sameGraphQuotient,
      same_complete_game: comparison.sameLiteralGame,
      arcs_only_in_left: comparison.onlyLeft,
      arcs_only_in_right: comparison.onlyRight,
      left,
      right,
    }),
    [comparison, left, right],
  );

  async function copyComparison() {
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      setCopyState("Copied");
    } catch {
      setCopyState("Copy failed");
    }
  }

  function downloadComparison() {
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `partizan-${left.label}-${right.label}-comparison.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const differences = [...comparison.onlyLeft, ...comparison.onlyRight];
  const differenceText = differences.length
    ? differences.map(arcKey).join(" and ")
    : "no literal arcs";

  const captions = [
    `${left.label} and ${right.label} are different directed graphs.`,
    `${differences.length === 1 ? "One arc changes" : `${differences.length} arcs change`}: ${differenceText}.`,
    comparison.sameLiteralGame
      ? `Their graph quotients differ. Their complete-game digest is identical.`
      : `Their graph quotients and complete games differ. Their exact value is identical.`,
  ];

  const nextLabels = ["Isolate the change", "Test what survives", "Replay"];

  return (
    <section
      className={`crossing-theater stage-${stage}`}
      id="crossing"
      aria-labelledby="crossing-title"
    >
      <header className="theater-header">
        <div>
          <p className="eyebrow">A certified crossing</p>
          <h1 id="crossing-title">What remains when correctness is fixed?</h1>
        </div>
        <div className="pair-picker" aria-label="Choose a pair">
          <span>Compare</span>
          {pairOptions.map((option) => (
            <button
              type="button"
              className={option.key === pairKey ? "active" : ""}
              aria-pressed={option.key === pairKey}
              key={option.key}
              onClick={() => {
                setPairKey(option.key);
                setStage(0);
                setCopyState("Copy evidence JSON");
              }}
            >
              {option.left}/{option.right}
            </button>
          ))}
        </div>
      </header>

      <div className="visual-stage">
        <div className="graph-pair">
          <GraphFigure
            position={left}
            counterpart={right}
            side="left"
            changedVertices={changedVertices}
          />
          <GraphFigure
            position={right}
            counterpart={left}
            side="right"
            changedVertices={changedVertices}
          />
        </div>
        <IdentityPlate
          left={left}
          right={right}
          sameLiteralGame={comparison.sameLiteralGame}
          visible={stage === 2}
        />
        <div className="stage-index" aria-hidden="true">0{stage + 1}</div>
      </div>

      <div className="theater-controls">
        <div className="stage-caption" aria-live="polite">
          <span>0{stage + 1}</span>
          <p>{captions[stage]}</p>
        </div>
        <div className="stage-buttons" aria-label="Crossing stages">
          {([0, 1, 2] as Stage[]).map((item) => (
            <button
              type="button"
              className={stage === item ? "active" : ""}
              aria-current={stage === item ? "step" : undefined}
              key={item}
              onClick={() => setStage(item)}
            >
              {item + 1}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="next-stage"
          onClick={() => setStage((stage === 2 ? 0 : stage + 1) as Stage)}
        >
          {nextLabels[stage]} <span aria-hidden="true">→</span>
        </button>
      </div>

      <details className="technical-evidence">
        <summary>Technical evidence</summary>
        <div className="technical-grid">
          <div>
            <span>{left.label} graph quotient</span>
            <code>{left.quotient_sha256}</code>
          </div>
          <div>
            <span>{right.label} graph quotient</span>
            <code>{right.quotient_sha256}</code>
          </div>
          <div>
            <span>{left.label} complete game</span>
            <code>{left.literal_game_sha256}</code>
          </div>
          <div>
            <span>{right.label} complete game</span>
            <code>{right.literal_game_sha256}</code>
          </div>
        </div>
        <div className="technical-actions">
          <button type="button" onClick={copyComparison}>{copyState}</button>
          <button type="button" onClick={downloadComparison}>Download evidence JSON</button>
        </div>
      </details>
    </section>
  );
}

export function PartizanExperience() {
  return (
    <main className="experience" id="top">
      <header className="masthead">
        <a className="wordmark" href="#top">Partizan</a>
        <span>Fixed-value repertoire</span>
        <nav aria-label="Page links">
          <a href="#crossing">Crossing</a>
          <a
            href="https://github.com/devinnicholson/partizan"
            target="_blank"
            rel="noreferrer"
          >
            Source
          </a>
        </nav>
      </header>

      <CrossingTheater />

      <section className="reading-note" aria-labelledby="reading-title">
        <p className="eyebrow">The result</p>
        <h2 id="reading-title">
          Mathematics can identify two objects while their visible forms remain
          different.
        </h2>
        <div className="reading-columns">
          <p>
            Partizan searches inside a fixed value. The verifier admits exact
            realizations; the repertoire preserves the structural differences
            between them.
          </p>
          <p>
            The B/C crossing is the sharpest example in this set. Form C adds
            the arc 6→0. The complete-game digest remains unchanged.
          </p>
        </div>
      </section>

      <section className="evidence-strip" aria-label="Study evidence">
        <div>
          <strong>{motif.run.proposal_count.toLocaleString("en-US")}</strong>
          <span>replayed proposals</span>
        </div>
        <div>
          <strong>{motif.atlas.quotient_unique_representatives.toLocaleString("en-US")}</strong>
          <span>quotient-unique forms</span>
        </div>
        <div>
          <strong>{motif.run.linked_motif_count.toLocaleString("en-US")}</strong>
          <span>linked motifs</span>
        </div>
        <div>
          <strong>{motif.run.negative_test_families_rejected}</strong>
          <span>corruption families rejected</span>
        </div>
      </section>

      <section className="history-note">
        <p>
          Lewis Stiller found an endgame kernel. Noam Elkies composed a study
          around it. Partizan carries that division of labor into a searchable
          combinatorial-game repertoire.
        </p>
        <a href={elkies.source.url} target="_blank" rel="noreferrer">
          Read the historical source
        </a>
      </section>

      <footer className="footer">
        <span>Independent replay passed</span>
        <span>completion {shortHash(motif.completion_sha256)}</span>
      </footer>
    </main>
  );
}
