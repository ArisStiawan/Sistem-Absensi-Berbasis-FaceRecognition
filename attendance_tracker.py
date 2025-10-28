import time
from datetime import datetime
import requests
import csv
import os
from pathlib import Path

class AttendanceTracker:
    def __init__(self):
        self.last_attendance = {}  # Store last attendance time for each person
        self.marked_shifts = {}  # Track which shifts have been marked for each person today
        self.cooldown = 3600  # 1 hour in seconds
        self._user_data_cache = None
        self._user_data_mtime = 0.0
        
        # Define shift times (24-hour format)
        self.morning_shift = {
            'start': '08:00',
            'end': '17:00'
        }
        self.night_shift = {
            'start': '16:00',
            'end': '22:00'
        }
    
    def _get_current_shift(self):
        """Determine which shift the current time falls into"""
        current_time = datetime.now().strftime('%H:%M')
        
        if self._is_time_between(current_time, self.morning_shift['start'], self.morning_shift['end']):
            return 'morning'
        elif self._is_time_between(current_time, self.night_shift['start'], self.night_shift['end']):
            return 'night'
        return None
    
    def _is_time_between(self, current, start, end):
        """Check if current time is between start and end times"""
        current = datetime.strptime(current, '%H:%M').time()
        start = datetime.strptime(start, '%H:%M').time()
        end = datetime.strptime(end, '%H:%M').time()
        
        return start <= current <= end

    def _load_user_data(self):
        """Load user_data.json from project root or dashboard directory with basic caching."""
        try:
            # Determine probable locations
            root_path = Path(__file__).parent / 'user_data.json'
            dashboard_path = Path(__file__).parent / 'dashboard' / 'user_data.json'

            # Prefer root file if exists
            candidate = None
            if root_path.exists():
                candidate = root_path
            elif dashboard_path.exists():
                candidate = dashboard_path

            if candidate is None:
                self._user_data_cache = {}
                self._user_data_mtime = 0.0
                return

            mtime = candidate.stat().st_mtime
            if self._user_data_cache is None or mtime != self._user_data_mtime:
                with open(candidate, 'r', encoding='utf-8') as f:
                    import json
                    self._user_data_cache = json.load(f)
                    self._user_data_mtime = mtime
        except Exception:
            # On any error, fallback to empty map
            self._user_data_cache = {}
            self._user_data_mtime = 0.0

    def _get_assigned_shift(self, name: str):
        """Return the assigned shift for a user ('morning'/'night') if available."""
        self._load_user_data()
        data = self._user_data_cache or {}
        meta = data.get(name) or data.get(name.lower()) or data.get(name.title())
        if not meta:
            return None
        shift = meta.get('shift')
        if isinstance(shift, str):
            s = shift.strip().lower()
            if s in ('morning', 'night'):
                return s
        return None

    def get_user_assigned_shift(self, name: str):
        """Public method to get the user's assigned shift from user_data.json"""
        assigned = self._get_assigned_shift(name)
        return assigned if assigned else 'morning'  # Default to morning if not assigned

    def has_valid_shift(self, name: str) -> bool:
        """Check if the user's assigned shift matches the current shift window."""
        current_shift = self._get_current_shift()
        if not current_shift:
            return False
        assigned = self._get_assigned_shift(name)
        if assigned is None:
            # If no assignment, treat as valid for now
            return True
        return assigned == current_shift
    
    def _reset_daily_records(self, name):
        """Reset daily records if it's a new day"""
        current_date = datetime.now().date()
        if name in self.marked_shifts:
            last_date = datetime.fromtimestamp(self.last_attendance.get(name, 0)).date()
            if current_date != last_date:
                self.marked_shifts[name] = set()
    
    def can_mark_attendance(self, name):
        """Check if attendance can be marked based on assigned shift and cooldown"""
        # Get user's ASSIGNED shift, not the current time-based shift
        assigned_shift = self.get_user_assigned_shift(name)
        
        # If user has no assigned shift, cannot mark
        if not assigned_shift:
            return False
        
        # Reset records if it's a new day
        self._reset_daily_records(name)
        
        # Initialize marked shifts for new names
        if name not in self.marked_shifts:
            self.marked_shifts[name] = set()
        
        # Check if already marked for this assigned shift today
        if assigned_shift in self.marked_shifts[name]:
            return False
            
        # Check cooldown period (one detection per hour)
        current_time = time.time()
        if name in self.last_attendance:
            time_diff = current_time - self.last_attendance[name]
            if time_diff < self.cooldown:
                # Calculate remaining cooldown time in minutes
                remaining_minutes = int((self.cooldown - time_diff) / 60)
                print(f"Cooldown active for {name}. Please wait {remaining_minutes} minutes before next detection.")
                return False
        
        return True
        
    def mark_attendance(self, name):
        """Mark attendance using the user's assigned shift"""
        if not self.can_mark_attendance(name):
            return False
            
        current_time = time.time()
        self.last_attendance[name] = current_time
        
        # Get assigned shift and mark it as recorded
        assigned_shift = self.get_user_assigned_shift(name)
        if assigned_shift:
            self.marked_shifts.setdefault(name, set()).add(assigned_shift)
        
        # Get current date and time
        now = datetime.now()
        time_str = now.strftime('%H:%M:%S')
        date_str = now.strftime('%Y-%m-%d')
        
        # Ensure the directory exists
        os.makedirs("Attendance_Entry", exist_ok=True)
        
        # Create the CSV file for today
        current_date = now.strftime("%y_%m_%d")
        attendance_file = f'Attendance_Entry/Attendance_{current_date}.csv'
        
        try:
            # Create file with headers if it doesn't exist
            if not os.path.exists(attendance_file):
                with open(attendance_file, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Name", "Time", "Date", "Shift", "Status"])
            
            # Record the attendance with assigned shift
            with open(attendance_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([name, time_str, date_str, assigned_shift, "on_time"])
            
            # Notify the API
            try:
                response = requests.post(
                    "http://localhost:8000/attendance",
                    json={
                        "name": name,
                        "time": time_str,
                        "date": date_str,
                        "shift": assigned_shift
                    }
                )
                if response.status_code == 200:
                    print(f"Attendance marked for {name} at {time_str} on {assigned_shift} shift")
            except requests.RequestException:
                # Silently continue if API is not available
                pass
            
            return True
            
        except Exception as e:
            print(f"Error marking attendance: {e}")
            return False