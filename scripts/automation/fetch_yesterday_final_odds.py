#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
前日の確定オッズを取得（暫定オッズの上書き）

毎朝7:05に実行され、前日レースの確定オッズを取得してDBを更新します。
これにより、バックテストで正確なオッズデータを使用できます。
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.scraper.odds_scraper import OddsScraper
from config.settings import DATABASE_PATH
import sqlite3
import time


def fetch_yesterday_final_odds(headless: bool = True) -> int:
    """
    前日の確定オッズを取得してDBを上書き

    Args:
        headless: ヘッドレスモードで実行するか

    Returns:
        int: 更新したレース数
    """
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    date_yyyymmdd = yesterday.strftime('%Y%m%d')

    print(f"\n前日確定オッズ取得開始: {date_str}")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 前日のレースを取得
    cursor.execute('''
        SELECT id, venue_code, race_number, race_date
        FROM races
        WHERE race_date = ?
        ORDER BY venue_code, race_number
    ''', (date_str,))
    races = [dict(row) for row in cursor.fetchall()]

    if not races:
        print(f"[INFO] {date_str} のレースが見つかりませんでした")
        conn.close()
        return 0

    print(f"対象レース数: {len(races)}件")

    scraper = OddsScraper()
    success_count = 0
    skip_count = 0
    error_count = 0

    for i, race in enumerate(races, 1):
        race_id = race['id']
        venue_code = race['venue_code']
        race_number = race['race_number']

        # venue_codeは文字列の可能性があるため整数に変換
        venue_str = f"{int(venue_code):02d}"

        try:
            # 確定オッズを取得
            odds_data = scraper.get_trifecta_odds(venue_str, date_yyyymmdd, race_number)

            if odds_data and len(odds_data) > 0:
                # 確定オッズを挿入（更新）
                for combination, odds in odds_data.items():
                    cursor.execute('''
                        INSERT OR REPLACE INTO trifecta_odds (race_id, combination, odds, fetched_at)
                        VALUES (?, ?, ?, ?)
                    ''', (race_id, combination, odds, datetime.now().isoformat()))

                conn.commit()
                success_count += 1

                if success_count % 10 == 0:
                    print(f"進捗: {i}/{len(races)} ({success_count}件成功, {skip_count}件スキップ, {error_count}件エラー)")
            else:
                skip_count += 1

        except Exception as e:
            error_count += 1
            if error_count <= 5:  # 最初の5件のみエラー表示
                print(f"[WARNING] オッズ取得失敗: {venue_str} {date_yyyymmdd} {race_number}R - {str(e)}")

        # レート制限対策
        time.sleep(0.5)

    conn.close()

    print("\n" + "=" * 80)
    print(f"前日確定オッズ取得完了")
    print(f"  成功: {success_count}件")
    print(f"  スキップ: {skip_count}件")
    print(f"  エラー: {error_count}件")
    print("=" * 80)

    return success_count


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='前日の確定オッズを取得')
    parser.add_argument('--no-headless', action='store_true', help='ブラウザを表示')

    args = parser.parse_args()

    try:
        count = fetch_yesterday_final_odds(headless=not args.no_headless)
        print(f"\n[OK] {count}レースの確定オッズを取得しました")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] エラーが発生しました: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
