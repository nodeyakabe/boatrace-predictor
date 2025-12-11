@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul

REM ========================================
REM 夜間バッチ処理マスタースクリプト
REM ========================================

set LOG_DIR=logs\night_batch
set OUTPUT_DIR=output
mkdir "%LOG_DIR%" 2>nul
mkdir "%OUTPUT_DIR%" 2>nul

set TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TIMESTAMP=%TIMESTAMP: =0%
set LOG_FILE=%LOG_DIR%\batch_%TIMESTAMP%.log

echo ======================================== >> "%LOG_FILE%"
echo 夜間バッチ開始: %date% %time% >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

echo 夜間バッチを開始します...
echo ログファイル: %LOG_FILE%
echo.

REM ========================================
REM タスク1: データ収集完了待機
REM ========================================
echo [1/7] データ収集完了を待機中...
echo [1/7] データ収集完了を待機中... >> "%LOG_FILE%"

set WAIT_COUNT=0
set MAX_WAIT=240

:WAIT_LOOP
if !WAIT_COUNT! GEQ !MAX_WAIT! goto WAIT_TIMEOUT

python -c "import sqlite3; conn = sqlite3.connect('data/boatrace.db'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(DISTINCT r.race_date) FROM race_predictions rp JOIN races r ON rp.race_id = r.id WHERE rp.generated_at >= \"2025-12-10\"'); print(cursor.fetchone()[0]); conn.close()" > temp_count.txt 2>&1
set /p COMPLETED=<temp_count.txt
del temp_count.txt

if !COMPLETED! GEQ 365 (
    echo データ収集完了！ 365日分のデータを確認しました。
    echo データ収集完了！ 365日分のデータを確認しました。 >> "%LOG_FILE%"
    goto DATA_READY
)

echo 進捗: !COMPLETED!/365日完了...
echo 進捗: !COMPLETED!/365日完了... >> "%LOG_FILE%"
timeout /t 60 /nobreak > nul
set /a WAIT_COUNT+=1
goto WAIT_LOOP

:WAIT_TIMEOUT
echo [警告] タイムアウト: データ収集が完了しませんでした
echo [警告] タイムアウト: データ収集が完了しませんでした >> "%LOG_FILE%"
echo 収集済みデータで分析を続行します...
echo 収集済みデータで分析を続行します... >> "%LOG_FILE%"

:DATA_READY
echo. >> "%LOG_FILE%"

REM ========================================
REM タスク2-7: 分析スクリプト実行
REM ========================================
echo [2/7] 全期間信頼度B三連単的中率検証...
echo [2/7] 全期間信頼度B三連単的中率検証... >> "%LOG_FILE%"
python scripts/validate_confidence_b_trifecta.py --start 2025-01-01 --end 2025-12-31 >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [エラー] タスク2でエラーが発生しましたが続行します
    echo [エラー] タスク2でエラーが発生しましたが続行します >> "%LOG_FILE%"
) else (
    echo [OK] タスク2完了
    echo [OK] タスク2完了 >> "%LOG_FILE%"
)
echo. >> "%LOG_FILE%"

echo [3/7] 季節変動分析（信頼度B）...
echo [3/7] 季節変動分析（信頼度B）... >> "%LOG_FILE%"
python scripts/analyze_seasonal_trends.py --confidence B >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [エラー] タスク3でエラーが発生しましたが続行します
    echo [エラー] タスク3でエラーが発生しましたが続行します >> "%LOG_FILE%"
) else (
    echo [OK] タスク3完了
    echo [OK] タスク3完了 >> "%LOG_FILE%"
)
echo. >> "%LOG_FILE%"

echo [4/7] 会場別・条件別分析（信頼度B）...
echo [4/7] 会場別・条件別分析（信頼度B）... >> "%LOG_FILE%"
python scripts/analyze_conditions.py --confidence B >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [エラー] タスク4でエラーが発生しましたが続行します
    echo [エラー] タスク4でエラーが発生しましたが続行します >> "%LOG_FILE%"
) else (
    echo [OK] タスク4完了
    echo [OK] タスク4完了 >> "%LOG_FILE%"
)
echo. >> "%LOG_FILE%"

echo [5/7] 信頼度B細分化検証...
echo [5/7] 信頼度B細分化検証... >> "%LOG_FILE%"
python scripts/validate_confidence_b_split.py --threshold 70 >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [エラー] タスク5でエラーが発生しましたが続行します
    echo [エラー] タスク5でエラーが発生しましたが続行します >> "%LOG_FILE%"
) else (
    echo [OK] タスク5完了
    echo [OK] タスク5完了 >> "%LOG_FILE%"
)
echo. >> "%LOG_FILE%"

echo [6/7] 信頼度別総合精度レポート作成...
echo [6/7] 信頼度別総合精度レポート作成... >> "%LOG_FILE%"
python scripts/analyze_comprehensive_accuracy.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [エラー] タスク6でエラーが発生しましたが続行します
    echo [エラー] タスク6でエラーが発生しましたが続行します >> "%LOG_FILE%"
) else (
    echo [OK] タスク6完了
    echo [OK] タスク6完了 >> "%LOG_FILE%"
)
echo. >> "%LOG_FILE%"

echo [7/7] 季節変動分析（信頼度C）...
echo [7/7] 季節変動分析（信頼度C）... >> "%LOG_FILE%"
python scripts/analyze_seasonal_trends.py --confidence C >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [エラー] タスク7でエラーが発生しましたが続行します
    echo [エラー] タスク7でエラーが発生しましたが続行します >> "%LOG_FILE%"
) else (
    echo [OK] タスク7完了
    echo [OK] タスク7完了 >> "%LOG_FILE%"
)
echo. >> "%LOG_FILE%"

REM ========================================
REM 完了サマリー
REM ========================================
echo. >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"
echo 夜間バッチ完了: %date% %time% >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

echo 生成されたレポート: >> "%LOG_FILE%"
dir /b "%OUTPUT_DIR%\*.csv" >> "%LOG_FILE%" 2>&1
dir /b "%OUTPUT_DIR%\*.png" >> "%LOG_FILE%" 2>&1
dir /b "%OUTPUT_DIR%\*.md" >> "%LOG_FILE%" 2>&1
echo. >> "%LOG_FILE%"

echo.
echo ========================================
echo 夜間バッチが完了しました
echo ========================================
echo.
echo ログファイル: %LOG_FILE%
echo 出力ディレクトリ: %OUTPUT_DIR%
echo.
echo 生成されたファイル:
dir /b "%OUTPUT_DIR%\*.csv" 2>nul
dir /b "%OUTPUT_DIR%\*.png" 2>nul
dir /b "%OUTPUT_DIR%\*.md" 2>nul
echo.
