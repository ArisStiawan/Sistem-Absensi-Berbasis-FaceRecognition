from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from typing import List
from datetime import datetime, timedelta
import uvicorn
import logging

# Import API submodules. Use relative imports when the package is installed/imported
# normally (e.g. run from project root as `uvicorn api.main:app`). If the module
# is executed from inside the `api/` folder (for example `uvicorn main:app`),
# relative imports raise "attempted relative import with no known parent package".
# In that case catch the error, add the project root to sys.path and import the
# modules using absolute package names so both invocation styles work.
try:
    from .database import AttendanceDB
    from .models import User, UserInDB, Token, TokenData, AttendanceRecord, DeviceInfo
    from .auth import authenticate_user, create_access_token, get_current_active_user
except Exception:
    import sys
    import os
    # Insert the project root (parent of this api folder) into sys.path so
    # absolute imports like `import api.database` will succeed when running
    # from inside the api directory.
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from api.database import AttendanceDB
    from api.models import User, UserInDB, Token, TokenData, AttendanceRecord, DeviceInfo
    from api.auth import authenticate_user, create_access_token, get_current_active_user

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Face Recognition Attendance API",
             description="API for managing attendance data",
             version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = AttendanceDB()

@app.get("/")
async def root():
    return {
        "message": "Face Recognition Attendance API",
        "endpoints": [
            {"path": "/attendance/today", "description": "Get today's attendance"},
            {"path": "/attendance/all", "description": "Get all attendance records"},
            {"path": "/users/", "description": "Get registered users"},
            {"path": "/devices/", "description": "Get connected devices"}
        ]
    }

@app.get("/attendance/today")
async def get_today_attendance():
    try:
        logger.info("Fetching today's attendance")
        data = db.get_attendance_by_date(datetime.now())
        return {"data": data}
    except Exception as e:
        logger.error(f"Error getting today's attendance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/attendance/all")
async def get_all_attendance():
    try:
        logger.info("Fetching all attendance records")
        data = db.get_all_attendance()
        return {"data": data}
    except Exception as e:
        logger.error(f"Error getting all attendance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users")
async def get_users():
    """Get all registered users from images directory"""
    try:
        logger.info("Fetching registered users from images")
        data = db.get_registered_users()
        logger.info(f"Found {len(data)} registered users")
        return {"data": data}
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/database")
async def get_database_users():
    """Get all users from database"""
    try:
        logger.info("Fetching users from database")
        data = db.get_users_from_database()
        logger.info(f"Found {len(data)} database users")
        return {"data": data}
    except Exception as e:
        logger.error(f"Error getting database users: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/devices/")
async def get_devices():
    try:
        logger.info("Fetching devices")
        data = db.get_all_devices()
        return {"data": data}
    except Exception as e:
        logger.error(f"Error getting devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/attendance/today")
async def get_today_attendance():
    try:
        logger.info("Fetching today's attendance")
        today = datetime.now().strftime("%y_%m_%d")
        df = db.get_attendance_by_date(today)
        result = df.to_dict(orient="records")
        logger.info(f"Found {len(result)} attendance records for today")
        return result
    except Exception as e:
        logger.error(f"Error getting today's attendance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/attendance/all")
async def get_all_attendance():
    try:
        logger.info("Fetching all attendance records")
        df = db.get_all_attendance()
        result = df.to_dict(orient="records")
        logger.info(f"Found {len(result)} total attendance records")
        return result
    except Exception as e:
        logger.error(f"Error getting all attendance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/attendance")
async def mark_attendance(data: dict):
    """Mark attendance from face recognition engine
    
    Request body:
    {
        "name": "employee_name",
        "time": "HH:MM:SS",
        "date": "YYYY-MM-DD", 
        "shift": "morning or night",
        "status": "on_time or off_shift"
    }
    """
    try:
        name = data.get("name")
        time_str = data.get("time")
        date_str = data.get("date")
        shift = data.get("shift")
        status = data.get("status")
        
        logger.info(f"Marking attendance: {name} at {time_str} on {date_str} (Shift: {shift}, Status: {status})")
        # Just log the attendance marking - the main recording is done in CSV
        # This endpoint is for API consistency and potential future database integration
        return {
            "success": True,
            "message": f"Attendance marked for {name}",
            "data": {
                "name": name,
                "time": time_str,
                "date": date_str,
                "shift": shift,
                "status": status
            }
        }
    except Exception as e:
        logger.error(f"Error marking attendance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# User management endpoints (admin only)
@app.post("/users/add", response_model=User)
async def create_user(user: User, current_user: User = Depends(get_current_active_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        return db.create_user(user)
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/users/{username}", response_model=User)
async def update_user(
    username: str,
    user_update: User,
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        return db.update_user(username, user_update)
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/users/{username}")
async def delete_user(
    username: str,
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        return db.delete_user(username)
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Device management endpoints
@app.post("/devices/status", response_model=DeviceInfo)
async def update_device_status(
    device_id: str,
    status: str,
    current_user: User = Depends(get_current_active_user)
):
    try:
        return db.update_device_status(device_id, status)
    except Exception as e:
        logger.error(f"Error updating device status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/devices/", response_model=List[DeviceInfo])
async def get_devices(current_user: User = Depends(get_current_active_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        return db.get_all_devices()
    except Exception as e:
        logger.error(f"Error getting devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)