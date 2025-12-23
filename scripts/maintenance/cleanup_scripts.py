#!/usr/bin/env python3
"""
スクリプトファイル整理自動化スクリプト
PROJECT_CLEANUP_PLAN_20251210.mdに基づいてファイルを整理
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict

# ベースディレクトリ
BASE_DIR = Path(__file__).parent
SCRIPTS_DIR = BASE_DIR / "scripts"
SCRIPTS_ARCHIVE_DIR = BASE_DIR / "scripts_archive"

# 整理対象ファイルリスト
FILES_TO_MOVE: Dict[str, List[str]] = {
    "duplicate_archived": [
        # 空ファイル・特定月専用
        "generate_october_predictions.py",
        "generate_november_predictions.py",
        "compare_november_predictions.py",
        "backtest_november_strategy.py",
        "november_backtest_detailed.py",
        "november_backtest_ui_strategy.py",

        # 最終戦略重複
        "backtest_final_strategy.py",
        "backtest_final_strategy_historical.py",

        # イン強会場重複
        "backtest_high_in_venues_no_filter.py",

        # 信頼度B重複
        "analyze_confidence_b.py",
        "analyze_confidence_b_comprehensive.py",
        "analyze_confidence_b_detail.py",
        "analyze_confidence_b_from_csv.py",

        # 予測生成重複
        "generate_predictions_batch.py",
    ],

    "test_debug_archived": [
        # デバッグスクリプト
        "debug_final_strategy.py",
        "debug_high_in_venues.py",

        # テストスクリプト
        "test_evaluator.py",
        "test_flag_adjuster.py",
        "test_phase_integration.py",
        "test_confidence_specific_hybrid.py",
        "test_hybrid_scoring_confidence_b.py",
        "test_top3_scoring.py",
        "test_prediction_types.py",

        # クイックテスト
        "quick_test.py",
        "quick_test_hybrid.py",
        "quick_test_v2_model.py",

        # その他
        "migrate_prediction_unique_constraint.py",
        "night_auto_collection.py",
        "ev_bet_tool.py",
    ],

    "analyze_archived": [
        # 信頼度B関連
        "check_confidence_b.py",
        "show_confidence_b_summary.py",
        "analyze_confidence_c_conditions.py",
        "analyze_confidence_issues.py",
        "confidence_c_conditions.py",

        # BEFORE情報関連
        "analyze_before_element_correlation.py",
        "analyze_before_rank_bonus.py",
        "analyze_beforeinfo_comprehensive.py",
        "analyze_beforeinfo_correlation.py",
        "analyze_beforeinfo_correlation_lite.py",
        "check_beforeinfo_status.py",
        "analyze_pre_before_correlation.py",
        "validate_before_patterns.py",

        # パターン抽出
        "extract_before_patterns.py",
        "extract_2nd_3rd_presets.py",
        "extract_environmental_presets.py",

        # 年度別・期間別
        "analyze_2024_performance.py",
        "analyze_2025_fast.py",
        "analyze_2025_full_year.py",
        "analyze_2025_with_bet_filter.py",
        "monthly_performance_analysis.py",
        "analyze_monthly_and_confidence_b.py",
        "analyze_changed_races.py",

        # その他分析
        "analyze_all_confidence_levels.py",
        "analyze_entry_change_impact.py",
        "analyze_hit_races.py",
        "analyze_pattern_application.py",
        "analyze_phases_detail.py",
        "analyze_rank23_accuracy.py",
        "analyze_top3_coverage.py",
        "analyze_venue_patterns.py",
        "check_db_basic.py",
        "check_db_structure.py",
        "compare_before_after_hybrid.py",
        "compare_prediction_methods.py",
        "compare_strategy_vs_current.py",
        "discover_high_roi_conditions.py",
        "evaluate_conditional_v1_comprehensive.py",
        "evaluate_top3_scoring_confidence_b.py",
        "evaluate_unused_6_conditions.py",
        "evaluate_v2_performance.py",
        "find_improvement_opportunities.py",
        "quick_condition_scan.py",
        "verify_st_correlation.py",
        "validate_flag_adjustment.py",
        "validate_gated_integration.py",
        "validate_hierarchical_prediction.py",
        "validate_normalized_integration.py",
        "validate_stage2_training_data.py",
        "clean_hybrid_evaluation.py",
        "comprehensive_hybrid_evaluation.py",
        "backup_old_predictions.py",
        "comprehensive_strategy_analysis.py",
    ],

    "backtest_archived": [
        # 古いバックテスト
        "backtest_combined_strategy.py",
        "backtest_exacta_only_optimized.py",
        "backtest_exacta_optimized.py",
        "backtest_integrated_strategy.py",
        "backtest_multi_month.py",
        "backtest_optimized_v2.py",
        "backtest_strategy.py",
        "backtest_v1_moderate.py",
        "backtest_conditional_models_v2.py",
        "comprehensive_backtest_correct.py",
        "comprehensive_backtest_v1_v2.py",
    ],
}


def move_files(dry_run=True):
    """ファイルを移動する"""
    moved_count = 0
    not_found = []

    for target_dir, file_list in FILES_TO_MOVE.items():
        target_path = SCRIPTS_ARCHIVE_DIR / target_dir

        print(f"\n{'='*80}")
        print(f"移動先: {target_path}")
        print(f"{'='*80}")

        for filename in file_list:
            source = SCRIPTS_DIR / filename
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
                print(f"[NOT FOUND] {filename}")

    print(f"\n{'='*80}")
    print(f"サマリー")
    print(f"{'='*80}")
    print(f"移動対象ファイル: {sum(len(files) for files in FILES_TO_MOVE.values())}個")
    print(f"移動完了: {moved_count}個")
    print(f"見つからなかった: {len(not_found)}個")

    if not_found:
        print(f"\n見つからなかったファイル:")
        for filename in not_found:
            print(f"  - {filename}")

    return moved_count, not_found


def count_scripts():
    """現在のスクリプト数を数える"""
    scripts_count = len(list(SCRIPTS_DIR.glob("*.py")))
    archive_count = sum(len(list((SCRIPTS_ARCHIVE_DIR / d).glob("*.py")))
                       for d in ["analyze_archived", "backtest_archived",
                                 "test_debug_archived", "duplicate_archived"])

    print(f"\nスクリプト数:")
    print(f"  scripts/: {scripts_count}個")
    print(f"  scripts_archive/: {archive_count}個")
    print(f"  合計: {scripts_count + archive_count}個")

    return scripts_count, archive_count


if __name__ == "__main__":
    import sys

    print("="*80)
    print("スクリプト整理ツール")
    print("="*80)

    # 整理前のカウント
    print("\n[整理前]")
    count_scripts()

    # ドライランモード
    if "--dry-run" in sys.argv or len(sys.argv) == 1:
        print("\n" + "="*80)
        print("DRY RUNモード（実際の移動は行いません）")
        print("実際に移動するには: python cleanup_scripts.py --execute")
        print("="*80)
        move_files(dry_run=True)

    # 実行モード
    elif "--execute" in sys.argv:
        print("\n" + "="*80)
        print("実行モード（ファイルを実際に移動します）")
        print("="*80)

        # 確認
        response = input("\n本当に実行しますか？ (yes/no): ")
        if response.lower() == "yes":
            move_files(dry_run=False)

            # 整理後のカウント
            print("\n[整理後]")
            count_scripts()
        else:
            print("キャンセルしました")

    else:
        print("使い方:")
        print("  python cleanup_scripts.py              # ドライラン")
        print("  python cleanup_scripts.py --dry-run    # ドライラン")
        print("  python cleanup_scripts.py --execute    # 実行")
