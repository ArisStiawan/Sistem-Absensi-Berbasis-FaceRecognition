import datetime
import requests
import os
from pathlib import Path

class AttendanceTracker:
    def __init__(self):
        self.cooldown_period = 300  # 5 minutes in seconds
        self.marked_shifts = {}  # Store marked attendance by shift
        self.last_detection = {}  # Store last detection times
        
        # Create Attendance_Entry directory if it doesn't exist
        self.attendance_dir = Path(__file__).parent.parent / "Attendance_Entry"
        os.makedirs(self.attendance_dir, exist_ok=True)

    def _get_current_shift(self):
        """Determine current shift based on time"""
        current_hour = datetime.datetime.now().hour
        
        if 8 <= current_hour < 17:
            return 'morning'
        elif 16 <= current_hour < 22:  # 4 PM to 10 PM
            return 'night'
        return None  # Outside shift hours

    def can_mark_attendance(self, name):
        """Check if attendance can be marked based on cooldown and shift"""
        current_time = datetime.datetime.now()
        current_shift = self._get_current_shift()
        
        if not current_shift:
            return False
        
        # Check if already marked for current shift
        if name in self.marked_shifts and current_shift in self.marked_shifts[name]:
            return False
        
        # Check cooldown period
        if name in self.last_detection:
            time_diff = (current_time - self.last_detection[name]).total_seconds()
            if time_diff < self.cooldown_period:
                return False
        
        return True

    def mark_attendance(self, name):
        """Mark attendance for a person"""
        if not self.can_mark_attendance(name):
            return False
            
        current_time = datetime.datetime.now()
        current_shift = self._get_current_shift()
        
        if not current_shift:
            return False
            
        try:
            # Update attendance file
            date_str = current_time.strftime("%y_%m_%d")
            file_path = self.attendance_dir / f"Attendance_{date_str}.csv"
            
            # Create file with headers if it doesn't exist
            if not file_path.exists():
                with open(file_path, "w", newline='') as f:
                    f.write("Name,Time,Date\n")
            
            # Append attendance
            with open(file_path, "a", newline='') as f:
                time_str = current_time.strftime("%H:%M:%S")
                date_str = current_time.strftime("%Y-%m-%d")
                f.write(f"{name},{time_str},{date_str}\n")
            
            # Update tracking
            self.last_detection[name] = current_time
            if name not in self.marked_shifts:
                self.marked_shifts[name] = set()
            self.marked_shifts[name].add(current_shift)
            
            # Try to send to API
            try:
                requests.post(
                    "http://localhost:8000/attendance/mark",
                    json={"employee_name": name, "check_in": current_time.isoformat()}
                )
            except:
                # Continue even if API call fails
                pass
                
            return True
            
        except Exception as e:
            print(f"Error marking attendance: {e}")
            return False