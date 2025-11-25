#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
オリジナル展示データ日次収集スクリプト

毎日実行して翌日のレースデータを取得し、DBに保存する
実行タイミング: 毎日20:00（翌日のデータが公開された後）
"""
import sys
import os
import time
import sqlite3
from datetime import datetime, timedelta

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.original_tenji_browser import OriginalTenjiBrowserScraper

# 会場コードと会場名の対応
VENUES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
    '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
    '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
    '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}

# データベースパス
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'boatrace.db')


def save_original_tenji_to_db(venue_code, date_str, race_number, tenji_data):
    """
    オリジナル展示データをデータベースに保存

    Args:
        venue_code: 会場コード（例: "20"）
        date_str: 日付文字列（例: "2025-11-13"）
        race_number: レース番号（1-12）
        tenji_data: オリジナル展示データ dict

    Returns:
        bool: 保存成功ならTrue
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # race_details テーブルを更新
        update_count = 0
        for boat_num, data in tenji_data.items():
            # race_idを取得
            cursor.execute('''
                SELECT id FROM races
                WHERE venue_code = ? AND date = ? AND race_number = ?
            ''', (venue_code, date_str, race_number))

            race_result = cursor.fetchone()
            if not race_result:
                continue

            race_id = race_result[0]

            # race_details に該当レコードがあるか確認
            cursor.execute('''
                SELECT id FROM race_details
                WHERE race_id = ? AND waku = ?
            ''', (race_id, boat_num))

            detail_result = cursor.fetchone()

            if detail_result:
                # 既存レコードを更新
                cursor.execute('''
                    UPDATE race_details
                    SET chikusen_time = ?, isshu_time = ?, mawariashi_time = ?
                    WHERE race_id = ? AND waku = ?
                ''', (
                    data.get('chikusen_time'),
                    data.get('isshu_time'),
                    data.get('mawariashi_time'),
                    race_id,
                    boat_num
                ))
                update_count += 1
            else:
                # 新規レコードを挿入
                cursor.execute('''
                    INSERT INTO race_details (race_id, waku, chikusen_time, isshu_time, mawariashi_time)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    race_id,
                    boat_num,
                    data.get('chikusen_time'),
                    data.get('isshu_time'),
                    data.get('mawariashi_time')
                ))
                update_count += 1

        conn.commit()
        conn.close()

        return update_count > 0

    except Exception as e:
        print(f"  [DB保存エラー] {e}")
        return False


def fetch_tomorrow_tenji(target_date=None, test_mode=False, limit_races=None):
    """
    指定日のオリジナル展示データを取得してDBに保存

    Args:
        target_date: 対象日（datetime or str）。Noneの場合は翌日
        test_mode: Trueの場合はDB保存をスキップ
        limit_races: 取得するレース数の上限（テスト用）

    Returns:
        dict: 統計情報
    """
    # 対象日の決定
    if target_date is None:
        target = datetime.now() + timedelta(days=1)
    elif isinstance(target_date, str):
        target = datetime.strptime(target_date, '%Y-%m-%d')
    else:
        target = target_date

    target_str = target.strftime('%Y-%m-%d')

    print(f'=== オリジナル展示データ収集 ===')
    print(f'対象日: {target_str}')
    print(f'モード: {"テスト" if test_mode else "本番（DB保存あり）"}')
    if limit_races:
        print(f'取得上限: {limit_races}レース')
    print()

    # 統計情報
    stats = {
        'total_attempts': 0,
        'success_races': 0,
        'success_boats': 0,
        'failed_races': 0,
        'db_saved': 0
    }

    scraper = None

    try:
        scraper = OriginalTenjiBrowserScraper(headless=True)

        for venue_code, venue_name in VENUES.items():
            for race_num in range(1, 13):
                # 上限チェック
                if limit_races and stats['success_races'] >= limit_races:
                    print(f'\n取得上限 {limit_races}レース に到達しました。')
                    break

                stats['total_attempts'] += 1

                try:
                    data = scraper.get_original_tenji(venue_code, target_str, race_num)

                    if data and len(data) > 0:
                        stats['success_races'] += 1
                        stats['success_boats'] += len(data)

                        print(f'  [成功] {venue_name} {race_num}R: {len(data)}艇')

                        # DB保存
                        if not test_mode:
                            if save_original_tenji_to_db(venue_code, target_str, race_num, data):
                                stats['db_saved'] += 1

                except KeyboardInterrupt:
                    print('\n\n中断されました')
                    raise
                except Exception as e:
                    stats['failed_races'] += 1
                    # エラーは表示しない（データがない場合が多い）

                # レート制限
                time.sleep(0.3)

            # 上限チェック
            if limit_races and stats['success_races'] >= limit_races:
                break

    finally:
        if scraper:
            scraper.close()

    # 結果サマリー
    print(f'\n=== 収集完了 ===')
    print(f'試行回数: {stats["total_attempts"]}')
    print(f'成功レース数: {stats["success_races"]}')
    print(f'取得艇数: {stats["success_boats"]}')
    print(f'失敗レース数: {stats["failed_races"]}')
    if not test_mode:
        print(f'DB保存レース数: {stats["db_saved"]}')

    return stats


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='オリジナル展示データ日次収集')
    parser.add_argument('--date', type=str, help='対象日（YYYY-MM-DD）。未指定の場合は翌日')
    parser.add_argument('--test', action='store_true', help='テストモード（DB保存なし）')
    parser.add_argument('--limit', type=int, help='取得するレース数の上限（テスト用）')
    parser.add_argument('--today', action='store_true', help='当日のデータを取得')

    args = parser.parse_args()

    # 対象日の決定
    if args.date:
        target_date = args.date
    elif args.today:
        target_date = datetime.now().strftime('%Y-%m-%d')
    else:
        target_date = None  # 翌日

    try:
        fetch_tomorrow_tenji(
            target_date=target_date,
            test_mode=args.test,
            limit_races=args.limit
        )
    except KeyboardInterrupt:
        print('\n処理を中断しました')
        sys.exit(1)
    except Exception as e:
        print(f'\nエラーが発生しました: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
