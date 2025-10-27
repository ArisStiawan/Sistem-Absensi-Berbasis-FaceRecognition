import json
from pathlib import Path

__all__ = ['delete_user_completely', 'get_user_data']

def delete_user_completely(username: str) -> tuple[bool, str]:
    """
    Delete user data completely from the system, including:
    - API database entry
    - user_data.json entries
    - Image files
    - Image folders
    
    Returns:
        tuple[bool, str]: (success, message)
    """
    print(f"Starting delete for user: {username}")
    try:
        import requests
        import shutil
        from pathlib import Path
        import traceback
        
        # 1. Delete from API first using admin auth (optional)
        api_success = False
        try:
            print(f"Attempting to delete user {username} from API...")
            # First get admin token
            auth_response = requests.post(
                "http://localhost:8000/token",
                data={
                    "username": "admin",  # Admin credentials should be configured
                    "password": "admin123"
                },
                timeout=3  # Add timeout to avoid hanging
            )
            
            if auth_response.status_code != 200:
                print(f"Failed to authenticate with API: {auth_response.text}")
                # Continue anyway to clean up files
            else:
                token = auth_response.json()["access_token"]
                
                # Now delete with auth token
                headers = {"Authorization": f"Bearer {token}"}
                response = requests.delete(
                    f"http://localhost:8000/users/{username}",
                    headers=headers,
                    timeout=3  # Add timeout to avoid hanging
                )
                
                if response.status_code != 200:
                    print(f"API delete failed: {response.text}")
                    # Continue anyway to clean up files
                else:
                    print(f"Successfully deleted user {username} from API")
                    api_success = True
        except Exception as e:
            print(f"API Error (will continue with file deletion): {e}")
            # Continue anyway to clean up files

        # 2. Get the paths
        root_dir = Path(__file__).parent.parent.parent
        dashboard_dir = Path(__file__).parent.parent

        # 2. Get the paths
        root_dir = Path(__file__).parent.parent.parent  # Project root
        dashboard_dir = Path(__file__).parent.parent    # Dashboard dir
        
        print(f"Root dir: {root_dir}")
        print(f"Dashboard dir: {dashboard_dir}")

        # 3. Delete from user_data.json files
        json_files = [
            root_dir / "user_data.json",
            dashboard_dir / "user_data.json"
        ]
        
        json_deleted = False
        for json_path in json_files:
            if json_path.exists():
                try:
                    print(f"Checking JSON file: {json_path}")
                    with open(json_path, 'r') as f:
                        data = json.load(f)
                    if username in data:
                        print(f"Found user {username} in {json_path}, removing...")
                        del data[username]
                        with open(json_path, 'w') as f:
                            json.dump(data, f, indent=4)
                        print(f"Removed user from {json_path}")
                        json_deleted = True
                    else:
                        print(f"User {username} not found in {json_path}")
                except Exception as e:
                    print(f"Error updating {json_path}: {e}")
                    print(traceback.format_exc())
                    # Continue to clean up other files
                    
        # 4. Delete image files
        attendance_dirs = [
            root_dir / "Attendance_data",
            dashboard_dir / "Attendance_data"
        ]
        
        files_deleted = False
        for att_dir in attendance_dirs:
            if not att_dir.exists():
                print(f"Attendance directory doesn't exist: {att_dir}")
                continue
            
            print(f"Checking directory: {att_dir}")
                
            # Check for single image
            single_img = att_dir / f"{username}.png"
            if single_img.exists():
                try:
                    print(f"Found single image: {single_img}")
                    single_img.unlink()
                    print(f"Deleted single image: {single_img}")
                    files_deleted = True
                except Exception as e:
                    print(f"Error deleting image {single_img}: {e}")
                    print(traceback.format_exc())
                
            # Check for image folder
            user_folder = att_dir / username
            if user_folder.exists():
                try:
                    print(f"Found user folder: {user_folder}")
                    # First try to delete all files inside the folder
                    for img in user_folder.glob("*.png"):
                        try:
                            print(f"Deleting image: {img}")
                            img.unlink()
                            print(f"Deleted image: {img}")
                            files_deleted = True
                        except Exception as e:
                            print(f"Error deleting {img}: {e}")
                            print(traceback.format_exc())
                    
                    # Then try to remove the folder with shutil.rmtree
                    try:
                        shutil.rmtree(user_folder, ignore_errors=True)
                        print(f"Deleted folder: {user_folder}")
                    except Exception as e:
                        print(f"Error with rmtree for {user_folder}: {e}")
                        print(traceback.format_exc())
                        
                except Exception as e:
                    print(f"Error deleting folder {user_folder}: {e}")
                    print(traceback.format_exc())
            
            # Search for any other images that might contain the username
            try:
                print(f"Searching for other images containing '{username}'")
                for img in att_dir.glob(f"*{username}*.png"):
                    if img.exists() and img != single_img:  # Don't try to delete the same file twice
                        print(f"Found and deleting related image: {img}")
                        img.unlink()
                        print(f"Deleted related image: {img}")
                        files_deleted = True
            except Exception as e:
                print(f"Error searching for related images: {e}")
                print(traceback.format_exc())
        
        # Return success if anything was deleted (API, JSON, or files)          
        if api_success or json_deleted or files_deleted:
            return True, "User deleted successfully"
        else:
            return False, "No user data found to delete"
        
    except Exception as e:
        print(f"Unexpected error in delete_user_completely: {e}")
        print(traceback.format_exc())
        return False, f"Unexpected error: {e}"

def get_user_data():
    """Get user data from json file.
    Looks in both project root and dashboard folder and merges, preferring root entries."""
    data = {}
    candidates = [
        # Project root: .../Simslife_FaceRecognition/user_data.json
        Path(__file__).parent.parent.parent / "user_data.json",
        # Dashboard folder: .../dashboard/user_data.json
        Path(__file__).parent.parent / "user_data.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f) or {}
                    # Root entries should override dashboard ones by iteration order
                    data.update(loaded)
            except Exception as e:
                print(f"Error reading user data at {path}: {e}")
                continue
    return data