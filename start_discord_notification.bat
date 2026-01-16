@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================================
echo ディスコード通知スケジューラーを起動します
echo ============================================================
echo.
echo 起動中...
echo.

start /B python scripts\automation\daily_scheduler.py

echo ディスコード通知スケジューラーが起動しました。
echo.
echo スケジュール:
echo   - 毎朝 8:30 - 本日の予想を生成してDiscordに通知
echo   - 5分ごと - レース監視（締切10分前に通知）
echo.
echo このウィンドウは閉じて構いません。
echo スケジューラーはバックグラウンドで動作し続けます。
echo.
echo 停止方法: タスクマネージャーでpython.exeプロセスを終了
echo.
pause
