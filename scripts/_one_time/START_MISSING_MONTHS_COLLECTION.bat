@echo off
chcp 65001 > nul
echo ========================================
echo 未処理月のみのデータ収集を開始します
echo ========================================
echo.
echo 対象: 2021年7月～12月 + 2023年全体（18ヶ月）
echo 予想時間: 約45-63時間
echo.
echo ログファイル: log_missing_months_collection.txt
echo.
pause

echo.
echo データ収集を開始しています...
echo.

python scripts\data_collection\補完_未処理月のみ実行.py > log_missing_months_collection.txt 2>&1

echo.
echo ========================================
echo データ収集が完了しました
echo ========================================
echo.
echo ログを確認してください: log_missing_months_collection.txt
echo.
pause
