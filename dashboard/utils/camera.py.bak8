import streamlit as st
import cv2
import numpy as np
import face_recognition
import time
from pathlib import Path
import os

def get_camera_feed():
    """
    Creates a Streamlit camera component that can be used in the dashboard.
    This function returns a camera object that can be used to get frames.
    """
    # Use st.camera_input to capture from webcam directly in the browser
    camera_image = st.camera_input("Camera", key="camera_feed")
    
    return camera_image

def analyze_face_image(image, known_face_encodings=None, known_face_names=None):
    """
    Analyzes a face in an image and compares it with known faces.
    
    Args:
        image: The image captured from the camera
        known_face_encodings: List of known face encodings
        known_face_names: List of names corresponding to the encodings
    
    Returns:
        Dict with detection results including face locations, names, etc.
    """
    if image is None:
        return None
    
    # Convert the image from BGR to RGB format
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    # Resize for faster face recognition processing
    small_frame = cv2.resize(image_rgb, (0, 0), fx=0.25, fy=0.25)
    
    # Find all faces in the current frame
    face_locations = face_recognition.face_locations(small_frame)
    
    result = {
        "face_detected": len(face_locations) > 0,
        "multiple_faces": len(face_locations) > 1,
        "face_locations": face_locations,
        "recognized_name": None,
        "match_confidence": None,
        "face_encoding": None
    }
    
    # If faces are found and we have reference encodings, try to identify them
    if face_locations and known_face_encodings is not None and known_face_names is not None:
        face_encodings = face_recognition.face_encodings(small_frame, face_locations)
        
        if face_encodings:
            result["face_encoding"] = face_encodings[0]
            
            # Compare the detected face with our known faces
            face_distances = face_recognition.face_distance(known_face_encodings, face_encodings[0])
            if len(face_distances) > 0:
                best_match_index = np.argmin(face_distances)
                match_confidence = 1 - face_distances[best_match_index]
                
                # If the face is a close match
                if match_confidence > 0.6:  # Threshold for recognition
                    result["recognized_name"] = known_face_names[best_match_index]
                    result["match_confidence"] = match_confidence
    
    return result

def capture_and_save_face(image, output_path, pose="center"):
    """
    Captures an image of a face and saves it to the specified path.
    
    Args:
        image: Image from which to extract the face
        output_path: Directory path where to save the image
        pose: The pose name (center, left, right)
    
    Returns:
        bool: True if successful, False otherwise
    """
    if image is None:
        return False
        
    try:
        # Create directory if it doesn't exist
        os.makedirs(output_path, exist_ok=True)
        
        # Convert to RGB (face_recognition uses RGB)
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # Detect faces
        face_locations = face_recognition.face_locations(rgb_image)
        
        if not face_locations:
            return False
            
        # Take the first face found
        top, right, bottom, left = face_locations[0]
        
        # Add some margin to the face
        margin = 30
        top = max(0, top - margin)
        right = min(image.shape[1], right + margin)
        bottom = min(image.shape[0], bottom + margin)
        left = max(0, left - margin)
        
        # Crop the face
        face_image = image[top:bottom, left:right]
        
        # Save the image
        output_file = os.path.join(output_path, f"{pose}.png")
        cv2.imwrite(output_file, face_image)
        
        return True
    except Exception as e:
        st.error(f"Error capturing face: {str(e)}")
        return False

def load_face_encodings():
    """
    Loads all face encodings from the Attendance_data directory
    
    Returns:
        Tuple: (encodings, names)
    """
    root_dir = Path(__file__).parent.parent.parent
    attendance_dir = root_dir / "Attendance_data"
    
    if not attendance_dir.exists():
        return [], []
    
    # Get list of person folders
    person_folders = [f for f in os.listdir(attendance_dir) if os.path.isdir(os.path.join(attendance_dir, f))]
    
    encodings = []
    names = []
    
    for person in person_folders:
        person_dir = attendance_dir / person
        
        # Check for center.png (primary image)
        center_img_path = person_dir / "center.png"
        if center_img_path.exists():
            try:
                # Load the image
                img = cv2.imread(str(center_img_path))
                rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                
                # Get encodings
                face_encodings = face_recognition.face_encodings(rgb_img)
                if face_encodings:
                    encodings.append(face_encodings[0])
                    names.append(person)
            except Exception as e:
                st.warning(f"Could not load encoding for {person}: {str(e)}")
    
    return encodings, names

def get_orientation_instructions(progress_step):
    """
    Returns instructions for face orientation based on the current progress step
    
    Args:
        progress_step: Current step in the registration process
    
    Returns:
        str: Instruction text
    """
    if progress_step == 0:
        return "Posisikan wajah menghadap ke kamera (depan)"
    elif progress_step == 1:
        return "Posisikan wajah menghadap ke kiri"
    elif progress_step == 2:
        return "Posisikan wajah menghadap ke kanan"
    else:
        return "Proses selesai"