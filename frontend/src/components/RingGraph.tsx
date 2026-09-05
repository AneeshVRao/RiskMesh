import { useMemo } from "react";
import type { RingGraphData, GraphNode } from "../api/types";

// Ported from mockups/api.js's renderGraph() (around line 193). Same column
// math, same edge-curve formula, same accessible alt text -- deliberately not
// reimplemented as "a React version" with different layout choices, and no
// graph-visualization library was added: this is exactly the kind of small,
// auditable rendering riskmesh/graph.py's own docstring argues for over a
// heavy dependency (union-find vs. networkx).
//
// Three columns, left to right: shared attributes -> accounts -> merchants.
// Layout is arithmetic, not a force simulation, so identical input always
// gives an identical picture -- checkable against the API like every other
// number on screen.

const KIND: Record<string, { color: string; op: number; w: number }> = {
  device: { color: "#d81f26", op: 0.9, w: 1.6 },
  instrument: { color: "#a8171d", op: 0.9, w: 1.6 },
  ip: { color: "#8f5400", op: 0.75, w: 1.2 },
  merchant: { color: "#5c6670", op: 0.22, w: 0.8 },
};
const COLUMN: Record<string, number> = { device: 0, instrument: 1, ip: 2 };
const G = {
  BW: 88,
  BH: 20,
  PITCH: 26,
  TOP: 28,
  PAD: 12,
  W: 470,
  X: { left: 4, mid: 191, right: 378 },
};

const byId = (a: { id: string }, b: { id: string }) => (a.id < b.id ? -1 : 1);

function merchants(g: RingGraphData): GraphNode[] {
  return g.nodes
    .filter((n) => n.type === "merchant")
    .sort((a, b) => b.degree - a.degree || byId(a, b));
}

function shared(g: RingGraphData): GraphNode[] {
  return g.nodes
    .filter((n) => n.type !== "merchant")
    .sort((a, b) => COLUMN[a.type] - COLUMN[b.type] || b.degree - a.degree || byId(a, b));
}

interface Pos {
  x: number;
  y: number;
  cy: number;
}

export function graphCaption(ev: { graph: RingGraphData }): string {
  const g = ev.graph;
  const n = g.accounts.length;
  const top = [...shared(g)].sort((a, b) => b.degree - a.degree)[0];
  const m = merchants(g)[0];
  const out = [`${n} accounts · ${g.nodes.length} shared nodes · ${g.edges.length} links.`];
  if (top) {
    out.push(`Strongest link: ${top.type} ${top.id} on ${top.degree} of ${n} accounts.`);
  }
  if (m) out.push(`Busiest merchant ${m.id} takes ${m.degree}.`);
  out.push(
    "Only attributes shared by two or more accounts are drawn, capped infrastructure " +
      "(ip_nat*) included. The ip_sharing signal skips capped IPs, so the node count " +
      "here is not the signal.",
  );
  return out.join(" ");
}

export function RingGraph({ componentId, graph }: { componentId: string; graph: RingGraphData }) {
  const built = useMemo(() => {
    const g = graph;
    const left = shared(g);
    const right = merchants(g);
    const accts = g.accounts;
    // Floor the row count so the panel does not resize under the cursor while
    // an analyst clicks down the queue.
    const rows = Math.max(left.length, accts.length, right.length, 9);
    const H = G.TOP + rows * G.PITCH + G.PAD;

    const P = new Map<string, Pos>();
    const lay = (items: (string | GraphNode)[], x: number) => {
      const top = G.TOP + ((rows - items.length) * G.PITCH) / 2;
      items.forEach((it, i) => {
        const y = top + i * G.PITCH;
        const id = typeof it === "string" ? it : it.id;
        P.set(id, { x, y, cy: y + G.BH / 2 });
      });
    };
    lay(left, G.X.left);
    lay(accts, G.X.mid);
    lay(right, G.X.right);

    const maxTxn = g.edges.reduce((m, e) => Math.max(m, e.txns), 1);
    const wires = g.edges.map((e, i) => {
      const k = KIND[e.kind] || KIND.merchant;
      const a = P.get(e.account);
      const n = P.get(e.node);
      if (!a || !n) return null;
      const [s, t] = e.kind === "merchant" ? [a, n] : [n, a];
      const x1 = s.x + G.BW;
      const x2 = t.x;
      const m = (x1 + x2) / 2;
      const w = (k.w * (0.5 + 0.5 * (e.txns / maxTxn))).toFixed(2);
      return (
        <path
          key={i}
          d={`M${x1} ${s.cy}C${m} ${s.cy} ${m} ${t.cy} ${x2} ${t.cy}`}
          fill="none"
          stroke={k.color}
          strokeWidth={w}
          opacity={k.op}
        />
      );
    });

    const box = (id: string, stroke: string, label: string, heavy: boolean, key: string) => {
      const p = P.get(id);
      if (!p) return null;
      return (
        <g key={key}>
          <rect
            x={p.x}
            y={p.y}
            width={G.BW}
            height={G.BH}
            fill="#fff"
            stroke={stroke}
            strokeWidth={heavy ? 1.8 : 1.2}
          />
          <text
            x={p.x + G.BW / 2}
            y={p.y + 14}
            textAnchor="middle"
            fontFamily="ui-monospace,monospace"
            fontSize={11}
            fill="#111418"
          >
            {label}
          </text>
        </g>
      );
    };

    const boxes = [
      ...left.map((n) => box(n.id, KIND[n.type].color, `${n.id} ×${n.degree}`, n.degree === accts.length, `l-${n.id}`)),
      ...accts.map((a) => box(a, "#767d87", a, false, `a-${a}`)),
      ...right.map((n) => box(n.id, KIND.merchant.color, `${n.id} ×${n.degree}`, false, `r-${n.id}`)),
    ];

    const head = (x: number, t: string, n: number) =>
      n ? (
        <text key={t} x={x} y={15} fontFamily="ui-monospace,monospace" fontSize={10} fill="#767d87">
          {t}
        </text>
      ) : null;
    const heads = [
      head(G.X.left, "SHARED ATTRIBUTES", left.length),
      head(G.X.mid, "ACCOUNTS", accts.length),
      head(G.X.right, "MERCHANTS", right.length),
    ];

    const top = left[0];
    const alt =
      `Component ${componentId}: ${accts.length} accounts, ${left.length} shared ` +
      `attribute nodes, ${right.length} merchants, ${g.edges.length} links. ` +
      (top
        ? `Most shared: ${top.type} ${top.id}, on ${top.degree} of ${accts.length} accounts.`
        : "No shared attributes.");

    return { H, wires, boxes, heads, alt };
  }, [componentId, graph]);

  if (!graph || graph.accounts.length === 0) {
    return <p className="p-4 text-sm text-ink-3">No graph structure for this component.</p>;
  }

  return (
    <svg
      className="block w-full h-auto"
      viewBox={`0 0 ${G.W} ${built.H}`}
      role="img"
      aria-label={built.alt}
    >
      {built.heads}
      {built.wires}
      {built.boxes}
    </svg>
  );
}
