import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import AttendanceDB
from datetime import datetime, time

def test_morning_shift():
    db = AttendanceDB()
    # Test on time (morning)
    assert db.get_attendance_status(time(7, 0), "morning") == "on time"
    assert db.get_attendance_status(time(8, 15), "morning") == "on time"
    
    # Test late (morning)
    assert db.get_attendance_status(time(8, 16), "morning") == "late"
    assert db.get_attendance_status(time(9, 0), "morning") == "late"
    
    # Test off shift (morning)
    assert db.get_attendance_status(time(5, 59), "morning") == "off shift"
    assert db.get_attendance_status(time(16, 1), "morning") == "off shift"

def test_night_shift():
    db = AttendanceDB()
    # Test on time (night)
    assert db.get_attendance_status(time(15, 30), "night") == "on time"
    assert db.get_attendance_status(time(16, 15), "night") == "on time"
    
    # Test late (night)
    assert db.get_attendance_status(time(16, 16), "night") == "late"
    assert db.get_attendance_status(time(17, 0), "night") == "late"
    
    # Test off shift (night)
    assert db.get_attendance_status(time(14, 59), "night") == "off shift"
    assert db.get_attendance_status(time(22, 1), "night") == "off shift"

if __name__ == "__main__":
    test_morning_shift()
    test_night_shift()
    print("All tests passed!")