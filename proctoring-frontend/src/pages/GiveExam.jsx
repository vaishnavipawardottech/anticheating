import React, { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import Webcam from "react-webcam";
import axios from "axios";
import * as faceDetection from "@tensorflow-models/face-detection";
import * as faceLandmarksDetection from "@tensorflow-models/face-landmarks-detection";
import * as cocoSsd from "@tensorflow-models/coco-ssd";
import "@tensorflow/tfjs";

// How often (ms) the detection loop runs
const DETECTION_INTERVAL_MS = 1000;
const EYE_TRACKING_INTERVAL_MS = 2000; // Check eyes every 2 seconds
const GAZE_AWAY_THRESHOLD_SECONDS = 10; // Warning after 10 seconds of looking away
const LIVENESS_CHECK_INTERVAL_SECONDS = 30; // Require blink/movement every 30 seconds
const NO_BLINK_WARNING_THRESHOLD = 30; // Warn if no blink for 30 seconds
const NO_MOVEMENT_WARNING_THRESHOLD = 20; // Warn if no movement for 20 seconds
const EAR_THRESHOLD = 0.2; // Eye Aspect Ratio threshold for blink detection
const MOVEMENT_THRESHOLD = 5; // Minimum pixel movement to consider as "alive"
const DEPTH_FLATNESS_THRESHOLD = 150; // Max variance in Z-coords for "flat" face (video/photo)
const DEPTH_CHECK_THROTTLE_MS = 5000; // Check depth every 5 seconds
const RECORDED_VIDEO_WARNING_LIMIT = 3; // Terminate after 3 flat face detections
const PHONE_DETECTION_INTERVAL_MS = 3000; // Check for phones every 3 seconds
const PHONE_DETECTION_WARNING_LIMIT = 3; // Terminate after 3 phone detections
const PHONE_CONFIDENCE_THRESHOLD = 0.3; // Lower threshold for phone detection (30% confidence)

export default function GiveExam() {
  const navigate = useNavigate();
  const webcamRef = useRef(null);

  // Phase 1: Identity Verification State
  const [isVerified, setIsVerified] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState("Please verify your identity to begin the exam.");

  // Phase 2: Active Exam State
  const [isExamStarted, setIsExamStarted] = useState(false);
  const [warnings, setWarnings] = useState([]);
  const [examTimeLeft, setExamTimeLeft] = useState(120); // 2 minutes in seconds
  
  // Identity verification tracking
  const consecutiveMismatchesRef = useRef(0);
  const consecutiveNoFaceRef = useRef(0);
  const identityCheckIntervalRef = useRef(null);

  // --- Multiple-Face Detection Refs ---
  // Using refs (not state) for the throttle flags so they never cause re-renders
  // and are always current inside the setInterval callback closure.
  const detectorRef = useRef(null);           // The TF face detector instance
  const isMultipleFacesActive = useRef(false); // Throttle: true = violation already reported
  const detectionLoopRef = useRef(null);       // The setInterval handle

  // --- Eye Tracking / Gaze Detection Refs ---
  const faceLandmarkDetectorRef = useRef(null); // Face landmarks detector for eye tracking
  const eyeTrackingLoopRef = useRef(null);      // Eye tracking interval handle
  const gazeAwayStartTimeRef = useRef(null);    // Timestamp when eyes started looking away
  const gazeAwayWarningCountRef = useRef(0);    // Count of "looking away" warnings
  const isGazeAwayActiveRef = useRef(false);    // Throttle for gaze warnings

  // --- Liveness Detection (Anti-Spoofing) Refs ---
  const lastBlinkTimeRef = useRef(Date.now());         // Last time a blink was detected
  const blinkCountRef = useRef(0);                     // Number of blinks detected
  const previousFacePositionRef = useRef(null);        // Previous face position for movement detection
  const noMovementDurationRef = useRef(0);             // How long the face has been static
  const photoSpoofingWarningCountRef = useRef(0);      // Count of spoofing warnings
  const isCheckingLivenessRef = useRef(false);         // Throttle for liveness checks

  // --- 3D Depth Detection (Anti-Video Spoofing) Refs ---
  const recordedVideoWarningCountRef = useRef(0);      // Count of flat face detections
  const lastDepthCheckTimeRef = useRef(0);             // Last time depth was checked

  // --- Phone Detection (Anti-Cheating) Refs ---
  const objectDetectorRef = useRef(null);              // COCO-SSD object detector instance
  const phoneDetectionLoopRef = useRef(null);          // Phone detection interval handle
  const phoneWarningCountRef = useRef(0);              // Count of phone detections
  const isPhoneWarningActiveRef = useRef(false);       // Throttle for phone warnings

  // --- 1. VERIFICATION LOGIC ---
  const verifyIdentityForExam = async () => {
    setIsLoading(true);
    setMessage("📸 Analyzing live facial structure...");

    const imageSrc = webcamRef.current.getScreenshot();
    const token = localStorage.getItem("access_token");

    try {
      const response = await axios.post(
        "http://127.0.0.1:8000/api/verify-face",
        { image_base64: imageSrc },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setMessage(`✅ ${response.data.message}`);
      setIsVerified(true);
    } catch (error) {
      setMessage(`❌ Error: ${error.response?.data?.detail || "Verification failed"}`);
      setIsVerified(false);
    } finally {
      setIsLoading(false);
    }
  };

  // --- 2. BACKEND LOGGING FUNCTION ---
  const logEventToBackend = useCallback(async (eventType, details, snapshotBase64 = null) => {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    try {
      await axios.post(
        "http://127.0.0.1:8000/api/exam/log-event",
        { event_type: eventType, details: details, snapshot_base64: snapshotBase64 },
        { headers: { Authorization: `Bearer ${token}` } }
      );
    } catch (error) {
      console.error("Failed to log event:", error);
    }
  }, []);

  // --- 3. START EXAM & LOCK BROWSER ---
  const startExam = async () => {
    try {
      if (document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen();
      }
      setIsExamStarted(true);
      setExamTimeLeft(120);
      // Reset counters at exam start
      consecutiveMismatchesRef.current = 0;
      consecutiveNoFaceRef.current = 0;
      gazeAwayStartTimeRef.current = null;
      gazeAwayWarningCountRef.current = 0;
      isGazeAwayActiveRef.current = false;
      // Reset liveness detection counters
      lastBlinkTimeRef.current = Date.now();
      blinkCountRef.current = 0;
      previousFacePositionRef.current = null;
      noMovementDurationRef.current = 0;
      photoSpoofingWarningCountRef.current = 0;
      isCheckingLivenessRef.current = false;
      // Reset 3D depth detection counters
      recordedVideoWarningCountRef.current = 0;
      lastDepthCheckTimeRef.current = 0;
      // Reset phone detection counters
      phoneWarningCountRef.current = 0;
      isPhoneWarningActiveRef.current = false;
      logEventToBackend("EXAM_STARTED", "Student entered the exam and went full-screen.");
    } catch (err) {
      alert("⚠️ You must allow full-screen mode to start the exam.");
    }
  };

  const handleLogout = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    localStorage.clear();
    navigate("/login");
  };

  const handleSubmitExam = async () => {
    if (window.confirm("Are you sure you want to submit your exam?")) {
      logEventToBackend("EXAM_SUBMITTED", "Student submitted the exam.");
      
      // Exit fullscreen
      if (document.fullscreenElement) {
        document.exitFullscreen();
      }
      
      // Delay to allow event to be queued
      setTimeout(() => {
        setIsExamStarted(false);
        setIsVerified(false);
        navigate("/login");
      }, 500);
    }
  };

  // --- 4. MULTIPLE FACE DETECTION HOOK ---
  useEffect(() => {
    if (!isExamStarted) return;

    let isMounted = true;

    // Load the TensorFlow MediaPipe face detector once
    const loadDetector = async () => {
      const model = faceDetection.SupportedModels.MediaPipeFaceDetector;
      const detector = await faceDetection.createDetector(model, {
        runtime: "tfjs",      // runs fully in-browser, no extra server needed
        maxFaces: 5,          // cap at 5 so the model doesn't over-search
      });
      if (isMounted) detectorRef.current = detector;
    };

    loadDetector();

    // --- STATE-CHANGE DETECTION LOOP ---
    // Runs every DETECTION_INTERVAL_MS (1 second).
    // Only fires an API call when the state CHANGES — not on every frame.
    detectionLoopRef.current = setInterval(async () => {
      // Guard: only run if detector is ready and the webcam video is live
      const video = webcamRef.current?.video;
      if (!detectorRef.current || !video || video.readyState < 2) return;

      const faces = await detectorRef.current.estimateFaces(video);
      const multipleFacesNow = faces.length > 1;

      if (multipleFacesNow) {
        // --- THROTTLE CHECK ---
        // If the violation is already active, do NOTHING (skip the API call entirely)
        if (isMultipleFacesActive.current) return;

        // Multiple faces detected immediately. Take ONE snapshot and fire ONE API request, then flip the flag.
        const snapshot = webcamRef.current?.getScreenshot();
        isMultipleFacesActive.current = true;   // 🔒 ARMED: prevent repeated events while faces are present

        setWarnings((prev) => [
          ...prev,
          `⚠️ MORE THAN 1 PERSON DETECTED at ${new Date().toLocaleTimeString()}: Another person was detected nearby.`,
        ]);

        logEventToBackend(
          "MORE_THAN_1_PERSON_DETECTED",
          `${faces.length} faces detected. Snapshot captured at ${new Date().toISOString()}.`,
          snapshot
        );
      } else {
        // --- RESET ---
        // Faces dropped back to 1 or 0. Re-arm the system.
        if (isMultipleFacesActive.current) {
          // The extra person(s) just left — log the resolution and immediately re-arm
          // so the next detection (if multiple faces appear again) will trigger a new event.
          isMultipleFacesActive.current = false;  // 🔓 DISARMED: ready for the next violation
          logEventToBackend(
            "MULTIPLE_FACES_RESOLVED",
            `Faces count reduced to ${faces.length}. System re-armed for next detection.`
          );
        }
      }
    }, DETECTION_INTERVAL_MS);

    return () => {
      isMounted = false;
      clearInterval(detectionLoopRef.current);
    };
  }, [isExamStarted, logEventToBackend]);

  // --- 4a. EYE TRACKING / GAZE DETECTION HOOK ---
  useEffect(() => {
    if (!isExamStarted) return;

    let isMounted = true;

    // Load MediaPipe FaceMesh for eye landmark detection
    const loadFaceLandmarkDetector = async () => {
      try {
        console.log("🔄 Loading face landmark detector...");
        const model = faceLandmarksDetection.SupportedModels.MediaPipeFaceMesh;
        console.log("📦 Model:", model);
        
        const detector = await faceLandmarksDetection.createDetector(model, {
          runtime: "mediapipe",
          solutionPath: "https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh",
          refineLandmarks: true, // Enable iris tracking for accurate eye position
        });
        
        console.log("✅ Detector created:", detector);
        console.log("✅ Has estimateFaces method:", typeof detector.estimateFaces);
        
        if (isMounted) {
          faceLandmarkDetectorRef.current = detector;
          console.log("👁️ Eye tracking initialized successfully");
        }
      } catch (error) {
        console.error("❌ Failed to load eye tracking model:", error);
        console.error("Error details:", error.message, error.stack);
      }
    };

    loadFaceLandmarkDetector();

    // Helper function to calculate distance between two points
    const calculateDistance = (p1, p2) => {
      const dx = p1.x - p2.x;
      const dy = p1.y - p2.y;
      return Math.sqrt(dx * dx + dy * dy);
    };

    // Calculate Eye Aspect Ratio (EAR) for blink detection
    // EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
    // Returns low value when eye is closed (blink)
    const calculateEAR = (eyeLandmarks) => {
      if (!eyeLandmarks || eyeLandmarks.length < 6) return 1.0;
      
      const [p1, p2, p3, p4, p5, p6] = eyeLandmarks;
      
      // Vertical distances
      const vertical1 = calculateDistance(p2, p6);
      const vertical2 = calculateDistance(p3, p5);
      
      // Horizontal distance
      const horizontal = calculateDistance(p1, p4);
      
      // Avoid division by zero
      if (horizontal === 0) return 1.0;
      
      return (vertical1 + vertical2) / (2.0 * horizontal);
    };

    // Detect blink by checking if EAR drops below threshold
    const detectBlink = (face) => {
      if (!face || !face.keypoints) return false;
      
      try {
        const keypoints = face.keypoints;
        
        // Left eye landmarks (6 points): outer, top, top-inner, inner, bottom-inner, bottom
        const leftEye = [
          keypoints[33],   // p1: Left eye left corner
          keypoints[160],  // p2: Left eye top
          keypoints[158],  // p3: Left eye top inner
          keypoints[133],  // p4: Left eye right corner
          keypoints[153],  // p5: Left eye bottom inner
          keypoints[144]   // p6: Left eye bottom
        ];
        
        // Right eye landmarks (6 points)
        const rightEye = [
          keypoints[362],  // p1: Right eye right corner
          keypoints[385],  // p2: Right eye top
          keypoints[387],  // p3: Right eye top inner
          keypoints[263],  // p4: Right eye left corner
          keypoints[373],  // p5: Right eye bottom inner
          keypoints[380]   // p6: Right eye bottom
        ];
        
        const leftEAR = calculateEAR(leftEye);
        const rightEAR = calculateEAR(rightEye);
        const avgEAR = (leftEAR + rightEAR) / 2.0;
        
        // Blink detected if average EAR is below threshold
        return avgEAR < EAR_THRESHOLD;
      } catch (error) {
        console.error("Blink detection error:", error);
        return false;
      }
    };

    // Detect face movement by comparing current position with previous
    const detectFaceMovement = (face) => {
      if (!face || !face.box) return 0;
      
      const currentPosition = {
        x: face.box.xMin + face.box.width / 2,
        y: face.box.yMin + face.box.height / 2
      };
      
      if (!previousFacePositionRef.current) {
        previousFacePositionRef.current = currentPosition;
        return 0;
      }
      
      const distance = calculateDistance(currentPosition, previousFacePositionRef.current);
      previousFacePositionRef.current = currentPosition;
      
      return distance;
    };

    // Detect 3D depth/flatness - Videos/photos are flat, real faces have 3D depth
    const detect3DDepth = (face) => {
      if (!face || !face.keypoints || face.keypoints.length < 468) return { isFlatFace: false, variance: 0 };
      
      try {
        const keypoints = face.keypoints;
        
        // Sample key facial landmarks that should have varying Z-depth
        const depthPoints = [
          keypoints[1],    // Nose tip (should protrude)
          keypoints[33],   // Left eye corner
          keypoints[263],  // Right eye corner
          keypoints[61],   // Left cheek
          keypoints[291],  // Right cheek
          keypoints[199],  // Chin
        ].filter(p => p && p.z !== undefined);
        
        if (depthPoints.length < 3) return { isFlatFace: false, variance: 0 };
        
        // Calculate Z-coordinate variance
        const zValues = depthPoints.map(p => p.z || 0);
        const meanZ = zValues.reduce((a, b) => a + b, 0) / zValues.length;
        const variance = zValues.reduce((sum, z) => sum + Math.pow(z - meanZ, 2), 0) / zValues.length;
        
        // Low variance means all points are at same depth = flat surface (video/photo)
        const isFlatFace = variance < DEPTH_FLATNESS_THRESHOLD;
        
        return { isFlatFace, variance };
      } catch (error) {
        console.error("3D depth detection error:", error);
        return { isFlatFace: false, variance: 0 };
      }
    };

    // Calculate gaze direction from eye landmarks
    const detectGazeDirection = (face) => {
      if (!face || !face.keypoints) {
        console.log("No face or keypoints detected");
        return "CENTER";
      }

      try {
        // MediaPipe FaceMesh landmark indices (with refineLandmarks=true)
        // Left eye: inner corner (133), outer corner (33)
        // Right eye: inner corner (362), outer corner (263)
        // Left iris center: 468
        // Right iris center: 473

        const keypoints = face.keypoints;
        
        // Get specific landmark points
        const leftIrisCenter = keypoints[468];
        const rightIrisCenter = keypoints[473];
        const leftEyeInner = keypoints[133];
        const leftEyeOuter = keypoints[33];
        const rightEyeInner = keypoints[362];
        const rightEyeOuter = keypoints[263];

        if (!leftIrisCenter || !rightIrisCenter || !leftEyeInner || !leftEyeOuter || !rightEyeInner || !rightEyeOuter) {
          console.log("Missing eye landmarks");
          return "CENTER";
        }

        // Calculate eye width (distance between corners)
        const leftEyeWidth = Math.abs(leftEyeOuter.x - leftEyeInner.x);
        const rightEyeWidth = Math.abs(rightEyeOuter.x - rightEyeInner.x);

        // Calculate normalized iris position (0 = outer corner, 1 = inner corner)
        const leftIrisRatio = (leftIrisCenter.x - leftEyeOuter.x) / leftEyeWidth;
        const rightIrisRatio = (rightEyeInner.x - rightIrisCenter.x) / rightEyeWidth;

        // Average the ratios from both eyes
        const horizontalRatio = (leftIrisRatio + rightIrisRatio) / 2;

        // For vertical: compare iris Y position with eye corners
        const leftEyeCenterY = (leftEyeInner.y + leftEyeOuter.y) / 2;
        const rightEyeCenterY = (rightEyeInner.y + rightEyeOuter.y) / 2;
        
        const leftVerticalOffset = leftIrisCenter.y - leftEyeCenterY;
        const rightVerticalOffset = rightIrisCenter.y - rightEyeCenterY;
        const verticalOffset = (leftVerticalOffset + rightVerticalOffset) / 2;

        // Log for debugging
        console.log(`Gaze - H: ${horizontalRatio.toFixed(2)}, V: ${verticalOffset.toFixed(2)}`);

        // Determine direction with STRICT thresholds to avoid false positives
        // Horizontal: < 0.15 = LEFT, > 0.85 = RIGHT, otherwise CENTER
        // Vertical: < -5 = UP, > 5 = DOWN, otherwise CENTER

        if (horizontalRatio < 0.15) {
          return "LEFT";
        } else if (horizontalRatio > 0.85) {
          return "RIGHT";
        } else if (verticalOffset < -5) {
          return "UP";
        } else if (verticalOffset > 5) {
          return "DOWN";
        }

        return "CENTER";
      } catch (error) {
        console.error("Gaze detection error:", error);
        return "CENTER";
      }
    };

    // Eye tracking detection loop
    eyeTrackingLoopRef.current = setInterval(async () => {
      const video = webcamRef.current?.video;
      
      if (!faceLandmarkDetectorRef.current) {
        console.log("⏳ Face landmark detector not ready yet...");
        return;
      }
      
      if (!video) {
        console.log("⏳ Video element not available...");
        return;
      }
      
      if (video.readyState < 2) {
        console.log(`⏳ Video not ready (readyState: ${video.readyState})...`);
        return;
      }

      try {
        console.log("🔍 Attempting to detect face landmarks...");
        const faces = await faceLandmarkDetectorRef.current.estimateFaces(video, {
          flipHorizontal: false,
        });
        
        console.log(`📊 Detected ${faces.length} face(s) with landmarks`);
        
        if (faces.length === 0) {
          // No face detected, reset gaze tracking
          gazeAwayStartTimeRef.current = null;
          console.warn("⚠️ No face detected for eye tracking");
          return;
        }
        
        console.log(`📍 Face has ${faces[0].keypoints?.length || 0} keypoints`);

        const gazeDirection = detectGazeDirection(faces[0]);
        const isLookingAway = gazeDirection !== "CENTER";

        console.log(`👁️ Current gaze: ${gazeDirection}`);

        if (isLookingAway) {
          // Student is looking away
          if (!gazeAwayStartTimeRef.current) {
            // Start tracking the duration
            gazeAwayStartTimeRef.current = Date.now();
            console.warn(`⚠️ ALERT: Student looking ${gazeDirection} - timer started`);
          } else {
            // Check how long they've been looking away
            const duration = (Date.now() - gazeAwayStartTimeRef.current) / 1000; // seconds
            console.log(`⏱️ Looking ${gazeDirection} for ${duration.toFixed(1)}s / ${GAZE_AWAY_THRESHOLD_SECONDS}s`);
            
            if (duration >= GAZE_AWAY_THRESHOLD_SECONDS && !isGazeAwayActiveRef.current) {
              // Exceeded 10 seconds - trigger warning
              isGazeAwayActiveRef.current = true;
              gazeAwayWarningCountRef.current += 1;
              const warningCount = gazeAwayWarningCountRef.current;

              console.warn(`⚠️ GAZE AWAY WARNING #${warningCount} - Looking ${gazeDirection} for ${duration.toFixed(1)}s`);

              const snapshot = webcamRef.current?.getScreenshot();
              
              setWarnings((prev) => [
                ...prev,
                `👁️ EYE MOVEMENT WARNING #${warningCount} at ${new Date().toLocaleTimeString()}: Eyes looking ${gazeDirection} for more than 10 seconds. WARNING: Exam will be terminated after 3 occurrences.`,
              ]);

              logEventToBackend(
                "SUSPICIOUS_EYE_MOVEMENT",
                `Warning #${warningCount} of 3. Eyes looking ${gazeDirection} for ${duration.toFixed(1)} seconds.`,
                snapshot
              );

              // Check if we've reached 3 warnings
              if (warningCount >= 3) {
                console.error("🛑 AUTO-TERMINATING exam due to 3 suspicious eye movement warnings");
                alert("⛔ EXAM TERMINATED: Suspicious eye movement detected 3 times. Eyes were consistently looking away from the screen.");
                
                logEventToBackend(
                  "EXAM_AUTO_TERMINATED",
                  "Exam terminated due to 3 SUSPICIOUS_EYE_MOVEMENT events. Student repeatedly looking away from screen.",
                  snapshot
                );
                
                if (document.fullscreenElement) {
                  document.exitFullscreen();
                }
                
                setTimeout(() => {
                  setIsExamStarted(false);
                  setIsVerified(false);
                  navigate("/login");
                }, 1000);
              }

              // Reset the start time after warning
              gazeAwayStartTimeRef.current = null;
              
              // Reset throttle after 5 seconds to allow next detection
              setTimeout(() => {
                isGazeAwayActiveRef.current = false;
              }, 5000);
            }
          }
        } else {
          // Student is looking at the screen - reset tracking
          if (gazeAwayStartTimeRef.current) {
            const duration = (Date.now() - gazeAwayStartTimeRef.current) / 1000;
            console.log(`✅ Student looking at screen again (was away for ${duration.toFixed(1)}s)`);
            gazeAwayStartTimeRef.current = null;
            isGazeAwayActiveRef.current = false;
          }
        }

        // --- LIVENESS DETECTION (Anti-Photo Spoofing) ---
        if (!isCheckingLivenessRef.current) {
          isCheckingLivenessRef.current = true;
          
          // 1. Check for blinks
          const isBlink = detectBlink(faces[0]);
          if (isBlink) {
            lastBlinkTimeRef.current = Date.now();
            blinkCountRef.current += 1;
            console.log(`👁️‍🗨️ Blink detected! Total blinks: ${blinkCountRef.current}`);
          }
          
          // 2. Check for face movement
          const movement = detectFaceMovement(faces[0]);
          if (movement > MOVEMENT_THRESHOLD) {
            noMovementDurationRef.current = 0; // Reset if movement detected
            console.log(`🤸 Face movement detected: ${movement.toFixed(1)} pixels`);
          } else {
            // No significant movement
            if (noMovementDurationRef.current === 0) {
              noMovementDurationRef.current = Date.now();
            }
          }
          
          // 3. Check for liveness violations
          const timeSinceLastBlink = (Date.now() - lastBlinkTimeRef.current) / 1000;
          const timeWithoutMovement = noMovementDurationRef.current 
            ? (Date.now() - noMovementDurationRef.current) / 1000 
            : 0;
          
          console.log(`👁️ Liveness check - No blink: ${timeSinceLastBlink.toFixed(1)}s, No movement: ${timeWithoutMovement.toFixed(1)}s`);
          
          // Trigger warning if BOTH no blink AND no movement for extended period
          const noBlink = timeSinceLastBlink > NO_BLINK_WARNING_THRESHOLD;
          const noMovement = timeWithoutMovement > NO_MOVEMENT_WARNING_THRESHOLD;
          
          if (noBlink && noMovement) {
            photoSpoofingWarningCountRef.current += 1;
            const warningCount = photoSpoofingWarningCountRef.current;
            
            console.warn(`🚨 PHOTO SPOOFING WARNING #${warningCount} - No blinks (${timeSinceLastBlink.toFixed(1)}s) and no movement (${timeWithoutMovement.toFixed(1)}s)`);
            
            const snapshot = webcamRef.current?.getScreenshot();
            
            setWarnings((prev) => [
              ...prev,
              `📸 PHOTO SPOOFING WARNING #${warningCount} at ${new Date().toLocaleTimeString()}: No blinks for ${timeSinceLastBlink.toFixed(0)}s and no movement for ${timeWithoutMovement.toFixed(0)}s. Possible photo attack! WARNING: Exam will be terminated after 3 occurrences.`,
            ]);
            
            logEventToBackend(
              "PHOTO_SPOOFING_DETECTED",
              `Warning #${warningCount} of 3. No blinks for ${timeSinceLastBlink.toFixed(1)}s and no face movement for ${timeWithoutMovement.toFixed(1)}s. Possible photo/video spoofing.`,
              snapshot
            );
            
            // Check if we've reached 3 warnings
            if (warningCount >= 3) {
              console.error("🛑 AUTO-TERMINATING exam due to 3 photo spoofing warnings");
              alert("⛔ EXAM TERMINATED: Photo spoofing detected 3 times. No natural blinks or movements detected. This appears to be a photo or video instead of a live person.");
              
              logEventToBackend(
                "EXAM_AUTO_TERMINATED",
                "Exam terminated due to 3 PHOTO_SPOOFING_DETECTED events. No natural blinks or face movements detected.",
                snapshot
              );
              
              if (document.fullscreenElement) {
                document.exitFullscreen();
              }
              
              setTimeout(() => {
                setIsExamStarted(false);
                setIsVerified(false);
                navigate("/login");
              }, 1000);
            }
            
            // Reset counters to detect next violation
            lastBlinkTimeRef.current = Date.now();
            noMovementDurationRef.current = 0;
          }
          
          // Reset throttle after check
          setTimeout(() => {
            isCheckingLivenessRef.current = false;
          }, 5000);
        }

        // --- 3D DEPTH DETECTION (Anti-Recorded Video Spoofing) ---
        const now = Date.now();
        const timeSinceLastDepthCheck = now - lastDepthCheckTimeRef.current;
        
        // Check depth periodically (throttled)
        if (timeSinceLastDepthCheck > DEPTH_CHECK_THROTTLE_MS) {
          lastDepthCheckTimeRef.current = now;
          
          const depthResult = detect3DDepth(faces[0]);
          
          if (depthResult.isFlatFace) {
            recordedVideoWarningCountRef.current += 1;
            const warningCount = recordedVideoWarningCountRef.current;
            
            console.warn(`🚨 RECORDED VIDEO WARNING #${warningCount} - Flat face detected. Variance: ${depthResult.variance.toFixed(2)} (threshold: ${DEPTH_FLATNESS_THRESHOLD}). Possible video/photo!`);
            
            const snapshot = webcamRef.current?.getScreenshot();
            
            setWarnings((prev) => [
              ...prev,
              `🎥 RECORDED VIDEO WARNING #${warningCount} at ${new Date().toLocaleTimeString()}: Flat surface detected (depth variance: ${depthResult.variance.toFixed(2)}). Possible pre-recorded video or photo! WARNING: Exam will be terminated after ${RECORDED_VIDEO_WARNING_LIMIT} occurrences.`,
            ]);
            
            logEventToBackend(
              "USING_RECORDED_VIDEO",
              `Warning #${warningCount} of ${RECORDED_VIDEO_WARNING_LIMIT}. Flat face detected with depth variance ${depthResult.variance.toFixed(2)}. Possible pre-recorded video or photo displayed on screen.`,
              snapshot
            );
            
            // Check if we've reached warning limit
            if (warningCount >= RECORDED_VIDEO_WARNING_LIMIT) {
              console.error("🛑 AUTO-TERMINATING exam due to 3 recorded video detections");
              alert("⛔ EXAM TERMINATED: Recorded video detected 3 times. The face appears flat (2D) like a video or photo on a screen instead of a real 3D person.");
              
              logEventToBackend(
                "EXAM_AUTO_TERMINATED",
                `Exam terminated due to ${RECORDED_VIDEO_WARNING_LIMIT} USING_RECORDED_VIDEO events. Flat face consistently detected.`,
                snapshot
              );
              
              if (document.fullscreenElement) {
                document.exitFullscreen();
              }
              
              setTimeout(() => {
                setIsExamStarted(false);
                setIsVerified(false);
                navigate("/login");
              }, 1000);
            }
          } else {
            // Real 3D face detected - log for transparency
            console.log(`✅ Real 3D face detected - Depth variance: ${depthResult.variance.toFixed(2)}`);
          }
        }

      } catch (error) {
        console.error("❌ Eye tracking error:", error);
        console.error("Error details:", error.message, error.stack);
        // Reset on error
        gazeAwayStartTimeRef.current = null;
      }
    }, EYE_TRACKING_INTERVAL_MS);

    return () => {
      isMounted = false;
      clearInterval(eyeTrackingLoopRef.current);
    };
  }, [isExamStarted, logEventToBackend, navigate]);

  // --- 4a2. PHONE DETECTION HOOK (Anti-Cheating) ---
  useEffect(() => {
    if (!isExamStarted) return;

    let isMounted = true;

    // Load COCO-SSD object detection model
    const loadObjectDetector = async () => {
      try {
        console.log("📱 Loading COCO-SSD object detector for phone detection...");
        const detector = await cocoSsd.load();
        
        if (isMounted) {
          objectDetectorRef.current = detector;
          console.log("✅ Phone detection initialized successfully");
        }
      } catch (error) {
        console.error("❌ Failed to load object detector:", error);
      }
    };

    loadObjectDetector();

    // Phone detection loop
    phoneDetectionLoopRef.current = setInterval(async () => {
      const video = webcamRef.current?.video;
      
      if (!objectDetectorRef.current) {
        console.log("⏳ Object detector not ready yet...");
        return;
      }
      
      if (!video) {
        console.log("⏳ Video element not available for phone detection...");
        return;
      }
      
      if (video.readyState < 2) {
        console.log(`⏳ Video not ready for phone detection (readyState: ${video.readyState})...`);
        return;
      }

      try {
        console.log("📱 Running phone detection check...");
        
        // Detect objects in the video frame
        const predictions = await objectDetectorRef.current.detect(video);
        
        // Log all detected objects for debugging
        if (predictions.length > 0) {
          console.log(`📦 Detected ${predictions.length} object(s):`, 
            predictions.map(p => `${p.class} (${(p.score * 100).toFixed(1)}%)`).join(', ')
          );
          const uniqueClasses = [...new Set(predictions.map(p => p.class))];
          console.log(`🔍 Unique classes detected: ${uniqueClasses.join(", ")}`);
          console.log(`🎯 Looking for: 'cell phone' class`);
        } else {
          console.log("📦 No objects detected in frame");
        }
        
        // Check if any detected object is a cell phone
        const phoneDetected = predictions.some(prediction => 
          prediction.class === 'cell phone' && prediction.score > PHONE_CONFIDENCE_THRESHOLD
        );
        
        // Also log if phone detected with low confidence
        const lowConfidencePhone = predictions.find(p => p.class === 'cell phone');
        if (lowConfidencePhone) {
          if (lowConfidencePhone.score <= PHONE_CONFIDENCE_THRESHOLD) {
            console.log(`📱 Phone detected but confidence too low: ${(lowConfidencePhone.score * 100).toFixed(1)}% (threshold: ${PHONE_CONFIDENCE_THRESHOLD * 100}%)`);
          } else {
            console.log(`📱 ✅ PHONE DETECTED! Confidence: ${(lowConfidencePhone.score * 100).toFixed(1)}%`);
          }
        }

        if (phoneDetected && !isPhoneWarningActiveRef.current) {
          // Phone detected in frame - trigger warning
          isPhoneWarningActiveRef.current = true;
          phoneWarningCountRef.current += 1;
          const warningCount = phoneWarningCountRef.current;

          console.warn(`🚨 PHONE DETECTED WARNING #${warningCount} - Cell phone found in camera frame! Confidence: ${(predictions.find(p => p.class === 'cell phone').score * 100).toFixed(1)}%`);

          const snapshot = webcamRef.current?.getScreenshot();
          const phoneConfidence = predictions.find(p => p.class === 'cell phone').score;
          
          setWarnings((prev) => [
            ...prev,
            `📱 PHONE DETECTED WARNING #${warningCount} at ${new Date().toLocaleTimeString()}: Cell phone detected in camera frame (${(phoneConfidence * 100).toFixed(1)}% confidence). You may be taking photos of the exam! WARNING: Exam will be terminated after ${PHONE_DETECTION_WARNING_LIMIT} occurrences.`,
          ]);

          logEventToBackend(
            "USER_USING_PHONE",
            `Warning #${warningCount} of ${PHONE_DETECTION_WARNING_LIMIT}. Cell phone detected in camera frame with ${(phoneConfidence * 100).toFixed(1)}% confidence. Student may be taking photos of exam questions.`,
            snapshot
          );

          // Check if we've reached warning limit
          if (warningCount >= PHONE_DETECTION_WARNING_LIMIT) {
            console.error("🛑 AUTO-TERMINATING exam due to 3 phone detections");
            alert("⛔ EXAM TERMINATED: Phone detected in camera frame 3 times. Using phones during exam is strictly prohibited.");
            
            logEventToBackend(
              "EXAM_AUTO_TERMINATED",
              `Exam terminated due to ${PHONE_DETECTION_WARNING_LIMIT} USER_USING_PHONE events. Phone repeatedly detected in camera frame.`,
              snapshot
            );
            
            if (document.fullscreenElement) {
              document.exitFullscreen();
            }
            
            setTimeout(() => {
              setIsExamStarted(false);
              setIsVerified(false);
              navigate("/login");
            }, 1000);
          }

          // Reset throttle after 5 seconds to allow next detection
          setTimeout(() => {
            isPhoneWarningActiveRef.current = false;
          }, 5000);
        }

      } catch (error) {
        console.error("❌ Phone detection error:", error);
        console.error("Error details:", error.message, error.stack);
      }
    }, PHONE_DETECTION_INTERVAL_MS);

    return () => {
      isMounted = false;
      clearInterval(phoneDetectionLoopRef.current);
    };
  }, [isExamStarted, logEventToBackend, navigate]);

  // --- 4b. PERIODIC IDENTITY VERIFICATION HOOK ---
  useEffect(() => {
    if (!isExamStarted) return;

    console.log("🔍 Periodic identity verification started - checking every 15 seconds");

    const verifyIdentity = async () => {
      console.log("🔄 Running identity verification check at", new Date().toLocaleTimeString());
      
      const snapshot = webcamRef.current?.getScreenshot();
      if (!snapshot) {
        console.warn("⚠️ No snapshot available for verification");
        return;
      }

      const token = localStorage.getItem("access_token");
      if (!token) {
        console.warn("⚠️ No access token found");
        return;
      }

      try {
        console.log("📤 Sending snapshot to backend for verification...");
        const response = await axios.post(
          "http://127.0.0.1:8000/api/exam/continuous-verify",
          { image_base64: snapshot },
          { headers: { Authorization: `Bearer ${token}` } }
        );

        console.log("📥 Verification response:", response.data);

        // Handle skipped verification (no clear face in frame)
        if (response.data.skipped) {
          consecutiveNoFaceRef.current += 1;
          const noFaceCount = consecutiveNoFaceRef.current;
          
          console.log(`⚠️ Verification skipped - no clear face detected in frame (${noFaceCount}/5)`);
          
          setWarnings((prev) => [
            ...prev,
            `⚠️ FACE NOT CLEAR #${noFaceCount} at ${new Date().toLocaleTimeString()}: Please face the camera directly. WARNING: Exam will be terminated after 5 times.`,
          ]);

          // Log event for no face detection
          logEventToBackend(
            "NO_FACE_DETECTED",
            `No clear face detected #${noFaceCount} of 5 allowed. Student not facing camera or absent.`,
            snapshot
          );

          // Auto-terminate after 5 consecutive "no face" detections
          if (noFaceCount >= 5) {
            console.error("🛑 AUTO-TERMINATING exam due to 5 consecutive no-face detections");
            alert("⛔ EXAM TERMINATED: No person detected in front of camera for 5 consecutive checks.");
            logEventToBackend(
              "NO_PERSON_DETECTED",
              "Exam terminated due to 5 consecutive NO_FACE_DETECTED events. Student absent or not facing camera.",
              snapshot
            );
            
            if (document.fullscreenElement) {
              document.exitFullscreen();
            }
            
            setTimeout(() => {
              setIsExamStarted(false);
              setIsVerified(false);
              navigate("/login");
            }, 1000);
          }
          return;
        }

        if (response.data.match) {
          // Identity verified - reset consecutive mismatches and no-face counter
          console.log("✅ Identity VERIFIED - Face matches registered student");
          consecutiveMismatchesRef.current = 0;
          consecutiveNoFaceRef.current = 0;
        } else {
          // Identity mismatch detected - reset no-face counter since a face was detected
          consecutiveMismatchesRef.current += 1;
          consecutiveNoFaceRef.current = 0;
          
          const mismatchCount = consecutiveMismatchesRef.current;
          console.error(`❌ IDENTITY MISMATCH #${mismatchCount} detected!`);
          
          setWarnings((prev) => [
            ...prev,
            `🚨 IDENTITY_MISMATCH #${mismatchCount} at ${new Date().toLocaleTimeString()}: Face does not match registered student! WARNING: Exam will be terminated after 3 mismatches.`,
          ]);

          logEventToBackend(
            "IDENTITY_MISMATCH",
            `Mismatch #${mismatchCount} of 3 allowed. Cosine distance exceeded threshold. Different person detected.`,
            snapshot
          );

          // Auto-submit after 3 consecutive mismatches
          if (mismatchCount >= 3) {
            console.error("🛑 AUTO-TERMINATING exam due to 3 consecutive identity mismatches");
            alert("⛔ EXAM TERMINATED: Identity verification failed 3 times. A different person was detected taking the exam.");
            logEventToBackend(
              "EXAM_AUTO_TERMINATED",
              "Exam terminated due to 3 consecutive IDENTITY_MISMATCH events. Different person detected multiple times."
            );
            
            if (document.fullscreenElement) {
              document.exitFullscreen();
            }
            
            setTimeout(() => {
              setIsExamStarted(false);
              setIsVerified(false);
              navigate("/login");
            }, 1000);
          }
        }
      } catch (error) {
        console.error("❌ Identity verification error:", error);
        if (error.response) {
          console.error("Server error:", error.response.status, error.response.data);
        } else if (error.request) {
          console.error("Network error: No response from server");
        } else {
          console.error("Error details:", error.message);
        }
      }
    };

    // Run first check immediately, then every 15 seconds
    verifyIdentity();
    identityCheckIntervalRef.current = setInterval(verifyIdentity, 15000);

    return () => {
      console.log("🛑 Stopping periodic identity verification");
      if (identityCheckIntervalRef.current) {
        clearInterval(identityCheckIntervalRef.current);
      }
    };
  }, [isExamStarted, logEventToBackend, navigate]);

  // --- 4c. EXAM TIMER HOOK ---
  useEffect(() => {
    if (!isExamStarted) return;

    const timerInterval = setInterval(() => {
      setExamTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timerInterval);
          logEventToBackend("EXAM_TIME_EXPIRED", "2-minute exam duration ended.");
          alert("⏰ Exam time finished!");
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timerInterval);
  }, [isExamStarted, logEventToBackend]);

  // --- 5. CONTINUOUS MONITORING HOOK (Tab / Fullscreen / Right-click) ---
  useEffect(() => {
    if (!isExamStarted) return;

    const handleVisibilityChange = () => {
      if (document.hidden) {
        setWarnings((prev) => [...prev, "⚠️ TAB SWITCH DETECTED: You left the exam environment!"]);
        logEventToBackend("TAB_SWITCH", "Student switched to another browser tab or minimized the window.");
      }
    };

    const handleFullscreenChange = () => {
      if (!document.fullscreenElement) {
        setWarnings((prev) => [...prev, "⚠️ FULL-SCREEN EXITED: You must remain in full-screen!"]);
        logEventToBackend("FULLSCREEN_EXITED", "Student exited full-screen mode.");
      }
    };

    const handleContextMenu = (e) => e.preventDefault();

    document.addEventListener("visibilitychange", handleVisibilityChange);
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    document.addEventListener("contextmenu", handleContextMenu);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      document.removeEventListener("contextmenu", handleContextMenu);
    };
  }, [isExamStarted, logEventToBackend]);

  return (
    <div style={{ maxWidth: "800px", margin: "50px auto", textAlign: "center", fontFamily: "sans-serif" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "2px solid #eee", paddingBottom: "10px" }}>
        <h2>📝 Live Examination Portal</h2>
        <button onClick={handleLogout} style={{ padding: "8px 16px", background: "#dc3545", color: "white", border: "none", borderRadius: "4px", cursor: "pointer" }}>
          Logout
        </button>
      </div>

      <div style={{ marginTop: "30px", padding: "20px", background: "#f8f9fa", borderRadius: "8px" }}>

        {/* Verification Screen */}
        {!isVerified && (
          <div>
            <div style={{ marginBottom: "20px", padding: "10px", fontWeight: "bold", color: "#333" }}>{message}</div>
            <div style={{ border: "3px solid #333", background: "#000", marginBottom: "15px" }}>
              <Webcam audio={false} ref={webcamRef} screenshotFormat="image/jpeg" videoConstraints={{ width: 640, height: 480, facingMode: "user" }} style={{ width: "100%" }} />
            </div>
            <button onClick={verifyIdentityForExam} disabled={isLoading} style={{ padding: "12px", background: isLoading ? "#ccc" : "#007BFF", color: "white", width: "100%", border: "none", cursor: "pointer", fontSize: "16px" }}>
              {isLoading ? "Comparing with Database..." : "Verify Identity & Unlock Exam"}
            </button>
          </div>
        )}

        {/* Start Exam Screen */}
        {isVerified && !isExamStarted && (
          <div style={{ padding: "40px", border: "2px solid #28a745", borderRadius: "8px", background: "#e9ecef" }}>
            <h3 style={{ color: "#28a745" }}>Identity Confirmed.</h3>
            <p>Clicking start will lock your browser into Full-Screen mode. Leaving the screen will be flagged.</p>
            <button onClick={startExam} style={{ padding: "15px 30px", fontSize: "18px", background: "#28a745", color: "white", border: "none", borderRadius: "5px", marginTop: "20px", cursor: "pointer" }}>
              Enter Full-Screen & Start Exam
            </button>
          </div>
        )}

        {/* Active Exam Screen */}
        {isExamStarted && (
          <div style={{ textAlign: "left" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px", padding: "10px", background: "#fff3cd", borderRadius: "5px" }}>
              <h4 style={{ margin: 0, color: "#856404" }}>⏱️ Time Remaining: {Math.floor(examTimeLeft / 60)}:{(examTimeLeft % 60).toString().padStart(2, "0")}</h4>
            </div>

            <div style={{ border: "2px solid #333", background: "#000", marginBottom: "15px", borderRadius: "5px", overflow: "hidden" }}>
              <Webcam audio={false} ref={webcamRef} screenshotFormat="image/jpeg" videoConstraints={{ width: 640, height: 480, facingMode: "user" }} style={{ width: "100%", display: "block" }} />
            </div>
            <h3 style={{ color: "#007BFF" }}>Question 1:</h3>
            <p>Explain the architectural benefits of using a Redis Queue in an Event-Driven Architecture.</p>
            <textarea rows="10" style={{ width: "100%", padding: "10px", marginTop: "10px", fontSize: "16px", resize: "none" }} placeholder="Type your answer here..."></textarea>

            {/* Warning Log Feed */}
            {warnings.length > 0 && (
              <div style={{ marginTop: "30px", padding: "15px", background: "#ffebee", border: "2px solid #f44336", borderRadius: "5px", boxShadow: "0 4px 6px rgba(0,0,0,0.1)" }}>
                <h4 style={{ color: "#d32f2f", marginTop: 0 }}>🚨 Proctoring Alerts</h4>
                <ul style={{ color: "#d32f2f", textAlign: "left", margin: 0, listStyle: "none", padding: 0 }}>
                  {warnings.map((warn, index) => {
                    const isIdentityMismatch = warn.includes("IDENTITY_MISMATCH");
                    const isNoFace = warn.includes("FACE NOT CLEAR");
                    const isEyeMovement = warn.includes("EYE MOVEMENT");
                    const isPhotoSpoofing = warn.includes("PHOTO SPOOFING");
                    const isRecordedVideo = warn.includes("RECORDED VIDEO");
                    const isPhoneDetected = warn.includes("PHONE DETECTED");
                    
                    return (
                      <li key={index} style={{ 
                        padding: "8px", 
                        marginBottom: "5px", 
                        background: isIdentityMismatch ? "#ffcdd2" : 
                                   isNoFace ? "#fff3cd" : 
                                   isEyeMovement ? "#e1bee7" : 
                                   isPhotoSpoofing ? "#ffe0b2" :
                                   isRecordedVideo ? "#f8bbd0" :
                                   isPhoneDetected ? "#ffccbc" :
                                   "transparent",
                        borderLeft: isIdentityMismatch ? "4px solid #c62828" : 
                                   isNoFace ? "4px solid #ff9800" : 
                                   isEyeMovement ? "4px solid #7b1fa2" : 
                                   isPhotoSpoofing ? "4px solid #f57c00" :
                                   isRecordedVideo ? "4px solid #c2185b" :
                                   isPhoneDetected ? "4px solid #d84315" :
                                   "none",
                        fontWeight: (isIdentityMismatch || isNoFace || isEyeMovement || isPhotoSpoofing || isRecordedVideo || isPhoneDetected) ? "bold" : "normal",
                        color: isNoFace ? "#f57c00" : 
                               isEyeMovement ? "#6a1b9a" : 
                               isPhotoSpoofing ? "#e65100" :
                               isRecordedVideo ? "#880e4f" :
                               isPhoneDetected ? "#bf360c" :
                               "#d32f2f",
                        borderRadius: "3px"
                      }}>
                        {warn}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {/* Submit Button */}
            <div style={{ marginTop: "30px", display: "flex", gap: "10px", justifyContent: "center" }}>
              <button 
                onClick={handleSubmitExam}
                style={{ 
                  padding: "12px 30px", 
                  fontSize: "16px", 
                  background: "#28a745", 
                  color: "white", 
                  border: "none", 
                  borderRadius: "5px", 
                  cursor: "pointer",
                  fontWeight: "bold"
                }}
              >
                ✅ Submit Exam
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}