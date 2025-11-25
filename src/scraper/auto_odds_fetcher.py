"""
オッズ自動取得機能
指定されたレースのオッズを自動的に取得してデータベースに保存
"""
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
import time

from src.scraper.odds_scraper import OddsScraper
from src.utils.date_utils import to_iso_format
from config.settings import DATABASE_PATH


class AutoOddsFetcher:
    """オッズ自動取得クラス"""

    def __init__(self, delay: float = 1.5):
        """
        初期化

        Args:
            delay: リクエスト間の遅延時間（秒）
        """
        self.odds_scraper = OddsScraper(delay=delay)
        self.db_path = DATABASE_PATH

    def fetch_odds_for_race(self, race_id: int, venue_code: str, race_date: str, race_number: int) -> Dict[str, bool]:
        """
        指定されたレースのオッズを取得してデータベースに保存

        Args:
            race_id: レースID
            venue_code: 会場コード
            race_date: レース日付 (YYYY-MM-DD または YYYYMMDD)
            race_number: レース番号

        Returns:
            {
                'trifecta_success': bool,
                'win_success': bool,
                'trifecta_count': int,
                'message': str
            }
        """
        # 日付フォーマット変換（YYYYMMDD形式に）
        if '-' in race_date:
            race_date_formatted = race_date.replace('-', '')
        else:
            race_date_formatted = race_date

        result = {
            'trifecta_success': False,
            'win_success': False,
            'trifecta_count': 0,
            'message': ''
        }

        try:
            # 3連単オッズを取得
            print(f"\n[INFO] 3連単オッズ取得開始: {venue_code} {race_date} {race_number}R")
            trifecta_odds = self.odds_scraper.get_trifecta_odds(venue_code, race_date_formatted, race_number)

            if trifecta_odds:
                # データベースに保存
                saved_count = self._save_trifecta_odds(race_id, trifecta_odds)
                result['trifecta_success'] = True
                result['trifecta_count'] = saved_count
                print(f"[OK] 3連単オッズ保存完了: {saved_count}通り")
            else:
                print(f"[WARNING] 3連単オッズ取得失敗")

            # 単勝オッズを取得
            print(f"[INFO] 単勝オッズ取得開始: {venue_code} {race_date} {race_number}R")
            win_odds = self.odds_scraper.get_win_odds(venue_code, race_date_formatted, race_number)

            if win_odds:
                # データベースに保存
                saved = self._save_win_odds(race_id, win_odds)
                result['win_success'] = saved
                print(f"[OK] 単勝オッズ保存完了: 6艇")
            else:
                print(f"[WARNING] 単勝オッズ取得失敗")

            # メッセージ作成
            if result['trifecta_success'] and result['win_success']:
                result['message'] = f"✅ 全オッズ取得成功"
            elif result['trifecta_success']:
                result['message'] = f"⚠️ 3連単のみ取得成功"
            elif result['win_success']:
                result['message'] = f"⚠️ 単勝のみ取得成功"
            else:
                result['message'] = f"❌ オッズ取得失敗"

        except Exception as e:
            print(f"[ERROR] オッズ取得エラー: {e}")
            import traceback
            traceback.print_exc()
            result['message'] = f"❌ エラー: {e}"

        return result

    def fetch_odds_for_today(self, today_schedule: Dict[str, str]) -> Dict:
        """
        本日の全レースのオッズを取得

        Args:
            today_schedule: {venue_code: race_date} の辞書

        Returns:
            {
                'total_races': int,
                'success_count': int,
                'failed_count': int,
                'details': List[Dict]
            }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 全レースリストを取得
        all_races = []
        for venue_code, race_date in today_schedule.items():
            race_date_formatted = to_iso_format(race_date)

            cursor.execute("""
                SELECT id, race_number
                FROM races
                WHERE venue_code = ? AND race_date = ?
                ORDER BY race_number
            """, (venue_code, race_date_formatted))

            for row in cursor.fetchall():
                all_races.append({
                    'race_id': row[0],
                    'venue_code': venue_code,
                    'race_date': race_date,
                    'race_number': row[1]
                })

        conn.close()

        print(f"\n{'='*70}")
        print(f"本日のオッズ自動取得開始: {len(all_races)}レース")
        print(f"{'='*70}")

        success_count = 0
        failed_count = 0
        details = []

        for idx, race in enumerate(all_races, 1):
            print(f"\n[{idx}/{len(all_races)}] {race['venue_code']} {race['race_number']}R")

            result = self.fetch_odds_for_race(
                race['race_id'],
                race['venue_code'],
                race['race_date'],
                race['race_number']
            )

            if result['trifecta_success'] or result['win_success']:
                success_count += 1
            else:
                failed_count += 1

            details.append({
                'venue_code': race['venue_code'],
                'race_number': race['race_number'],
                'result': result
            })

            # サーバー負荷軽減のため遅延
            if idx < len(all_races):
                time.sleep(self.odds_scraper.delay)

        print(f"\n{'='*70}")
        print(f"オッズ取得完了: 成功 {success_count} / 失敗 {failed_count}")
        print(f"{'='*70}")

        return {
            'total_races': len(all_races),
            'success_count': success_count,
            'failed_count': failed_count,
            'details': details
        }

    def _save_trifecta_odds(self, race_id: int, odds_data: Dict[str, float]) -> int:
        """
        3連単オッズをデータベースに保存

        Args:
            race_id: レースID
            odds_data: {'1-2-3': 12.5, ...}

        Returns:
            保存件数
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 既存データを削除（再取得の場合）
            cursor.execute("DELETE FROM trifecta_odds WHERE race_id = ?", (race_id,))

            # 新規データを挿入
            saved_count = 0
            for combination, odds in odds_data.items():
                cursor.execute("""
                    INSERT INTO trifecta_odds (race_id, combination, odds)
                    VALUES (?, ?, ?)
                """, (race_id, combination, odds))
                saved_count += 1

            conn.commit()
            return saved_count

        except Exception as e:
            print(f"[ERROR] 3連単オッズ保存エラー: {e}")
            if conn:
                conn.rollback()
            return 0

        finally:
            if conn:
                conn.close()

    def _save_win_odds(self, race_id: int, odds_data: Dict[int, float]) -> bool:
        """
        単勝オッズをデータベースに保存

        Args:
            race_id: レースID
            odds_data: {1: 1.5, 2: 3.2, ...}

        Returns:
            成功したかどうか
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 既存データを削除（再取得の場合）
            cursor.execute("DELETE FROM win_odds WHERE race_id = ?", (race_id,))

            # 新規データを挿入
            for pit_number, odds in odds_data.items():
                cursor.execute("""
                    INSERT INTO win_odds (race_id, pit_number, odds)
                    VALUES (?, ?, ?)
                """, (race_id, pit_number, odds))

            conn.commit()
            return True

        except Exception as e:
            print(f"[ERROR] 単勝オッズ保存エラー: {e}")
            if conn:
                conn.rollback()
            return False

        finally:
            if conn:
                conn.close()

    def get_race_odds(self, race_id: int) -> Optional[Dict]:
        """
        レースのオッズをデータベースから取得

        Args:
            race_id: レースID

        Returns:
            {
                'trifecta': {'1-2-3': 12.5, ...},
                'win': {1: 1.5, 2: 3.2, ...},
                'fetched_at': '2025-11-14 12:34:56'
            }
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 3連単オッズ取得
            cursor.execute("""
                SELECT combination, odds, fetched_at
                FROM trifecta_odds
                WHERE race_id = ?
                ORDER BY odds
            """, (race_id,))
            trifecta_rows = cursor.fetchall()

            # 単勝オッズ取得
            cursor.execute("""
                SELECT pit_number, odds, fetched_at
                FROM win_odds
                WHERE race_id = ?
                ORDER BY pit_number
            """, (race_id,))
            win_rows = cursor.fetchall()

            if not trifecta_rows and not win_rows:
                return None

            result = {
                'trifecta': {},
                'win': {},
                'fetched_at': None
            }

            for row in trifecta_rows:
                result['trifecta'][row[0]] = row[1]
                if not result['fetched_at']:
                    result['fetched_at'] = row[2]

            for row in win_rows:
                result['win'][row[0]] = row[1]
                if not result['fetched_at']:
                    result['fetched_at'] = row[2]

            return result

        except Exception as e:
            print(f"[ERROR] オッズ取得エラー: {e}")
            return None

        finally:
            if conn:
                conn.close()

    def close(self):
        """リソースクローズ"""
        self.odds_scraper.close()
