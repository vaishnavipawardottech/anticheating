import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Clock, CheckCircle2, Send, AlertTriangle, Video, Shield, Maximize, UserX, Users, Eye, ChevronLeft, ChevronRight } from 'lucide-react';
import { toast } from 'react-toastify';
import Webcam from 'react-webcam';
import * as faceDetection from '@tensorflow-models/face-detection';
import '@tensorflow/tfjs';
import './StudentExamTake.css';

/* ─── Detection constants (from GiveExam.jsx) ──────────────────────────────── */
const DETECTION_INTERVAL_MS = 1000;
const EYE_TRACKING_INTERVAL_MS = 2000;
const GAZE_AWAY_THRESHOLD_SECONDS = 15;
const NO_BLINK_WARNING_THRESHOLD = 30;
const NO_MOVEMENT_WARNING_THRESHOLD = 20;
const EAR_THRESHOLD = 0.2;
const MOVEMENT_THRESHOLD = 5;
const DEPTH_FLATNESS_THRESHOLD = 150;
const DEPTH_CHECK_THROTTLE_MS = 5000;
const RECORDED_VIDEO_WARNING_LIMIT = 3;
const IDENTITY_CHECK_INTERVAL_MS = 15000;
const NO_FACE_TERMINATE_LIMIT = 5;
const IDENTITY_MISMATCH_LIMIT = 3;

const API = 'http://localhost:8001';

const getStudentToken = () => {
    try { const s = JSON.parse(localStorage.getItem('pareeksha_student_session') || 'null'); return s?.token || null; } catch { return null; }
};
const getStudentSession = () => {
    try { return JSON.parse(localStorage.getItem('pareeksha_student_session') || 'null'); } catch { return null; }
};
const studentFetch = (path, opts = {}) => {
    const token = getStudentToken();
    return fetch(`${API}${path}`, { ...opts, headers: { ...(opts.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) } });
};

const enterFullscreen = () => {
    const el = document.documentElement;
    if (el.requestFullscreen) el.requestFullscreen().catch(() => { });
    else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
};
const exitFullscreen = () => { if (document.exitFullscreen) document.exitFullscreen().catch(() => { }); };
const isFullscreen = () => !!(document.fullscreenElement || document.webkitFullscreenElement);

const StudentExamTake = () => {
    const { examId } = useParams();
    const navigate = useNavigate();
    const [examData, setExamData] = useState(null);
    const [currentQ, setCurrentQ] = useState(0);
    const [answers, setAnswers] = useState({});
    const [remaining, setRemaining] = useState(0);
    const [submitted, setSubmitted] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [result, setResult] = useState(null);
    const [showResult, setShowResult] = useState(false);
    const timerRef = useRef(null);

    // Phase gates
    const [isVerified, setIsVerified] = useState(false);
    const [isVerifying, setIsVerifying] = useState(false);
    const [verifyMessage, setVerifyMessage] = useState('');
    const [examStarted, setExamStarted] = useState(false);

    // Proctoring state
    const webcamRef = useRef(null);
    const [warnings, setWarnings] = useState([]);
    const [webcamReady, setWebcamReady] = useState(false);
    const [fullscreenBlocked, setFullscreenBlocked] = useState(false);
    const [faceDetectorReady, setFaceDetectorReady] = useState(false);
    const examIdRef = useRef(examId);
    const startedRef = useRef(false);
    const submittedRef = useRef(false);

    // Multi-face detection refs
    const detectorRef = useRef(null);
    const isMultipleFacesActive = useRef(false);
    const detectionLoopRef = useRef(null);

    // Identity verification refs
    const identityCheckIntervalRef = useRef(null);
    const consecutiveMismatchesRef = useRef(0);
    const consecutiveNoFaceRef = useRef(0);

    // Eye tracking refs
    const faceLandmarkDetectorRef = useRef(null);
    const eyeTrackingLoopRef = useRef(null);
    const gazeAwayStartTimeRef = useRef(null);
    const gazeAwayWarningCountRef = useRef(0);
    const isGazeAwayActiveRef = useRef(false);

    // Liveness / photo spoofing refs
    const lastBlinkTimeRef = useRef(Date.now());
    const blinkCountRef = useRef(0);
    const previousFacePositionRef = useRef(null);
    const noMovementDurationRef = useRef(0);
    const photoSpoofingWarningCountRef = useRef(0);
    const isCheckingLivenessRef = useRef(false);

    // Video spoofing refs
    const recordedVideoWarningCountRef = useRef(0);
    const lastDepthCheckTimeRef = useRef(0);

    const eventCooldownRef = useRef({});

    useEffect(() => { startedRef.current = examStarted; }, [examStarted]);
    useEffect(() => { submittedRef.current = submitted; }, [submitted]);
    const hasEmbedding = getStudentSession()?.student?.has_embedding;

    // ─── Log event ─────────────────────────────────────────────────────
    const logEventToBackend = useCallback(async (eventType, details = '', snapshotBase64 = null) => {
        const now = Date.now();
        if (eventCooldownRef.current[eventType] && now - eventCooldownRef.current[eventType] < 3000) return;
        eventCooldownRef.current[eventType] = now;

        setWarnings(prev => [{ event_type: eventType, details, time: new Date().toLocaleTimeString() }, ...prev].slice(0, 50));

        // Professional toast messages (no emojis)
        const messages = {
            'TAB_SWITCH': 'Tab switch detected — this has been logged.',
            'FULLSCREEN_EXITED': 'Fullscreen exited — please return to fullscreen.',
            'MORE_THAN_1_PERSON_DETECTED': 'Multiple faces detected — only you should be visible.',
            'IDENTITY_MISMATCH': 'Identity mismatch — your face does not match.',
            'NO_FACE_DETECTED': 'No face detected — please face the camera.',
            'SUSPICIOUS_EYE_MOVEMENT': 'Suspicious eye movement — keep your eyes on the screen.',
            'PHOTO_SPOOFING_DETECTED': 'Possible photo detected — ensure you are a live person.',
            'USING_RECORDED_VIDEO': 'Possible recorded video detected — ensure live camera feed.',
        };
        if (messages[eventType]) {
            if (['TAB_SWITCH', 'FULLSCREEN_EXITED', 'MORE_THAN_1_PERSON_DETECTED', 'IDENTITY_MISMATCH', 'PHOTO_SPOOFING_DETECTED', 'USING_RECORDED_VIDEO'].includes(eventType)) {
                toast.error(messages[eventType], { autoClose: 4000 });
            } else {
                toast.warn(messages[eventType], { autoClose: 4000 });
            }
        }

        if (!snapshotBase64 && webcamRef.current) {
            try { snapshotBase64 = webcamRef.current.getScreenshot(); } catch { }
        }
        studentFetch(`/student/exams/${examIdRef.current}/proctoring-event`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event_type: eventType, details, snapshot_base64: snapshotBase64 }),
        }).catch(() => { });
    }, []);

    // ─── Tab switch ────────────────────────────────────────────────────
    useEffect(() => {
        const h = () => { if (startedRef.current && !submittedRef.current && document.hidden) logEventToBackend('TAB_SWITCH', 'Student switched to another tab'); };
        document.addEventListener('visibilitychange', h);
        return () => document.removeEventListener('visibilitychange', h);
    }, [logEventToBackend]);

    // ─── Fullscreen exit ───────────────────────────────────────────────
    useEffect(() => {
        const h = () => {
            if (!startedRef.current || submittedRef.current) return;
            if (!isFullscreen()) { setFullscreenBlocked(true); logEventToBackend('FULLSCREEN_EXITED', 'Student exited fullscreen'); }
            else setFullscreenBlocked(false);
        };
        document.addEventListener('fullscreenchange', h);
        document.addEventListener('webkitfullscreenchange', h);
        return () => { document.removeEventListener('fullscreenchange', h); document.removeEventListener('webkitfullscreenchange', h); };
    }, [logEventToBackend]);

    // ─── Multi-face detection (TF.js MediaPipe, 1s, state-change) ────
    useEffect(() => {
        if (!examStarted || submitted) return;
        let isMounted = true;
        const loadDetector = async () => {
            try {
                const model = faceDetection.SupportedModels.MediaPipeFaceDetector;
                const det = await faceDetection.createDetector(model, { runtime: 'tfjs', maxFaces: 5 });
                if (isMounted) { detectorRef.current = det; setFaceDetectorReady(true); }
            } catch (e) { console.warn('Face detector load failed:', e); }
        };
        loadDetector();

        detectionLoopRef.current = setInterval(async () => {
            const video = webcamRef.current?.video;
            if (!detectorRef.current || !video || video.readyState < 2) return;
            try {
                const faces = await detectorRef.current.estimateFaces(video);
                if (faces.length > 1) {
                    if (isMultipleFacesActive.current) return;
                    const snap = webcamRef.current?.getScreenshot();
                    isMultipleFacesActive.current = true;
                    logEventToBackend('MORE_THAN_1_PERSON_DETECTED', `${faces.length} faces detected`, snap);
                } else {
                    if (isMultipleFacesActive.current) {
                        isMultipleFacesActive.current = false;
                        logEventToBackend('MULTIPLE_FACES_RESOLVED', `Faces reduced to ${faces.length}`);
                    }
                }
            } catch { }
        }, DETECTION_INTERVAL_MS);

        return () => { isMounted = false; clearInterval(detectionLoopRef.current); };
    }, [examStarted, submitted, logEventToBackend]);

    // ─── Eye tracking + liveness + video spoofing (FaceMesh) ─────────
    useEffect(() => {
        if (!examStarted || submitted) return;
        let isMounted = true;

        const loadFaceLandmarks = async () => {
            try {
                const faceLandmarksDetection = await import('@tensorflow-models/face-landmarks-detection');
                const model = faceLandmarksDetection.SupportedModels.MediaPipeFaceMesh;
                const det = await faceLandmarksDetection.createDetector(model, {
                    runtime: 'mediapipe',
                    solutionPath: 'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh',
                    refineLandmarks: true,
                });
                if (isMounted) { faceLandmarkDetectorRef.current = det; }
            } catch (e) { console.warn('FaceMesh load failed:', e); }
        };
        loadFaceLandmarks();

        // Helpers
        const dist = (a, b) => Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);

        const calcEAR = (pts) => {
            if (!pts || pts.length < 6) return 1.0;
            const [p1, p2, p3, p4, p5, p6] = pts;
            const v1 = dist(p2, p6), v2 = dist(p3, p5), h = dist(p1, p4);
            return h === 0 ? 1.0 : (v1 + v2) / (2 * h);
        };

        const detectGaze = (face) => {
            if (!face?.keypoints) return 'CENTER';
            try {
                const kp = face.keypoints;
                const liC = kp[468], riC = kp[473], leI = kp[133], leO = kp[33], reI = kp[362], reO = kp[263];
                if (!liC || !riC || !leI || !leO || !reI || !reO) return 'CENTER';
                const lw = Math.abs(leO.x - leI.x), rw = Math.abs(reO.x - reI.x);
                const lR = (liC.x - leO.x) / lw, rR = (reI.x - riC.x) / rw;
                const hR = (lR + rR) / 2;
                const lCY = (leI.y + leO.y) / 2, rCY = (reI.y + reO.y) / 2;
                const vOff = ((liC.y - lCY) + (riC.y - rCY)) / 2;
                if (hR < 0.15) return 'LEFT'; if (hR > 0.85) return 'RIGHT';
                if (vOff < -5) return 'UP'; if (vOff > 5) return 'DOWN';
                return 'CENTER';
            } catch { return 'CENTER'; }
        };

        eyeTrackingLoopRef.current = setInterval(async () => {
            const video = webcamRef.current?.video;
            if (!faceLandmarkDetectorRef.current || !video || video.readyState < 2) return;

            try {
                const faces = await faceLandmarkDetectorRef.current.estimateFaces(video, { flipHorizontal: false });
                if (faces.length === 0) { gazeAwayStartTimeRef.current = null; return; }
                const face = faces[0];
                const kp = face.keypoints;

                // --- Eye gaze detection ---
                const gaze = detectGaze(face);
                const lookingAway = gaze !== 'CENTER';

                if (lookingAway) {
                    if (!gazeAwayStartTimeRef.current) {
                        gazeAwayStartTimeRef.current = Date.now();
                    } else {
                        const dur = (Date.now() - gazeAwayStartTimeRef.current) / 1000;
                        if (dur >= GAZE_AWAY_THRESHOLD_SECONDS && !isGazeAwayActiveRef.current) {
                            isGazeAwayActiveRef.current = true;
                            gazeAwayWarningCountRef.current += 1;
                            const wc = gazeAwayWarningCountRef.current;
                            const snap = webcamRef.current?.getScreenshot();
                            logEventToBackend('SUSPICIOUS_EYE_MOVEMENT', `Warning ${wc}/3 — eyes ${gaze} for ${dur.toFixed(0)}s`, snap);
                            if (wc >= 3) {
                                toast.error('Exam auto-terminated: Repeated suspicious eye movement.');
                                logEventToBackend('EXAM_AUTO_TERMINATED', '3 eye movement warnings', snap);
                                handleAutoSubmit();
                            }
                            gazeAwayStartTimeRef.current = null;
                            setTimeout(() => { isGazeAwayActiveRef.current = false; }, 5000);
                        }
                    }
                } else {
                    gazeAwayStartTimeRef.current = null;
                    isGazeAwayActiveRef.current = false;
                }

                // --- Liveness / photo spoofing ---
                if (!isCheckingLivenessRef.current) {
                    isCheckingLivenessRef.current = true;

                    // Blink detection
                    const leftEye = [kp[33], kp[160], kp[158], kp[133], kp[153], kp[144]];
                    const rightEye = [kp[362], kp[385], kp[387], kp[263], kp[373], kp[380]];
                    const avgEAR = (calcEAR(leftEye) + calcEAR(rightEye)) / 2;
                    if (avgEAR < EAR_THRESHOLD) { lastBlinkTimeRef.current = Date.now(); blinkCountRef.current++; }

                    // Movement detection
                    const curPos = face.box ? { x: face.box.xMin + face.box.width / 2, y: face.box.yMin + face.box.height / 2 } : null;
                    if (curPos && previousFacePositionRef.current) {
                        const mv = dist(curPos, previousFacePositionRef.current);
                        if (mv > MOVEMENT_THRESHOLD) noMovementDurationRef.current = 0;
                        else if (noMovementDurationRef.current === 0) noMovementDurationRef.current = Date.now();
                    }
                    if (curPos) previousFacePositionRef.current = curPos;

                    const tsBlink = (Date.now() - lastBlinkTimeRef.current) / 1000;
                    const tsMove = noMovementDurationRef.current ? (Date.now() - noMovementDurationRef.current) / 1000 : 0;

                    if (tsBlink > NO_BLINK_WARNING_THRESHOLD && tsMove > NO_MOVEMENT_WARNING_THRESHOLD) {
                        photoSpoofingWarningCountRef.current++;
                        const wc = photoSpoofingWarningCountRef.current;
                        const snap = webcamRef.current?.getScreenshot();
                        logEventToBackend('PHOTO_SPOOFING_DETECTED', `Warning ${wc}/3 — no blinks ${tsBlink.toFixed(0)}s, no movement ${tsMove.toFixed(0)}s`, snap);
                        if (wc >= 3) {
                            toast.error('Exam auto-terminated: Photo spoofing detected.');
                            logEventToBackend('EXAM_AUTO_TERMINATED', '3 photo spoofing warnings', snap);
                            handleAutoSubmit();
                        }
                        lastBlinkTimeRef.current = Date.now();
                        noMovementDurationRef.current = 0;
                    }
                    setTimeout(() => { isCheckingLivenessRef.current = false; }, 5000);
                }

                // --- 3D Video spoofing detection ---
                const now = Date.now();
                if (now - lastDepthCheckTimeRef.current > DEPTH_CHECK_THROTTLE_MS) {
                    lastDepthCheckTimeRef.current = now;
                    if (kp && kp.length >= 468) {
                        const depthPts = [kp[1], kp[33], kp[263], kp[61], kp[291], kp[199]].filter(p => p?.z !== undefined);
                        if (depthPts.length >= 3) {
                            const zVals = depthPts.map(p => p.z || 0);
                            const meanZ = zVals.reduce((a, b) => a + b, 0) / zVals.length;
                            const variance = zVals.reduce((s, z) => s + (z - meanZ) ** 2, 0) / zVals.length;
                            if (variance < DEPTH_FLATNESS_THRESHOLD) {
                                recordedVideoWarningCountRef.current++;
                                const wc = recordedVideoWarningCountRef.current;
                                const snap = webcamRef.current?.getScreenshot();
                                logEventToBackend('USING_RECORDED_VIDEO', `Warning ${wc}/${RECORDED_VIDEO_WARNING_LIMIT} — flat face variance: ${variance.toFixed(2)}`, snap);
                                if (wc >= RECORDED_VIDEO_WARNING_LIMIT) {
                                    toast.error('Exam auto-terminated: Recorded video detected.');
                                    logEventToBackend('EXAM_AUTO_TERMINATED', `${RECORDED_VIDEO_WARNING_LIMIT} video spoofing warnings`, snap);
                                    handleAutoSubmit();
                                }
                            }
                        }
                    }
                }
            } catch (e) { gazeAwayStartTimeRef.current = null; }
        }, EYE_TRACKING_INTERVAL_MS);

        return () => { isMounted = false; clearInterval(eyeTrackingLoopRef.current); };
    }, [examStarted, submitted, logEventToBackend]);

    // ─── Continuous identity verification (15s) ────────────────────────
    useEffect(() => {
        if (!examStarted || submitted || !hasEmbedding) return;
        const verify = async () => {
            const snap = webcamRef.current?.getScreenshot();
            if (!snap) return;
            try {
                const res = await studentFetch(`/student/exams/${examIdRef.current}/continuous-verify`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image_base64: snap }),
                });
                if (!res.ok) return;
                const data = await res.json();
                if (data.skipped) {
                    consecutiveNoFaceRef.current++;
                    consecutiveMismatchesRef.current = 0;
                    const c = consecutiveNoFaceRef.current;
                    logEventToBackend('NO_FACE_DETECTED', `No face ${c}/${NO_FACE_TERMINATE_LIMIT}`, snap);
                    if (c >= NO_FACE_TERMINATE_LIMIT) {
                        toast.error('Exam auto-submitted: No person detected.');
                        logEventToBackend('EXAM_AUTO_TERMINATED', `${NO_FACE_TERMINATE_LIMIT} no-face detections`, snap);
                        handleAutoSubmit();
                    }
                } else if (data.match) {
                    consecutiveMismatchesRef.current = 0;
                    consecutiveNoFaceRef.current = 0;
                } else {
                    consecutiveMismatchesRef.current++;
                    consecutiveNoFaceRef.current = 0;
                    const c = consecutiveMismatchesRef.current;
                    logEventToBackend('IDENTITY_MISMATCH', `Mismatch ${c}/${IDENTITY_MISMATCH_LIMIT}`, snap);
                    if (c >= IDENTITY_MISMATCH_LIMIT) {
                        toast.error('Exam auto-submitted: Identity verification failed.');
                        logEventToBackend('EXAM_AUTO_TERMINATED', `${IDENTITY_MISMATCH_LIMIT} identity mismatches`, snap);
                        handleAutoSubmit();
                    }
                }
            } catch { }
        };
        const t = setTimeout(verify, 5000);
        identityCheckIntervalRef.current = setInterval(verify, IDENTITY_CHECK_INTERVAL_MS);
        return () => { clearTimeout(t); clearInterval(identityCheckIntervalRef.current); };
    }, [examStarted, submitted, hasEmbedding, logEventToBackend]);

    // ─── Keyboard/copy blocks ──────────────────────────────────────────
    useEffect(() => {
        if (!examStarted) return;
        const bC = (e) => { e.preventDefault(); };
        const bK = (e) => {
            if (((e.ctrlKey || e.metaKey) && 'cCaAuUsSpP'.includes(e.key)) || e.key === 'PrintScreen' || e.key === 'Escape') e.preventDefault();
        };
        document.addEventListener('copy', bC); document.addEventListener('cut', bC);
        document.addEventListener('contextmenu', bC); document.addEventListener('keydown', bK);
        return () => { document.removeEventListener('copy', bC); document.removeEventListener('cut', bC); document.removeEventListener('contextmenu', bC); document.removeEventListener('keydown', bK); };
    }, [examStarted]);

    // ─── Load exam ─────────────────────────────────────────────────────
    useEffect(() => {
        studentFetch(`/student/exams/${examId}/start`, { method: 'POST' })
            .then(r => { if (!r.ok) throw new Error('Failed'); return r.json(); })
            .then(data => {
                setExamData(data); setRemaining(data.remaining_seconds || 0);
                const saved = {};
                data.questions?.forEach(q => { if (q.saved_answer) saved[q.pool_question_id] = q.saved_answer; });
                setAnswers(saved);
            })
            .catch(() => navigate('/student/exams'));
    }, [examId]);

    // Timer
    useEffect(() => {
        if (remaining <= 0 || submitted) return;
        timerRef.current = setInterval(() => {
            setRemaining(p => { if (p <= 1) { clearInterval(timerRef.current); handleSubmit(true); return 0; } return p - 1; });
        }, 1000);
        return () => clearInterval(timerRef.current);
    }, [remaining > 0, submitted]);

    const fmt = (s) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

    const handleAnswer = useCallback(async (qid, opt) => {
        setAnswers(p => ({ ...p, [qid]: opt }));
        try { await studentFetch(`/student/exams/${examId}/save-answer`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question_id: qid, selected_option: opt }) }); } catch { }
    }, [examId]);

    const handleAutoSubmit = () => handleSubmit(true);

    const handleSubmit = async (isAuto = false) => {
        if (submitted || submitting) return;
        if (!isAuto && !confirm('Submit exam? This cannot be undone.')) return;
        setSubmitting(true);
        try {
            const res = await studentFetch(`/student/exams/${examId}/submit`, { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                setResult(data); setSubmitted(true); setFullscreenBlocked(false);
                clearInterval(timerRef.current); clearInterval(detectionLoopRef.current);
                clearInterval(identityCheckIntervalRef.current); clearInterval(eyeTrackingLoopRef.current);
                exitFullscreen();
                toast.success(isAuto ? 'Exam auto-submitted.' : 'Exam submitted successfully.');
                logEventToBackend('EXAM_SUBMITTED', isAuto ? 'Auto-submitted' : 'Manually submitted');
                try {
                    const rr = await studentFetch(`/student/exams/${examId}/result`);
                    if (rr.ok) { const rd = await rr.json(); setShowResult(rd.show_result_to_student); if (rd.show_result_to_student) setResult(rd); }
                } catch { }
            }
        } catch { toast.error('Network error'); }
        finally { setSubmitting(false); }
    };

    // ─── Phase 1: Verify identity ──────────────────────────────────────
    const handleVerifyIdentity = async () => {
        if (!webcamRef.current) return;
        setIsVerifying(true); setVerifyMessage('Analyzing facial structure...');
        try {
            const img = webcamRef.current.getScreenshot();
            if (!img) { setVerifyMessage('Camera error — please allow access.'); setIsVerifying(false); return; }
            const res = await studentFetch('/student/verify-face', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image_base64: img }),
            });
            if (res.ok) { const d = await res.json(); setVerifyMessage(d.message); setIsVerified(true); }
            else { const e = await res.json().catch(() => ({})); setVerifyMessage(e.detail || 'Verification failed.'); }
        } catch { setVerifyMessage('Network error — please try again.'); }
        finally { setIsVerifying(false); }
    };

    const handleStartExam = async () => {
        try {
            await document.documentElement.requestFullscreen();
            setExamStarted(true);
            consecutiveMismatchesRef.current = 0; consecutiveNoFaceRef.current = 0;
            gazeAwayWarningCountRef.current = 0; photoSpoofingWarningCountRef.current = 0;
            recordedVideoWarningCountRef.current = 0; lastBlinkTimeRef.current = Date.now();
            noMovementDurationRef.current = 0; lastDepthCheckTimeRef.current = 0;
            setTimeout(() => logEventToBackend('EXAM_STARTED', 'Exam started with proctoring'), 500);
        } catch { toast.error('You must allow fullscreen to start.'); }
    };

    if (!examData) return (
        <div className="exam-loading-screen">
            <div className="exam-loading-spinner"></div>
            <p>Loading exam...</p>
        </div>
    );

    // Phase 0: No embedding
    if (!hasEmbedding) return (
        <div className="exam-gate-screen">
            <div className="exam-gate-card">
                <div className="exam-gate-icon-wrap error"><UserX size={28} /></div>
                <h2 className="exam-gate-title">Biometric Setup Required</h2>
                <p className="exam-gate-desc">
                    You need to register your face before taking proctored exams. Complete the setup in your profile.
                </p>
                <button className="exam-gate-btn" onClick={() => navigate('/student/profile')}>
                    Go to Profile
                </button>
            </div>
        </div>
    );

    // Phase 1: Identity verification
    if (!isVerified) return (
        <div className="exam-gate-screen">
            <div className="exam-gate-card wide">
                <div className="exam-gate-icon-wrap primary"><Shield size={28} /></div>
                <h2 className="exam-gate-title">Identity Verification</h2>
                <p className="exam-gate-subtitle">{examData.exam_title}</p>

                <div className="exam-gate-webcam-wrap">
                    <Webcam ref={webcamRef} audio={false} screenshotFormat="image/jpeg"
                        videoConstraints={{ width: 640, height: 480, facingMode: 'user' }}
                        onUserMedia={() => setWebcamReady(true)} style={{ width: '100%', display: 'block' }} />
                </div>

                {verifyMessage && (
                    <div className={`exam-gate-msg ${verifyMessage.includes('verified') || verifyMessage.includes('Verified') ? 'success' : verifyMessage.includes('failed') || verifyMessage.includes('error') || verifyMessage.includes('Error') || verifyMessage.includes('denied') || verifyMessage.includes('match') ? 'error' : 'info'}`}>
                        {verifyMessage}
                    </div>
                )}

                <button className="exam-gate-btn" onClick={handleVerifyIdentity} disabled={isVerifying || !webcamReady}>
                    {isVerifying ? 'Analyzing...' : 'Verify Identity'}
                </button>
            </div>
        </div>
    );

    // Phase 2: Ready
    if (!examStarted) return (
        <div className="exam-gate-screen">
            <div className="exam-gate-card">
                <div className="exam-gate-icon-wrap success"><CheckCircle2 size={28} /></div>
                <h2 className="exam-gate-title">Identity Confirmed</h2>
                <p className="exam-gate-subtitle">
                    {examData.exam_title} &middot; {examData.duration_minutes} min &middot; {examData.questions?.length} questions
                </p>
                <ul className="exam-gate-rules">
                    <li>Full-screen mode will be enforced. Exiting will be logged.</li>
                    <li>Copying, right-clicking, and shortcuts are blocked.</li>
                    <li>Answers save automatically.</li>
                    <li>Webcam remains active for continuous proctoring.</li>
                    <li>Identity is re-verified every 15 seconds.</li>
                    <li>Eye movement, multiple faces, and absence are monitored.</li>
                    <li>Photo and video spoofing are detected.</li>
                    <li>Violations may auto-submit your exam.</li>
                </ul>
                <button className="exam-gate-btn" onClick={handleStartExam}>
                    Enter Fullscreen & Start Exam
                </button>
            </div>
        </div>
    );

    // Submitted
    if (submitted) return (
        <div className="exam-gate-screen">
            <div className="exam-gate-card">
                <div className="exam-gate-icon-wrap success"><CheckCircle2 size={28} /></div>
                <h2 className="exam-gate-title">Exam Submitted</h2>
                {showResult && result ? (
                    <div className="exam-result-wrap">
                        <span className="exam-result-score">{result.score}/{result.total_questions}</span>
                        <span className="exam-result-pct">{result.percentage}%</span>
                    </div>
                ) : (
                    <p className="exam-gate-desc">Your exam has been submitted. Results will be available once published by the teacher.</p>
                )}
                <button className="exam-gate-btn" onClick={() => { window.location.href = '/student/exams'; }}>
                    Back to Exams
                </button>
            </div>
        </div>
    );

    // Phase 3: Active
    const questions = examData.questions || [];
    const q = questions[currentQ];
    const answeredCount = Object.keys(answers).length;

    const badgeColor = (type) => {
        const map = {
            'TAB_SWITCH': { bg: '#FEE2E2', fg: '#991B1B' },
            'FULLSCREEN_EXITED': { bg: '#FEF3C7', fg: '#92400E' },
            'MORE_THAN_1_PERSON_DETECTED': { bg: '#FCE7F3', fg: '#9D174D' },
            'MULTIPLE_FACES_RESOLVED': { bg: '#D1FAE5', fg: '#065F46' },
            'IDENTITY_MISMATCH': { bg: '#FEE2E2', fg: '#991B1B' },
            'NO_FACE_DETECTED': { bg: '#FEF3C7', fg: '#92400E' },
            'SUSPICIOUS_EYE_MOVEMENT': { bg: '#EDE9FE', fg: '#5B21B6' },
            'PHOTO_SPOOFING_DETECTED': { bg: '#FFF7ED', fg: '#9A3412' },
            'USING_RECORDED_VIDEO': { bg: '#FCE7F3', fg: '#9D174D' },
            'EXAM_STARTED': { bg: '#DBEAFE', fg: '#1E40AF' },
            'EXAM_SUBMITTED': { bg: '#D1FAE5', fg: '#065F46' },
            'EXAM_AUTO_TERMINATED': { bg: '#FEE2E2', fg: '#991B1B' },
        };
        return map[type] || { bg: '#F3F4F6', fg: '#374151' };
    };

    return (
        <div className="exam-active-layout">
            {/* Fullscreen overlay */}
            {fullscreenBlocked && (
                <div className="fs-block-overlay">
                    <div className="fs-block-card">
                        <div className="exam-gate-icon-wrap error"><Maximize size={28} /></div>
                        <h2 className="exam-gate-title">Fullscreen Required</h2>
                        <p className="exam-gate-desc">You exited fullscreen. This violation has been recorded.</p>
                        <p className="fs-block-timer"><Clock size={14} /> Time remaining: <strong>{fmt(remaining)}</strong></p>
                        <button className="exam-gate-btn danger" onClick={enterFullscreen}>Return to Fullscreen</button>
                        <p className="fs-block-note">All exit events are logged and visible to your teacher.</p>
                    </div>
                </div>
            )}

            {/* Sidebar */}
            <aside className="exam-sidebar">
                <div className="exam-sidebar-header">
                    <h3>{examData.exam_title}</h3>
                    <span className="exam-sidebar-progress">{answeredCount}/{questions.length} answered</span>
                </div>
                <div className="exam-sidebar-grid">
                    {questions.map((qq, i) => (
                        <button key={i} onClick={() => setCurrentQ(i)}
                            className={`exam-nav-btn ${i === currentQ ? 'current' : answers[qq.pool_question_id] ? 'answered' : ''}`}>
                            {i + 1}
                        </button>
                    ))}
                </div>
                <div className="exam-sidebar-footer">
                    <button className="exam-submit-btn" onClick={() => handleSubmit(false)} disabled={submitting}>
                        <Send size={13} /> {submitting ? 'Submitting...' : 'Submit Exam'}
                    </button>
                </div>
            </aside>

            {/* Main */}
            <main className="exam-main">
                {/* Top bar */}
                <div className="exam-topbar">
                    <span className="exam-q-indicator">Question {currentQ + 1} of {questions.length}</span>
                    <div className="exam-topbar-right">
                        <div className="exam-proctor-badge">
                            <span className={`proctor-dot ${webcamReady ? 'on' : ''}`}></span>
                            {faceDetectorReady ? 'Proctoring Active' : webcamReady ? 'Loading AI...' : 'Camera...'}
                        </div>
                        <div className={`exam-timer ${remaining < 300 ? 'warn' : ''}`}>
                            <Clock size={14} /> {fmt(remaining)}
                        </div>
                    </div>
                </div>

                <div className="exam-content-row">
                    {/* Question */}
                    {q && (
                        <div className="exam-question-col" onCopy={e => e.preventDefault()} onCut={e => e.preventDefault()}>
                            <div className="exam-question-card" style={{ userSelect: 'none' }}>
                                <p className="exam-question-text">{q.question_text}</p>
                                <div className="exam-options">
                                    {q.options?.map(opt => (
                                        <button key={opt.label}
                                            className={`exam-option ${answers[q.pool_question_id] === opt.label ? 'selected' : ''}`}
                                            onClick={() => handleAnswer(q.pool_question_id, opt.label)}>
                                            <span className="exam-option-letter">{opt.label}</span>
                                            <span className="exam-option-text">{opt.text}</span>
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <div className="exam-nav-row">
                                <button className="exam-nav-btn-prev" onClick={() => setCurrentQ(c => Math.max(0, c - 1))} disabled={currentQ === 0}>
                                    <ChevronLeft size={14} /> Previous
                                </button>
                                <button className="exam-nav-btn-next" onClick={() => setCurrentQ(c => Math.min(questions.length - 1, c + 1))} disabled={currentQ === questions.length - 1}>
                                    Next <ChevronRight size={14} />
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Proctoring panel */}
                    <div className="exam-proctor-panel">
                        <div className="exam-proctor-panel-title"><Video size={13} /> Proctoring</div>
                        <div className="exam-webcam-wrap">
                            <Webcam ref={webcamRef} audio={false} screenshotFormat="image/jpeg" screenshotQuality={0.6}
                                videoConstraints={{ width: 320, height: 240, facingMode: 'user' }}
                                onUserMedia={() => setWebcamReady(true)}
                                onUserMediaError={() => setWebcamReady(false)}
                                className="exam-webcam" mirrored={true} />
                            {!webcamReady && <div className="exam-webcam-placeholder"><Video size={20} /> Connecting...</div>}
                        </div>
                        <div className="exam-alerts-section">
                            <div className="exam-alerts-title"><AlertTriangle size={11} /> Alerts ({warnings.length})</div>
                            <div className="exam-alerts-list">
                                {warnings.length === 0 ? (
                                    <div className="exam-alerts-empty">No events</div>
                                ) : warnings.slice(0, 12).map((evt, i) => {
                                    const bc = badgeColor(evt.event_type);
                                    return (
                                        <div key={i} className="exam-alert-item">
                                            <span className="exam-alert-time">{evt.time}</span>
                                            <span className="exam-alert-badge" style={{ background: bc.bg, color: bc.fg }}>
                                                {evt.event_type.replace(/_/g, ' ')}
                                            </span>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
};

export default StudentExamTake;
