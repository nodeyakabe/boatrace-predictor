@echo off
echo ================================================================================
echo データ収集後の自動処理を開始します
echo ================================================================================
echo.
echo 処理内容:
echo 1. データ収集完了を待機
echo 2. Dry-run検証 (2021年・2023年)
echo 3. DB投入 (2021年・2023年)
echo 4. 予測データ生成 (2021年・2023年)
echo 5. 標準バックテスト (全6年分)
echo.
echo ログファイル: log_auto_processing.txt
echo.
echo 開始します...
echo.

nohup python scripts\data_collection\自動実行_収集後処理.py > log_auto_processing.txt 2>&1 &

echo.
echo バックグラウンドで実行開始しました
echo 進捗確認: type log_auto_processing.txt
echo ================================================================================
pause
