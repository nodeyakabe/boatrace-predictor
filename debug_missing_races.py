"""
欠損レースのデバッグスクリプト
会場19（下関）10R と 会場22（福岡）6R が取得できなかった原因を調査
"""

import sys
import os

# Windows コンソールでのUnicodeエラー回避
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.race_scraper_v2 import RaceScraperV2
from src.scraper.base_scraper_v2 import BaseScraperV2
import sqlite3
from config.settings import DATABASE_PATH

def debug_scrape_race(venue_code, race_date, race_number):
    """
    個別レースのスクレイピングをデバッグ
    """
    print(f"\n{'='*60}")
    print(f"デバッグ: 会場{venue_code} {race_number}R (日付: {race_date})")
    print(f"{'='*60}")

    scraper = RaceScraperV2()

    try:
        # Step 1: ページ取得を試行
        print("\n[Step 1] ページ取得...")
        from config.settings import BOATRACE_OFFICIAL_URL
        url = f"{BOATRACE_OFFICIAL_URL}/racelist"
        params = {
            "rno": race_number,
            "jcd": venue_code,
            "hd": race_date
        }
        print(f"URL: {url}")
        print(f"パラメータ: {params}")

        tree = scraper.fetch_page(url, params)

        if not tree:
            print("❌ ページ取得失敗: fetch_page()がNoneを返しました")
            return None

        print("✅ ページ取得成功")

        # Step 2: レース時刻抽出
        print("\n[Step 2] レース時刻抽出...")
        race_time = scraper._extract_race_time(tree, race_number)
        print(f"レース時刻: {race_time}")

        # Step 3: レースグレード抽出
        print("\n[Step 3] レースグレード抽出...")
        race_grade = scraper._extract_race_grade(tree)
        print(f"レースグレード: {race_grade}")

        # Step 4: レース距離抽出
        print("\n[Step 4] レース距離抽出...")
        race_distance = scraper._extract_race_distance(tree)
        print(f"レース距離: {race_distance}m")

        # Step 5: 出走表テーブルパース
        print("\n[Step 5] 出走表テーブルパース...")

        # テーブル構造を確認
        table_div = tree.css_first("div.table1.is-tableFixed__3rdadd")
        if not table_div:
            print("❌ 出走表テーブル(div.table1.is-tableFixed__3rdadd)が見つかりません")

            # 他のテーブル要素を探す
            all_tables = tree.css("table")
            print(f"   ページ内のテーブル数: {len(all_tables)}")

            all_divs = tree.css("div.table1")
            print(f"   div.table1の数: {len(all_divs)}")

            # ページ内容の一部を表示
            body = tree.body
            if body:
                body_text = body.text(deep=True)[:500]
                print(f"\n   ページ内容の一部:\n{body_text}...")

            return None

        print("✅ 出走表テーブルが見つかりました")

        entries = scraper.parse_race_card_table(tree)

        if not entries:
            print("❌ 選手データが取得できませんでした")

            # tbodyを確認
            table = table_div.css_first("table")
            if table:
                tbodies = table.css("tbody.is-fs12")
                print(f"   tbody.is-fs12の数: {len(tbodies)}")

                if tbodies:
                    first_tbody = tbodies[0]
                    rows = first_tbody.css("tr")
                    print(f"   最初のtbodyのtr数: {len(rows)}")

                    if rows:
                        first_row = rows[0]
                        tds = first_row.css("td")
                        print(f"   最初のtrのtd数: {len(tds)}")

            return None

        print(f"✅ 選手データ取得成功: {len(entries)}名")

        # 選手情報を表示
        for entry in entries:
            pit = entry.get('pit_number', '?')
            name = entry.get('racer_name', '不明')
            number = entry.get('racer_number', '????')
            print(f"   {pit}号艇: {name} ({number})")

        # 完全なレースデータを構築
        race_data = {
            "venue_code": venue_code,
            "race_date": race_date,
            "race_number": race_number,
            "race_time": race_time,
            "race_grade": race_grade,
            "race_distance": race_distance,
            "entries": entries
        }

        print("\n✅ レースデータ取得完了")
        return race_data

    except Exception as e:
        import traceback
        print(f"\n❌ エラー発生: {e}")
        traceback.print_exc()
        return None
    finally:
        scraper.close()


def check_database_status():
    """
    データベースの現状を確認
    """
    print("\n" + "="*60)
    print("データベース状況確認")
    print("="*60)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 今日の日付
    today = "2025-11-19"

    # 会場19と22のレース状況
    for venue_code in ['19', '22']:
        print(f"\n会場{venue_code}:")
        cursor.execute("""
            SELECT race_number, COUNT(*) as entry_count
            FROM races r
            LEFT JOIN entries e ON r.id = e.race_id
            WHERE r.venue_code = ? AND r.race_date = ?
            GROUP BY r.race_number
            ORDER BY r.race_number
        """, (venue_code, today))

        results = cursor.fetchall()
        existing_races = [r[0] for r in results]

        # 全レース（1-12R）をチェック
        for race_num in range(1, 13):
            if race_num in existing_races:
                entry_count = next(r[1] for r in results if r[0] == race_num)
                status = f"✅ {entry_count}選手"
            else:
                status = "❌ 未取得"
            print(f"  {race_num:2}R: {status}")

    conn.close()


def main():
    print("=" * 60)
    print("欠損レース デバッグ調査")
    print("=" * 60)

    # まずデータベース状況を確認
    check_database_status()

    # 欠損レースをスクレイピング
    missing_races = [
        ("19", "20251119", 10),  # 下関 10R
        ("22", "20251119", 6),   # 福岡 6R
    ]

    for venue_code, race_date, race_number in missing_races:
        result = debug_scrape_race(venue_code, race_date, race_number)

        if result:
            print(f"\n✅ 会場{venue_code} {race_number}R: スクレイピング成功")
        else:
            print(f"\n❌ 会場{venue_code} {race_number}R: スクレイピング失敗")

    print("\n" + "="*60)
    print("調査完了")
    print("="*60)


if __name__ == "__main__":
    main()
