@echo off
REM V5再実行バッチファイル（修正版data_manager使用）
REM 対象期間: 2023-11-01 ～ 2025-10-31 (2年間、731日)
REM 既存データを修正版ロジックで更新

echo ========================================
echo V5 再実行（修正版）
echo 対象期間: 2023-11-01 ～ 2025-10-31
echo 総日数: 731日 (2年間)
echo ========================================
echo.
echo 修正内容:
echo - 展示タイム保存ロジック修正済み (INSERT OR REPLACE → UPSERT with COALESCE)
echo - 既存データを上書きせず、不足データのみ補完
echo.
echo ログファイル: v5_fixed_output.log
echo.
pause

REM Python仮想環境のパスを設定
set VENV_PATH=venv\Scripts\python.exe

REM V5スクリプトを実行（並列度10、ログ出力）
%VENV_PATH% -u fetch_parallel_v5.py --start 2023-11-01 --end 2025-10-31 --workers 10 > v5_fixed_output.log 2>&1

echo.
echo ========================================
echo V5 再実行完了
echo ログを確認してください: v5_fixed_output.log
echo ========================================
pause
