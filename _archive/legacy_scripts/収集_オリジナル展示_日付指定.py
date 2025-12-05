#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
オリジナル展示データ収集（日付指定版）

UIからの実行を想定したシンプルなインターフェース

【重要】データ利用可能期間について:
  オリジナル展示データは「昨日」と「今日」のみ公開されています。
  2日前以前のデータは自動的に削除されるため、取得できません。

実行方法:
  python 収集_オリジナル展示_日付指定.py 2025-11-18        # 単一日
  python 収集_オリジナル展示_日付指定.py 2025-11-18 2025-11-19  # 日付範囲（昨日〜今日のみ推奨）
"""
import sys
sys.path.append('src')

import sqlite3
import subprocess
from datetime import datetime, timedelta
from scraper.original_tenji_browser import OriginalTenjiBrowserScraper
from tqdm import tqdm
import time

def collect_original_tenji_for_date(date_str):
    """
    指定日のオリジナル展示データを収集

    Args:
        date_str: 日付文字列 (YYYY-MM-DD)

    Returns:
        dict: 収集結果
    """
    print("="*80)
    print(f"オリジナル展示データ収集: {date_str}")
    print("="*80)

    # 日付の妥当性チェック（昨日〜今日のみ推奨）
    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    target_date_only = target_date.date()

    if target_date_only < yesterday - timedelta(days=1):
        print(f"\n[警告] {date_str} は2日前以前の日付です")
        print("オリジナル展示データは「昨日」と「今日」のみ公開されています。")
        print("古いデータは公式サイトから既に削除されている可能性が高いです。")
        print("\n収集を試みますが、データが取得できない可能性があります。\n")

    # DBから対象日のレースを取得
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # レース情報取得
    cursor.execute("""
        SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number, v.name
        FROM races r
        JOIN venues v ON r.venue_code = v.code
        WHERE r.race_date = ?
        ORDER BY r.venue_code, r.race_number
    """, (date_str,))

    races = cursor.fetchall()

    print(f"\n対象レース数: {len(races)}レース")

    if len(races) == 0:
        print(f"\n[INFO] {date_str} のレースデータがありません")
        print("レース基本データを収集しますか？")
        conn.close()
        return {
            'status': 'no_races',
            'message': 'レースデータが未登録です',
            'success': 0,
            'no_data': 0,
            'error': 0
        }

    # race_detailsの存在確認
    print("race_detailsレコードを確認中...")
    cursor.execute("""
        SELECT COUNT(*) FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        WHERE r.race_date = ?
    """, (date_str,))
    details_count = cursor.fetchone()[0]

    if details_count == 0:
        print(f"\n[INFO] {date_str} のrace_detailsレコードが0件です")
        print("race_detailsを作成します...\n")

        conn.close()

        # race_details作成（高速版）
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
                print(f"[WARNING] race_details作成でエラーが発生しましたが、処理を続行します\n")

        except Exception as e:
            print(f"[WARNING] race_details作成でエラー: {e}\n")

        # DB再接続
        conn = sqlite3.connect('data/boatrace.db')
        cursor = conn.cursor()

        # race_details再確認
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

    print("オリジナル展示収集を開始します...\n")

    for race_id, venue_code, race_date, race_number, venue_name in tqdm(races, desc="オリジナル展示収集"):
        try:
            # race_detailsレコードの存在確認
            cursor.execute("""
                SELECT COUNT(*) FROM race_details
                WHERE race_id = ?
            """, (race_id,))

            if cursor.fetchone()[0] == 0:
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
            else:
                error_count += 1

    scraper.close()

    # 収集結果
    print("\n" + "="*80)
    print("収集完了")
    print("="*80)
    print(f"成功: {success_count}レース")
    print(f"データなし: {no_data_count}レース")
    print(f"404エラー: {not_found_count}レース")
    print(f"タイムアウト: {timeout_count}レース")
    print(f"その他エラー: {error_count}レース")

    total = success_count + no_data_count + not_found_count + error_count + timeout_count
    if total > 0:
        print(f"成功率: {success_count/total*100:.1f}%")

    # 保存されたデータを確認
    if success_count > 0:
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
            print(f"\n【{date_str}の保存データ】")
            print(f"  総艇数: {total_boats}艇")
            print(f"  直線タイム: {with_chikusen}艇 ({with_chikusen/total_boats*100:.1f}%)")
            print(f"  1周タイム: {with_isshu}艇 ({with_isshu/total_boats*100:.1f}%)")
            print(f"  回り足タイム: {with_mawariashi}艇 ({with_mawariashi/total_boats*100:.1f}%)")

    conn.close()
    print("\n" + "="*80)

    return {
        'status': 'completed',
        'date': date_str,
        'success': success_count,
        'no_data': no_data_count,
        'not_found': not_found_count,
        'timeout': timeout_count,
        'error': error_count
    }


def main():
    if len(sys.argv) < 2:
        print("使用方法: python 収集_オリジナル展示_日付指定.py [日付]")
        print("例: python 収集_オリジナル展示_日付指定.py 2025-11-18")
        print("    python 収集_オリジナル展示_日付指定.py 2025-11-01 2025-11-30")
        sys.exit(1)

    start_date_str = sys.argv[1]

    if len(sys.argv) >= 3:
        end_date_str = sys.argv[2]
        # 複数日の場合
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

        current_date = start_date
        all_results = []

        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            result = collect_original_tenji_for_date(date_str)
            all_results.append(result)

            current_date += timedelta(days=1)

            if current_date <= end_date:
                print("\n次の日付に進みます...\n")
                time.sleep(2)

        # 全体のサマリー
        print("\n" + "="*80)
        print("全期間の収集結果")
        print("="*80)
        total_success = sum(r['success'] for r in all_results)
        total_no_data = sum(r['no_data'] for r in all_results)
        total_error = sum(r.get('error', 0) + r.get('not_found', 0) + r.get('timeout', 0) for r in all_results)

        print(f"成功: {total_success}レース")
        print(f"データなし: {total_no_data}レース")
        print(f"エラー: {total_error}レース")
        print("="*80)

    else:
        # 1日だけの場合
        result = collect_original_tenji_for_date(start_date_str)


if __name__ == "__main__":
    main()
