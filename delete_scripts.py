"""
不要スクリプト削除ツール
CLEANUP_REPORT.mdに基づいて不要なファイルを削除
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import shutil

# 削除対象ファイルリスト
DELETE_FILES = [
    # テスト・デバッグスクリプト
    'test_2020_data_availability.py',
    'test_data_fetchers.py',
    'test_db_sync.py',
    'test_environment.py',
    'test_exhibition_save.py',
    'test_exhibition_time_save.py',
    'test_kimarite_fast.py',
    'test_kimarite_v2.py',
    'test_ml_system.py',
    'test_parser_format_detection.py',
    'test_parser_with_sample.py',
    'test_rdmdb_access.py',
    'test_rdmdb_collection.py',
    'test_rdmdb_download.py',
    'test_rdmdb_parser_3files.py',
    'test_rdmdb_parser_single.py',
    'test_rdmdb_search.py',
    'test_rule_integration.py',
    'test_single_failing_file.py',
    'test_single_race_v5.py',
    'test_two_phase_save.py',
    'test_ui_integration.py',
    'test_v4_quick.py',
    'test_wind_direction.py',
    'test_wind_extraction.py',
    'test_収集_RDMDB潮位_単一.py',
    'test_新URL_1ファイル.py',
    'test_結果イベント抽出.py',
    'test_結果イベント抽出v2.py',
    'test_結果イベント抽出v3.py',
    'test_補完_決まり手_単一.py',

    # デバッグスクリプト
    'debug_checkbox_ids.py',
    'debug_failed_hiroshima.py',
    'debug_hiroshima_detailed.py',
    'debug_racer_query.py',
    'debug_rdmdb_options.py',
    'debug_rdmdb_parser.py',
    'debug_result_page_exhibition.py',
    'debug_tide_extraction.py',
    'debug_tide_html.py',
    'debug_wind_html.py',

    # 旧バージョン
    '補完_決まり手データ.py',
    '補完_決まり手データ_高速版.py',
    '補完_結果データ.py',
    '補完_レース詳細データ.py',
    '補完_レース詳細データ_改善版.py',
    '補完_レース詳細データ_改善版v2.py',
    '補完_レース詳細データ_改善版v3.py',
    '補完_天候データ取得.py',
    '収集_RDMDB潮位データ.py',
    '収集_RDMDB潮位データ_単一.py',
    '収集_RDMDB潮位データ_新URL対応.py',
    'fetch_parallel_v4.py',
    'fetch_parallel_v5.py',
    'fetch_parallel_v5_fixed.py',
    'analyze_demei_probability.py',
    'analyze_demei_probability_fixed.py',
    'analyze_prediction_patterns.py',
    'analyze_prediction_patterns_fixed.py',
    'comprehensive_bug_check.py',
    'comprehensive_bug_check_fixed.py',
    'check_coverage_fixed.py',

    # 一時的な調査スクリプト
    'extract_all_boats_tilt.py',
    'extract_exhibition_table3.py',
    'extract_first_row_html.py',
    'extract_start_info_html.py',
    'extract_start_table.py',
    'find_all_start_tables.py',
    'find_all_tbodies.py',
    'find_exhibition_time.py',
    'find_rdmdb_new_url.py',
    'count_tbody_rows.py',
    'investigate_exhibition_details.py',
    'investigate_jcg_tide.py',
    'investigate_rdmdb_flow.py',
    'investigate_schedule.py',
    'investigate_tide_url.py',
    'analyze_endpoints.py',
    'analyze_further_optimization.py',
    'analyze_payout_data.py',
    'analyze_schedule_structure.py',
    'analyze_st_time.py',
    'analyze_tilt_structure.py',
    'analyze_v4_speed.py',
    'analyze_venue_patterns.py',
    'analyze_wakamatsu.py',
    'check_2023_data.py',
    'check_data_completeness.py',
    'check_data_coverage_detail.py',
    'check_data_gaps.py',
    'check_data_integrity.py',
    'check_exhibition_coverage.py',
    'check_exhibition_time_html.py',
    'check_latest_wind_data.py',
    'check_logs.py',
    'check_missing_data.py',
    'check_missing_weather.py',
    'check_new_rdmdb_url.py',
    'check_rdmdb_page.py',
    'check_tide_coverage.py',
    'check_tide_data.py',
    'check_v5_data_quality.py',
    '30日確認.py',

    # マイグレーション・初期化スクリプト
    'migrate_rank_column.py',
    'migrate_add_weather_columns.py',
    'migrate_add_race_details.py',
    'migrate_add_payouts_table.py',
    'migrate_add_kimarite_column.py',
    'migrate_add_winning_technique.py',
    'register_all_venues.py',
    'register_wakamatsu_rules.py',
    'register_top_racer_rules.py',
    'create_racer_rules_table.py',
    'create_rules_table.py',
    'create_test_db.py',
    'add_weather_columns.py',
    'add_payout_methods.py',
    'add_rule_validation_tab.py',

    # 廃止された機能
    'train_model.py',
    'uiapp.py',
    'continuous_auto_collect.py',
    'auto_collect_next_month.py',
    'merge_databases.py',
    'convert_to_readonly_db.py',
    'enable_wal_mode.py',
    'fix_pyarrow.py',
    'fix_tabs.py',
    'create_package.py',

    # 再処理・バックフィル
    '再パース_RDMDB潮位_既存ファイル.py',
    '再パース_Hiroshima_2ファイル.py',
    '再収集_RDMDB潮位_10ファイルテスト.py',
    '削除_結果イベント_tide直行.py',
    '削除_結果イベント_追加3候補.py',
    '補完_決まり手_全件.py',
    '補完_決まり手_全件_並列.py',
    '補完_決まり手_全件_並列後.py',
    '補完_過去天候データ.py',
    'fill_weather_data.py',
    'fetch_missing_race_details.py',
    'fetch_missing_weather.py',
    'fetch_historical_data_bulk.py',
    'update_results_table.py',
    '過去データ一括取得_並列版.py',

    # サンプル・ダウンロード
    'download_rdmdb_sample.py',
    'save_result_html.py',
    '解凍_RDMDB潮位ZIP.py',
]

def delete_files(base_dir):
    """ファイルを削除"""
    deleted = []
    not_found = []
    errors = []

    print(f"削除対象: {len(DELETE_FILES)}ファイル\n")

    for filename in DELETE_FILES:
        filepath = os.path.join(base_dir, filename)

        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                deleted.append(filename)
                print(f"✓ 削除: {filename}")
            except Exception as e:
                errors.append((filename, str(e)))
                print(f"✗ エラー: {filename} - {e}")
        else:
            not_found.append(filename)

    print(f"\n{'='*80}")
    print("削除完了レポート")
    print(f"{'='*80}")
    print(f"削除成功: {len(deleted)}ファイル")
    print(f"存在せず: {len(not_found)}ファイル")
    print(f"エラー: {len(errors)}ファイル")

    if not_found:
        print(f"\n存在しなかったファイル:")
        for f in not_found[:10]:
            print(f"  - {f}")
        if len(not_found) > 10:
            print(f"  ... 他{len(not_found)-10}ファイル")

    if errors:
        print(f"\nエラーが発生したファイル:")
        for f, e in errors:
            print(f"  - {f}: {e}")

    return len(deleted), len(not_found), len(errors)

if __name__ == "__main__":
    base_dir = r"C:\Users\seizo\Desktop\BoatRace"

    print("="*80)
    print("不要スクリプト削除ツール")
    print("="*80)
    print(f"対象ディレクトリ: {base_dir}")
    print(f"バックアップ: C:\\Users\\seizo\\Desktop\\BoatRace_backup_20251102")
    print()

    deleted, not_found, errors = delete_files(base_dir)

    print(f"\n削除完了: {deleted}ファイルを削除しました")
