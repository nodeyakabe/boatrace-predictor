@echo off
chcp 65001 >nul
echo ================================================================================
echo 全年度欠損オッズ自動収集（CSV方式）
echo ================================================================================
echo.
echo 【CSV方式の利点】
echo   - 大量データに最適（DB負荷なし）
echo   - 途中停止しても既存データが保護される
echo   - 後でまとめてDB投入可能
echo.
echo 実行順序（実測62.0件/分ベース）:
echo   1. 2023年 (46,915レース) - 約12.6時間
echo   2. 2024年 (25,434レース) - 約6.8時間
echo   3. 2022年 (20,976レース) - 約5.6時間
echo   4. 2020年 (19,068レース) - 約5.1時間
echo   5. 2021年 (12,323レース) - 約3.3時間
echo   6. 2025年 (3,959レース) - 約1.1時間
echo   7. 2026年 (551レース) - 約9分
echo.
echo 全体予想時間: 約34.7時間（テスト結果: 62.0件/分達成）
echo ================================================================================
echo.

cd /d "%~dp0..\\.."

echo [%date% %time%] 2023年のCSV収集開始
python scripts/data_collection/fetch_odds_to_csv_parallel.py --start-date 2023-01-01 --end-date 2023-12-31 --output data/csv/odds/2023 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2023年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2023年のCSV収集完了
echo.

echo [%date% %time%] 2024年のCSV収集開始
python scripts/data_collection/fetch_odds_to_csv_parallel.py --start-date 2024-01-01 --end-date 2024-12-31 --output data/csv/odds/2024 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2024年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2024年のCSV収集完了
echo.

echo [%date% %time%] 2022年のCSV収集開始
python scripts/data_collection/fetch_odds_to_csv_parallel.py --start-date 2022-01-01 --end-date 2022-12-31 --output data/csv/odds/2022 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2022年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2022年のCSV収集完了
echo.

echo [%date% %time%] 2020年のCSV収集開始
python scripts/data_collection/fetch_odds_to_csv_parallel.py --start-date 2020-01-01 --end-date 2020-12-31 --output data/csv/odds/2020 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2020年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2020年のCSV収集完了
echo.

echo [%date% %time%] 2021年のCSV収集開始
python scripts/data_collection/fetch_odds_to_csv_parallel.py --start-date 2021-01-01 --end-date 2021-12-31 --output data/csv/odds/2021 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2021年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2021年のCSV収集完了
echo.

echo [%date% %time%] 2025年のCSV収集開始
python scripts/data_collection/fetch_odds_to_csv_parallel.py --start-date 2025-01-01 --end-date 2025-12-31 --output data/csv/odds/2025 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2025年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2025年のCSV収集完了
echo.

echo [%date% %time%] 2026年のCSV収集開始
python scripts/data_collection/fetch_odds_to_csv_parallel.py --start-date 2026-01-01 --end-date 2026-12-31 --output data/csv/odds/2026 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2026年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2026年のCSV収集完了
echo.

echo ================================================================================
echo 全年度のCSV収集完了！
echo ================================================================================
echo.
echo 完了時刻: %date% %time%
echo.
echo 【次の作業】
echo   CSV→DB投入スクリプトを実行してください:
echo   python scripts/data_collection/import_odds_csv_to_db.py --input data/csv/odds
echo.
pause
