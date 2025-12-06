"""
オリジナル展示データ収集ワークフロー

バックグラウンド処理・UI両方から呼び出される共通ロジック
"""
import os
import sys
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable
import logging

logger = logging.getLogger(__name__)


class TenjiCollectionWorkflow:
    """
    オリジナル展示データ収集ワークフロー

    使用例:
        workflow = TenjiCollectionWorkflow(
            db_path='data/boatrace.db',
            progress_callback=lambda step, msg, pct: print(f"[{pct}%] {step}: {msg}")
        )
        workflow.run(target_date=datetime.now().date())
    """

    def __init__(
        self,
        db_path: str = None,
        project_root: str = None,
        progress_callback: Callable[[str, str, int], None] = None
    ):
        """
        Args:
            db_path: データベースパス
            project_root: プロジェクトルートパス
            progress_callback: 進捗コールバック関数 (step, message, progress_percent)
        """
        self.project_root = project_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), '../..')
        )
        self.db_path = db_path or os.path.join(self.project_root, 'data/boatrace.db')
        self.progress_callback = progress_callback or self._default_progress

    def _default_progress(self, step: str, message: str, progress: int):
        """デフォルトの進捗表示"""
        print(f"[{progress}%] {step}: {message}")

    def _update_progress(self, step: str, message: str, progress: int):
        """進捗を更新"""
        self.progress_callback(step, message, progress)

    def run(self, target_date=None, days_offset: int = 0) -> Dict:
        """
        ワークフロー全体を実行

        Args:
            target_date: 対象日（datetime.date or str）
            days_offset: 日数オフセット（0=今日, -1=昨日）

        Returns:
            実行結果の辞書
        """
        result = {
            'success': False,
            'races_collected': 0,
            'venues_success': 0,
            'venues_total': 0,
            'errors': []
        }

        try:
            # 対象日を決定
            if target_date is None:
                target_date = datetime.now().date() + timedelta(days=days_offset)
            elif isinstance(target_date, str):
                target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

            self._update_progress(
                "初期化",
                f"{target_date} のオリジナル展示データ収集を開始",
                0
            )

            # データベースから開催レースを取得
            races = self._get_scheduled_races(target_date)

            if not races:
                logger.warning(f"{target_date} に開催されるレースが見つかりません")
                result['success'] = True
                result['message'] = f"{target_date} の開催レースなし"
                return result

            # 会場ごとにグループ化
            venues_dict = {}
            for race_id, venue_code, race_date, race_number in races:
                if venue_code not in venues_dict:
                    venues_dict[venue_code] = []
                venues_dict[venue_code].append((race_id, race_date, race_number))

            result['venues_total'] = len(venues_dict)

            self._update_progress(
                "データ収集",
                f"{len(venues_dict)}会場 × {len(races)}レース のデータ収集開始",
                10
            )

            # 収集処理
            collected_count = 0
            total_races = len(races)

            # UnifiedTenjiCollectorをインポート（遅延読み込み）
            from src.scraper.unified_tenji_collector import UnifiedTenjiCollector
            collector = UnifiedTenjiCollector(headless=True, timeout=15)

            for venue_idx, (venue_code, venue_races) in enumerate(venues_dict.items(), 1):
                venue_success = 0

                for race_id, race_date, race_number in venue_races:
                    try:
                        # オリジナル展示データを取得
                        tenji_data = collector.get_original_tenji(
                            venue_code, target_date, race_number
                        )

                        if tenji_data:
                            # データベースに保存
                            if self._save_tenji_to_db(venue_code, race_date, race_number, tenji_data):
                                collected_count += 1
                                venue_success += 1

                        # 進捗更新
                        progress = int(10 + (collected_count / total_races) * 85)
                        self._update_progress(
                            "データ収集",
                            f"{venue_code} R{race_number:2d} 収集中... ({collected_count}/{total_races})",
                            progress
                        )

                    except Exception as e:
                        logger.warning(f"{venue_code} R{race_number} 収集エラー: {e}")
                        result['errors'].append(f"{venue_code} R{race_number}: {str(e)[:100]}")

                if venue_success > 0:
                    result['venues_success'] += 1

            # クリーンアップ
            collector.close()

            # 最終結果
            result['success'] = True
            result['races_collected'] = collected_count
            result['message'] = f"{target_date} 収集完了: {collected_count}/{total_races}レース"

            self._update_progress(
                "完了",
                result['message'],
                100
            )

        except Exception as e:
            result['errors'].append(str(e))
            result['message'] = f"エラー: {str(e)[:200]}"
            logger.exception("ワークフロー実行エラー")

        return result

    def _get_scheduled_races(self, target_date) -> list:
        """指定日の開催レースを取得（DBになければスケジュールから取得）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        date_str = target_date.strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT id, venue_code, race_date, race_number
            FROM races
            WHERE race_date = ?
            ORDER BY venue_code, race_number
        """, (date_str,))

        rows = cursor.fetchall()
        conn.close()

        # DBにレースがある場合はそのまま返す
        if rows:
            return rows

        # DBにレースがない場合、月間スケジュールから開催場を取得
        logger.info(f"DB内に {date_str} のレースがありません。スケジュールから取得します。")

        try:
            from src.scraper.schedule_scraper import ScheduleScraper
            scraper = ScheduleScraper()

            # 対象月のスケジュールを取得
            schedule = scraper.get_monthly_schedule(target_date.year, target_date.month)
            scraper.close()

            # 対象日に開催している会場を抽出
            target_date_str = target_date.strftime('%Y%m%d')
            venues_today = []
            for venue_code, dates in schedule.items():
                if target_date_str in dates:
                    venues_today.append(venue_code)

            if not venues_today:
                logger.warning(f"{date_str} は開催日ではありません")
                return []

            # 各会場の全12レースを仮想的なレースリストとして返す
            # (race_id=None, venue_code, race_date, race_number) の形式
            virtual_races = []
            for venue_code in sorted(venues_today):
                for race_number in range(1, 13):
                    virtual_races.append((None, venue_code, date_str, race_number))

            logger.info(f"スケジュールから {len(venues_today)} 会場 × 12レース = {len(virtual_races)} レースを取得")
            return virtual_races

        except Exception as e:
            logger.error(f"スケジュール取得エラー: {e}")
            return []

    def _save_tenji_to_db(self, venue_code: str, date_str: str, race_number: int, tenji_data: dict) -> bool:
        """オリジナル展示データをデータベースに保存"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # race_idを取得
            cursor.execute('''
                SELECT id FROM races
                WHERE venue_code = ? AND race_date = ? AND race_number = ?
            ''', (venue_code, date_str, race_number))

            race_result = cursor.fetchone()

            if not race_result:
                # レースが存在しない場合は新規作成
                cursor.execute('''
                    INSERT INTO races (venue_code, race_date, race_number)
                    VALUES (?, ?, ?)
                ''', (venue_code, date_str, race_number))
                race_id = cursor.lastrowid
                logger.info(f"新規レース作成: {venue_code} {date_str} R{race_number} (id={race_id})")
            else:
                race_id = race_result[0]
            update_count = 0

            # 各艇のデータを保存
            for boat_num, data in tenji_data.items():
                if boat_num == 'source':  # メタデータはスキップ
                    continue

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
            logger.error(f"DB保存エラー ({venue_code} R{race_number}): {e}")
            return False
