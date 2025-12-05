"""
今日のレースのオッズを自動収集するスクリプト

使い方:
  python collect_today_odds.py           # 今日の全レースのオッズを収集
  python collect_today_odds.py --test    # テストモード（1レースのみ）
  python collect_today_odds.py --venue 01 # 特定会場のみ
"""

import sys
import os
import argparse
import time
from datetime import datetime
import sqlite3
from typing import List, Tuple

# パス設定
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.odds_scraper import OddsScraper
from config.settings import DATABASE_PATH, VENUES


def get_today_races(venue_code: str = None) -> List[Tuple]:
    """今日開催されるレースのリストを取得"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    today = datetime.now().strftime('%Y-%m-%d')

    if venue_code:
        cursor.execute("""
            SELECT id, venue_code, race_number, race_time
            FROM races
            WHERE race_date = ? AND venue_code = ?
            ORDER BY venue_code, race_number
        """, (today, venue_code))
    else:
        cursor.execute("""
            SELECT id, venue_code, race_number, race_time
            FROM races
            WHERE race_date = ?
            ORDER BY venue_code, race_number
        """, (today,))

    races = cursor.fetchall()
    conn.close()

    return races


def collect_odds_for_race(race_id: int, venue_code: str, race_number: int,
                          scraper: OddsScraper, save_to_db: bool = True) -> dict:
    """1レースのオッズを収集"""

    race_date = datetime.now().strftime('%Y%m%d')

    result = {
        'race_id': race_id,
        'venue_code': venue_code,
        'race_number': race_number,
        'trifecta_success': False,
        'win_success': False,
        'trifecta_count': 0,
        'win_count': 0,
        'error': None
    }

    try:
        # 3連単オッズ取得
        trifecta_odds = scraper.get_trifecta_odds(
            venue_code=venue_code,
            race_date=race_date,
            race_number=race_number
        )

        if trifecta_odds:
            result['trifecta_success'] = True
            result['trifecta_count'] = len(trifecta_odds)

            if save_to_db:
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()

                for combination, odds in trifecta_odds.items():
                    cursor.execute("""
                        INSERT OR REPLACE INTO trifecta_odds
                        (race_id, combination, odds, fetched_at)
                        VALUES (?, ?, ?, ?)
                    """, (race_id, combination, odds, datetime.now()))

                conn.commit()
                conn.close()

        # 単勝オッズ取得
        win_odds = scraper.get_win_odds(
            venue_code=venue_code,
            race_date=race_date,
            race_number=race_number
        )

        if win_odds:
            result['win_success'] = True
            result['win_count'] = len(win_odds)

            if save_to_db:
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()

                for pit_number, odds in win_odds.items():
                    cursor.execute("""
                        INSERT OR REPLACE INTO win_odds
                        (race_id, pit_number, odds, fetched_at)
                        VALUES (?, ?, ?, ?)
                    """, (race_id, int(pit_number), odds, datetime.now()))

                conn.commit()
                conn.close()

    except Exception as e:
        result['error'] = str(e)

    return result


def collect_today_odds(test_mode: bool = False, venue_code: str = None,
                       delay: float = 2.0):
    """今日のオッズを収集"""

    print("="*70)
    print("今日のレースオッズ自動収集")
    print("="*70)

    # 今日のレースを取得
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"\n今日の日付: {today}")

    if venue_code:
        print(f"対象会場: {venue_code}")

    races = get_today_races(venue_code)

    if not races:
        print(f"\n⚠️ {today} のレースが見つかりませんでした")
        return

    print(f"\n✅ 今日のレース {len(races)}件を発見")

    if test_mode:
        print("\n🧪 テストモード: 最初の1レースのみ収集します")
        races = races[:1]

    # 会場名マッピング
    venue_names = {}
    for vid, vinfo in VENUES.items():
        venue_names[vinfo['code']] = vinfo['name']

    print(f"\n収集対象レース数: {len(races)}件")
    print("="*70)

    # オッズスクレイパー初期化
    scraper = OddsScraper(delay=delay, max_retries=3)

    # 統計
    stats = {
        'total': len(races),
        'trifecta_success': 0,
        'win_success': 0,
        'both_success': 0,
        'both_failed': 0,
        'errors': []
    }

    # レースごとにオッズ収集
    for idx, race in enumerate(races, 1):
        race_id, vc, rn, race_time = race
        venue_name = venue_names.get(vc, f'会場{vc}')

        print(f"\n[{idx}/{len(races)}] {venue_name} {rn}R ({race_time or '時刻未定'})")

        result = collect_odds_for_race(
            race_id=race_id,
            venue_code=vc,
            race_number=rn,
            scraper=scraper,
            save_to_db=True
        )

        # 結果表示
        if result['trifecta_success']:
            print(f"  ✅ 3連単オッズ: {result['trifecta_count']}通り")
            stats['trifecta_success'] += 1
        else:
            print(f"  ❌ 3連単オッズ: 取得失敗")

        if result['win_success']:
            print(f"  ✅ 単勝オッズ: {result['win_count']}艇")
            stats['win_success'] += 1
        else:
            print(f"  ❌ 単勝オッズ: 取得失敗")

        if result['trifecta_success'] and result['win_success']:
            stats['both_success'] += 1
        elif not result['trifecta_success'] and not result['win_success']:
            stats['both_failed'] += 1

        if result['error']:
            print(f"  ⚠️ エラー: {result['error']}")
            stats['errors'].append({
                'race': f"{venue_name} {rn}R",
                'error': result['error']
            })

        # レート制限対策
        if idx < len(races):
            time.sleep(delay)

    scraper.close()

    # 統計サマリー
    print("\n" + "="*70)
    print("収集結果サマリー")
    print("="*70)
    print(f"総レース数: {stats['total']}件")
    print(f"3連単成功: {stats['trifecta_success']}件 ({stats['trifecta_success']/stats['total']*100:.1f}%)")
    print(f"単勝成功: {stats['win_success']}件 ({stats['win_success']/stats['total']*100:.1f}%)")
    print(f"両方成功: {stats['both_success']}件 ({stats['both_success']/stats['total']*100:.1f}%)")
    print(f"両方失敗: {stats['both_failed']}件 ({stats['both_failed']/stats['total']*100:.1f}%)")

    if stats['errors']:
        print(f"\nエラー発生: {len(stats['errors'])}件")
        for err in stats['errors'][:5]:  # 最初の5件のみ表示
            print(f"  - {err['race']}: {err['error']}")

    print("\n" + "="*70)
    print("収集完了")
    print("="*70)


def main():
    """メイン関数"""

    parser = argparse.ArgumentParser(
        description='今日のレースのオッズを自動収集'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='テストモード（1レースのみ収集）'
    )
    parser.add_argument(
        '--venue',
        type=str,
        help='特定会場のみ収集（例: 01=桐生, 12=住之江）'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=2.0,
        help='リクエスト間の遅延時間（秒）デフォルト: 2.0'
    )

    args = parser.parse_args()

    collect_today_odds(
        test_mode=args.test,
        venue_code=args.venue,
        delay=args.delay
    )


if __name__ == "__main__":
    main()
