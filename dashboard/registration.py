import streamlit as st
from pathlib import Path
import subprocess
import time
import sys
import os
from typing import Tuple

def navigate_to(page_name: str):
    """
    Navigate to a different page and reset registration state if needed
    """
    st.session_state['current_page'] = page_name
    if page_name != 'Register New User':
        st.session_state['registration_state'] = {
            'is_registering': False,
            'current_step': 0,
            'user_data': None,
            'process': None,
            'error': None
        }

def check_user_exists(name: str) -> bool:
    """
    Check if user already exists in the system
    Returns: True if user exists
    """
    # Get the root project directory (where main.py is)
    root_dir = Path(__file__).parent.parent
    attendance_dir = root_dir / "Attendance_data"
    
    # Check both single image and folder formats
    user_file = attendance_dir / f"{name}.png"
    user_folder = attendance_dir / name
    
    # Also check if user exists in either location
    dashboard_attendance_dir = Path(__file__).parent / "Attendance_data"
    dashboard_user_file = dashboard_attendance_dir / f"{name}.png"
    dashboard_user_folder = dashboard_attendance_dir / name
    
    return any([
        user_file.exists(),
        user_folder.exists(),
        dashboard_user_file.exists(),
        dashboard_user_folder.exists()
    ])

def prepare_registration(user_data: dict) -> Tuple[bool, str, None]:
    """
    Prepare the registration process (integrated version)
    Returns: (success, message, None)
    """
    try:
        # Get root project directory
        root_dir = Path(__file__).parent.parent.resolve()
        
        # Save user data for shift management
        user_data_file = root_dir / "user_data.json"
        try:
            import json
            if user_data_file.exists():
                with open(user_data_file, 'r') as f:
                    saved_data = json.load(f)
            else:
                saved_data = {}
            
            # Add new user data
            saved_data[user_data['name']] = {
                'shift': user_data['shift'],
                'role': user_data['role']
            }
            
            with open(user_data_file, 'w') as f:
                json.dump(saved_data, f, indent=4)
        except Exception as e:
            st.warning(f"Warning: Could not save user shift data: {str(e)}")
        
        # Cek user exists
        if check_user_exists(user_data['name']):
            return False, f"❌ User dengan nama '{user_data['name']}' sudah terdaftar!", None

        # Make sure main Attendance_data directory exists (do not pre-create user folder;
        # initial_data_capture will create it to avoid name-exists conflict)
        attendance_dir = root_dir / "Attendance_data"
        attendance_dir.mkdir(exist_ok=True)

        # Initialize registration state
        return True, "✅ Proses registrasi dimulai! Silakan ikuti instruksi selanjutnya.", None

    except Exception as e:
        return False, f"❌ Error: {str(e)}", None

def check_registration_complete() -> Tuple[bool, str]:
    """
    Check if registration is complete by verifying all required images exist
    Returns: (is_complete, status_message)
    """
    if 'registration_state' not in st.session_state or not st.session_state.registration_state['user_data']:
        return False, "❌ No active registration"
    
    username = st.session_state.registration_state['user_data']['name']
    root_dir = Path(__file__).parent.parent
    user_folder = root_dir / "Attendance_data" / username
    
    # Check if all required images exist
    if user_folder.exists():
        missing_poses = []
        for pose in ['center', 'left', 'right']:
            if not (user_folder / f"{pose}.png").exists():
                missing_poses.append(pose)
        
        if not missing_poses:
            return True, "✅ Registrasi berhasil!"
        else:
            return False, f"⏳ Masih perlu foto: {', '.join(missing_poses)}"
    else:
        return False, "⏳ Persiapan registrasi..."

def render_registration_form() -> dict:
    """
    Render the registration form and return user input
    """
    with st.form("user_registration", clear_on_submit=True):
        user_name = st.text_input(
            "Masukkan Nama User",
            placeholder="Contoh: John Doe",
            help="Nama harus unik dan hanya mengandung huruf dan angka"
        ).strip()
        
        col1, col2 = st.columns(2)
        with col1:
            shift = st.selectbox(
                "Pilih Shift",
                ["morning", "night"],
                help="Pilih shift kerja user"
            )
        with col2:
            role = st.selectbox(
                "Pilih Role",
                ["employee", "supervisor", "manager"],
                help="Pilih role/jabatan user"
            )
        
        submitted = st.form_submit_button(
            "Mulai Registrasi",
            use_container_width=True,
            type="primary"
        )
        
        if submitted:
            return {
                'name': user_name,
                'shift': shift,
                'role': role
            }
    return None

def render_registration_progress():
    """
    Render registration progress and instructions
    """
    # Progress steps
    steps = [
        "Persiapan Registrasi",
        "Pengambilan Foto Tengah",
        "Pengambilan Foto Kiri",
        "Pengambilan Foto Kanan",
        "Finalisasi"
    ]
    
    current_step = st.session_state.registration_state['current_step']
    
    # Progress bar
    progress_val = current_step / (len(steps) - 1)
    st.progress(progress_val)
    
    # Step indicator
    if current_step < len(steps):
        st.info(f"📸 Langkah saat ini: {steps[current_step]}")
    
    # Instructions based on current step
    if current_step == 0:
        st.info("Tunggu sebentar, window kamera akan terbuka...")
    elif current_step == 1:
        st.info("Posisikan wajah menghadap ke kamera")
    elif current_step == 2:
        st.info("Posisikan wajah menghadap ke kiri")
    elif current_step == 3:
        st.info("Posisikan wajah menghadap ke kanan")
    elif current_step == 4:
        st.success("✅ Registrasi selesai! Form akan direset otomatis...")

def show_user_registration():
    """
    Handle user registration process by launching initial_data_capture.py
    in an external OpenCV window (like Attendance).
    """
    st.header("Register New User")
    st.write("Gunakan halaman ini untuk mendaftarkan user baru ke sistem face recognition.")

    # Initialize simple process state holders
    if 'reg_process' not in st.session_state:
        st.session_state.reg_process = None
    if 'reg_user' not in st.session_state:
        st.session_state.reg_user = None
    if 'reg_started_at' not in st.session_state:
        st.session_state.reg_started_at = None
    if 'reg_last_result' not in st.session_state:
        st.session_state.reg_last_result = None

    # Show last completion status if any
    if st.session_state.reg_last_result:
        res = st.session_state.reg_last_result
        ts = time.strftime('%H:%M:%S', time.localtime(res.get('timestamp', time.time())))
        if res.get('status') == 'success':
            st.success(f"✅ Registrasi untuk '{res.get('user','')}' selesai pada {ts}.")
        else:
            st.warning(f"ℹ️ Registrasi untuk '{res.get('user','')}' belum lengkap pada {ts}. Silakan coba lagi.")
        if st.button("Tutup notifikasi", key="reg_close_notice"):
            st.session_state.reg_last_result = None
            st.rerun()

    # If a registration process is running, show controls
    if st.session_state.reg_process is not None:
        proc = st.session_state.reg_process
        code = proc.poll()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Status", "Running" if code is None else "Finished")
        with col2:
            st.metric("User", st.session_state.reg_user or "-")
        with col3:
            if st.session_state.reg_started_at:
                elapsed = time.time() - st.session_state.reg_started_at
                st.metric("Elapsed", f"{int(elapsed)}s")

        if code is None:
            if st.button("Stop Registration", type="secondary"):
                try:
                    proc.terminate()
                except Exception:
                    pass
                st.session_state.reg_process = None
                st.rerun()
        else:
            # Process finished: check captured images
            root_dir = Path(__file__).parent.parent
            user_folder = root_dir / "Attendance_data" / (st.session_state.reg_user or "")
            required = [user_folder / f for f in ("center.png", "left.png", "right.png")]
            if all(p.exists() for p in required):
                st.session_state.reg_last_result = {
                    'status': 'success',
                    'user': st.session_state.reg_user or '',
                    'timestamp': time.time(),
                }
            else:
                st.session_state.reg_last_result = {
                    'status': 'incomplete',
                    'user': st.session_state.reg_user or '',
                    'timestamp': time.time(),
                }
            # Clear process state
            st.session_state.reg_process = None
            st.session_state.reg_started_at = None
            st.session_state.reg_user = None
            st.rerun()
        return

    # No process running: show registration form
    user_data = render_registration_form()
    if user_data:
        if not user_data['name']:
            st.error("❌ Nama user harus diisi!")
            return
        # Prepare (save user_data.json and ensure base folder)
        success, message, _ = prepare_registration(user_data)
        if not success:
            st.error(message)
            return
        # Launch initial_data_capture.py with username argument
        root_dir = Path(__file__).parent.parent
        script_path = root_dir / "initial_data_capture.py"
        if not script_path.exists():
            st.error("❌ initial_data_capture.py tidak ditemukan di root project.")
            return
        try:
            # Pass flag to prevent auto-open of attendance window after registration
            proc = subprocess.Popen([sys.executable, str(script_path), user_data['name'], "--no-run-main"], cwd=str(root_dir))
            st.session_state.reg_process = proc
            st.session_state.reg_user = user_data['name']
            st.session_state.reg_started_at = time.time()
            st.info("📷 Window registrasi telah dibuka. Ikuti instruksi pada jendela tersebut.")
            st.rerun()
        except Exception as e:
            st.error(f"Gagal menjalankan proses registrasi: {e}")