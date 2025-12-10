"""
不足データ取得ワークフロー（並列化版）

並列化改善ポイント:
1. 結果データ取得: 順次処理 → ThreadPoolExecutor（8-16スレッド）
2. オッズ取得: 順次処理 → ThreadPoolExecutor（4-8スレッド）
3. 期待速度: 約10-20倍高速化

改善前: 1レースあたり12秒 → 1634レース = 5.4時間
改善後: 並列16スレッド → 1634レース = 約20-40分
"""
import os
import sys
import sqlite3
import subprocess
import time
import concurrent.futures
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
    ("収集_潮位データ_最新.py", "潮位データ"),
]


class MissingDataFetchWorkflowParallel:
    """
    不足データ取得ワークフロー（並列化版）

    使用例:
        workflow = MissingDataFetchWorkflowParallel(
            db_path='data/boatrace.db',
            progress_callback=lambda step, msg, pct: print(f"[{pct}%] {step}: {msg}")
        )
        workflow.run(missing_dates=[...], check_types=['当日確定情報'])
    """

    def __init__(
        self,
        db_path: str = None,
        project_root: str = None,
        progress_callback: Callable[[str, str, int], None] = None,
        max_workers_results: int = 16,  # 結果取得の並列数
        max_workers_beforeinfo: int = 16,  # 直前情報取得の並列数（8→16に高速化）
        max_workers_odds: int = 20  # オッズ取得の並列数（高速化）
    ):
        """
        Args:
            db_path: データベースパス
            project_root: プロジェクトルートパス
            progress_callback: 進捗コールバック関数 (step, message, progress_percent)
            max_workers_results: 結果取得の最大並列数
            max_workers_beforeinfo: 直前情報取得の最大並列数
            max_workers_odds: オッズ取得の最大並列数
        """
        self.project_root = project_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), '../..')
        )
        self.db_path = db_path or os.path.join(self.project_root, 'data/boatrace.db')
        self.progress_callback = progress_callback or self._default_progress
        self.max_workers_results = max_workers_results
        self.max_workers_beforeinfo = max_workers_beforeinfo
        self.max_workers_odds = max_workers_odds

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
            missing_dates: 不足データの日付リスト
            check_types: 取得対象 ['直前情報取得', '当日確定情報']

        Returns:
            実行結果の辞書
        """
        missing_dates = missing_dates or []
        check_types = check_types or []

        # 期間情報を抽出
        if missing_dates:
            dates = [item['日付'] for item in missing_dates if '日付' in item]
            if dates:
                self.start_date = min(dates)
                self.end_date = max(dates)
            else:
                self.start_date = None
                self.end_date = None
        else:
            self.start_date = None
            self.end_date = None

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

            # フェーズ1.5: 結果データの取得（並列化版）
            if races_without_results:
                current_step, processed, errors = self._fetch_results_parallel(
                    races_without_results, current_step, total_steps,
                    result_steps, processed, errors
                )

            # フェーズ2: 直前情報の直接取得（既に並列化済み）
            if races_without_beforeinfo:
                current_step, processed, errors = self._fetch_beforeinfo(
                    races_without_beforeinfo, current_step, total_steps,
                    beforeinfo_steps, processed, errors
                )

            # フェーズ3: オッズの取得（並列化版）
            if races_without_odds:
                current_step, processed, errors = self._fetch_odds_parallel(
                    races_without_odds, current_step, total_steps,
                    odds_steps, processed, errors
                )

            # フェーズ3.5: 直前情報補完スクリプトの実行
            if beforeinfo_scripts_to_run:
                current_step, processed, errors = self._run_scripts(
                    beforeinfo_scripts_to_run, "フェーズ3.5",
                    current_step, total_steps, processed, errors
                )

            # フェーズ4: 補完スクリプトの実行
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
        """結果データがないレースを取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        date_filter = "AND r.race_date < date('now')"
        params = []

        if self.start_date and self.end_date:
            date_filter += " AND r.race_date BETWEEN ? AND ?"
            params.extend([self.start_date, self.end_date])
        elif self.start_date:
            date_filter += " AND r.race_date >= ?"
            params.append(self.start_date)
        elif self.end_date:
            date_filter += " AND r.race_date <= ?"
            params.append(self.end_date)

        query = f"""
            SELECT
                r.id,
                r.venue_code,
                r.race_date,
                r.race_number
            FROM races r
            WHERE r.id NOT IN (SELECT DISTINCT race_id FROM results)
              {date_filter}
            ORDER BY r.race_date DESC, r.venue_code, r.race_number
        """

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return rows

    def _get_races_without_beforeinfo(self) -> List:
        """直前情報がないレースを取得"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        date_filter = ""
        params = []

        if self.start_date and self.end_date:
            date_filter = " AND r.race_date BETWEEN ? AND ?"
            params.extend([self.start_date, self.end_date])
        elif self.start_date:
            date_filter = " AND r.race_date >= ?"
            params.append(self.start_date)
        elif self.end_date:
            date_filter = " AND r.race_date <= ?"
            params.append(self.end_date)

        query = f"""
            SELECT DISTINCT
                r.id,
                r.venue_code,
                r.race_date,
                r.race_number
            FROM races r
            LEFT JOIN race_details rd ON r.id = rd.race_id
            WHERE (rd.race_id IS NULL OR rd.exhibition_time IS NULL)
              AND r.race_status = 'completed'
              {date_filter}
            ORDER BY r.race_date DESC, r.venue_code, r.race_number
        """

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return rows

    def _get_races_without_odds(self) -> List:
        """オッズデータがないレースを取得（当日のみ）"""
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

    def _fetch_results_parallel(
        self, races_without_results: List,
        current_step: int, total_steps: int, result_steps: int,
        processed: int, errors: int
    ) -> tuple:
        """フェーズ1.5: 結果データの取得（並列化版）"""
        self._update_progress(
            "フェーズ1.5",
            f'{len(races_without_results)}レースの結果データを取得中...',
            int((current_step / total_steps) * 100)
        )

        from src.scraper.result_scraper import ResultScraper
        from src.database.data_manager import DataManager

        result_success = 0
        result_error = 0
        total = len(races_without_results)

        # 並列処理用の関数
        def fetch_single_result(race_info):
            """1レース分の結果を取得"""
            race_id, venue_code, race_date, race_number = race_info
            try:
                date_str = race_date.replace('-', '')
                scraper = ResultScraper()
                result = scraper.fetch_result(venue_code, date_str, race_number)
                scraper.close()

                if result and result.get('results'):
                    # DB保存（スレッドセーフなコネクション使用）
                    data_manager = DataManager(self.db_path)
                    data_manager.save_race_result(result)
                    return True
                else:
                    return False
            except Exception as e:
                logger.warning(f"結果取得エラー (race_id={race_id}): {e}")
                return False

        # ThreadPoolExecutorで並列処理
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers_results) as executor:
            futures = {
                executor.submit(fetch_single_result, race): race
                for race in races_without_results
            }

            # タイムアウトなし（個別タスクで制御）
            for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
                try:
                    # 個別タスクに60秒のタイムアウト
                    if future.result(timeout=60):
                        result_success += 1
                    else:
                        result_error += 1
                except concurrent.futures.TimeoutError:
                    result_error += 1
                    logger.warning(f"タイムアウト: {idx}件目のレース")
                except Exception as e:
                    result_error += 1
                    logger.warning(f"並列処理エラー: {e}")

                # 進捗表示（20件ごと、または最初と最後）
                if idx % 20 == 0 or idx == 1 or idx == total:
                    elapsed = time.time() - start_time
                    rate = idx / elapsed if elapsed > 0 else 0
                    remaining_sec = (total - idx) / rate if rate > 0 else 0

                    phase_progress = idx / total
                    overall_progress = int((current_step + phase_progress * result_steps) / total_steps * 100)

                    self._update_progress(
                        "フェーズ1.5",
                        f'結果データを取得中... ({idx}/{total}) - {rate:.1f}件/秒 - 残り約{remaining_sec/60:.0f}分',
                        min(overall_progress, 99)
                    )

                if idx % 100 == 0:
                    current_step += 1

        remaining_steps = result_steps - (total // 100)
        current_step += max(1, remaining_steps)
        processed += result_success
        errors += result_error

        elapsed_total = time.time() - start_time
        logger.info(f"結果取得完了: {result_success}件成功, {result_error}件失敗, 所要時間: {elapsed_total/60:.1f}分")

        return current_step, processed, errors

    def _fetch_beforeinfo(
        self, races_without_beforeinfo: List,
        current_step: int, total_steps: int, beforeinfo_steps: int,
        processed: int, errors: int
    ) -> tuple:
        """フェーズ2: 直前情報の直接取得（既に並列化済み）"""
        self._update_progress(
            "フェーズ2",
            f'{len(races_without_beforeinfo)}レースの直前情報を取得中...',
            int((current_step / total_steps) * 100)
        )

        from src.scraper.beforeinfo_scraper import BeforeInfoScraper

        beforeinfo_success = 0
        beforeinfo_error = 0

        def fetch_single_beforeinfo(race_info):
            """1レース分の直前情報を取得"""
            race_id, venue_code, race_date, race_number = race_info
            try:
                date_str = race_date.replace('-', '')
                scraper = BeforeInfoScraper(delay=0.05)
                beforeinfo = scraper.get_race_beforeinfo(venue_code, date_str, race_number)

                if beforeinfo and beforeinfo.get('is_published'):
                    success = scraper.save_to_db(race_id, beforeinfo, self.db_path)
                    scraper.close()
                    return success
                else:
                    scraper.close()
                    return False
            except Exception as e:
                logger.warning(f"直前情報取得エラー (race_id={race_id}): {e}")
                return False

        total = len(races_without_beforeinfo)

        # ThreadPoolExecutorで並列処理
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers_beforeinfo) as executor:
            futures = {
                executor.submit(fetch_single_beforeinfo, race): race
                for race in races_without_beforeinfo
            }

            for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
                try:
                    # 個別タスクに60秒のタイムアウト
                    if future.result(timeout=60):
                        beforeinfo_success += 1
                    else:
                        beforeinfo_error += 1
                except concurrent.futures.TimeoutError:
                    beforeinfo_error += 1
                    logger.warning(f"タイムアウト: {idx}件目の直前情報")
                except Exception as e:
                    beforeinfo_error += 1
                    logger.warning(f"並列処理エラー: {e}")

                # 進捗表示
                if idx % 20 == 0 or idx == 1 or idx == total:
                    elapsed = time.time() - start_time
                    rate = idx / elapsed if elapsed > 0 else 0
                    remaining_sec = (total - idx) / rate if rate > 0 else 0

                    progress = int(((current_step + idx/total * beforeinfo_steps) / total_steps) * 100)
                    self._update_progress(
                        "フェーズ2",
                        f'直前情報を取得中... ({idx}/{total}) - {rate:.1f}件/秒 - 残り約{remaining_sec/60:.0f}分',
                        min(progress, 99)
                    )

                if idx % 100 == 0:
                    current_step += 1

        remaining_steps = beforeinfo_steps - (total // 100)
        current_step += max(1, remaining_steps)
        processed += beforeinfo_success
        errors += beforeinfo_error

        return current_step, processed, errors

    def _fetch_odds_parallel(
        self, races_without_odds: List,
        current_step: int, total_steps: int, odds_steps: int,
        processed: int, errors: int
    ) -> tuple:
        """フェーズ3: オッズの取得（並列化版・高速化）"""
        self._update_progress(
            "フェーズ3",
            f'{len(races_without_odds)}レースのオッズを取得中...',
            int((current_step / total_steps) * 100)
        )

        import threading
        import requests
        from bs4 import BeautifulSoup
        from src.database.data_manager import DataManager

        odds_success = 0
        odds_error = 0
        total = len(races_without_odds)

        # スレッドローカルセッション管理
        thread_local = threading.local()

        def get_session():
            """スレッドごとにセッションを再利用"""
            if not hasattr(thread_local, 'session'):
                thread_local.session = requests.Session()
                thread_local.session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
                    'Accept': 'text/html',
                })
            return thread_local.session

        def fetch_single_odds(race_info):
            """1レース分のオッズを取得（高速版）"""
            race_id, venue_code, race_date, race_number = race_info
            try:
                date_str = race_date.replace('-', '')
                url = "https://www.boatrace.jp/owpc/pc/race/odds3t"
                params = {
                    'rno': race_number,
                    'jcd': venue_code.zfill(2),
                    'hd': date_str
                }

                time.sleep(0.1)  # 最小限の遅延
                session = get_session()
                response = session.get(url, params=params, timeout=30)

                if response.status_code != 200:
                    return False

                response.encoding = 'utf-8'
                trifecta_odds = self._parse_odds_html(response.text)

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
                    return True
                else:
                    return False
            except Exception as e:
                logger.warning(f"オッズ取得エラー (race_id={race_id}): {e}")
                return False

        # ThreadPoolExecutorで並列処理
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers_odds) as executor:
            futures = {
                executor.submit(fetch_single_odds, race): race
                for race in races_without_odds
            }

            for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
                try:
                    # 個別タスクに60秒のタイムアウト
                    if future.result(timeout=60):
                        odds_success += 1
                    else:
                        odds_error += 1
                except concurrent.futures.TimeoutError:
                    odds_error += 1
                    logger.warning(f"タイムアウト: {idx}件目のオッズ")
                except Exception as e:
                    odds_error += 1
                    logger.warning(f"並列処理エラー: {e}")

                # 進捗表示
                if idx % 10 == 0 or idx == 1 or idx == total:
                    elapsed = time.time() - start_time
                    rate = idx / elapsed if elapsed > 0 else 0
                    remaining_sec = (total - idx) / rate if rate > 0 else 0

                    progress = int(((current_step + idx/total * odds_steps) / total_steps) * 100)
                    self._update_progress(
                        "フェーズ3",
                        f'オッズを取得中... ({idx}/{total}) - {rate:.1f}件/秒 - 残り約{remaining_sec/60:.0f}分',
                        min(progress, 99)
                    )

                if idx % 50 == 0:
                    current_step += 1

        remaining_steps = odds_steps - (total // 50)
        current_step += max(1, remaining_steps)
        processed += odds_success
        errors += odds_error

        return current_step, processed, errors

    def _run_scripts(
        self, scripts: List[tuple], phase_name: str,
        current_step: int, total_steps: int,
        processed: int, errors: int
    ) -> tuple:
        """補完スクリプトを実行（並列化済み）"""
        self._update_progress(
            phase_name,
            f'{len(scripts)}種類のスクリプトを実行中...',
            int((current_step / total_steps) * 100)
        )

        def run_single_script(script_info):
            """1つのスクリプトを実行"""
            script_name, label = script_info
            script_path = os.path.join(self.project_root, script_name)

            if not os.path.exists(script_path):
                return {'success': False, 'label': label, 'error': 'スクリプトが見つかりません'}

            try:
                args = [sys.executable, script_path]

                if hasattr(self, 'start_date') and self.start_date:
                    args.extend(['--start-date', self.start_date])
                if hasattr(self, 'end_date') and self.end_date:
                    args.extend(['--end-date', self.end_date])

                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    cwd=self.project_root,
                    timeout=600,
                    encoding='utf-8',
                    errors='ignore'
                )

                if result.returncode != 0:
                    return {'success': False, 'label': label, 'error': result.stderr[:200]}
                else:
                    return {'success': True, 'label': label}

            except subprocess.TimeoutExpired:
                return {'success': False, 'label': label, 'error': 'タイムアウト'}
            except Exception as e:
                return {'success': False, 'label': label, 'error': str(e)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(run_single_script, script_info): script_info
                for script_info in scripts
            }

            for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
                try:
                    # 個別タスクに300秒のタイムアウト（補完スクリプトは時間がかかる）
                    result = future.result(timeout=300)

                    progress = int((current_step / total_steps) * 100)
                    self._update_progress(
                        phase_name,
                        f'{result["label"]}完了 ({idx}/{len(scripts)})',
                        progress
                    )

                    if result['success']:
                        processed += 1
                    else:
                        logger.warning(f"{result['label']} 失敗: {result.get('error', '不明')}")
                        errors += 1

                    current_step += 1

                except concurrent.futures.TimeoutError:
                    logger.error(f"スクリプトタイムアウト（300秒）: {idx}件目")
                    errors += 1
                    current_step += 1
                except Exception as e:
                    logger.warning(f"スクリプト実行エラー: {e}")
                    errors += 1
                    current_step += 1

        return current_step, processed, errors

    def _parse_odds_html(self, html: str) -> dict:
        """
        オッズHTMLをパース（高速版）

        Args:
            html: 3連単オッズページのHTML

        Returns:
            {'1-2-3': 8.8, '1-2-4': 15.2, ...}
        """
        from bs4 import BeautifulSoup
        import warnings
        warnings.filterwarnings("ignore")

        odds_data = {}
        try:
            soup = BeautifulSoup(html, 'html.parser')

            for table in soup.find_all('table'):
                rows = table.find_all('tr')
                if len(rows) < 20:
                    continue

                second_boats = [2, 3, 4, 5, 6]
                row_idx = 1

                for second_boat in second_boats:
                    for sub_row in range(4):
                        if row_idx >= len(rows):
                            break

                        row = rows[row_idx]
                        cells = row.find_all('td')
                        row_idx += 1

                        if len(cells) >= 18:
                            for first_boat in range(1, 7):
                                base_idx = (first_boat - 1) * 3
                                try:
                                    cell_second = int(cells[base_idx].text.strip())
                                    third_boat = int(cells[base_idx + 1].text.strip())
                                    odds_text = cells[base_idx + 2].text.strip().replace(',', '')
                                    if odds_text and odds_text != '-':
                                        odds_value = float(odds_text)
                                        if 1.0 <= odds_value <= 99999.0:
                                            if len(set([first_boat, cell_second, third_boat])) == 3:
                                                odds_data[f"{first_boat}-{cell_second}-{third_boat}"] = odds_value
                                except (ValueError, IndexError):
                                    continue

                        elif len(cells) >= 12:
                            for first_boat in range(1, 7):
                                if first_boat == second_boat:
                                    continue
                                base_idx = (first_boat - 1) * 2
                                try:
                                    third_boat = int(cells[base_idx].text.strip())
                                    odds_text = cells[base_idx + 1].text.strip().replace(',', '')
                                    if odds_text and odds_text != '-':
                                        odds_value = float(odds_text)
                                        if 1.0 <= odds_value <= 99999.0:
                                            if len(set([first_boat, second_boat, third_boat])) == 3:
                                                odds_data[f"{first_boat}-{second_boat}-{third_boat}"] = odds_value
                                except (ValueError, IndexError):
                                    continue

                if len(odds_data) >= 60:
                    break

        except Exception as e:
            logger.warning(f"オッズパースエラー: {e}")

        return odds_data if odds_data else None
