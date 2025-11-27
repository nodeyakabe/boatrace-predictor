#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
オリジナル展示データ収集スクリプト（最適化版）

改善点:
1. データベースから開催レースのみを対象にする
2. タイムアウト時間を短縮
3. 並列処理オプション（オプション）
4. 進捗表示の改善
"""
import sys
import os
import time
import sqlite3
from datetime import datetime, timedelta
from typing import List, Tuple

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.original_tenji_browser import OriginalTenjiBrowserScraper

# データベースパス
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'boatrace.db')


def get_scheduled_races(target_date: str) -> List[Tuple]:
    """
    指定日に開催予定のレース一覧を取得

    Args:
        target_date: 対象日（YYYY-MM-DD）

    Returns:
        [(venue_code, race_number, venue_name), ...]
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT r.venue_code, r.race_number, v.name
        FROM races r
        LEFT JOIN venues v ON r.venue_code = v.code
        WHERE r.race_date = ?
        ORDER BY r.venue_code, r.race_number
    """, (target_date,))

    races = cursor.fetchall()
    conn.close()

    return races


def save_original_tenji_to_db(venue_code, date_str, race_number, tenji_data):
    """
    オリジナル展示データをデータベースに保存
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # race_idを取得
        cursor.execute("""
            SELECT id FROM races
            WHERE venue_code = ? AND race_date = ? AND race_number = ?
        """, (venue_code, date_str, race_number))

        race_result = cursor.fetchone()
        if not race_result:
            conn.close()
            return False

        race_id = race_result[0]
        update_count = 0

        # race_details テーブルを更新
        for boat_num, data in tenji_data.items():
            cursor.execute("""
                SELECT id FROM race_details
                WHERE race_id = ? AND waku = ?
            """, (race_id, boat_num))

            detail_result = cursor.fetchone()

            if detail_result:
                # 既存レコードを更新
                cursor.execute("""
                    UPDATE race_details
                    SET chikusen_time = ?, isshu_time = ?, mawariashi_time = ?
                    WHERE race_id = ? AND waku = ?
                """, (
                    data.get('chikusen_time'),
                    data.get('isshu_time'),
                    data.get('mawariashi_time'),
                    race_id,
                    boat_num
                ))
            else:
                # 新規レコードを挿入
                cursor.execute("""
                    INSERT INTO race_details (race_id, waku, chikusen_time, isshu_time, mawariashi_time)
                    VALUES (?, ?, ?, ?, ?)
                """, (
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


def fetch_tenji_optimized(target_date=None, test_mode=False, limit_races=None,
                         timeout=15, delay=0.3):
    """
    開催レースのみを対象にオリジナル展示データを取得（最適化版）

    Args:
        target_date: 対象日（datetime or str）。Noneの場合は翌日
        test_mode: Trueの場合はDB保存をスキップ
        limit_races: 取得するレース数の上限（テスト用）
        timeout: ブラウザのタイムアウト時間（秒）デフォルト15秒
        delay: リクエスト間の遅延（秒）デフォルト0.3秒

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

    print('='*70)
    print('オリジナル展示データ収集（最適化版）')
    print('='*70)
    print(f'対象日: {target_str}')
    print(f'モード: {"テスト" if test_mode else "本番（DB保存あり）"}')
    print(f'タイムアウト: {timeout}秒')
    print(f'遅延: {delay}秒')
    if limit_races:
        print(f'取得上限: {limit_races}レース')
    print()

    # 開催予定レースを取得
    scheduled_races = get_scheduled_races(target_str)

    if not scheduled_races:
        print(f'❌ {target_str} の開催予定レースが見つかりませんでした')
        print('データベースにレース情報が登録されていない可能性があります')
        return {
            'total_attempts': 0,
            'success_races': 0,
            'success_boats': 0,
            'failed_races': 0,
            'db_saved': 0
        }

    print(f'✅ 開催予定レース: {len(scheduled_races)}件')

    # 上限適用
    if limit_races:
        scheduled_races = scheduled_races[:limit_races]
        print(f'   取得対象: {len(scheduled_races)}件（上限適用）')

    print('='*70)

    # 統計情報
    stats = {
        'total_attempts': len(scheduled_races),
        'success_races': 0,
        'success_boats': 0,
        'failed_races': 0,
        'db_saved': 0,
        'skipped': 0
    }

    scraper = None
    start_time = time.time()

    try:
        # タイムアウト時間を短縮して初期化
        print('ブラウザを起動中...')
        scraper = OriginalTenjiBrowserScraper(headless=True, timeout=timeout)
        print('✅ ブラウザ起動完了\n')

        for idx, (venue_code, race_number, venue_name) in enumerate(scheduled_races, 1):
            elapsed = time.time() - start_time
            avg_time = elapsed / idx if idx > 0 else 0
            remaining = (len(scheduled_races) - idx) * avg_time

            print(f'[{idx}/{len(scheduled_races)}] {venue_name or f"会場{venue_code}"} {race_number}R', end=' ')
            print(f'(経過: {int(elapsed)}秒, 残り推定: {int(remaining)}秒)')

            try:
                data = scraper.get_original_tenji(venue_code, target_str, race_number)

                if data and len(data) > 0:
                    stats['success_races'] += 1
                    stats['success_boats'] += len(data)

                    print(f'  ✅ 取得成功: {len(data)}艇')

                    # DB保存
                    if not test_mode:
                        if save_original_tenji_to_db(venue_code, target_str, race_number, data):
                            stats['db_saved'] += 1
                            print(f'  💾 DB保存完了')
                else:
                    stats['skipped'] += 1
                    print(f'  ⚠️  データなし（未発売または終了済み）')

            except KeyboardInterrupt:
                print('\n\n⚠️  ユーザーによる中断')
                raise
            except Exception as e:
                stats['failed_races'] += 1
                print(f'  ❌ エラー: {str(e)[:50]}')

            # レート制限
            if idx < len(scheduled_races):
                time.sleep(delay)

    finally:
        if scraper:
            print('\nブラウザを終了中...')
            scraper.close()
            print('✅ ブラウザ終了完了')

    total_time = time.time() - start_time

    # 結果サマリー
    print('\n' + '='*70)
    print('収集完了サマリー')
    print('='*70)
    print(f'総処理時間: {int(total_time)}秒 ({int(total_time/60)}分{int(total_time%60)}秒)')
    print(f'対象レース: {stats["total_attempts"]}件')
    print(f'成功: {stats["success_races"]}件')
    print(f'取得艇数: {stats["success_boats"]}艇')
    print(f'失敗: {stats["failed_races"]}件')
    print(f'スキップ: {stats["skipped"]}件')
    if not test_mode:
        print(f'DB保存: {stats["db_saved"]}件')
    print('='*70)

    return stats


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='オリジナル展示データ収集（最適化版）')
    parser.add_argument('--date', type=str, help='対象日（YYYY-MM-DD）。未指定の場合は翌日')
    parser.add_argument('--test', action='store_true', help='テストモード（DB保存なし）')
    parser.add_argument('--limit', type=int, help='取得するレース数の上限（テスト用）')
    parser.add_argument('--today', action='store_true', help='当日のデータを取得')
    parser.add_argument('--timeout', type=int, default=15, help='ブラウザタイムアウト（秒）デフォルト: 15')
    parser.add_argument('--delay', type=float, default=0.3, help='リクエスト間隔（秒）デフォルト: 0.3')

    args = parser.parse_args()

    # 対象日の決定
    if args.date:
        target_date = args.date
    elif args.today:
        target_date = datetime.now().strftime('%Y-%m-%d')
    else:
        target_date = None  # 翌日

    try:
        fetch_tenji_optimized(
            target_date=target_date,
            test_mode=args.test,
            limit_races=args.limit,
            timeout=args.timeout,
            delay=args.delay
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
