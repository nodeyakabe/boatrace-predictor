#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
前日の直前情報を収集するスクリプト

daily_schedulerから毎朝呼び出される。
前日の直前情報（確定情報）を取得してDBに保存する。
"""
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from config.settings import DATABASE_PATH
import sqlite3
import time


def fetch_yesterday_beforeinfo(headless: bool = True) -> int:
    """
    前日の直前情報を取得

    Args:
        headless: ブラウザをヘッドレスモードで実行するか（現在は未使用だがAPI統一のため）

    Returns:
        int: 取得したレース数
    """
    # 前日の日付を取得
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')  # YYYY-MM-DD形式
    date_yyyymmdd = yesterday.strftime('%Y%m%d')  # YYYYMMDD形式

    print(f"前日直前情報収集開始: {date_str}")

    try:
        scraper = BeforeInfoScraper()
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row

        # 前日のレース一覧を取得
        cursor = conn.cursor()
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

        # 直前情報を収集
        success_count = 0
        skip_count = 0
        errors = []

        for race in races:
            venue_code = None
            race_number = None
            try:
                venue_code = f"{race['venue_code']:02d}"
                race_number = race['race_number']

                # 直前情報を取得
                result = scraper.get_race_beforeinfo(
                    venue_code,
                    date_yyyymmdd,
                    race_number
                )

                if result and result.get('is_published'):
                    # DBに保存
                    success = scraper.save_to_db(race['id'], result)

                    if success:
                        success_count += 1

                        if success_count % 50 == 0:
                            print(f"  進捗: {success_count}/{len(races)}")
                    else:
                        skip_count += 1

                else:
                    skip_count += 1

                # レート制限対策
                time.sleep(0.3)

            except Exception as e:
                # venue_codeがNoneの場合はrace辞書から取得
                venue_str = venue_code if venue_code else f"{race.get('venue_code', '??'):02d}"
                race_num_str = race_number if race_number else race.get('race_number', '?')
                error_msg = f"直前情報取得エラー: 会場={venue_str}, 日付={date_str}, R={race_num_str}, エラー={str(e)}"
                errors.append(error_msg)
                print(f"[WARNING] {error_msg}")
                continue

        print(f"\n前日直前情報収集完了:")
        print(f"  取得成功: {success_count}レース")
        print(f"  スキップ: {skip_count}レース")

        if errors:
            print(f"  エラー: {len(errors)}件")
            for error in errors[:5]:  # 最初の5件のみ表示
                print(f"    - {error}")

        conn.close()
        return success_count

    except Exception as e:
        print(f"[ERROR] 前日直前情報収集でエラー: {str(e)}")
        if 'conn' in locals():
            conn.close()
        raise
    finally:
        if 'scraper' in locals():
            scraper.close()


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='前日の直前情報を収集')
    parser.add_argument('--show-browser', action='store_true',
                       help='ブラウザを表示する（現在は未使用）')
    args = parser.parse_args()

    headless = not args.show_browser

    try:
        count = fetch_yesterday_beforeinfo(headless=headless)
        print(f"\n収集完了: {count}レース")
        return 0
    except Exception as e:
        print(f"\n[ERROR] エラーが発生しました: {str(e)}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
