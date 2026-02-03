@echo off
chcp 65001 > nul
echo ========================================
echo 未処理月データ収集の進捗確認
echo ========================================
echo.

echo [2021年のCSVファイル]
dir /s /b data\csv\補完\2021\*.csv 2>nul | find /c ".csv"
echo.

echo [2023年のCSVファイル]
dir /s /b data\csv\補完\2023\*.csv 2>nul | find /c ".csv"
echo.

echo ========================================
echo 最新ログ（直近30行）
echo ========================================
powershell -Command "Get-Content log_missing_months_collection.txt -Tail 30 -Encoding UTF8" 2>nul

pause
