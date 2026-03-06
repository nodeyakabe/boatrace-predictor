@echo off
cd /d "C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032"
set LOG=logs\2025_brute_force_main.log

echo [%date% %time%] 2025年brute-force収集 開始 >> %LOG%
echo [%date% %time%] 2025年brute-force収集 開始

REM === 1月 ===
echo [%date% %time%] 1月 収集開始... >> %LOG%
python scripts\data_collection\fetch_to_csv_parallel_improved.py --start 2025-01-01 --end 2025-01-31 --output data\csv\2025_補完_01 --brute-force --workers 8 >> %LOG% 2>&1
echo [%date% %time%] 1月 完了 >> %LOG%

REM === 2月 ===
echo [%date% %time%] 2月 収集開始... >> %LOG%
python scripts\data_collection\fetch_to_csv_parallel_improved.py --start 2025-02-01 --end 2025-02-28 --output data\csv\2025_補完_02 --brute-force --workers 8 >> %LOG% 2>&1
echo [%date% %time%] 2月 完了 >> %LOG%

REM === 3月 ===
echo [%date% %time%] 3月 収集開始... >> %LOG%
python scripts\data_collection\fetch_to_csv_parallel_improved.py --start 2025-03-01 --end 2025-03-31 --output data\csv\2025_補完_03 --brute-force --workers 8 >> %LOG% 2>&1
echo [%date% %time%] 3月 完了 >> %LOG%

REM === 4月 ===
echo [%date% %time%] 4月 収集開始... >> %LOG%
python scripts\data_collection\fetch_to_csv_parallel_improved.py --start 2025-04-01 --end 2025-04-30 --output data\csv\2025_補完_04 --brute-force --workers 8 >> %LOG% 2>&1
echo [%date% %time%] 4月 完了 >> %LOG%

REM === 5月 ===
echo [%date% %time%] 5月 収集開始... >> %LOG%
python scripts\data_collection\fetch_to_csv_parallel_improved.py --start 2025-05-01 --end 2025-05-31 --output data\csv\2025_補完_05 --brute-force --workers 8 >> %LOG% 2>&1
echo [%date% %time%] 5月 完了 >> %LOG%

REM === 6月 ===
echo [%date% %time%] 6月 収集開始... >> %LOG%
python scripts\data_collection\fetch_to_csv_parallel_improved.py --start 2025-06-01 --end 2025-06-30 --output data\csv\2025_補完_06 --brute-force --workers 8 >> %LOG% 2>&1
echo [%date% %time%] 6月 完了 >> %LOG%

REM === 7月 ===
echo [%date% %time%] 7月 収集開始... >> %LOG%
python scripts\data_collection\fetch_to_csv_parallel_improved.py --start 2025-07-01 --end 2025-07-31 --output data\csv\2025_補完_07 --brute-force --workers 8 >> %LOG% 2>&1
echo [%date% %time%] 7月 完了 >> %LOG%

REM === 8月 ===
echo [%date% %time%] 8月 収集開始... >> %LOG%
python scripts\data_collection\fetch_to_csv_parallel_improved.py --start 2025-08-01 --end 2025-08-31 --output data\csv\2025_補完_08 --brute-force --workers 8 >> %LOG% 2>&1
echo [%date% %time%] 8月 完了 >> %LOG%

REM === 9月 ===
echo [%date% %time%] 9月 収集開始... >> %LOG%
python scripts\data_collection\fetch_to_csv_parallel_improved.py --start 2025-09-01 --end 2025-09-30 --output data\csv\2025_補完_09 --brute-force --workers 8 >> %LOG% 2>&1
echo [%date% %time%] 9月 完了 >> %LOG%

REM === 10月 ===
echo [%date% %time%] 10月 収集開始... >> %LOG%
python scripts\data_collection\fetch_to_csv_parallel_improved.py --start 2025-10-01 --end 2025-10-31 --output data\csv\2025_補完_10 --brute-force --workers 8 >> %LOG% 2>&1
echo [%date% %time%] 10月 完了 >> %LOG%

REM === 11月 ===
echo [%date% %time%] 11月 収集開始... >> %LOG%
python scripts\data_collection\fetch_to_csv_parallel_improved.py --start 2025-11-01 --end 2025-11-30 --output data\csv\2025_補完_11 --brute-force --workers 8 >> %LOG% 2>&1
echo [%date% %time%] 11月 完了 >> %LOG%

REM === 12月 ===
echo [%date% %time%] 12月 収集開始... >> %LOG%
python scripts\data_collection\fetch_to_csv_parallel_improved.py --start 2025-12-01 --end 2025-12-31 --output data\csv\2025_補完_12 --brute-force --workers 8 >> %LOG% 2>&1
echo [%date% %time%] 12月 完了 >> %LOG%

REM === DBインポート ===
echo [%date% %time%] DBインポート開始... >> %LOG%
python scripts\data_collection\import_races_csv.py ^
  --dir data\csv\2025_補完_01 ^
  --dir data\csv\2025_補完_02 ^
  --dir data\csv\2025_補完_03 ^
  --dir data\csv\2025_補完_04 ^
  --dir data\csv\2025_補完_05 ^
  --dir data\csv\2025_補完_06 ^
  --dir data\csv\2025_補完_07 ^
  --dir data\csv\2025_補完_08 ^
  --dir data\csv\2025_補完_09 ^
  --dir data\csv\2025_補完_10 ^
  --dir data\csv\2025_補完_11 ^
  --dir data\csv\2025_補完_12 >> %LOG% 2>&1
echo [%date% %time%] DBインポート完了 >> %LOG%

echo [%date% %time%] 全処理完了 >> %LOG%
echo [%date% %time%] 全処理完了
pause
