#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
前日のレース結果を収集するスクリプト

daily_schedulerから毎朝呼び出される。
前日のレース結果（確定情報）を取得してDBに保存する。
"""
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.scraper.result_scraper import ResultScraper
from config.settings import DATABASE_PATH
import sqlite3
import time


def fetch_yesterday_results(headless: bool = True) -> int:
    """
    前日のレース結果を取得

    Args:
        headless: ブラウザをヘッドレスモードで実行するか

    Returns:
        int: 取得したレース数
    """
    # 前日の日付を取得
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')

    print(f"前日レース結果収集開始: {date_str}")

    try:
        scraper = ResultScraper()
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 前日のレースIDを取得
        cursor.execute('''
            SELECT id, venue_code, race_number, race_date
            FROM races
            WHERE race_date = ?
            ORDER BY venue_code, race_number
        ''', (date_str,))
        races = [dict(row) for row in cursor.fetchall()]

        if not races:
            print(f"前日({date_str})のレースデータが見つかりません")
            conn.close()
            return 0

        print(f"前日のレース数: {len(races)}")

        # 結果がまだ保存されていないレースをフィルタ
        races_without_results = []
        for race in races:
            cursor.execute('SELECT COUNT(*) FROM results WHERE race_id = ?', (race['id'],))
            if cursor.fetchone()[0] == 0:
                races_without_results.append(race)

        if not races_without_results:
            print(f"前日のレース結果は全て取得済みです")
            return 0

        print(f"結果未取得のレース: {len(races_without_results)}")

        # 結果を収集
        results_count = 0
        errors = []

        for race in races_without_results:
            try:
                venue_code = race['venue_code']
                race_number = race['race_number']
                race_date = race['race_date'].replace('-', '')  # YYYYMMDD形式

                # 結果を取得
                results = scraper.get_race_results(venue_code, race_date, race_number)

                if results:
                    # DBに保存
                    for result in results:
                        cursor.execute('''
                            INSERT INTO results (race_id, pit_number, rank)
                            VALUES (?, ?, ?)
                        ''', (race['id'], result.get('pit_number'), result.get('rank')))

                    conn.commit()
                    results_count += 1

                    if results_count % 10 == 0:
                        print(f"  進捗: {results_count}/{len(races_without_results)}")

            except Exception as e:
                error_msg = f"レース結果取得エラー: 会場={venue_code}, 日付={race_date}, R={race_number}, エラー={str(e)}"
                errors.append(error_msg)
                print(f"[WARNING] {error_msg}")
                continue

        print(f"\n前日レース結果収集完了:")
        print(f"  取得成功: {results_count}レース")
        if errors:
            print(f"  エラー: {len(errors)}件")
            for error in errors[:5]:  # 最初の5件のみ表示
                print(f"    - {error}")

        conn.close()
        return results_count

    except Exception as e:
        print(f"[ERROR] 前日レース結果収集でエラー: {str(e)}")
        if 'conn' in locals():
            conn.close()
        raise


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='前日のレース結果を収集')
    parser.add_argument('--show-browser', action='store_true',
                       help='ブラウザを表示する')
    args = parser.parse_args()

    headless = not args.show_browser

    try:
        count = fetch_yesterday_results(headless=headless)
        print(f"\n収集完了: {count}レース")
        return 0
    except Exception as e:
        print(f"\n[ERROR] エラーが発生しました: {str(e)}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
