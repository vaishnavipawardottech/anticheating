import React, { useState } from 'react';
import { Upload, FileText, Send, Sparkles, ArrowLeft } from 'lucide-react';
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
  const [rawToc, setRawToc] = useState('');
  const [normalizedToc, setNormalizedToc] = useState('');
  const [normalizedJson, setNormalizedJson] = useState(null); // Store the JSON structure
  const [selectedFiles, setSelectedFiles] = useState([]); // Changed to array for multiple files
  const [isProcessingToc, setIsProcessingToc] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSavingIndex, setIsSavingIndex] = useState(false);

  // Fetch existing subjects when component mounts
  React.useEffect(() => {
    fetchExistingSubjects();
  }, []);

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
        body: JSON.stringify({ name: tocData.subject, description: 'Saved from TOC' })
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
          body: JSON.stringify({ name: tocData.subject, description: 'Auto-created' })
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

                {normalizedToc && (
                  <div className="form-group">
                    <label className="form-label">Processed TOC (Editable)</label>
                    <textarea
                      value={normalizedToc}
                      onChange={(e) => setNormalizedToc(e.target.value)}
                      className="form-textarea normalized"
                      rows="10"
                    />
                    <p className="form-hint">✓ TOC processed! You can edit if needed.</p>
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
