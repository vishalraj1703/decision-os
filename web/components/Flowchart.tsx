"use client";

import dagre from "@dagrejs/dagre";
import { Background, Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { useMemo, useState } from "react";
import { Item, ManagerState } from "@/lib/api";

const W = 214;
const H = 92;
const CAP = 7;
const RANK: Record<string, number> = { red: 0, orange: 1, grey: 2, green: 3 };

type TaskData = { item: Item; onOpen: (i: Item) => void };
type MoreData = { count: number; onExpand: () => void };

function TaskNode({ data }: NodeProps<Node<TaskData>>) {
  const i = data.item;
  const label = i.status === "done" ? "complete" : i.status === "blocked" ? "blocked" : i.overdue ? "overdue"
    : i.at_risk ? "at risk" : i.review_state === "needs_review" ? "needs review" : "pending";
  return (
    <button className={`node node-${i.color}`} onClick={() => data.onOpen(i)} aria-label={`${i.text}, ${i.owner ?? "owner unknown"}, ${label}. Show evidence`}>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div className="team">{i.team ?? "No team"} · {label}</div>
      <div className="task">{i.text}</div>
      <div className="muted">{i.owner ?? "UNKNOWN"} · {i.deadline_date ? i.deadline_text : "unknown"}</div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </button>
  );
}

function MoreNode({ data }: NodeProps<Node<MoreData>>) {
  return (
    <button className="node node-more" onClick={data.onExpand}>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      and {data.count} more
      <div className="faint" style={{ fontSize: 11 }}>click to expand</div>
    </button>
  );
}

const nodeTypes = { task: TaskNode, more: MoreNode };

export default function Flowchart({ graph, onOpen }: { graph: ManagerState["graph"]; onOpen: (i: Item) => void }) {
  const [expanded, setExpanded] = useState(false);

  const { nodes, edges } = useMemo(() => {
    const all = graph.nodes;
    // Keep the most important nodes visible: problems first, then anything that is part of a chain.
    const linked = new Set(graph.edges.flatMap((e) => [e.source, e.target]));
    const ordered = [...all].sort((a, b) => (RANK[a.color] - RANK[b.color]) || (Number(linked.has(b.id)) - Number(linked.has(a.id))));
    const shown = expanded || all.length <= CAP ? all : ordered.slice(0, CAP - 1);
    const shownIds = new Set(shown.map((n) => n.id));
    const hidden = all.length - shown.length;

    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: "LR", nodesep: 26, ranksep: 70 });
    g.setDefaultEdgeLabel(() => ({}));
    shown.forEach((n) => g.setNode(n.id, { width: W, height: H }));
    if (hidden > 0) g.setNode("__more", { width: W, height: 60 });
    const es = graph.edges.filter((e) => shownIds.has(e.source) && shownIds.has(e.target));
    es.forEach((e) => g.setEdge(e.source, e.target));
    dagre.layout(g);

    const nodes: Node[] = shown.map((n) => {
      const p = g.node(n.id);
      return { id: n.id, type: "task", position: { x: p.x - W / 2, y: p.y - H / 2 }, data: { item: n, onOpen } };
    });
    if (hidden > 0) {
      const p = g.node("__more");
      nodes.push({ id: "__more", type: "more", position: { x: p.x - W / 2, y: p.y - 30 }, data: { count: hidden, onExpand: () => setExpanded(true) } });
    }
    const edges: Edge[] = es.map((e) => ({
      id: `${e.source}->${e.target}`, source: e.source, target: e.target, animated: e.blocked,
      style: { stroke: e.blocked ? "var(--red)" : "#5b6b7b", strokeWidth: e.blocked ? 2.5 : 1.6 },
      markerEnd: { type: MarkerType.ArrowClosed, color: e.blocked ? "#e5534b" : "#5b6b7b" },
    }));
    return { nodes, edges };
  }, [graph, expanded, onOpen]);

  if (graph.nodes.length === 0) {
    return <div className="flow" style={{ display: "grid", placeItems: "center" }}><span className="muted">No tasks yet. Extract a meeting to draw the dependency graph.</span></div>;
  }
  return (
    <div>
      <div className="flow">
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.2 }}
                   nodesDraggable={false} nodesConnectable={false} proOptions={{ hideAttribution: true }} colorMode="dark">
          <Background color="#1c2834" gap={22} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <div className="legend">
        <span><i className="dot dot-grey" />pending</span><span><i className="dot dot-orange" />attention / at risk</span>
        <span><i className="dot dot-red" />blocked / overdue</span><span><i className="dot dot-green" />complete</span>
        {expanded && graph.nodes.length > CAP && <button className="btn-link" onClick={() => setExpanded(false)}>collapse</button>}
      </div>
    </div>
  );
}
