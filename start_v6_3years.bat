@echo off
REM V6データ取得バッチファイル
REM 対象期間: 2022-11-01 ～ 2025-10-31 (3年間、1,096日)
REM 修正版スクレイパー使用

echo ========================================
echo V6 データ取得開始
echo 対象期間: 2022-11-01 ～ 2025-10-31
echo 総日数: 1,096日 (3年間)
echo ========================================
echo.
echo 修正内容:
echo - 展示タイム取得率向上 (1.3%% → 70-90%%)
echo - 決まり手取得率向上 (1.5%% → 90%%+)
echo.
echo ログファイル: v6_output.log
echo.
pause

REM Python仮想環境のパスを設定
set VENV_PATH=venv\Scripts\python.exe

REM V6スクリプトを実行（並列度10、ログ出力）
%VENV_PATH% -u fetch_parallel_v6.py --start 2022-11-01 --end 2025-10-31 --workers 10 > v6_output.log 2>&1

echo.
echo ========================================
echo V6 データ取得完了
echo ログを確認してください: v6_output.log
echo ========================================
pause
