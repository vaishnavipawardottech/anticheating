# Smart Assessment — Deep Dive: Each Algorithm

This document explains **every retrieval and context-building algorithm** in depth: intuition, mathematics, step-by-step behaviour, and design choices.

---

## 1. Full-Text Search (PostgreSQL tsvector / ts_rank_cd)

### What it is

A **keyword-based** way to find chunks that contain the user’s query terms, and to **rank** them by how “good” the match is (term frequency, proximity, and where the match occurred).

### Why we use it

- Users often search for **exact phrases or terms** (e.g. “virtual memory”, “page fault”).
- Semantic search alone can return chunks that are *about* the topic but don’t contain the words; FTS ensures **lexical match**.
- Postgres gives us **one consistent API**: store a searchable representation of text and query it with a single SQL expression.

### How it works (step by step)

**1. Building the search vector (at index time)**

For each chunk we store:

- **text** (body) → tokenized and stemmed with `to_tsvector('english', text)`.
- **section_path** (e.g. "Unit I > Memory Management") → same, but we assign it a **lower weight** than the body.

Concretely:

```text
search_vector = setweight(to_tsvector('english', text), 'A')
            || setweight(to_tsvector('english', section_path), 'B')
```

- **to_tsvector('english', x):**  
  - Splits `x` into words (using the English config).  
  - Stems words (e.g. “memory” and “memories” → same lexeme).  
  - Produces a set of (lexeme, position) entries.  
- **setweight(..., 'A')** and **setweight(..., 'B'):**  
  - In PostgreSQL, weights are **D, C, B, A** (D = lowest, A = highest).  
  - So body gets **A**, section_path gets **B**. When we rank, matches in the body contribute more than matches only in the path.  
- **||** concatenates the two tsvectors so one column holds both body and path with different weights.

**2. Query (at search time)**

- User query string `q` is turned into a **query tree** with `plainto_tsquery('english', q)`.
- **plainto_tsquery:**  
  - Normalizes and stems each word.  
  - Puts an **AND** between words: all terms must appear.  
  - So "virtual memory management" becomes something like `virtual & memori & manag`.

**3. Matching**

- Condition: `search_vector @@ plainto_tsquery('english', q)`.
- **@@** means “the document (tsvector) matches the query (tsquery)”.  
- So we only keep chunks that contain **all** query terms (after stemming).

**4. Ranking**

- We use **ts_rank_cd** (cover density):
  - **ts_rank_cd(tsvector, tsquery)** returns a real number that depends on:
    - **Term frequency:** more occurrences of query terms → higher rank.
    - **Proximity (cover density):** query terms appearing **close together** (e.g. “virtual memory” in one phrase) rank higher than the same terms scattered.
    - **Weights:** matches on A (body) count more than matches on B (path).
- We run:  
  `ORDER BY ts_rank_cd(search_vector, plainto_tsquery('english', q)) DESC`  
  and take the top N (e.g. 100). We then **only use the rank position** (1st, 2nd, 3rd, …) for RRF; we do **not** use the raw ts_rank_cd number when merging with vector search.

**5. Index**

- **GIN** index on `search_vector` makes `@@` and `ts_rank_cd` fast over large tables.

### Summary

- **Algorithm:** Tokenize + stem (English) → weight body (A) and path (B) → store as tsvector. Query: plainto_tsquery (AND of stemmed terms) → match with `@@` → rank with ts_rank_cd (frequency + proximity + weight).
- **We do not implement BM25 ourselves;** we use Postgres’s built-in FTS and its rank, then feed **positions** into RRF.

---

## 2. Cosine Similarity (and vector search)

### What it is

**Cosine similarity** measures how “aligned” two vectors are, regardless of length. It’s the standard way to compare **embedding** vectors (e.g. from text-embedding-3-small).

### Formula

For vectors **a** and **b** (same dimension):

```text
cos(a, b) = (a · b) / (||a|| × ||b||)
```

- **a · b** = dot product = Σᵢ aᵢ bᵢ  
- **||a||** = Euclidean norm = √(Σᵢ aᵢ²)

So:

```text
cos(a, b) = (Σᵢ aᵢ bᵢ) / (√(Σᵢ aᵢ²) × √(Σᵢ bᵢ²))
```

### Range and meaning

- **Range:** Always in **[-1, 1]**.
- **1:** Same direction (identical or proportional).  
- **0:** Orthogonal (no linear relation).  
- **-1:** Opposite direction.  
- For **typical embedding models** (e.g. OpenAI), coordinates are non-negative, so scores are usually in **[0, 1]**; higher = more similar.

### Why cosine (and not Euclidean distance)?

- **Length-agnostic:** A long paragraph and a short sentence about the same idea can have very different vector lengths; cosine focuses on **direction** (topic), not length.
- **Nearest-neighbor in vector DBs:** Qdrant (and many others) can use **cosine** as the distance; “nearest” then means “largest cosine similarity”. So “vector search” here = find chunks whose embeddings have **highest cosine** with the query embedding.

### Where we use it

- **Qdrant retrieval:** Query → embedding → search by cosine → ranked list of chunk IDs.
- **MMR:** Diversity term = “max cosine between candidate and already-selected chunks”.
- **Duplicate detection:** Two questions with cosine(embed(q1), embed(q2)) > 0.92 are treated as near-duplicates.
- **Semantic split (chunker):** Split at the boundary where **cosine between consecutive part-embeddings is minimum** (topic shift).

### Implementation note

Our code (e.g. `retrieval_engine._cosine`) is the direct formula: dot product divided by product of norms. Qdrant uses the same notion internally when `Distance.COSINE` is set.

---

## 3. RRF (Reciprocal Rank Fusion)

### What it is

**RRF** is a **score-free** way to merge several **ranked lists** into one. We don’t need to calibrate or normalize the raw scores of each system (FTS vs vector); we only use **positions** (ranks).

### Formula

For each list ℓ we have a ranking of items (1st, 2nd, 3rd, …). For an item **d** that appears in list ℓ at **rank** r (1-based):

- **Contribution from list ℓ:**  
  **score_ℓ(d) = 1 / (k + r)**  
  where **k** is a constant. We use **k = 60** everywhere.

**RRF score** for item d:

```text
RRF(d) = Σ over all lists ℓ  score_ℓ(d)
```

If d does not appear in a list, that list’s contribution is 0. Final ordering: sort items by **RRF(d)** descending.

### Why this shape (1/(k + rank))

- **Rank 1:** 1/(k+1) — highest contribution.  
- **Rank 2:** 1/(k+2) — a bit lower.  
- As rank grows, contribution drops smoothly; items at rank 100+ add very little.
- **k** controls how much we care about top vs tail:  
  - **k = 0:** Only rank 1 gets 1; rank 2 gets 1/2, etc. Very steep; only top positions matter.  
  - **k = 60 (our choice):** Softer; rank 1 = 1/61, rank 2 = 1/62, … Rank 40 still adds 1/100. So we get a **smooth decay** without completely ignoring mid ranks.  
- Common choice in literature is k ∈ [1, 60]; 60 is on the conservative side and avoids over-rewarding a single list’s top-1.

### Why RRF (and not linear combination of scores)?

- **FTS** gives ts_rank_cd (unbounded, different scale per corpus).  
- **Vector** gives cosine in [0,1].  
- To combine them you’d need **score normalization** and **weights** (e.g. 0.5*FTS_norm + 0.5*vector). RRF avoids that: we only need **order** from each system. No tuning of weights or scales.
- **Theoretical property:** Under mild assumptions, RRF approximates the ordering of a “true” relevance that would rank by probability of relevance; it’s a simple and robust heuristic.

### Small example

- **FTS list:** [chunk_A, chunk_B, chunk_C] (ranks 1, 2, 3).  
- **Vector list:** [chunk_B, chunk_A, chunk_D] (ranks 1, 2, 3).  
- k = 60:

  - chunk_A: 1/61 + 1/62 = 0.0164 + 0.0161 ≈ 0.0325  
  - chunk_B: 1/62 + 1/61 ≈ 0.0325  
  - chunk_C: 1/63 + 0 = 0.0159  
  - chunk_D: 0 + 1/63 = 0.0159  

So A and B tie at the top (both lists agree they’re good); C and D tie (each appears in only one list). We break ties by our implementation (e.g. stable sort or secondary key).

### Summary

- **Algorithm:** From each list, contribution(d) = 1/(k + rank(d)); RRF(d) = sum of contributions; sort by RRF descending.
- **Parameters:** k = 60.
- **Role:** Merge FTS and vector rankings without score normalization.

---

## 4. Keyword-Overlap Rerank

### What it is

A **second-stage reranker** that uses only the **query string** and **chunk text**: how many of the query’s words actually appear in the chunk. No embeddings, no FTS internals.

### Formula

- **Query terms:** T = set of words in the query (after splitting on non-alphanumeric, lowercased).  
  In code: `terms = set(re.findall(r"\w+", query.lower()))`.
- For each chunk **c** with text **t**:
  - **overlap(c) = |{w ∈ T : w in t}| / |T|**  
  i.e. fraction of query terms that appear at least once in the chunk (binary: in or not, no count).
- **Ordering:** Sort the candidate chunks (e.g. top 30 from RRF) by **overlap** descending; ties can be broken by original RRF order.

### Why use it

- Hybrid (FTS + vector) can return a chunk that is **semantically** related but doesn’t contain the exact words (e.g. query “page fault”, chunk talks about “page miss” and “exception”). Rerank boosts chunks that **lexically** contain the query.
- It’s **cheap** (no extra API or DB call), and acts as a simple **precision** boost on the final shortlist.

### Design choices

- **Binary overlap:** We count “term present yes/no”, not term frequency. So 10× “memory” doesn’t beat 1× “memory”; we only care that the word appears.
- **Denominator = |T|:** So the score is always in [0, 1]; chunks that contain all query terms get 1.0.

### Summary

- **Algorithm:** Extract query terms T; for each chunk, score = (number of distinct T that appear in chunk) / |T|; sort by score descending.
- **Role:** Rerank RRF top-N to favour chunks that actually contain the query words.

---

## 5. Context Building: Neighbor Expansion

### What it is

After we have a list of **retrieved chunk IDs** (e.g. from vector or hybrid), we optionally **add** the **immediate previous and next chunk** (same document, by chunk_index) for each retrieved chunk. No new retrieval; we just look up neighbors in the DB.

### Formula / rule

- For each retrieved chunk **c** (document_id = d, chunk_index = i):
  - Consider all chunks in the same document **d**.
  - Add chunks with **chunk_index in {i−1, i+1}** (if they exist), unless already in the list.
- **Order:** We keep a global order: first all “seed” chunk IDs in retrieval order, then we append neighbor IDs (and we avoid duplicates). When building the final context string, we sort by (document_id, chunk_index) so the text is in **reading order**.

### Why use it

- Retrieval returns **isolated** chunks. Sentences often span boundaries or refer to the previous paragraph; **adding ±1 chunk** gives the model a bit of surrounding context and reduces mid-sentence cuts.
- **Cost:** One extra DB query to load chunks by IDs and then in-memory grouping by document; no extra embedding or FTS.

### Summary

- **Algorithm:** For each retrieved chunk (doc_id, chunk_idx), add chunks (doc_id, chunk_idx−1) and (doc_id, chunk_idx+1) if present; dedupe; order by (document_id, chunk_index).
- **Role:** Improve coherence of the context string for RAG/generation.

---

## 6. Context Building: Token Budget and Truncation

### What it is

We have a **max_tokens** budget (e.g. 4000) for the combined context. We fill it by appending chunk text in order; if the **next** chunk would exceed the budget, we **truncate that chunk** (take a prefix) so that we stay under the cap.

### Token approximation

- We don’t call a tokenizer for every chunk. We use:  
  **approx_tokens(text) = int(len(text.split()) * 1.3)**  
  i.e. words × 1.3. This approximates subword tokenizers (e.g. ~1.2–1.4 tokens per word for English).

### Algorithm (step by step)

- **State:** `total_tokens = 0`, `parts = []`.
- For each chunk **c** in order (after neighbor expansion and dedupe):
  - **text** = chunk text (or "").
  - **tok** = approx_tokens(text).
  - If **total_tokens + tok ≤ max_tokens:**  
    Append full text to parts; total_tokens += tok.
  - Else (adding the full chunk would exceed budget):  
    - **remain** = max_tokens − total_tokens.  
    - **keep_words** = max(0, int(remain / 1.3)).  
    - Append the first **keep_words** words of **text** to parts; update total_tokens; **stop** (we don’t add more chunks after a truncation in the current logic, so we stay within budget).
- Final **context_text** = concatenation of parts with a separator (e.g. `\n\n---\n\n`).

### Why truncate the last chunk (and not drop it)?

- Using a **prefix** of the last chunk still gives the model the beginning of that thought (often the most relevant part). Dropping the chunk entirely would lose that content. So we prefer “partial last chunk” over “one chunk less”.

### Summary

- **Algorithm:** Approx tokens = words × 1.3; walk chunks in order; add full chunk if fits, else add prefix of chunk of length (remaining_budget / 1.3) words and stop.
- **Role:** Enforce a strict token limit for the LLM context.

---

## 7. Usage Penalty

### What it is

Each chunk can have a **usage_count**: how many times it has already been used for question generation (in the current run or historically). We **down-weight** chunks with high usage so the same chunk isn’t reused too often.

### Formula

- **base_score:** The score the chunk got from the previous stage (e.g. RRF merged score).
- **penalised_score = base_score × (β ^ usage_count)**  
  We use **β = 0.85** (USAGE_PENALTY_BASE).

So:

- usage_count = 0 → factor 1 (no penalty).  
- usage_count = 1 → × 0.85.  
- usage_count = 2 → × 0.7225.  
- usage_count = 5 → × 0.44.  

It’s an **exponential decay** in the number of uses.

### Why exponential (0.85^n)

- **Linear** (e.g. 1 − 0.1×n) can go negative or zero; exponential stays positive and smooth.
- **0.85** means each extra use multiplies the score by 0.85; after a few uses the chunk is much less likely to be chosen, but not hard-banned. So we **spread** usage across chunks without completely excluding popular chunks.

### Where it’s applied

- In **retrieval_engine.retrieve_chunks_for_spec**: after merging FTS + vector via RRF and taking top MAX_CANDIDATES, we multiply each chunk’s merged score by 0.85^usage_count before passing to MMR. So “relevance” in MMR is already usage-penalised.

### Summary

- **Algorithm:** new_score = old_score × (0.85 ^ usage_count).
- **Role:** Prefer less-used chunks when generating multiple questions.

---

## 8. MMR (Maximal Marginal Relevance)

### What it is

**MMR** selects a **small set of items** (e.g. 5 chunks) from a larger candidate set so that the set is both **relevant** (good for the query) and **diverse** (not redundant with each other). It’s a **greedy** algorithm: pick one item at a time by a score that balances relevance and dissimilarity to already-selected items.

### Origin

- From Carbonell & Goldstein (e.g. “The Use of MMR, Diversity-Based Reranking for Reordering Documents and Producing Summaries”, 1998). Used in summarization and retrieval to reduce redundancy.

### Formula (per candidate)

Suppose we already have a set **S** of selected chunks. For a **candidate** chunk **c** (not in S):

- **rel(c)** = relevance of c to the query (in our code: the usage-penalised score from RRF).
- **max_sim(c, S)** = max over s ∈ S of **similarity(c, s)**. We use **cosine(c.embedding, s.embedding)**.

**MMR score:**

```text
MMR(c) = λ × rel(c) − (1 − λ) × max_sim(c, S)
```

We use **λ = 0.7** (MMR_LAMBDA).

- **λ × rel(c):** “How good is c for the query?” — we want to keep this high.  
- **(1−λ) × max_sim(c, S):** “How similar is c to something we already picked?” — we want to keep this **low** (so we subtract it). So the **more** c looks like an already-selected chunk, the **lower** its MMR score.

### Greedy selection (step by step)

- **Input:** List of candidates, each with (chunk, relevance score, embedding); parameter **k** (e.g. 5).
- **Initialization:** S = [] (empty selected set), remaining = copy of candidates.
- **Loop** until |S| = k or remaining is empty:
  - For each candidate **c** in remaining, compute **MMR(c)** with current S (if S is empty, max_sim(c, S) = 0).
  - Pick **c*** with **largest** MMR(c).
  - Add **c*** to S and remove **c*** from remaining.
- **Output:** S (ordered by selection order).

So the **first** chosen chunk is the one with highest relevance (since S is empty, MMR = λ×rel). Each next chunk is the one that best trades off “still relevant” and “not too similar to what we already have”.

### Why λ = 0.7

- **λ = 1:** Pure relevance; no diversity. We’d pick the top 5 by score, which can be very similar to each other.
- **λ = 0:** Pure diversity; relevance ignored. We’d pick the most different chunks, which might be off-topic.
- **λ = 0.7** favours relevance (70%) and diversity (30%). So we stay on-topic but avoid picking five almost-identical chunks.

### Why cosine for “max_sim”

- We already have embeddings for chunks (from indexing). Cosine between two chunk embeddings measures “semantic similarity”; if two chunks have high cosine, they’re about the same thing. So **max_sim(c, S)** answers: “How much does c repeat something we already selected?” Using cosine there is consistent with how we do semantic search elsewhere.

### Summary

- **Algorithm:** Greedy. Repeatedly choose the candidate c that maximizes λ×rel(c) − (1−λ)×max_s∈S cos(c,s); add c to S; repeat until k selected.
- **Parameters:** λ = 0.7, k = 5 (FINAL_CHUNK_COUNT).
- **Role:** From ~40 RRF+penalised candidates, pick 5 that are both relevant and diverse for one question spec.

---

## 9. End-to-end flow (where each algo fits)

1. **User / spec query**  
   → Embed (for vector) and/or pass as string (for FTS).

2. **FTS**  
   → tsvector + plainto_tsquery + ts_rank_cd → ranked list L1 (chunk IDs).

3. **Vector**  
   → Cosine search in Qdrant → ranked list L2 (chunk IDs).

4. **RRF**  
   → Merge L1 and L2 with 1/(60+rank) per list → single ranked list.

5. **(Optional) Keyword rerank**  
   → Rerank top-N of that list by query-term overlap.

6. **Context builder**  
   → Optionally add neighbors (chunk_index ± 1); then fill context up to max_tokens with truncation of the last chunk if needed.

7. **Paper pipeline only:**  
   - Apply **usage penalty** (× 0.85^usage_count) to RRF scores.  
   - Run **MMR** on (candidate, penalised_score, embedding) to get final k chunks per question spec.

This is the full “deep” picture of each algorithm and how they chain together.
