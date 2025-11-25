"""
一括スクレイピング機能
複数レースを効率的に取得
"""

from .race_scraper_v2 import RaceScraperV2
from .schedule_scraper import ScheduleScraper
from datetime import datetime
import time


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

    def fetch_all_races(self, venue_code, race_date, race_count=12, callback=None):
        """
        指定日・指定場の全レースを取得

        Args:
            venue_code: 競艇場コード
            race_date: レース日付（YYYYMMDD形式）
            race_count: 取得するレース数（デフォルト12）
            callback: 進捗コールバック関数 callback(race_number, total, race_data)

        Returns:
            取得したレースデータのリスト
        """
        all_races = []
        success_count = 0
        error_count = 0

        print(f"\n{'='*60}")
        print(f"全レース取得開始")
        print(f"競艇場コード: {venue_code}")
        print(f"日付: {race_date}")
        print(f"対象レース: 1R～{race_count}R")
        print(f"{'='*60}\n")

        for race_number in range(1, race_count + 1):
            print(f"[{race_number}/{race_count}] {race_number}R 取得中...")

            try:
                race_data = self.scraper.get_race_card(venue_code, race_date, race_number)

                if race_data and race_data.get('entries'):
                    all_races.append(race_data)
                    success_count += 1
                    print(f"  [OK] 成功: 選手数={len(race_data['entries'])}名")

                    # コールバック実行
                    if callback:
                        callback(race_number, race_count, race_data)
                else:
                    error_count += 1
                    print(f"  [NG] 失敗: データが取得できませんでした")

            except Exception as e:
                error_count += 1
                print(f"  [ERROR] エラー: {e}")

            # レート制限対策（最後のレース以外は少し待機）
            if race_number < race_count:
                time.sleep(0.5)

        print(f"\n{'='*60}")
        print(f"全レース取得完了")
        print(f"成功: {success_count}件 / 失敗: {error_count}件")
        print(f"{'='*60}\n")

        return all_races

    def fetch_multiple_venues(self, venue_codes, race_date, race_count=12):
        """
        複数競艇場の全レースを取得

        Args:
            venue_codes: 競艇場コードのリスト
            race_date: レース日付（YYYYMMDD形式）
            race_count: 各場のレース数（デフォルト12）

        Returns:
            {venue_code: [race_data, ...]} の辞書
        """
        all_venue_data = {}

        for i, venue_code in enumerate(venue_codes):
            print(f"\n{'#'*60}")
            print(f"競艇場 {i+1}/{len(venue_codes)}: コード={venue_code}")
            print(f"{'#'*60}")

            races = self.fetch_all_races(venue_code, race_date, race_count)
            all_venue_data[venue_code] = races

            # 次の競艇場に移る前に少し待機
            if i < len(venue_codes) - 1:
                print(f"\n次の競艇場へ移動します（2秒待機）...")
                time.sleep(2)

        return all_venue_data

    def close(self):
        """スクレイパーをクローズ"""
        self.scraper.close()
