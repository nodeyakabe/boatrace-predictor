@echo off
echo ================================================================================
echo V5データ収集開始 - 過去2年分（2023-11-01 ~ 2025-10-31）
echo ================================================================================
echo.
echo 推定処理時間: 約7時間
echo 取得期間: 2023年11月 ~ 2025年10月（24ヶ月分）
echo workers: 10並列
echo HTTP並列化: 有効（3倍高速化）
echo.
echo 現在時刻: %date% %time%
echo.
echo ================================================================================
echo.

REM 既存のPythonプロセスを確認
echo [確認] 既存のデータ収集プロセスをチェック中...
tasklist | findstr /i "python.exe" >nul
if %errorlevel% equ 0 (
    echo.
    echo 警告: 既存のPythonプロセスが稼働中です
    echo 以下のプロセスが見つかりました:
    tasklist | findstr /i "python.exe"
    echo.
    echo V4データ収集が稼働中の場合は完了を待ってから実行してください
    echo.
    choice /c YN /m "このまま続行しますか？"
    if errorlevel 2 (
        echo.
        echo キャンセルしました
        pause
        exit /b
    )
)

echo.
echo [開始] V5データ収集を開始します...
echo.

REM V5を実行
venv\Scripts\python.exe -u fetch_parallel_v5.py --start 2023-11-01 --end 2025-10-31 --workers 10

echo.
echo ================================================================================
echo V5データ収集完了
echo ================================================================================
echo 終了時刻: %date% %time%
echo.
pause
