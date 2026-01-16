@echo off
REM オリジナル展示データ自動収集のWindowsタスクスケジューラー設定
REM
REM 使い方:
REM   1. このファイルを右クリック → 「管理者として実行」
REM   2. タスクが登録されます（毎日朝8時に実行）
REM
REM 確認方法:
REM   タスクスケジューラー（taskschd.msc）を開いて確認
REM
REM 削除方法:
REM   schtasks /delete /tn "BoatRace_Tenji_Collector" /f

echo ========================================
echo オリジナル展示データ自動収集
echo Windowsタスクスケジューラー設定
echo ========================================
echo.

REM 現在のディレクトリを取得
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..\..
set PYTHON_SCRIPT=%PROJECT_DIR%\scripts\automation\daily_tenji_collector.py

echo プロジェクトディレクトリ: %PROJECT_DIR%
echo Pythonスクリプト: %PYTHON_SCRIPT%
echo.

REM タスク名
set TASK_NAME=BoatRace_Tenji_Collector

REM 既存タスクを削除（存在する場合）
echo 既存タスクをチェック中...
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo 既存タスクを削除します...
    schtasks /delete /tn "%TASK_NAME%" /f
)

echo.
echo 新しいタスクを作成中...
echo   タスク名: %TASK_NAME%
echo   実行時刻: 毎日朝8:00
echo   実行内容: Python %PYTHON_SCRIPT%
echo.

REM タスクを作成
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "python \"%PYTHON_SCRIPT%\"" ^
    /sc daily ^
    /st 08:00 ^
    /ru SYSTEM ^
    /rl HIGHEST ^
    /f

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo タスク登録成功！
    echo ========================================
    echo.
    echo タスク名: %TASK_NAME%
    echo 実行時刻: 毎日朝8:00
    echo.
    echo 確認方法:
    echo   タスクスケジューラー（taskschd.msc）で確認できます
    echo.
    echo ログファイル:
    echo   %PROJECT_DIR%\logs\tenji_collection\
    echo.
    echo 手動実行方法:
    echo   python %PYTHON_SCRIPT% --manual
    echo.
) else (
    echo.
    echo ========================================
    echo エラー: タスク登録失敗
    echo ========================================
    echo.
    echo 管理者権限で実行してください:
    echo   このファイルを右クリック → 「管理者として実行」
    echo.
)

pause
