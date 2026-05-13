#!/usr/bin/env python3
"""
ドキュメント整理自動化スクリプト
PROJECT_CLEANUP_PLAN_20251210.mdに基づいてMarkdownファイルを整理
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict

# ベースディレクトリ
BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "docs"
DOCS_ARCHIVE_DIR = DOCS_DIR / "archive"

# 整理対象ファイルリスト（ルートディレクトリ）
ROOT_FILES_TO_MOVE: Dict[str, List[str]] = {
    "archive_2025_11_work_logs": [
        # WORK系
        "WORK_SUMMARY_20251113.md",
        "WORKFLOW_TEST_REPORT.md",
        "FINAL_WORK_SUMMARY_20251113.md",
        "README_WORK_GUIDE.md",

        # SESSION系
        "SESSION_COMPLETION_REPORT.md",
        "SESSION_FINAL_REPORT.md",
        "SESSION_REPORT.md",
        "CURRENT_SESSION_SUMMARY.md",
        "CURRENT_SESSION_SUMMARY_UPDATED.md",

        # PROGRESS系
        "PROGRESS_REPORT.md",
        "PROGRESS_SUMMARY.md",

        # STATUS系
        "STATUS_REPORT.md",
        "STATUS_SUMMARY_20251113.md",

        # 復元作業
        "復元作業報告_20251113.md",
        "機能比較レポート_復元版vs破損版.md",
        "欠落機能と復元計画.md",
        "復元完了_購入履歴とバックテスト追加.md",
        "復元完了_最終レポート.md",
        "PROJECT_BUG_REPORT_20251113.md",
        "CRITICAL_DISCOVERY_20251113.md",
        "EXECUTION_SUMMARY_20251113.md",
        "FILE_ORGANIZATION_ANALYSIS_20251113.md",

        # HANDOVER系
        "HANDOVER_REPORT_20251111.md",
        "HANDOVER.md",
        "CORRECTED_WORK_REPORT_20251111.md",
        "TEST_COMPLETION_REPORT_20251111.md",

        # DATA_COLLECTION系
        "DATA_COLLECTION_ISSUES.md",
        "COLLECTION_STATUS_REPORT.md",
        "MISSING_DATA_ANALYSIS_20251111.md",
    ],

    "archive_2025_11_reports": [
        # IMPLEMENTATION系
        "IMPLEMENTATION_GUIDE.md",
        "IMPLEMENTATION_SUMMARY.md",
        "IMPLEMENTATION_SUMMARY_20251117.md",
        "FINAL_IMPLEMENTATION_REPORT.md",
        "FINAL_IMPLEMENTATION_SUMMARY.md",
        "IMPROVEMENT_IMPLEMENTATION_SUMMARY.md",
        "PHASE_1-3_IMPLEMENTATION_SUMMARY.md",
        "PHASE_1-4_FINAL_REPORT.md",

        # IMPROVEMENT系
        "IMPROVEMENT_PLAN_20251117.md",
        "IMPROVEMENTS.md",
        "FUTURE_IMPROVEMENTS_ANALYSIS.md",
        "IMPROVEMENT_ROADMAP.md",
        "IMPROVEMENT_ADVICE_COMPARISON.md",

        # FINAL系レポート
        "FINAL_COMPREHENSIVE_REPORT.md",
        "FINAL_EXPERIMENTS_REPORT.md",
        "FINAL_PROJECT_REPORT.md",
        "FINAL_SUMMARY.md",
        "FINAL_SUMMARY_REPORT.md",
        "IMPROVEMENTS_COMPREHENSIVE_REPORT.md",
        "ULTIMATE_SUMMARY_REPORT.md",

        # ANALYSIS系
        "COMPREHENSIVE_*.md",  # パターンマッチング用
        "BACKTEST_COMPARISON_REPORT.md",
        "CODE_ANALYSIS_REPORT.md",
        "EFFICIENCY_ANALYSIS.md",
        "EFFICIENCY_IMPROVEMENT.md",
        "ANALYSIS_MODULE_GUIDE.md",
        "CALIBRATION_VALIDATION_COMPLETED.md",
        "ERROR_HANDLING_IMPROVEMENT.md",
        "EXCEPTION_HANDLING_IMPROVEMENTS.md",
        "FURTHER_OPTIMIZATION_ANALYSIS.md",
        "HTML_DOWNLOAD_ANALYSIS.md",
        "MODEL_ANALYSIS_REPORT.md",
        "PARALLEL_RISK_ANALYSIS.md",
        "RACER_ANALYSIS_REPORT.md",
        "REAL_BOTTLENECK_ANALYSIS.md",
        "REORGANIZATION_SUMMARY.md",
        "SPEED_COMPARISON.md",

        # FEATURE系
        "FEATURE_COMPARISON.md",
        "FEATURE_DESIGN.md",

        # SUMMARY/その他
        "SUMMARY_V3_FIX.md",
        "FIXES_APPLIED.md",
    ],

    "archive_quickstart_duplicates": [
        # QUICK_START系
        "QUICK_START.md",
        "QUICK_START_GUIDE.md",
        "README_QUICK_START.md",
        "NEXT_SESSION_QUICKSTART.md",

        # DATA_COLLECTION系
        "DATA_COLLECTION_GUIDE.md",
        "DATA_FILLING_GUIDE.md",
        "COMPREHENSIVE_DATA_COLLECTION_README.md",
        "DAILY_COLLECTION_SETUP.md",
    ],

    "archive_experiments": [
        # 実験レポート
        "EXPERIMENT_004_REPORT.md",
        "EXPERIMENT_005_REPORT.md",
        "EXPERIMENT_006_REPORT.md",
        "EXPERIMENT_007_REPORT.md",
        "EXPERIMENT_009B_REPORT.md",
        "EXPERIMENTS_FINAL_REPORT.md",
        "EXPERIMENTS_SUMMARY_REPORT.md",
    ],

    "archive_old_guides": [
        # 古いステータスレポート
        "PROJECT_STATUS_AND_NEXT_STEPS.md",
        "SYSTEM_OVERVIEW_FINAL.md",

        # 古いガイド
        "ALTERNATIVE_DATA_SOURCES.md",
        "DATA_RETENTION_DISCOVERY.md",
        "DOWNLOAD_SOLUTION_SUMMARY.md",

        # 古い仕様書
        "RACER_ANALYSIS_DESIGN.md",
        "API_STRUCTURE.md",
        "REFERENCE_SITES_ANALYSIS.md",
        "database_migration_strategy.md",
        "dual_pc_setup.md",

        # その他
        "RESTART_HANDOVER.md",
        "IMPORTANT_KNOW_HOW.md",
        "CLEANUP_PLAN_20251118.md",
        "CLEANUP_REPORT.md",
        "BOTTLENECK_ANALYSIS_AND_IMPROVEMENTS.md",
        "DEPLOYMENT_PLAN_V3.md",
    ],
}

# docs/内のファイル
DOCS_FILES_TO_MOVE: Dict[str, List[str]] = {
    "archive_2025_11_work_logs": [
        "work_summary_20251117.md",
        "work_summary_20251118.md",
        "work_summary_20251119.md",
        "work_summary_20251125.md",
        "20251125_作業ログ.md",
        "model_bias_analysis_20251118.md",
        "technical_insights_20251119.md",
        "プロジェクト全体レビュー_20251118.md",
    ],

    "archive_old_reports": [
        "IMPLEMENTATION_SUMMARY.md",
        "COMPLETION_REPORT.md",
        "TEST_RESULTS.md",
    ],

    "archive_old_guides": [
        "odds_scraping_guide.md",
        "kimarite_prediction_system.md",
        "model_experiments.md",
        "PREDICTION_LOGIC_INSIGHTS.md",
        "VENUE_RACER_CHARACTERISTICS.md",
        "reprediction_setup_guide.md",
        "ui_improvements_guide.md",
        "README.md",  # docs/README.mdは古い
    ],
}


def move_files(files_dict: Dict[str, List[str]], base_dir: Path, archive_base: Path, dry_run=True):
    """ファイルを移動する"""
    moved_count = 0
    not_found = []

    for target_dir, file_list in files_dict.items():
        target_path = archive_base / target_dir

        print(f"\n{'='*80}")
        print(f"移動先: {target_path}")
        print(f"{'='*80}")

        for filename in file_list:
            # パターンマッチング対応
            if "*" in filename:
                import glob
                pattern = str(base_dir / filename)
                matched_files = glob.glob(pattern)

                for matched_file in matched_files:
                    matched_filename = Path(matched_file).name
                    source = Path(matched_file)
                    dest = target_path / matched_filename

                    if source.exists():
                        if dry_run:
                            print(f"[DRY RUN] {matched_filename} → {target_dir}/")
                        else:
                            shutil.move(str(source), str(dest))
                            print(f"[MOVED] {matched_filename} → {target_dir}/")
                        moved_count += 1
            else:
                source = base_dir / filename
                dest = target_path / filename

                if source.exists():
                    if dry_run:
                        print(f"[DRY RUN] {filename} → {target_dir}/")
                    else:
                        shutil.move(str(source), str(dest))
                        print(f"[MOVED] {filename} → {target_dir}/")
                    moved_count += 1
                else:
                    not_found.append(filename)
                    # print(f"[NOT FOUND] {filename}")  # 見つからないファイルは表示しない

    return moved_count, not_found


def count_docs():
    """現在のドキュメント数を数える"""
    root_count = len(list(BASE_DIR.glob("*.md")))
    docs_count = len(list(DOCS_DIR.glob("*.md")))
    archive_count = len(list(DOCS_ARCHIVE_DIR.glob("**/*.md")))

    print(f"\nドキュメント数:")
    print(f"  ルート: {root_count}個")
    print(f"  docs/: {docs_count}個")
    print(f"  docs/archive/: {archive_count}個")
    print(f"  合計: {root_count + docs_count + archive_count}個")

    return root_count, docs_count, archive_count


if __name__ == "__main__":
    import sys

    print("="*80)
    print("ドキュメント整理ツール")
    print("="*80)

    # 整理前のカウント
    print("\n[整理前]")
    count_docs()

    # ドライランモード
    if "--dry-run" in sys.argv or len(sys.argv) == 1:
        print("\n" + "="*80)
        print("DRY RUNモード（実際の移動は行いません）")
        print("実際に移動するには: python cleanup_docs.py --execute")
        print("="*80)

        print("\n【ルートディレクトリのMDファイル】")
        root_moved, root_not_found = move_files(ROOT_FILES_TO_MOVE, BASE_DIR, DOCS_ARCHIVE_DIR, dry_run=True)

        print("\n【docs/ディレクトリのMDファイル】")
        docs_moved, docs_not_found = move_files(DOCS_FILES_TO_MOVE, DOCS_DIR, DOCS_ARCHIVE_DIR, dry_run=True)

        print(f"\n{'='*80}")
        print(f"サマリー")
        print(f"{'='*80}")
        print(f"ルート移動対象: {root_moved}個")
        print(f"docs/移動対象: {docs_moved}個")
        print(f"合計: {root_moved + docs_moved}個")

    # 実行モード
    elif "--execute" in sys.argv:
        print("\n" + "="*80)
        print("実行モード（ファイルを実際に移動します）")
        print("="*80)

        # 確認
        response = input("\n本当に実行しますか？ (yes/no): ")
        if response.lower() == "yes":
            print("\n【ルートディレクトリのMDファイル】")
            root_moved, root_not_found = move_files(ROOT_FILES_TO_MOVE, BASE_DIR, DOCS_ARCHIVE_DIR, dry_run=False)

            print("\n【docs/ディレクトリのMDファイル】")
            docs_moved, docs_not_found = move_files(DOCS_FILES_TO_MOVE, DOCS_DIR, DOCS_ARCHIVE_DIR, dry_run=False)

            print(f"\n{'='*80}")
            print(f"サマリー")
            print(f"{'='*80}")
            print(f"ルート移動完了: {root_moved}個")
            print(f"docs/移動完了: {docs_moved}個")
            print(f"合計: {root_moved + docs_moved}個")

            # 整理後のカウント
            print("\n[整理後]")
            count_docs()
        else:
            print("キャンセルしました")

    else:
        print("使い方:")
        print("  python cleanup_docs.py              # ドライラン")
        print("  python cleanup_docs.py --dry-run    # ドライラン")
        print("  python cleanup_docs.py --execute    # 実行")
