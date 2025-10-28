# Attendance Data Display Fix

## Problem Summary
Data absensi yang sudah terekam belum terdisplay dengan baik pada:
1. **Menu Overview** - Data tidak muncul
2. **Daily Statistics** - Data tidak muncul atau error
3. **Riwayat Absensi** - Data tidak muncul atau tidak lengkap

### Root Cause
Terdapat **mixed CSV format**:
- **Old format** (sebelumnya): `Name, Time, Date` (3 kolom)
- **New format** (setelah fix shift): `Name, Time, Date, Shift, Status` (5 kolom)
- File attendance CSV mengandung **campuran kedua format** pada baris yang berbeda

Contoh `Attendance_25_10_27.csv`:
```
Name,Time,Date
hu,08:40:59,2025-10-27        <- 3 kolom (format lama)
jj,08:50:05,2025-10-27,morning,on_time <- 5 kolom (format baru)
jj,08:58:41,2025-10-27,morning,on_time <- 5 kolom (format baru)
```

Masalah yang terjadi:
- Pandas default C engine: **Error tokenizing data** (expected 3 fields, saw 5)
- Pandas python engine dengan `on_bad_lines='skip'`: **Skip baris dengan 5 kolom** (data hilang)
- Dashboard functions: Mencari kolom yang tidak konsisten

---

## Solution Implemented

### 1. **Enhanced `safe_read_attendance_csv()` in `pages/attendance.py`**

**Sebelumnya:** Menggunakan `on_bad_lines='skip'` yang membuang data
**Sesudahnya:** Prioritas adalah **line-by-line repair** untuk preserve ALL rows

**Strategi:**
1. **Strategy A (Prioritas Utama):** Line-by-line repair untuk mixed format CSV
   - Baca semua baris secara manual
   - Deteksi max column count di seluruh file
   - Pad semua baris ke max column count dengan empty strings
   - Tambahkan nama kolom yang proper: Name, Time, Date, Shift, Status
   - Result: **Semua 12 baris terekam** (sebelumnya hanya 9)

2. **Strategy B:** Python engine dengan `on_bad_lines='warn'` (keep lines)
3. **Strategy C:** Default C engine untuk file clean
4. **Strategy D:** Try different separators
5. **Strategy E:** Raw csv.reader fallback

### 2. **Updated `get_today_attendance()` in `dashboard/app.py`**

**Enhancements:**
- Handle mixed column formats (old 3-col, new 5-col)
- Normalize column names: `Name → employee_name`, `Time → check_in_time`, etc
- Prioritize recorded shift/status from CSV jika tersedia
- Fallback ke user_data.json untuk assigned shift jika CSV tidak punya
- Handle missing columns gracefully

**Flow:**
```
1. Read CSV dengan safe_read_attendance_csv() → mixed format OK
2. Normalize column names ke standard format
3. Untuk setiap row:
   - Get assigned_shift dari user_data.json
   - Jika tidak ada, gunakan recorded_shift dari CSV (backward compatible)
   - Get recorded_status dari CSV jika tersedia
   - Jika tidak ada, hitung berdasarkan time dan shift
4. Return DataFrame dengan konsisten: 
   employee_name, check_in, check_out, assigned_shift, actual_shift, status
```

### 3. **Updated Attendance History Display in `pages/attendance.py`**

**Enhancements:**
- Normalize column names untuk handle both old dan new format
- Flexible column mapping dengan fallback
- Format Time column untuk consistency
- Display hanya available columns (tidak error jika kolom missing)
- Show Shift/Status metrics hanya jika kolom tersedia
- Better error logging

**Display logic:**
```
1. Read file dengan safe_read_attendance_csv()
2. Normalize column names
3. Map ke display names: Name→Nama, Time→Waktu, Date→Tanggal, etc
4. Display dataframe dengan available columns saja
5. Show metrics berdasarkan available data (Shift count atau Status count)
```

---

## Results

### Before Fix
```
Attendance_25_10_27.csv (Sample):
✗ Reading dengan default pandas: ParserError
✗ Reading dengan python engine: Hanya 9 dari 12 baris (3 baris skip)
✗ Dashboard display: Empty atau error
```

### After Fix
```
Attendance_25_10_27.csv (Sample):
✓ Reading: Semua 12 baris berhasil dibaca
✓ Columns: Name, Time, Date, Shift, Status
✓ Display: Semua data terlihat dengan baik
✓ Metrics: Shift pagi = 3, Status on_time = 2, late = 1
```

### Test Result
```
Testing updated safe_read_attendance_csv with proper column names...
✓ Read successful
✓ Columns: ['Name', 'Time', 'Date', 'Shift', 'Status']
✓ Rows: 12 (increased from 9)
✓ Sample data: Semua baris visible, termasuk rows dengan Shift/Status
```

---

## Files Modified

1. **`dashboard/pages/attendance.py`**
   - Updated `safe_read_attendance_csv()` - line-by-line repair strategy
   - Updated attendance history display section - flexible column mapping

2. **`dashboard/app.py`**
   - Updated `get_today_attendance()` - handle mixed formats

---

## Verification Checklist

- [x] Old CSV format (3 columns) dibaca dengan baik
- [x] New CSV format (5 columns) dibaca dengan baik
- [x] Mixed format CSV dibaca dengan all rows preserved
- [x] Overview page data displays correctly
- [x] Daily Statistics page data displays correctly
- [x] Riwayat Absensi page data displays correctly
- [x] Shift metrics ditampilkan jika ada kolom Shift
- [x] Status metrics ditampilkan jika ada kolom Status
- [x] No missing data rows (12/12 rows successfully read)

---

## Migration Notes

**Tidak perlu aksi manual:**
- ✓ Old CSV files masih support (backward compatible)
- ✓ New CSV files langsung work
- ✓ Mixed CSV files sekarang work (sebelumnya problem)

Attendance data yang sebelumnya "hilang" akan kembali muncul di dashboard!
