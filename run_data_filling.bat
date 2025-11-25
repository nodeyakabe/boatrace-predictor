@echo off
chcp 65001 > nul
echo ========================================
echo データ補充スクリプト実行ツール
echo ========================================
echo.

:MENU
echo 実行するタスクを選択してください:
echo.
echo [1] データ状況チェック（推奨：最初に実行）
echo [2] race_details補充（2022年）- 推定4-5時間
echo [3] results補充（全期間）- 推定2時間
echo [4] payouts補充（全期間）- 推定6時間
echo [5] テスト実行（50レース限定）
echo [0] 終了
echo.

set /p choice="選択 [0-5]: "

if "%choice%"=="0" goto END
if "%choice%"=="1" goto CHECK
if "%choice%"=="2" goto DETAILS
if "%choice%"=="3" goto RESULTS
if "%choice%"=="4" goto PAYOUTS
if "%choice%"=="5" goto TEST

echo 無効な選択です。
goto MENU

:CHECK
echo.
echo データ状況をチェック中...
python check_all_data_completeness.py
echo.
pause
goto MENU

:DETAILS
echo.
echo ========================================
echo race_details補充を開始します
echo 対象: 2022年全体
echo 推定時間: 4-5時間
echo ========================================
echo.
echo 注意: 長時間実行されます。PCをスリープさせないでください。
echo.
set /p confirm="実行しますか？ (Y/N): "
if /i not "%confirm%"=="Y" goto MENU

echo.
echo 実行中... (Ctrl+Cで中断可能)
python -u fill_missing_data_v4_ultra.py --start 2022-01-01 --end 2022-12-31 --type details --workers 30 --rps 30 --batch-size 200

echo.
echo 完了しました。
pause
goto MENU

:RESULTS
echo.
echo ========================================
echo results補充を開始します
echo 対象: 全期間（2016-2025）
echo 推定時間: 2時間
echo ========================================
echo.
set /p confirm="実行しますか？ (Y/N): "
if /i not "%confirm%"=="Y" goto MENU

echo.
echo 実行中... (Ctrl+Cで中断可能)
python -u fill_missing_data_v4_ultra.py --start 2016-01-01 --end 2025-11-12 --type results --workers 30 --rps 30 --batch-size 200

echo.
echo 完了しました。
pause
goto MENU

:PAYOUTS
echo.
echo ========================================
echo payouts補充を開始します
echo 対象: 全期間（2016-2025）
echo 推定時間: 6時間
echo ========================================
echo.
set /p confirm="実行しますか？ (Y/N): "
if /i not "%confirm%"=="Y" goto MENU

echo.
echo 実行中... (Ctrl+Cで中断可能)
python -u fill_missing_data_v4_ultra.py --start 2016-01-01 --end 2025-11-12 --type payouts --workers 30 --rps 30 --batch-size 200

echo.
echo 完了しました。
pause
goto MENU

:TEST
echo.
echo ========================================
echo テスト実行（50レース限定）
echo ========================================
echo.
python -u fill_missing_data_v4_ultra.py --start 2022-01-10 --end 2022-01-20 --type details --workers 10 --rps 10 --limit 50

echo.
echo テスト完了。
pause
goto MENU

:END
echo.
echo 終了します。
exit /b 0
