
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

# Initialize the attendance tracker (safe to keep at import time)
attendance_tracker = AttendanceTracker()

def markAttendance(name):
    '''
    This function handles attendance marking using the AttendanceTracker
    
    args:
    name: str
    returns: bool - True if attendance was marked, False if within cooldown period
    '''
    return attendance_tracker.mark_attendance(name)

#Preprocessing the data 

def _load_known_faces(path='Attendance_data'):
    """Load known face images and names from Attendance_data."""
    images = []
    names = []
    if not os.path.isdir(path):
        return images, names
    myList = [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))]
    print("Found persons:", myList)
    for person_folder in myList:
        person_path = os.path.join(path, person_folder)
        for pose in ['center.png', 'left.png', 'right.png']:
            pose_path = os.path.join(person_path, pose)
            if os.path.exists(pose_path):
                curImg = cv2.imread(pose_path)
                if curImg is not None:
                    images.append(curImg)
                    names.append(person_folder)
    print("Loaded persons:", names)
    print(f"Total images loaded: {len(images)} (including all poses)")
    return images, names

def run_attendance_window():
    """Run the original OpenCV window workflow for attendance."""
    # Ensure Attendance_Entry directory exists and today's file present
    os.makedirs("Attendance_Entry", exist_ok=True)
    current_date = datetime.now().strftime("%y_%m_%d")
    attendance_file = f"Attendance_Entry/Attendance_{current_date}.csv"
    if not os.path.exists(attendance_file):
        with open(attendance_file, "w", newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Name", "Time", "Date"])
        print(f"Created new attendance file for today: {attendance_file}")
    else:
        print(f"Using today's attendance file: {attendance_file}")

    # Load known faces and encodings
    images, classNames = _load_known_faces('Attendance_data')
    encodeListKnown = identifyEncodings(images, classNames)
    print('Encoding Complete')
    print(f'Successfully encoded {len(encodeListKnown)} faces')

    # GPU config when available
    if cv2.cuda.getCudaEnabledDeviceCount() > 0:
        cv2.cuda.setDevice(0)
        print("Using GPU acceleration")
        cv2.ocl.setUseOpenCL(True)
        stream = cv2.cuda_Stream()
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

    # Function to check if mouse click is within button bounds
    def is_mouse_click_in_button(x, y, button_pos):
        bx, by, bw, bh = button_pos
        return bx <= x <= bx + bw and by <= y <= by + bh

    # Mouse callback function
    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            button_pos = param
            if is_mouse_click_in_button(x, y, button_pos):
                print("\nStarting registration process...")
                cap.release()
                cv2.destroyAllWindows()
                import subprocess as _sub
                import sys as _sys
                try:
                    _sub.run([_sys.executable, "initial_data_capture.py"], check=True)
                except _sub.CalledProcessError as e:
                    print(f"Error running registration: {e}")
                nonlocal_running[0] = False

    # Camera capture
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Create window and set mouse callback
    cv2.namedWindow('Attendance System')
    button_pos = (10, 440, 150, 30)  # x, y, width, height
    cv2.setMouseCallback('Attendance System', mouse_callback, button_pos)

    last_detected_name = None
    last_detect_time = 0
    CACHE_TIME = 2.0
    nonlocal_running = [True]

    while nonlocal_running[0]:
        success, img = cap.read()
        if not success:
            break

        # Draw registration button
        x, y, w, h = button_pos
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), cv2.FILLED)
        cv2.putText(img, "Register New", (x + 5, y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Process image
        if cv2.cuda.getCudaEnabledDeviceCount() > 0:
            gpu_frame = cv2.cuda_GpuMat()
            gpu_frame.upload(img)
            gpu_small = cv2.cuda.resize(gpu_frame, (0, 0), fx=0.25, fy=0.25)
            gpu_rgb = cv2.cuda.cvtColor(gpu_small, cv2.COLOR_BGR2RGB)
            rgb_small = gpu_rgb.download()
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
            small_frame = cv2.resize(img, (0, 0), fx=0.25, fy=0.25)
            rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            facesCurFrame = face_recognition.face_locations(rgb_small, model="hog")

        if len(facesCurFrame) > 1:
            cv2.putText(img, "Multiple faces detected!",
                        (10, 30), cv2.FONT_HERSHEY_COMPLEX, 0.7, (0, 0, 255), 2)
        elif len(facesCurFrame) == 0:
            cv2.putText(img, "No face detected", (10, 30),
                        cv2.FONT_HERSHEY_COMPLEX, 0.7, (0, 255, 255), 2)
        else:
            encodesCurFrame = face_recognition.face_encodings(rgb_small, facesCurFrame)
            if len(encodesCurFrame) > 0:
                encodeFace = encodesCurFrame[0]
                faceLoc = facesCurFrame[0]
                name = "Unknown"
                if len(encodeListKnown) > 0:
                    faceDis = face_recognition.face_distance(encodeListKnown, encodeFace)
                    matchIndex = np.argmin(faceDis)
                    if faceDis[matchIndex] < 0.4:
                        name = classNames[matchIndex]
                        top, right, bottom, left = [coord * 4 for coord in faceLoc]
                        cv2.rectangle(img, (left, top), (right, bottom), (0, 255, 0), 2)
                        cv2.rectangle(img, (left, bottom - 35), (right, bottom), (0, 255, 0), cv2.FILLED)
                        current_shift = attendance_tracker._get_current_shift()
                        if current_shift:
                            # Validate assigned shift
                            if not attendance_tracker.has_valid_shift(name):
                                status = "Invalid shift for this user"
                            else:
                                if attendance_tracker.can_mark_attendance(name):
                                    marked = markAttendance(name)
                                    if marked:
                                        status = f"\u2713 {current_shift.upper()} Shift"
                                    else:
                                        status = f"{current_shift.upper()} Shift - Already Marked"
                                else:
                                    if name in attendance_tracker.marked_shifts and \
                                       current_shift in attendance_tracker.marked_shifts[name]:
                                        status = f"{current_shift.upper()} Shift - Already Marked"
                                    else:
                                        status = f"{current_shift.upper()} Shift"
                        else:
                            status = "Outside shift hours"
                        cv2.putText(img, name, (left + 6, bottom - 25),
                                    cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 255), 2)
                        cv2.putText(img, status, (left + 6, bottom - 6),
                                    cv2.FONT_HERSHEY_COMPLEX, 0.6, (255, 255, 255), 1)

        cv2.imshow('Attendance System', img)
        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_attendance_window()
