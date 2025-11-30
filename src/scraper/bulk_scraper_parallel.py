"""
並列処理版一括スクレイピング機能
複数レースを効率的に取得（処理時間1/3〜1/4に短縮）
エラーハンドリング強化版
"""

from .race_scraper_v2 import RaceScraperV2
from .schedule_scraper import ScheduleScraper
from datetime import datetime
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import threading

logger = logging.getLogger(__name__)


class BulkScraperParallel:
    """並列処理版一括スクレイピングクラス"""

    def __init__(self, max_workers=4, timeout_per_venue=120):
        """
        初期化

        Args:
            max_workers: 並列処理のワーカー数（デフォルト4）
            timeout_per_venue: 1会場あたりのタイムアウト秒数（デフォルト120秒）
        """
        self.max_workers = max_workers
        self.timeout_per_venue = timeout_per_venue
        self.schedule_scraper = ScheduleScraper()
        # スレッドローカルでスクレイパーを管理
        self._local = threading.local()
        self._lock = threading.Lock()

    def _get_scraper(self):
        """スレッドローカルなスクレイパーを取得"""
        if not hasattr(self._local, 'scraper'):
            self._local.scraper = RaceScraperV2()
        return self._local.scraper

    def fetch_single_race(self, venue_code, race_date, race_number):
        """
        単一レースを取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付
            race_number: レース番号

        Returns:
            (venue_code, race_number, race_data) のタプル
        """
        try:
            scraper = self._get_scraper()
            race_data = scraper.get_race_card(venue_code, race_date, race_number)

            if race_data and race_data.get('entries'):
                return (venue_code, race_number, race_data, None)
            else:
                return (venue_code, race_number, None, "データなし")

        except Exception as e:
            logger.warning(f"会場{venue_code} {race_number}R 取得エラー: {e}")
            return (venue_code, race_number, None, str(e))

    def fetch_all_races_parallel(self, venue_code, race_date, race_count=12, callback=None):
        """
        指定日・指定場の全レースを並列取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）
            race_count: 取得するレース数（デフォルト12）
            callback: 進捗コールバック関数 callback(completed, total, race_data)

        Returns:
            取得したレースデータのリスト
        """
        all_races = []
        success_count = 0
        error_count = 0

        # 並列でレースを取得
        with ThreadPoolExecutor(max_workers=min(self.max_workers, race_count)) as executor:
            futures = {
                executor.submit(
                    self.fetch_single_race,
                    venue_code,
                    race_date,
                    race_number
                ): race_number
                for race_number in range(1, race_count + 1)
            }

            completed = 0
            for future in as_completed(futures):
                venue, race_num, race_data, error = future.result()
                completed += 1

                if race_data:
                    all_races.append(race_data)
                    success_count += 1
                    if callback:
                        callback(completed, race_count, race_data)
                else:
                    error_count += 1
                    logger.warning(f"会場{venue_code} {race_num}R 取得失敗: {error}")

        # レース番号順にソート
        all_races.sort(key=lambda x: x.get('race_number', 0))

        logger.info(f"会場{venue_code}: 成功{success_count}/失敗{error_count}")
        return all_races

    def fetch_multiple_venues_parallel(self, venue_codes, race_date, race_count=12, progress_callback=None):
        """
        複数競艇場の全レースを並列取得（エラーハンドリング強化版）

        Args:
            venue_codes: 競艇場コードのリスト
            race_date: レース日付（YYYYMMDD形式）
            race_count: 各場のレース数（デフォルト12）
            progress_callback: 進捗コールバック callback(venue_idx, total_venues, venue_code, status)

        Returns:
            {venue_code: [race_data, ...]} の辞書
        """
        all_venue_data = {}
        failed_venues = []  # 失敗した会場を追跡
        total_venues = len(venue_codes)

        logger.info(f"=== 並列取得開始: {total_venues}会場, 日付={race_date} ===")

        def fetch_venue_races(venue_code):
            """1会場の全レースを取得"""
            races = []
            failed_races = []
            scraper = None

            try:
                scraper = RaceScraperV2()

                # 第1パス: 全レースを取得
                for race_number in range(1, race_count + 1):
                    try:
                        race_data = scraper.get_race_card(venue_code, race_date, race_number)
                        if race_data and race_data.get('entries'):
                            races.append(race_data)
                        else:
                            failed_races.append(race_number)
                            logger.debug(f"会場{venue_code} {race_number}R: データなし")
                        # 短い待機（レート制限対策）
                        time.sleep(0.3)
                    except Exception as e:
                        failed_races.append(race_number)
                        logger.warning(f"会場{venue_code} {race_number}R 取得失敗: {e}")

                # 第2パス: 失敗したレースをリトライ（待機時間を長くして）
                if failed_races:
                    logger.info(f"会場{venue_code}: {len(failed_races)}レース失敗、リトライ中...")
                    time.sleep(2)  # 少し待機してからリトライ

                    retry_failed = []
                    for race_number in failed_races:
                        try:
                            race_data = scraper.get_race_card(venue_code, race_date, race_number)
                            if race_data and race_data.get('entries'):
                                races.append(race_data)
                                logger.info(f"会場{venue_code} {race_number}R: リトライ成功")
                            else:
                                retry_failed.append(race_number)
                            time.sleep(0.5)
                        except Exception as e:
                            retry_failed.append(race_number)
                            logger.error(f"会場{venue_code} {race_number}R リトライ失敗: {e}")

                    if retry_failed:
                        logger.warning(f"会場{venue_code}: 最終的に{len(retry_failed)}レース取得失敗 ({retry_failed})")

            except Exception as e:
                logger.error(f"会場{venue_code} 処理中に例外発生: {e}")

            finally:
                if scraper:
                    try:
                        scraper.close()
                    except:
                        pass

            return (venue_code, races)

        # 会場を並列処理（同時に最大3会場 - サーバー負荷軽減のため少なめに）
        max_parallel = min(3, total_venues)
        logger.info(f"並列数: {max_parallel}")

        with ThreadPoolExecutor(max_workers=max_parallel) as executor:
            futures = {
                executor.submit(fetch_venue_races, venue_code): venue_code
                for venue_code in venue_codes
            }

            completed = 0
            for future in as_completed(futures, timeout=self.timeout_per_venue * total_venues):
                try:
                    venue_code, races = future.result(timeout=self.timeout_per_venue)
                    all_venue_data[venue_code] = races
                    completed += 1

                    status = f"{len(races)}レース取得"
                    if len(races) < race_count:
                        status += f" (不足{race_count - len(races)})"
                        if len(races) == 0:
                            failed_venues.append(venue_code)

                    logger.info(f"[{completed}/{total_venues}] 会場{venue_code}: {status}")

                    if progress_callback:
                        progress_callback(completed, total_venues, venue_code, status)

                except FuturesTimeoutError:
                    venue_code = futures[future]
                    logger.error(f"会場{venue_code}: タイムアウト ({self.timeout_per_venue}秒)")
                    failed_venues.append(venue_code)
                    all_venue_data[venue_code] = []
                    completed += 1

                    if progress_callback:
                        progress_callback(completed, total_venues, venue_code, "タイムアウト")

                except Exception as e:
                    venue_code = futures[future]
                    logger.error(f"会場{venue_code}: 例外発生 - {e}")
                    failed_venues.append(venue_code)
                    all_venue_data[venue_code] = []
                    completed += 1

                    if progress_callback:
                        progress_callback(completed, total_venues, venue_code, f"エラー: {e}")

        # 失敗した会場のサマリー
        if failed_venues:
            logger.warning(f"=== 取得失敗会場: {failed_venues} ===")
        else:
            logger.info("=== 全会場取得成功 ===")

        # 統計情報
        total_races = sum(len(races) for races in all_venue_data.values())
        expected_races = total_venues * race_count
        logger.info(f"取得結果: {total_races}/{expected_races}レース ({total_races/expected_races*100:.1f}%)")

        return all_venue_data

    def fetch_with_retry(self, venue_codes, race_date, race_count=12, progress_callback=None, max_retries=2):
        """
        失敗時に自動リトライする取得メソッド

        Args:
            venue_codes: 競艇場コードのリスト
            race_date: レース日付
            race_count: レース数
            progress_callback: 進捗コールバック
            max_retries: 最大リトライ回数

        Returns:
            {venue_code: [race_data, ...]} の辞書
        """
        all_data = {}
        remaining_venues = list(venue_codes)

        for attempt in range(max_retries + 1):
            if not remaining_venues:
                break

            if attempt > 0:
                logger.info(f"=== リトライ {attempt}/{max_retries}: {len(remaining_venues)}会場 ===")
                time.sleep(5)  # リトライ前に待機

            result = self.fetch_multiple_venues_parallel(
                remaining_venues, race_date, race_count, progress_callback
            )

            # 結果をマージ
            for venue_code, races in result.items():
                if venue_code not in all_data or len(races) > len(all_data.get(venue_code, [])):
                    all_data[venue_code] = races

            # 不足会場を特定
            remaining_venues = [
                vc for vc in remaining_venues
                if len(all_data.get(vc, [])) < race_count
            ]

            if not remaining_venues:
                logger.info("全会場の取得完了")
                break

        return all_data

    def close(self):
        """スクレイパーをクローズ"""
        if hasattr(self._local, 'scraper'):
            try:
                self._local.scraper.close()
            except:
                pass
        try:
            self.schedule_scraper.close()
        except:
            pass


# テスト用
if __name__ == "__main__":
    import time

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    print("並列処理版BulkScraper テスト（エラーハンドリング強化版）")
    print("=" * 60)

    scraper = BulkScraperParallel(max_workers=4)

    # 今日のスケジュールを取得
    today_schedule = scraper.schedule_scraper.get_today_schedule()

    if today_schedule:
        print(f"本日開催: {len(today_schedule)}会場")

        # 最初の2会場だけテスト
        test_venues = list(today_schedule.items())[:2]

        start_time = time.time()

        def progress(idx, total, venue, status):
            print(f"  [{idx}/{total}] {venue}: {status}")

        results = scraper.fetch_with_retry(
            venue_codes=[v[0] for v in test_venues],
            race_date=test_venues[0][1],
            race_count=12,
            progress_callback=progress,
            max_retries=1
        )

        elapsed = time.time() - start_time

        print(f"\n結果:")
        total_races = 0
        for venue, races in results.items():
            print(f"  {venue}: {len(races)}レース")
            total_races += len(races)

        print(f"\n合計: {total_races}レース")
        print(f"処理時間: {elapsed:.1f}秒")
        print(f"1レースあたり: {elapsed/max(1, total_races):.2f}秒")
    else:
        print("本日開催のレースがありません")

    scraper.close()
