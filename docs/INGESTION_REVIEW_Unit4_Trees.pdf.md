# Ingestion Review: Unit 4-Trees.pptx.pdf

This document reviews how the smart-assessment **ingestion pipeline** will process `Unit 4-Trees.pptx.pdf` (PDF exported from PowerPoint, ~800 KB).

---

## 1. File and format

| Item | Value |
|------|--------|
| **Path** | `/Users/pranavbhosale1/Desktop/PICT/DM/Unit 4-Trees.pptx.pdf` |
| **Extension** | `.pdf` |
| **Treated as** | **PDF** (parser is chosen by extension only; native `.pptx` is not used) |
| **Parser** | `unstructured.partition.pdf` with **strategy** `"fast"` or `"hi_res"` (see below). |

- **Strategy `"fast"` (default):**
  - Text-only extraction; **skips image/layout detection** — so **Image/Table elements are not produced** and diagrams in the PPT will not be detected.
  - No OCR (text must be embedded/selectable).
- **Strategy `"hi_res"` (when subject has math_mode):**
  - Layout + image detection; **extracts Image/Table elements** so diagrams and figures can be captioned and indexed.
  - Used automatically for PDFs when the subject has **math_mode = True** (e.g. Discrete Mathematics). If `hi_res` fails (e.g. missing `unstructured[local-inference]`), the pipeline falls back to `"fast"`.
- **Why your run had no images:** With strategy `"fast"`, Unstructured does not process images in PDFs. Enable **math_mode** on the subject and re-ingest to use `hi_res` and get Image/Table elements.

---

## 2. Pipeline steps relevant to this PDF

| Step | Module | Relevance for Unit 4-Trees (DM) |
|------|--------|----------------------------------|
| **1. Parse** | `parser.py` | PDF → list of elements (Title, NarrativeText, ListItem, Image, Table, etc.). Each slide typically becomes one or more “pages”; order is preserved. |
| **2. Normalize** | `normalizer.py` | Cleans CID artifacts, PUA chars, bullets, spaces. **For DM subject:** use **formula_mode=True** so symbols ∀, ∃, ∧, ∨, ¬, →, ↔, − are preserved (critical for tree/logic content). |
| **3. Caption images** | `image_captioner.py` | GPT-4o Vision captions detected **Image** elements. Diagram-heavy slides benefit from this. |
| **4. Format tables** | `table_formatter.py` | Table elements → Markdown. Any “Trees” comparison or property tables get cleaned. |
| **5. Cleanup** | `cleanup.py` | Removes Header/Footer, page numbers, TOC leaders, pure numeric, symbol-only, empty, CID. Slide footers (e.g. “Unit 4 - Trees”) are removed if classified as Header/Footer. |
| **6. Classify** | `classifier.py` | Elements → TEXT / DIAGRAM / TABLE / CODE / FORMULA / OTHER. Tree diagrams and figures can be marked DIAGRAM. |
| **6c. Assets** | `asset_extractor.py` | **PDF only**, and only when **subject.math_mode is True**. Renders pages, crops Image/Table regions, creates Asset rows; optional vision captioning. |
| **7. Chunk** | `chunker.py` | Section-aware chunks (600–1000 chars, 100 overlap). Section path comes from title/heading stack (e.g. “Unit 4 / Trees / Binary Tree”). Short slide text may be merged across slides into one chunk. |
| **8–9. Embed & index** | embeddings + Qdrant | Chunks and (for PDF) visual chunks get embedded and indexed. |
| **9c. Visual chunks** | `visual_chunks.py` | **PDF only.** Builds visual chunks only for elements already detected as Image/Figure/Table; renders only those pages, crops by bbox, captions the crop. |
| **10. Align** | alignment router | Chunks are aligned to subject concepts (e.g. Trees, Traversals) via Gemini. |

---

## 3. Subject settings to check (DM)

- **formula_mode**  
  Should be **True** for Discrete Mathematics so that:
  - Normalizer keeps logic/math symbols (∀, ∃, ∧, ∨, ¬, →, ↔, −).
  - Equations and definitions in “Unit 4 - Trees” are not corrupted.

- **math_mode** (optional)  
  If **True**:
  - Phase 2 asset extraction runs (per-element Image/Table crops, Asset rows).
  - Optional **vision_budget** controls how many images get vision captions.
  - Chunks can reference assets and get `[[FIGURE: kind | caption]]` in text.

- **vision_budget**  
  Limits how many image-type assets are sent for captioning; avoids excessive API cost on diagram-heavy decks.

---

## 4. PPT-exported PDF specifics

- **Structure:**  
  Slides become pages. Section hierarchy (section_path) is inferred from Title/heading elements, not from PPT slide structure. If the deck has clear slide titles (e.g. “Definition”, “Binary Tree”, “Traversals”), section paths will reflect that.

- **Images/diagrams:**  
  Unstructured with `strategy="fast"` may not detect every embedded image (e.g. flowcharts, tree figures). Only elements that come out as Image/Figure/Table get:
  - Image captioning (Step 3),
  - Asset extraction (Step 6c, when math_mode),
  - Visual chunk creation (Step 9c).

- **Tables:**  
  Any Table elements are formatted to Markdown and get table-row chunks in addition to normal text chunks.

- **Cleanup:**  
  Repeated slide footers/headers are removed if they are classified as Header/Footer by Unstructured.

---

## 5. Optional: native PPTX

If you have the original **.pptx**:

- Uploading **Unit 4-Trees.pptx** (instead of the PDF) would use `partition_pptx`, which preserves slide-based structure and often gives clearer slide boundaries and titles.
- Visual chunk pipeline is **only run for PDF**; for PPTX you get element-based parsing and chunking but not the “render page → crop → caption” visual pipeline.

So:

- **Use PDF** when you want visual chunks and (with math_mode) asset extraction.
- **Use PPTX** when slide structure and titles are more important than full-page/crop visuals.

---

## 6. How to verify after ingestion

1. **Subject:**  
   Ensure the subject (e.g. “Discrete Mathematics”) has **formula_mode = True** (and optionally **math_mode** and **vision_budget**).

2. **Upload:**  
   Upload `Unit 4-Trees.pptx.pdf` to that subject via the app (or `POST /documents/upload-and-store`).

3. **Inspect:**
   - **Elements:** `GET /documents/{document_id}/elements` — check counts by `element_type` (Title, NarrativeText, ListItem, Image, Table) and that tree-related text and definitions are present.
   - **Chunks:** `GET /documents/chunks-with-embeddings?document_id={id}` — check that section_path reflects “Unit 4”, “Trees”, and sub-topics, and that chunk text is readable (no broken formulas if formula_mode is on).
   - **Visuals:** If math_mode/visual pipeline ran, check DB/API for Asset and VisualChunk rows and that key diagrams have captions.

4. **Optional local check (no DB):**  
   From `ai-backend`, with dependencies installed (`pip install 'unstructured[pdf]'` etc.):

   ```bash
   python scripts/check_pdf_ingestion.py "/Users/pranavbhosale1/Desktop/PICT/DM/Unit 4-Trees.pptx.pdf"
   ```

   This prints element types, page range, and sample elements so you can confirm parsing quality before full ingestion.

---

## 7. Summary

| Aspect | Status / recommendation |
|--------|--------------------------|
| **Format** | Treated as PDF; parsing uses `strategy="fast"` (no OCR). Suitable for selectable-text PPT exports. |
| **Math/logic** | Enable **formula_mode** on the DM subject so ∀, ∃, ∧, ∨, ¬, →, ↔, − are preserved. |
| **Diagrams/assets** | Enable **math_mode** (and optionally **vision_budget**) if you want per-figure assets and captions; visual chunks run only for PDF. |
| **Structure** | Section paths come from detected titles/headings; ensure slide titles are clear for good section_path and chunk context. |
| **Verification** | After upload, check elements and chunks for this document; optionally run `scripts/check_pdf_ingestion.py` for a quick parse-only check. |

The pipeline is **thorough with respect to ingestion**: it covers parsing, normalization (with formula_mode), cleanup, classification, chunking, embedding, indexing, optional assets/visuals for PDF, and concept alignment. For “Unit 4 - Trees” the main things to ensure are **formula_mode** for the subject and, if you care about diagrams, **math_mode** and a sensible **vision_budget**.
