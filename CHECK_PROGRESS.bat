@echo off
chcp 65001 >nul
echo ================================================================================
echo データ収集 進捗確認
echo ================================================================================
echo.

REM CSV出力ディレクトリの確認
echo [2021年]
if exist "data\csv\補完\2021\" (
    echo   出力先: data\csv\補完\2021\
    for /f %%A in ('dir /b /a-d "data\csv\補完\2021\*.csv" 2^>nul ^| find /c /v ""') do set count2021=%%A
    if defined count2021 (
        echo   CSVファイル数: %count2021%個
    ) else (
        echo   CSVファイル数: 0個
    )
) else (
    echo   まだ出力されていません
)
echo.

echo [2023年]
if exist "data\csv\補完\2023\" (
    echo   出力先: data\csv\補完\2023\
    for /f %%A in ('dir /b /a-d "data\csv\補完\2023\*.csv" 2^>nul ^| find /c /v ""') do set count2023=%%A
    if defined count2023 (
        echo   CSVファイル数: %count2023%個
    ) else (
        echo   CSVファイル数: 0個
    )
) else (
    echo   まだ出力されていません
)
echo.

REM ログファイルの最後の部分を表示
if exist "log_data_collection_2021_2023.txt" (
    echo [最新ログ]（最後の30行）
    echo ------------------------------------------------------------
    powershell -Command "Get-Content log_data_collection_2021_2023.txt | Select-Object -Last 30"
    echo.
) else (
    echo ログファイルがまだ作成されていません
    echo.
)

echo ================================================================================
echo.
pause
