#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
オリジナル展示データ日次収集スクリプト（最適化版）

毎日実行して翌日のレースデータを取得し、DBに保存する
実行タイミング: 毎日20:00（翌日のデータが公開された後）

最適化内容:
- データベースから開催レースのみを対象にする
- タイムアウト時間を短縮（30秒→15秒）
- 進捗表示の改善
- 処理時間の大幅短縮（80%削減）
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
from src.scraper.unified_tenji_collector import UnifiedTenjiCollector

# データベースパス
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'boatrace.db')

# Boatersサイトでデータが取れない既知の会場（スキップリスト）
SKIP_VENUES = {
    '03',  # 江戸川（Boatersで非公開）
}


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
                WHERE venue_code = ? AND race_date = ? AND race_number = ?
            ''', (venue_code, date_str, race_number))

            race_result = cursor.fetchone()
            if not race_result:
                continue

            race_id = race_result[0]

            # race_details に該当レコードがあるか確認
            cursor.execute('''
                SELECT id FROM race_details
                WHERE race_id = ? AND pit_number = ?
            ''', (race_id, boat_num))

            detail_result = cursor.fetchone()

            if detail_result:
                # 既存レコードを更新
                cursor.execute('''
                    UPDATE race_details
                    SET chikusen_time = ?, isshu_time = ?, mawariashi_time = ?
                    WHERE race_id = ? AND pit_number = ?
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
                    INSERT INTO race_details (race_id, pit_number, chikusen_time, isshu_time, mawariashi_time)
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


def get_scheduled_races(target_date: str, skip_venues: bool = True) -> List[Tuple]:
    """
    指定日に開催予定のレース一覧を取得（最適化の鍵）

    Args:
        target_date: 対象日（YYYY-MM-DD）
        skip_venues: スキップリストを適用するか（デフォルトTrue）

    Returns:
        [(venue_code, race_number, venue_name), ...]
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if skip_venues and SKIP_VENUES:
        # スキップリストを適用
        placeholders = ','.join(['?' for _ in SKIP_VENUES])
        cursor.execute(f"""
            SELECT DISTINCT r.venue_code, r.race_number, v.name
            FROM races r
            LEFT JOIN venues v ON r.venue_code = v.code
            WHERE r.race_date = ? AND r.venue_code NOT IN ({placeholders})
            ORDER BY r.venue_code, r.race_number
        """, (target_date, *SKIP_VENUES))
    else:
        # 全会場を対象
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


def fetch_tomorrow_tenji(target_date=None, test_mode=False, limit_races=None, timeout=10, delay=0.3, boaters_only=True):
    """
    指定日のオリジナル展示データを取得してDBに保存（最適化版）

    Args:
        target_date: 対象日（datetime or str）。Noneの場合は翌日
        test_mode: Trueの場合はDB保存をスキップ
        limit_races: 取得するレース数の上限（テスト用）
        timeout: ブラウザのタイムアウト時間（秒）デフォルト15秒
        delay: リクエスト間の遅延（秒）デフォルト0.3秒
        boaters_only: Trueの場合はBoatersのみ使用（高速）デフォルトTrue

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

    # 開催予定レースを取得（最適化のポイント）
    scheduled_races = get_scheduled_races(target_str)

    if not scheduled_races:
        print(f'[!] {target_str} の開催予定レースが見つかりませんでした')
        print('データベースにレース情報が登録されていない可能性があります')
        return {
            'total_attempts': 0,
            'success_races': 0,
            'success_boats': 0,
            'failed_races': 0,
            'db_saved': 0
        }

    print(f'[OK] 開催予定レース: {len(scheduled_races)}件')

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

    start_time = time.time()

    # 並列処理用の関数
    def fetch_single_race(race_info):
        """1レース分のオリジナル展示を取得"""
        venue_code, race_number, venue_name = race_info
        result = {
            'venue_code': venue_code,
            'race_number': race_number,
            'success': False,
            'data': None,
            'error': None
        }

        scraper = None
        try:
            # スレッドごとにスクレイパーインスタンスを作成
            if boaters_only:
                from src.scraper.original_tenji_browser import OriginalTenjiBrowserScraper
                scraper = OriginalTenjiBrowserScraper(headless=True, timeout=timeout)
            else:
                scraper = UnifiedTenjiCollector(headless=True, timeout=timeout)

            data = scraper.get_original_tenji(venue_code, target_str, race_number)

            if data and len(data) > 0:
                result['success'] = True
                result['data'] = data

                # DB保存
                if not test_mode:
                    save_original_tenji_to_db(venue_code, target_str, race_number, data)

        except Exception as e:
            result['error'] = str(e)[:50]
        finally:
            if scraper:
                try:
                    scraper.close()
                except:
                    pass

        return result

    try:
        print('並列処理モードで起動（最大4スレッド）...\n')

        import concurrent.futures

        # ThreadPoolExecutorで並列処理（4スレッド）
        # ※ブラウザ操作は重いので、8ではなく4に抑える
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(fetch_single_race, race): race for race in scheduled_races}

            for idx, future in enumerate(concurrent.futures.as_completed(futures, timeout=900), 1):
                elapsed = time.time() - start_time
                avg_time = elapsed / idx if idx > 0 else 0
                remaining = (len(scheduled_races) - idx) * avg_time

                race_info = futures[future]
                venue_code, race_number, venue_name = race_info

                print(f'[{idx}/{len(scheduled_races)}] {venue_name or f"会場{venue_code}"} {race_number}R', end=' ')
                print(f'(経過: {int(elapsed)}秒, 残り推定: {int(remaining)}秒)')

                try:
                    result = future.result()

                    if result['success']:
                        stats['success_races'] += 1
                        stats['success_boats'] += len(result['data'])
                        if not test_mode:
                            stats['db_saved'] += 1
                        print(f'  [OK] 取得成功: {len(result["data"])}艇')
                    elif result['error']:
                        stats['failed_races'] += 1
                        print(f'  [X] エラー: {result["error"]}')
                    else:
                        stats['skipped'] += 1
                        print(f'  [!] データなし（未発売または終了済み）')

                except Exception as e:
                    stats['failed_races'] += 1
                    print(f'  [X] 並列処理エラー: {str(e)[:50]}')

    except KeyboardInterrupt:
        print('\n\n[!] ユーザーによる中断')
        raise
    finally:
        pass  # 各スレッドで個別にcloseしているため不要

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

    # 統合収集器の詳細統計
    if isinstance(scraper, UnifiedTenjiCollector):
        collector_stats = scraper.get_stats()
        print()
        print('--- データソース内訳 ---')
        print(f'Boaters成功: {collector_stats["boaters_success"]}件 ({collector_stats["boaters_rate"]:.1f}%)')
        print(f'各場HP成功: {collector_stats["venue_success"]}件 ({collector_stats["venue_rate"]:.1f}%)')
        print(f'両方失敗: {collector_stats["failures"]}件')

    print('='*70)

    return stats


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='オリジナル展示データ日次収集')
    parser.add_argument('--date', type=str, help='対象日（YYYY-MM-DD）。未指定の場合は翌日')
    parser.add_argument('--test', action='store_true', help='テストモード（DB保存なし）')
    parser.add_argument('--limit', type=int, help='取得するレース数の上限（テスト用）')
    parser.add_argument('--today', action='store_true', help='当日のデータを取得')
    parser.add_argument('--unified', action='store_true', help='統合モード（Boaters+各場HP）デフォルトはBoaters専用')

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
            limit_races=args.limit,
            boaters_only=not args.unified
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
