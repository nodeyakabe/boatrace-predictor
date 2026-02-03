@echo off
chcp 65001 > nul
setlocal

echo ========================================
echo 2021年9月～12月 + 2023年全体のデータ収集
echo ========================================
echo.

REM 2021年9月
echo [2021年9月] 処理開始...
python scripts\data_collection\補完_2021_2023_欠損データ.py --year 2021 --month 9
if %errorlevel% neq 0 (
    echo [ERROR] 2021年9月の処理に失敗しました
    pause
    exit /b 1
)
echo [OK] 2021年9月完了
echo.

REM 2021年10月
echo [2021年10月] 処理開始...
python scripts\data_collection\補完_2021_2023_欠損データ.py --year 2021 --month 10
if %errorlevel% neq 0 (
    echo [ERROR] 2021年10月の処理に失敗しました
    pause
    exit /b 1
)
echo [OK] 2021年10月完了
echo.

REM 2021年11月
echo [2021年11月] 処理開始...
python scripts\data_collection\補完_2021_2023_欠損データ.py --year 2021 --month 11
if %errorlevel% neq 0 (
    echo [ERROR] 2021年11月の処理に失敗しました
    pause
    exit /b 1
)
echo [OK] 2021年11月完了
echo.

REM 2021年12月
echo [2021年12月] 処理開始...
python scripts\data_collection\補完_2021_2023_欠損データ.py --year 2021 --month 12
if %errorlevel% neq 0 (
    echo [ERROR] 2021年12月の処理に失敗しました
    pause
    exit /b 1
)
echo [OK] 2021年12月完了
echo.

REM 2023年1-12月
for /L %%m in (1,1,12) do (
    echo [2023年%%m月] 処理開始...
    python scripts\data_collection\補完_2021_2023_欠損データ.py --year 2023 --month %%m
    if errorlevel 1 (
        echo [ERROR] 2023年%%m月の処理に失敗しました
        pause
        exit /b 1
    )
    echo [OK] 2023年%%m月完了
    echo.
)

echo.
echo ========================================
echo 全てのデータ収集が完了しました
echo ========================================
echo.
pause
