"""
一括スクレイピング機能
複数レースを効率的に取得
"""

from .race_scraper_v2 import RaceScraperV2
from .schedule_scraper import ScheduleScraper
from datetime import datetime
import time
import concurrent.futures

from src.database.race_checker import RaceChecker


class BulkScraper:
    """一括スクレイピングクラス"""

    def __init__(self):
        try:
            print("[DEBUG] BulkScraper初期化開始")
            print("[DEBUG] RaceScraperV2インスタンス化中...")
            self.scraper = RaceScraperV2()
            print("[DEBUG] RaceScraperV2インスタンス化完了")

            print("[DEBUG] ScheduleScraperインスタンス化中...")
            self.schedule_scraper = ScheduleScraper()
            print("[DEBUG] ScheduleScraperインスタンス化完了")

            print("[DEBUG] RaceCheckerインスタンス化中...")
            self.race_checker = RaceChecker()
            print("[DEBUG] RaceCheckerインスタンス化完了")

            print(f"[DEBUG] BulkScraper初期化完了: scraper={type(self.scraper)}, schedule_scraper={type(self.schedule_scraper)}")
        except Exception as e:
            print(f"[ERROR] BulkScraper初期化エラー: {e}")
            import traceback
            traceback.print_exc()
            # エラーが発生しても、部分的に初期化された属性を削除
            if hasattr(self, 'scraper'):
                delattr(self, 'scraper')
            if hasattr(self, 'schedule_scraper'):
                delattr(self, 'schedule_scraper')
            raise

    def fetch_all_races(self, venue_code, race_date, race_count=12, callback=None, skip_existing=False):
        """
        指定日・指定場の全レースを取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYY-MM-DD または YYYYMMDD形式）
            race_count: 取得するレース数（デフォルト12）
            callback: 進捗コールバック関数 callback(race_number, total, race_data)
            skip_existing: 既存データをスキップするか（デフォルトFalse）

        Returns:
            取得したレースデータのリスト
        """
        all_races = []
        success_count = 0
        error_count = 0
        skipped_count = 0

        # 日付形式を正規化（YYYY-MM-DD形式に統一）
        race_date_normalized = race_date
        if len(race_date) == 8 and '-' not in race_date:
            race_date_normalized = f"{race_date[:4]}-{race_date[4:6]}-{race_date[6:8]}"

        print(f"\n{'='*60}")
        print(f"全レース取得開始")
        print(f"競艇場コード: {venue_code}")
        print(f"日付: {race_date}")
        print(f"対象レース: 1R～{race_count}R")
        if skip_existing:
            print(f"スキップモード: ON（既存データをスキップ）")
        print(f"{'='*60}\n")

        # スキップ対象のレースを事前チェック
        races_to_fetch = []
        for race_number in range(1, race_count + 1):
            if skip_existing:
                if self.race_checker.is_race_collected(venue_code, race_date_normalized, race_number):
                    print(f"[{race_number}/{race_count}] {race_number}R [SKIP] 既に収集済み")
                    skipped_count += 1
                    continue
            races_to_fetch.append(race_number)

        if not races_to_fetch:
            print(f"  [INFO] 取得対象のレースがありません")
            return all_races

        # 並列処理用の関数
        def fetch_single_race(race_number):
            """1レース分のデータを取得"""
            try:
                race_data = self.scraper.get_race_card(venue_code, race_date, race_number)

                if race_data and race_data.get('entries'):
                    return {
                        'success': True,
                        'race_number': race_number,
                        'race_data': race_data
                    }
                else:
                    return {
                        'success': False,
                        'race_number': race_number,
                        'error': 'データが取得できませんでした'
                    }
            except Exception as e:
                return {
                    'success': False,
                    'race_number': race_number,
                    'error': str(e)
                }

        # ThreadPoolExecutorで並列処理（4スレッド）
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(fetch_single_race, race_num): race_num
                for race_num in races_to_fetch
            }

            for future in concurrent.futures.as_completed(futures, timeout=1800):
                result = future.result()
                race_number = result['race_number']

                if result['success']:
                    all_races.append(result['race_data'])
                    success_count += 1
                    entry_count = len(result['race_data']['entries'])
                    print(f"[{race_number}/{race_count}] {race_number}R [OK] 成功: 選手数={entry_count}名")

                    # コールバック実行
                    if callback:
                        callback(race_number, race_count, result['race_data'])
                else:
                    error_count += 1
                    print(f"[{race_number}/{race_count}] {race_number}R [NG] 失敗: {result['error']}")

        print(f"\n{'='*60}")
        print(f"全レース取得完了")
        print(f"成功: {success_count}件 / 失敗: {error_count}件 / スキップ: {skipped_count}件")
        print(f"{'='*60}\n")

        return all_races

    def fetch_multiple_venues(self, venue_codes, race_date, race_count=12, skip_existing=False):
        """
        複数競艇場の全レースを取得

        Args:
            venue_codes: 競艇場コードのリスト
            race_date: レース日付（YYYY-MM-DD または YYYYMMDD形式）
            race_count: 各場のレース数（デフォルト12）
            skip_existing: 既存データをスキップするか（デフォルトFalse）

        Returns:
            {venue_code: [race_data, ...]} の辞書
        """
        all_venue_data = {}

        if skip_existing:
            print(f"\n[INFO] スキップモード有効: 既存データをスキップします")

        for i, venue_code in enumerate(venue_codes):
            print(f"\n{'#'*60}")
            print(f"競艇場 {i+1}/{len(venue_codes)}: コード={venue_code}")
            print(f"{'#'*60}")

            races = self.fetch_all_races(venue_code, race_date, race_count, skip_existing=skip_existing)
            all_venue_data[venue_code] = races

            # 次の競艇場に移る前に少し待機（レースを取得した場合のみ）
            if i < len(venue_codes) - 1 and races:
                print(f"\n次の競艇場へ移動します（2秒待機）...")
                time.sleep(2)

        return all_venue_data

    def close(self):
        """スクレイパーをクローズ"""
        self.scraper.close()
