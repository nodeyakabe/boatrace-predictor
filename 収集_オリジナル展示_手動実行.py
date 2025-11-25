"""
オリジナル展示データ収集（手動実行用）

実行方法:
  python 収集_オリジナル展示_手動実行.py [days_offset]

  days_offset: 今日を基準とした日数オフセット（デフォルト: 0=今日）
    例: python 収集_オリジナル展示_手動実行.py 0   # 今日のデータ
        python 収集_オリジナル展示_手動実行.py 1   # 明日のデータ
        python 収集_オリジナル展示_手動実行.py -1  # 昨日のデータ
"""
import sys
sys.path.append('src')

import sqlite3
import subprocess
from datetime import datetime, timedelta
from scraper.original_tenji_browser import OriginalTenjiBrowserScraper
from tqdm import tqdm
import time

print("="*80)
print("オリジナル展示データ収集（手動実行）")
print("="*80)

# コマンドライン引数から日数オフセットを取得
days_offset = int(sys.argv[1]) if len(sys.argv) > 1 else 0

# 現在の日付を基準
base_date = datetime.now()
target_date = base_date + timedelta(days=days_offset)
date_str = target_date.strftime('%Y-%m-%d')

print(f"\n収集対象日: {date_str}")
if days_offset == 0:
    print("  (今日)")
elif days_offset == 1:
    print("  (明日)")
elif days_offset == -1:
    print("  (昨日)")
else:
    print(f"  (今日{days_offset:+d}日)")

# DBから対象日のレースを取得
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number, v.name
    FROM races r
    JOIN venues v ON r.venue_code = v.code
    WHERE r.race_date = ?
    ORDER BY r.venue_code, r.race_number
""", (date_str,))

races = cursor.fetchall()

print(f"\n対象レース数: {len(races)}レース")

# レース情報がない、またはrace_detailsが不足している場合は自動収集
needs_fetch = False

if len(races) == 0:
    print("\n[INFO] レースデータが未登録です")
    needs_fetch = True
else:
    # race_detailsレコードの存在確認
    print("race_detailsレコードを確認中...")
    cursor.execute("""
        SELECT COUNT(*) FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        WHERE r.race_date = ?
    """, (date_str,))
    details_count = cursor.fetchone()[0]

    if details_count == 0:
        print(f"\n[INFO] {date_str} のrace_detailsレコードが0件です")
        needs_fetch = True
    else:
        print(f"race_detailsレコード: {details_count}件\n")

# レースデータ収集が必要な場合
if needs_fetch:
    print("\n" + "="*80)
    print("レースデータを自動収集します")
    print("="*80)
    print(f"対象日: {date_str}")
    print()

    conn.close()  # 一時的にDB接続を閉じる

    # ステップ1: racesテーブル作成
    print(f"ステップ1: レース基本データ収集")
    print(f"実行: python fetch_historical_data.py --start-date {date_str} --end-date {date_str} --workers 4\n")

    try:
        result = subprocess.run(
            [sys.executable, "fetch_historical_data.py",
             "--start-date", date_str,
             "--end-date", date_str,
             "--workers", "4"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        if result.returncode == 0:
            print("[OK] レース基本データ収集完了\n")
        else:
            print(f"[ERROR] レース基本データ収集失敗")
            print(f"終了コード: {result.returncode}")
            if result.stderr:
                print(f"エラー出力:\n{result.stderr}")
            sys.exit(1)

    except Exception as e:
        print(f"[ERROR] レース基本データ収集でエラーが発生: {e}")
        sys.exit(1)

    # ステップ2: race_details作成（高速版）
    print(f"ステップ2: race_details作成（高速版）")
    print(f"実行: python 補完_race_details_INSERT対応_高速版.py {date_str} {date_str}\n")

    try:
        result = subprocess.run(
            [sys.executable, "補完_race_details_INSERT対応_高速版.py",
             date_str, date_str],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        if result.returncode == 0:
            print("[OK] race_details作成完了\n")
        else:
            print(f"[WARNING] race_details作成でエラーが発生しましたが、処理を続行します")
            print(f"終了コード: {result.returncode}\n")

    except Exception as e:
        print(f"[WARNING] race_details作成でエラーが発生: {e}")
        print("処理を続行します\n")

    # DBに再接続してレース情報を再取得
    print("\n" + "="*80)
    print("収集後のレース情報を確認")
    print("="*80)

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number, v.name
        FROM races r
        JOIN venues v ON r.venue_code = v.code
        WHERE r.race_date = ?
        ORDER BY r.venue_code, r.race_number
    """, (date_str,))

    races = cursor.fetchall()
    print(f"対象レース数: {len(races)}レース")

    if len(races) == 0:
        print(f"\n[ERROR] {date_str} のレースデータが収集できませんでした")
        print("この日は開催がなかった可能性があります")
        conn.close()
        sys.exit(0)

    # race_details確認
    cursor.execute("""
        SELECT COUNT(*) FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        WHERE r.race_date = ?
    """, (date_str,))
    details_count = cursor.fetchone()[0]
    print(f"race_detailsレコード: {details_count}件\n")

# オリジナル展示データを収集
scraper = OriginalTenjiBrowserScraper(headless=True, timeout=30)
success_count = 0
no_data_count = 0
error_count = 0
not_found_count = 0
timeout_count = 0
no_details_count = 0

for race_id, venue_code, race_date, race_number, venue_name in tqdm(races, desc="オリジナル展示収集"):
    try:
        # race_detailsレコードの存在確認
        cursor.execute("""
            SELECT COUNT(*) FROM race_details
            WHERE race_id = ?
        """, (race_id,))

        if cursor.fetchone()[0] == 0:
            no_details_count += 1
            continue

        # オリジナル展示データを取得
        tenji_data = scraper.get_original_tenji(venue_code, race_date, race_number)

        if tenji_data:
            # 各艇のデータを更新
            updated = 0
            for boat_num, data in tenji_data.items():
                chikusen = data.get('chikusen_time')
                isshu = data.get('isshu_time')
                mawariashi = data.get('mawariashi_time')

                if chikusen is not None or isshu is not None or mawariashi is not None:
                    result = cursor.execute("""
                        UPDATE race_details
                        SET chikusen_time = COALESCE(?, chikusen_time),
                            isshu_time = COALESCE(?, isshu_time),
                            mawariashi_time = COALESCE(?, mawariashi_time)
                        WHERE race_id = ? AND pit_number = ?
                    """, (chikusen, isshu, mawariashi, race_id, boat_num))

                    if result.rowcount > 0:
                        updated += 1

            if updated > 0:
                conn.commit()
                success_count += 1
            else:
                no_data_count += 1
        else:
            no_data_count += 1

        # レート制限対策
        time.sleep(1.0)

    except Exception as e:
        error_str = str(e)
        if '404' in error_str or 'Not Found' in error_str:
            not_found_count += 1
        elif 'timeout' in error_str.lower() or 'timed out' in error_str.lower():
            timeout_count += 1
            print(f"\n[タイムアウト] ({venue_name}, R{race_number})")
        else:
            error_count += 1
            print(f"\n[エラー] ({venue_name}, R{race_number}): {e}")

scraper.close()

# 収集結果をレポート
print("\n" + "="*80)
print("収集完了")
print("="*80)
print(f"成功: {success_count}レース")
print(f"データなし: {no_data_count}レース")
print(f"404エラー: {not_found_count}レース")
print(f"タイムアウト: {timeout_count}レース")
print(f"race_details未登録: {no_details_count}レース")
print(f"その他エラー: {error_count}レース")
total = success_count + no_data_count + not_found_count + error_count + timeout_count + no_details_count
if total > 0:
    print(f"成功率: {success_count/total*100:.1f}%")

# 保存されたデータを確認
if success_count > 0:
    print("\n" + "="*80)
    print("保存データ確認")
    print("="*80)

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN rd.chikusen_time IS NOT NULL THEN 1 END) as with_chikusen,
            COUNT(CASE WHEN rd.isshu_time IS NOT NULL THEN 1 END) as with_isshu,
            COUNT(CASE WHEN rd.mawariashi_time IS NOT NULL THEN 1 END) as with_mawariashi
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        WHERE r.race_date = ?
    """, (date_str,))

    row = cursor.fetchone()
    total_boats, with_chikusen, with_isshu, with_mawariashi = row

    if total_boats > 0:
        print(f"\n{date_str}:")
        print(f"  総艇数: {total_boats}艇")
        print(f"  直線タイム: {with_chikusen}艇 ({with_chikusen/total_boats*100:.1f}%)")
        print(f"  1周タイム: {with_isshu}艇 ({with_isshu/total_boats*100:.1f}%)")
        print(f"  回り足タイム: {with_mawariashi}艇 ({with_mawariashi/total_boats*100:.1f}%)")

# 公開範囲に関する情報
if not_found_count > 0 and success_count == 0:
    print("\n" + "="*80)
    print("ヒント: データ公開範囲について")
    print("="*80)
    print("すべてのレースが404エラーになりました。")
    print("オリジナル展示データは限られた期間のみ公開されている可能性があります。")
    print("\n試してみてください:")
    print("  python 収集_オリジナル展示_手動実行.py -1  # 昨日")
    print("  python 収集_オリジナル展示_手動実行.py 0   # 今日")
    print("  python 収集_オリジナル展示_手動実行.py 1   # 明日")

conn.close()
print("\n" + "="*80)
