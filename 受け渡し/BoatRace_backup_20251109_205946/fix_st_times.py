"""
ST時間修正スクリプト
V3スクレイパーを使用して、ST時間が不足しているレースを再取得

使用方法:
    # 2024年4月のみ修正
    python fix_st_times.py --start 2024-04-01 --end 2024-04-30

    # 最近のレースをテスト（5レースのみ）
    python fix_st_times.py --start 2024-10-01 --end 2024-10-31 --limit 5 --test

    # 全期間を修正（時間がかかります）
    python fix_st_times.py --start 2024-01-01 --end 2024-12-31
"""

import argparse
import sqlite3
import time
from datetime import datetime
from collections import defaultdict

from src.scraper.result_scraper_improved_v3 import ImprovedResultScraperV3
from src.database.data_manager import DataManager


class STTimeFixer:
    """ST時間修正クラス"""

    def __init__(self, db_path="data/boatrace.db", test_mode=False):
        """
        初期化

        Args:
            db_path: データベースパス
            test_mode: テストモード（実際の更新を行わない）
        """
        self.db_path = db_path
        self.test_mode = test_mode
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'fixed_st_count': defaultdict(int)
        }

    def find_missing_st_races(self, start_date: str, end_date: str, limit: int = None):
        """
        ST時間が不足しているレースを検出

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)
            limit: 最大取得数

        Returns:
            list: (race_id, venue_code, race_date, race_number, st_count) のリスト
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT r.id, r.venue_code, r.race_date, r.race_number,
                   COUNT(rd.pit_number) as total,
                   SUM(CASE WHEN rd.st_time IS NOT NULL THEN 1 ELSE 0 END) as st_count
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
            GROUP BY r.id
            HAVING st_count < 6 AND total > 0
            ORDER BY r.race_date, r.venue_code, r.race_number
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, (start_date, end_date))
        races = cursor.fetchall()
        conn.close()

        return races

    def fix_race_st_times(self, race_id: int, venue_code: str, race_date: str, race_number: int):
        """
        1レースのST時間を修正

        Args:
            race_id: レースID
            venue_code: 会場コード
            race_date: レース日 (YYYY-MM-DD)
            race_number: レース番号

        Returns:
            dict: 修正結果
        """
        result = {
            'success': False,
            'st_count': 0,
            'error': None,
            'updated_pits': []
        }

        try:
            # 日付フォーマット変換 (YYYY-MM-DD -> YYYYMMDD)
            date_str = race_date.replace('-', '')

            # V3スクレイパーでデータ取得
            scraper = ImprovedResultScraperV3()
            complete_result = scraper.get_race_result_complete(venue_code, date_str, race_number)
            scraper.close()

            if not complete_result:
                result['error'] = 'データ取得失敗（レース未実施またはネットワークエラー）'
                return result

            st_times = complete_result.get('st_times', {})
            st_status = complete_result.get('st_status', {})

            if len(st_times) < 6:
                result['error'] = f'ST時間不足（{len(st_times)}/6）'
                result['st_count'] = len(st_times)
                return result

            # テストモードでない場合のみ更新
            if not self.test_mode:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                # 各艇のST時間を更新
                for pit, st_time in st_times.items():
                    # 既存レコードがあるか確認
                    cursor.execute("""
                        SELECT id FROM race_details
                        WHERE race_id = ? AND pit_number = ?
                    """, (race_id, pit))

                    existing = cursor.fetchone()

                    if existing:
                        # 更新
                        cursor.execute("""
                            UPDATE race_details
                            SET st_time = ?
                            WHERE race_id = ? AND pit_number = ?
                        """, (st_time, race_id, pit))
                    else:
                        # 新規挿入
                        cursor.execute("""
                            INSERT INTO race_details (race_id, pit_number, st_time)
                            VALUES (?, ?, ?)
                        """, (race_id, pit, st_time))

                    result['updated_pits'].append(pit)

                conn.commit()
                conn.close()

            result['success'] = True
            result['st_count'] = len(st_times)

        except Exception as e:
            result['error'] = str(e)

        return result

    def run(self, start_date: str, end_date: str, limit: int = None, delay: float = 0.5):
        """
        ST時間修正を実行

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)
            limit: 最大修正レース数
            delay: レート制限用遅延時間（秒）
        """
        print("="*80)
        print("ST時間修正スクリプト - V3スクレイパー使用")
        print("="*80)
        print(f"期間: {start_date} ～ {end_date}")
        if self.test_mode:
            print("モード: テストモード（実際の更新は行いません）")
        else:
            print("モード: 本番モード（データベースを更新します）")
        print("="*80)

        # ST時間不足レースを検出
        print("\nST時間不足レースを検索中...")
        races = self.find_missing_st_races(start_date, end_date, limit)

        if len(races) == 0:
            print("修正が必要なレースは見つかりませんでした。")
            return

        print(f"修正対象レース数: {len(races)}")

        # ST時間不足の内訳
        st_count_dist = defaultdict(int)
        for race in races:
            st_count = race[5]
            st_count_dist[st_count] += 1

        print("\nST時間不足の内訳:")
        for st_count in sorted(st_count_dist.keys()):
            print(f"  {st_count}/6 ST時間: {st_count_dist[st_count]}レース")

        # 推定時間計算
        estimated_time = len(races) * delay
        estimated_minutes = estimated_time / 60
        print(f"\n推定時間: {estimated_minutes:.1f}分 ({delay}秒/レース)")

        # 確認
        if not self.test_mode:
            print("\n[WARNING] データベースを更新します。よろしいですか？")
            response = input("続行する場合は 'yes' と入力してください: ")
            if response.lower() != 'yes':
                print("キャンセルしました。")
                return

        print("\n修正を開始します...\n")

        start_time = time.time()

        for i, race in enumerate(races, 1):
            race_id, venue_code, race_date, race_number, total, st_count = race

            self.stats['total'] += 1

            # 進捗表示
            if i % 10 == 0 or i == 1:
                elapsed = time.time() - start_time
                avg_time = elapsed / i
                remaining = (len(races) - i) * avg_time
                print(f"進捗: {i}/{len(races)} ({i/len(races)*100:.1f}%) "
                      f"- 残り時間: {remaining/60:.1f}分")

            # 修正実行
            fix_result = self.fix_race_st_times(race_id, venue_code, race_date, race_number)

            if fix_result['success']:
                self.stats['success'] += 1
                self.stats['fixed_st_count'][fix_result['st_count']] += 1

                if i <= 5 or (i % 50 == 0):  # 最初の5件と50件ごとに詳細表示
                    print(f"  [OK] 会場{venue_code} {race_date} {race_number}R: "
                          f"ST時間 {st_count}/6 → {fix_result['st_count']}/6")
            else:
                self.stats['failed'] += 1
                print(f"  [FAIL] 会場{venue_code} {race_date} {race_number}R: {fix_result['error']}")

            # レート制限
            time.sleep(delay)

        # 結果サマリー
        elapsed_total = time.time() - start_time

        print("\n" + "="*80)
        print("修正結果サマリー")
        print("="*80)
        print(f"総レース数: {self.stats['total']}")
        print(f"成功: {self.stats['success']}")
        print(f"失敗: {self.stats['failed']}")
        print(f"スキップ: {self.stats['skipped']}")
        print(f"実行時間: {elapsed_total/60:.1f}分")

        if self.stats['fixed_st_count']:
            print("\n修正後のST時間数:")
            for st_count in sorted(self.stats['fixed_st_count'].keys(), reverse=True):
                count = self.stats['fixed_st_count'][st_count]
                print(f"  {st_count}/6 ST時間: {count}レース")

        if not self.test_mode:
            print("\n[OK] データベースの更新が完了しました。")
            print("次のコマンドで確認してください:")
            print(f"  python verify_db_integrity.py --start {start_date} --end {end_date}")
        else:
            print("\n[OK] テストモードで実行しました。実際の更新は行われていません。")
            print("本番実行する場合は --test オプションを外してください。")

        print("="*80)


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='ST時間修正スクリプト')
    parser.add_argument('--start', type=str, required=True,
                        help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True,
                        help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--limit', type=int, default=None,
                        help='最大修正レース数（テスト用）')
    parser.add_argument('--delay', type=float, default=0.5,
                        help='レート制限用遅延時間（秒）、デフォルト: 0.5')
    parser.add_argument('--test', action='store_true',
                        help='テストモード（実際の更新を行わない）')
    parser.add_argument('--db', type=str, default='data/boatrace.db',
                        help='データベースパス')

    args = parser.parse_args()

    # 日付バリデーション
    try:
        datetime.strptime(args.start, '%Y-%m-%d')
        datetime.strptime(args.end, '%Y-%m-%d')
    except ValueError:
        print("エラー: 日付は YYYY-MM-DD 形式で指定してください")
        return

    # 修正実行
    fixer = STTimeFixer(db_path=args.db, test_mode=args.test)
    fixer.run(args.start, args.end, limit=args.limit, delay=args.delay)


if __name__ == '__main__':
    main()
