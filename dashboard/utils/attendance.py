from datetime import datetime, time
from typing import Tuple

def determine_attendance_status(checkin_time: datetime, assigned_shift: str) -> str:
    """
    Tentukan status absensi berdasarkan assigned shift dan waktu check-in.
    
    Args:
        checkin_time: datetime object saat check-in
        assigned_shift: "morning" atau "night" - shift yang terdaftar user
    
    Returns:
        str: "on_time" atau "late"
    
    Logic untuk Morning Shift (08:00-17:00):
        - on_time: check-in < 08:00
        - late: check-in >= 08:00
        
    Logic untuk Night Shift (17:00-22:00):
        - on_time: check-in < 17:00 (termasuk 16:00-16:59 early arrival)
        - late: check-in >= 17:00
    """
    hour = checkin_time.hour
    
    if assigned_shift == "morning":
        # Morning shift on_time hanya jika < 08:00
        if hour < 8:
            return "on_time"
        else:
            return "late"
    
    elif assigned_shift == "night":
        # Night shift on_time jika < 17:00 (termasuk early arrival 16:00-16:59)
        if hour < 17:
            return "on_time"
        else:
            return "late"
    
    # Default fallback
    return "late"


def get_final_status(user_assigned_shift: str, checkin_time: datetime) -> str:
    """
    Dapatkan status final absensi dengan mempertimbangkan assigned shift.
    
    Args:
        user_assigned_shift: Shift yang terdaftar user ("morning" atau "night")
        checkin_time: datetime saat check-in
    
    Returns:
        str: "on_time", "late", atau "off_shift"
    
    Logic:
        Morning user (assigned_shift="morning"):
            - < 08:00 → on_time
            - 08:00-16:59 → late
            - >= 17:00 → off_shift
        
        Night user (assigned_shift="night"):
            - < 16:00 → off_shift (pagi)
            - 16:00-16:59 → on_time (early arrival)
            - 17:00-21:59 → late
            - >= 22:00 → off_shift
    """
    hour = checkin_time.hour
    
    if user_assigned_shift == "morning":
        # Morning shift user
        if hour < 8:
            return "on_time"
        elif hour < 17:
            return "late"
        else:
            return "off_shift"
    
    elif user_assigned_shift == "night":
        # Night shift user
        if hour < 16:
            return "off_shift"
        elif hour < 17:
            return "on_time"
        elif hour < 22:
            return "late"
        else:
            return "off_shift"
    
    return "off_shift"