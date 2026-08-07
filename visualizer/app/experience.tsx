"use client";

import { type CSSProperties, useState } from "react";
import elkiesJson from "../public/evidence/elkies-study.json";
import motifJson from "../public/evidence/fixed-value-motif.json";

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
  transitions: {
    operation: string;
    detail: string;
  }[];
  atlas: {
    quotient_unique_representatives: number;
    targets: {
      label: string;
      quotients: number;
      literal_games: number;
    }[];
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

const graphCoordinates = [
  { x: 50, y: 7 },
  { x: 82, y: 25 },
  { x: 88, y: 59 },
  { x: 65, y: 88 },
  { x: 35, y: 88 },
  { x: 12, y: 59 },
  { x: 18, y: 25 },
] as const;

const readings: Record<
  GraphPosition["label"],
  { title: string; summary: string; comparison: string }
> = {
  A: {
    title: "The larger game",
    summary: "A has 19 nodes and 18 edges in its complete game tree.",
    comparison: "Its complete game differs from B and C.",
  },
  B: {
    title: "The smaller game",
    summary: "Removing 2→3 reduces the complete game to 15 nodes and 14 edges.",
    comparison: "B and C have the same complete game but different graphs.",
  },
  C: {
    title: "A new graph",
    summary: "C adds 6→0 to B. The graph changes; the complete game stays the same.",
    comparison: "B and C have different graph quotients.",
  },
};

function shortHash(value: string) {
  return value.slice(0, 10);
}

function GraphEdge({ from, to }: { from: number; to: number }) {
  const start = graphCoordinates[from];
  const end = graphCoordinates[to];
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const distance = Math.hypot(dx, dy);
  const angle = Math.atan2(dy, dx) * (180 / Math.PI);

  return (
    <span
      className="graph-edge"
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

function DigraphBoard({ position }: { position: GraphPosition }) {
  return (
    <div
      className="digraph-board"
      aria-label={`Form ${position.label}, a seven-vertex Digraph Placement position with exact value zero`}
    >
      {position.arcs.map(([from, to]) => (
        <GraphEdge from={from} to={to} key={`${from}-${to}`} />
      ))}
      {graphCoordinates.map((coordinate, vertex) => (
        <span
          className={`graph-node ${
            position.blue_vertices.includes(vertex) ? "left-vertex" : "right-vertex"
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
    </div>
  );
}

function ComposerDesk() {
  const [activeLabel, setActiveLabel] =
    useState<GraphPosition["label"]>("B");
  const [selectedLabel, setSelectedLabel] =
    useState<GraphPosition["label"] | null>(null);
  const active =
    motif.positions.find((position) => position.label === activeLabel) ??
    motif.positions[1];
  const reading = readings[active.label];

  return (
    <section className="composer" id="compare" aria-labelledby="compare-title">
      <div className="section-heading">
        <p className="eyebrow">Composer&apos;s desk</p>
        <h2 id="compare-title">Compare the forms.</h2>
        <p>Click a graph. The exact value stays fixed; its structure changes.</p>
      </div>

      <div className="equality-statement" aria-label="Certified equality">
        <span>Certified equality</span>
        <strong>v(A) = v(B) = v(C) = 0</strong>
      </div>

      <div className="form-grid" aria-label="Three certified forms">
        {motif.positions.map((position) => {
          const activeCard = position.label === activeLabel;
          const selectedCard = position.label === selectedLabel;

          return (
            <button
              type="button"
              className={`form-card ${activeCard ? "active" : ""}`}
              aria-pressed={activeCard}
              onClick={() => setActiveLabel(position.label)}
              key={position.candidate_sha256}
            >
              <span className="form-label">
                Form {position.label}
                {selectedCard && <small>selected</small>}
              </span>
              <DigraphBoard position={position} />
              <span className="form-name">{readings[position.label].title}</span>
              <span className="form-counts">
                {position.literal_game_nodes} game nodes, {position.graph_arc_count} graph arcs
              </span>
            </button>
          );
        })}
      </div>

      <article className="inspection" aria-live="polite">
        <div className="inspection-copy">
          <p className="eyebrow">Form {active.label}</p>
          <h3>{reading.title}</h3>
          <p>{reading.summary}</p>
          <p>{reading.comparison}</p>
          <button
            type="button"
            className="select-form"
            onClick={() => setSelectedLabel(active.label)}
          >
            {selectedLabel === active.label
              ? `Form ${active.label} selected`
              : `Select form ${active.label}`}
          </button>
          <small className="selection-note">
            Partizan certifies equality. The composer chooses the form.
          </small>
        </div>

        <dl className="inspection-data">
          <div>
            <dt>Exact value</dt>
            <dd>0</dd>
          </div>
          <div>
            <dt>Graph quotient</dt>
            <dd title={active.quotient_sha256}>{shortHash(active.quotient_sha256)}</dd>
          </div>
          <div>
            <dt>Complete game</dt>
            <dd title={active.literal_game_sha256}>{shortHash(active.literal_game_sha256)}</dd>
          </div>
          <div>
            <dt>First event</dt>
            <dd>{active.first_global_event_index}</dd>
          </div>
        </dl>
      </article>
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
          <a href="#evidence">Evidence</a>
          <a
            href="https://github.com/devinnicholson/partizan"
            target="_blank"
            rel="noreferrer"
          >
            Source
          </a>
        </nav>
      </header>

      <section className="hero">
        <p className="eyebrow">Order-7 Digraph Placement</p>
        <h1>One value.<br />Three forms.</h1>
        <p className="hero-copy">
          Partizan found three positions with exact value 0. Their graphs and
          complete game trees are different.
        </p>
        <a className="primary-link" href="#compare">Compare the forms</a>
      </section>

      <ComposerDesk />

      <section className="roles" aria-labelledby="roles-title">
        <div className="section-heading compact">
          <p className="eyebrow">Division of work</p>
          <h2 id="roles-title">Who decides what.</h2>
        </div>
        <dl>
          <div>
            <dt>Search</dt>
            <dd>Proposes positions.</dd>
          </div>
          <div>
            <dt>Verifier</dt>
            <dd>Keeps positions equal to 0.</dd>
          </div>
          <div>
            <dt>Composer</dt>
            <dd>Chooses a form.</dd>
          </div>
        </dl>
      </section>

      <section className="evidence" id="evidence" aria-labelledby="evidence-title">
        <div className="section-heading">
          <p className="eyebrow">Evidence</p>
          <h2 id="evidence-title">A fixed value leaves room.</h2>
          <p>
            The frozen study replayed {motif.run.proposal_count.toLocaleString("en-US")} proposals
            and found {motif.atlas.quotient_unique_representatives.toLocaleString("en-US")} quotient-unique
            representatives across the targets 0, *, and 1/2. These three positions form one linked example.
          </p>
        </div>

        <div className="crossings">
          <article>
            <p className="eyebrow">A to B</p>
            <h3>Remove 2→3</h3>
            <p>The complete game changes from 19 nodes to 15.</p>
            <code>ℓ(A) ≠ ℓ(B)</code>
          </article>
          <article>
            <p className="eyebrow">B to C</p>
            <h3>Add 6→0</h3>
            <p>The graph changes. The complete game does not.</p>
            <code>ℓ(B) = ℓ(C)</code>
          </article>
        </div>

        <div className="scope-note">
          <p>
            Measured: exact equality, graph quotient, and complete game.
          </p>
          <p>
            Left to the composer: aesthetic preference. The study does not assign an aesthetic score.
          </p>
        </div>
      </section>

      <section className="history" aria-labelledby="history-title">
        <p className="eyebrow">A precedent in chess</p>
        <h2 id="history-title">Stiller found the endgame kernel. Elkies composed a study around it.</h2>
        <p>
          The mathematical core stayed intact while the route to it changed.
          Partizan applies the same division of labor to a certified family of
          combinatorial games.
        </p>
        <a href={elkies.source.url} target="_blank" rel="noreferrer">
          Read {elkies.source.title}
        </a>
      </section>

      <footer className="footer">
        <p>Partizan</p>
        <p>
          {motif.run.independent_replay ? "Independent replay passed" : "Replay pending"}
          <span aria-hidden="true"> · </span>
          completion {shortHash(motif.completion_sha256)}
        </p>
      </footer>
    </main>
  );
}
