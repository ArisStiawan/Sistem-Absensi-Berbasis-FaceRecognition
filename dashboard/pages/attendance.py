import streamlit as st
from pathlib import Path
import subprocess
import time
import sys
import os
import csv
from datetime import datetime
from utils import sound
import pandas as pd
import traceback
import io
import logging

logger = logging.getLogger(__name__)
# Optional: at app start you can set logging level once, e.g. in app entrypoint:
# logging.basicConfig(level=logging.INFO)

def get_current_root_dir():
    """Get the root directory where main.py is located"""
    return Path(__file__).parent.parent.parent

def safe_read_attendance_csv(csv_path, verbose=False):
    """
    Safely read attendance CSV with aggressive error recovery.
    Now prefer python engine first to avoid C-engine tokenizing error spam.
    """
    if not csv_path.exists():
        if verbose: logger.debug(f"CSV file does not exist: {csv_path}")
        return None
    
    try:
        if verbose: logger.debug(f"Attempting to read CSV: {csv_path}")
        
        # Prefer python engine first (tolerant to variable fields)
        try:
            df = pd.read_csv(csv_path, engine='python', on_bad_lines='skip', dtype=str)
            if verbose: logger.debug("✓ Strategy A succeeded (engine='python', skip bad lines)")
            return df
        except Exception as e_py:
            if verbose: logger.debug(f"✗ Strategy A failed: {type(e_py).__name__}: {str(e_py)[:120]}")

        # Fallback: default C engine (fast) if file is already clean
        try:
            df = pd.read_csv(csv_path)
            if verbose: logger.debug("✓ Strategy B succeeded (default C engine)")
            return df
        except Exception as e_c:
            if verbose: logger.debug(f"✗ Strategy B failed: {type(e_c).__name__}: {str(e_c)[:120]}")

        # Try different separators
        for sep in [',', ';', '\t', '|', ' ']:
            try:
                df = pd.read_csv(csv_path, sep=sep, engine='python', on_bad_lines='skip', dtype=str)
                if len(df.columns) >= 2:
                    if verbose: logger.debug(f"✓ Strategy C succeeded (separator='{sep}')")
                    return df
            except Exception:
                continue
        
        # Line-by-line repair
        try:
            lines = []
            with open(csv_path, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            if not all_lines:
                return None
            header = all_lines[0].strip()
            header_count = len(header.split(','))
            lines.append(header)
            for line in all_lines[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',')
                if len(parts) > header_count:
                    parts = parts[:header_count]
                elif len(parts) < header_count:
                    parts.extend([''] * (header_count - len(parts)))
                lines.append(','.join(parts))
            csv_content = '\n'.join(lines)
            df = pd.read_csv(io.StringIO(csv_content), dtype=str)
            if verbose: logger.debug("✓ Strategy D succeeded (line-by-line repair)")
            return df
        except Exception as e_fix:
            if verbose: logger.debug(f"✗ Strategy D failed: {type(e_fix).__name__}: {str(e_fix)[:120]}")

        # Raw reader fallback
        try:
            data = []
            header = None
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i == 0:
                        header = row
                        continue
                    if not row or all(not str(c).strip() for c in row):
                        continue
                    data.append(row)
            if data and header:
                df = pd.DataFrame(data, columns=header[:len(header)])
                if verbose: logger.debug("✓ Strategy E succeeded (raw csv.reader)")
                return df
        except Exception as e_raw:
            if verbose: logger.debug(f"✗ Strategy E failed: {type(e_raw).__name__}: {str(e_raw)[:120]}")

        return None
    except Exception as e:
        logger.exception(f"Unexpected error in safe_read_attendance_csv: {e}")
        return None

def validate_attendance_dataframe(df):
    """
    Validate dan clean attendance dataframe
    
    Args:
        df: DataFrame to validate
        
    Returns:
        pd.DataFrame: Cleaned dataframe
    """
    if df is None or df.empty:
        return df
    
    try:
        # Normalisasi nama kolom tanpa .str (hindari error pada Jetson/older pandas)
        df.columns = [str(c).strip() for c in df.columns]
        
        # Cari dan rename kolom yang relevan
        col_mapping = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'name' in col_lower or col_lower == 'nama':
                col_mapping[col] = 'Name'
            elif 'time' in col_lower or col_lower == 'waktu':
                col_mapping[col] = 'Time'
            elif 'date' in col_lower or col_lower == 'tanggal':
                col_mapping[col] = 'Date'
            elif 'shift' in col_lower:
                col_mapping[col] = 'Shift'
            elif 'status' in col_lower:
                col_mapping[col] = 'Status'
        
        df = df.rename(columns=col_mapping)
        
        # Drop duplicate columns if any
        df = df.loc[:, ~df.columns.duplicated()]
        
        # Remove rows where all values are empty
        df = df.dropna(how='all')
        
        return df
    except Exception as e:
        print(f"Error in validate_attendance_dataframe: {e}")
        return df

def get_current_attendance():
    """Get today's attendance records"""
    try:
        current_date = datetime.now().strftime("%y_%m_%d")
        attendance_file = get_current_root_dir() / "Attendance_Entry" / f"Attendance_{current_date}.csv"
        
        df = safe_read_attendance_csv(attendance_file)
        
        if df is None:
            return []
        
        df = validate_attendance_dataframe(df)
        return df.to_dict('records')
        
    except Exception as e:
        print(f"Error reading attendance: {e}")
        traceback.print_exc()
        return []

def check_registration():
    """Check if any users are registered in the system"""
    attendance_dir = get_current_root_dir() / "Attendance_data"
    if not attendance_dir.exists():
        return False
    
    # Check for any user folders or files
    try:
        items = list(attendance_dir.iterdir())
        return len(items) > 0
    except:
        return False

def start_attendance(mode="checkin"):
    """
    This is a placeholder function to maintain compatibility with existing code.
    The actual attendance is now handled directly within the Streamlit interface.
    """
    return True

def get_shift_status(recognized_name):
    """
    Get user's shift and attendance status
    Returns: (assigned_shift, current_shift, status, is_checkout)
    """
    now = datetime.now()
    current_hour = now.hour
    
    # Define shift times
    morning_start = 8    # 08:00
    morning_end = 17     # 17:00
    night_start = 17     # 17:00
    night_end = 22      # 22:00
    
    # Toleransi untuk shift malam yang datang lebih awal
    night_early_start = 16  # Boleh datang 1 jam sebelum shift
    
    # Determine current shift
    if morning_start <= current_hour < morning_end:
        current_shift = "morning"
    elif night_early_start <= current_hour <= night_end:  # Diperluas untuk toleransi
        current_shift = "night"
    else:
        current_shift = "outside_hours"  # Di luar jam kerja
    
    # Get user's assigned shift from registration data
    root_dir = get_current_root_dir()
    try:
        import json
        with open(root_dir / "user_data.json", "r") as f:
            user_data = json.load(f)
            if recognized_name in user_data:
                assigned_shift = user_data[recognized_name].get('shift', 'morning')
            else:
                assigned_shift = 'morning'  # default to morning if not found
    except:
        assigned_shift = 'morning'  # default to morning if file not found
        
    # Check if this is checkout time based on shift
    is_checkout = False
    if current_shift == "morning" and current_hour >= 16:  # Bisa checkout mulai 16:00
        is_checkout = True
    elif current_shift == "night" and current_hour >= 21:  # Bisa checkout mulai 21:00
        is_checkout = True
    
    # Check if already checked in today
    has_checked_in = False
    try:
        attendance_file = get_current_root_dir() / "Attendance_Entry" / f"Attendance_{now.strftime('%y_%m_%d')}.csv"
        df = safe_read_attendance_csv(attendance_file)
        if df is not None:
            df = validate_attendance_dataframe(df)
            if 'Name' in df.columns:
                has_checked_in = recognized_name in df['Name'].values
    except:
        pass  # Assume not checked in if can't read file
    
    # Determine status based on time and check-in status
    if current_shift == "outside_hours":
        status = "outside_hours"  # Di luar jam kerja
    elif is_checkout:
        if not has_checked_in:
            status = "no_checkin"  # Trying to checkout without checkin
        else:
            status = "checkout"
    else:
        # For check-in
        if has_checked_in:
            status = "already_checkedin"
        else:
            # Cek kesesuaian shift
            shift_match = assigned_shift == current_shift
            
            if current_shift == "morning" and assigned_shift == "night":
                status = "wrong_shift"  # User shift malam mencoba absen di pagi hari
            elif current_shift == "night" and assigned_shift == "morning":
                # Toleransi khusus untuk shift pagi yang lembur/overlap ke shift malam
                if current_hour < night_start:  # Sebelum jam 17:00
                    status = "overtime_checkin"
                else:
                    status = "wrong_shift"
            else:
                # Normal check-in sesuai shift
                if current_shift == "morning":
                    status = "on_time" if current_hour <= 8 else "late"
                else:  # night shift
                    # Toleransi untuk shift malam yang datang lebih awal
                    status = "on_time" if current_hour <= 17 else "late"
        
    return assigned_shift, current_shift, status, is_checkout

def process_recognized_face(recognized_name):
    """
    Process a recognized face and record attendance
    
    Args:
        recognized_name: Name of the recognized person
        
    Returns:
        str: Status message to display
    """
    try:
        # Get shift status
        assigned_shift, current_shift, status, is_checkout = get_shift_status(recognized_name)
        
        # Record attendance
        now = datetime.now()
        attendance_file = get_current_root_dir() / "Attendance_Entry" / f"Attendance_{now.strftime('%y_%m_%d')}.csv"
        
        # Ensure directory exists
        attendance_file.parent.mkdir(exist_ok=True)
        
        # Create or append to CSV dengan struktur yang konsisten
        file_exists = attendance_file.exists()
        with open(attendance_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Name", "Time", "Date", "Shift", "Status"])
            writer.writerow([
                recognized_name,
                now.strftime('%H:%M:%S'),
                now.strftime('%Y-%m-%d'),
                current_shift,
                status
            ])
        
        # Prepare status message based on attendance type and status
        message = ""
        if status == "outside_hours":
            message = f"❌ Di luar jam kerja!\nNama: {recognized_name}\n\nJam kerja:\nShift Pagi: 08:00 - 17:00\nShift Malam: 17:00 - 22:00"
        elif status == "wrong_shift":
            message = (f"⚠️ Ketidaksesuaian Shift!\n"
                     f"Nama: {recognized_name}\n"
                     f"Anda terdaftar di shift {assigned_shift.upper()}\n"
                     f"Jam kerja Anda:\n"
                     f"{'08:00 - 17:00' if assigned_shift == 'morning' else '17:00 - 22:00'}")
        elif status == "overtime_checkin":
            message = (f"⚠️ Perhatian - Overtime Check-in\n"
                     f"Nama: {recognized_name}\n"
                     f"Anda melakukan check-in di luar shift normal Anda (Shift {assigned_shift.upper()})\n"
                     f"Absensi akan dicatat sebagai overtime/lembur.")
            try:
                sound.play_sound('notification')
            except:
                pass
        elif status == "no_checkin":
            message = f"❌ Tidak dapat melakukan checkout!\nNama: {recognized_name}\nAnda belum melakukan check-in hari ini."
        elif status == "already_checkedin":
            message = f"⚠️ Sudah absen masuk!\nNama: {recognized_name}\nSilakan lakukan checkout di jam pulang."
        elif status == "checkout":
            message = f"✅ Checkout berhasil!\nNama: {recognized_name}\nTerima kasih atas kerja kerasnya hari ini!"
            try:
                sound.play_sound('success')
            except:
                pass
        else:
            time_status = "tepat waktu" if status == "on_time" else "terlambat"
            shift_info = ""
            if assigned_shift != current_shift and status != "overtime_checkin":
                shift_info = f"\n⚠️ Anda terdaftar di shift {assigned_shift} tapi melakukan absensi di shift {current_shift}"
            
            batas_telat = "08:00" if current_shift == "morning" else "17:00"
            message = f"✅ Check-in berhasil!\nNama: {recognized_name}\nStatus: {time_status} (Batas: {batas_telat}){shift_info}"
            if status == "on_time":
                try:
                    sound.play_sound('success')
                except:
                    pass
            else:
                try:
                    sound.play_sound('notification')
                except:
                    pass
                
        return message
    except Exception as e:
        print(f"Error in process_recognized_face: {e}")
        traceback.print_exc()
        return f"❌ Error: {str(e)}"

def show_attendance():
    """Show attendance capture page"""
    st.header("✅ Face Recognition Attendance")
    
    # Helper to manage external attendance window (main.py)
    def _start_external_attendance():
        root = get_current_root_dir()
        if 'attendance_proc' in st.session_state and st.session_state['attendance_proc'] is not None:
            return False, "Attendance window is already running"
        try:
            # Launch main.py in a separate process so it can open its own OpenCV window
            proc = subprocess.Popen([sys.executable, str(root / "main.py")], cwd=str(root))
            st.session_state['attendance_proc'] = proc
            return True, "Started external attendance window (OpenCV)"
        except Exception as e:
            return False, f"Failed to start main.py: {e}"

    def _stop_external_attendance():
        proc = st.session_state.get('attendance_proc')
        if proc is None:
            return False, "No attendance window process to stop"
        try:
            # Try graceful termination first
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            st.session_state['attendance_proc'] = None
            return True, "Stopped external attendance window"
        except Exception as e:
            return False, f"Failed to stop attendance window: {e}"
    
    # Check if users are registered
    if not check_registration():
        st.warning("⚠️ Belum ada user yang terdaftar. Silakan registrasi user terlebih dahulu di menu Register New User.")
        if st.button("Ke Halaman Registrasi", type="primary"):
            st.session_state['current_page'] = "Register New User"
            st.rerun()
        return
    
    # Create tabs for attendance actions and history
    tab1, tab2 = st.tabs(["Absensi", "Riwayat Absensi"])
    
    with tab1:

        # Process status
        proc = st.session_state.get('attendance_proc')
        running = proc is not None and (proc.poll() is None)
        status_text = "Running" if running else "Stopped"
        st.metric("External Attendance Status", status_text)

        c1, c2 = st.columns(2)
        with c1:
            if not running:
                if st.button("▶️ Start Attendance (OpenCV Window)", type="primary", use_container_width=True):
                    ok, msg = _start_external_attendance()
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            else:
                st.button("▶️ Start Attendance (OpenCV Window)", disabled=True, use_container_width=True)
        with c2:
            if running:
                if st.button("⏹ Stop Attendance", use_container_width=True):
                    ok, msg = _stop_external_attendance()
                    if ok:
                        st.warning(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            else:
                st.button("⏹ Stop Attendance", disabled=True, use_container_width=True)

        st.markdown("""
        Tips:
        - Jika jendela OpenCV tidak muncul, pastikan izin kamera diberikan dan dependency terinstal.
        - Tutup jendela OpenCV (ESC) atau gunakan tombol Stop di sini untuk mengakhiri proses.
        """)
    
    with tab2:
        st.subheader("📊 Riwayat Absensi")
        
        # Date selector for attendance history
        col1, col2 = st.columns([2,2])
        with col1:
            # Gunakan date() bukan datetime untuk kompatibilitas Jetson Nano
            default_date = datetime.now().date()
            selected_date = st.date_input(
                "Pilih Tanggal",
                default_date
            )
        
        # Guard: konversi string ke date jika perlu (untuk kompatibilitas Streamlit lama)
        if isinstance(selected_date, str):
            try:
                selected_date = pd.to_datetime(selected_date).date()
            except Exception:
                selected_date = datetime.now().date()
        
        # Format date for filename
        date_str = selected_date.strftime("%y_%m_%d")
        attendance_file = get_current_root_dir() / "Attendance_Entry" / f"Attendance_{date_str}.csv"
        
        if attendance_file.exists():
            try:
                df = safe_read_attendance_csv(attendance_file)  # no verbose to keep terminal clean
                if df is None or df.empty:
                    st.info(f"Tidak ada data absensi untuk tanggal {selected_date.strftime('%d-%m-%Y')}")
                else:
                    df = validate_attendance_dataframe(df)

                    # Standarisasi kolom Time tanpa warning (ekstrak HH:MM:SS)
                    if 'Time' in df.columns:
                        try:
                            # Aman untuk semua versi pandas: convert to str, extract, kemudian fillna
                            df['Time'] = df['Time'].astype(str).str.extract(r'(\d{1,2}:\d{2}:\d{2})', expand=False).fillna(df['Time'].astype(str))
                        except Exception as e:
                            print(f"Warning: Could not format Time column: {e}")
                            # Fallback: keep original Time values
                            pass

                    st.dataframe(
                        df,
                        column_config={
                            "Name": "Nama",
                            "Time": "Waktu",
                            "Date": "Tanggal",
                            "Shift": "Shift",
                            "Status": "Status"
                        },
                        hide_index=True,
                        use_container_width=True
                    )

                    # Summary metrics
                    total_records = len(df)
                    if total_records > 0:
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Absensi", total_records)
                        if 'Shift' in df.columns:
                            shifts = df['Shift'].value_counts()
                            with col2:
                                st.metric("Shift Pagi", shifts.get('morning', 0))
                            with col3:
                                st.metric("Shift Malam", shifts.get('night', 0))
            except Exception as e:
                st.error(f"Error membaca data absensi: {str(e)}")
        else:
            st.info(f"Tidak ada data absensi untuk tanggal {selected_date.strftime('%d-%m-%Y')}")
