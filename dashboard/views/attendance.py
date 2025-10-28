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
    """
    if df is None or df.empty:
        return df
    
    try:
        # Normalisasi nama kolom
        df.columns = df.columns.str.strip()
        df.columns = df.columns.str.lower()
        
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
        df = df.loc[:, ~df.columns.duplicated()]
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
    
    try:
        items = list(attendance_dir.iterdir())
        return len(items) > 0
    except:
        return False

def start_attendance(mode="checkin"):
    return True

def show_attendance():
    """Show attendance capture page"""
    st.header("✅ Face Recognition Attendance")
    
    def _start_external_attendance():
        root = get_current_root_dir()
        if 'attendance_proc' in st.session_state and st.session_state['attendance_proc'] is not None:
            return False, "Attendance window is already running"
        try:
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
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            st.session_state['attendance_proc'] = None
            return True, "Stopped external attendance window"
        except Exception as e:
            return False, f"Failed to stop attendance window: {e}"
    
    if not check_registration():
        st.warning("⚠️ Belum ada user yang terdaftar. Silakan registrasi user terlebih dahulu di menu Register New User.")
        if st.button("Ke Halaman Registrasi", type="primary"):
            st.session_state['current_page'] = "Register New User"
            st.rerun()
        return
    
    tab1, tab2 = st.tabs(["Absensi", "Riwayat Absensi"])
    
    with tab1:
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
        col1, _ = st.columns([2,2])
        with col1:
            selected_date = st.date_input(
                "Pilih Tanggal",
                datetime.now()
            )
        date_str = selected_date.strftime("%y_%m_%d")
        attendance_file = get_current_root_dir() / "Attendance_Entry" / f"Attendance_{date_str}.csv"
        
        if attendance_file.exists():
            try:
                df = safe_read_attendance_csv(attendance_file)
                if df is None or df.empty:
                    st.info(f"Tidak ada data absensi untuk tanggal {selected_date.strftime('%d-%m-%Y')}")
                else:
                    df = validate_attendance_dataframe(df)
                    if 'Time' in df.columns:
                        df['Time'] = df['Time'].astype(str).str.extract(r'(\b\d{1,2}:\d{2}:\d{2}\b)')[0]
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
    
    st.divider()
    st.subheader("Riwayat Absensi Hari Ini")

    try:
        attendance_file = get_current_root_dir() / "Attendance_Entry" / f"Attendance_{datetime.now().strftime('%y_%m_%d')}.csv"
        if attendance_file.exists():
            df = safe_read_attendance_csv(attendance_file)
            if df is not None and not df.empty:
                df = validate_attendance_dataframe(df)
                if 'Time' in df.columns:
                    df['Time'] = df['Time'].astype(str).str.extract(r'(\b\d{1,2}:\d{2}:\d{2}\b)')[0]
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Belum ada absensi hari ini")
        else:
            st.info("Belum ada absensi hari ini")
    except Exception as e:
        st.error(f"Error membaca riwayat absensi: {str(e)}")
