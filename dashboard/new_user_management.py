import streamlit as st
import os
import shutil
import json
from pathlib import Path
import requests
import time
from utils import delete_user_completely, delete_user_image, get_user_images, get_user_data

API_URL = "http://localhost:8000"

def api_call(endpoint: str, method="get", **kwargs):
    """Helper untuk panggil API"""
    url = f"{API_URL}{endpoint}"
    try:
        if method == "get":
            r = requests.get(url, **kwargs)
        elif method == "delete":
            r = requests.delete(url, **kwargs)
        elif method == "post":
            r = requests.post(url, **kwargs)
        else:
            raise ValueError("Method tidak dikenal")

        if r.status_code != 200:
            st.error(f"API Error {r.status_code}: {r.text}")
            return None
        return r.json()
    except Exception as e:
        st.error(f"Gagal koneksi ke API: {e}")
        return None


def show_user_management():
    st.header("👤 User Management")

    # Get user metadata from JSON first (this has shift and role info)
    user_meta = get_user_data() or {}

    # Get API users if available
    users_response = api_call("/users")
    registered_users = []
    if users_response and "data" in users_response:
        # API is available, but we need to enrich with shift/role data from user_meta
        registered_users = users_response["data"]
        # Enrich API data with shift and role from user_meta JSON
        for user in registered_users:
            user_name = user.get("name", "")
            if user_name in user_meta:
                # Merge metadata (shift, role) from user_data.json
                user["shift"] = user_meta[user_name].get("shift", user.get("shift", "morning"))
                user["role"] = user_meta[user_name].get("role", user.get("role", "employee"))
            else:
                # If not in user_meta, set default
                user.setdefault("shift", "morning")
                user.setdefault("role", "employee")
    else:
        # Fallback to local file scan if API isn't working
        root_dir = Path(__file__).parent.parent
        dashboard_dir = Path(__file__).parent
        attendance_dirs = []
        if (root_dir / "Attendance_data").exists():
            attendance_dirs.append(root_dir / "Attendance_data")
        if (dashboard_dir / "Attendance_data").exists():
            attendance_dirs.append(dashboard_dir / "Attendance_data")

        if not attendance_dirs:
            st.warning("⚠️ Folder Attendance_data tidak ditemukan.")
            return

        st.warning("⚠️ API tidak tersedia, menggunakan data lokal")

        # Aggregate users from all possible Attendance_data locations
        users_map = {}
        for attendance_dir in attendance_dirs:
            # Single-image users
            for img in attendance_dir.glob("*.png"):
                name = img.stem
                # Prefer directory/multiple over single if both exist later
                if name not in users_map:
                    shift_val = user_meta.get(name, {}).get("shift", "morning")
                    users_map[name] = {
                        "name": name,
                        "role": user_meta.get(name, {}).get("role", "employee"),
                        "shift": shift_val,
                        "image_path": str(img),
                        "type": "file"
                    }

            # Multiple-image users (folder with center.png)
            for folder in [d for d in attendance_dir.iterdir() if d.is_dir()]:
                center_img = folder / "center.png"
                if center_img.exists():
                    shift_val = user_meta.get(folder.name, {}).get("shift", "morning")
                    users_map[folder.name] = {
                        "name": folder.name,
                        "role": user_meta.get(folder.name, {}).get("role", "employee"),
                        "shift": shift_val,
                        "image_path": str(center_img),
                        "type": "directory"
                    }

        registered_users = list(users_map.values())

    if not registered_users:
        st.info("Belum ada user.")
        return

    # CSS untuk styling
    st.markdown("""
    <style>
    .user-card {
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
        height: 100%;
        transition: transform 0.2s;
    }
    .user-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 6px 10px rgba(0,0,0,0.1);
    }
    .user-name {
        font-size: 1.2rem;
        font-weight: bold;
        margin: 0.5rem 0;
        color: #2C3E50;
        text-transform: capitalize;
    }
    .user-info {
        color: #666;
        font-size: 0.9rem;
        margin: 0.3rem 0;
    }
    .image-type {
        background-color: #e1f5fe;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8rem;
        color: #0277bd;
        margin-top: 0.5rem;
        display: inline-block;
    }
    .status-active {
        color: #4CAF50;
        font-weight: bold;
    }
    .user-images {
        display: flex;
        gap: 8px;
        margin-top: 10px;
    }
    .user-image-container {
        position: relative;
        width: 80px;
    }
    .image-label {
        font-size: 0.7rem;
        text-align: center;
        color: #555;
    }
    .delete-image-btn {
        position: absolute;
        top: 0;
        right: 0;
        background-color: rgba(255,59,48,0.8);
        color: white;
        border: none;
        border-radius: 50%;
        width: 20px;
        height: 20px;
        font-size: 10px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        opacity: 0.7;
    }
    .delete-image-btn:hover {
        opacity: 1;
    }
    </style>
    """, unsafe_allow_html=True)

    # Filter: tampilkan hanya users dengan multiple images (bukan file tunggal)
    multiple_image_users = [u for u in registered_users if u.get("type") != "file"]

    show_multiple_image_users(multiple_image_users)
    
    # Tombol registrasi
    st.markdown("---")
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("""
        <div style='text-align: center'>
            <h3>Tambah User Baru</h3>
            <p>Klik tombol di bawah untuk menambahkan user baru ke sistem.</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("➕ Registrasi User Baru", use_container_width=True):
            # Navigate to the in-app registration view controlled by app.py
            st.session_state['current_page'] = "Register New User"
            st.rerun()


def show_multiple_image_users(users):
    """Menampilkan users dengan images"""
    if not users:
        st.info("Tidak ada Image User")
        return
        
    st.subheader(f"Image Users ({len(users)})")
    
    # Buat grid layout
    cols = st.columns(4)
    
    for idx, user in enumerate(users):
        col = cols[idx % 4]
        with col:
            with st.container():
                # Card container
                st.markdown('<div class="user-card">', unsafe_allow_html=True)
                
                # Image (center image)
                st.image(user["image_path"], width=150)
                
                # User info
                st.markdown(f'<div class="user-name">{user["name"]}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="user-info">{user.get("role", "Employee").title()}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="user-info">Shift: {user.get("shift", "Not Set").title()}</div>', unsafe_allow_html=True)
                st.markdown('<div class="image-type">Images</div>', unsafe_allow_html=True)
                st.markdown('<div class="status-active">● Active</div>', unsafe_allow_html=True)
                
                # Get all images for this user
                user_images = get_user_images(user["name"])
                image_count = len(user_images)
                
                # Show number of images
                st.markdown(f'<div class="user-info">Images: {image_count}</div>', unsafe_allow_html=True)
                
                # Action buttons
                col1, col2 = st.columns(2)
                        
                with col1:
                    if st.button("🗑️ Delete", key=f"del_multi_{user['name']}_{idx}"):
                        # Store confirmation state in session_state
                        st.session_state[f"confirm_delete_{user['name']}"] = True
                        st.rerun()
                
                # Handle delete confirmation in session_state
                if st.session_state.get(f"confirm_delete_{user['name']}", False):
                    st.warning(f"Are you sure you want to delete user {user['name']}? This will remove all data.")
                    conf_col1, conf_col2 = st.columns(2)
                    with conf_col1:
                        if st.button("✅ Yes", key=f"confirm_yes_multi_{user['name']}_{idx}"):
                            try:
                                st.info(f"Deleting user {user['name']}...")
                                success, message = delete_user_completely(user['name'])
                                if success:
                                    st.success(f"✅ {message}")
                                    # Clear state and wait briefly before reloading
                                    st.session_state[f"confirm_delete_{user['name']}"] = False
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")
                            except Exception as e:
                                st.error(f"Error during deletion: {e}")
                                import traceback
                                st.code(traceback.format_exc())
                    with conf_col2:
                        if st.button("❌ No", key=f"confirm_no_multi_{user['name']}_{idx}"):
                            # Clear confirmation state
                            st.session_state[f"confirm_delete_{user['name']}"] = False
                            st.rerun()
                
                st.markdown('</div>', unsafe_allow_html=True)
    
    # Image editor modal
    if "editing_user" in st.session_state and "user_images" in st.session_state:
        with st.expander(f"Manage Images for {st.session_state.editing_user}", expanded=True):
            st.subheader(f"User Images: {st.session_state.editing_user}")
            
            # Display all images with delete buttons
            user = st.session_state.editing_user
            images = st.session_state.user_images
            
            # Organize by image type
            pose_images = [img for img in images if img["type"] in ["center", "left", "right"]]
            other_images = [img for img in images if img["type"] not in ["center", "left", "right"]]
            
            st.write("### Pose Images")
            pose_cols = st.columns(3)
            
            for i, img in enumerate(pose_images):
                with pose_cols[i % 3]:
                    st.image(img["path"], caption=img["type"], use_container_width=True)
                    
                    # Delete button for individual image
                    if st.button(f"🗑️ Delete {img['type']}", key=f"del_img_{user}_{img['type']}"):
                        st.warning(f"Are you sure you want to delete the {img['type']} image?")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("✅ Yes", key=f"confirm_del_img_{user}_{img['type']}"):
                                success, message = delete_user_image(user, img["type"])
                                if success:
                                    st.success(f"✅ {message}")
                                    time.sleep(1)
                                    # Refresh the image list
                                    st.session_state.user_images = get_user_images(user)
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")
                        with col2:
                            if st.button("❌ No", key=f"cancel_del_img_{user}_{img['type']}"):
                                st.rerun()
            
 


def _edit_user(user_name: str):
    """Edit nama, role, dan shift user"""
    st.subheader(f"✏️ Edit Data User: {user_name}")

    json_path = Path(__file__).parent.parent / "user_data.json"
    data = {}
    if json_path.exists():
        with open(json_path, "r") as f:
            data = json.load(f)

    current_role = data.get(user_name, {}).get("role", "employee")
    current_shift = data.get(user_name, {}).get("shift", "morning")
    
    new_name = st.text_input("Nama User", value=user_name)
    
    col1, col2 = st.columns(2)
    with col1:
        new_role = st.selectbox(
            "Role",
            ["employee", "supervisor", "manager"],
            index=["employee", "supervisor", "manager"].index(current_role) if current_role in ["employee", "supervisor", "manager"] else 0
        )
    with col2:
        new_shift = st.selectbox(
            "Shift",
            ["morning", "night"],
            index=["morning", "night"].index(current_shift) if current_shift in ["morning", "night"] else 0
        )

    if st.button("💾 Simpan"):
        try:
            # Rename folder/file sesuai nama baru
            attendance_dir = Path(__file__).parent.parent / "Attendance_data"
            old_folder = attendance_dir / user_name
            new_folder = attendance_dir / new_name
            old_file = attendance_dir / f"{user_name}.png"
            new_file = attendance_dir / f"{new_name}.png"

            if old_folder.exists() and old_folder.is_dir():
                old_folder.rename(new_folder)
            if old_file.exists():
                old_file.rename(new_file)

            # Update user_data.json
            if user_name in data:
                user_data = data[user_name]
                del data[user_name]
                data[new_name] = user_data
                data[new_name]["role"] = new_role
                data[new_name]["shift"] = new_shift
            else:
                data[new_name] = {"role": new_role, "shift": new_shift}

            with open(json_path, "w") as f:
                json.dump(data, f, indent=4)

            st.success(f"✅ User '{user_name}' berhasil diubah menjadi '{new_name}' (Shift: {new_shift.title()}).")
            st.rerun()
        except Exception as e:
            st.error(f"Gagal edit user: {e}")