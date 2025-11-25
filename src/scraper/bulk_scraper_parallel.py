"""
並列処理版一括スクレイピング機能
複数レースを効率的に取得（処理時間1/3〜1/4に短縮）
"""

from .race_scraper_v2 import RaceScraperV2
from .schedule_scraper import ScheduleScraper
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class BulkScraperParallel:
    """並列処理版一括スクレイピングクラス"""

    def __init__(self, max_workers=4):
        """
        初期化

        Args:
            max_workers: 並列処理のワーカー数（デフォルト4）
        """
        self.max_workers = max_workers
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

        # レース番号順にソート
        all_races.sort(key=lambda x: x.get('race_number', 0))

        return all_races

    def fetch_multiple_venues_parallel(self, venue_codes, race_date, race_count=12, progress_callback=None):
        """
        複数競艇場の全レースを並列取得

        Args:
            venue_codes: 競艇場コードのリスト
            race_date: レース日付（YYYYMMDD形式）
            race_count: 各場のレース数（デフォルト12）
            progress_callback: 進捗コールバック callback(venue_idx, total_venues, venue_code, status)

        Returns:
            {venue_code: [race_data, ...]} の辞書
        """
        all_venue_data = {}
        total_venues = len(venue_codes)

        def fetch_venue_races(venue_code):
            """1会場の全レースを取得"""
            races = []
            failed_races = []
            scraper = RaceScraperV2()

            try:
                # 第1パス: 全レースを取得
                for race_number in range(1, race_count + 1):
                    try:
                        race_data = scraper.get_race_card(venue_code, race_date, race_number)
                        if race_data and race_data.get('entries'):
                            races.append(race_data)
                        else:
                            failed_races.append(race_number)
                        # 短い待機（レート制限対策）
                        time.sleep(0.3)
                    except Exception as e:
                        failed_races.append(race_number)
                        import logging
                        logging.warning(f"会場{venue_code} {race_number}R 取得失敗: {e}")

                # 第2パス: 失敗したレースをリトライ（待機時間を長くして）
                if failed_races:
                    time.sleep(2)  # 少し待機してからリトライ
                    for race_number in failed_races:
                        try:
                            race_data = scraper.get_race_card(venue_code, race_date, race_number)
                            if race_data and race_data.get('entries'):
                                races.append(race_data)
                            time.sleep(0.5)
                        except Exception as e:
                            import logging
                            logging.error(f"会場{venue_code} {race_number}R リトライ失敗: {e}")
            finally:
                scraper.close()

            return (venue_code, races)

        # 会場を並列処理（同時に最大3会場）
        with ThreadPoolExecutor(max_workers=min(3, total_venues)) as executor:
            futures = {
                executor.submit(fetch_venue_races, venue_code): venue_code
                for venue_code in venue_codes
            }

            completed = 0
            for future in as_completed(futures):
                venue_code, races = future.result()
                all_venue_data[venue_code] = races
                completed += 1

                if progress_callback:
                    progress_callback(completed, total_venues, venue_code, f"{len(races)}レース取得")

        return all_venue_data

    def close(self):
        """スクレイパーをクローズ"""
        if hasattr(self._local, 'scraper'):
            self._local.scraper.close()
        self.schedule_scraper.close()


# テスト用
if __name__ == "__main__":
    import time

    print("並列処理版BulkScraper テスト")
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

        results = scraper.fetch_multiple_venues_parallel(
            venue_codes=[v[0] for v in test_venues],
            race_date=test_venues[0][1],
            race_count=12,
            progress_callback=progress
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
