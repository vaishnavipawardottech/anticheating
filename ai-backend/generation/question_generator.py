"""
Step 4 — Question Generation Engine

Generates one exam question per QuestionSpec using OpenAI GPT.
Supports two generation modes:
  - "mcq"        → 4 options (A/B/C/D) with correct answer labelled
  - "descriptive" → full question + answer key + marking scheme

Output: GeneratedQuestion with all fields populated correctly.
"""

import json
import re
from typing import List, Optional

from database.models import DocumentChunk
from generation.schemas import QuestionSpec, GeneratedQuestion, MarkingPoint, MCQOption


# ─── MCQ Generation Prompt ─────────────────────────────────────────────────────

MCQ_PROMPT = """You are an expert university exam question setter.

Generate exactly ONE Multiple Choice Question (MCQ) based on the specifications below.

SPECIFICATIONS:
- Bloom's Level: {bloom_target}
- Marks: {marks}
- Difficulty: {difficulty}
- Topic Nature: {nature}
- Target Units: {units}

CONTEXT (use ONLY information from these chunks; do NOT copy text verbatim):
---
{context_text}
---

OUTPUT FORMAT — respond with ONLY a valid JSON object, no markdown, no explanation:
{{
  "question_text": "<clear, unambiguous MCQ question stem>",
  "bloom_level": "<remember|understand|apply|analyze|evaluate|create>",
  "difficulty": "<easy|medium|hard>",
  "marks": {marks},
  "options": [
    {{"label": "A", "text": "<option text>"}},
    {{"label": "B", "text": "<option text>"}},
    {{"label": "C", "text": "<option text>"}},
    {{"label": "D", "text": "<option text>"}}
  ],
  "answer_key": "<A|B|C|D>",
  "explanation": "<brief explanation of why the answer is correct>",
  "source_chunk_ids": [<chunk_id>, ...]
}}

RULES:
1. The question stem must be complete and self-sufficient — no dangling context
2. All 4 options must be plausible — distractors should be common misconceptions or close alternatives
3. Exactly ONE option must be clearly correct based on the context
4. Do NOT use "All of the above" or "None of the above"
5. Do NOT copy chunk text verbatim
6. source_chunk_ids: list IDs of chunks supporting the answer
7. **MATH**: For any mathematical expressions use LaTeX: inline as \\( ... \\) or display as \\[ ... \\] (e.g. \\( x^2 + y^2 \\), \\( \\neg P \\lor Q \\))
8. **TABLES/GRAPHS**: When context includes a table (e.g. Truth Table, comparison table) or graph/figure description, you may ask a question based on it; if the table is small, you may include it in the question in Markdown format
9. **GRAPH DIAGRAMS**: For ANY question involving a graph algorithm or graph property, embed a rendered diagram using this syntax INSIDE question_text:
   [GRAPH: nodes=...  edges=...  directed=...  layout=...  highlight=...  highlight_edges=...  show_degrees=...  title=...]

   Field reference:
   - edges: NodeA-NodeB:weight (undirected weighted), NodeA-NodeB (unweighted), NodeA->NodeB[:w] (directed)
   - directed: true | false (default false)
   - layout: spring (default) | circular | shell | kamada_kawai
   - highlight: comma-separated node names to draw in RED (e.g. path endpoints, start vertex)
   - highlight_edges: comma-separated edges to draw in ORANGE/thick (e.g. Eulerian trail, MST edges, shortest path)
   - show_degrees: true — annotates every node with its degree d=N; use for Eulerian questions
   - title: short label shown below the graph

   TOPIC-SPECIFIC EXAMPLES:

   Eulerian path/circuit:
     "Determine whether an Eulerian path exists in the graph below. If yes, write the path.\n[GRAPH: edges=A-B,A-C,A-D,B-C,C-D  directed=false  layout=circular  show_degrees=true  title=Graph G — check for Eulerian path]"
     (Hint: design edges so exactly 0 or 2 nodes have odd degree)

   Eulerian circuit (Königsberg-style):
     "The following graph represents the Königsberg bridge problem. Explain why an Eulerian circuit does NOT exist.\n[GRAPH: nodes=A,B,C,D  edges=A-B,A-B,A-C,A-C,A-D,B-D,C-D  directed=false  layout=spring  show_degrees=true  title=Königsberg Bridge Graph]"

   Eulerian path answer diagram (highlight the trail):
     "[GRAPH: edges=A-B,B-C,C-D,D-A,A-C  highlight_edges=A-B,B-C,C-D,D-A,A-C  show_degrees=true  title=Eulerian path: A-B-C-D-A-C]"

   Dijkstra:
     "[GRAPH: edges=S-A:4,S-B:2,A-C:3,B-C:1,B-D:5,C-D:2  directed=false  highlight=S  layout=spring  title=Find shortest path from S]"

   BFS/DFS (directed):
     "[GRAPH: edges=A->B,A->C,B->D,B->E,C->F,C->G  directed=true  highlight=A  layout=spring  title=BFS/DFS from A]"

   MST (highlight MST edges):
     "[GRAPH: edges=A-B:2,A-C:3,B-C:1,B-D:4,C-D:2  highlight_edges=B-C,A-B,C-D  title=MST edges highlighted]"

   Bipartite check:
     "[GRAPH: nodes=A,B,C,X,Y,Z  edges=A-X,A-Y,B-Y,B-Z,C-X,C-Z  layout=shell  title=Is this graph bipartite?]"

   USE this for: Eulerian path/circuit, Hamiltonial path, Dijkstra, BFS, DFS, MST (Kruskal/Prim), topological sort, bipartite check, graph colouring, matching, Königsberg bridge problem, clique/independent set identification.
10. Return ONLY the JSON object
"""


# ─── Descriptive Generation Prompt ─────────────────────────────────────────────

DESCRIPTIVE_PROMPT = """You are an expert university exam question setter.

Generate exactly ONE descriptive exam question based on the specifications below.

SPECIFICATIONS:
- Bloom's Level: {bloom_target}
- Marks: {marks}
- Difficulty: {difficulty}
- Question Nature: {nature}
- Target Units: {units}

CONTEXT (use ONLY information from these chunks; do NOT copy text verbatim):
---
{context_text}
---

OUTPUT FORMAT — respond with ONLY a valid JSON object, no markdown, no explanation:
{{
  "question_text": "<full question text — may include sub-parts like (a), (b) for high-mark questions>",
  "bloom_level": "<remember|understand|apply|analyze|evaluate|create>",
  "difficulty": "<easy|medium|hard>",
  "marks": {marks},
  "answer_key": "<detailed model answer — LENGTH MUST BE PROPORTIONAL TO MARKS>",
  "marking_scheme": [
    {{"point": "<what to check>", "marks": <int>}},
    ...
  ],
  "source_chunk_ids": [<chunk_id>, ...]
}}

RULES:
1. Bloom level must match the specification: {bloom_target}
2. Marking scheme points must sum to exactly {marks} marks
3. Do NOT start with "According to the passage" or "Based on the text"
4. Do NOT copy chunk text verbatim — paraphrase and synthesise
5. For marks >= 10: include sub-parts (a), (b), (c) or structured parts
6. For marks <= 5: ask a focused, single-concept question
7. source_chunk_ids: list IDs of chunks used
8. **MATH**: For mathematical expressions use LaTeX: inline \\( ... \\) or display \\[ ... \\] (e.g. \\( \\forall x \\), \\( A \\wedge B \\rightarrow C \\), equations)
9. **TABLES/GRAPHS**: When context includes a table (Truth Table, data table) or graph/figure, you may ask the student to complete, interpret, or reason about it; include the table in the question in Markdown if needed
10. **GRAPH DIAGRAMS**: For ANY question involving a graph algorithm or graph property, embed a rendered diagram INSIDE question_text:
    [GRAPH: nodes=...  edges=...  directed=...  layout=...  highlight=...  highlight_edges=...  show_degrees=...  title=...]

    Field reference:
    - edges: NodeA-NodeB:weight (undirected weighted), NodeA-NodeB (unweighted), NodeA->NodeB[:w] (directed)
    - directed: true | false (default false)
    - layout: spring (default) | circular | shell | kamada_kawai
    - highlight: comma-separated node names to draw in RED (start vertex, path endpoints)
    - highlight_edges: edges to draw in ORANGE/thick (Eulerian trail, MST, shortest path)
    - show_degrees: true — annotates every node with its degree; ALWAYS use for Eulerian path/circuit questions
    - title: short label below the graph; describe what the student must do

    TOPIC-SPECIFIC EXAMPLES:

    Eulerian path (design so exactly 2 odd-degree nodes exist):
      "Determine whether an Eulerian path exists. If so, find one.\n[GRAPH: edges=A-B,A-C,B-C,B-D,C-D,C-E,D-E  directed=false  layout=circular  show_degrees=true  title=Graph G: find Eulerian path]"

    Eulerian circuit (0 odd-degree nodes):
      "Does Graph G below have an Eulerian circuit? Justify using degree conditions.\n[GRAPH: edges=A-B,B-C,C-D,D-A,A-C,B-D  directed=false  layout=circular  show_degrees=true  title=Graph G]"

    Königsberg bridge:
      "Explain the Königsberg bridge problem and prove no Eulerian circuit exists.\n[GRAPH: nodes=A,B,C,D  edges=A-B,A-B,A-C,A-C,A-D,B-D,C-D  directed=false  layout=spring  show_degrees=true  title=Königsberg Bridge Graph]"

    Trail in answer (highlight the Eulerian path):
      "[GRAPH: edges=A-B,B-C,C-D,D-E,E-A,A-C  highlight_edges=A-B,B-C,C-D,D-E,E-A,A-C  show_degrees=true  title=Eulerian circuit: A→B→C→D→E→A→C]"

    Dijkstra: "[GRAPH: edges=S-A:4,S-B:2,A-C:3,B-C:1,B-D:5,C-D:2  highlight=S  title=Dijkstra from S]"
    MST Kruskal: "[GRAPH: edges=A-B:2,A-C:3,B-C:1,B-D:4,C-D:2  highlight_edges=B-C,A-B,C-D  title=MST edges highlighted]"
    Topological sort: "[GRAPH: edges=A->B,A->C,B->D,C->D,D->E  directed=true  layout=spring  title=Find topological order]"

    ALWAYS use graph diagrams for: Eulerian path/circuit, Hamiltonian path, Dijkstra, BFS, DFS, MST, topological sort, bipartite check, graph colouring, matching, cliques, the Königsberg bridge problem.

**CRITICAL - ANSWER LENGTH REQUIREMENTS:**
- **2 marks**: 1-2 paragraphs (100-150 words) - Brief but complete answer with key concepts
- **3-4 marks**: 2-3 paragraphs (150-250 words) - Detailed explanation with examples
- **5 marks**: 3 paragraphs (250-350 words) - Comprehensive coverage with examples and explanations
- **6-8 marks**: 4-5 paragraphs (350-500 words) - Extensive discussion, multiple perspectives, detailed examples
- **10+ marks**: 5-7 paragraphs (500-800 words) - In-depth analysis, comprehensive coverage, multiple examples, comparative discussion

Each paragraph should be 3-5 sentences. Higher marks = more depth, more examples, more analysis.

8. Return ONLY the JSON object
"""



# ─── Context formatter ─────────────────────────────────────────────────────────

def _format_context(chunks: List[DocumentChunk]) -> str:
    """Format chunks into labelled context block."""
    parts = []
    for chunk in chunks:
        cid = chunk.id
        unit_label = f"(Unit {chunk.unit_id})" if chunk.unit_id else ""
        bloom_label = f"[{chunk.blooms_level}]" if chunk.blooms_level else ""
        text = (chunk.text or "").strip()
        parts.append(f"[Chunk ID: {cid}] {unit_label} {bloom_label}\n{text}")
    return "\n\n---\n\n".join(parts)


def _format_visual_context(visual_chunks: List) -> str:
    """Format visual chunk captions for prompt context. visual_chunks are VisualChunk ORM objects."""
    if not visual_chunks:
        return ""
    parts = []
    for v in visual_chunks:
        aid = getattr(v, "id", None)
        caption = (getattr(v, "caption_text", None) or "").strip()
        if caption:
            parts.append(f"[Figure ID: {aid}] {caption}")
    if not parts:
        return ""
    return "\n\n".join(parts)


# ─── JSON extraction ───────────────────────────────────────────────────────────

def _fix_latex_escapes(json_str: str) -> str:
    """
    Pre-process raw LLM JSON to fix LaTeX backslash sequences that are invalid
    or misinterpreted as JSON escape sequences.

    The LLM writes LaTeX like \\( \\neg P \\lor Q \\) inside JSON string values,
    but those backslashes break json.loads in two ways:
      • Invalid escapes  — \\(  \\)  \\[  \\]  \\,  \\!  \\;  \\l  \\p … crash the parser
      • Silent corruption — \\n → newline (but LaTeX means \\neg), \\f → form-feed
                            (but LaTeX means \\forall / \\frac), \\t → tab (\\theta) …

    Strategy: double EVERY backslash except \\\" (escaped quote) and \\\\ (already-
    escaped backslash).  This turns every LaTeX \\cmd into \\\\cmd, which json.loads
    reads back as the literal string \\cmd — exactly what the PDF renderer expects.

    Only called after json.loads() has already failed, so correctly-escaped output
    is never touched by this function.
    """
    # Replace any \ that is NOT immediately followed by \ or " with \\
    # This covers all LaTeX commands (\neg, \forall, \frac, \rightarrow …),
    # math delimiters (\( \) \[ \]), spacing (\, \! \; \:) and everything else.
    return re.sub(r'\\(?![\\"])', r'\\\\', json_str)


def _extract_json_obj(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found: {raw[:200]}")
    json_str = raw[start:end]

    # First attempt: standard parse (handles well-formed LLM output)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Second attempt: fix LaTeX backslash sequences that break JSON parsing,
    # then re-parse.  This covers \\neg, \\lor, \\rightarrow, \\(, \\[ etc.
    try:
        return json.loads(_fix_latex_escapes(json_str))
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse error: {e}") from e


# ─── MCQ builder ──────────────────────────────────────────────────────────────

def _build_mcq(data: dict, spec: QuestionSpec, chunks: List[DocumentChunk]) -> GeneratedQuestion:
    """Parse GPT MCQ output into a GeneratedQuestion."""
    options = []
    for opt in data.get("options", []):
        label = str(opt.get("label", "")).upper().strip()
        text = str(opt.get("text", "")).strip()
        if label and text:
            options.append(MCQOption(label=label, text=text))

    # Fallback: if GPT didn't give 4 options, something went wrong
    if len(options) < 2:
        raise ValueError("GPT returned fewer than 2 MCQ options")

    answer_key = str(data.get("answer_key", "A")).upper().strip()

    chunk_ids = {c.id for c in chunks}
    source_ids = [int(i) for i in (data.get("source_chunk_ids") or []) if int(i) in chunk_ids] or [c.id for c in chunks]

    return GeneratedQuestion(
        question_type="mcq",
        question_text=data.get("question_text", ""),
        bloom_level=data.get("bloom_level", spec.bloom_targets[0] if spec.bloom_targets else "understand"),
        difficulty=data.get("difficulty", spec.difficulty),
        marks=spec.marks,
        options=options,
        answer_key=answer_key,
        marking_scheme=[],
        source_chunk_ids=source_ids,
        source_asset_ids=[],  # set by caller when visual_chunks provided
        unit_ids=spec.units,
    )


# ─── Descriptive builder ──────────────────────────────────────────────────────

def _build_descriptive(data: dict, spec: QuestionSpec, chunks: List[DocumentChunk]) -> GeneratedQuestion:
    """Parse GPT descriptive output into a GeneratedQuestion."""
    marking_scheme = []
    total_scheme_marks = 0
    for item in (data.get("marking_scheme") or []):
        pt = str(item.get("point", "")).strip()
        m = int(item.get("marks", 0))
        if pt:
            marking_scheme.append(MarkingPoint(point=pt, marks=m))
            total_scheme_marks += m

    # Adjust last item if scheme doesn't sum correctly
    if marking_scheme and total_scheme_marks != spec.marks:
        diff = spec.marks - total_scheme_marks
        marking_scheme[-1].marks = max(0, marking_scheme[-1].marks + diff)

    chunk_ids = {c.id for c in chunks}
    raw_ids = data.get("source_chunk_ids") or []
    source_ids = [int(i) for i in raw_ids if isinstance(i, (int, str)) and str(i).isdigit() and int(i) in chunk_ids]
    if not source_ids:
        source_ids = [c.id for c in chunks]

    return GeneratedQuestion(
        question_type="descriptive",
        question_text=data.get("question_text", ""),
        bloom_level=data.get("bloom_level", spec.bloom_targets[0] if spec.bloom_targets else "understand"),
        difficulty=data.get("difficulty", spec.difficulty),
        marks=spec.marks,
        options=[],
        answer_key=data.get("answer_key", ""),
        marking_scheme=marking_scheme,
        source_chunk_ids=source_ids,
        source_asset_ids=[],  # set by caller when visual_chunks provided
        unit_ids=spec.units,
    )


# ─── Token calculation helper ──────────────────────────────────────────────────

def _calculate_max_tokens(marks: int, is_mcq: bool) -> int:
    """
    Calculate appropriate max_tokens based on question marks.
    
    Token estimates (rough guide):
    - 100 words ≈ 133 tokens
    - 2 marks (150 words) ≈ 200 tokens
    - 5 marks (300 words) ≈ 400 tokens
    - 10 marks (650 words) ≈ 850 tokens
    
    We add buffer for JSON structure, marking scheme, etc.
    """
    if is_mcq:
        # MCQs don't scale much with marks - fixed size
        return 1200
    
    # Descriptive questions scale with marks
    if marks <= 2:
        return 1500  # ~150 words answer + overhead
    elif marks <= 4:
        return 2000  # ~250 words answer + overhead
    elif marks <= 5:
        return 2500  # ~350 words answer + overhead
    elif marks <= 8:
        return 3200  # ~500 words answer + overhead
    else:  # 10+ marks
        return 4000  # ~800 words answer + overhead


# ─── Main generator ────────────────────────────────────────────────────────────

async def generate_question(
    spec: QuestionSpec,
    chunks: List[DocumentChunk],
    visual_chunks: Optional[List] = None,
    extra_instruction: Optional[str] = None,
    table_markdown_context: Optional[str] = None,
) -> GeneratedQuestion:
    """
    Step 4: Generate one exam question for a QuestionSpec.

    Routes to MCQ or descriptive generation based on spec.question_type.
    If visual_chunks is provided, their captions are appended to context and
    source_asset_ids are set on the result (for diagram-in-paper export).
    extra_instruction: optional teacher guidance appended to the prompt (e.g. LaTeX, tables).
    table_markdown_context: full table Markdown from ParsedElement (chunks only have row-level text).
    Falls back to a safe error question on complete failure.
    """
    from generation.gpt_client import call_gpt

    context_text = _format_context(chunks)
    visual_context = _format_visual_context(visual_chunks or [])
    if visual_context:
        context_text = context_text + "\n\n---\n\nFIGURES/DIAGRAMS (use when question involves a diagram or graph):\n" + visual_context
    if table_markdown_context and table_markdown_context.strip():
        context_text = context_text + "\n\n---\n\nTABLES (Markdown — use when question involves data, truth tables, or comparisons):\n" + table_markdown_context.strip()
    bloom_target = ", ".join(spec.bloom_targets) if spec.bloom_targets else "understand"
    is_mcq = spec.question_type == "mcq"
    
    # Scale context length with marks for better quality answers
    context_limit = 5000 if is_mcq else min(6000 + (spec.marks * 200), 12000)

    if is_mcq:
        prompt = MCQ_PROMPT.format(
            bloom_target=bloom_target,
            marks=spec.marks,
            difficulty=spec.difficulty,
            nature=spec.nature or "general",
            units=", ".join(f"Unit {u}" for u in spec.units),
            context_text=context_text[:context_limit],
        )
    else:
        prompt = DESCRIPTIVE_PROMPT.format(
            bloom_target=bloom_target,
            marks=spec.marks,
            difficulty=spec.difficulty,
            nature=spec.nature or "general",
            units=", ".join(f"Unit {u}" for u in spec.units),
            context_text=context_text[:context_limit],
        )

    if extra_instruction and extra_instruction.strip():
        prompt = prompt + "\n\nADDITIONAL INSTRUCTIONS (follow these):\n" + extra_instruction.strip()

    raw = await call_gpt(
        prompt,
        temperature=0.45 if is_mcq else 0.55,
        max_tokens=_calculate_max_tokens(spec.marks, is_mcq),
    )

    try:
        data = _extract_json_obj(raw)
    except Exception as e:
        return _fallback_question(spec, chunks, f"JSON parse error: {e}", visual_chunks)

    try:
        if is_mcq:
            q = _build_mcq(data, spec, chunks)
        else:
            q = _build_descriptive(data, spec, chunks)
        if visual_chunks:
            q.source_asset_ids = [getattr(v, "id", 0) for v in visual_chunks if getattr(v, "id", None)]
        return q
    except Exception as e:
        return _fallback_question(spec, chunks, f"Build error: {e}", visual_chunks)


def _fallback_question(
    spec: QuestionSpec,
    chunks: List[DocumentChunk],
    reason: str,
    visual_chunks: Optional[List] = None,
) -> GeneratedQuestion:
    """Return a safe placeholder question instead of crashing the pipeline."""
    asset_ids = [getattr(v, "id", 0) for v in (visual_chunks or []) if getattr(v, "id", None)]
    return GeneratedQuestion(
        question_type=spec.question_type,
        question_text=f"[Q{spec.question_no} — generation failed: {reason}]",
        bloom_level=spec.bloom_targets[0] if spec.bloom_targets else "understand",
        difficulty=spec.difficulty,
        marks=spec.marks,
        answer_key="",
        options=[],
        marking_scheme=[],
        source_chunk_ids=[c.id for c in chunks],
        source_asset_ids=asset_ids,
        unit_ids=spec.units,
    )
