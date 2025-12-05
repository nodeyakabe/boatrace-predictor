"""
今日の予測生成ワークフロー

バックグラウンド処理・UI両方から呼び出される共通ロジック
"""
import os
import sys
import sqlite3
import subprocess
import concurrent.futures
import threading
from datetime import datetime
from typing import Dict, Optional, Callable
import logging

logger = logging.getLogger(__name__)


class TodayPredictionWorkflow:
    """
    今日の予測生成ワークフロー

    使用例:
        workflow = TodayPredictionWorkflow(
            db_path='data/boatrace.db',
            progress_callback=lambda step, msg, pct: print(f"[{pct}%] {step}: {msg}")
        )
        workflow.run()
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

        # 並列処理用の共有カウンター
        self._parallel_lock = threading.Lock()
        self._beforeinfo_count = 0
        self._beforeinfo_total = 0
        self._odds_count = 0
        self._odds_total = 0

    def _default_progress(self, step: str, message: str, progress: int):
        """デフォルトの進捗表示"""
        print(f"[{progress}%] {step}: {message}")

    def _update_parallel_progress(self):
        """並列処理の統合進捗を更新（スレッドセーフ）"""
        with self._parallel_lock:
            total_count = self._beforeinfo_count + self._odds_count
            total_total = self._beforeinfo_total + self._odds_total

            if total_total == 0:
                return

            pct = 26 + int((total_count / total_total) * 13)  # 26-39%
            self._update_progress(
                "Step 2-3/6",
                f"直前情報・オッズ取得中... ({total_count}/{total_total})",
                pct
            )

    def _update_progress(self, step: str, message: str, progress: int):
        """進捗を更新"""
        self.progress_callback(step, message, progress)

    def run(self) -> Dict:
        """
        ワークフロー全体を実行（並列化最適化版）

        Returns:
            実行結果の辞書
        """
        result = {
            'success': False,
            'races_fetched': 0,
            'predictions_generated': 0,
            'odds_fetched': 0,
            'errors': []
        }

        try:
            # Step 1: データ取得
            today_schedule = self.fetch_today_data()
            result['races_fetched'] = self._count_today_races()

            if not today_schedule:
                logger.warning("今日のスケジュールが取得できませんでした")
                result['success'] = True
                return result

            # Step 2-3: 並列実行（DBビュー更新、直前情報取得、オッズ取得）
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                # 3つの独立した処理を並列実行
                future_db_views = executor.submit(self.update_db_views)
                future_beforeinfo = executor.submit(self.fetch_beforeinfo, today_schedule)
                future_odds = executor.submit(self.fetch_odds, today_schedule)

                # 完了を待機
                concurrent.futures.wait([future_db_views, future_beforeinfo, future_odds])

                # 結果を取得（エラーがあっても続行）
                try:
                    future_db_views.result()
                except Exception as e:
                    logger.warning(f"DBビュー更新エラー: {e}")

                try:
                    result['beforeinfo_fetched'] = future_beforeinfo.result()
                except Exception as e:
                    logger.warning(f"直前情報取得エラー: {e}")
                    result['beforeinfo_fetched'] = 0

                try:
                    result['odds_fetched'] = future_odds.result()
                except Exception as e:
                    logger.warning(f"オッズ取得エラー: {e}")
                    result['odds_fetched'] = 0

            # 並列処理完了後の最終メッセージ
            self._update_progress(
                "Step 2-3/6",
                f"直前情報・オッズ取得完了 (直前:{result.get('beforeinfo_fetched', 0)}, オッズ:{result.get('odds_fetched', 0)})",
                39
            )

            # Step 4: 法則再解析
            self.reanalyze_rules()

            # Step 5: 予測生成
            self.generate_predictions(today_schedule)

            # Step 6: 統計更新
            stats = self.update_stats()
            result['predictions_generated'] = stats.get('prediction_count', 0)

            result['success'] = True

        except Exception as e:
            result['errors'].append(str(e))
            logger.exception("ワークフロー実行エラー")

        return result

    def fetch_today_data(self) -> Dict[str, str]:
        """
        Step 1: 本日のデータを取得

        Returns:
            {venue_code: race_date} のスケジュール辞書
        """
        self._update_progress("Step 1/6", "本日のデータを確認中...", 5)

        today = datetime.now().strftime('%Y-%m-%d')
        today_yyyymmdd = today.replace('-', '')

        # 既存データをチェック
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT DISTINCT venue_code FROM races WHERE race_date = ?",
            (today,)
        )
        existing_venues = {row[0] for row in cursor.fetchall()}

        cursor.execute(
            "SELECT COUNT(*) FROM races WHERE race_date = ?",
            (today,)
        )
        existing_race_count = cursor.fetchone()[0]
        conn.close()

        # 既に十分なデータがあればスキップ
        if existing_race_count >= len(existing_venues) * 12 * 0.8 and len(existing_venues) >= 1:
            self._update_progress(
                "Step 1/6",
                f"既存データ使用 ({len(existing_venues)}会場, {existing_race_count}レース)",
                15
            )
            return {vc: today_yyyymmdd for vc in existing_venues}

        # データ不足の場合はスクレイピング
        from src.scraper.bulk_scraper import BulkScraper
        from src.database.data_manager import DataManager

        scraper = BulkScraper()
        data_manager = DataManager(self.db_path)
        today_schedule = {}

        # 今日のスケジュールを取得
        schedule = scraper.schedule_scraper.get_today_schedule()

        if schedule:
            for venue_code in schedule.keys():
                today_schedule[venue_code] = today_yyyymmdd

            # 未取得の会場のみ取得
            venues_to_fetch = [vc for vc in today_schedule.keys() if vc not in existing_venues]

            if not venues_to_fetch:
                self._update_progress(
                    "Step 1/6",
                    f"全会場取得済み ({len(today_schedule)}会場)",
                    15
                )
                return today_schedule

            total_venues = len(venues_to_fetch)
            saved_count = 0

            for i, venue_code in enumerate(venues_to_fetch, 1):
                pct = 5 + int((i / total_venues) * 10)
                self._update_progress(
                    "Step 1/6",
                    f"会場 {venue_code} を取得中... ({i}/{total_venues})",
                    pct
                )

                try:
                    result = scraper.fetch_multiple_venues(
                        venue_codes=[venue_code],
                        race_date=today_yyyymmdd,
                        race_count=12
                    )

                    # 取得したデータをDBに保存
                    if venue_code in result:
                        for race_data in result[venue_code]:
                            if race_data and isinstance(race_data, dict):
                                if data_manager.save_race_data(race_data):
                                    saved_count += 1

                except Exception as e:
                    logger.warning(f"会場 {venue_code} 取得エラー: {e}")

            logger.info(f"保存完了: {saved_count}レース")

        self._update_progress(
            "Step 1/6",
            f"データ取得完了 ({len(today_schedule)}会場)",
            15
        )
        return today_schedule

    def update_db_views(self):
        """Step 2: DBビューを更新"""
        self._update_progress("Step 2/6", "DBビューを更新中...", 20)

        try:
            from src.database.views import initialize_views
            initialize_views(self.db_path)
            self._update_progress("Step 2/6", "DBビュー更新完了", 25)
        except Exception as e:
            logger.warning(f"DBビュー更新エラー: {e}")

    def fetch_beforeinfo(self, today_schedule: Dict[str, str]) -> int:
        """
        Step 2.5: 直前情報を取得（並列実行対応）

        Returns:
            取得成功したレース数
        """

        from src.scraper.beforeinfo_scraper import BeforeInfoScraper

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        all_races = []
        for venue_code, race_date in today_schedule.items():
            race_date_iso = f"{race_date[:4]}-{race_date[4:6]}-{race_date[6:8]}"
            cursor.execute("""
                SELECT id, race_number FROM races
                WHERE venue_code = ? AND race_date = ?
                ORDER BY race_number
            """, (venue_code, race_date_iso))

            for row in cursor.fetchall():
                all_races.append({
                    'race_id': row[0],
                    'venue_code': venue_code,
                    'race_date': race_date,
                    'race_number': row[1]
                })
        conn.close()

        if not all_races:
            return 0

        # 合計数を設定
        with self._parallel_lock:
            self._beforeinfo_total = len(all_races)

        def fetch_single_beforeinfo(race_info):
            try:
                scraper = BeforeInfoScraper(delay=0.2)
                beforeinfo = scraper.get_race_beforeinfo(
                    race_info['venue_code'],
                    race_info['race_date'],
                    race_info['race_number']
                )

                if beforeinfo and beforeinfo.get('is_published'):
                    # DB保存
                    success = scraper.save_to_db(
                        race_info['race_id'],
                        beforeinfo,
                        self.db_path
                    )
                    scraper.close()

                    # 成功したら統合進捗を更新
                    with self._parallel_lock:
                        self._beforeinfo_count += 1
                    self._update_parallel_progress()
                    return success
                else:
                    scraper.close()
                    with self._parallel_lock:
                        self._beforeinfo_count += 1
                    self._update_parallel_progress()
                    return False
            except Exception:
                with self._parallel_lock:
                    self._beforeinfo_count += 1
                self._update_parallel_progress()
                return False

        success_count = 0
        total = len(all_races)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(fetch_single_beforeinfo, race): race for race in all_races}

            for future in concurrent.futures.as_completed(futures, timeout=300):
                if future.result():
                    success_count += 1

        return success_count

    def fetch_odds(self, today_schedule: Dict[str, str]) -> int:
        """
        Step 3: オッズを取得（並列実行対応）

        Returns:
            取得成功したレース数
        """
        from src.scraper.odds_scraper import OddsScraper

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        all_races = []
        for venue_code, race_date in today_schedule.items():
            race_date_iso = f"{race_date[:4]}-{race_date[4:6]}-{race_date[6:8]}"
            cursor.execute("""
                SELECT id, race_number FROM races
                WHERE venue_code = ? AND race_date = ?
                ORDER BY race_number
            """, (venue_code, race_date_iso))

            for row in cursor.fetchall():
                all_races.append({
                    'race_id': row[0],
                    'venue_code': venue_code,
                    'race_date': race_date,
                    'race_number': row[1]
                })
        conn.close()

        if not all_races:
            return 0

        # 合計数を設定
        with self._parallel_lock:
            self._odds_total = len(all_races)

        def fetch_single_odds(race_info):
            try:
                scraper = OddsScraper(delay=0.1, max_retries=1)
                odds = scraper.get_trifecta_odds(
                    race_info['venue_code'],
                    race_info['race_date'],
                    race_info['race_number']
                )
                scraper.close()

                if odds and len(odds) > 50:
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM trifecta_odds WHERE race_id = ?",
                        (race_info['race_id'],)
                    )
                    for combo, odds_val in odds.items():
                        cursor.execute(
                            "INSERT INTO trifecta_odds (race_id, combination, odds) VALUES (?, ?, ?)",
                            (race_info['race_id'], combo, odds_val)
                        )
                    conn.commit()
                    conn.close()

                    # 成功したら統合進捗を更新
                    with self._parallel_lock:
                        self._odds_count += 1
                    self._update_parallel_progress()
                    return True
                else:
                    with self._parallel_lock:
                        self._odds_count += 1
                    self._update_parallel_progress()
                    return False
            except Exception:
                with self._parallel_lock:
                    self._odds_count += 1
                self._update_parallel_progress()
                return False

        success_count = 0
        total = len(all_races)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(fetch_single_odds, race): race for race in all_races}

            for future in concurrent.futures.as_completed(futures, timeout=300):
                if future.result():
                    success_count += 1

        return success_count

    def reanalyze_rules(self):
        """Step 4: 法則を再解析"""
        self._update_progress("Step 4/6", "法則を再解析中...", 50)

        try:
            from src.analysis.pattern_analyzer import PatternAnalyzer

            analyzer = PatternAnalyzer(db_path=self.db_path)
            analyzer.analyze_all_venues(days=90)
            self._update_progress("Step 4/6", "法則再解析完了", 55)
        except Exception as e:
            logger.warning(f"法則再解析エラー: {e}")

    def generate_predictions(self, today_schedule: Dict[str, str]):
        """Step 5: 予測を生成"""
        self._update_progress("Step 5/6", "予測を生成中...", 60)

        from src.utils.date_utils import to_iso_format

        if not today_schedule:
            self._update_progress("Step 5/6", "予測対象なし", 85)
            return

        target_date = to_iso_format(list(today_schedule.values())[0])

        script_path = os.path.join(
            self.project_root, 'scripts', 'fast_prediction_generator.py'
        )

        if os.path.exists(script_path):
            try:
                result = subprocess.run(
                    [sys.executable, script_path, '--date', target_date],
                    capture_output=True,
                    text=True,
                    cwd=self.project_root,
                    timeout=600
                )
                if result.returncode == 0:
                    self._update_progress("Step 5/6", "予測生成完了", 85)
                else:
                    logger.warning(f"予測生成エラー: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.warning("予測生成タイムアウト")
        else:
            logger.warning(f"スクリプトが見つかりません: {script_path}")

    def update_stats(self) -> Dict:
        """
        Step 6: 統計を更新

        Returns:
            統計情報の辞書
        """
        self._update_progress("Step 6/6", "統計を更新中...", 90)

        stats = {'prediction_count': 0, 'odds_count': 0}

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            today = datetime.now().strftime('%Y-%m-%d')

            cursor.execute("""
                SELECT COUNT(DISTINCT rp.race_id)
                FROM race_predictions rp
                JOIN races r ON rp.race_id = r.id
                WHERE r.race_date = ?
            """, (today,))
            stats['prediction_count'] = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(DISTINCT race_id) FROM trifecta_odds to_
                JOIN races r ON to_.race_id = r.id
                WHERE r.race_date = ?
            """, (today,))
            stats['odds_count'] = cursor.fetchone()[0]

            conn.close()

            self._update_progress(
                "Step 6/6",
                f"完了: 予測{stats['prediction_count']}レース, オッズ{stats['odds_count']}レース",
                100
            )
        except Exception as e:
            logger.warning(f"統計更新エラー: {e}")

        return stats

    def _count_today_races(self) -> int:
        """今日のレース数をカウント"""
        today = datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM races WHERE race_date = ?",
            (today,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count
