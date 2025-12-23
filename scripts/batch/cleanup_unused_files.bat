@echo off
chcp 65001 > nul
echo ================================================================================
echo 不要ファイル削除スクリプト
echo ================================================================================
echo.
echo このスクリプトは以下のファイル・ディレクトリを削除します:
echo.
echo 【大容量ディレクトリ】
echo   - 受け渡し\temp_extract\ (1.3GB) - 一時展開ファイル
echo   - rdmdb_tide_data\ (376MB) - 潮汐生データ（DB取り込み済み）
echo   - backups\cleanup_20251210\ (5.0MB) - 古いバックアップ
echo   - temp\ (3.8MB) - 一時ファイル
echo.
echo 【大きいログファイル】
echo   - backtest_output.txt (32MB)
echo   - conditional_v1_eval.txt (15MB)
echo   - top3_coverage.txt (15MB)
echo   - v2_eval_output.txt (3.0MB)
echo.
echo 【HTMLファイル】
echo   - デバッグ用HTMLファイル群
echo.
echo 【その他】
echo   - archive_20251118_165053.zip (492KB)
echo   - 各種ログファイル
echo.
echo 推定削減容量: 約1.75GB
echo.
echo ================================================================================
echo.

set /p confirm="削除を実行しますか？ (Y/N): "
if /i not "%confirm%"=="Y" (
    echo.
    echo キャンセルしました
    pause
    exit /b
)

echo.
echo 削除を開始します...
echo.

:: 大容量ディレクトリの削除
echo [1/4] 大容量ディレクトリを削除中...

if exist "受け渡し\temp_extract" (
    rmdir /s /q "受け渡し\temp_extract"
    echo   [OK] temp_extract削除完了 (1.3GB)
) else (
    echo   [SKIP] temp_extractは既に削除済み
)

if exist rdmdb_tide_data (
    rmdir /s /q rdmdb_tide_data
    echo   [OK] rdmdb_tide_data削除完了 (376MB)
) else (
    echo   [SKIP] rdmdb_tide_dataは既に削除済み
)

if exist "backups\cleanup_20251210" (
    rmdir /s /q "backups\cleanup_20251210"
    echo   [OK] cleanup_20251210削除完了 (5.0MB)
) else (
    echo   [SKIP] cleanup_20251210は既に削除済み
)

if exist temp (
    rmdir /s /q temp
    echo   [OK] temp削除完了 (3.8MB)
) else (
    echo   [SKIP] tempは既に削除済み
)

:: ログファイルの削除
echo.
echo [2/4] 大きいログファイルを削除中...

if exist backtest_output.txt (
    del /f backtest_output.txt
    echo   [OK] backtest_output.txt削除完了 (32MB)
)

if exist conditional_v1_eval.txt (
    del /f conditional_v1_eval.txt
    echo   [OK] conditional_v1_eval.txt削除完了 (15MB)
)

if exist top3_coverage.txt (
    del /f top3_coverage.txt
    echo   [OK] top3_coverage.txt削除完了 (15MB)
)

if exist v2_eval_output.txt (
    del /f v2_eval_output.txt
    echo   [OK] v2_eval_output.txt削除完了 (3.0MB)
)

if exist log_oct_2024.txt (
    del /f log_oct_2024.txt
    echo   [OK] log_oct_2024.txt削除完了 (538KB)
)

if exist cfc743_output.txt (
    del /f cfc743_output.txt
    echo   [OK] cfc743_output.txt削除完了
)

if exist error_traceback.txt (
    del /f error_traceback.txt
    echo   [OK] error_traceback.txt削除完了
)

if exist output.txt (
    del /f output.txt
    echo   [OK] output.txt削除完了
)

if exist output_weather_impact.txt (
    del /f output_weather_impact.txt
    echo   [OK] output_weather_impact.txt削除完了
)

if exist output_weather_patterns.txt (
    del /f output_weather_patterns.txt
    echo   [OK] output_weather_patterns.txt削除完了
)

if exist nov_dec_analysis.txt (
    del /f nov_dec_analysis.txt
    echo   [OK] nov_dec_analysis.txt削除完了
)

:: HTMLファイルの削除
echo.
echo [3/4] HTMLファイルを削除中...

del /f debug_odds_*.html 2>nul
echo   [OK] debug_odds_*.html削除完了

if exist page_source.html (
    del /f page_source.html
    echo   [OK] page_source.html削除完了
)

if exist exhibition_table3.html (
    del /f exhibition_table3.html
    echo   [OK] exhibition_table3.html削除完了
)

if exist jodc_top_page.html (
    del /f jodc_top_page.html
    echo   [OK] jodc_top_page.html削除完了
)

if exist race_schedule_page.html (
    del /f race_schedule_page.html
    echo   [OK] race_schedule_page.html削除完了
)

if exist rdmdb_download_page.html (
    del /f rdmdb_download_page.html
    echo   [OK] rdmdb_download_page.html削除完了
)

if exist rdmdb_new_page.html (
    del /f rdmdb_new_page.html
    echo   [OK] rdmdb_new_page.html削除完了
)

if exist monthly_schedule.html (
    del /f monthly_schedule.html
    echo   [OK] monthly_schedule.html削除完了
)

if exist first_row.html (
    del /f first_row.html
    echo   [OK] first_row.html削除完了
)

:: その他のファイル
echo.
echo [4/4] その他のファイルを削除中...

if exist archive_20251118_165053.zip (
    del /f archive_20251118_165053.zip
    echo   [OK] archive_20251118_165053.zip削除完了 (492KB)
)

if exist missing_data_log.txt (
    del /f missing_data_log.txt
    echo   [OK] missing_data_log.txt削除完了
)

if exist missing_races.txt (
    del /f missing_races.txt
    echo   [OK] missing_races.txt削除完了
)

:: 完了メッセージ
echo.
echo ================================================================================
echo 削除完了
echo ================================================================================
echo.
echo 削減された容量を確認中...
powershell -Command "& {$size = (Get-ChildItem -Recurse | Measure-Object -Property Length -Sum).Sum / 1GB; Write-Host \"現在のプロジェクト容量: $([math]::Round($size, 2))GB\"}"
echo.
echo 詳細は cleanup_plan.md を参照してください
echo.
pause
