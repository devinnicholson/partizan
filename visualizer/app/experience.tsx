"use client";

import { type CSSProperties, useMemo, useState } from "react";
import elkiesJson from "../public/evidence/elkies-study.json";
import motifJson from "../public/evidence/fixed-value-motif.json";

type Label = "A" | "B" | "C";
type PairKey = "A:B" | "B:C" | "A:C";

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

type ArcState = "shared" | "left-only" | "right-only";

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
  return value.slice(0, 10);
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
  state,
}: {
  from: number;
  to: number;
  state: ArcState;
}) {
  const start = graphCoordinates[from];
  const end = graphCoordinates[to];
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const distance = Math.hypot(dx, dy);
  const angle = Math.atan2(dy, dx) * (180 / Math.PI);

  return (
    <span
      className={`graph-edge ${state}`}
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

function ComparisonGraph({
  left,
  right,
}: {
  left: GraphPosition;
  right: GraphPosition;
}) {
  const leftKeys = new Set(left.arcs.map(arcKey));
  const rightKeys = new Set(right.arcs.map(arcKey));
  const allArcs = new Map<string, [number, number]>();

  [...left.arcs, ...right.arcs].forEach((arc) => allArcs.set(arcKey(arc), arc));

  return (
    <div
      className="comparison-graph"
      aria-label={`Overlay of forms ${left.label} and ${right.label}. Rust arcs occur only in ${left.label}; blue arcs occur only in ${right.label}.`}
    >
      {[...allArcs.entries()].map(([key, [from, to]]) => {
        const state: ArcState =
          leftKeys.has(key) && rightKeys.has(key)
            ? "shared"
            : leftKeys.has(key)
              ? "left-only"
              : "right-only";
        return <GraphEdge from={from} to={to} state={state} key={key} />;
      })}

      {graphCoordinates.map((coordinate, vertex) => (
        <span
          className={`graph-node ${
            left.blue_vertices.includes(vertex) ? "left-player" : "right-player"
          }`}
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

      <div className="graph-legend" aria-hidden="true">
        <span><i className="left-key" />only {left.label}</span>
        <span><i className="shared-key" />shared</span>
        <span><i className="right-key" />only {right.label}</span>
      </div>
    </div>
  );
}

function PairWorkbench() {
  const [pairKey, setPairKey] = useState<PairKey>("B:C");
  const [copyState, setCopyState] = useState("Copy JSON");
  const pair = pairOptions.find((option) => option.key === pairKey) ?? pairOptions[0];
  const left = getPosition(pair.left);
  const right = getPosition(pair.right);
  const comparison = useMemo(() => compareForms(left, right), [left, right]);

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

  const changeText = comparison.sameLiteralGame
    ? "The graph changes. The complete game stays the same."
    : "The graph and complete game both change.";

  return (
    <section className="workbench" id="compare" aria-labelledby="compare-title">
      <header className="workbench-header">
        <div>
          <p className="eyebrow">Exact pair comparison</p>
          <h2 id="compare-title">{left.label} and {right.label}</h2>
        </div>
        <div className="pair-tabs" role="tablist" aria-label="Choose two forms">
          {pairOptions.map((option) => (
            <button
              type="button"
              role="tab"
              aria-selected={option.key === pairKey}
              className={option.key === pairKey ? "active" : ""}
              key={option.key}
              onClick={() => {
                setPairKey(option.key);
                setCopyState("Copy JSON");
              }}
            >
              {option.left} / {option.right}
            </button>
          ))}
        </div>
      </header>

      <div className="workbench-grid">
        <div className="graph-panel">
          <div className="value-lock">
            <span>Exact relation</span>
            <strong>v({left.label}) = v({right.label}) = 0</strong>
          </div>
          <ComparisonGraph left={left} right={right} />
        </div>

        <aside className="comparison-panel" aria-live="polite">
          <p className="eyebrow">Result</p>
          <h3>{changeText}</h3>

          <dl className="comparison-facts">
            <div>
              <dt>Exact value</dt>
              <dd className="same">same</dd>
            </div>
            <div>
              <dt>Complete game</dt>
              <dd className={comparison.sameLiteralGame ? "same" : "different"}>
                {comparison.sameLiteralGame ? "same" : "different"}
              </dd>
            </div>
            <div>
              <dt>Graph quotient</dt>
              <dd className={comparison.sameGraphQuotient ? "same" : "different"}>
                {comparison.sameGraphQuotient ? "same" : "different"}
              </dd>
            </div>
          </dl>

          <div className="arc-difference">
            <div>
              <span>Only in {left.label}</span>
              <strong>
                {comparison.onlyLeft.length
                  ? comparison.onlyLeft.map(arcKey).join(", ")
                  : "none"}
              </strong>
            </div>
            <div>
              <span>Only in {right.label}</span>
              <strong>
                {comparison.onlyRight.length
                  ? comparison.onlyRight.map(arcKey).join(", ")
                  : "none"}
              </strong>
            </div>
          </div>

          <div className="record-actions">
            <button type="button" onClick={copyComparison}>{copyState}</button>
            <button type="button" onClick={downloadComparison}>Download record</button>
          </div>

          <details className="certificate-record">
            <summary>Show exact digests</summary>
            <dl>
              <div>
                <dt>{left.label} graph quotient</dt>
                <dd>{left.quotient_sha256}</dd>
              </div>
              <div>
                <dt>{right.label} graph quotient</dt>
                <dd>{right.quotient_sha256}</dd>
              </div>
              <div>
                <dt>{left.label} complete game</dt>
                <dd>{left.literal_game_sha256}</dd>
              </div>
              <div>
                <dt>{right.label} complete game</dt>
                <dd>{right.literal_game_sha256}</dd>
              </div>
            </dl>
          </details>
        </aside>
      </div>

      <details className="form-records">
        <summary>All three source records</summary>
        <div className="record-table">
          <div className="record-row record-head">
            <span>Form</span><span>Game</span><span>Graph</span><span>Nodes</span><span>Arcs</span>
          </div>
          {motif.positions.map((position) => (
            <div className="record-row" key={position.candidate_sha256}>
              <strong>{position.label}</strong>
              <code title={position.literal_game_sha256}>{shortHash(position.literal_game_sha256)}</code>
              <code title={position.quotient_sha256}>{shortHash(position.quotient_sha256)}</code>
              <span>{position.literal_game_nodes}</span>
              <span>{position.graph_arc_count}</span>
            </div>
          ))}
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
        <nav aria-label="Page links">
          <a href="#compare">Compare</a>
          <a
            href="https://github.com/devinnicholson/partizan"
            target="_blank"
            rel="noreferrer"
          >Source</a>
        </nav>
      </header>

      <section className="intro">
        <div>
          <p className="eyebrow">Order-7 Digraph Placement</p>
          <h1>Three forms. One exact value.</h1>
        </div>
        <div className="intro-copy">
          <p>
            Pick two forms. The overlay shows every changed arc and whether the
            complete game changed with it.
          </p>
          <a href="#compare">Start with B / C</a>
        </div>
      </section>

      <PairWorkbench />

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
        <p>
          Search proposes positions. Exact comparison admits them. A person
          decides which relation to inspect or export.
        </p>
      </section>

      <section className="history-note">
        <p>
          Lewis Stiller found an endgame kernel. Noam Elkies composed a study
          around it. Partizan tests the same division of labor in combinatorial
          games.
        </p>
        <a href={elkies.source.url} target="_blank" rel="noreferrer">
          {elkies.source.title}
        </a>
      </section>

      <footer className="footer">
        <span>Independent replay passed</span>
        <span>completion {shortHash(motif.completion_sha256)}</span>
      </footer>
    </main>
  );
}
