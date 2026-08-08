"use client";

import {
  type CSSProperties,
  type KeyboardEvent,
  type MouseEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import elkiesJson from "../public/evidence/elkies-study.json";
import fiberJson from "../public/evidence/fixed-value-fiber-193.json";
import motifJson from "../public/evidence/fixed-value-motif.json";

type Label = "A" | "B" | "C";
type Layer = 0 | 1 | 2;

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
  positions: GraphPosition[];
  transitions: {
    from: Label;
    to: Label;
    operation: string;
    arc: [number, number];
    headline: string;
    detail: string;
  }[];
  atlas: {
    quotient_unique_representatives: number;
    targets: { label: string; quotients: number; literal_games: number }[];
  };
};

type AtlasItem = {
  a: number;
  b: number;
  g: string;
  i: number;
  l: number;
  m: number;
  n: number;
  p: [number, number, number, number, number, number];
  q: string;
  t: number;
};

type AtlasGroup = { c: number; d: string; p: [number, number]; t: number };
type DagNode = { d: string; r: number; s: string; x: boolean };
type DagEdge = { f: number; p: "L" | "R"; t: number };
type LiteralDag = {
  root: number;
  state_count: number;
  nodes: DagNode[];
  edges: DagEdge[];
};

type AtlasData = {
  atlas_sha256: string;
  counts: {
    exact_values: number;
    literal_games: number;
    quotient_forms: number;
  };
  groups: AtlasGroup[];
  items: AtlasItem[];
  motif: Record<Label, number>;
  motif_dags: { A: LiteralDag; B: LiteralDag; C: "B" };
  source: {
    completion_sha256: string;
    events_file_sha256: string;
    independent_replay: boolean;
    negative_test_families_rejected: number;
    proposal_count: number;
    representative_set_sha256: string;
  };
  targets: {
    complete_game_node_range: [number, number];
    formal: string;
    graph_arc_range: [number, number];
    label: string;
    literal_games: number;
    quotient_forms: number;
  }[];
};

type HistoricalEvidence = { source: { title: string; url: string } };
type CompactFiber = {
  items: {
    a: number;
    b: number;
    g: string;
    i: number;
    m: number;
    n: number;
    p: [number, number];
    q: string;
  }[];
  selection: {
    literal_game_sha256: string;
    observed_quotient_forms: number;
    target_formal: string;
    target_label: string;
  };
};

const motif = motifJson as unknown as FixedValueMotif;
const elkies = elkiesJson as HistoricalEvidence;
const compactFiber = fiberJson as unknown as CompactFiber;
const numberFormat = new Intl.NumberFormat("en-US");
const layerNames = ["Graph form", "Complete game", "Exact value"] as const;
const layerCounts = [21_697, 16_120, 3] as const;
const nextLayerActions = [
  "Group by complete game",
  "Group by exact value",
  "Show graph forms",
] as const;
const atlasColors = ["#d7b168", "#e8e1d4", "#9b968b"] as const;
const FOCUS_LITERAL_DIGEST = compactFiber.selection.literal_game_sha256;

const graphCoordinates = [
  { x: 50, y: 8 },
  { x: 82, y: 26 },
  { x: 88, y: 60 },
  { x: 65, y: 88 },
  { x: 35, y: 88 },
  { x: 12, y: 60 },
  { x: 18, y: 26 },
] as const;

function shortHash(value: string) {
  return value.slice(0, 12);
}

function getPosition(label: Label) {
  const position = motif.positions.find((item) => item.label === label);
  if (!position) throw new Error(`Missing form ${label}`);
  return position;
}

function arcKey([from, to]: [number, number]) {
  return `${from}→${to}`;
}

function decodedArcs(code: string): [number, number][] {
  const bits = BigInt(`0x${code}`);
  const arcs: [number, number][] = [];
  for (let source = 0; source < 7; source += 1) {
    for (let target = 0; target < 7; target += 1) {
      if ((bits & (1n << BigInt(source * 7 + target))) !== 0n) {
        arcs.push([source, target]);
      }
    }
  }
  return arcs;
}

function decodedBlue(mask: number) {
  return Array.from({ length: 7 }, (_, vertex) => vertex).filter(
    (vertex) => (mask & (1 << vertex)) !== 0,
  );
}

function GraphEdge({
  from,
  to,
  highlighted,
}: {
  from: number;
  to: number;
  highlighted?: boolean;
}) {
  const start = graphCoordinates[from];
  const end = graphCoordinates[to];
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const distance = Math.hypot(dx, dy);
  const angle = Math.atan2(dy, dx) * (180 / Math.PI);

  return (
    <span
      className={`graph-edge${highlighted ? " highlighted" : ""}`}
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

function DirectedGraph({
  label,
  name,
  arcs,
  blueVertices,
  highlightedArc,
  compact = false,
}: {
  label: string;
  name: string;
  arcs: [number, number][];
  blueVertices: number[];
  highlightedArc?: [number, number];
  compact?: boolean;
}) {
  const highlightedKey = highlightedArc ? arcKey(highlightedArc) : null;
  return (
    <figure className={`directed-graph${compact ? " compact" : ""}`}>
      <figcaption>
        <span>{label}</span>
        <strong>{name}</strong>
      </figcaption>
      <div className="graph-field">
        {arcs.map(([from, to]) => (
          <GraphEdge
            from={from}
            to={to}
            highlighted={arcKey([from, to]) === highlightedKey}
            key={`${from}-${to}`}
          />
        ))}
        {graphCoordinates.map((coordinate, vertex) => (
          <span
            className={`graph-node ${
              blueVertices.includes(vertex) ? "blue" : "red"
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
    </figure>
  );
}

type FiberMember = { index: number; item: AtlasItem };
type FiberArcState = "shared" | "added" | "removed";

function FiberEdge({
  from,
  to,
  state,
}: {
  from: number;
  to: number;
  state: FiberArcState;
}) {
  const start = graphCoordinates[from];
  const end = graphCoordinates[to];
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const distance = Math.hypot(dx, dy);
  const angle = Math.atan2(dy, dx) * (180 / Math.PI);

  return (
    <span
      className={`fiber-edge ${state}`}
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

function FiberGraph({
  item,
  reference,
  large = false,
}: {
  item: AtlasItem;
  reference?: AtlasItem;
  large?: boolean;
}) {
  const arcs = decodedArcs(item.g);
  const referenceArcs = reference ? decodedArcs(reference.g) : arcs;
  const arcSet = new Set(arcs.map(arcKey));
  const referenceSet = new Set(referenceArcs.map(arcKey));
  const union = new Map<string, [number, number]>();
  for (const arc of [...referenceArcs, ...arcs]) union.set(arcKey(arc), arc);

  return (
    <div className={`fiber-graph${large ? " large" : ""}`} aria-hidden="true">
      {Array.from(union.values()).map(([from, to]) => {
        const key = arcKey([from, to]);
        const state: FiberArcState = !referenceSet.has(key)
          ? "added"
          : !arcSet.has(key)
            ? "removed"
            : "shared";
        return <FiberEdge from={from} to={to} state={state} key={key} />;
      })}
      {graphCoordinates.map((coordinate, vertex) => (
        <span
          className={`fiber-node ${
            (item.m & (1 << vertex)) !== 0 ? "blue" : "red"
          }`}
          key={vertex}
          style={
            {
              "--node-x": `${coordinate.x}%`,
              "--node-y": `${coordinate.y}%`,
            } as CSSProperties
          }
        >
          {large ? vertex : ""}
        </span>
      ))}
    </div>
  );
}

function edgeDifference(reference: AtlasItem, selected: AtlasItem) {
  const referenceSet = new Set(decodedArcs(reference.g).map(arcKey));
  const selectedSet = new Set(decodedArcs(selected.g).map(arcKey));
  return {
    added: Array.from(selectedSet).filter((arc) => !referenceSet.has(arc)),
    removed: Array.from(referenceSet).filter((arc) => !selectedSet.has(arc)),
  };
}

type FiberCanvasCell = {
  member: FiberMember;
  x: number;
  y: number;
  width: number;
  height: number;
};

function FiberHeroCanvas({
  columns,
  selected,
  reference,
  onSelect,
  onNavigate,
}: {
  columns: { arcCount: number; members: FiberMember[] }[];
  selected: FiberMember | null;
  reference: FiberMember | null;
  onSelect: (member: FiberMember) => void;
  onNavigate: (key: string) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const cellsRef = useRef<FiberCanvasCell[]>([]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const targetWidth = Math.max(1, Math.round(width * dpr));
    const targetHeight = Math.max(1, Math.round(height * dpr));
    if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
      canvas.width = targetWidth;
      canvas.height = targetHeight;
    }
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#090908";
    context.fillRect(0, 0, width, height);

    const rows = 11;
    const top = 76;
    const bottom = 18;
    const outer = 18;
    const gap = 12;
    const usableWidth = width - outer * 2 - gap * (columns.length - 1);
    const units = columns.map(({ members }) => Math.max(1, Math.ceil(members.length / rows)));
    const totalUnits = units.reduce((sum, value) => sum + value, 0);
    const unitWidth = usableWidth / totalUnits;
    const rowHeight = (height - top - bottom) / rows;
    const cells: FiberCanvasCell[] = [];
    let columnX = outer;

    context.textBaseline = "alphabetic";
    columns.forEach(({ arcCount, members }, columnIndex) => {
      const columnWidth = units[columnIndex] * unitWidth;
      context.strokeStyle = "rgba(241,236,223,.17)";
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(Math.round(columnX) + 0.5, 16);
      context.lineTo(Math.round(columnX) + 0.5, height - 12);
      context.stroke();
      context.fillStyle = "#f1ecdf";
      context.font = "22px Iowan Old Style, Baskerville, serif";
      context.fillText(String(arcCount), columnX + 7, 34);
      context.fillStyle = "#8f8b81";
      context.font = "9px SFMono-Regular, Roboto Mono, monospace";
      context.fillText(`${members.length} ${members.length === 1 ? "FORM" : "FORMS"}`, columnX + 7, 51);

      members.forEach((member, memberIndex) => {
        const subcolumn = Math.floor(memberIndex / rows);
        const row = memberIndex % rows;
        const cellX = columnX + subcolumn * unitWidth;
        const cellY = top + row * rowHeight;
        const cellWidth = unitWidth;
        const cellHeight = rowHeight;
        cells.push({ member, x: cellX, y: cellY, width: cellWidth, height: cellHeight });

        const centerX = cellX + cellWidth / 2;
        const centerY = cellY + cellHeight / 2;
        const graphSize = Math.min(52, cellWidth - 8, cellHeight - 8);
        const radius = 2.05;
        const nodePosition = (vertex: number) => ({
          x: centerX + ((graphCoordinates[vertex].x - 50) / 100) * graphSize,
          y: centerY + ((graphCoordinates[vertex].y - 50) / 100) * graphSize,
        });

        const isSelected = member.index === selected?.index;
        const isReference = member.index === reference?.index;
        if (isSelected || isReference) {
          context.strokeStyle = isSelected ? "#e96f58" : "#d7b168";
          context.lineWidth = isSelected ? 1.5 : 1;
          context.strokeRect(
            Math.round(cellX + 2) + 0.5,
            Math.round(cellY + 2) + 0.5,
            Math.max(4, cellWidth - 5),
            Math.max(4, cellHeight - 5),
          );
        }

        context.strokeStyle = "rgba(241,236,223,.42)";
        context.fillStyle = "rgba(241,236,223,.42)";
        context.lineWidth = 0.9;
        for (const [from, to] of decodedArcs(member.item.g)) {
          const start = nodePosition(from);
          const end = nodePosition(to);
          if (from === to) {
            context.beginPath();
            context.arc(start.x + 2.4, start.y - 2.4, 3.2, 0.4, Math.PI * 2.05);
            context.stroke();
            context.beginPath();
            context.moveTo(start.x + 4.8, start.y - 4.7);
            context.lineTo(start.x + 2.7, start.y - 5.1);
            context.lineTo(start.x + 4.2, start.y - 2.9);
            context.fill();
            continue;
          }
          const dx = end.x - start.x;
          const dy = end.y - start.y;
          const length = Math.hypot(dx, dy) || 1;
          const ux = dx / length;
          const uy = dy / length;
          const startX = start.x + ux * (radius + 0.5);
          const startY = start.y + uy * (radius + 0.5);
          const endX = end.x - ux * (radius + 0.8);
          const endY = end.y - uy * (radius + 0.8);
          context.beginPath();
          context.moveTo(startX, startY);
          context.lineTo(endX, endY);
          context.stroke();
          const arrowX = startX + (endX - startX) * 0.73;
          const arrowY = startY + (endY - startY) * 0.73;
          context.beginPath();
          context.moveTo(arrowX + ux * 2.2, arrowY + uy * 2.2);
          context.lineTo(arrowX - uy * 1.6, arrowY + ux * 1.6);
          context.lineTo(arrowX + uy * 1.6, arrowY - ux * 1.6);
          context.closePath();
          context.fill();
        }

        graphCoordinates.forEach((_, vertex) => {
          const point = nodePosition(vertex);
          context.beginPath();
          context.arc(point.x, point.y, radius, 0, Math.PI * 2);
          context.fillStyle =
            (member.item.m & (1 << vertex)) !== 0 ? "#73b8bc" : "#e96f58";
          context.fill();
        });
      });
      columnX += columnWidth + gap;
    });

    context.beginPath();
    context.moveTo(Math.round(width - outer) + 0.5, 16);
    context.lineTo(Math.round(width - outer) + 0.5, height - 12);
    context.strokeStyle = "rgba(241,236,223,.17)";
    context.stroke();
    cellsRef.current = cells;
  }, [columns, reference, selected]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    draw();
    return () => observer.disconnect();
  }, [draw]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const scroller = canvas?.parentElement;
    if (!canvas || !scroller || !selected) return;
    const frame = requestAnimationFrame(() => {
      const cell = cellsRef.current.find(
        (candidate) => candidate.member.index === selected.index,
      );
      if (!cell) return;
      const leftEdge = scroller.scrollLeft;
      const rightEdge = leftEdge + scroller.clientWidth;
      const cellLeft = cell.x;
      const cellRight = cell.x + cell.width;
      if (cellLeft < leftEdge || cellRight > rightEdge) {
        scroller.scrollTo({
          left: Math.max(0, cell.x + cell.width / 2 - scroller.clientWidth / 2),
          behavior: "auto",
        });
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [selected]);

  function pick(clientX: number, clientY: number) {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const bounds = canvas.getBoundingClientRect();
    const x = clientX - bounds.left;
    const y = clientY - bounds.top;
    const cell = cellsRef.current.find(
      (candidate) =>
        x >= candidate.x &&
        x <= candidate.x + candidate.width &&
        y >= candidate.y &&
        y <= candidate.y + candidate.height,
    );
    if (cell) onSelect(cell.member);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLCanvasElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      if (reference) onSelect(reference);
      return;
    }
    if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    onNavigate(event.key);
  }

  function handleClick(event: MouseEvent<HTMLCanvasElement>) {
    pick(event.clientX, event.clientY);
  }

  return (
    <canvas
      data-fiber-hero-canvas
      ref={canvasRef}
      className="fiber-hero-canvas"
      role="group"
      tabIndex={0}
      aria-describedby="fiber-keyboard-help"
      aria-label="All 193 observed graph forms arranged in columns by directed-arc count from 17 through 27"
      onKeyDown={handleKeyDown}
      onClick={handleClick}
    />
  );
}

function FiberClass({ atlas, error }: { atlas: AtlasData | null; error: boolean }) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const largestGroupIndex = useMemo(() => {
    if (!atlas) return -1;
    return atlas.groups.findIndex(
      (group) => group.c === 193 && group.d === FOCUS_LITERAL_DIGEST,
    );
  }, [atlas]);

  const members = useMemo<FiberMember[]>(() => {
    const source =
      atlas && largestGroupIndex >= 0
        ? atlas.items
            .map((item, index) => ({ item, index }))
            .filter(({ item }) => item.l === largestGroupIndex)
        : compactFiber.items.map((item, index) => ({
            index,
            item: {
              ...item,
              l: -1,
              p: [item.p[0], item.p[1], 0, 0, 0, 0] as AtlasItem["p"],
              t: 2,
            },
          }));
    return source
      .sort((left, right) => left.item.a - right.item.a || left.item.q.localeCompare(right.item.q));
  }, [atlas, largestGroupIndex]);

  const byArcCount = useMemo(
    () =>
      Array.from({ length: 11 }, (_, offset) => 17 + offset).map((arcCount) => ({
        arcCount,
        members: members.filter(({ item }) => item.a === arcCount),
      })),
    [members],
  );

  const reference = useMemo(
    () => members.find(({ item }) => item.a === 23) ?? members[0] ?? null,
    [members],
  );

  const defaultSelected = members[Math.floor(members.length / 2)] ?? reference;
  const selected =
    members.find((member) => member.index === selectedIndex) ??
    defaultSelected;
  const selectedPosition = selected
    ? members.findIndex((member) => member.index === selected.index)
    : -1;
  const neighborhoodSize = 9;
  const neighborhoodStart = Math.max(
    0,
    Math.min(
      Math.max(0, members.length - neighborhoodSize),
      selectedPosition - Math.floor(neighborhoodSize / 2),
    ),
  );
  const neighborhood = members.slice(
    neighborhoodStart,
    neighborhoodStart + neighborhoodSize,
  );
  const difference =
    reference && selected ? edgeDifference(reference.item, selected.item) : null;
  const largestGroup =
    atlas && largestGroupIndex >= 0
      ? atlas.groups[largestGroupIndex]
      : ({ c: 193, d: FOCUS_LITERAL_DIGEST, p: [0, 0], t: 2 } as AtlasGroup);

  function focusMember(member: FiberMember) {
    setSelectedIndex(member.index);
  }

  function moveWithinBoard(key: string) {
    if (!selected) return;
    const columnIndex = byArcCount.findIndex(
      ({ arcCount }) => arcCount === selected.item.a,
    );
    const column = byArcCount[columnIndex];
    const rowIndex = column.members.findIndex(
      (member) => member.index === selected.index,
    );
    if (key === "ArrowUp" || key === "ArrowDown") {
      const delta = key === "ArrowUp" ? -1 : 1;
      const next = column.members[Math.max(0, Math.min(column.members.length - 1, rowIndex + delta))];
      if (next) focusMember(next);
      return;
    }
    if (key === "ArrowLeft" || key === "ArrowRight") {
      const delta = key === "ArrowLeft" ? -1 : 1;
      const nextColumn = byArcCount[Math.max(0, Math.min(byArcCount.length - 1, columnIndex + delta))];
      const next = nextColumn.members[Math.min(rowIndex, nextColumn.members.length - 1)];
      if (next) focusMember(next);
      return;
    }
    if (key === "Home" && members[0]) focusMember(members[0]);
    if (key === "End" && members.at(-1)) focusMember(members.at(-1)!);
  }

  function moveSequentially(delta: number) {
    if (!members.length) return;
    const nextPosition =
      (Math.max(0, selectedPosition) + delta + members.length) % members.length;
    focusMember(members[nextPosition]);
  }

  return (
    <section
      className="fiber-class"
      id="class"
      aria-labelledby="fiber-title"
      data-fixed-fiber-hero="193"
    >
      <header className="fiber-intro">
        <div>
          <p className="eyebrow">One certified equivalence class</p>
          <h1 id="fiber-title">193 graph forms. One complete game.</h1>
        </div>
        <p>
          The class map shows every observed order-7 Digraph Placement graph.
          The neighborhood and specimen views support direct comparison. The
          complete-game digest and exact value stay fixed.
        </p>
      </header>

      <div className="identity-receipt" aria-label="Exact identity receipt">
        <div><strong>193</strong><span>graph quotient digests</span></div>
        <b aria-hidden="true">→</b>
        <div><strong>1</strong><span>complete-game digest</span></div>
        <b aria-hidden="true">→</b>
        <div><strong>1/2</strong><span>exact value</span></div>
      </div>
      <p className="fiber-digest-receipt">
        Shared complete-game identity <code>{FOCUS_LITERAL_DIGEST}</code>
      </p>

      <div className="fiber-scale-guide" aria-label="Three levels of inspection">
        <div><span>01</span><strong>Complete class</strong><small>193 forms in one map</small></div>
        <div><span>02</span><strong>Neighborhood</strong><small>nine readable forms</small></div>
        <div><span>03</span><strong>Specimen</strong><small>one exact comparison</small></div>
      </div>

      <div className="fiber-instrument">
        <div className="fiber-instrument-header">
          <div>
            <p className="eyebrow">01 · Complete class</p>
            <p>All 193 forms, grouped by directed-arc count. This map establishes the size of the class.</p>
          </div>
          <div className="fiber-keyboard-hint">
            <kbd>←</kbd><kbd>→</kbd> arc column
            <kbd>↑</kbd><kbd>↓</kbd> form
          </div>
        </div>

        <div className="sr-only" aria-label="Arc-count distribution">
          {byArcCount.map(({ arcCount, members: columnMembers }) => (
            <div data-arc-column={arcCount} key={arcCount}>
              <strong>{arcCount}</strong>
              <span>
                {columnMembers.length} {columnMembers.length === 1 ? "form" : "forms"}
              </span>
            </div>
          ))}
        </div>

        <p className="sr-only" id="fiber-keyboard-help">
          Use Left and Right Arrow keys to change arc-count columns, Up and Down
          Arrow keys to move within a column, Home and End to reach the limits,
          and Escape to return to the stable reference. Touch or click any graph
          to compare it.
        </p>

        {largestGroup && members.length === 193 ? (
          <div className="fiber-board-scroll">
            <FiberHeroCanvas
              columns={byArcCount}
              selected={selected}
              reference={reference}
              onSelect={focusMember}
              onNavigate={moveWithinBoard}
            />
          </div>
        ) : (
          <div className="fiber-loading" role="status">
            {error ? "The checked equivalence class could not be loaded." : "Loading 193 certified graphs…"}
          </div>
        )}

        {reference && selected && difference && largestGroup && (
          <>
          <section
            className="fiber-neighborhood"
            id="neighborhood"
            aria-labelledby="fiber-neighborhood-title"
            data-fiber-neighborhood="9"
          >
            <header className="fiber-neighborhood-header">
              <div>
                <p className="eyebrow">02 · Neighborhood</p>
                <h2 id="fiber-neighborhood-title">Nine neighboring forms</h2>
                <p>
                  Forms {neighborhoodStart + 1}–{neighborhoodStart + neighborhood.length} of 193.
                  Select one for an exact comparison below.
                </p>
              </div>
              <div className="fiber-step-buttons fiber-neighborhood-nav">
                <button data-fiber-previous type="button" onClick={() => moveSequentially(-1)} aria-label="Previous graph form">← Previous</button>
                <button data-fiber-next type="button" onClick={() => moveSequentially(1)} aria-label="Next graph form">Next →</button>
              </div>
            </header>
            <div className="fiber-neighborhood-grid" role="list" aria-label="Nine graph forms near the current selection">
              {neighborhood.map((member) => {
                const position = members.findIndex((candidate) => candidate.index === member.index);
                const isCurrent = member.index === selected.index;
                return (
                  <div role="listitem" key={member.index}>
                    <button
                      type="button"
                      className={`fiber-neighborhood-card${isCurrent ? " selected" : ""}`}
                      aria-current={isCurrent ? "true" : undefined}
                      aria-label={`Form ${position + 1} of 193, ${member.item.a} directed arcs`}
                      onClick={() => focusMember(member)}
                    >
                      <FiberGraph item={member.item} />
                      <span><strong>{String(position + 1).padStart(3, "0")}</strong><small>{member.item.a} arcs</small></span>
                    </button>
                  </div>
                );
              })}
            </div>
          </section>

          <div className="fiber-inspector" data-fiber-specimen>
            <header className="fiber-selection-bar">
              <div>
                <span>03 · Specimen</span>
                <strong>{selectedPosition + 1} / 193</strong>
                <small>{selected.item.a} directed arcs · event {numberFormat.format(selected.item.i)}</small>
              </div>
            </header>
            <p className="sr-only" aria-live="polite">
              Selected form {selectedPosition + 1} of 193 with {selected.item.a} directed arcs.
            </p>
            <div className="fiber-specimens">
              <figure>
                <figcaption><span>Stable reference</span><strong>23 arcs</strong></figcaption>
                <FiberGraph item={reference.item} large />
                <small>Lexicographically first quotient digest in the median arc-count column.</small>
              </figure>
              <figure>
                <figcaption><span>Selected embodiment</span><strong>{selected.item.a} arcs</strong></figcaption>
                <FiberGraph item={selected.item} reference={reference.item} large />
                <small>{shortHash(selected.item.q)} · birthday {selected.item.b} · {selected.item.n} complete-game nodes</small>
              </figure>
              <aside className="fiber-difference">
                <p className="eyebrow">Against the reference</p>
                <div><strong>+{difference.added.length}</strong><span>added arcs</span></div>
                <p>{difference.added.length ? difference.added.join(", ") : "None"}</p>
                <div><strong>−{difference.removed.length}</strong><span>removed arcs</span></div>
                <p>{difference.removed.length ? difference.removed.join(", ") : "None"}</p>
                <dl>
                  <div>
                    <dt>Graph quotient</dt>
                    <dd>{selected.item.q === reference.item.q ? "same" : "different"}</dd>
                  </div>
                  <div><dt>Complete game</dt><dd>same</dd></div>
                  <div><dt>Exact value</dt><dd>1/2</dd></div>
                </dl>
              </aside>
            </div>
            <div className="fiber-legend" aria-label="Graph legend">
              <span><i className="node-blue" /> Blue vertex: Left</span>
              <span><i className="node-red" /> Red vertex: Right</span>
              <span><i className="line-shared" /> shared arc</span>
              <span><i className="line-added" /> added arc</span>
              <span><i className="line-removed" /> removed arc</span>
              <code>complete game {largestGroup.d}</code>
            </div>
          </div>
          </>
        )}
      </div>
    </section>
  );
}

function AtlasCanvas({
  atlas,
  layer,
  selectedIndex,
  onSelect,
  highlightMotif,
}: {
  atlas: AtlasData;
  layer: Layer;
  selectedIndex: number | null;
  onSelect: (index: number | null) => void;
  highlightMotif: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const layerValueRef = useRef<number>(layer);
  const animationRef = useRef<number | null>(null);
  const selectedRef = useRef(selectedIndex);
  const motifRef = useRef(highlightMotif);
  const groupFirstItem = useMemo(() => {
    const first = Array.from({ length: atlas.groups.length }, () => -1);
    for (let index = 0; index < atlas.items.length; index += 1) {
      const group = atlas.items[index].l;
      if (first[group] === -1) first[group] = index;
    }
    return first;
  }, [atlas]);

  const draw = useCallback((layerValue: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const targetWidth = Math.max(1, Math.round(width * dpr));
    const targetHeight = Math.max(1, Math.round(height * dpr));
    if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
      canvas.width = targetWidth;
      canvas.height = targetHeight;
    }
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);

    const lower = Math.min(1, Math.floor(layerValue));
    const upper = Math.min(2, lower + 1);
    const mix = layerValue - lower;
    const lowerOffset = lower * 2;
    const upperOffset = upper * 2;
    const pointSize = layerValue > 1.65 ? 1.1 : layerValue > 0.65 ? 1.35 : 1.55;

    context.save();
    context.strokeStyle = "rgba(245,240,228,.12)";
    context.lineWidth = 1;
    for (const split of [1 / 3, 2 / 3]) {
      context.beginPath();
      context.moveTo(Math.round(width * split) + 0.5, 22);
      context.lineTo(Math.round(width * split) + 0.5, height - 22);
      context.stroke();
    }
    context.restore();

    const islandOpacity = Math.max(0, 1 - Math.abs(layerValue - 1) / 0.48);
    if (islandOpacity > 0) {
      context.save();
      context.lineWidth = 1;
      for (let index = 0; index < atlas.groups.length; index += 1) {
        const group = atlas.groups[index];
        if (group.c <= 1) continue;
        const radius = Math.min(17, 2.5 + Math.sqrt(group.c) * 0.88);
        context.beginPath();
        context.arc(
          (group.p[0] / 10_000) * width,
          (group.p[1] / 10_000) * height,
          radius,
          0,
          Math.PI * 2,
        );
        context.globalAlpha = islandOpacity * Math.min(0.42, 0.12 + group.c / 300);
        context.strokeStyle = "#f5f0e4";
        context.stroke();
      }
      context.restore();
    }

    for (let target = 0; target < 3; target += 1) {
      context.beginPath();
      for (let index = 0; index < atlas.items.length; index += 1) {
        const item = atlas.items[index];
        if (item.t !== target) continue;
        const x =
          item.p[lowerOffset] +
          (item.p[upperOffset] - item.p[lowerOffset]) * mix;
        const y =
          item.p[lowerOffset + 1] +
          (item.p[upperOffset + 1] - item.p[lowerOffset + 1]) * mix;
        const screenX = (x / 10_000) * width;
        const screenY = (y / 10_000) * height;
        context.rect(screenX, screenY, pointSize, pointSize);
      }
      context.globalAlpha = layerValue > 1.65 ? 0.36 : 0.64;
      context.fillStyle = atlasColors[target];
      context.fill();
    }
    context.globalAlpha = 1;

    const valueOpacity = Math.max(0, (layerValue - 1.55) / 0.45);
    if (valueOpacity > 0) {
      context.save();
      context.globalAlpha = valueOpacity;
      context.lineWidth = 1.5;
      context.strokeStyle = "rgba(245,240,228,.62)";
      for (const center of [1_700, 5_000, 8_300]) {
        context.beginPath();
        context.arc((center / 10_000) * width, height * 0.5, 34, 0, Math.PI * 2);
        context.stroke();
      }
      context.restore();
    }

    const emphasized = new Set<number>();
    if (motifRef.current) {
      emphasized.add(atlas.motif.A);
      emphasized.add(atlas.motif.B);
      emphasized.add(atlas.motif.C);
    }
    if (selectedRef.current !== null) emphasized.add(selectedRef.current);

    for (const index of emphasized) {
      const item = atlas.items[index];
      const x =
        item.p[lowerOffset] +
        (item.p[upperOffset] - item.p[lowerOffset]) * mix;
      const y =
        item.p[lowerOffset + 1] +
        (item.p[upperOffset + 1] - item.p[lowerOffset + 1]) * mix;
      const screenX = (x / 10_000) * width;
      const screenY = (y / 10_000) * height;
      context.beginPath();
      context.arc(screenX, screenY, 6, 0, Math.PI * 2);
      context.strokeStyle = index === selectedRef.current ? "#ffffff" : "#e96f58";
      context.lineWidth = 1.5;
      context.stroke();
    }

    if (motifRef.current) {
      context.save();
      context.fillStyle = "#e96f58";
      context.font = "11px SFMono-Regular, Roboto Mono, monospace";
      context.textBaseline = "bottom";
      for (const [label, index] of Object.entries(atlas.motif) as [Label, number][]) {
        const item = atlas.items[index];
        const x =
          item.p[lowerOffset] +
          (item.p[upperOffset] - item.p[lowerOffset]) * mix;
        const y =
          item.p[lowerOffset + 1] +
          (item.p[upperOffset + 1] - item.p[lowerOffset + 1]) * mix;
        context.fillText(label, (x / 10_000) * width + 9, (y / 10_000) * height - 7);
      }
      context.restore();

      const focusX = Math.max(26, width * 0.07);
      const focusY = Math.max(72, height * 0.15);
      const focusWidth = Math.min(width * 0.72, 850);
      const focusHeight = Math.min(height * 0.62, 470);
      const aX = focusX + focusWidth * 0.28;
      const bcX = focusX + focusWidth * 0.72;
      const centerY = focusY + focusHeight * 0.55;
      context.save();
      context.globalAlpha = 0.98;
      context.fillStyle = "#10100e";
      context.fillRect(focusX, focusY, focusWidth, focusHeight);
      context.globalAlpha = 1;
      context.strokeStyle = "#5a574f";
      context.lineWidth = 1;
      context.strokeRect(focusX + 0.5, focusY + 0.5, focusWidth - 1, focusHeight - 1);
      context.fillStyle = "#e96f58";
      context.font = "10px SFMono-Regular, Roboto Mono, monospace";
      context.fillText("VALUE 0 CASE STUDY", focusX + 20, focusY + 26);

      for (const [x, radius] of [[aX, 66], [bcX, 80]] as const) {
        context.beginPath();
        context.arc(x, centerY, radius, 0, Math.PI * 2);
        context.strokeStyle = "rgba(245,240,228,.38)";
        context.stroke();
      }
      context.fillStyle = "#aaa69a";
      context.textAlign = "center";
      context.font = "11px SFMono-Regular, Roboto Mono, monospace";
      context.fillText("32 observed forms", aX, centerY + 94);
      context.fillText("54 observed forms", bcX, centerY + 108);

      const focusPoints = [
        { label: "A", x: aX, y: centerY },
        { label: "B", x: bcX - 18, y: centerY - 18 },
        { label: "C", x: bcX + 22, y: centerY + 20 },
      ];
      for (const point of focusPoints) {
        context.beginPath();
        context.arc(point.x, point.y, 6, 0, Math.PI * 2);
        context.fillStyle = point.label === "C" ? "#73b8bc" : "#d7b168";
        context.fill();
        context.fillStyle = "#f5f0e4";
        context.font = "12px SFMono-Regular, Roboto Mono, monospace";
        context.fillText(point.label, point.x, point.y - 13);
      }

      const arrow = (fromX: number, fromY: number, toX: number, toY: number) => {
        context.beginPath();
        context.moveTo(fromX, fromY);
        context.lineTo(toX, toY);
        context.strokeStyle = "#e96f58";
        context.stroke();
      };
      arrow(aX + 72, centerY, bcX - 32, centerY - 18);
      arrow(bcX - 11, centerY - 12, bcX + 14, centerY + 12);
      context.fillStyle = "#aaa69a";
      context.font = "9px SFMono-Regular, Roboto Mono, monospace";
      context.fillText("remove 2→3", (aX + bcX) / 2, centerY - 15);
      context.fillText("add 6→0", bcX + 54, centerY - 1);
      context.fillStyle = "#f5f0e4";
      context.font = "16px Iowan Old Style, Baskerville, serif";
      context.fillText("A: distinct complete game", aX, focusY + focusHeight - 22);
      context.fillText("B and C: same complete game", bcX, focusY + focusHeight - 22);
      context.restore();
    }

    if (layerValue > 1.58) {
      context.save();
      context.globalAlpha = Math.min(0.17, (layerValue - 1.58) * 0.42);
      context.fillStyle = "#f5f0e4";
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.font = `${Math.min(190, width * 0.14)}px Iowan Old Style, Baskerville, serif`;
      for (let target = 0; target < 3; target += 1) {
        context.fillText(atlas.targets[target].label, width * ((target * 2 + 1) / 6), height * 0.5);
      }
      context.restore();
    }
  }, [atlas]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(() => draw(layerValueRef.current));
    observer.observe(canvas);
    draw(layerValueRef.current);
    return () => observer.disconnect();
  }, [draw]);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (animationRef.current !== null) cancelAnimationFrame(animationRef.current);
    const startValue = layerValueRef.current;
    if (reduceMotion) {
      layerValueRef.current = layer;
      draw(layer);
      return;
    }
    const start = performance.now();
    const duration = 900;
    const frame = (time: number) => {
      const progress = Math.min(1, (time - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      layerValueRef.current = startValue + (layer - startValue) * eased;
      draw(layerValueRef.current);
      if (progress < 1) animationRef.current = requestAnimationFrame(frame);
    };
    animationRef.current = requestAnimationFrame(frame);
    return () => {
      if (animationRef.current !== null) cancelAnimationFrame(animationRef.current);
    };
  }, [layer, draw]);

  useEffect(() => {
    selectedRef.current = selectedIndex;
    motifRef.current = highlightMotif;
    draw(layerValueRef.current);
  }, [selectedIndex, highlightMotif, draw]);

  function pick(clientX: number, clientY: number) {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const pointerX = clientX - rect.left;
    const pointerY = clientY - rect.top;
    const layerValue = layerValueRef.current;
    if (Math.abs(layerValue - 1) < 0.34) {
      let nearestGroup: number | null = null;
      let nearestGroupDistance = 24 * 24;
      for (let index = 0; index < atlas.groups.length; index += 1) {
        const group = atlas.groups[index];
        const dx = (group.p[0] / 10_000) * rect.width - pointerX;
        const dy = (group.p[1] / 10_000) * rect.height - pointerY;
        const distance = dx * dx + dy * dy;
        const radius = Math.max(14, Math.min(24, 5 + Math.sqrt(group.c) * 1.15));
        if (distance <= radius * radius && distance < nearestGroupDistance) {
          nearestGroupDistance = distance;
          nearestGroup = index;
        }
      }
      if (nearestGroup !== null) return groupFirstItem[nearestGroup];
    }
    const lower = Math.min(1, Math.floor(layerValue));
    const upper = Math.min(2, lower + 1);
    const mix = layerValue - lower;
    let nearest: number | null = null;
    let nearestDistance = 15 * 15;
    for (let index = 0; index < atlas.items.length; index += 1) {
      const item = atlas.items[index];
      const x = item.p[lower * 2] + (item.p[upper * 2] - item.p[lower * 2]) * mix;
      const y =
        item.p[lower * 2 + 1] +
        (item.p[upper * 2 + 1] - item.p[lower * 2 + 1]) * mix;
      const dx = (x / 10_000) * rect.width - pointerX;
      const dy = (y / 10_000) * rect.height - pointerY;
      const distance = dx * dx + dy * dy;
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearest = index;
      }
    }
    return nearest;
  }

  function handleKeyDown(event: KeyboardEvent<HTMLCanvasElement>) {
    if (event.key === "Escape") {
      onSelect(null);
      return;
    }
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const current = selectedIndex ?? (direction === 1 ? -1 : 0);
    onSelect((current + direction + atlas.items.length) % atlas.items.length);
  }

  return (
    <canvas
      ref={canvasRef}
      className="atlas-canvas"
      role="img"
      tabIndex={0}
      aria-describedby="atlas-keyboard-help"
      aria-label={`${numberFormat.format(layerCounts[layer])} ${layerNames[layer].toLowerCase()} identities across the three target values. Select a mark to inspect a certified graph form.`}
      onClick={(event) => onSelect(pick(event.clientX, event.clientY))}
      onKeyDown={handleKeyDown}
    />
  );
}

function SpecimenPanel({
  atlas,
  selectedIndex,
  onSelect,
}: {
  atlas: AtlasData;
  selectedIndex: number | null;
  onSelect: (index: number | null) => void;
}) {
  const [compareGroup, setCompareGroup] = useState<number | null>(null);
  const selectedGroupIndex =
    selectedIndex === null ? -1 : atlas.items[selectedIndex].l;
  const groupMembers = useMemo(
    () =>
      selectedGroupIndex < 0
        ? []
        : atlas.items
            .map((item, index) => ({ item, index }))
            .filter(({ item }) => item.l === selectedGroupIndex)
            .map(({ index }) => index),
    [atlas, selectedGroupIndex],
  );

  if (selectedIndex === null) {
    const multiFormGroups = atlas.groups.filter((group) => group.c > 1);
    const largest = Math.max(...atlas.groups.map((group) => group.c));
    return (
      <aside className="specimen-panel empty" aria-label="Atlas guide">
        <p className="eyebrow">Observed multiplicity</p>
        <strong>{numberFormat.format(multiFormGroups.length)}</strong>
        <p>complete-game identities contain multiple graph quotients.</p>
        <div>
          <span>Largest equivalence class</span>
          <b>{largest} forms</b>
        </div>
        <p className="panel-hint">Select a mark. Arrow keys move between forms.</p>
      </aside>
    );
  }

  const item = atlas.items[selectedIndex];
  const group = atlas.groups[item.l];
  const currentMember = Math.max(0, groupMembers.indexOf(selectedIndex));
  const nextIndex = groupMembers[(currentMember + 1) % groupMembers.length];
  const comparisonItem = atlas.items[nextIndex];
  const compareOpen = compareGroup === selectedGroupIndex;
  return (
    <aside className="specimen-panel">
      <button className="panel-close" type="button" onClick={() => onSelect(null)}>
        Close
      </button>
      <p className="eyebrow">Certified form {selectedIndex + 1}</p>
      <DirectedGraph
        compact
        label={`value ${atlas.targets[item.t].label}`}
        name={`${item.a} directed arcs`}
        arcs={decodedArcs(item.g)}
        blueVertices={decodedBlue(item.m)}
      />
      <dl className="specimen-facts">
        <div><dt>Complete-game class</dt><dd>{numberFormat.format(group.c)} graph {group.c === 1 ? "form" : "forms"}</dd></div>
        <div><dt>Complete-game nodes</dt><dd>{item.n}</dd></div>
        <div><dt>Birthday</dt><dd>{item.b}</dd></div>
        <div><dt>Source event</dt><dd>{numberFormat.format(item.i)}</dd></div>
      </dl>
      <details className="hash-details">
        <summary>Technical identity</summary>
        <span>Graph quotient</span><code>{item.q}</code>
        <span>Complete game</span><code>{group.d}</code>
      </details>
      {groupMembers.length > 1 && (
        <div className="specimen-actions">
          <button type="button" onClick={() => onSelect(nextIndex)}>
            Next graph form
          </button>
          <button
            type="button"
            onClick={() => setCompareGroup(compareOpen ? null : selectedGroupIndex)}
          >
            {compareOpen ? "Close comparison" : "Compare graph forms"}
          </button>
        </div>
      )}
      {compareOpen && comparisonItem && (
        <div className="specimen-compare">
          <p>Both graph quotients map to the same complete game.</p>
          <DirectedGraph
            compact
            label={`form ${nextIndex + 1}`}
            name={`${comparisonItem.a} directed arcs`}
            arcs={decodedArcs(comparisonItem.g)}
            blueVertices={decodedBlue(comparisonItem.m)}
          />
        </div>
      )}
    </aside>
  );
}

function AtlasStage({
  atlas,
  error,
  onFindCrossing,
}: {
  atlas: AtlasData | null;
  error: boolean;
  onFindCrossing: () => void;
}) {
  const [layer, setLayer] = useState<Layer>(0);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [highlightMotif, setHighlightMotif] = useState(false);

  const currentCount = layerCounts[layer];
  const nextLayer = layer === 2 ? 0 : ((layer + 1) as Layer);
  const targetSummaries = atlas
    ? atlas.targets.map((target) => ({
        label: target.label,
        quotients: target.quotient_forms,
        literalGames: target.literal_games,
        graphArcRange: target.graph_arc_range,
        nodeRange: target.complete_game_node_range,
      }))
    : motif.atlas.targets.map((target) => ({
        label: target.label,
        quotients: target.quotients,
        literalGames: target.literal_games,
        graphArcRange: null,
        nodeRange: null,
      }));
  const multiFormGroups = atlas
    ? atlas.groups.filter((group) => group.c > 1).length
    : 2_402;
  const largestClass = atlas
    ? Math.max(...atlas.groups.map((group) => group.c))
    : 193;

  return (
    <section
      className="atlas-section"
      id="atlas"
      aria-labelledby="atlas-title"
      data-secondary-corpus-view
    >
      <header className="atlas-intro">
        <div>
          <p className="eyebrow">Secondary corpus overview</p>
          <h1 id="atlas-title">21,697 certified graph forms across three exact values.</h1>
        </div>
        <div className="atlas-context">
          <p>
            Each mark is a quotient-distinct order-7 graph recovered in the
            study. The controls group forms by recursive complete game and then
            by exact combinatorial value.
          </p>
          <aside className="corpus-summary-card" aria-label="Observed multiplicity summary">
            <div><strong>{numberFormat.format(multiFormGroups)}</strong><span>complete games with multiple observed graph forms</span></div>
            <div><strong>{largestClass}</strong><span>forms in the largest observed class</span></div>
          </aside>
          <div className="corpus-color-key" aria-label="Exact-value color key">
            <span><i style={{ background: atlasColors[0] }} /> value 0</span>
            <span><i style={{ background: atlasColors[1] }} /> value ∗</span>
            <span><i style={{ background: atlasColors[2] }} /> value 1/2</span>
          </div>
        </div>
      </header>

      <div className="atlas-shell">
        <div className="atlas-toolbar">
          <div className="layer-tabs" aria-label="Identity layer">
            {([0, 1, 2] as Layer[]).map((item) => (
              <button
                type="button"
                key={item}
                className={layer === item ? "active" : ""}
                aria-pressed={layer === item}
                onClick={() => {
                  setLayer(item);
                  setSelectedIndex(null);
                  setHighlightMotif(false);
                }}
              >
                <span>{layerNames[item]}</span>
                <strong>{numberFormat.format(layerCounts[item])}</strong>
              </button>
            ))}
          </div>
          <button
            type="button"
            className="compress-action"
            onClick={() => {
              setLayer(nextLayer);
              setSelectedIndex(null);
              setHighlightMotif(false);
            }}
          >
            {nextLayerActions[layer]}
            <span aria-hidden="true">→</span>
          </button>
        </div>

        <div className="atlas-view">
          <div className="target-labels" aria-hidden="true">
            {targetSummaries.map((target) => (
              <div key={target.label}>
                <strong>{target.label}</strong>
                <span>
                  {layer === 0
                    ? `${numberFormat.format(target.quotients)} forms`
                    : layer === 1
                      ? `${numberFormat.format(target.literalGames)} games`
                      : `one value · ${numberFormat.format(target.quotients)} forms`}
                </span>
                {layer === 0 && target.graphArcRange && target.nodeRange && (
                  <small>
                    {target.graphArcRange.join("–")} arcs · {target.nodeRange.join("–")} nodes
                  </small>
                )}
              </div>
            ))}
          </div>

          <p className="sr-only" id="atlas-keyboard-help">
            Select a mark to inspect it. With the canvas focused, use the Left
            and Right Arrow keys to move between forms and Escape to close the
            specimen. The layer controls and A, B, C case study provide shorter
            keyboard paths through the dataset.
          </p>

          {layer === 0 && (
            <>
              <div className="corpus-axis-y" aria-hidden="true">
                complete-game nodes · logarithmic scale
              </div>
              <div className="corpus-axis-x" aria-hidden="true">
                directed arcs →
              </div>
            </>
          )}

          {atlas ? (
            <>
              <AtlasCanvas
                atlas={atlas}
                layer={layer}
                selectedIndex={selectedIndex}
                onSelect={setSelectedIndex}
                highlightMotif={highlightMotif}
              />
              {selectedIndex !== null && (
                <SpecimenPanel
                  atlas={atlas}
                  selectedIndex={selectedIndex}
                  onSelect={setSelectedIndex}
                />
              )}
              <p className="sr-only" aria-live="polite">
                {selectedIndex === null
                  ? highlightMotif
                    ? "A is in a 32-form complete game. B and C are in one 54-form complete game. A to B removes arc 2 to 3. B to C adds arc 6 to 0."
                    : "No atlas specimen selected."
                  : `Selected certified form ${selectedIndex + 1}.`}
              </p>
            </>
          ) : (
            <div className="atlas-loading" role="status">
              {error ? (
                <p>The checked atlas could not be loaded.</p>
              ) : (
                <div className="loading-receipt">
                  <p>Loading the checked atlas</p>
                  <div aria-hidden="true">
                    <span><strong>21,697</strong><small>graph forms</small></span>
                    <b>→</b>
                    <span><strong>16,120</strong><small>complete games</small></span>
                    <b>→</b>
                    <span><strong>3</strong><small>exact values</small></span>
                  </div>
                  <small>Coordinates derived from the verified dataset · 5.3 MB</small>
                </div>
              )}
            </div>
          )}

          <div className="atlas-actions">
            <button
              type="button"
              onClick={() => {
                setLayer(1);
                setHighlightMotif((visible) => !visible);
                setSelectedIndex(null);
              }}
              disabled={!atlas}
            >
              {highlightMotif ? "Close case study" : "Show A, B, and C"}
            </button>
            <button type="button" onClick={onFindCrossing}>
              Open the case study <span aria-hidden="true">↓</span>
            </button>
          </div>
        </div>

        <footer className="atlas-legend">
          <p aria-live="polite">
            <strong>{numberFormat.format(currentCount)}</strong>{" "}
            {layer === 2
              ? "exact values · 21,697 forms represented"
              : `${layerNames[layer].toLowerCase()} identities shown`}
          </p>
          <p>
            {layer === 0
              ? "Horizontal position is directed-arc count. Vertical position is complete-game node count on a logarithmic scale. A small deterministic digest jitter separates coincident marks and has no semantic meaning."
              : layer === 1
                ? "Each outlined class is one complete game. Packing separates classes; distance does not encode similarity."
                : "The study examined three target values. Each mark still denotes one observed graph form."}
          </p>
        </footer>
      </div>
      <p className="claim-boundary">
        These counts describe the observed sample. The total number of representations for each value is unknown.
      </p>
    </section>
  );
}

function DagEdgeLine({
  from,
  to,
  player,
  coordinates,
}: {
  from: number;
  to: number;
  player: "L" | "R";
  coordinates: { x: number; y: number }[];
}) {
  const start = coordinates[from];
  const end = coordinates[to];
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const distance = Math.hypot(dx, dy);
  const angle = Math.atan2(dy, dx) * (180 / Math.PI);
  return (
    <span
      className={`dag-edge ${player === "L" ? "left" : "right"}`}
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

function LiteralDagFigure({ dag }: { dag: LiteralDag }) {
  const coordinates = useMemo(() => {
    const maxRank = Math.max(...dag.nodes.map((node) => node.r));
    return dag.nodes.map((node, index) => {
      const peers = dag.nodes
        .map((peer, peerIndex) => ({ peer, peerIndex }))
        .filter(({ peer }) => peer.r === node.r);
      const position = peers.findIndex(({ peerIndex }) => peerIndex === index);
      return {
        x: ((position + 1) / (peers.length + 1)) * 100,
        y: 10 + (node.r / Math.max(1, maxRank)) * 78,
      };
    });
  }, [dag]);

  return (
    <figure className="literal-dag">
      <figcaption>
        <span>One complete game</span>
        <strong>{dag.nodes.length} distinct option identities</strong>
      </figcaption>
      <div className="dag-field">
        {dag.edges.map((edge, index) => (
          <DagEdgeLine
            key={`${edge.f}-${edge.t}-${edge.p}-${index}`}
            from={edge.f}
            to={edge.t}
            player={edge.p}
            coordinates={coordinates}
          />
        ))}
        {dag.nodes.map((node, index) => (
          <span
            className={`dag-node${index === dag.root ? " root" : ""}`}
            key={node.d}
            style={
              {
                "--node-x": `${coordinates[index].x}%`,
                "--node-y": `${coordinates[index].y}%`,
              } as CSSProperties
            }
            title={node.s}
          >
            {index === dag.root ? "root" : `g${index}`}
          </span>
        ))}
      </div>
      <footer><span>Blue edge: Left option</span><span>Red edge: Right option</span></footer>
    </figure>
  );
}

function CrossingJourney({ atlas }: { atlas: AtlasData | null }) {
  const [step, setStep] = useState(0);
  const sectionRef = useRef<HTMLElement>(null);
  const A = getPosition("A");
  const B = getPosition("B");
  const C = getPosition("C");
  const bGroupCount = atlas ? atlas.groups[atlas.items[atlas.motif.B].l].c : 54;
  const aGroupCount = atlas ? atlas.groups[atlas.items[atlas.motif.A].l].c : 32;

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      setStep((current) => Math.min(4, current + 1));
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setStep((current) => Math.max(0, current - 1));
    }
  }

  return (
    <section
      className="crossing-journey"
      id="crossing"
      ref={sectionRef}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      aria-labelledby="crossing-title"
    >
      <header className="crossing-header">
        <div>
          <p className="eyebrow">Case study: value 0</p>
          <h2 id="crossing-title">Three graph forms, two complete games, one value</h2>
        </div>
        <div className="journey-progress" aria-label="Case-study steps">
          {Array.from({ length: 5 }, (_, index) => (
            <button
              type="button"
              className={step === index ? "active" : ""}
              aria-current={step === index ? "step" : undefined}
              onClick={() => setStep(index)}
              key={index}
            >
              {index + 1}
            </button>
          ))}
        </div>
      </header>

      <div className="journey-stage" aria-live="polite">
        {step === 0 && (
          <div className="inside-zero">
            <div><strong>7,555</strong><span>graph forms</span></div>
            <span aria-hidden="true">→</span>
            <div><strong>6,386</strong><span>complete games</span></div>
            <span aria-hidden="true">→</span>
            <div><strong>0</strong><span>exact value</span></div>
          </div>
        )}

        {step === 1 && (
          <div className="graph-comparison">
            <DirectedGraph label="Form A" name={A.name} arcs={A.arcs} blueVertices={A.blue_vertices} highlightedArc={[2, 3]} />
            <div className="change-column"><strong>remove</strong><code>2→3</code><span>the complete-game graph loses four nodes</span></div>
            <DirectedGraph label="Form B" name={B.name} arcs={B.arcs} blueVertices={B.blue_vertices} />
          </div>
        )}

        {step === 2 && (
          <div className="graph-comparison">
            <DirectedGraph label="Form B" name={B.name} arcs={B.arcs} blueVertices={B.blue_vertices} />
            <div className="change-column"><strong>add</strong><code>6→0</code><span>the complete-game digest is unchanged</span></div>
            <DirectedGraph label="Form C" name={C.name} arcs={C.arcs} blueVertices={C.blue_vertices} highlightedArc={[6, 0]} />
          </div>
        )}

        {step === 3 && (
          <div className="dag-collapse">
            <div className="surface-pair">
              <DirectedGraph compact label="B" name="21 arcs" arcs={B.arcs} blueVertices={B.blue_vertices} />
              <DirectedGraph compact label="C" name="22 arcs" arcs={C.arcs} blueVertices={C.blue_vertices} highlightedArc={[6, 0]} />
            </div>
            <div className="collapse-arrow"><span>identical complete-game digest</span><b aria-hidden="true">↓</b></div>
            {atlas && <LiteralDagFigure dag={atlas.motif_dags.B} />}
          </div>
        )}

        {step === 4 && (
          <div className="identity-result">
            <p>
              A, B, and C have the same exact value. Their graph quotients are
              pairwise distinct, and A maps to a different complete game from B and C.
            </p>
            <div className="island-result">
              <div><span>A’s complete game</span><strong>{aGroupCount} forms</strong></div>
              <div><span>B/C complete game</span><strong>{bGroupCount} forms</strong></div>
            </div>
            <div className="identity-equations">
              <code>q(A), q(B), q(C): pairwise distinct graph quotients</code>
              <code>ℓ(A) ≠ ℓ(B) = ℓ(C): two complete games</code>
              <code>v(A) = v(B) = v(C) = 0: one exact value</code>
            </div>
          </div>
        )}
      </div>

      <footer className="journey-controls">
        <div>
          <span>0{step + 1}</span>
          <p>
            {[
              "Value 0 contains 7,555 observed graph quotients and 6,386 complete games.",
              "Removing arc 2→3 maps A to a different complete game, B.",
              "Adding arc 6→0 maps B to graph form C without changing the complete game.",
              "B and C have the same complete-game directed acyclic graph.",
              "A, B, and C are distinct graph quotients with exact value 0.",
            ][step]}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setStep((current) => (current === 4 ? 0 : current + 1))}
        >
          {step === 4 ? "Restart" : "Next"} <span aria-hidden="true">→</span>
        </button>
      </footer>
    </section>
  );
}

function EvidenceLedger({ atlas }: { atlas: AtlasData | null }) {
  const [copyState, setCopyState] = useState("Copy verification record");

  async function copyAuthority() {
    if (!atlas) return;
    const record = {
      schema_version: "partizan.fixed_value_atlas.authority.v1",
      atlas_sha256: atlas.atlas_sha256,
      source: atlas.source,
      counts: atlas.counts,
      targets: atlas.targets,
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(record, null, 2));
      setCopyState("Copied");
    } catch {
      setCopyState("Copy failed");
    }
  }

  return (
    <section className="evidence-ledger" id="evidence" aria-labelledby="evidence-title">
      <header>
        <p className="eyebrow">Verification</p>
        <h2 id="evidence-title">The atlas is derived from the independently replayed event ledger.</h2>
      </header>
      <div className="ledger-grid">
        <div><strong>73,728</strong><span>source proposals</span></div>
        <div><strong>21,697</strong><span>quotient-unique forms</span></div>
        <div><strong>16,120</strong><span>complete-game identities</span></div>
        <div><strong>{atlas?.source.negative_test_families_rejected ?? "pending"}</strong><span>corruption families rejected</span></div>
      </div>
      <div className="ledger-notes">
        <p>
          Partizan proposes graph forms. The exact verifier computes the
          combinatorial-game value of each proposal. This interface lets the
          reader inspect the certified results at three levels of identity.
        </p>
        <p>
          Stiller used computation to locate an endgame kernel, and Elkies
          recomposed it as a chess study. That history motivates the workflow
          used here: machine search enumerates certified possibilities, and a
          person selects the representation.
        </p>
        <p>
          The reported results concern structural novelty and certified
          equality. Aesthetic preference was not evaluated.
        </p>
      </div>
      <div className="ledger-actions">
        <button
          type="button"
          onClick={copyAuthority}
          disabled={!atlas}
          title="Copies the atlas hash, source hashes, counts, and target definitions."
        >
          {copyState}
        </button>
        <a href={elkies.source.url} target="_blank" rel="noreferrer">Historical source</a>
        <a href="https://github.com/devinnicholson/partizan" target="_blank" rel="noreferrer">Source code</a>
      </div>
    </section>
  );
}

export function PartizanExperience() {
  const [atlas, setAtlas] = useState<AtlasData | null>(null);
  const [atlasError, setAtlasError] = useState(false);

  useEffect(() => {
    const basePath = process.env.NEXT_PUBLIC_PARTIZAN_BASE_PATH ?? "";
    fetch(`${basePath}/evidence/fixed-value-atlas.json.gz`)
      .then((response) => {
        if (!response.ok) throw new Error("atlas request failed");
        if (!response.body || typeof DecompressionStream === "undefined") {
          throw new Error("gzip decoding is unavailable");
        }
        const decoded = response.body.pipeThrough(
          new DecompressionStream("gzip"),
        );
        return new Response(decoded).json() as Promise<AtlasData>;
      })
      .then((data) => {
        if (
          data.counts.quotient_forms !== 21_697 ||
          data.counts.literal_games !== 16_120 ||
          data.counts.exact_values !== 3
        ) {
          throw new Error("atlas evidence count mismatch");
        }
        setAtlas(data);
      })
      .catch(() => setAtlasError(true));
  }, []);

  function findCrossing() {
    const crossing = document.getElementById("crossing");
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    crossing?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" });
    window.setTimeout(() => crossing?.focus(), reduceMotion ? 0 : 450);
  }

  return (
    <main className="experience" id="top">
      <header className="masthead">
        <a className="wordmark" href="#top">Partizan</a>
        <span>One value, many forms</span>
        <nav aria-label="Page links">
          <a href="#class">Class</a>
          <a href="#neighborhood">Neighborhood</a>
          <a href="#atlas">Corpus</a>
          <a href="#crossing">Case study</a>
          <a href="#evidence">Verification</a>
        </nav>
      </header>

      <FiberClass atlas={atlas} error={atlasError} />
      <AtlasStage atlas={atlas} error={atlasError} onFindCrossing={findCrossing} />
      <CrossingJourney atlas={atlas} />
      <EvidenceLedger atlas={atlas} />

      <footer className="footer">
        <span>Independent replay: passed</span>
        <span>completion {shortHash(motif.completion_sha256)}</span>
      </footer>
    </main>
  );
}
