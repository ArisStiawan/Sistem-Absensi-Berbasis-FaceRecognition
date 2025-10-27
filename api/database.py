import pandas as pd
from datetime import datetime, time
import os
from pathlib import Path
import sqlite3
from typing import List, Optional

class AttendanceDB:
    def __init__(self):
        # Get the root directory (one level up from api folder)
        self.root_dir = Path(__file__).parent.parent
        self.attendance_path = self.root_dir / "Attendance_Entry"
        self.users_path = self.root_dir / "Attendance_data"
        self.db_path = self.root_dir / "attendance.db"
        self.init_db()
        
    def init_db(self):
        """Initialize database with required tables"""
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        
        # Create users table
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                full_name TEXT,
                hashed_password TEXT,
                role TEXT,
                shift TEXT,
                is_active BOOLEAN
            )
        ''')
        
        # Create attendance table with shift support
        c.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_name TEXT,
                date DATE,
                check_in TIME,
                check_out TIME,
                shift TEXT,
                status TEXT,
                device_id TEXT
            )
        ''')
        
        # Create devices table
        c.execute('''
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                name TEXT,
                location TEXT,
                last_active TIMESTAMP,
                status TEXT
            )
        ''')
        
        conn.commit()
        conn.close()

    def _safe_read_csv(self, csv_path):
        """Try reading a CSV robustly. Attempts multiple parsers and separators,
        skips bad lines, and normalizes columns to ['Name','Date','Time'].
        Returns a DataFrame or None on failure.
        """
        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            # Try a more permissive parser
            try:
                df = pd.read_csv(csv_path, engine='python', on_bad_lines='skip')
            except Exception:
                # Try common alternative separators
                for sep in [';', '\t']:
                    try:
                        df = pd.read_csv(csv_path, sep=sep, engine='python', on_bad_lines='skip')
                        break
                    except Exception:
                        df = None
                if df is None:
                    print(f"Error reading {csv_path}: {e}")
                    return None

        # Normalize column names: look for columns containing 'name','date','time'
        cols_lower = {c.lower(): c for c in df.columns}
        mapping = {}
        for key in ['name', 'date', 'time']:
            if key in cols_lower:
                mapping[cols_lower[key]] = key.capitalize()
            else:
                # try fuzzy match
                for c in df.columns:
                    if key in c.lower():
                        mapping[c] = key.capitalize()
                        break

        # Ensure required columns exist
        if not all(k in mapping.values() for k in ['Name', 'Date', 'Time']):
            print(f"CSV {csv_path} missing required columns. Found: {list(df.columns)}")
            return None

        df = df.rename(columns=mapping)
        return df
        
    def validate_shift_time(self, check_time: time, employee_name: str) -> tuple[str, str]:
        """Validate check time and return shift and status based on employee's registered shift"""
        morning_start = time(8, 0)
        morning_end = time(16, 0)
        night_start = time(16, 0)
        night_end = time(22, 0)
        
        # Get employee's registered shift
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        c.execute('SELECT shift FROM users WHERE username = ?', (employee_name,))
        result = c.fetchone()
        conn.close()
        
        registered_shift = result[0] if result else None
        
        if registered_shift == 'morning':
            if morning_start <= check_time < morning_end:
                if check_time > time(8, 15):  # 15 minutes tolerance
                    return "morning", "late"
                return "morning", "on_time"
            return "morning", "invalid"  # Wrong time for morning shift
        
        elif registered_shift == 'night':
            if night_start <= check_time < night_end:
                if check_time > time(16, 15):  # 15 minutes tolerance
                    return "night", "late"
                return "night", "on_time"
            return "night", "invalid"  # Wrong time for night shift
        
        else:
            # Fallback if shift not registered
            if morning_start <= check_time < morning_end:
                shift = "morning"
                if check_time > time(8, 15):
                    status = "late"
                else:
                    status = "on_time"
            elif night_start <= check_time < night_end:
                shift = "night"
                if check_time > time(16, 15):
                    status = "late"
                else:
                    status = "on_time"
            else:
                shift = "unknown"
                status = "invalid"
            return shift, status
        
    def mark_attendance(self, employee_name: str, device_id: str):
        """Mark attendance with shift validation"""
        now = datetime.now()
        current_time = now.time()
        
        shift, status = self.validate_shift_time(current_time)
        
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        
        # Check if already checked in today
        c.execute('''
            SELECT check_in, check_out FROM attendance 
            WHERE employee_name = ? AND date = ? AND shift = ?
        ''', (employee_name, now.date(), shift))
        
        existing = c.fetchone()
        
        if existing:
            if existing[1] is None:  # No check-out yet
                # Update check-out time
                c.execute('''
                    UPDATE attendance 
                    SET check_out = ? 
                    WHERE employee_name = ? AND date = ? AND shift = ?
                ''', (current_time, employee_name, now.date(), shift))
            else:
                status = "invalid"  # Already checked out
        else:
            # New check-in
            c.execute('''
                INSERT INTO attendance (employee_name, date, check_in, shift, status, device_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (employee_name, now.date(), current_time, shift, status, device_id))
        
        conn.commit()
        
        # Update device status
        self.update_device_status(device_id, "active")
        
        conn.close()
        
        return {
            "employee_name": employee_name,
            "date": now.date().isoformat(),
            "check_in": current_time.isoformat() if not existing else None,
            "check_out": current_time.isoformat() if existing else None,
            "shift": shift,
            "status": status,
            "device_id": device_id
        }
        
    def get_attendance_by_date(self, date=None):
        """Get attendance records for a specific date"""
        try:
            if date is None:
                date = datetime.now()
            elif isinstance(date, str):
                try:
                    date = datetime.strptime(date, '%Y-%m-%d')
                except ValueError:
                    try:
                        date = datetime.strptime(date, '%y_%m_%d')
                    except ValueError:
                        return []

            # First try SQLite database
            conn = sqlite3.connect(str(self.db_path))
            c = conn.cursor()
            
            c.execute('''
                SELECT employee_name, date, check_in, check_out, shift, status, device_id 
                FROM attendance WHERE date(date) = date(?)
            ''', (date.strftime('%Y-%m-%d'),))
            
            records = []
            for row in c.fetchall():
                records.append({
                    "name": row[0],
                    "date": str(row[1]),
                    "time": str(row[2]) if row[2] else None,
                    "shift": row[4] if row[4] else "unknown",
                    "status": row[5] if row[5] else "unknown",
                    "device_id": row[6] if row[6] else ""
                })
            
            conn.close()

            # If no records in SQLite, try CSV files
            if not records:
                date_str = date.strftime("%y_%m_%d")
                csv_path = self.attendance_path / f'Attendance_{date_str}.csv'
                if csv_path.exists():
                    df = self._safe_read_csv(csv_path)
                    if df is not None:
                        for _, row in df.iterrows():
                            records.append({
                                "employee_name": row["Name"],
                                "date": row["Date"],
                                "check_in": row["Time"],
                                "check_out": None,
                                "shift": self.determine_shift(row["Time"]),
                                "status": "legacy",
                                "device_id": "legacy_device"
                            })

            return records
        except Exception as e:
            print(f"Error in get_attendance_by_date: {e}")
            return []
            
    def determine_shift(self, time_str):
        """Determine shift based on time"""
        try:
            time_obj = datetime.strptime(time_str, "%H:%M:%S").time()
            if time(8, 0) <= time_obj < time(16, 0):
                return "morning"
            elif time(16, 0) <= time_obj < time(22, 0):
                return "night"
            return "unknown"
        except:
            return "unknown"
    
    def get_monthly_report(self, year: int, month: int) -> pd.DataFrame:
        """Get monthly attendance report"""
        conn = sqlite3.connect(str(self.db_path))
        
        query = '''
            SELECT 
                employee_name,
                shift,
                COUNT(*) as total_days,
                SUM(CASE WHEN status = 'on_time' THEN 1 ELSE 0 END) as on_time,
                SUM(CASE WHEN status = 'late' THEN 1 ELSE 0 END) as late,
                SUM(CASE WHEN status = 'invalid' THEN 1 ELSE 0 END) as invalid
            FROM attendance 
            WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?
            GROUP BY employee_name, shift
        '''
        
        df = pd.read_sql_query(query, conn, params=(str(year), f"{month:02d}"))
        conn.close()
        return df
    
    def update_device_status(self, device_id: str, status: str):
        """Update device status and last active time"""
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        
        now = datetime.now()
        
        c.execute('''
            INSERT INTO devices (device_id, status, last_active)
            VALUES (?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                status = ?,
                last_active = ?
        ''', (device_id, status, now, status, now))
        
        conn.commit()
        
        c.execute('SELECT * FROM devices WHERE device_id = ?', (device_id,))
        device = c.fetchone()
        
        conn.close()
        
        return {
            "device_id": device[0],
            "name": device[1] or "",
            "location": device[2] or "",
            "last_active": device[3],
            "status": device[4]
        }
    
    def get_all_attendance(self):
        """Get all attendance records"""
        try:
            records = []
            
            # Get from SQLite
            conn = sqlite3.connect(str(self.db_path))
            c = conn.cursor()
            c.execute('''
                SELECT employee_name, date, check_in, check_out, shift, status, device_id 
                FROM attendance 
                ORDER BY date DESC, check_in DESC
            ''')
            
            for row in c.fetchall():
                records.append({
                    "name": row[0],
                    "date": str(row[1]),
                    "time": str(row[2]) if row[2] else None,
                    "shift": row[4] if row[4] else "unknown",
                    "status": row[5] if row[5] else "unknown",
                    "device_id": row[6] if row[6] else ""
                })
            
            conn.close()
            
            # Get from CSV files if needed
            if not records and self.attendance_path.exists():
                for csv_file in self.attendance_path.glob("Attendance_*.csv"):
                    try:
                        df = self._safe_read_csv(csv_file)
                        if df is None:
                            print(f"Skipping malformed CSV: {csv_file}")
                            continue
                        for _, row in df.iterrows():
                            records.append({
                                "employee_name": row["Name"],
                                "date": row["Date"],
                                "check_in": row["Time"],
                                "check_out": None,
                                "shift": self.determine_shift(row["Time"]),
                                "status": "legacy",
                                "device_id": "legacy_device"
                            })
                    except Exception as e:
                        print(f"Error reading {csv_file}: {e}")
                        continue
            
            return records
        except Exception as e:
            print(f"Error in get_all_attendance: {e}")
            return []

    def get_all_devices(self):
        """Get list of all devices and their status"""
        try:
            # For now, return a default device
            return [{
                "device_id": "default",
                "name": "Default Camera",
                "location": "Main Entrance",
                "last_active": datetime.now().isoformat(),
                "status": "active"
            }]
        except Exception as e:
            print(f"Error in get_all_devices: {e}")
            return []

    def get_registered_users(self):
        """Get list of registered users"""
        try:
            users = []
            # Get users from Attendance_data directory
            if self.users_path.exists():
                print(f"Scanning directory: {self.users_path}")
                
                # Get users from directories and files
                for item in self.users_path.iterdir():
                    # Skip __pycache__ and other system directories
                    if item.name.startswith('__') or item.name.startswith('.'):
                        continue
                        
                    if item.is_dir():
                        # Check if directory contains required images
                        center_image = item / 'center.png'
                        if center_image.exists():
                            print(f"Adding directory user: {item.name}")
                            users.append({
                                "name": item.name,
                                "role": "Employee",
                                "shift": "Morning",
                                "image_path": str(center_image),
                                "type": "directory"
                            })
                    elif item.suffix.lower() == '.png':
                        print(f"Adding file user: {item.stem}")
                        users.append({
                            "name": item.stem,
                            "role": "Employee",
                            "shift": "Morning",
                            "image_path": str(item),
                            "type": "file"
                        })
                        
                return sorted(users, key=lambda x: x['name'].lower())
            return []
        except Exception as e:
            print(f"Error in get_registered_users: {e}")
            import traceback
            print(traceback.format_exc())
            return []

        if users:
            print(f"Total users found: {len(users)}")
            return users
        else:
            print(f"Directory not found: {self.users_path}")
            return []
            
    def get_users_from_database(self):
        """Get all users from the database"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            query = '''
                SELECT username, full_name, role, shift, is_active 
                FROM users
            '''
            df = pd.read_sql_query(query, conn)
            return df.to_dict(orient="records")
        except Exception as e:
            print(f"Error getting users from database: {e}")
            return []
        finally:
            if 'conn' in locals():
                conn.close()
                
    def delete_user(self, username: str):
        """
        Delete a user from the system:
        1. Remove from the database
        2. Delete image files
        
        Returns dict with status and message
        """
        try:
            # 1. Delete from database
            conn = sqlite3.connect(str(self.db_path))
            c = conn.cursor()
            
            # Delete from users table
            c.execute('DELETE FROM users WHERE username = ?', (username,))
            
            # Mark attendance records as inactive
            c.execute('''
                UPDATE attendance
                SET status = 'user_deleted'
                WHERE employee_name = ?
            ''', (username,))
            
            conn.commit()
            conn.close()
            
            # 2. Delete user images
            # This is actually handled by the client side function delete_user_completely
            # But let's make sure to clean up server-side files too
            
            # Check for single image
            single_img = self.users_path / f"{username}.png"
            if single_img.exists():
                try:
                    os.remove(single_img)
                    print(f"API: Deleted single image: {single_img}")
                except Exception as e:
                    print(f"API: Error deleting image {single_img}: {e}")
            
            # Check for image folder
            user_folder = self.users_path / username
            if user_folder.exists() and user_folder.is_dir():
                try:
                    import shutil
                    shutil.rmtree(user_folder)
                    print(f"API: Deleted folder: {user_folder}")
                except Exception as e:
                    print(f"API: Error deleting folder {user_folder}: {e}")
            
            return {"status": "success", "message": f"User '{username}' deleted successfully"}
        except Exception as e:
            print(f"API: Error in delete_user: {e}")
            import traceback
            print(traceback.format_exc())
            return {"status": "error", "message": str(e)}