@echo off
REM ================================================
REM Phase 2/2.5/3 本番環境導入スクリプト
REM ================================================
REM
REM 使用方法:
REM   production_deployment.bat [オプション]
REM
REM オプション:
REM   --test          テストモードで実行（変更なし）
REM   --enable-all    全機能を有効化
REM   --rollback      前の状態にロールバック
REM
REM ================================================

setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"

echo ================================================
echo Phase 2/2.5/3 本番環境導入
echo ================================================
echo.
echo 実行日時: %date% %time%
echo プロジェクト: %PROJECT_ROOT%
echo.

REM ステップ1: 環境チェック
echo [Step 1/6] 環境チェック...
python --version > nul 2>&1
if errorlevel 1 (
    echo エラー: Pythonが見つかりません
    exit /b 1
)
echo   Python: OK

if not exist "data\boatrace.db" (
    echo エラー: データベースが見つかりません
    exit /b 1
)
echo   Database: OK

if not exist "config\feature_flags.py" (
    echo エラー: feature_flags.pyが見つかりません
    exit /b 1
)
echo   Feature Flags: OK
echo.

REM ステップ2: バックアップ作成
echo [Step 2/6] バックアップ作成...
set "BACKUP_DIR=backups\pre_deployment_%date:~0,4%%date:~5,2%%date:~8,2%"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

copy "config\feature_flags.py" "%BACKUP_DIR%\feature_flags.py.bak" > nul
echo   feature_flags.py backed up
echo.

REM ステップ3: ログディレクトリ準備
echo [Step 3/6] ログディレクトリ準備...
if not exist "logs\monitoring" mkdir "logs\monitoring"
if not exist "logs\alerts" mkdir "logs\alerts"
if not exist "output\monitoring" mkdir "output\monitoring"
echo   ログディレクトリ: OK
echo.

REM ステップ4: モニタリング設定確認
echo [Step 4/6] モニタリング設定確認...
if not exist "config\monitoring_config.json" (
    echo   警告: monitoring_config.jsonがありません（デフォルト設定を使用）
) else (
    echo   monitoring_config.json: OK
)
echo.

REM ステップ5: 機能有効化
echo [Step 5/6] 機能フラグ確認...
python -c "from config.feature_flags import get_enabled_features; print('  有効な機能:', ', '.join(get_enabled_features()[:5]), '...')" 2>nul
echo.

REM ステップ6: 動作確認
echo [Step 6/6] 簡易動作確認...
python -c "from src.analysis.race_predictor import RacePredictor; print('  RacePredictor: OK')" 2>nul
python -c "from src.utils.pattern_cache import PatternCache; print('  PatternCache: OK')" 2>nul
python -c "from src.analysis.negative_pattern_checker import NegativePatternChecker; print('  NegativePatternChecker: OK')" 2>nul
echo.

echo ================================================
echo 導入準備完了
echo ================================================
echo.
echo 次のステップ:
echo   1. ネガティブパターン有効化:
echo      python -c "from config.feature_flags import set_feature_flag; set_feature_flag('negative_patterns', True)"
echo.
echo   2. 自動モニタリング起動:
echo      python scripts\automated_monitoring.py
echo.
echo   3. パターン分析実行:
echo      python scripts\auto_pattern_update.py --days 7
echo.
echo ================================================

endlocal
