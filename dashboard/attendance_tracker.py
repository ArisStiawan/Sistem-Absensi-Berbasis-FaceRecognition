import datetime
import requests
import os
import json
from pathlib import Path

class AttendanceTracker:
    def __init__(self):
        self.cooldown_period = 300  # 5 minutes in seconds
        self.marked_shifts = {}  # Store marked attendance by shift
        self.last_detection = {}  # Store last detection times
        
        # Create Attendance_Entry directory if it doesn't exist
        self.attendance_dir = Path(__file__).parent.parent / "Attendance_Entry"
        os.makedirs(self.attendance_dir, exist_ok=True)
        
        # Load user data with assigned shifts
        self.user_shifts = self._load_user_shifts()

    def _load_user_shifts(self):
        """Load user shift assignments from user_data.json"""
        user_shifts = {}
        candidates = [
            Path(__file__).parent.parent / "user_data.json",
            Path(__file__).parent / "user_data.json",
        ]
        for path in candidates:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f) or {}
                        for user_name, user_info in data.items():
                            if isinstance(user_info, dict) and 'shift' in user_info:
                                user_shifts[user_name] = user_info['shift']
                except Exception as e:
                    print(f"Error loading user shifts from {path}: {e}")
        return user_shifts

    def get_user_assigned_shift(self, name):
        """Get the user's assigned shift from user_data.json"""
        return self.user_shifts.get(name, 'morning')  # Default to morning if not found

    def _get_current_shift(self):
        """Determine current shift based on time (for reference only)"""
        current_hour = datetime.datetime.now().hour
        
        if 8 <= current_hour < 17:
            return 'morning'
        elif 16 <= current_hour < 22:  # 4 PM to 10 PM
            return 'night'
        return None  # Outside shift hours

    def can_mark_attendance(self, name):
        """Check if attendance can be marked based on cooldown and shift"""
        current_time = datetime.datetime.now()
        
        # Get user's ASSIGNED shift, not the current time-based shift
        assigned_shift = self.get_user_assigned_shift(name)
        
        if not assigned_shift:
            return False
        
        # Check if already marked for assigned shift (not current time-based shift)
        if name in self.marked_shifts and assigned_shift in self.marked_shifts[name]:
            return False
        
        # Check cooldown period
        if name in self.last_detection:
            time_diff = (current_time - self.last_detection[name]).total_seconds()
            if time_diff < self.cooldown_period:
                return False
        
        return True

    def mark_attendance(self, name):
        """Mark attendance for a person using their assigned shift"""
        if not self.can_mark_attendance(name):
            return False
            
        current_time = datetime.datetime.now()
        # Use assigned shift, not time-based shift
        assigned_shift = self.get_user_assigned_shift(name)
        
        if not assigned_shift:
            return False
            
        try:
            # Update attendance file
            date_str = current_time.strftime("%y_%m_%d")
            file_path = self.attendance_dir / f"Attendance_{date_str}.csv"
            
            # Create file with headers if it doesn't exist
            if not file_path.exists():
                with open(file_path, "w", newline='') as f:
                    f.write("Name,Time,Date,Shift,Status\n")
            
            # Append attendance with ASSIGNED shift
            with open(file_path, "a", newline='') as f:
                time_str = current_time.strftime("%H:%M:%S")
                date_str = current_time.strftime("%Y-%m-%d")
                status = "on_time"  # Default status
                f.write(f"{name},{time_str},{date_str},{assigned_shift},{status}\n")
            
            # Update tracking with ASSIGNED shift
            self.last_detection[name] = current_time
            if name not in self.marked_shifts:
                self.marked_shifts[name] = set()
            self.marked_shifts[name].add(assigned_shift)
            
            # Try to send to API
            try:
                requests.post(
                    "http://localhost:8000/attendance/mark",
                    json={"employee_name": name, "check_in": current_time.isoformat(), "shift": assigned_shift}
                )
            except:
                # Continue even if API call fails
                pass
                
            return True
            
        except Exception as e:
            print(f"Error marking attendance: {e}")
            return False
