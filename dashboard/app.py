import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime, timedelta
import time
from pathlib import Path
import os
import sys
import subprocess
import shutil
import json
from utils import sound
import cv2
import numpy as np
import face_recognition
from attendance_tracker import AttendanceTracker
from typing import Tuple

# Import safe CSV reader from pages
from pages.attendance import safe_read_attendance_csv, validate_attendance_dataframe

# Initialize face recognition system
def initialize_face_recognition():
    if 'face_recognition_initialized' not in st.session_state:
        path = Path(__file__).parent.parent / 'Attendance_data'
        images = []
        classNames = []
        
        # Get list of person folders
        myList = [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))]
        
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
                        classNames.append(person_folder)
        
        # Encode faces
        encodeListKnown = []
        for img, name in zip(images, classNames):
            img = cv2.cvtColor(cv2.resize(img, (0,0), fx=0.25, fy=0.25), cv2.COLOR_BGR2RGB)
            encodings = face_recognition.face_encodings(img)
            if len(encodings) > 0:
                encodeListKnown.append(encodings[0])
            else:
                classNames.remove(name)
                continue
        
        st.session_state.classNames = classNames
        st.session_state.encodeListKnown = encodeListKnown
        st.session_state.face_recognition_initialized = True
        st.session_state.attendance_tracker = AttendanceTracker()

# Initialize face recognition on app start
initialize_face_recognition()

# Import utility functions
from pathlib import Path
import json
from utils.user_data import delete_user_completely
from utils.image_management import delete_user_image, get_user_images

# Menghapus duplikat fungsi delete_user_completely karena sudah diimpor dari utils.user_data

# Configure page and initial session state
st.set_page_config(
    page_title="Face Recognition Attendance Dashboard",
    page_icon="📊",
    layout="wide"
)

# Import pages
from pages.attendance import show_attendance

# API endpoints
API_URL = "http://localhost:8000"
TOKEN_KEY = "access_token"

def api_call(endpoint: str, method="get", **kwargs):
    try:
        url = f"{API_URL}{endpoint}"
        if method.lower() == "get":
            response = requests.get(url, **kwargs)
        else:
            response = requests.post(url, **kwargs)
            
        if response.status_code != 200:
            st.error(f"API Error: {response.status_code} - {response.text}")
            return None
            
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("Tidak dapat terhubung ke server. Pastikan server API sedang berjalan.")
        return None
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None

def is_checkout_time(time, assigned_shift):
    """
    Check if the given time is a checkout time for the shift
    Returns: bool
    """
    hour = time.hour
    minute = time.minute
    
    if assigned_shift == 'morning':
        # Morning shift ends at 17:00
        return hour == 17 and minute <= 15
    else:
        # Night shift ends at 22:00
        return hour == 22 and minute <= 15

def get_attendance_status(check_in_time, assigned_shift):
    """
    Determine attendance status based on check-in time and assigned shift
    Returns: status (on_time, late, checkout)
    """
    hour = check_in_time.hour
    minute = check_in_time.minute
    total_minutes = hour * 60 + minute
    
    if assigned_shift == 'morning':
        # Morning shift: 08:00 - 17:00, toleransi 15 menit
        shift_start_minutes = 8 * 60  # 08:00
        tolerance_limit = shift_start_minutes + 15  # 08:15
        
        if hour == 17 and minute <= 15:
            return 'checkout'  # Checkout time for morning shift
        
        return 'on_time' if total_minutes <= tolerance_limit else 'late'
    else:
        # Night shift: 17:00 - 22:00, toleransi 15 menit
        shift_start_minutes = 17 * 60  # 17:00
        tolerance_limit = shift_start_minutes + 15  # 17:15
        
        if hour == 22 and minute <= 15:
            return 'checkout'  # Checkout time for night shift
            
        return 'on_time' if total_minutes <= tolerance_limit else 'late'

def determine_actual_shift(check_in_time):
    """
    Determine the actual shift based on check-in time
    Returns: actual_shift (morning or night)
    """
    hour = check_in_time.hour
    return 'morning' if 8 <= hour < 17 else 'night'

def get_today_attendance():
    try:
        # Load user data for shift information
        user_data_file = Path(__file__).parent.parent / "user_data.json"
        user_shifts = {}
        if user_data_file.exists():
            import json
            try:
                with open(user_data_file, 'r') as f:
                    data = json.load(f)
                user_shifts = {name: info['shift'] for name, info in data.items()}
            except:
                pass  # silently continue with empty shifts
        
        # Get attendance data
        attendance_dir = Path(__file__).parent.parent / "Attendance_Entry"
        today_file = attendance_dir / f"Attendance_{datetime.now().strftime('%y_%m_%d')}.csv"
        
        if not today_file.exists():
            # Return empty DataFrame if today's file doesn't exist yet
            return pd.DataFrame(columns=['employee_name', 'check_in', 'check_out', 'assigned_shift', 'actual_shift', 'status'])
        
        # Use the safe CSV reader from pages.attendance
        df = safe_read_attendance_csv(today_file, verbose=False)
        if df is None or df.empty:
            return pd.DataFrame(columns=['employee_name', 'check_in', 'check_out', 'assigned_shift', 'actual_shift', 'status'])
        
        # Validate and normalize the DataFrame
        df = validate_attendance_dataframe(df)
        
        # Normalize column names (handle both old and new CSV formats)
        df.columns = [str(c).strip() for c in df.columns]
        
        # Map column names to standard names
        if 'Name' in df.columns:
            df = df.rename(columns={'Name': 'employee_name'})
        if 'Time' in df.columns:
            df = df.rename(columns={'Time': 'check_in_time'})
        if 'Date' in df.columns:
            df = df.rename(columns={'Date': 'date'})
        if 'Shift' in df.columns:
            df = df.rename(columns={'Shift': 'recorded_shift'})
        if 'Status' in df.columns:
            df = df.rename(columns={'Status': 'recorded_status'})
        
        # Process each attendance entry
        processed_data = []
        for idx, row in df.iterrows():
            try:
                # Get employee name
                employee_name = row.get('employee_name')
                if not employee_name or str(employee_name).strip() == '':
                    continue
                
                employee_name = str(employee_name).strip()
                
                # Get check-in time
                check_in_str = row.get('check_in_time')
                if not check_in_str or str(check_in_str).strip() == '':
                    continue
                
                check_in_str = str(check_in_str).strip()
                
                # Parse the date and time
                check_in_time = None
                date_val = row.get('date')
                
                if date_val and check_in_str:
                    try:
                        check_in_time = pd.to_datetime(f"{date_val} {check_in_str}")
                    except Exception:
                        try:
                            check_in_time = pd.to_datetime(check_in_str)
                        except:
                            continue
                else:
                    try:
                        check_in_time = pd.to_datetime(check_in_str)
                    except:
                        continue
                
                if check_in_time is None:
                    continue
                
                # Get assigned shift from user data or recorded shift (for backward compatibility)
                assigned_shift = user_shifts.get(employee_name)
                
                # If no assigned shift in user_data.json, use recorded shift from CSV (if available)
                if assigned_shift is None:
                    recorded_shift = row.get('recorded_shift')
                    if recorded_shift and str(recorded_shift).strip() in ['morning', 'night']:
                        assigned_shift = str(recorded_shift).strip()
                    else:
                        assigned_shift = 'morning'  # Default fallback
                
                # Determine actual shift based on check-in time
                actual_shift = determine_actual_shift(check_in_time.time())
                
                # Get recorded status from CSV (if available)
                recorded_status = row.get('recorded_status')
                if recorded_status and str(recorded_status).strip() in ['on_time', 'late', 'off_shift']:
                    status = str(recorded_status).strip()
                else:
                    # Fallback: determine status based on time and assigned shift
                    status = get_attendance_status(check_in_time.time(), assigned_shift)
                
                # Add processed entry
                processed_data.append({
                    'employee_name': employee_name,
                    'check_in': check_in_time,
                    'check_out': None,
                    'assigned_shift': assigned_shift,
                    'actual_shift': actual_shift,
                    'status': status
                })
                
            except Exception as e:
                # Log error but continue processing other rows
                continue
        
        if processed_data:
            return pd.DataFrame(processed_data)
        else:
            return pd.DataFrame(columns=['employee_name', 'check_in', 'check_out', 'assigned_shift', 'actual_shift', 'status'])
    
    except Exception as e:
        # Return empty DataFrame on error instead of showing error to user
        return pd.DataFrame(columns=['employee_name', 'check_in', 'check_out', 'assigned_shift', 'actual_shift', 'status'])

def get_all_attendance():
    """Get all attendance data from CSV files (local fallback if API fails)"""
    try:
        # Try API first
        response = api_call("/attendance/all")
        if response and 'data' in response:
            api_df = pd.DataFrame(response['data'])
            if not api_df.empty:
                return api_df
    except:
        pass  # Fallback to local files
    
    # Fallback: Read from all CSV files locally
    try:
        from pathlib import Path
        sys.path.insert(0, './dashboard')
        from pages.attendance import safe_read_attendance_csv, validate_attendance_dataframe
        
        attendance_dir = Path("Attendance_Entry")
        if not attendance_dir.exists():
            return pd.DataFrame()
        
        all_data = []
        # Read all CSV files in Attendance_Entry directory
        for csv_file in sorted(attendance_dir.glob("Attendance_*.csv")):
            df = safe_read_attendance_csv(csv_file, verbose=False)
            if df is not None and not df.empty:
                df = validate_attendance_dataframe(df)
                all_data.append(df)
        
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            # Normalize columns
            combined_df.columns = [col.strip() for col in combined_df.columns]
            return combined_df
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

def get_registered_users():
    try:
        response = api_call("/users")
        if response and "data" in response:
            # Sort users by name
            users = sorted(response["data"], key=lambda x: x["name"].lower())
            # Log the users for debugging
            print("Retrieved users:", users)
            return users
        print("No data in response or invalid response:", response)
        return []
    except Exception as e:
        st.error(f"Failed to fetch registered users: {str(e)}")
        return []

# Import modules
from registration import show_user_registration, navigate_to
from pages.attendance import show_attendance
# Import the new user management implementation
from new_user_management import show_user_management

# Initialize session state
if 'current_page' not in st.session_state:
    st.session_state['current_page'] = 'Overview'
if 'registration_state' not in st.session_state:
    st.session_state['registration_state'] = {
        'is_registering': False,
        'current_step': 0,
        'user_data': None,
        'process': None,
        'error': None
    }
    
# Main dashboard
def main():
    st.title("Face Recognition Attendance Dashboard")
    
    # Navigation sidebar
    st.sidebar.title("Navigation")
    
    # Navigation options
    pages = ["Overview", "Daily Statistics", "User Management", "Register New User", "Attendance"]
    
    # Use session state for the radio button
    current_page_index = pages.index(st.session_state['current_page'])
    selected_page = st.sidebar.radio("Choose a page", pages, index=current_page_index)
    
    # Update session state if page changes
    if selected_page != st.session_state['current_page']:
        st.session_state['current_page'] = selected_page
        st.rerun()
        
    # Route to appropriate page
    if st.session_state['current_page'] == "Overview":
        show_overview()
    elif st.session_state['current_page'] == "Daily Statistics":
        show_daily_statistics()
    elif st.session_state['current_page'] == "User Management":
        show_user_management()
    elif st.session_state['current_page'] == "Register New User":
        show_user_registration()
    elif st.session_state['current_page'] == "Attendance":
        show_attendance()

def show_overview():
    st.header("Overview Hari Ini")
    
    # Get today's data and device status
    df = get_today_attendance()
    response = api_call("/devices")
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    total_present = len(df) if not df.empty else 0
    with col1:
        st.metric("Total Hadir", total_present)
    
    # Initialize counters for assigned shifts
    morning_count = 0
    night_count = 0
    
    if not df.empty:
        # Count by assigned shift (what shift they're assigned to, not when they checked in)
        morning_shift = df[df['assigned_shift'] == 'morning']
        night_shift = df[df['assigned_shift'] == 'night']
        
        morning_count = len(morning_shift)
        night_count = len(night_shift)
    
    with col2:
        st.metric("Hadir di Shift Pagi", morning_count)
    with col3:
        st.metric("Hadir di Shift Malam", night_count)
    
    # Get device status
    devices = response.get('data', []) if response else []
    active_devices = 0
    if devices:
        active_devices = sum(1 for device in devices if isinstance(device, dict) and device.get('status') == 'active')
    
    with col4:
        st.metric("Perangkat Aktif", active_devices)
    
    # Display comprehensive shift details
    st.subheader("Detail Absensi Hari Ini")
    if not df.empty:
        tabs = st.tabs(["Shift Pagi", "Shift Malam"])
        
        # Morning Shift Tab
        with tabs[0]:
            # Get all employees who are assigned to morning shift
            morning_df = df[df['assigned_shift'] == 'morning']
            if not morning_df.empty:
                # Status counts
                on_time = len(morning_df[morning_df['status'] == 'on_time'])
                late = len(morning_df[morning_df['status'] == 'late'])
                checked_out = len(morning_df[morning_df['check_out'].notna()])
                pending_checkout = len(morning_df[morning_df['check_out'].isna()])
                
                mcol1, mcol2, mcol3, mcol4 = st.columns(4)
                with mcol1:
                    st.metric("Tepat Waktu", on_time)
                with mcol2:
                    st.metric("Terlambat", late)
                with mcol3:
                    st.metric("Sudah Checkout", checked_out)
                with mcol4:
                    st.metric("Belum Checkout", pending_checkout)
                    
                # Add late time details if any
                if late > 0:
                    late_df = morning_df[morning_df['status'] == 'late'].copy()
                    st.warning("Detail Keterlambatan:")
                    # Calculate late minutes for each entry
                    late_df['jam_masuk'] = pd.to_datetime(late_df['check_in']).dt.strftime('%H:%M')
                    late_df['keterlambatan'] = (pd.to_datetime(late_df['check_in']).dt.hour * 60 + 
                                              pd.to_datetime(late_df['check_in']).dt.minute - 
                                              (8 * 60 + 15))  # Minutes after 08:15
                    late_df['keterlambatan'] = late_df['keterlambatan'].astype(str) + ' menit'
                    # Display table
                    st.dataframe(
                        late_df[['employee_name', 'jam_masuk', 'keterlambatan']].rename(
                            columns={
                                'employee_name': 'Nama Karyawan',
                                'jam_masuk': 'Jam Masuk',
                                'keterlambatan': 'Keterlambatan'
                            }
                        ),
                        hide_index=True,
                        use_container_width=True
                    )
                
                # Format check-in time
                display_df = morning_df.copy()
                display_df['check_in'] = pd.to_datetime(display_df['check_in']).dt.strftime('%H:%M:%S')
                if 'check_out' in display_df.columns:
                    display_df['check_out'] = pd.to_datetime(display_df['check_out']).dt.strftime('%H:%M:%S')
                
                # Show detailed table
                st.dataframe(
                    display_df[[
                        'employee_name', 'check_in', 'check_out',
                        'actual_shift', 'status'
                    ]].rename(columns={
                        'employee_name': 'Nama',
                        'check_in': 'Jam Masuk',
                        'check_out': 'Jam Keluar',
                        'actual_shift': 'Shift Aktual',
                        'status': 'Status'
                    }),
                    use_container_width=True
                )
            else:
                st.info("Belum ada absensi untuk shift pagi")
        
        # Night Shift Tab
        with tabs[1]:
            # Get all employees who are assigned to night shift
            night_df = df[df['assigned_shift'] == 'night']
            if not night_df.empty:
                # Status counts
                on_time = len(night_df[night_df['status'] == 'on_time'])
                late = len(night_df[night_df['status'] == 'late'])
                checked_out = len(night_df[night_df['check_out'].notna()])
                pending_checkout = len(night_df[night_df['check_out'].isna()])
                
                ncol1, ncol2, ncol3, ncol4 = st.columns(4)
                with ncol1:
                    st.metric("Tepat Waktu", on_time)
                with ncol2:
                    st.metric("Terlambat", late)
                with ncol3:
                    st.metric("Sudah Checkout", checked_out)
                with ncol4:
                    st.metric("Belum Checkout", pending_checkout)
                    
                # Add late time details if any
                if late > 0:
                    late_df = night_df[night_df['status'] == 'late']
                    st.warning("Detail Keterlambatan:")
                    for _, row in late_df.iterrows():
                        check_in = pd.to_datetime(row['check_in']).strftime('%H:%M')
                        minutes_late = (pd.to_datetime(row['check_in']).hour * 60 + 
                                     pd.to_datetime(row['check_in']).minute - 
                                     (17 * 60 + 15))  # Minutes after 17:15
                        st.write(f"👤 {row['employee_name']}: {check_in} ({minutes_late} menit terlambat)")
                
                # Format check-in time
                display_df = night_df.copy()
                display_df['check_in'] = pd.to_datetime(display_df['check_in']).dt.strftime('%H:%M:%S')
                if 'check_out' in display_df.columns:
                    display_df['check_out'] = pd.to_datetime(display_df['check_out']).dt.strftime('%H:%M:%S')
                
                # Show detailed table
                st.dataframe(
                    display_df[[
                        'employee_name', 'check_in', 'check_out',
                        'actual_shift', 'status'
                    ]].rename(columns={
                        'employee_name': 'Nama',
                        'check_in': 'Jam Masuk',
                        'check_out': 'Jam Keluar',
                        'actual_shift': 'Shift Aktual',
                        'status': 'Status'
                    }),
                    use_container_width=True
                )
            else:
                st.info("No night shift attendance yet")
    else:
        st.info("No attendance records for today yet")
    
    # Display device status
    if devices:
        st.subheader("Device Status")
        device_df = pd.DataFrame(devices)
        device_df['last_active'] = pd.to_datetime(device_df['last_active'])
        
        # Add status indicators
        def get_status_color(status):
            return '🟢' if status == 'active' else '🔴'
            
        device_df['indicator'] = device_df['status'].apply(get_status_color)
        device_df['last_active'] = device_df['last_active'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        st.dataframe(device_df[['indicator', 'device_id', 'name', 'location', 'last_active', 'status']])

def export_attendance_to_csv(df, filename):
    """Export attendance data to CSV"""
    try:
        # Create Attendance_Entry directory if not exists
        export_dir = Path(__file__).parent.parent / "Attendance_Entry"
        export_dir.mkdir(exist_ok=True)
        
        # Save to CSV
        export_path = export_dir / filename
        df.to_csv(export_path, index=False)
        return True, export_path
    except Exception as e:
        return False, str(e)

def show_daily_statistics():
    st.header("Daily Statistics")

    # Add Export & Import buttons
    col1, col2 = st.columns([1, 1])
    
    def prepare_attendance_data(df):
        """Prepare attendance data by converting date/time columns, KEEP ALL ROWS"""
        import pandas as pd
        try:
            if df is None or df.empty:
                return df, None
            
            # Make a copy to avoid SettingWithCopyWarning
            df = df.copy()
            
            # Normalize column names (make lowercase and strip)
            df.columns = [col.lower().strip() for col in df.columns]
            
            # Rename 'name' to 'employee_name' for consistency if needed
            if 'name' in df.columns and 'employee_name' not in df.columns:
                df = df.rename(columns={'name': 'employee_name'})

            # Convert date column - KEEP ALL ROWS, no filtering
            if 'date' in df.columns:
                # Try to parse dates flexibly
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                # NOTE: We keep rows with NaT dates too - they might have partial data
            
            # Convert time column if exists - KEEP ALL ROWS
            if 'time' in df.columns:
                # Try to parse times
                df['time'] = pd.to_datetime(df['time'], format='%H:%M:%S', errors='coerce').dt.time
                # Replace NaT with None for time columns
                df['time'] = df['time'].where(df['time'].notna(), None)
            
            return df, None
        except Exception as e:
            return None, str(e)
    
    with col1:
        # Get the data first
        df = get_all_attendance()
        
        # Debug info
        if df.empty:
            st.warning("⚠️ Tidak ada data untuk di-export")
        else:
            st.info(f"📊 Total records loaded: {len(df)}")
            
            # Prepare data
            prepared_df, error = prepare_attendance_data(df)
            
            if error:
                st.error(f"❌ Error saat memproses data: {error}")
            elif prepared_df is None:
                st.error("❌ Gagal memproses data")
            else:
                df = prepared_df
                
                # Add weekly filter
                current_date = datetime.now()
                start_of_week = current_date - timedelta(days=current_date.weekday())
                end_of_week = start_of_week + timedelta(days=6)
                
                # Format untuk nama file
                period = st.selectbox(
                    "Periode Export",
                    ["Hari Ini", "Minggu Ini", "Bulan Ini", "Semua"],
                    help="Pilih periode data yang akan diexport"
                )
                
                if st.button("📥 Download CSV", use_container_width=True, key='export_csv_button'):
                    try:
                        # FILTER DENGAN BENAR - hanya filter rows yang punya valid date
                        df_valid = df.dropna(subset=['date']).copy()
                        
                        if df_valid.empty:
                            st.error(f"❌ Tidak ada data dengan tanggal valid untuk periode ini")
                        else:
                            st.info(f"📍 Valid records for filtering: {len(df_valid)}")
                            
                            # Filter data berdasarkan periode
                            if period == "Hari Ini":
                                mask = df_valid['date'].dt.date == current_date.date()
                                filename = f"Attendance_{current_date.strftime('%d_%m_%y')}.csv"
                            elif period == "Minggu Ini":
                                mask = (df_valid['date'].dt.date >= start_of_week.date()) & (df_valid['date'].dt.date <= end_of_week.date())
                                filename = f"Weekly_Attendance_{start_of_week.strftime('%d_%m_%y')}_to_{end_of_week.strftime('%d_%m_%y')}.csv"
                            elif period == "Bulan Ini":
                                mask = df_valid['date'].dt.to_period('M') == current_date.to_period('M')
                                filename = f"Monthly_Attendance_{current_date.strftime('%m_%Y')}.csv"
                            else:  # Semua
                                mask = pd.Series(True, index=df_valid.index)
                                filename = f"All_Attendance_as_of_{current_date.strftime('%d_%m_%y')}.csv"
                            
                            # Filter dan persiapkan data untuk download
                            filtered_df = df_valid[mask].copy()
                            
                            if not filtered_df.empty:
                                # Convert datetime to string untuk CSV (untuk kolom yang sudah datetime)
                                if 'date' in filtered_df.columns and hasattr(filtered_df['date'].iloc[0], 'strftime'):
                                    filtered_df['date'] = filtered_df['date'].dt.strftime('%Y-%m-%d')
                                
                                # Time sudah di-convert ke time object, convert ke string
                                if 'time' in filtered_df.columns:
                                    filtered_df['time'] = filtered_df['time'].apply(lambda x: str(x) if x is not None else '')
                                
                                # Download CSV
                                csv_data = filtered_df.to_csv(index=False).encode('utf-8-sig')
                                st.download_button(
                                    label="💾 Simpan File",
                                    data=csv_data,
                                    file_name=filename,
                                    mime="text/csv",
                                    key=f'download_{period}_{current_date.timestamp()}'
                                )
                                st.success(f"✅ {len(filtered_df)} data siap didownload: {filename}")
                            else:
                                st.warning(f"⚠️ Tidak ada data untuk periode: {period}")
                                st.info(f"Coba pilih periode lain atau gunakan 'Semua'")
                                
                    except Exception as e:
                        st.error(f"❌ Error saat memproses data: {str(e)}")
                        import traceback
                        st.write(traceback.format_exc())
    
    with col2:
        uploaded_file = st.file_uploader(
            "📥 Import CSV",
            type=['csv'],
            help="Upload file CSV untuk import data absensi"
        )
        
        if uploaded_file is not None:
            try:
                # Read CSV
                import_df = pd.read_csv(uploaded_file)
                
                # Normalize column names
                import_df.columns = [col.lower().strip() for col in import_df.columns]
                
                # Check for required columns (flexible naming)
                has_name = any(col in import_df.columns for col in ['employee_name', 'name', 'nama'])
                has_date = any(col in import_df.columns for col in ['date', 'tanggal', 'tgl'])
                has_time = any(col in import_df.columns for col in ['time', 'waktu', 'jam'])
                
                if not (has_name and has_date and has_time):
                    missing = []
                    if not has_name: missing.append('employee_name/name/nama')
                    if not has_date: missing.append('date/tanggal/tgl')
                    if not has_time: missing.append('time/waktu/jam')
                    
                    st.error(f"❌ Kolom yang diperlukan tidak ditemukan: {', '.join(missing)}")
                    st.info("""
                    Format CSV yang diperlukan:
                    - Nama kolom: employee_name/name/nama
                    - Kolom tanggal: date/tanggal/tgl (format: YYYY-MM-DD)
                    - Kolom waktu: time/waktu/jam (format: HH:MM:SS)
                    - Opsional: status, shift
                    """)
                else:
                    # Show preview
                    st.subheader("Preview Data Import")
                    st.dataframe(import_df.head())
                    
                    # Confirm import
                    if st.button("✅ Konfirmasi Import", use_container_width=True):
                        # Save to attendance directory
                        filename = f"Attendance_{datetime.now().strftime('%y_%m_%d')}.csv"
                        success, result = export_attendance_to_csv(import_df, filename)
                        
                        if success:
                            st.success("✅ Data berhasil diimport!")
                            st.rerun()  # Refresh page to show new data
                        else:
                            st.error(f"❌ Gagal import data: {result}")
                        
            except Exception as e:
                st.error(f"❌ Error saat membaca file: {str(e)}")
                st.info("Pastikan format file CSV sesuai")
    
    # Show statistics
    st.markdown("---")
    
    df = get_all_attendance()
    if not df.empty:
        # Normalize column names to lowercase
        df.columns = [col.lower().strip() for col in df.columns]
        
        # Check and rename columns if needed
        date_column = 'date' if 'date' in df.columns else 'Date'
        time_column = 'time' if 'time' in df.columns else 'Time'
        
        if date_column not in df.columns:
            st.error("Date column not found in the data")
            st.write("Available columns:", df.columns.tolist())
            return

        # Filter hanya baris dengan format tanggal valid sebelum parsing
        df = df[df[date_column].astype(str).str.match(r'^(\d{4}-\d{2}-\d{2}|\d{2}_\d{2}_\d{2})$', na=False)]
        if not df.empty:
            df[date_column] = pd.to_datetime(df[date_column], errors='coerce')
            df = df[df[date_column].notna()]
        
        # Only proceed if we have data
        if not df.empty:
            # Daily attendance chart - Updated untuk selalu menampilkan semua tanggal dengan data
            daily_counts = df.groupby(date_column).size().reset_index(name='count')
            daily_counts[date_column] = pd.to_datetime(daily_counts[date_column])
            daily_counts = daily_counts.sort_values(date_column)
            
            # Create line chart dengan marker untuk lebih jelas melihat tiap tanggal
            fig = px.line(
                daily_counts,
                x=date_column,
                y='count',
                title='Tren Kehadiran (Real-time Update)',
                labels={'count': 'Jumlah Kehadiran', date_column: 'Tanggal'},
                markers=True,
                line_shape='spline'
            )
            
            # Improve layout untuk readability
            fig.update_layout(
                hovermode='x unified',
                height=450,
                xaxis=dict(
                    tickformat='%d-%m-%Y',
                    tickangle=-45
                ),
                template='plotly_white'
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Hourly distribution
            if time_column in df.columns:
                df['Hour'] = pd.to_datetime(df[time_column]).dt.hour
                hourly_counts = df.groupby('Hour').size().reset_index(name='count')
                hourly_counts = hourly_counts.sort_values('Hour')
                
                fig2 = px.bar(
                    hourly_counts,
                    x='Hour',
                    y='count',
                    title='⏰ Distribusi Jam Kehadiran',
                    labels={'count': 'Jumlah', 'Hour': 'Jam'},
                    color='count',
                    color_continuous_scale='Blues'
                )
                
                fig2.update_layout(
                    height=450,
                    hovermode='x unified',
                    template='plotly_white'
                )
                
                st.plotly_chart(fig2, use_container_width=True)
            
        # Show weekly summary
        st.subheader("Rekap Mingguan")
        
        # Get current week dates
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        dates_of_week = [(start_of_week + timedelta(days=x)).date() for x in range(7)]
        
        # Filter df untuk hanya data minggu ini (dan data valid dengan format tanggal)
        df_weekly = df.copy() if not df.empty else pd.DataFrame()
        
        # Create weekly summary - UPDATED untuk real-time counting
        weekly_data = []
        for i, date in enumerate(dates_of_week):
            if not df_weekly.empty:
                # Filter data untuk tanggal spesifik
                day_data = df_weekly[df_weekly[date_column].dt.date == date]
            else:
                day_data = pd.DataFrame()
            
            # Calculate statistics - ALWAYS GET FRESH COUNT FROM CURRENT DAY'S DATA
            total_attendance = len(day_data) if not day_data.empty else 0
            on_time = len(day_data[day_data['status'] == 'on_time']) if (not day_data.empty and 'status' in day_data.columns) else 0
            late = len(day_data[day_data['status'] == 'late']) if (not day_data.empty and 'status' in day_data.columns) else 0
            
            day_names = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
            
            weekly_data.append({
                'Tanggal': date.strftime('%d %b %Y'),
                'Hari': day_names[date.weekday()],
                'Total Hadir': total_attendance,
                'Tepat Waktu': on_time,
                'Terlambat': late
            })
        
        # Display weekly summary
        weekly_df = pd.DataFrame(weekly_data)
        st.dataframe(
            weekly_df,
            column_config={
                'Tanggal': st.column_config.TextColumn('Tanggal', width=200),
                'Hari': st.column_config.TextColumn('Hari', width=150),
                'Total Hadir': st.column_config.NumberColumn('Total Hadir', format='%d'),
                'Tepat Waktu': st.column_config.NumberColumn('Tepat Waktu', format='%d'),
                'Terlambat': st.column_config.NumberColumn('Terlambat', format='%d')
            },
            use_container_width=True,
            hide_index=True
        )

# The show_user_management function is now imported from new_user_management.py
# The user management functionality has been moved to new_user_management.py
# This provides improved UI and functionality for managing user images

class RegistrationError(Exception):
    """Custom exception for registration errors"""
    pass

def validate_user_input(user_data: dict) -> Tuple[bool, str]:
    """
    Validate all user registration input
    Returns: (is_valid, error_message)
    """
    name = user_data.get('name', '').strip()
    
    # Validasi nama
    if not name:
        return False, "⚠️ Nama user harus diisi!"
    if len(name) < 2:
        return False, "⚠️ Nama user terlalu pendek!"
    if not name.replace(" ", "").isalnum():
        return False, "⚠️ Nama user hanya boleh mengandung huruf dan angka!"
        
    # Validasi shift
    if user_data.get('shift') not in ['morning', 'night']:
        return False, "⚠️ Shift tidak valid!"
        
    # Validasi role
    if user_data.get('role') not in ['employee', 'supervisor', 'manager']:
        return False, "⚠️ Role tidak valid!"
        
    return True, ""

def check_user_exists(name: str) -> bool:
    """
    Check if user already exists in the system
    Returns: True if user exists
    """
    attendance_dir = Path(__file__).parent.parent / "Attendance_data"
    user_file = attendance_dir / f"{name}.png"
    user_folder = attendance_dir / name
    
    return user_file.exists() or user_folder.exists()

def prepare_registration(user_data: dict) -> Tuple[bool, str, subprocess.Popen]:
    """
    Prepare and start the registration process
    Returns: (success, message, process)
    """
    try:
        script_path = Path(__file__).parent.parent / "initial_data_capture.py"
        
        # Validasi script exists
        if not script_path.exists():
            return False, f"❌ Script registrasi tidak ditemukan di: {script_path}", None
            
        # Cek user exists
        if check_user_exists(user_data['name']):
            return False, f"❌ User dengan nama '{user_data['name']}' sudah terdaftar!", None
            
        # Siapkan command dengan pipe agar bisa capture output
        process = subprocess.Popen(
            [sys.executable, str(script_path), user_data['name']],
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            universal_newlines=True)
            
        # Tunggu sebentar untuk memastikan process mulai
        time.sleep(1)
        
        if process.poll() is not None:  # Process gagal dimulai
            return False, "❌ Gagal memulai proses registrasi", None
            
        return True, "✅ Proses registrasi dimulai!", process
        
    except Exception as e:
        return False, f"❌ Error: {str(e)}", None

def get_registration_status(process: subprocess.Popen) -> Tuple[bool, str]:
    """
    Check registration process status from running process
    Returns: (is_running, status_message)
    """
    if not process:
        return False, "❌ Process tidak ditemukan"
        
    # Cek apakah process masih berjalan
    if process.poll() is None:
        # Coba baca output terakhir
        try:
            # Baca output tanpa blocking
            stdout = process.stdout.readline().strip()
            stderr = process.stderr.readline().strip()
            
            # Update status based on output
            if stdout:
                if "center image captured" in stdout.lower():
                    return True, "✅ Foto tengah berhasil diambil"
                elif "left image captured" in stdout.lower():
                    return True, "✅ Foto kiri berhasil diambil"
                elif "right image captured" in stdout.lower():
                    return True, "✅ Foto kanan berhasil diambil"
                elif "Look at CENTER" in stdout:
                    return True, "🎯 Lihat ke tengah"
                elif "TURN LEFT" in stdout:
                    return True, "👈 Hadap ke kiri"
                elif "TURN RIGHT" in stdout:
                    return True, "👉 Hadap ke kanan"
                elif "Get ready" in stdout:
                    return True, "⏳ Bersiap untuk foto..."
                elif "All images captured" in stdout:
                    return False, "✅ Registrasi berhasil!"
                else:
                    return True, stdout
            
            # Cek error
            if stderr:
                return False, f"❌ Error: {stderr}"
                
            # Process masih jalan tapi tidak ada output baru
            return True, "⏳ Memproses..."
            
        except Exception as e:
            # Masih jalan tapi tidak bisa baca output
            return True, "⏳ Memproses..."
            




if __name__ == "__main__":
    main()