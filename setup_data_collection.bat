@echo off
echo ================================================
echo 2PC体制セットアップ - このPC（データ収集専用）
echo ================================================
echo.

echo [1/3] 不要なStreamlitプロセスを停止...
taskkill /F /IM streamlit.exe 2>nul
if %errorlevel% EQU 0 (
    echo     OK: Streamlitを停止しました
) else (
    echo     SKIP: Streamlitは起動していません
)
echo.

echo [2/3] 現在のデータベース状況を確認...
venv\Scripts\python.exe -c "import sqlite3; conn = sqlite3.connect('data/boatrace.db'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM races'); print(f'    総レース数: {cursor.fetchone()[0]:,}'); cursor.execute('SELECT MAX(race_date) FROM races'); print(f'    最新レース日: {cursor.fetchone()[0]}'); conn.close()"
echo.

echo [3/3] スリープ設定を無効化...
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 30
echo     OK: PCがスリープしないように設定しました
echo.

echo ================================================
echo セットアップ完了！
echo ================================================
echo.
echo 次のコマンドでデータ収集を開始してください：
echo.
echo   venv\Scripts\activate
echo   python fetch_parallel_v4.py --start 2025-10-01 --end 2025-10-31 --workers 10
echo.
echo または、より広い範囲で：
echo   python fetch_parallel_v4.py --start 2025-08-01 --end 2025-10-31 --workers 10
echo.
pause
