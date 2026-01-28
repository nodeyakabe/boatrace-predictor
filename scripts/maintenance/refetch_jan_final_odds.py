#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
1月の確定オッズを再取得（上書き）

既存の暫定オッズを削除して、確定オッズで置き換える
"""
import sys
import os
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.scraper.odds_scraper import OddsScraper
from config.settings import DATABASE_PATH
import sqlite3
import time


def refetch_january_final_odds():
    """1月の確定オッズを再取得"""

    print("=" * 100)
    print("1月確定オッズ再取得開始")
    print("=" * 100)
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 1月のレース一覧を取得
    cursor.execute('''
        SELECT DISTINCT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number
        FROM races r
        WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')

    races = [dict(zip(['race_id', 'race_date', 'venue_code', 'race_number'], row))
             for row in cursor.fetchall()]

    print(f"対象レース数: {len(races)}件")
    print()

    scraper = OddsScraper()

    success_count = 0
    skip_count = 0
    error_count = 0

    for i, race in enumerate(races, 1):
        race_id = race['race_id']
        race_date = race['race_date']
        venue_code = race['venue_code']
        race_number = race['race_number']

        # YYYYMMDD形式に変換
        date_yyyymmdd = race_date.replace('-', '')
        # venue_codeは既に文字列の可能性があるため、整数に変換してからフォーマット
        venue_str = f"{int(venue_code):02d}"

        try:
            # 確定オッズを取得
            odds_data = scraper.get_trifecta_odds(venue_str, date_yyyymmdd, race_number)

            if odds_data and len(odds_data) > 0:
                # 既存オッズを削除
                cursor.execute('DELETE FROM trifecta_odds WHERE race_id = ?', (race_id,))

                # 新しい確定オッズを挿入
                for combination, odds in odds_data.items():
                    cursor.execute('''
                        INSERT INTO trifecta_odds (race_id, combination, odds, fetched_at)
                        VALUES (?, ?, ?, ?)
                    ''', (race_id, combination, odds, datetime.now().isoformat()))

                conn.commit()
                success_count += 1

                if i % 50 == 0:
                    print(f"  進捗: {i}/{len(races)} ({success_count}件成功, {skip_count}件スキップ, {error_count}件エラー)")
            else:
                skip_count += 1

            # レート制限対策
            time.sleep(0.5)

        except Exception as e:
            error_count += 1
            print(f"[ERROR] {race_date} 会場{venue_code:02d} {race_number}R: {str(e)}")
            continue

    conn.close()

    print()
    print("=" * 100)
    print("確定オッズ再取得完了")
    print("=" * 100)
    print(f"  成功: {success_count}件")
    print(f"  スキップ: {skip_count}件")
    print(f"  エラー: {error_count}件")
    print()

    return success_count


if __name__ == '__main__':
    try:
        count = refetch_january_final_odds()
        print(f"\n[OK] {count}レースの確定オッズを再取得しました")
        print("\n次のステップ:")
        print("  python scripts/backtest/standard_backtest.py --year 2026")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] エラーが発生しました: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
