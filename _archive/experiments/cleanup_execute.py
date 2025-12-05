#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
プロジェクトクリーンアップ実行スクリプト

使用方法:
  python cleanup_execute.py --dry-run  # 移動対象を表示のみ
  python cleanup_execute.py --execute  # 実際に移動を実行
"""
import os
import shutil
import argparse
from pathlib import Path

# 移動対象スクリプト
SCRIPTS_TO_ARCHIVE = [
    # test_*.py（例外除く）
    "test_補完_決まり手_改善版.py",
    "test_収集_RDMDB潮位_改善版.py",
    "test_潮位イベント抽出.py",
    "test_潮位イベント抽出v2.py",
    "test_潮位イベント抽出v3.py",
    "test_kimarite_fix.py",
    "test_historical_data_access.py",
    "test_single_race.py",
    "test_scraper.py",
    "test_improved_scraper.py",
    "test_improved_simple.py",
    "test_basic_scraper.py",
    "test_v4_scraper.py",
    "test_v4_multiple_races.py",
    "test_odds_fetcher.py",
    "test_new_modules.py",
    "test_racer_features.py",
    "test_dataset_with_racer_features.py",

    # check_*.py（check_db_status.py除く）
    "check_all_data_completeness.py",
    "check_cancelled_races.py",
    "check_collection_progress.py",
    "check_collection_status.py",
    "check_columns.py",
    "check_data_dates.py",
    "check_data_progress.py",
    "check_db_20251113.py",
    "check_db_20251113_final.py",
    "check_db_20251113_v2.py",
    "check_db_quick.py",
    "check_db_schema.py",
    "check_db_schema_v2.py",
    "check_db_structure.py",
    "check_db_tables.py",
    "check_missing_data.py",
    "check_missing_data_simple.py",
    "check_missing_final.py",
    "check_missing_correct.py",
    "check_monthly_data.py",
    "check_pit3_pattern.py",
    "check_progress.py",
    "check_recent_st.py",
    "check_settings.py",
    "check_st_coverage.py",
    "check_system_status.py",
    "check_venues.py",
    "check_venue_count.py",
    "check_weather_data.py",
    "check_yesterday_st.py",
    "check_original_tenji_saved.py",

    # debug/analyze/verify/monitor/count/measure
    "debug_race_result.py",
    "debug_table_structure.py",
    "analyze_characteristics_simple.py",
    "analyze_collected_data.py",
    "analyze_data_quality.py",
    "analyze_exp009_issue.py",
    "analyze_missing_data.py",
    "analyze_racer_comprehensive.py",
    "analyze_shap_values.py",
    "analyze_top_racers.py",
    "analyze_venue_patterns.py",
    "analyze_venue_racer_characteristics.py",
    "analyze_win_rate.py",
    "verify_fix_result.py",
    "verify_v3_data.py",
    "monitor_collection.py",
    "monitor_parallel.py",
    "monitor_progress.py",
    "monitor_tide_linking.py",
    "count_missing.py",
    "count_2016_2025_st_races.py",
    "measure_bottleneck.py",

    # 古い補完スクリプト
    "補完_風向データ.py",
    "補完_風向データ_全件.py",
    "補完_風向データ_全件_自動.py",
    "補完_展示タイム_全件_自動.py",
    "補完_展示タイム_全件_高速化.py",
    "補完_展示タイム_並列.py",
    "補完_払戻金データ.py",

    # 古い収集スクリプト
    "収集_オリジナル展示_最新.py",
    "収集_潮位データ_最新.py",
    "収集_2020年潮位データ.py",

    # 古いfetchスクリプト
    "fetch_historical_data_backup.py",
    "fetch_venue_data.py",
    "fetch_parallel_improved.py",
    "fetch_improved_v2.py",
    "fetch_missing_data.py",
    "collect_environmental_data.py",

    # その他古いスクリプト
    "抽出_潮位イベント_tide移行.py",
    "抽出_潮位イベント_追加3会場.py",
    "link_tide_data.py",
    "reanalyze_all.py",
    "register_top_racer_rules.py",
    "fix_data_coverage_checker.py",
    "fix_sql_syntax_errors.py",
    "update_existing_race_status.py",
    "add_race_status_column.py",
    "delete_scripts.py",
    "場攻略情報インポート.py",
    "30分後確認.py",
    "investigate_tide_data.py",
    "investigate_rdmdb_tide.py",
    "investigate_rdmdb_simple.py",
    "estimate_storage.py",
    "comprehensive_logic_check.py",
    "generate_data_quality_report.py",
    "setup_test_data.py",
    "quick_status.py",
    "create_race_details_for_tenji.py",
]

# 移動対象ドキュメント
DOCS_TO_ARCHIVE = [
    # 作業サマリー系（重複）
    "SESSION_REPORT.md",
    "PROGRESS_REPORT.md",
    "PROGRESS_SUMMARY.md",
    "STATUS_REPORT.md",
    "STATUS_SUMMARY_20251113.md",
    "CURRENT_SESSION_SUMMARY.md",
    "CURRENT_SESSION_SUMMARY_UPDATED.md",
    "SESSION_FINAL_REPORT.md",
    "SESSION_COMPLETION_REPORT.md",
    "FINAL_SUMMARY.md",
    "WORK_SUMMARY.md",

    # 分析・計画系（古い）
    "EFFICIENCY_IMPROVEMENT.md",
    "EFFICIENCY_ANALYSIS.md",
    "SPEED_COMPARISON.md",
    "OPTIMIZATION_COMPLETE.md",
    "FURTHER_OPTIMIZATION_ANALYSIS.md",
    "TIMING_ANALYSIS.md",
    "TURBO_EDITION_COMPLETE.md",
    "TURBO_PERFORMANCE_VALIDATION.md",
    "BOTTLENECK_ANALYSIS_AND_IMPROVEMENTS.md",
    "REAL_BOTTLENECK_ANALYSIS.md",
    "ALTERNATIVE_DATA_SOURCES.md",
    "DOWNLOAD_SOLUTION_SUMMARY.md",
    "HTML_DOWNLOAD_ANALYSIS.md",
    "SELECTOLAX_TEST_RESULTS.md",
    "ULTRA_OPTIMIZATION_PLAN.md",
    "PARALLEL_RISK_ANALYSIS.md",
    "LUNCH_BREAK_PLAN.md",
    "PHASE3_PREPARATION.md",

    # 実装・仕様系（古い）
    "FEATURE_DESIGN.md",
    "DEPLOYMENT_PLAN_V3.md",
    "DATA_COLLECTION_ISSUES.md",
    "V3_OPTIMIZATION_ANALYSIS.md",
    "REORGANIZATION_SUMMARY.md",
    "MODULE_CONSOLIDATION_PLAN.md",
    "SCRAPER_CONSOLIDATION_PLAN.md",
    "MODULE_CONSOLIDATION_COMPLETED.md",
    "SCRAPER_CONSOLIDATION_COMPLETED.md",
    "ANALYSIS_MODULE_GUIDE.md",
    "OFFICIAL_VENUE_DATA_IMPLEMENTATION.md",
    "VENUE_RACER_ANALYSIS_UI_COMPLETED.md",
    "STAGE2_MODEL_COMPLETED.md",
    "REALTIME_PREDICTION_IMPROVED.md",
    "PURCHASE_HISTORY_TRACKING_COMPLETED.md",
    "REMAINING_TASKS.md",
    "TASK_COMPLETION_SUMMARY.md",
    "ODDS_API_COMPLETED.md",
    "CALIBRATION_VALIDATION_COMPLETED.md",
    "FINAL_PROJECT_REPORT.md",
    "STAGE1_IMPROVEMENT_COMPLETED.md",
    "IMPROVEMENT_ADVICE_COMPARISON.md",
    "RACER_FEATURES_COMPLETED.md",
    "FEATURE_COMPARISON.md",
    "COLLECTION_STATUS_REPORT.md",
    "SUMMARY_V3_FIX.md",
    "TEST_COMPLETION_REPORT_20251111.md",
    "MISSING_DATA_ANALYSIS_20251111.md",
    "ORIGINAL_TENJI_SCRAPER_FIX_20251111.md",
    "ORIGINAL_TENJI_STATUS.md",
    "CORRECTED_WORK_REPORT_20251111.md",
    "SCRAPER_V4_COMPLETED.md",
    "V4_INTEGRATION_TEST_SUCCESS.md",
    "DATA_RETENTION_DISCOVERY.md",

    # その他古いレポート
    "ROADMAP.md",
    "ISSUES_AND_NEXT_STEPS.md",
    "IMPLEMENTATION_SUMMARY.md",
    "SAFETY_CHECK_AND_READINESS.md",
    "START_DATA_COLLECTION.md",
    "RISK_ASSESSMENT.md",
    "FIXES_APPLIED.md",
    "ERROR_HANDLING_IMPROVEMENT.md",
    "EXCEPTION_HANDLING_IMPROVEMENTS.md",
    "KELLY_BETTING_INTEGRATION.md",
    "ODDS_API_STATUS.md",
    "CODE_ANALYSIS_REPORT.md",
    "HANDOVER.md",
    "SYSTEM_SPECIFICATION.md",
    "TONIGHT_3MONTHS_README.md",
    "TRANSFER_README.md",
    "README_復元完了.md",
    "investigate_additional_data.md",
    "data_gap_analysis.md",
    "kimarite_investigation.md",
    "IMPROVEMENT_PLAN.md",
    "潮位API調査.md",
    "V5並行実行分析.md",
    "データ収集状況_中間レポート.md",
    "RDMDB潮位データ調査結果.md",
    "CLEANUP_REPORT.md",
]


def main():
    parser = argparse.ArgumentParser(description='プロジェクトクリーンアップ実行')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true', help='移動対象を表示のみ（実際には移動しない）')
    group.add_argument('--execute', action='store_true', help='実際に移動を実行')

    args = parser.parse_args()

    # アーカイブディレクトリの作成
    archive_scripts = Path('archive/scripts_old')
    archive_docs = Path('archive/docs_old')

    if args.execute:
        archive_scripts.mkdir(parents=True, exist_ok=True)
        archive_docs.mkdir(parents=True, exist_ok=True)

    # スクリプトの移動
    print("=" * 80)
    print("スクリプトファイルの移動")
    print("=" * 80)

    moved_scripts = 0
    skipped_scripts = 0

    for script in SCRIPTS_TO_ARCHIVE:
        src = Path(script)
        if src.exists():
            if args.dry_run:
                print(f"[DRY RUN] {script} → archive/scripts_old/")
            else:
                dst = archive_scripts / script
                shutil.move(str(src), str(dst))
                print(f"[MOVED] {script} → archive/scripts_old/")
            moved_scripts += 1
        else:
            skipped_scripts += 1

    print(f"\n移動: {moved_scripts}件, スキップ: {skipped_scripts}件")

    # ドキュメントの移動
    print("\n" + "=" * 80)
    print("ドキュメントファイルの移動")
    print("=" * 80)

    moved_docs = 0
    skipped_docs = 0

    for doc in DOCS_TO_ARCHIVE:
        src = Path(doc)
        if src.exists():
            if args.dry_run:
                print(f"[DRY RUN] {doc} → archive/docs_old/")
            else:
                dst = archive_docs / doc
                shutil.move(str(src), str(dst))
                print(f"[MOVED] {doc} → archive/docs_old/")
            moved_docs += 1
        else:
            skipped_docs += 1

    print(f"\n移動: {moved_docs}件, スキップ: {skipped_docs}件")

    # サマリー
    print("\n" + "=" * 80)
    print("クリーンアップサマリー")
    print("=" * 80)
    print(f"スクリプト: 移動{moved_scripts}件, スキップ{skipped_scripts}件")
    print(f"ドキュメント: 移動{moved_docs}件, スキップ{skipped_docs}件")
    print(f"合計移動: {moved_scripts + moved_docs}件")

    if args.dry_run:
        print("\n[DRY RUN] 実際には移動していません")
        print("実行する場合は: python cleanup_execute.py --execute")
    else:
        print("\n[完了] ファイルをarchive/に移動しました")
        print("元に戻す場合は archive/ から手動で戻してください")


if __name__ == "__main__":
    main()
