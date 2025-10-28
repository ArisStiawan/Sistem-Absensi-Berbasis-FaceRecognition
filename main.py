import cv2
import numpy as np
import os
import time
import warnings

# Suppress pkg_resources deprecation warning
warnings.filterwarnings('ignore', category=UserWarning, module='pkg_resources')
warnings.filterwarnings('ignore', message='pkg_resources is deprecated as an API')

import face_recognition
from datetime import datetime
from datetime import date
import pytz
import csv

# Hardware acceleration configuration
HARDWARE_CODEC = {
    'backend': cv2.CAP_FFMPEG,
    'codec': cv2.VideoWriter_fourcc(*'H264'),  # H.264 codec for NVIDIA acceleration
    'buffersize': 1024*64,  # 64KB buffer
    'extra_options': {}
}


def identifyEncodings(images, classNames):
    '''
    Encoding is Recognition and comparing particular face in database or stored folder
    with GPU acceleration when available

    args:
    images: list of images
    classNames: list of image names
    '''
    
    encodeList = []
    use_gpu = cv2.cuda.getCudaEnabledDeviceCount() > 0
    
    for img, name in zip(images, classNames):
        if use_gpu:
            # Upload to GPU
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)
            
            # Resize on GPU
            gpu_small = cv2.cuda.resize(gpu_img, (0,0), fx=0.25, fy=0.25)
            
            # Color convert on GPU
            gpu_rgb = cv2.cuda.cvtColor(gpu_small, cv2.COLOR_BGR2RGB)
            
            # Download for face_recognition
            img = gpu_rgb.download()
        else:
            small_frame = cv2.resize(img, (0,0), fx=0.25, fy=0.25)
            img = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        
        # Use CNN model when GPU is available, HOG for CPU
        encodings = face_recognition.face_encodings(img, model="cnn" if use_gpu else "hog")
        
        if len(encodings) > 0:
            encode = encodings[0]
            encodeList.append(encode)
        else:
            print(f"Warning: No face detected in image for {name}")
            # Remove the corresponding name from classNames
            classNames.remove(name)
            continue
    return encodeList

from attendance_tracker import AttendanceTracker

# Initialize the attendance tracker
attendance_tracker = AttendanceTracker()

def markAttendance(name):
    '''
    This function handles attendance marking using the AttendanceTracker
    
    args:
    name: str
    returns: bool - True if attendance was marked, False if within cooldown period
    '''
    return attendance_tracker.mark_attendance(name)

# Ensure Attendance_Entry directory exists
os.makedirs("Attendance_Entry", exist_ok=True)

# Create today's attendance file
current_date = datetime.now().strftime("%y_%m_%d")
attendance_file = f"Attendance_Entry/Attendance_{current_date}.csv"

# Create file with headers if it doesn't exist
if not os.path.exists(attendance_file):
    with open(attendance_file, "w", newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Name", "Time", "Date"])
    print(f"Created new attendance file for today: {attendance_file}")
else:
    print(f"Using today's attendance file: {attendance_file}")

#Preprocessing the data 

path = 'Attendance_data'
images = []
classNames = []
# Get list of person folders
myList = [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))]
print("Found persons:", myList)

# Process each person's folder
for person_folder in myList:
    person_path = os.path.join(path, person_folder)
    # Look for all pose images (center, left, right)
    for pose in ['center.png', 'left.png', 'right.png']:
        pose_path = os.path.join(person_path, pose)
        if os.path.exists(pose_path):
            curImg = cv2.imread(pose_path)
            if curImg is not None:
                images.append(curImg)
                classNames.append(person_folder)  # Use folder name as class name
print("Loaded persons:", classNames)
print(f"Total images loaded: {len(images)} (including all poses)")

# Encoding of input image data
encodeListKnown = identifyEncodings(images, classNames)
print('Encoding Complete')
print(f'Successfully encoded {len(encodeListKnown)} faces')


# Set CUDA device and configurations if available
if cv2.cuda.getCudaEnabledDeviceCount() > 0:
    cv2.cuda.setDevice(0)
    print("Using GPU acceleration")
    # Enable OpenCL
    cv2.ocl.setUseOpenCL(True)
    # Configure CUDA stream
    stream = cv2.cuda_Stream()
    # Create CUDA-enabled face detector
    face_detector = cv2.cuda.FaceDetectorYN_create(
        model="face_detection_yunet_2023mar.onnx",
        config="",
        size=(640, 480),
        score_threshold=0.9,
        nms_threshold=0.3,
        top_k=5000,
    )
else:
    print("Using CPU processing")
    stream = None
    face_detector = None

# Camera capture 
cap = cv2.VideoCapture(0)

# Create window first
cv2.namedWindow('Attendance System', cv2.WINDOW_NORMAL)

# Create a temporary window to get screen dimensions
temp_window = cv2.namedWindow('temp', cv2.WINDOW_NORMAL)
cv2.setWindowProperty('temp', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
screen_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
screen_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
cv2.destroyWindow('temp')

# If we couldn't get proper dimensions, use default resolution
if screen_width <= 0 or screen_height <= 0:
    screen_width = 1920
    screen_height = 1080
    print("Warning: Could not detect screen size, using default 1920x1080")

# Set window to fullscreen
cv2.namedWindow('Attendance System', cv2.WINDOW_NORMAL)
cv2.setWindowProperty('Attendance System', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

# Calculate button position based on screen dimensions
window_width = screen_width
window_height = screen_height

# Detect platform
import platform
if platform.system() == 'Linux':  # Jetson Nano
    font_scale = 0.8  # Smaller text for Jetson
else:  # Windows or other platforms
    font_scale = 1.5  # Larger text for desktop

# Store font_scale for later use
button_font_scale = font_scale

last_detected_name = None
last_detect_time = 0
CACHE_TIME = 2.0  # detik, cache nama wajah biar gak dihitung ulang tiap frame
running = True

while running:
    success, img = cap.read()
    if not success:
        break

    # Process image with GPU acceleration if available
    if cv2.cuda.getCudaEnabledDeviceCount() > 0:
        # Upload image to GPU memory
        gpu_frame = cv2.cuda_GpuMat()
        gpu_frame.upload(img)
        
        # Resize on GPU
        gpu_small = cv2.cuda.resize(gpu_frame, (0, 0), fx=0.25, fy=0.25)
        
        # Convert color on GPU
        gpu_rgb = cv2.cuda.cvtColor(gpu_small, cv2.COLOR_BGR2RGB)
        
        # Download for face_recognition (since it doesn't support direct GPU tensors)
        rgb_small = gpu_rgb.download()
        
        # Detect faces using GPU-accelerated detector if available
        if face_detector is not None:
            faces = face_detector.detect(gpu_frame)
            if faces[1] is not None:
                facesCurFrame = [(int(face[1]), int(face[0] + face[2]), 
                                int(face[1] + face[3]), int(face[0])) 
                               for face in faces[1]]
            else:
                facesCurFrame = []
        else:
            facesCurFrame = face_recognition.face_locations(rgb_small, model="cnn")
    else:
        # CPU fallback
        small_frame = cv2.resize(img, (0, 0), fx=0.25, fy=0.25)
        rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        facesCurFrame = face_recognition.face_locations(rgb_small, model="hog")
    
    # Check number of faces and show appropriate status message
    if len(facesCurFrame) > 1:
        cv2.putText(img, "Multiple faces detected!", 
                (10, 30), cv2.FONT_HERSHEY_COMPLEX, 0.7, (0, 0, 255), 2)
    elif len(facesCurFrame) == 0:
        cv2.putText(img, "No face detected", (10, 30),
                cv2.FONT_HERSHEY_COMPLEX, 0.7, (0, 255, 255), 2)
    # Only process and show frame when exactly one face is detected
    elif len(facesCurFrame) == 1:
        encodesCurFrame = face_recognition.face_encodings(rgb_small, facesCurFrame)
        
        # Process the single detected face
        if len(encodesCurFrame) > 0:
            encodeFace = encodesCurFrame[0]
            faceLoc = facesCurFrame[0]
            name = "Unknown"
            
            # Check for face match
            if len(encodeListKnown) > 0:
                faceDis = face_recognition.face_distance(encodeListKnown, encodeFace)
                matchIndex = np.argmin(faceDis)
                if faceDis[matchIndex] < 0.4:  # strict threshold for better accuracy
                    name = classNames[matchIndex]
                    
                    # Draw boxes and base name
                    top, right, bottom, left = [coord * 4 for coord in faceLoc]
                    cv2.rectangle(img, (left, top), (right, bottom), (0, 255, 0), 2)
                    cv2.rectangle(img, (left, bottom - 35), (right, bottom), (0, 255, 0), cv2.FILLED)
                    
                    # Try to mark attendance and get status using ASSIGNED shift
                    assigned_shift = attendance_tracker.get_user_assigned_shift(name)
                    if assigned_shift:
                        if attendance_tracker.can_mark_attendance(name):
                            marked = markAttendance(name)
                            if marked:
                                status = f"✓ {assigned_shift.upper()} Shift"
                            else:
                                status = f"{assigned_shift.upper()} Shift - Already Marked"
                        else:
                            if name in attendance_tracker.marked_shifts and \
                               assigned_shift in attendance_tracker.marked_shifts[name]:
                                status = f"{assigned_shift.upper()} Shift - Already Marked"
                            else:
                                status = f"{assigned_shift.upper()} Shift"
                    else:
                        status = "Shift not assigned"
                    
                    # Display name on top line
                    cv2.putText(img, name, (left + 6, bottom - 25),
                            cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 255), 2)
                    # Display shift status on bottom line
                    cv2.putText(img, status, (left + 6, bottom - 6),
                            cv2.FONT_HERSHEY_COMPLEX, 0.6, (255, 255, 255), 1)

    # Resize image to fit the screen while maintaining aspect ratio
    h, w = img.shape[:2]
    scale = min(window_width/w, window_height/h)
    
    # Resize image
    img = cv2.resize(img, (int(w*scale), int(h*scale)))
    
    # Create a black canvas of screen size
    canvas = np.zeros((window_height, window_width, 3), dtype=np.uint8)
    
    # Calculate position to center the image
    y_offset = (window_height - int(h*scale)) // 2
    x_offset = (window_width - int(w*scale)) // 2
    
    # Place the resized image in the center of the canvas
    canvas[y_offset:y_offset+int(h*scale), x_offset:x_offset+int(w*scale)] = img
    
    # Display the result
    cv2.imshow('Attendance System', canvas)
    if cv2.waitKey(1) & 0xFF == 27:  # ESC to exit fullscreen
        break

cap.release()
cv2.destroyAllWindows()