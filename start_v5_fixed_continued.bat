@echo off
REM V5修正版継続実行
REM 2023-11-01 ~ 2025-10-31 (731日)

echo ========================================
echo V5修正版 データ収集継続
echo 対象期間: 2023-11-01 ～ 2025-10-31
echo ========================================
echo.
echo [注意] 風向修正版を使用
echo.

set VENV_PATH=venv\Scripts\python.exe
%VENV_PATH% -u fetch_parallel_v5.py --start 2023-11-01 --end 2025-10-31 --workers 10 > v5_fixed_continued.log 2>&1

echo.
echo ========================================
echo V5修正版 完了
echo ログ: v5_fixed_continued.log
echo ========================================
