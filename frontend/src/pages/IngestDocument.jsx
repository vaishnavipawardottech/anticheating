import React, { useState } from 'react';
import { Upload, FileText, Send, Sparkles, ArrowLeft, Plus, Trash2, Edit2, Check, X } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import './IngestDocument.css';

const IngestDocument = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preSelectedSubjectId = searchParams.get('subjectId');
  
  const [mode, setMode] = useState(preSelectedSubjectId ? 'existing' : 'new'); // 'new' or 'existing'
  const [existingSubjects, setExistingSubjects] = useState([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState(preSelectedSubjectId || '');
  const [subjectName, setSubjectName] = useState('');
  const [mathMode, setMathMode] = useState(false);
  const [rawToc, setRawToc] = useState('');
  const [normalizedToc, setNormalizedToc] = useState('');
  const [normalizedJson, setNormalizedJson] = useState(null); // Store the JSON structure
  const [selectedFiles, setSelectedFiles] = useState([]); // Changed to array for multiple files
  const [maxPages, setMaxPages] = useState(''); // Optional: only ingest first N pages (e.g. 2 or 3) to save API cost
  const [isProcessingToc, setIsProcessingToc] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSavingIndex, setIsSavingIndex] = useState(false);
  const [viewMode, setViewMode] = useState('structured'); // 'structured' or 'text'
  const [editingUnit, setEditingUnit] = useState(null); // {unitIndex: 0, value: 'New Name'}
  const [editingConcept, setEditingConcept] = useState(null); // {unitIndex: 0, conceptIndex: 1, value: 'New Concept'}

  // Fetch existing subjects when component mounts
  React.useEffect(() => {
    fetchExistingSubjects();
  }, []);

  // Sync normalizedJson to normalizedToc whenever it changes
  React.useEffect(() => {
    if (normalizedJson) {
      let formatted = `Subject: ${normalizedJson.subject}\n\n`;
      normalizedJson.units.forEach((unit, idx) => {
        formatted += `${unit.name}\n`;
        unit.concepts.forEach(concept => {
          formatted += `  - ${concept}\n`;
        });
        if (idx < normalizedJson.units.length - 1) formatted += '\n';
      });
      setNormalizedToc(formatted);
    }
  }, [normalizedJson]);

  const fetchExistingSubjects = async () => {
    try {
      const response = await fetch('http://localhost:8001/subjects/with-stats/all');
      if (response.ok) {
        const data = await response.json();
        setExistingSubjects(data);
      }
    } catch (error) {
      console.error('Error fetching subjects:', error);
    }
  };

  const handleModeChange = (newMode) => {
    setMode(newMode);
    // Reset fields when switching modes
    if (newMode === 'existing') {
      setSubjectName('');
      setMathMode(false);
      setRawToc('');
      setNormalizedToc('');
      setNormalizedJson(null);
    } else {
      setSelectedSubjectId('');
    }
  };

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
      // Add new files to existing ones
      setSelectedFiles(prev => [...prev, ...files]);
    }
    // Reset input to allow selecting the same file again
    e.target.value = '';
  };

  const handleRemoveFile = (indexToRemove) => {
    setSelectedFiles(prev => prev.filter((_, index) => index !== indexToRemove));
  };

  const handleProcessToc = async () => {
    if (!rawToc.trim()) {
      alert('Please enter TOC first');
      return;
    }

    setIsProcessingToc(true);

    try {
      const response = await fetch('http://localhost:8001/structure/normalize', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          raw_text: rawToc,
          subject_hint: subjectName || null
        })
      });

      if (!response.ok) {
        throw new Error('Failed to normalize TOC');
      }

      const data = await response.json();

      // Store the JSON structure for later use
      setNormalizedJson(data);

      // Format normalized TOC
      let formatted = `Subject: ${data.subject}\n\n`;
      data.units.forEach((unit, idx) => {
        formatted += `${unit.name}\n`;
        unit.concepts.forEach(concept => {
          formatted += `  - ${concept}\n`;
        });
        if (idx < data.units.length - 1) formatted += '\n';
      });

      setNormalizedToc(formatted);

      // Set subject name if not already set
      if (!subjectName && data.subject) {
        setSubjectName(data.subject);
      }
    } catch (error) {
      console.error('Error:', error);
      alert('Failed to process TOC. Please try again.');
    } finally {
      setIsProcessingToc(false);
    }
  };

  // Helper functions for structured editing
  const handleAddUnit = () => {
    if (!normalizedJson) return;
    const newJson = { ...normalizedJson };
    newJson.units.push({ name: 'New Unit', concepts: [] });
    setNormalizedJson(newJson);
  };

  const handleRemoveUnit = (unitIndex) => {
    if (!normalizedJson) return;
    const newJson = { ...normalizedJson };
    newJson.units.splice(unitIndex, 1);
    setNormalizedJson(newJson);
  };

  const handleUpdateUnitName = (unitIndex, newName) => {
    if (!normalizedJson) return;
    const newJson = { ...normalizedJson };
    newJson.units[unitIndex].name = newName;
    setNormalizedJson(newJson);
    setEditingUnit(null);
  };

  const handleAddConcept = (unitIndex) => {
    if (!normalizedJson) return;
    const newJson = { ...normalizedJson };
    newJson.units[unitIndex].concepts.push('New Concept');
    setNormalizedJson(newJson);
  };

  const handleRemoveConcept = (unitIndex, conceptIndex) => {
    if (!normalizedJson) return;
    const newJson = { ...normalizedJson };
    newJson.units[unitIndex].concepts.splice(conceptIndex, 1);
    setNormalizedJson(newJson);
  };

  const handleUpdateConcept = (unitIndex, conceptIndex, newValue) => {
    if (!normalizedJson) return;
    const newJson = { ...normalizedJson };
    newJson.units[unitIndex].concepts[conceptIndex] = newValue;
    setNormalizedJson(newJson);
    setEditingConcept(null);
  };


  const handleSaveIndex = async () => {
    if (!normalizedJson) {
      alert('Please process TOC first');
      return;
    }

    setIsSavingIndex(true);

    try {
      console.log('Saving index to database...');

      // Use the stored normalized JSON directly
      const tocData = normalizedJson;

      // Step 1: Create or find subject
      let subjectId;
      const subjectResponse = await fetch('http://localhost:8001/subjects/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: tocData.subject, description: 'Saved from TOC', math_mode: mathMode })
      });

      if (!subjectResponse.ok) {
        // Subject might already exist, try to find it
        const existingSubjects = await fetch('http://localhost:8001/subjects/').then(r => r.json());
        const existing = existingSubjects.find(s => s.name === tocData.subject);
        if (!existing) throw new Error('Failed to create subject');
        subjectId = existing.id;
        console.log(`Using existing subject ID: ${subjectId}`);
      } else {
        subjectId = (await subjectResponse.json()).id;
        console.log(`Created new subject ID: ${subjectId}`);
      }

      // Step 2: Create units and concepts
      let totalConcepts = 0;
      for (const unit of tocData.units) {
        const unitResp = await fetch('http://localhost:8001/units/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: unit.name,
            subject_id: subjectId,
            order: tocData.units.indexOf(unit)
          })
        });

        if (!unitResp.ok) {
          console.error(`Failed to create unit "${unit.name}"`);
          continue;
        }

        const unitData = await unitResp.json();
        console.log(`Created unit: ${unit.name}`);

        // Create concepts for this unit
        for (const conceptName of unit.concepts) {
          // Skip empty or whitespace-only concept names
          if (!conceptName || !conceptName.trim()) {
            console.warn('Skipping empty concept');
            continue;
          }

          const conceptResp = await fetch('http://localhost:8001/concepts/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: conceptName.trim(),
              unit_id: unitData.id,
              order: unit.concepts.indexOf(conceptName),
              diagram_critical: false
            })
          });

          if (!conceptResp.ok) {
            const errorData = await conceptResp.json();
            console.error(`Failed to create concept "${conceptName}":`, errorData);
          } else {
            totalConcepts++;
          }
        }
      }

      console.log(`Index saved successfully!`);
      alert(`Index saved!\n\nSubject: ${tocData.subject}\nUnits: ${tocData.units.length}\nConcepts: ${totalConcepts}\n\nCheck database for results.`);
    } catch (error) {
      console.error('Error:', error);
      alert(`Failed to save index: ${error.message}`);
    } finally {
      setIsSavingIndex(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    // Validation based on mode
    if (mode === 'new') {
      if (!subjectName.trim() || !normalizedToc.trim() || selectedFiles.length === 0) {
        alert('Please fill all fields, process TOC, and upload at least one document');
        return;
      }
    } else {
      // Existing subject mode
      if (!selectedSubjectId || selectedFiles.length === 0) {
        alert('Please select a subject and upload at least one document');
        return;
      }
    }

    setIsSubmitting(true);

    try {
      let subjectId;

      if (mode === 'new') {
        // Original flow for new subjects
        // Step 1: Parse normalized TOC
        console.log('Step 1: Parsing TOC...');
        const tocResponse = await fetch('http://localhost:8001/structure/normalize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ raw_text: normalizedToc, subject_hint: subjectName })
        });
        if (!tocResponse.ok) throw new Error('Failed to parse TOC');
        const tocData = await tocResponse.json();

        // Step 2: Create subject
        console.log('Step 2: Creating subject...');
        const subjectResponse = await fetch('http://localhost:8001/subjects/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: tocData.subject, description: 'Auto-created', math_mode: mathMode })
        });

        if (!subjectResponse.ok) {
          const existingSubjects = await fetch('http://localhost:8001/subjects/').then(r => r.json());
          const existing = existingSubjects.find(s => s.name === tocData.subject);
          if (!existing) throw new Error('Failed to create subject');
          subjectId = existing.id;
        } else {
          subjectId = (await subjectResponse.json()).id;
        }

        // Step 3: Create units and concepts
        console.log('Step 3: Creating structure...');
        for (const unit of tocData.units) {
          const unitResp = await fetch('http://localhost:8001/units/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: unit.name, subject_id: subjectId, order: tocData.units.indexOf(unit) })
          });
          if (!unitResp.ok) continue;
          const unitData = await unitResp.json();

          for (const conceptName of unit.concepts) {
            await fetch('http://localhost:8001/concepts/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: conceptName, unit_id: unitData.id, order: unit.concepts.indexOf(conceptName) })
            });
          }
        }
      } else {
        // Existing subject mode - use selected subject ID
        subjectId = parseInt(selectedSubjectId);
        console.log(`Using existing subject ID: ${subjectId}`);
      }

      // Step 4: Upload and process each document
      let totalDocuments = 0;
      let failedDocuments = 0;

      for (let i = 0; i < selectedFiles.length; i++) {
        const file = selectedFiles[i];
        console.log(`Step 4 (${i + 1}/${selectedFiles.length}): Uploading and processing ${file.name}...`);
        
        try {
          const formData = new FormData();
          formData.append('file', file);
          formData.append('subject_id', subjectId);
          if (maxPages.trim() !== '') {
            const n = parseInt(maxPages, 10);
            if (!isNaN(n) && n > 0) formData.append('max_pages', n);
          }

          const uploadResp = await fetch('http://localhost:8001/documents/upload-and-store', { 
            method: 'POST', 
            body: formData 
          });
          
          if (!uploadResp.ok) {
            const errorData = await uploadResp.json();
            console.error(`Failed to upload ${file.name}:`, errorData);
            failedDocuments++;
            continue;
          }
          
          const documentData = await uploadResp.json();
          console.log(`✓ Uploaded ${file.name} - Document ID: ${documentData.id}, Status: ${documentData.status}`);
          totalDocuments++;
          
        } catch (error) {
          console.error(`Error processing ${file.name}:`, error);
          failedDocuments++;
        }
      }

      const selectedSubject = mode === 'existing' 
        ? existingSubjects.find(s => s.id === parseInt(selectedSubjectId))
        : { name: subjectName };

      const successMessage = `Complete!\n\nSubject: ${selectedSubject?.name || 'Unknown'}\nDocuments Uploaded: ${totalDocuments}\nFailed: ${failedDocuments}\n\nDocuments are now indexed and searchable!`;
      alert(successMessage);

      // Reset form
      if (mode === 'new') {
        setSubjectName('');
        setRawToc('');
        setNormalizedToc('');
        setNormalizedJson(null);
      } else {
        setSelectedSubjectId('');
      }
      setSelectedFiles([]);
    } catch (error) {
      console.error('Error:', error);
      alert(`Failed: ${error.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleBack = () => navigate('/');

  return (
    <div className="ingest-container">
      <div className="ingest-card">
        <div className="ingest-header">
          <button className="back-btn" onClick={handleBack}>
            <ArrowLeft size={20} />
          </button>
          <h1 className="ingest-title">Document Ingestion</h1>
        </div>

        <div className="ingest-content">
          <form onSubmit={handleSubmit} className="ingest-form">
            
            {/* Mode Selection */}
            <div className="form-group">
              <label className="form-label">Select Mode</label>
              <div className="mode-selector">
                <button
                  type="button"
                  className={`mode-btn ${mode === 'new' ? 'active' : ''}`}
                  onClick={() => handleModeChange('new')}
                >
                  New Subject
                </button>
                <button
                  type="button"
                  className={`mode-btn ${mode === 'existing' ? 'active' : ''}`}
                  onClick={() => handleModeChange('existing')}
                >
                  Existing Subject
                </button>
              </div>
            </div>

            {/* Existing Subject Selection */}
            {mode === 'existing' && (
              <div className="form-group">
                <label className="form-label">Select Subject</label>
                <select
                  value={selectedSubjectId}
                  onChange={(e) => setSelectedSubjectId(e.target.value)}
                  className="form-input"
                  required
                >
                  <option value="">-- Choose a subject --</option>
                  {existingSubjects.map(subject => (
                    <option key={subject.id} value={subject.id}>
                      {subject.name} ({subject.unit_count} units, {subject.document_count} docs)
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* New Subject Fields */}
            {mode === 'new' && (
              <>
                <div className="form-group">
                  <label className="form-label">Subject Name</label>
                  <input
                    type="text"
                    value={subjectName}
                    onChange={(e) => setSubjectName(e.target.value)}
                    placeholder="e.g., Human Computer Interaction"
                    className="form-input"
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label ingest-math-mode-label">
                    <input
                      type="checkbox"
                      checked={mathMode}
                      onChange={(e) => setMathMode(e.target.checked)}
                      className="ingest-math-mode-check"
                    />
                    <span>Math Mode</span>
                  </label>
                  <p className="form-hint ingest-math-mode-hint">Use for math-heavy subjects (e.g. Discrete Mathematics). Preserves symbols and extracts figures.</p>
                </div>
                <div className="form-group">
                  <label className="form-label">Table of Contents (Raw)</label>
                  <textarea
                    value={rawToc}
                    onChange={(e) => setRawToc(e.target.value)}
                    placeholder="Paste your syllabus/TOC here..."
                    className="form-textarea"
                    rows="8"
                    required
                  />
                  <button
                    type="button"
                    onClick={handleProcessToc}
                    disabled={isProcessingToc || !rawToc.trim()}
                    className="process-btn"
                  >
                    {isProcessingToc ? (
                      <>
                        <div className="spinner"></div>
                        Processing...
                      </>
                    ) : (
                      <>
                        <Sparkles size={18} />
                        Process TOC
                      </>
                    )}
                  </button>
                </div>

                {normalizedJson && (
                  <div className="form-group toc-preview-group">
                    <div className="toc-header-bar">
                      <label className="form-label">Processed TOC Structure</label>
                      <div className="view-toggle">
                        <button
                          type="button"
                          className={`toggle-btn ${viewMode === 'structured' ? 'active' : ''}`}
                          onClick={() => setViewMode('structured')}
                        >
                          Structured
                        </button>
                        <button
                          type="button"
                          className={`toggle-btn ${viewMode === 'text' ? 'active' : ''}`}
                          onClick={() => setViewMode('text')}
                        >
                          Raw Text
                        </button>
                      </div>
                    </div>

                    {viewMode === 'structured' ? (
                      <div className="toc-structured-editor">
                        {/* Subject Editor */}
                        <div className="toc-subject-editor">
                          <label className="editor-label">Subject:</label>
                          <input
                            type="text"
                            value={normalizedJson.subject}
                            onChange={(e) => setNormalizedJson({ ...normalizedJson, subject: e.target.value })}
                            className="subject-input"
                          />
                        </div>

                        {/* Units Editor */}
                        <div className="toc-units-list">
                          {normalizedJson.units.map((unit, unitIdx) => (
                            <div key={unitIdx} className="toc-unit-block">
                              <div className="unit-header-row">
                                {editingUnit?.unitIndex === unitIdx ? (
                                  <div className="unit-edit-input-group">
                                    <input
                                      type="text"
                                      value={editingUnit.value}
                                      onChange={(e) => setEditingUnit({ ...editingUnit, value: e.target.value })}
                                      className="unit-name-input"
                                      autoFocus
                                    />
                                    <button
                                      type="button"
                                      className="icon-btn success"
                                      onClick={() => handleUpdateUnitName(unitIdx, editingUnit.value)}
                                      title="Save"
                                    >
                                      <Check size={16} />
                                    </button>
                                    <button
                                      type="button"
                                      className="icon-btn cancel"
                                      onClick={() => setEditingUnit(null)}
                                      title="Cancel"
                                    >
                                      <X size={16} />
                                    </button>
                                  </div>
                                ) : (
                                  <>
                                    <h4 className="unit-name">{unit.name}</h4>
                                    <div className="unit-actions">
                                      <button
                                        type="button"
                                        className="icon-btn edit"
                                        onClick={() => setEditingUnit({ unitIndex: unitIdx, value: unit.name })}
                                        title="Edit unit name"
                                      >
                                        <Edit2 size={14} />
                                      </button>
                                      <button
                                        type="button"
                                        className="icon-btn delete"
                                        onClick={() => handleRemoveUnit(unitIdx)}
                                        title="Delete unit"
                                      >
                                        <Trash2 size={14} />
                                      </button>
                                    </div>
                                  </>
                                )}
                              </div>

                              {/* Concepts List */}
                              <div className="concepts-list">
                                {unit.concepts.map((concept, conceptIdx) => (
                                  <div key={conceptIdx} className="concept-item">
                                    {editingConcept?.unitIndex === unitIdx && editingConcept?.conceptIndex === conceptIdx ? (
                                      <div className="concept-edit-group">
                                        <input
                                          type="text"
                                          value={editingConcept.value}
                                          onChange={(e) => setEditingConcept({ ...editingConcept, value: e.target.value })}
                                          className="concept-input"
                                          autoFocus
                                        />
                                        <button
                                          type="button"
                                          className="icon-btn success"
                                          onClick={() => handleUpdateConcept(unitIdx, conceptIdx, editingConcept.value)}
                                          title="Save"
                                        >
                                          <Check size={14} />
                                        </button>
                                        <button
                                          type="button"
                                          className="icon-btn cancel"
                                          onClick={() => setEditingConcept(null)}
                                          title="Cancel"
                                        >
                                          <X size={14} />
                                        </button>
                                      </div>
                                    ) : (
                                      <>
                                        <span className="concept-bullet">•</span>
                                        <span className="concept-text">{concept}</span>
                                        <div className="concept-actions">
                                          <button
                                            type="button"
                                            className="icon-btn edit"
                                            onClick={() => setEditingConcept({ unitIndex: unitIdx, conceptIndex: conceptIdx, value: concept })}
                                            title="Edit concept"
                                          >
                                            <Edit2 size={12} />
                                          </button>
                                          <button
                                            type="button"
                                            className="icon-btn delete"
                                            onClick={() => handleRemoveConcept(unitIdx, conceptIdx)}
                                            title="Delete concept"
                                          >
                                            <Trash2 size={12} />
                                          </button>
                                        </div>
                                      </>
                                    )}
                                  </div>
                                ))}
                                <button
                                  type="button"
                                  className="add-concept-btn"
                                  onClick={() => handleAddConcept(unitIdx)}
                                >
                                  <Plus size={14} />
                                  Add Concept
                                </button>
                              </div>
                            </div>
                          ))}

                          <button
                            type="button"
                            className="add-unit-btn"
                            onClick={handleAddUnit}
                          >
                            <Plus size={16} />
                            Add Unit
                          </button>
                        </div>

                        <p className="form-hint">✓ TOC processed! Edit units and concepts inline.</p>
                      </div>
                    ) : (
                      <div className="toc-text-editor">
                        <textarea
                          value={normalizedToc}
                          onChange={(e) => setNormalizedToc(e.target.value)}
                          className="form-textarea normalized"
                          rows="15"
                        />
                        <p className="form-hint">Raw text view (changes here won't sync with structured view)</p>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}


            <div className="form-group">
              <label className="form-label">Upload Documents</label>
              <div className="file-upload-area">
                <input
                  type="file"
                  id="file-upload"
                  onChange={handleFileChange}
                  accept=".pdf,.pptx,.docx"
                  className="file-input"
                  multiple
                />
                <label htmlFor="file-upload" className="file-upload-label">
                  {selectedFiles.length > 0 ? (
                    <div className="file-selected">
                      <Upload size={24} />
                      <span>Click to add more files</span>
                      <span className="file-hint">PDF, PPTX, or DOCX (max 50MB each)</span>
                    </div>
                  ) : (
                    <div className="file-placeholder">
                      <Upload size={32} />
                      <span>Click to upload or drag and drop</span>
                      <span className="file-hint">PDF, PPTX, or DOCX (max 50MB each)</span>
                    </div>
                  )}
                </label>
              </div>
              
              {selectedFiles.length > 0 && (
                <>
                <div className="form-group" style={{ marginTop: 8 }}>
                  <label className="form-label">Max pages (testing)</label>
                  <input
                    type="number"
                    min={1}
                    max={999}
                    placeholder="Leave empty for full document"
                    value={maxPages}
                    onChange={(e) => setMaxPages(e.target.value)}
                    className="form-input"
                    style={{ maxWidth: 120 }}
                  />
                  <span className="file-hint" style={{ marginLeft: 8 }}>Only ingest first N pages to save OpenAI cost (e.g. 2 or 3)</span>
                </div>
                <div className="selected-files-list">
                  <p className="files-count">{selectedFiles.length} file(s) selected</p>
                  {selectedFiles.map((file, index) => (
                    <div key={index} className="file-item">
                      <div className="file-info">
                        <FileText size={20} />
                        <div className="file-details">
                          <span className="file-name">{file.name}</span>
                          <span className="file-size">
                            {(file.size / 1024 / 1024).toFixed(2)} MB
                          </span>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleRemoveFile(index)}
                        className="remove-file-btn"
                        title="Remove file"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
                </>
              )}
            </div>
          </form>
        </div>

        <div className="ingest-actions">
          {mode === 'new' && (
            <button
              type="button"
              className="save-index-btn"
              onClick={handleSaveIndex}
              disabled={isSavingIndex || !normalizedToc}
            >
              {isSavingIndex ? (
                <>
                  <div className="spinner"></div>
                  Saving...
                </>
              ) : (
                <>
                  <FileText size={18} />
                  Save Index
                </>
              )}
            </button>
          )}
          <button
            type="submit"
            className="submit-btn"
            onClick={handleSubmit}
            disabled={isSubmitting || (mode === 'new' && !normalizedToc) || (mode === 'existing' && !selectedSubjectId)}
          >
            {isSubmitting ? (
              <>
                <div className="spinner"></div>
                Processing Document...
              </>
            ) : (
              <>
                <Send size={18} />
                {mode === 'existing' ? 'Upload Documents' : 'Process Document'}
              </>
            )}
          </button>
          <button
            type="button"
            className="cancel-btn"
            onClick={handleBack}
            disabled={isSubmitting}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

export default IngestDocument;
