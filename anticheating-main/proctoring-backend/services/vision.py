import cv2
import numpy as np
import base64
from deepface import DeepFace

def process_and_extract_embedding(base64_string: str, enforce_detection: bool = True) -> list:
    """
    Takes a Base64 string, runs the OpenCV enhancement pipeline, 
    and returns a 512-dimensional ArcFace embedding.
    
    Args:
        base64_string: Base64 encoded image
        enforce_detection: If True, raises exception when no face found. If False, returns None.
    
    Returns:
        512-dimensional embedding list, or None if no face detected and enforce_detection=False
    """
    # 1. Strip the HTML prefix if React sends it (e.g., "data:image/jpeg;base64,...")
    if "," in base64_string:
        base64_string = base64_string.split(",")[1]
        
    # 2. Decode Base64 into an OpenCV image
    img_data = base64.b64decode(base64_string)
    nparr = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # 3. Apply the Grayscale & Contrast Enhancement Pipeline
    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced_gray = clahe.apply(gray_img)
    clean_gray = cv2.fastNlMeansDenoising(enhanced_gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    
    # 4. Convert back to 3-channel (DeepFace requires 3 channels)
    final_img = cv2.cvtColor(clean_gray, cv2.COLOR_GRAY2RGB)

    # 5. Extract ArcFace Embedding
    try:
        results = DeepFace.represent(
            img_path=final_img, 
            model_name="ArcFace", 
            enforce_detection=True
        )
        # DeepFace returns a list of faces found. We take the embedding of the first face.
        return results[0]["embedding"]
    except Exception as e:
        if enforce_detection:
            raise  # Re-raise the exception for registration where we need a valid face
        else:
            return None  # Return None for continuous verification to handle gracefully

def compare_faces(saved_embedding: list, live_embedding: list) -> bool:
    """
    Compares two 512-dimensional arrays using Cosine Distance.
    ArcFace standard threshold for a match is typically 0.68.
    """
    a = np.array(saved_embedding)
    b = np.array(live_embedding)
    
    # Calculate Cosine Similarity
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    similarity = dot_product / (norm_a * norm_b)
    
    # Convert to distance
    distance = 1 - similarity
    
    # If distance is less than 0.68, it is the same person!
    # Convert numpy.bool_ to Python bool for JSON serialization
    return bool(distance < 0.68)