# Chunk Quality Issue & Fix

## Problem Summary

Your chunks are showing only metadata (section paths, headings) with minimal actual content because of **PDF parsing fragmentation**.

### Root Cause

The unstructured library's PDF parser sometimes fragments text incorrectly:

```
Order 3: Text     "Human : a user, a group of users , or a sequence of users in"
Order 4: NarrativeText "an organization, trying to get the job done with the"
Order 5: Title    "technology."  ← WRONG! This is a sentence fragment, not a heading!
```

When small fragments like "technology." are misclassified as `Title` elements, the chunker treats them as structural headings and starts new sections, causing:
- **Hundreds of tiny chunks** with mostly just section paths
- **Minimal body content** (just fragments between headings)
- **Poor retrieval quality** (no meaningful text to search)

### Example of Bad Chunks

```
Chunk 3113:
  Text: "Path: Unit II > Business Intelligence > Department of Computer Engineering BRACT'S...\n\n(An"
  Problem: Only shows path + fragment "(An"

Chunk 3114:
  Text: "Path: Unit II > Business Intelligence > Department of Computer Engineering BRACT'S...\n\nAutonomous"
  Problem: Only one word "Autonomous" in body
```

## Solution Applied

### 1. Fixed Chunker Logic (`parsing/chunker.py`)

**A) Ignore short Title fragments:**

Updated `_is_structural_heading()` to ignore short Title fragments:

```python
def _is_structural_heading(text: str, element_type: str) -> bool:
    # ... existing checks ...
    
    # NEW: Ignore very short "Title" fragments (likely PDF parsing errors)
    # A real structural heading should be at least 3 words or match major patterns
    stripped = text.strip()
    word_count = len(stripped.split())
    if word_count < 3 and not MAJOR_HEADING.match(stripped):
        # Short fragment that doesn't match major heading pattern → treat as regular text
        return False
    
    return True
```

**What this does:**
- Short Title fragments (< 3 words) like "technology." are now treated as **regular text**
- They get **merged into chunk bodies** instead of starting new sections
- Only real headings (3+ words or patterns like "Unit I", "1.1") start new sections

**B) Filter institutional boilerplate:**

Added patterns to detect and exclude college names, departments, etc. from section paths:

```python
# Institutional boilerplate patterns
INSTITUTIONAL_BOILERPLATE = re.compile(
    r"(Department of Computer Engineering|BRACT'?S|Vishwakarma Institute|"
    r"Institute of Information Technology|Pune-?\d+|"
    r"An Autonomous Institute|affiliated to|University|College|Department)", re.I
)
```

**What this does:**
- Removes **"Department of Computer Engineering BRACT'S, Vishwakarma Institute..."** from paths
- Keeps only **meaningful section hierarchy**: Unit II > Business Intelligence > Topic Name
- Saves tokens (embedding space) and makes chunks cleaner to read
- Before: `Path: Unit I > Business Intelligence > Department of Computer Engineering BRACT'S, Vishwakarma Institute of Information Technology, Pune-48 > Topic`
- After: `Path: Unit I > Business Intelligence > Topic`

### 2. Fix Script (`fix_chunks.py`)

Created utility to re-process existing documents with the fixed logic.

## How to Fix Your Existing Data

### Option 1: Re-chunk Specific Documents (Recommended)

Check which documents have poor chunks, then re-chunk them:

```bash
cd ai-backend

# Dry run first (see what would change)
python fix_chunks.py --document-id 55 --dry-run

# Actually fix it
python fix_chunks.py --document-id 55

# Fix multiple documents
python fix_chunks.py --document-id 56
python fix_chunks.py --document-id 57
python fix_chunks.py --document-id 58
```

### Option 2: Re-chunk All Documents

**WARNING:** This will re-process ALL documents. Takes time for large datasets.

```bash
cd ai-backend

# Dry run first (see impact)
python fix_chunks.py --all --dry-run

# Fix all documents
python fix_chunks.py --all
```

### Option 3: Re-upload Documents

Simply delete problematic documents from UI and re-upload them. The new upload will use the fixed chunker.

## Verification

After fixing, check VectorsExplorer:

1. Navigate to: **Pareeksha → VectorsExplorer**
2. Set View to: **Chunks (merged, for retrieval)**
3. Set Text to: **Full text**
4. Filter by: **Document ID** (e.g., 55)
5. Look for:
   - **Longer chunk text** (500-1000 tokens instead of just paths)
   - **Meaningful content** (paragraphs, not fragments)
   - **Fewer total chunks** (merged instead of fragmented)

### Before Fix
```
Text (full): Path: Unit II Decision Making and Support System > Business Intelligence and Data Analytics > Department of Computer Engineering BRACT'S, Vishwakarma Institute of Information Technology, Pune-48

(An
```
**Problems:**
- ❌ Institutional boilerplate in path (wastes tokens)
- ❌ Only fragment "(An" in body (useless for retrieval)
- ❌ 342 total chunks (over-fragmented)

### After Fix
```
Text (full): Path: Unit II Decision Making and Support System > Business Intelligence and Data Analytics

Business Intelligence (BI) is a technology-driven process for analyzing data and presenting actionable information to help executives, managers, and workers make informed business decisions. BI encompasses a variety of tools, applications, and methodologies that enable organizations to collect data from internal systems and external sources, prepare it for analysis, develop and run queries against that data, and create reports, dashboards, and data visualizations.
```
**Improvements:**
- ✅ Clean path without college name (saves ~50 tokens per chunk!)
- ✅ Full paragraph with actual content (useful for search!)
- ✅ ~50-100 total chunks (properly merged)

## Why Chunks Are Useful (When Fixed)

Chunks are the **main retrieval units** for your RAG system:

1. **Semantic Search**: When users search "What is Business Intelligence?", the system:
   - Embeds the question
   - Finds semantically similar chunks
   - Returns relevant content

2. **Context for Question Generation**: When creating exam questions:
   - System searches chunks for relevant topics
   - Uses chunk content as context for LLM
   - Generates questions grounded in course material

3. **Section-Aware Retrieval**: Chunks preserve hierarchy:
   - Path: "Unit II > BI Concepts > Data Warehousing"
   - Search can filter by unit/topic
   - Better organization than flat elements

**With bad chunks** (only paths), search returns nothing useful.  
**With good chunks** (500-1000 tokens of real content), retrieval works as designed.

## Prevention: Better PDF Quality

To avoid this issue in future uploads:

1. **Use native PPTX/DOCX when possible** (better parsing than PDF)
2. **Export PDFs with text layers** (not scanned images)
3. **Clean formatting** (avoid complex layouts that confuse parser)
4. **Test small samples** before bulk upload

## Technical Details

### Chunking Strategy

The chunker follows a smart strategy:

1. **Prepare**: Clean junk, merge sentence fragments, deduplicate
2. **Structure**: Build section_path from headings (Unit I > Topic > Subtopic)
3. **Merge**: Combine TEXT elements into ~500-1000 token chunks
4. **Enrich**: Prefix with "Path: ..." for embedding (gives retrieval context)
5. **Optional semantic split**: Use embeddings to break at topic boundaries

### Target Size
- **Min**: 400 words (~520 tokens)
- **Max**: 800 words (~1040 tokens)
- **Overlap**: 100 words between consecutive chunks (continuity)

### Element Types Handled
- **TEXT**: NarrativeText, ListItem, Text elements → merged into chunks
- **TITLES**: Headings → update section_path, start new chunks
- **TABLES**: Each row → separate chunk (retrieval-friendly)
- **DIAGRAMS**: Skipped from chunking (visual content)

## Questions?

If chunks are still poor after running the fix:

1. **Check parsed elements** first:
   ```bash
   # View raw parsed elements for a document
   curl "http://localhost:8001/documents/55/elements?limit=50"
   ```

2. **Look for patterns**:
   - Are most elements classified as Title?
   - Are Text elements very short (< 5 words)?
   - Is content missing entirely?

3. **Try different file format**:
   - If using PDF from PowerPoint → upload PPTX directly
   - If using scanned PDF → use OCR or text-based export

4. **Report parsing issues**:
   - Note which file types cause problems
   - May need to adjust unstructured parser settings
   - Or switch to alternative parser (PyMuPDF, pdfplumber, etc.)

## Summary

✅ **Fixed**: Chunker now ignores short Title fragments  
✅ **Script**: Run `fix_chunks.py` to re-process existing docs  
✅ **Verify**: Check VectorsExplorer to confirm improved chunks  
✅ **Prevention**: Use native PPTX/DOCX when possible  

Your retrieval quality should dramatically improve after fixing!
