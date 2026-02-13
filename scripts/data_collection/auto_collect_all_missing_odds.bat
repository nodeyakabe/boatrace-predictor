@echo off
chcp 65001 >nul
echo ================================================================================
echo 全年度欠損オッズ自動収集
echo ================================================================================
echo.
echo 実行順序:
echo   1. 2023年 (46,915レース) - 約11時間
echo   2. 2024年 (25,434レース) - 約7時間
echo   3. 2022年 (20,976レース) - 約6時間
echo   4. 2020年 (19,068レース) - 約5時間
echo   5. 2021年 (12,323レース) - 約3時間
echo   6. 2025年 (3,959レース) - 約1時間
echo   7. 2026年 (551レース) - 約10分
echo.
echo 全体予想時間: 約33時間
echo ================================================================================
echo.

cd /d "%~dp0..\.."

echo [%date% %time%] 2023年の収集開始
python scripts/data_collection/fetch_odds_parallel_safe.py --start-date 2023-01-01 --end-date 2023-12-31 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2023年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2023年の収集完了
echo.

echo [%date% %time%] 2024年の収集開始
python scripts/data_collection/fetch_odds_parallel_safe.py --start-date 2024-01-01 --end-date 2024-12-31 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2024年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2024年の収集完了
echo.

echo [%date% %time%] 2022年の収集開始
python scripts/data_collection/fetch_odds_parallel_safe.py --start-date 2022-01-01 --end-date 2022-12-31 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2022年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2022年の収集完了
echo.

echo [%date% %time%] 2020年の収集開始
python scripts/data_collection/fetch_odds_parallel_safe.py --start-date 2020-01-01 --end-date 2020-12-31 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2020年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2020年の収集完了
echo.

echo [%date% %time%] 2021年の収集開始
python scripts/data_collection/fetch_odds_parallel_safe.py --start-date 2021-01-01 --end-date 2021-12-31 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2021年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2021年の収集完了
echo.

echo [%date% %time%] 2025年の収集開始
python scripts/data_collection/fetch_odds_parallel_safe.py --start-date 2025-01-01 --end-date 2025-12-31 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2025年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2025年の収集完了
echo.

echo [%date% %time%] 2026年の収集開始
python scripts/data_collection/fetch_odds_parallel_safe.py --start-date 2026-01-01 --end-date 2026-12-31 --delay 0.3 --workers 10
if errorlevel 1 (
    echo [ERROR] 2026年の収集に失敗しました
    pause
    exit /b 1
)
echo [%date% %time%] 2026年の収集完了
echo.

echo ================================================================================
echo 全年度の収集完了！
echo ================================================================================
echo.
echo 完了時刻: %date% %time%
echo.
pause
