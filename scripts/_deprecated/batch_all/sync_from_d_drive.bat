@echo off
echo ================================================================================
echo D:/BoatRaceから現在のソースへ差分を反映
echo ================================================================================
echo.

echo [1/5] pattern_analyzer.pyのバグ修正を反映...
copy /Y "D:\BoatRace\src\analysis\pattern_analyzer.py" "C:\Users\seizo\Desktop\BoatRace\src\analysis\pattern_analyzer.py"
if %errorlevel% equ 0 (
    echo   [OK] pattern_analyzer.py更新完了
) else (
    echo   [NG] pattern_analyzer.py更新失敗
)
echo.

echo [2/5] 日本語ドキュメント（27ファイル）を反映...
for %%f in (
    "2025-10-31_作業引継ぎ資料.md"
    "boatrace_data_requirements.md"
    "boatrace_shap_spec.md"
    "COMPLETION_SUMMARY.md"
    "dual_pc_setup.md"
    "ENVIRONMENT_SETUP_COMPLETE.md"
    "HANDOVER_20251031.md"
    "SUBPC_CHANGES_BACKUP.md"
    "UI統合完了報告.md"
    "お昼作業完了サマリー.md"
    "データ取得_課題対応レポート.md"
    "ホーム画面機能説明.md"
    "過去1年分データ取得ガイド.md"
    "再解析機能_実装完了.md"
    "最終完了レポート.md"
    "若松競艇場_分析レポート.md"
    "選手分析_完了レポート.md"
    "並行データ取得ガイド.md"
    "並行実行準備完了.md"
    "補足_不足データ取得ガイド.md"
    "法則エンジン統合完了報告.md"
    "本番PC_データ取得手順書.md"
    "予想エンジン_統合手順書.md"
) do (
    if exist "D:\BoatRace\%%~f" (
        copy /Y "D:\BoatRace\%%~f" "C:\Users\seizo\Desktop\BoatRace\%%~f" >nul
        echo   [OK] %%~f
    ) else (
        echo   [SKIP] %%~f（存在しません）
    )
)
echo.

echo [3/5] 運用バッチファイル（5ファイル）を反映...
for %%f in (
    "fetch_all_missing_data.bat"
    "restart_streamlit.bat"
    "run_boatrace_ui.bat"
    "start_parallel_fetch_subpc.bat"
    "持ち帰り用_作成.bat"
) do (
    if exist "D:\BoatRace\%%~f" (
        copy /Y "D:\BoatRace\%%~f" "C:\Users\seizo\Desktop\BoatRace\%%~f" >nul
        echo   [OK] %%~f
    ) else (
        echo   [SKIP] %%~f（存在しません）
    )
)
echo.

echo [4/5] .streamlit設定ディレクトリを反映...
if exist "D:\BoatRace\.streamlit" (
    xcopy "D:\BoatRace\.streamlit" "C:\Users\seizo\Desktop\BoatRace\.streamlit" /E /I /Y /Q
    if %errorlevel% equ 0 (
        echo   [OK] .streamlit設定完了
    ) else (
        echo   [NG] .streamlit設定失敗
    )
) else (
    echo   [SKIP] .streamlitディレクトリが存在しません
)
echo.

echo [5/5] .claude設定ディレクトリを反映...
if exist "D:\BoatRace\.claude" (
    xcopy "D:\BoatRace\.claude" "C:\Users\seizo\Desktop\BoatRace\.claude" /E /I /Y /Q
    if %errorlevel% equ 0 (
        echo   [OK] .claude設定完了
    ) else (
        echo   [NG] .claude設定失敗
    )
) else (
    echo   [SKIP] .claudeディレクトリが存在しません
)
echo.

echo ================================================================================
echo 差分反映完了
echo ================================================================================
echo.
echo 次のステップ:
echo 1. pattern_analyzer.pyの修正確認
echo    venv\Scripts\python.exe -c "from src.analysis.pattern_analyzer import PatternAnalyzer; print('OK')"
echo.
echo 2. UI起動確認
echo    venv\Scripts\streamlit.exe run ui/app.py --server.port 8501
echo.
pause
