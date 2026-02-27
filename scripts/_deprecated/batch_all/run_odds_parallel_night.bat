@echo off
chcp 65001 > nul
echo ================================================================================
echo オッズデータ並列取得（夜間実行版）
echo ================================================================================
echo.
echo 実行日時: %date% %time%
echo.
echo 設定:
echo   - 対象期間: 2020-01-01 ～ 2024-12-31
echo   - 並列スレッド数: 10
echo   - リクエスト間隔: 0.3秒/スレッド
echo   - バッチサイズ: 50件
echo   - 推定処理時間: 13-20時間
echo.
echo 注意事項:
echo   1. 既存の逐次処理版を停止してください
echo   2. PCをスリープさせない設定を確認してください
echo   3. ログは logs/odds_fetch_parallel_night.log に保存されます
echo.
echo ================================================================================
echo.

:: 実行前の確認
set /p confirm="夜間実行を開始しますか？ (Y/N): "
if /i not "%confirm%"=="Y" (
    echo.
    echo キャンセルしました
    pause
    exit /b
)

:: 既存プロセスの確認
echo.
echo 既存のPythonプロセスを確認中...
tasklist /FI "IMAGENAME eq python.exe" | find /i "python.exe" > nul
if %errorlevel%==0 (
    echo.
    echo ⚠️  警告: Pythonプロセスが実行中です
    echo    既存のオッズ取得プロセスを停止してから実行してください
    echo.
    set /p force="それでも続行しますか？ (Y/N): "
    if /i not "%force%"=="Y" (
        echo.
        echo キャンセルしました
        pause
        exit /b
    )
)

:: ログディレクトリ作成
if not exist logs mkdir logs

:: 開始時刻を記録
echo. >> logs/night_execution_log.txt
echo ================================================================================ >> logs/night_execution_log.txt
echo 夜間実行開始: %date% %time% >> logs/night_execution_log.txt
echo ================================================================================ >> logs/night_execution_log.txt

echo.
echo ================================================================================
echo 並列オッズ取得開始
echo ================================================================================
echo.

:: 並列処理実行（バックグラウンド）
start /b python fetch_odds_parallel.py ^
    --db data/boatrace.db ^
    --start-date 2020-01-01 ^
    --end-date 2024-12-31 ^
    --workers 10 ^
    --delay 0.3 ^
    --batch-size 50 ^
    --log-file logs/odds_fetch_parallel_night.log ^
    --progress-interval 100

echo.
echo ✅ バックグラウンドで実行を開始しました
echo.
echo 📊 進捗確認方法:
echo    1. logs/odds_fetch_parallel_night.log を開く
echo    2. または check_odds_progress.py を実行
echo.
echo ⚠️  PCをスリープさせないでください
echo.
echo 終了時刻を記録: %date% %time% >> logs/night_execution_log.txt
echo.

:: 進捗確認ループ（オプション）
set /p monitor="進捗をリアルタイム監視しますか？ (Y/N): "
if /i "%monitor%"=="Y" (
    echo.
    echo Ctrl+C で監視を終了できます（処理は継続）
    echo.
    timeout /t 3
    powershell -Command "Get-Content logs/odds_fetch_parallel_night.log -Wait -Tail 20"
) else (
    echo.
    echo バックグラウンドで実行中です
    echo ログファイルで進捗を確認してください
    pause
)
