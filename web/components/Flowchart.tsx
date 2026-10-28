"use client";

import dagre from "@dagrejs/dagre";
import { Background, BackgroundVariant, Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { useMemo, useState } from "react";
import { fmtDate, Item, ManagerState } from "@/lib/api";

const W = 192;
const H = 84;
const CAP = 7;
const RANK: Record<string, number> = { red: 0, orange: 1, grey: 2, green: 3 };

type TaskData = { item: Item; onOpen: (i: Item) => void; delay?: number; absorbed?: boolean; origin?: boolean };
export type GraphPreview = { origin: string; delays: Record<string, number>; absorbed: Record<string, number> } | null;
type MoreData = { count: number; onExpand: () => void };

export function statusLabel(i: Item) {
  if (i.status === "done") return "Done";
  if (i.status === "blocked") return "Blocked";
  if (i.overdue) return "Overdue";
  if (i.at_risk) return "At risk";
  if (i.review_state === "needs_review") return "Needs review";
  if (i.status === "in_progress") return "In progress";
  return "Pending";
}

function TaskNode({ data }: NodeProps<Node<TaskData>>) {
  const i = data.item;
  const label = data.delay ? `${data.origin ? "Slips" : "Late"} +${data.delay}d` : data.absorbed ? "Absorbed" : statusLabel(i);
  const color = data.delay ? "red" : data.absorbed ? "green" : i.color;
  return (
    <button className={`node node-${color}${data.delay !== undefined || data.absorbed ? " node-whatif" : ""}`} onClick={() => data.onOpen(i)}
            aria-label={`${i.text}. ${i.owner ?? "Owner unknown"}. ${label}. Show source`}>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div className="strip" />
      <div className="body">
        <div className="meta"><span>{i.team ?? "No team"}</span><span className="st">{label}</span></div>
        <div className="name">{i.text}</div>
        <div className="who">{i.owner ?? <span className="unknown">Owner unknown</span>}{" · "}
          {i.deadline_date ? fmtDate(i.deadline_date) : i.deadline_status === "after_dependency" ? "after dependency" : <span className="unknown">no date</span>}
        </div>
      </div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </button>
  );
}

function MoreNode({ data }: NodeProps<Node<MoreData>>) {
  return (
    <button className="node node-more" onClick={data.onExpand}>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      + {data.count} more tasks
    </button>
  );
}

const nodeTypes = { task: TaskNode, more: MoreNode };

export default function Flowchart({ graph, onOpen, preview = null }: { graph: ManagerState["graph"]; onOpen: (i: Item) => void; preview?: GraphPreview }) {
  const [expanded, setExpanded] = useState(false);

  const { nodes, edges, hidden } = useMemo(() => {
    const all = graph.nodes;
    const linked = new Set(graph.edges.flatMap((e) => [e.source, e.target]));
    const ordered = [...all].sort((a, b) => (RANK[a.color] - RANK[b.color]) || (Number(linked.has(b.id)) - Number(linked.has(a.id))));
    const shown = expanded || all.length <= CAP ? all : ordered.slice(0, CAP - 1);
    const ids = new Set(shown.map((n) => n.id));
    const hidden = all.length - shown.length;

    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: "LR", nodesep: 22, ranksep: 46, marginx: 10, marginy: 10 });
    g.setDefaultEdgeLabel(() => ({}));
    shown.forEach((n) => g.setNode(n.id, { width: W, height: H }));
    if (hidden > 0) g.setNode("__more", { width: W, height: 48 });
    const es = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    es.forEach((e) => g.setEdge(e.source, e.target));
    dagre.layout(g);

    const nodes: Node[] = shown.map((n) => {
      const p = g.node(n.id);
      const data: TaskData = { item: n, onOpen, delay: preview?.delays[n.id], absorbed: preview ? n.id in preview.absorbed : false,
                               origin: preview?.origin === n.id };
      return { id: n.id, type: "task", position: { x: p.x - W / 2, y: p.y - H / 2 }, data };
    });
    if (hidden > 0) {
      const p = g.node("__more");
      nodes.push({ id: "__more", type: "more", position: { x: p.x - W / 2, y: p.y - 24 }, data: { count: hidden, onExpand: () => setExpanded(true) } });
    }
    const edges: Edge[] = es.map((e) => {
      const hot = preview ? Boolean(preview.delays[e.target]) : e.blocked;
      return {
        id: `${e.source}->${e.target}`, source: e.source, target: e.target, animated: hot, type: "smoothstep",
        style: { stroke: hot ? "#b91c1c" : "#94a3b8", strokeWidth: hot ? 2 : 1.4 },
        markerEnd: { type: MarkerType.ArrowClosed, color: hot ? "#b91c1c" : "#94a3b8", width: 16, height: 16 },
      };
    });
    return { nodes, edges, hidden };
  }, [graph, expanded, onOpen, preview]);

  if (graph.nodes.length === 0) {
    return <div className="flow" style={{ display: "grid", placeItems: "center" }}><div className="empty">No tasks yet. Add a meeting to draw the dependency graph.</div></div>;
  }
  return (
    <>
      <div className="flow">
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.08, maxZoom: 1.05, minZoom: 0.7 }} minZoom={0.5}
                   nodesDraggable={false} nodesConnectable={false} zoomOnScroll={false} preventScrolling={false} zoomOnDoubleClick={false} proOptions={{ hideAttribution: true }}>
          <Background variant={BackgroundVariant.Dots} color="#d5dde6" gap={18} size={1} />
          <Controls showInteractive={false} position="bottom-right" />
        </ReactFlow>
      </div>
      {(expanded && graph.nodes.length > CAP) && <div className="card-foot"><button className="link" onClick={() => setExpanded(false)}>Show fewer</button></div>}
      {hidden > 0 && <span className="sr-only">{hidden} tasks hidden</span>}
    </>
  );
}

export function Legend() {
  return (
    <div className="legend small">
      <span className="status s-grey"><i />Pending</span>
      <span className="status s-orange"><i />Attention</span>
      <span className="status s-red"><i />Blocked</span>
      <span className="status s-green"><i />Done</span>
    </div>
  );
}
