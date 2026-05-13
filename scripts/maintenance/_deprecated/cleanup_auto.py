"""
不要ファイル自動削除スクリプト（確認なし）
"""
import os
import shutil

def format_size(size_bytes):
    """バイトをMB/GBに変換"""
    if size_bytes >= 1024**3:
        return f"{size_bytes / (1024**3):.2f}GB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / (1024**2):.2f}MB"
    else:
        return f"{size_bytes / 1024:.2f}KB"

def delete_directory(path, name):
    """ディレクトリを削除"""
    if os.path.exists(path):
        try:
            # サイズを計算
            total_size = sum(
                os.path.getsize(os.path.join(dirpath, filename))
                for dirpath, dirnames, filenames in os.walk(path)
                for filename in filenames
            )
            shutil.rmtree(path)
            print(f"  [OK] {name}削除完了 ({format_size(total_size)})")
            return total_size
        except Exception as e:
            print(f"  [ERROR] {name}削除失敗: {e}")
            return 0
    else:
        print(f"  [SKIP] {name}は既に削除済み")
        return 0

def delete_file(path, name):
    """ファイルを削除"""
    if os.path.exists(path):
        try:
            size = os.path.getsize(path)
            os.remove(path)
            print(f"  [OK] {name}削除完了 ({format_size(size)})")
            return size
        except Exception as e:
            print(f"  [ERROR] {name}削除失敗: {e}")
            return 0
    else:
        return 0

def main():
    print("=" * 80)
    print("不要ファイル削除開始")
    print("=" * 80)
    print()

    total_deleted = 0

    # 大容量ディレクトリの削除
    print("[1/4] 大容量ディレクトリを削除中...")
    total_deleted += delete_directory("受け渡し/temp_extract", "temp_extract")
    total_deleted += delete_directory("rdmdb_tide_data", "rdmdb_tide_data")
    total_deleted += delete_directory("backups/cleanup_20251210", "cleanup_20251210")
    total_deleted += delete_directory("temp", "temp")

    # ログファイルの削除
    print()
    print("[2/4] ログファイルを削除中...")
    total_deleted += delete_file("backtest_output.txt", "backtest_output.txt")
    total_deleted += delete_file("conditional_v1_eval.txt", "conditional_v1_eval.txt")
    total_deleted += delete_file("top3_coverage.txt", "top3_coverage.txt")
    total_deleted += delete_file("v2_eval_output.txt", "v2_eval_output.txt")
    total_deleted += delete_file("log_oct_2024.txt", "log_oct_2024.txt")
    total_deleted += delete_file("cfc743_output.txt", "cfc743_output.txt")
    total_deleted += delete_file("error_traceback.txt", "error_traceback.txt")
    total_deleted += delete_file("output.txt", "output.txt")
    total_deleted += delete_file("output_weather_impact.txt", "output_weather_impact.txt")
    total_deleted += delete_file("output_weather_patterns.txt", "output_weather_patterns.txt")
    total_deleted += delete_file("nov_dec_analysis.txt", "nov_dec_analysis.txt")

    # HTMLファイルの削除
    print()
    print("[3/4] HTMLファイルを削除中...")

    # debug_odds_*.htmlを探して削除
    import glob
    for html_file in glob.glob("debug_odds_*.html"):
        total_deleted += delete_file(html_file, html_file)

    total_deleted += delete_file("page_source.html", "page_source.html")
    total_deleted += delete_file("exhibition_table3.html", "exhibition_table3.html")
    total_deleted += delete_file("jodc_top_page.html", "jodc_top_page.html")
    total_deleted += delete_file("race_schedule_page.html", "race_schedule_page.html")
    total_deleted += delete_file("rdmdb_download_page.html", "rdmdb_download_page.html")
    total_deleted += delete_file("rdmdb_new_page.html", "rdmdb_new_page.html")
    total_deleted += delete_file("monthly_schedule.html", "monthly_schedule.html")
    total_deleted += delete_file("first_row.html", "first_row.html")

    # その他のファイル
    print()
    print("[4/4] その他のファイルを削除中...")
    total_deleted += delete_file("archive_20251118_165053.zip", "archive_20251118_165053.zip")
    total_deleted += delete_file("missing_data_log.txt", "missing_data_log.txt")
    total_deleted += delete_file("missing_races.txt", "missing_races.txt")

    # 完了メッセージ
    print()
    print("=" * 80)
    print("削除完了")
    print("=" * 80)
    print(f"削減された容量: {format_size(total_deleted)}")
    print()

if __name__ == '__main__':
    main()
