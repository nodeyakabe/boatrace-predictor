@echo off
REM V6テスト実行バッチファイル
REM 対象期間: 2022-11-01 ～ 2022-11-07 (1週間)

echo ========================================
echo V6 テスト実行 (1週間分)
echo 対象期間: 2022-11-01 ～ 2022-11-07
echo ========================================
echo.
echo 修正版スクレイパーの動作確認:
echo - 展示タイム取得テスト
echo - 決まり手取得テスト
echo.
pause

REM Python仮想環境のパスを設定
set VENV_PATH=venv\Scripts\python.exe

REM V6スクリプトを実行（並列度10）
%VENV_PATH% -u fetch_parallel_v6.py --start 2022-11-01 --end 2022-11-07 --workers 10

echo.
echo ========================================
echo V6 テスト完了
echo ========================================
pause
