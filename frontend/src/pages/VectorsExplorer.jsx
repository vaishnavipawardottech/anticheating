import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Database, FileText, Hash, CheckCircle, AlertCircle, ArrowLeft } from 'lucide-react';
import './VectorsExplorer.css';

const API_BASE = 'http://localhost:8001';

const VectorsExplorer = () => {
    const navigate = useNavigate();
    const [data, setData] = useState({ elements: [], total: 0, returned: 0 });
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [documentId, setDocumentId] = useState('');
    const [limit, setLimit] = useState(1000);
    const [unembeddedOnly, setUnembeddedOnly] = useState(false);
    const [embeddedBefore, setEmbeddedBefore] = useState('');
    const [category, setCategory] = useState('');
    const [elementType, setElementType] = useState('');
    const [view, setView] = useState('elements'); // 'elements' | 'chunks'
    const [textDisplay, setTextDisplay] = useState('preview'); // 'preview' | 'full'

    const fetchStatus = useCallback(async () => {
        try {
            const docIdNum = documentId.trim() ? parseInt(documentId.trim(), 10) : NaN;
            const params = (!isNaN(docIdNum) && docIdNum > 0) ? `?document_id=${docIdNum}` : '';
            const res = await fetch(`${API_BASE}/documents/embedding-status${params}`);
            if (res.ok) {
                const json = await res.json();
                setStatus(json);
            }
        } catch {
            setStatus(null);
        }
    }, [documentId]);

    const fetchElements = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const params = new URLSearchParams({ limit: String(limit) });
            const docIdNum = documentId.trim() ? parseInt(documentId.trim(), 10) : NaN;
            if (!isNaN(docIdNum) && docIdNum > 0) params.set('document_id', String(docIdNum));
            if (unembeddedOnly) params.set('unembedded_only', 'true');
            if (embeddedBefore) params.set('embedded_before', embeddedBefore);
            if (category) params.set('category', category);
            if (elementType) params.set('element_type', elementType);
            params.set('text_mode', textDisplay);
            const url = view === 'chunks'
                ? `${API_BASE}/documents/chunks-with-embeddings?${params}`
                : `${API_BASE}/documents/elements-with-embeddings?${params}`;
            const res = await fetch(url);
            const contentType = res.headers.get('content-type') || '';
            const isJson = contentType.includes('application/json');
            const json = isJson ? await res.json() : null;

            if (!res.ok) {
                const detail = json?.detail;
                let msg = `Request failed (${res.status})`;
                if (typeof detail === 'string') msg = detail;
                else if (Array.isArray(detail) && detail[0]?.msg) msg = detail[0].msg;
                else if (detail?.msg) msg = detail.msg;
                else if (detail) msg = JSON.stringify(detail);
                throw new Error(msg);
            }
            const list = view === 'chunks' ? (json.chunks || []) : (json.elements || []);
            const total = json.total ?? 0;
            const returned = json.returned ?? list.length;
            setData({ elements: list, total, returned });
        } catch (e) {
            let msg = e.message || (typeof e === 'string' ? e : 'Failed to load');
            if (e.name === 'TypeError' && (e.message || '').includes('fetch')) {
                msg = `Cannot reach backend (${API_BASE}). Is the API running?`;
            }
            setError(msg);
            setData({ elements: [], total: 0, returned: 0 });
        } finally {
            setLoading(false);
        }
    }, [documentId, limit, unembeddedOnly, embeddedBefore, category, elementType, view, textDisplay]);

    useEffect(() => {
        fetchStatus();
    }, [fetchStatus]);

    useEffect(() => {
        fetchElements();
    }, [fetchElements]);

    const badge = status
        ? `${status.embedded_chunks ?? 0}/${status.total_chunks ?? 0} chunks embedded`
        : '—';
    const allChunksOk = status && status.total_chunks > 0 && status.embedded_chunks === status.total_chunks;

    return (
        <div className="vectors-explorer">
            <div className="vectors-header">
                <button className="back-btn" onClick={() => navigate(-1)} type="button" aria-label="Back">
                    <ArrowLeft size={20} />
                </button>
                <h1 className="vectors-title">Elements & chunks</h1>
            </div>

            {status && (
                <div className="vectors-badges">
                    <span className={`vectors-badge ${allChunksOk ? 'vectors-badge-ok' : ''}`}>
                        {allChunksOk ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
                        {badge} {allChunksOk ? '✅' : ''}
                    </span>
                    {status.embedding_model && (
                        <span className="vectors-badge vectors-badge-model">{status.embedding_model}</span>
                    )}
                    {status.by_document?.length > 0 && (
                        <span className="vectors-badge vectors-badge-docs">
                            {status.by_document.map((d) => (
                                <span key={d.document_id} title={d.filename}>
                                    Doc {d.document_id}: {d.badge}
                                </span>
                            ))}
                        </span>
                    )}
                </div>
            )}

            <div className="vectors-toolbar">
                <button className="vectors-refresh vectors-load-all" onClick={() => { fetchStatus(); fetchElements(); }} disabled={loading}>
                    {loading ? 'Loading…' : 'Refresh'}
                </button>
                <span className="vectors-toolbar-divider">|</span>
                <label>
                    Text
                    <select value={textDisplay} onChange={(e) => setTextDisplay(e.target.value)} title="Preview = first 200 chars; Full = entire content">
                        <option value="preview">Preview</option>
                        <option value="full">Full text</option>
                    </select>
                </label>
                <span className="vectors-toolbar-divider">|</span>
                <label>
                    View
                    <select value={view} onChange={(e) => setView(e.target.value)} title="Chunks = merged retrieval units (what search uses)">
                        <option value="elements">Elements (granular)</option>
                        <option value="chunks">Chunks (merged, for retrieval)</option>
                    </select>
                </label>
                <label>
                    Limit
                    <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
                        <option value={100}>100</option>
                        <option value={500}>500</option>
                        <option value={1000}>1000</option>
                        <option value={10000}>10k</option>
                    </select>
                </label>
                <label>
                    Document ID
                    <input
                        type="text"
                        inputMode="numeric"
                        placeholder="optional (e.g. 41)"
                        value={documentId}
                        onChange={(e) => setDocumentId(e.target.value)}
                    />
                </label>
                {view === 'elements' && (
                    <>
                        <label className="vectors-check">
                            <input
                                type="checkbox"
                                checked={unembeddedOnly}
                                onChange={(e) => setUnembeddedOnly(e.target.checked)}
                            />
                            Unembedded only
                        </label>
                        <label>
                            Embedded before
                            <input
                                type="date"
                                value={embeddedBefore}
                                onChange={(e) => setEmbeddedBefore(e.target.value)}
                            />
                        </label>
                        <label>
                            Category
                            <select value={category} onChange={(e) => setCategory(e.target.value)}>
                                <option value="">All</option>
                                <option value="TEXT">TEXT</option>
                                <option value="TABLE">TABLE</option>
                                <option value="DIAGRAM">DIAGRAM</option>
                                <option value="OTHER">OTHER</option>
                            </select>
                        </label>
                        <label>
                            Type
                            <select value={elementType} onChange={(e) => setElementType(e.target.value)}>
                                <option value="">All</option>
                                <option value="Title">Titles only</option>
                                <option value="NarrativeText">NarrativeText</option>
                                <option value="ListItem">ListItem</option>
                                <option value="Title,NarrativeText,ListItem">Primary (Title+Narrative+List)</option>
                            </select>
                        </label>
                    </>
                )}
            </div>

            {error && <p className="vectors-error">{error}</p>}

            <div className="vectors-summary">
                {view === 'chunks'
                    ? `Showing ${data.returned} of ${data.total} chunks (merged; main retrieval index). New uploads use ~500–1000 tokens per chunk; re-ingest a doc to see larger chunks.`
                    : `Showing ${data.returned} of ${data.total} elements (one per parser block)`}
            </div>

            <div className="vectors-table-wrap">
                <table className="vectors-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Doc</th>
                            {view === 'chunks' ? <th>Chunk #</th> : <th>Order</th>}
                            <th><FileText size={14} /> Text ({textDisplay === 'full' ? 'full' : 'preview'})</th>
                            {view === 'chunks' ? <th>Section path</th> : <th>Type</th>}
                            {view === 'elements' && <th>Category</th>}
                            <th><Hash size={14} /> vector_id</th>
                            <th>dim</th>
                        </tr>
                    </thead>
                    <tbody>
                        {view === 'chunks'
                            ? data.elements.map((c) => (
                                <tr key={c.id}>
                                    <td>{c.id}</td>
                                    <td>{c.document_id}</td>
                                    <td>{c.chunk_index}</td>
                                    <td className={textDisplay === 'full' ? 'vectors-text vectors-text-full' : 'vectors-text'}>
                                        {(textDisplay === 'full' && c.text != null) ? c.text : (c.text_preview ?? '—')}
                                    </td>
                                    <td className="vectors-text">{c.section_path ?? '—'}</td>
                                    <td className="vectors-vector-id">{c.vector_id ?? '—'}</td>
                                    <td>{c.embed_dim ?? '—'}</td>
                                </tr>
                            ))
                            : data.elements.map((el) => (
                                <tr key={el.id}>
                                    <td>{el.id}</td>
                                    <td>{el.document_id}</td>
                                    <td>{el.order_index}</td>
                                    <td className={textDisplay === 'full' ? 'vectors-text vectors-text-full' : 'vectors-text'}>
                                        {(textDisplay === 'full' && el.text != null) ? el.text : (el.text_preview ?? '—')}
                                    </td>
                                    <td>{el.element_type}</td>
                                    <td>{el.category}</td>
                                    <td className="vectors-vector-id">{el.vector_id ?? '—'}</td>
                                    <td>{el.embed_dim ?? '—'}</td>
                                </tr>
                            ))}
                    </tbody>
                </table>
            </div>

            {!loading && !error && data.elements.length === 0 && (
                <p className="vectors-empty">
                    {unembeddedOnly ? 'No unembedded elements.' : 'No items found. Ingest a document first.'}
                </p>
            )}
        </div>
    );
};

export default VectorsExplorer;
