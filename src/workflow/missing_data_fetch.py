"""
不足データ取得ワークフロー

バックグラウンド処理・UI両方から呼び出される共通ロジック

=== 2カテゴリ設計 ===

【直前情報取得】（レース前に取得可能）
- 展示タイム・チルト・部品交換 → BeforeInfoScraperで直接取得
- オッズ → OddsScraperで直接取得（当日のみ）

【当日確定情報】（レース後に取得）
- レース基本情報 → BulkScraperで取得
- 結果データ → ResultScraperで取得
- 補完スクリプト → 決まり手、払戻、天候、風向など
"""
import os
import sys
import sqlite3
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable
import logging

logger = logging.getLogger(__name__)

# 当日確定情報で実行する補完スクリプト（結果データに依存）
CONFIRMED_DATA_SCRIPTS = [
    ("補完_レース詳細データ_改善版v4.py", "レース詳細（ST/コース）"),
    ("補完_決まり手データ_改善版.py", "決まり手"),
    ("補完_払戻金データ.py", "払戻金"),
]

# 直前情報取得で実行する補完スクリプト（結果に依存しない）
BEFOREINFO_SCRIPTS = [
    ("補完_展示タイム_全件_高速化.py", "展示タイム"),
    ("補完_天候データ_改善版.py", "天候データ"),
    ("補完_風向データ_改善版.py", "風向データ"),
    ("収集_潮位データ_最新.py", "潮位データ"),
]


class MissingDataFetchWorkflow:
    """
    不足データ取得ワークフロー

    使用例:
        workflow = MissingDataFetchWorkflow(
            db_path='data/boatrace.db',
            progress_callback=lambda step, msg, pct: print(f"[{pct}%] {step}: {msg}")
        )
        workflow.run(missing_dates=[...], check_types=['当日確定情報'])
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

    def run(
        self,
        missing_dates: List[Dict] = None,
        check_types: List[str] = None
    ) -> Dict:
        """
        ワークフロー全体を実行

        Args:
            missing_dates: 不足データの日付リスト [{'日付': '2024-01-01', 'レース': 0, '問題': '...'}, ...]
            check_types: 取得対象 ['直前情報取得', '当日確定情報']

        Returns:
            実行結果の辞書
        """
        missing_dates = missing_dates or []
        check_types = check_types or []

        result = {
            'success': False,
            'processed': 0,
            'errors': 0,
            'total_steps': 0,
            'error_messages': []
        }

        if not missing_dates and not check_types:
            result['success'] = True
            result['message'] = '取得対象データがありません'
            return result

        try:
            is_beforeinfo_mode = "直前情報取得" in check_types
            is_confirmed_mode = "当日確定情報" in check_types

            # 各フェーズの対象を計算
            races_without_beforeinfo = []
            races_without_odds = []
            beforeinfo_scripts_to_run = []

            if is_beforeinfo_mode:
                races_without_beforeinfo = self._get_races_without_beforeinfo()
                races_without_odds = self._get_races_without_odds()
                beforeinfo_scripts_to_run = BEFOREINFO_SCRIPTS

            missing_race_dates = []
            races_without_results = []
            scripts_to_run = []

            if is_confirmed_mode:
                for item in missing_dates:
                    if item.get('レース', 0) == 0:
                        missing_race_dates.append(item['日付'])
                races_without_results = self._get_races_without_results()
                scripts_to_run = CONFIRMED_DATA_SCRIPTS

            # 総ステップ数を計算
            result_steps = (len(races_without_results) + 99) // 100 if races_without_results else 0
            beforeinfo_steps = (len(races_without_beforeinfo) + 99) // 100 if races_without_beforeinfo else 0
            odds_steps = (len(races_without_odds) + 49) // 50 if races_without_odds else 0

            total_steps = (
                len(missing_race_dates) +
                result_steps +
                beforeinfo_steps +
                odds_steps +
                len(scripts_to_run) +
                len(beforeinfo_scripts_to_run)
            )

            result['total_steps'] = total_steps

            if total_steps == 0:
                result['success'] = True
                result['message'] = '処理対象がありません'
                return result

            current_step = 0
            processed = 0
            errors = 0

            # フェーズ1: レース基本情報の取得
            if missing_race_dates:
                current_step, processed, errors = self._fetch_race_info(
                    missing_race_dates, current_step, total_steps, processed, errors
                )

            # フェーズ1.5: 結果データの取得
            if races_without_results:
                current_step, processed, errors = self._fetch_results(
                    races_without_results, current_step, total_steps,
                    result_steps, processed, errors
                )

            # フェーズ2: 直前情報の直接取得
            if races_without_beforeinfo:
                current_step, processed, errors = self._fetch_beforeinfo(
                    races_without_beforeinfo, current_step, total_steps,
                    beforeinfo_steps, processed, errors
                )

            # フェーズ3: オッズの取得（当日レースのみ）
            if races_without_odds:
                current_step, processed, errors = self._fetch_odds(
                    races_without_odds, current_step, total_steps,
                    odds_steps, processed, errors
                )

            # フェーズ3.5: 直前情報補完スクリプトの実行
            if beforeinfo_scripts_to_run:
                current_step, processed, errors = self._run_scripts(
                    beforeinfo_scripts_to_run, "フェーズ3.5",
                    current_step, total_steps, processed, errors
                )

            # フェーズ4: 補完スクリプトの実行（当日確定情報モードのみ）
            if scripts_to_run:
                current_step, processed, errors = self._run_scripts(
                    scripts_to_run, "フェーズ4",
                    current_step, total_steps, processed, errors
                )

            result['success'] = True
            result['processed'] = processed
            result['errors'] = errors

            message = f'{total_steps}ステップ完了（処理: {processed}件）'
            if errors > 0:
                message += f'（エラー: {errors}件）'
            result['message'] = message

        except Exception as e:
            result['error_messages'].append(str(e))
            result['message'] = f'エラー: {str(e)[:200]}'
            logger.exception("ワークフロー実行エラー")

        return result

    def _get_races_without_results(self) -> List:
        """結果データがないレースを取得（過去日のみ）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT
                r.id,
                r.venue_code,
                r.race_date,
                r.race_number
            FROM races r
            WHERE r.id NOT IN (SELECT DISTINCT race_id FROM results)
              AND r.race_date < date('now')
            ORDER BY r.race_date DESC, r.venue_code, r.race_number
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        return rows

    def _get_races_without_beforeinfo(self) -> List:
        """直前情報（展示タイム）がないレースを取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT DISTINCT
                r.id,
                r.venue_code,
                r.race_date,
                r.race_number
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            WHERE (rd.race_id IS NULL OR rd.exhibition_time IS NULL)
              AND r.race_status = 'completed'
            ORDER BY r.race_date DESC, r.venue_code, r.race_number
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        return rows

    def _get_races_without_odds(self) -> List:
        """オッズデータがないレースを取得（当日レースのみ）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        today = datetime.now().strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='odds'
        """)
        if not cursor.fetchone():
            conn.close()
            return []

        query = """
            SELECT
                r.id,
                r.venue_code,
                r.race_date,
                r.race_number
            FROM races r
            WHERE r.race_date = ?
              AND r.id NOT IN (SELECT DISTINCT race_id FROM odds WHERE race_id IS NOT NULL)
            ORDER BY r.venue_code, r.race_number
        """

        cursor.execute(query, (today,))
        rows = cursor.fetchall()
        conn.close()

        return rows

    def _fetch_race_info(
        self, missing_race_dates: List[str],
        current_step: int, total_steps: int,
        processed: int, errors: int
    ) -> tuple:
        """フェーズ1: レース基本情報の取得"""
        self._update_progress(
            "フェーズ1",
            f'{len(missing_race_dates)}日分のレース情報を取得中...',
            int((current_step / total_steps) * 100)
        )

        from src.scraper.bulk_scraper import BulkScraper
        from src.database.data_manager import DataManager

        scraper = BulkScraper()
        data_manager = DataManager(self.db_path)

        for idx, date_str in enumerate(missing_race_dates, 1):
            try:
                progress = int((current_step / total_steps) * 100)
                self._update_progress(
                    "フェーズ1",
                    f'{date_str} のレース情報を取得中... ({idx}/{len(missing_race_dates)})',
                    progress
                )

                venue_codes = [f"{i:02d}" for i in range(1, 25)]
                date_formatted = date_str.replace('-', '')

                result = scraper.fetch_multiple_venues(
                    venue_codes=venue_codes,
                    race_date=date_formatted,
                    race_count=12
                )

                # 取得したデータをDBに保存
                saved_count = 0
                for venue_code, races in result.items():
                    for race_data in races:
                        if race_data and isinstance(race_data, dict):
                            if data_manager.save_race_data(race_data):
                                saved_count += 1

                current_step += 1
                processed += 1
                logger.info(f"{date_str}: {saved_count}レース保存")

            except Exception as e:
                errors += 1
                current_step += 1
                logger.warning(f"{date_str} 取得エラー: {e}")

        return current_step, processed, errors

    def _fetch_results(
        self, races_without_results: List,
        current_step: int, total_steps: int, result_steps: int,
        processed: int, errors: int
    ) -> tuple:
        """フェーズ1.5: 結果データの取得"""
        self._update_progress(
            "フェーズ1.5",
            f'{len(races_without_results)}レースの結果データを取得中...',
            int((current_step / total_steps) * 100)
        )

        from src.scraper.result_scraper import ResultScraper
        from src.database.data_manager import DataManager

        result_success = 0
        result_error = 0

        for idx, (race_id, venue_code, race_date, race_number) in enumerate(races_without_results, 1):
            try:
                date_str = race_date.replace('-', '')
                scraper = ResultScraper()
                result = scraper.fetch_result(venue_code, date_str, race_number)
                scraper.close()

                if result and result.get('results'):
                    data_manager = DataManager(self.db_path)
                    data_manager.save_race_result(result)
                    result_success += 1
                else:
                    result_error += 1

                # 進捗を20件ごとに更新（UI表示用）
                if idx % 20 == 0 or idx == 1:
                    # 全体進捗を計算（結果取得フェーズ内での進捗）
                    phase_progress = idx / len(races_without_results)
                    overall_progress = int((current_step + phase_progress * result_steps) / total_steps * 100)
                    self._update_progress(
                        "フェーズ1.5",
                        f'結果データを取得中... ({idx}/{len(races_without_results)})',
                        min(overall_progress, 99)  # 100%は完了時のみ
                    )

                if idx % 100 == 0:
                    current_step += 1

                time.sleep(0.1)

            except Exception as e:
                result_error += 1

        remaining_steps = result_steps - (len(races_without_results) // 100)
        current_step += max(1, remaining_steps)
        processed += result_success
        errors += result_error

        return current_step, processed, errors

    def _fetch_beforeinfo(
        self, races_without_beforeinfo: List,
        current_step: int, total_steps: int, beforeinfo_steps: int,
        processed: int, errors: int
    ) -> tuple:
        """フェーズ2: 直前情報の直接取得"""
        self._update_progress(
            "フェーズ2",
            f'{len(races_without_beforeinfo)}レースの直前情報を取得中...',
            int((current_step / total_steps) * 100)
        )

        from src.scraper.beforeinfo_scraper import BeforeInfoScraper

        beforeinfo_success = 0
        beforeinfo_error = 0

        for idx, (race_id, venue_code, race_date, race_number) in enumerate(races_without_beforeinfo, 1):
            try:
                date_str = race_date.replace('-', '')
                scraper = BeforeInfoScraper()
                beforeinfo = scraper.get_race_beforeinfo(venue_code, date_str, race_number)

                if beforeinfo:
                    exhibition_times = beforeinfo.get('exhibition_times', {})
                    tilt_angles = beforeinfo.get('tilt_angles', {})
                    parts_replacements = beforeinfo.get('parts_replacements', {})

                    if exhibition_times:
                        conn = sqlite3.connect(self.db_path)
                        cursor = conn.cursor()

                        for pit in range(1, 7):
                            ex_time = exhibition_times.get(pit)
                            tilt = tilt_angles.get(pit)
                            parts = parts_replacements.get(pit)

                            if ex_time or tilt or parts:
                                cursor.execute("""
                                    SELECT id FROM race_details WHERE race_id = ? AND pit_number = ?
                                """, (race_id, pit))
                                existing = cursor.fetchone()

                                if existing:
                                    cursor.execute("""
                                        UPDATE race_details
                                        SET exhibition_time = COALESCE(?, exhibition_time),
                                            tilt_angle = COALESCE(?, tilt_angle),
                                            parts_replacement = COALESCE(?, parts_replacement)
                                        WHERE race_id = ? AND pit_number = ?
                                    """, (ex_time, tilt, parts, race_id, pit))
                                else:
                                    cursor.execute("""
                                        INSERT INTO race_details (race_id, pit_number, exhibition_time, tilt_angle, parts_replacement)
                                        VALUES (?, ?, ?, ?, ?)
                                    """, (race_id, pit, ex_time, tilt, parts))

                        conn.commit()
                        conn.close()
                        beforeinfo_success += 1
                    else:
                        beforeinfo_error += 1
                else:
                    beforeinfo_error += 1

                if idx % 100 == 0:
                    current_step += 1
                    progress = int((current_step / total_steps) * 100)
                    self._update_progress(
                        "フェーズ2",
                        f'直前情報を取得中... ({idx}/{len(races_without_beforeinfo)})',
                        progress
                    )

                time.sleep(0.1)

            except Exception as e:
                beforeinfo_error += 1

        remaining_steps = beforeinfo_steps - (len(races_without_beforeinfo) // 100)
        current_step += max(1, remaining_steps)
        processed += beforeinfo_success
        errors += beforeinfo_error

        return current_step, processed, errors

    def _fetch_odds(
        self, races_without_odds: List,
        current_step: int, total_steps: int, odds_steps: int,
        processed: int, errors: int
    ) -> tuple:
        """フェーズ3: オッズの取得（当日レースのみ）"""
        self._update_progress(
            "フェーズ3",
            f'{len(races_without_odds)}レースのオッズを取得中...',
            int((current_step / total_steps) * 100)
        )

        from src.scraper.odds_scraper import OddsScraper
        from src.database.data_manager import DataManager

        odds_success = 0
        odds_error = 0

        for idx, (race_id, venue_code, race_date, race_number) in enumerate(races_without_odds, 1):
            try:
                date_str = race_date.replace('-', '')
                scraper = OddsScraper(delay=0.5)
                trifecta_odds = scraper.get_trifecta_odds(venue_code, date_str, race_number)

                if trifecta_odds:
                    data_manager = DataManager(self.db_path)
                    odds_data = {
                        'race_id': race_id,
                        'venue_code': venue_code,
                        'race_date': race_date,
                        'race_number': race_number,
                        'trifecta_odds': trifecta_odds
                    }
                    data_manager.save_odds(odds_data)
                    odds_success += 1
                else:
                    odds_error += 1

                if idx % 50 == 0:
                    current_step += 1
                    progress = int((current_step / total_steps) * 100)
                    self._update_progress(
                        "フェーズ3",
                        f'オッズを取得中... ({idx}/{len(races_without_odds)})',
                        progress
                    )

                time.sleep(0.5)

            except Exception as e:
                odds_error += 1

        remaining_steps = odds_steps - (len(races_without_odds) // 50)
        current_step += max(1, remaining_steps)
        processed += odds_success
        errors += odds_error

        return current_step, processed, errors

    def _run_scripts(
        self, scripts: List[tuple], phase_name: str,
        current_step: int, total_steps: int,
        processed: int, errors: int
    ) -> tuple:
        """補完スクリプトを実行"""
        self._update_progress(
            phase_name,
            f'{len(scripts)}種類のスクリプトを実行中...',
            int((current_step / total_steps) * 100)
        )

        for idx, (script_name, label) in enumerate(scripts, 1):
            try:
                progress = int((current_step / total_steps) * 100)
                self._update_progress(
                    phase_name,
                    f'{label}を実行中... ({idx}/{len(scripts)})',
                    progress
                )

                script_path = os.path.join(self.project_root, script_name)

                if not os.path.exists(script_path):
                    logger.warning(f"スクリプトが見つかりません: {script_name}")
                    errors += 1
                    current_step += 1
                    continue

                result = subprocess.run(
                    [sys.executable, script_path],
                    capture_output=True,
                    text=True,
                    cwd=self.project_root,
                    timeout=600,
                    encoding='utf-8',
                    errors='ignore'
                )

                if result.returncode != 0:
                    logger.warning(f"{label} 失敗: {result.stderr[:200]}")
                    errors += 1
                else:
                    processed += 1

                current_step += 1

            except subprocess.TimeoutExpired:
                logger.warning(f"{label} タイムアウト")
                errors += 1
                current_step += 1
            except Exception as e:
                logger.warning(f"{label} エラー: {e}")
                errors += 1
                current_step += 1

        return current_step, processed, errors
