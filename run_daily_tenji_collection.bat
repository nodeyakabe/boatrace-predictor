@echo off
REM オリジナル展示データ日次収集バッチファイル
REM タスクスケジューラから実行される

cd /d %~dp0

REM 仮想環境がある場合はアクティベート
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM 日次収集スクリプトを実行（ログファイルに出力）
python fetch_original_tenji_daily.py >> logs\daily_tenji_collection.log 2>&1

REM 実行日時をログに記録
echo [%date% %time%] 収集完了 >> logs\daily_tenji_collection.log
