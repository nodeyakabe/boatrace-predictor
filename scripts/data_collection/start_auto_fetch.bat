@echo off
chcp 65001 >nul
cd /d "c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032"

echo ================================================
echo 2020-2025年データ自動取得を開始します
echo ================================================
echo.
echo 既存データをスキップして続きから取得します
echo ログファイル: logs\auto_fetch_2020_2025_*.log
echo.
echo このウィンドウを閉じると処理が中断されます
echo 3日間放置してください
echo.
echo ================================================
echo.

python scripts\data_collection\auto_fetch_2020_2025.py --skip-2022

echo.
echo ================================================
echo 処理が完了しました
echo ================================================
pause
