@echo off
REM V6実行バッチファイル（修正版 - 2年間）
REM 展示タイム修正 + 風向修正版
REM 対象期間: 2023-11-01 ～ 2025-10-31 (2年間、731日)

echo ========================================
echo V6 データ収集（修正版 - 2年間）
echo 対象期間: 2023-11-01 ～ 2025-10-31
echo 総日数: 731日 (2年間)
echo ========================================
echo.
echo [修正内容]
echo  1. 展示タイム: INSERT OR REPLACE → INSERT ... ON CONFLICT ... DO UPDATE
echo  2. 風向: 子要素の^<p^>タグから取得
echo.
echo ========================================

set VENV_PATH=venv\Scripts\python.exe
%VENV_PATH% -u fetch_parallel_v6.py --start 2023-11-01 --end 2025-10-31 --workers 10
