@echo off
chcp 65001 > nul
echo ================================================================================
echo DB破損対策強化版 - 並列オッズ収集
echo ================================================================================
echo.
echo 改善内容:
echo   - WALモード有効化（DB破損防止）
echo   - Ctrl+Cで優雅に終了（データ保存後に停止）
echo   - 1時間ごとに自動バックアップ
echo   - DB接続プーリング（高速化）
echo.
echo 注意事項:
echo   - 停止する場合は必ずCtrl+Cを使用してください
echo   - タスクマネージャーからの強制終了は避けてください
echo.
echo ================================================================================
echo.

set /p confirm="実行しますか？ (Y/N): "
if /i not "%confirm%"=="Y" (
    echo.
    echo キャンセルしました
    pause
    exit /b
)

echo.
echo 並列オッズ収集を開始します...
echo.

python fetch_odds_parallel_safe.py --db data/boatrace.db --start-date 2020-01-01 --end-date 2024-12-31 --workers 10 --delay 0.3 --batch-size 50 --log-file logs/odds_fetch_safe.log --progress-interval 100 --backup-interval 3600

echo.
echo ================================================================================
echo 処理が終了しました
echo ================================================================================
echo.
pause
