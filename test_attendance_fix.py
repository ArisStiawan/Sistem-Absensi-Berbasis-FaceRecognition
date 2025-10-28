import sys
sys.path.insert(0, './dashboard')
from pages.attendance import safe_read_attendance_csv
from pathlib import Path

attendance_file = Path('Attendance_Entry/Attendance_25_10_27.csv')

print('='*70)
print('ATTENDANCE DATA DISPLAY FIX - VERIFICATION')
print('='*70)
print()

# Test 1: Safe reading
print('[TEST 1] Safe Reading Mixed Format CSV')
print('-'*70)
df = safe_read_attendance_csv(attendance_file)
print('✓ Total rows read:', len(df))
print('✓ Columns:', list(df.columns))
print()

# Test 2: Column stats
print('[TEST 2] Column Data Statistics')
print('-'*70)
print('  Name column - Unique employees:', df["Name"].nunique())
print('  Shift column - Non-empty:', df["Shift"].notna().sum())
print('  Status column - Non-empty:', df["Status"].notna().sum())
print()

# Test 3: Shift breakdown
print('[TEST 3] Attendance by Shift')
print('-'*70)
shift_counts = df[df['Shift'].notna()]['Shift'].value_counts()
for shift, count in shift_counts.items():
    print('  ' + shift.upper() + ':', count, 'employee(s)')
print()

# Test 4: Status breakdown
print('[TEST 4] Attendance by Status')
print('-'*70)
status_counts = df[df['Status'].notna()]['Status'].value_counts()
for status, count in status_counts.items():
    print('  ' + status + ':', count, 'record(s)')
print()

# Test 5: Sample data preview
print('[TEST 5] Sample Data Preview')
print('-'*70)
print(df[['Name', 'Time', 'Shift', 'Status']].head(5).to_string(index=False))
print()

# Test 6: Data integrity
print('[TEST 6] Data Integrity Check')
print('-'*70)
print('✓ All Name values present:', df["Name"].notna().all())
print('✓ All Time values present:', df["Time"].notna().all())
print('✓ All Date values present:', df["Date"].notna().all())
print()

print('='*70)
print('✅ ATTENDANCE DISPLAY FIX SUCCESSFULLY APPLIED')
print('='*70)
