"""
Graph Renderer — [GRAPH: ...] syntax to PNG using networkx + matplotlib

Parses a compact graph description emitted by the LLM and renders it as a
labelled diagram that can be embedded inline in a ReportLab PDF.

Supported syntax (LLM writes this inside question_text):

    [GRAPH: nodes=A,B,C,D  edges=A-B:4,B-C:2,A-C:7,C-D:1  directed=false  layout=spring]

Fields (all optional except edges):
  nodes           — comma-separated node names; inferred from edges if omitted
  edges           — comma-separated EDGE specs:
                    unweighted  →  A-B  or  A->B
                    weighted    →  A-B:4  or  A->B:4
  directed        — true | false (default false)
  layout          — spring | circular | shell | kamada_kawai | spectral (default spring)
  highlight       — comma-separated NODES to draw in a different colour (e.g. path endpoints)
  highlight_edges — comma-separated EDGES to draw highlighted (e.g. Eulerian trail edges):
                    format same as edges but without weights: A-B,B-C,C-D  or A->B,B->C
  show_degrees    — true | false  (default false): annotate each node with its degree;
                    useful for Eulerian path questions so students can count odd-degree vertices
  title           — optional caption printed below the graph

The rendered PNG path + dimensions (in ReportLab points) are returned so the
caller can embed an <img> tag or an RLImage.
"""

import logging
import re
import tempfile
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Matches [GRAPH: ...] (possibly spanning multiple lines inside the brackets)
GRAPH_TAG = re.compile(r'\[GRAPH:\s*(.*?)\]', re.DOTALL | re.IGNORECASE)


# ─── Parsing ────────────────────────────────────────────────────────────────

def _parse_graph_tag(spec: str) -> Dict:
    """
    Parse the key=value pairs inside [GRAPH: ...].
    Returns a dict with keys: nodes, edges, directed, layout, highlight, title.
    """
    spec = spec.strip().replace('\n', ' ')

    def _get(key: str, default: str = "") -> str:
        m = re.search(rf'\b{key}\s*=\s*([^\s]+(?:\s+[^\s=]+)*?)(?=\s+\w+=|\s*$)', spec, re.IGNORECASE)
        return m.group(1).strip() if m else default

    nodes_str       = _get("nodes")
    edges_str       = _get("edges")
    directed        = _get("directed", "false").lower() in ("true", "yes", "1")
    layout          = _get("layout", "spring").lower()
    highlight       = _get("highlight")
    highlight_edges = _get("highlight_edges")
    show_degrees    = _get("show_degrees", "false").lower() in ("true", "yes", "1")
    title           = _get("title")

    def _parse_edge_list(s: str) -> List[Tuple]:
        result = []
        for raw in re.split(r'[,;]\s*', s):
            raw = raw.strip()
            if not raw:
                continue
            m = re.match(r'(\w+)\s*[-–>]+\s*(\w+)\s*[:]?\s*([\d.]+)?', raw)
            if m:
                u, v, w = m.group(1), m.group(2), m.group(3)
                result.append((u, v, float(w) if w else None))
        return result

    edges: List[Tuple] = _parse_edge_list(edges_str)

    # highlight_edges: same format but weights ignored
    h_edges: List[Tuple] = [(u, v, None) for u, v, _ in _parse_edge_list(highlight_edges)] if highlight_edges else []

    # Parse node list (optional override)
    explicit_nodes: List[str] = [n.strip() for n in nodes_str.split(',') if n.strip()] if nodes_str else []
    highlighted: List[str] = [n.strip() for n in highlight.split(',') if n.strip()] if highlight else []

    return {
        "explicit_nodes": explicit_nodes,
        "edges": edges,
        "directed": directed,
        "layout": layout,
        "highlighted": highlighted,
        "highlight_edges": h_edges,
        "show_degrees": show_degrees,
        "title": title,
    }


# ─── Rendering ──────────────────────────────────────────────────────────────

def render_graph_to_png(
    spec: str,
    figsize: Tuple[float, float] = (5.0, 3.5),
    dpi: int = 130,
) -> Optional[Tuple[str, float, float]]:
    """
    Parse spec and render a graph to a temp PNG.

    Args:
        spec:    The raw text inside [GRAPH: ...]
        figsize: Matplotlib figure size in inches
        dpi:     Render resolution

    Returns:
        (png_path, width_pts, height_pts) or None on failure.
        Dimensions in ReportLab points (72 pts/inch).
    """
    try:
        import networkx as nx
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError as e:
        log.warning("graph_renderer: missing library — %s", e)
        return None

    try:
        parsed = _parse_graph_tag(spec)
        edges            = parsed["edges"]
        directed         = parsed["directed"]
        layout           = parsed["layout"]
        highlighted      = set(parsed["highlighted"])
        h_edges_list     = parsed["highlight_edges"]   # [(u,v,None), ...]
        show_degrees     = parsed["show_degrees"]
        title            = parsed["title"]

        G = nx.DiGraph() if directed else nx.Graph()

        for node in parsed["explicit_nodes"]:
            G.add_node(node)

        has_weights = False
        for u, v, w in edges:
            if w is not None:
                G.add_edge(u, v, weight=w)
                has_weights = True
            else:
                G.add_edge(u, v)

        if G.number_of_nodes() == 0:
            log.warning("graph_renderer: no nodes parsed from spec=%r", spec[:80])
            return None

        # Separate edges into normal vs highlighted
        h_edge_set = set()
        for u, v, _ in h_edges_list:
            h_edge_set.add((u, v))
            if not directed:
                h_edge_set.add((v, u))  # undirected: both directions

        normal_edges     = [(u, v) for u, v in G.edges() if (u, v) not in h_edge_set]
        highlight_edges_draw = [(u, v) for u, v in G.edges() if (u, v) in h_edge_set]

        # Choose layout
        layout_fns = {
            "spring":       lambda g: nx.spring_layout(g, seed=42, k=2.0),
            "circular":     nx.circular_layout,
            "shell":        nx.shell_layout,
            "spectral":     nx.spectral_layout,
            "kamada_kawai": nx.kamada_kawai_layout,
        }
        layout_fn = layout_fns.get(layout, layout_fns["spring"])
        try:
            pos = layout_fn(G)
        except Exception:
            pos = nx.spring_layout(G, seed=42)

        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        # Node colours — red for highlighted endpoints, blue otherwise
        node_list = list(G.nodes())
        node_colors = [
            "#FF6B6B" if n in highlighted else "#4A90D9"
            for n in node_list
        ]

        nx.draw_networkx_nodes(
            G, pos,
            nodelist=node_list,
            node_color=node_colors,
            node_size=700,
            ax=ax,
        )

        # Node labels: show degree in parentheses if show_degrees=true
        if show_degrees:
            # For undirected, degree; for directed, show in-degree/out-degree
            if directed:
                node_labels = {n: f"{n}\n({G.in_degree(n)},{G.out_degree(n)})" for n in G.nodes()}
            else:
                node_labels = {n: f"{n}\n(d={G.degree(n)})" for n in G.nodes()}
        else:
            node_labels = {n: str(n) for n in G.nodes()}

        nx.draw_networkx_labels(
            G, pos,
            labels=node_labels,
            font_size=9 if show_degrees else 10,
            font_color="white",
            font_weight="bold",
            ax=ax,
        )

        # Draw normal edges
        common_opts = dict(ax=ax)
        if directed:
            common_opts.update(arrows=True, arrowstyle="-|>", arrowsize=18,
                               connectionstyle="arc3,rad=0.1")
        else:
            common_opts["arrows"] = False

        if normal_edges:
            nx.draw_networkx_edges(
                G, pos,
                edgelist=normal_edges,
                edge_color="#555555",
                width=1.8,
                **common_opts,
            )

        # Draw highlighted edges (Eulerian trail / path) in orange, thicker
        if highlight_edges_draw:
            nx.draw_networkx_edges(
                G, pos,
                edgelist=highlight_edges_draw,
                edge_color="#E8720C",
                width=3.5,
                style="solid",
                **common_opts,
            )

        # Edge weight labels
        if has_weights:
            edge_labels = {
                (u, v): (f"{d['weight']:.4g}" if isinstance(d.get("weight"), float) and d["weight"] != int(d["weight"]) else str(int(d["weight"])))
                for u, v, d in G.edges(data=True)
                if "weight" in d
            }
            nx.draw_networkx_edge_labels(
                G, pos,
                edge_labels=edge_labels,
                font_size=8,
                font_color="#222222",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.7),
                ax=ax,
            )

        if title:
            ax.set_title(title, fontsize=9, pad=4)

        ax.axis("off")
        plt.tight_layout(pad=0.3)

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp_path = tmp.name
        tmp.close()
        fig.savefig(tmp_path, dpi=dpi, bbox_inches="tight", facecolor="white")
        plt.close(fig)

        width_pts  = figsize[0] * 72
        height_pts = figsize[1] * 72

        return tmp_path, width_pts, height_pts

    except Exception as exc:
        log.warning("graph_renderer: render failed — %s", exc)
        try:
            import matplotlib.pyplot as plt
            plt.close("all")
        except Exception:
            pass
        return None


def has_graph_tag(text: str) -> bool:
    """Return True if text contains a [GRAPH: ...] tag."""
    return bool(GRAPH_TAG.search(text))


def extract_graph_tags(text: str) -> List[Dict]:
    """
    Split text into plain-text spans and graph spans.

    Returns a list of dicts:
      {"type": "text",  "content": "Find shortest path in this graph:"}
      {"type": "graph", "spec": "nodes=A,B edges=A-B:4 directed=false", "raw": "[GRAPH: ...]"}
      {"type": "text",  "content": " using Dijkstra's algorithm."}
    """
    spans = []
    last_end = 0
    for match in GRAPH_TAG.finditer(text):
        start, end = match.start(), match.end()
        if start > last_end:
            spans.append({"type": "text", "content": text[last_end:start]})
        spans.append({"type": "graph", "spec": match.group(1), "raw": match.group(0)})
        last_end = end
    if last_end < len(text):
        spans.append({"type": "text", "content": text[last_end:]})
    return spans if spans else [{"type": "text", "content": text}]
