import React, { useState } from 'react';
import { Upload, FileText, Send, Sparkles, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import './IngestDocument.css';

const IngestDocument = () => {
  const navigate = useNavigate();
  const [subjectName, setSubjectName] = useState('');
  const [rawToc, setRawToc] = useState('');
  const [normalizedToc, setNormalizedToc] = useState('');
  const [normalizedJson, setNormalizedJson] = useState(null); // Store the JSON structure
  const [selectedFile, setSelectedFile] = useState(null);
  const [isProcessingToc, setIsProcessingToc] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSavingIndex, setIsSavingIndex] = useState(false);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      setSelectedFile(file);
    }
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

    if (!subjectName.trim() || !normalizedToc.trim() || !selectedFile) {
      alert('Please fill all fields, process TOC, and upload a document');
      return;
    }

    setIsSubmitting(true);

    try {
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
      let subjectId;
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

      // Step 4: Parse document
      console.log('Step 4: Parsing document...');
      const formData = new FormData();
      formData.append('file', selectedFile);
      const parseResp = await fetch('http://localhost:8001/documents/parse-and-cleanup', { method: 'POST', body: formData });
      if (!parseResp.ok) throw new Error('Failed to parse document');
      const parseData = await parseResp.json();

      // Step 5: Align elements
      console.log('Step 5: Aligning elements...');
      const alignResp = await fetch('http://localhost:8001/alignment/align', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject_id: subjectId, elements: parseData.elements })
      });
      if (!alignResp.ok) throw new Error('Failed to align');
      const alignData = await alignResp.json();

      alert(`Complete!\n\nSubject: ${tocData.subject}\nElements: ${parseData.total_elements}\nAligned: ${alignData.aligned}\nUnassigned: ${alignData.unassigned}`);

      setSubjectName('');
      setRawToc('');
      setNormalizedToc('');
      setSelectedFile(null);
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

            <div className="form-group">
              <label className="form-label">Upload Document</label>
              <div className="file-upload-area">
                <input
                  type="file"
                  id="file-upload"
                  onChange={handleFileChange}
                  accept=".pdf,.pptx,.docx"
                  className="file-input"
                  required
                />
                <label htmlFor="file-upload" className="file-upload-label">
                  {selectedFile ? (
                    <div className="file-selected">
                      <FileText size={24} />
                      <span>{selectedFile.name}</span>
                      <span className="file-size">
                        ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
                      </span>
                    </div>
                  ) : (
                    <div className="file-placeholder">
                      <Upload size={32} />
                      <span>Click to upload or drag and drop</span>
                      <span className="file-hint">PDF, PPTX, or DOCX (max 50MB)</span>
                    </div>
                  )}
                </label>
              </div>
            </div>
          </form>
        </div>

        <div className="ingest-actions">
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
          <button
            type="submit"
            className="submit-btn"
            onClick={handleSubmit}
            disabled={isSubmitting || !normalizedToc}
          >
            {isSubmitting ? (
              <>
                <div className="spinner"></div>
                Processing Document...
              </>
            ) : (
              <>
                <Send size={18} />
                Process Document
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
