"""
安全な過去データ一括取得
長期間のデータ取得に対応（待機時間調整、エラーハンドリング強化）
"""

from datetime import datetime, timedelta
from .race_scraper import RaceScraper
from .result_scraper import ResultScraper
from .beforeinfo_scraper import BeforeInfoScraper
from src.database.data_manager import DataManager
import time
import random


class SafeHistoricalScraper:
    """安全な過去データ一括取得クラス（長期間対応）"""

    def __init__(self, safe_mode=True):
        """
        Args:
            safe_mode: 安全モード（待機時間を長めに設定）
        """
        self.race_scraper = RaceScraper()
        self.result_scraper = ResultScraper()
        self.beforeinfo_scraper = BeforeInfoScraper()
        self.data_manager = DataManager()
        self.safe_mode = safe_mode

        # 待機時間設定
        if safe_mode:
            self.race_wait = 1.0      # レース間: 1秒
            self.day_wait = 3.0       # 日付間: 3秒
            self.random_wait = 0.5    # ランダム待機の最大値
        else:
            self.race_wait = 0.3
            self.day_wait = 1.0
            self.random_wait = 0.0

        # エラー監視
        self.error_count = 0
        self.total_requests = 0
        self.consecutive_errors = 0

    def fetch_historical_data(self, venue_code, start_date, end_date, callback=None):
        """
        指定期間のデータを安全に取得

        Args:
            venue_code: 競艇場コード
            start_date: 開始日（datetime）
            end_date: 終了日（datetime）
            callback: 進捗コールバック関数

        Returns:
            取得成功日数、失敗日数のタプル
        """
        success_days = 0
        failed_days = 0
        total_days = (end_date - start_date).days + 1

        current_date = start_date

        print(f"\n{'='*70}")
        print(f"過去データ取得開始（安全モード: {'ON' if self.safe_mode else 'OFF'}）")
        print(f"競艇場コード: {venue_code}")
        print(f"期間: {start_date.strftime('%Y-%m-%d')} ～ {end_date.strftime('%Y-%m-%d')}")
        print(f"対象日数: {total_days}日")
        print(f"待機時間: レース間{self.race_wait}秒 / 日付間{self.day_wait}秒")
        print(f"{'='*70}\n")

        while current_date <= end_date:
            date_str_yyyymmdd = current_date.strftime("%Y%m%d")
            date_str_formatted = current_date.strftime("%Y-%m-%d")
            day_num = (current_date - start_date).days + 1

            print(f"[{day_num}/{total_days}] {date_str_formatted} 処理中...")

            # エラー率チェック
            if self._should_pause():
                print(f"\n⚠️  エラー率が高い（{self._get_error_rate():.1%}）- 10分間待機します")
                time.sleep(600)
                self.error_count = 0
                self.total_requests = 0

            # レースが存在するか確認
            try:
                if not self.result_scraper.check_race_exists(venue_code, date_str_yyyymmdd):
                    print(f"  → レース開催なし")
                    current_date += timedelta(days=1)
                    continue
            except Exception as e:
                print(f"  → レース存在確認エラー: {e}")
                self._handle_error()
                current_date += timedelta(days=1)
                continue

            # 全レース結果を一括取得
            try:
                all_results = self.result_scraper.get_all_race_results_by_date(
                    venue_code, date_str_yyyymmdd
                )
                self.total_requests += 1

                if not all_results:
                    print(f"  → 結果データ取得失敗")
                    self._handle_error()
                    failed_days += 1
                    current_date += timedelta(days=1)
                    continue

            except Exception as e:
                print(f"  → 結果取得エラー: {e}")
                self._handle_error()
                failed_days += 1
                current_date += timedelta(days=1)
                continue

            # 各レースの出走表と結果を保存
            day_success = 0
            day_failed = 0

            # 天気情報を取得（1Rの詳細結果から取得）
            weather_saved = False
            if all_results:
                try:
                    # 1Rの詳細結果を取得（天気情報を含む）
                    first_race_detail = self.result_scraper.get_race_result(
                        venue_code, date_str_yyyymmdd, 1
                    )
                    self.total_requests += 1

                    if first_race_detail and first_race_detail.get('weather_data'):
                        self.data_manager.save_weather_data(
                            venue_code,
                            date_str_formatted,
                            first_race_detail['weather_data']
                        )
                        weather_saved = True
                except Exception as e:
                    print(f"  天気情報取得/保存エラー: {e}")

            for result_data in all_results:
                race_number = result_data['race_number']

                try:
                    # 出走表を取得
                    race_data = self.race_scraper.get_race_card(
                        venue_code, date_str_yyyymmdd, race_number
                    )
                    self.total_requests += 1

                    if race_data and race_data.get('entries'):
                        # DBに保存
                        self.data_manager.save_race_data(race_data)
                        self.data_manager.save_race_result(result_data)

                        day_success += 1
                        self.consecutive_errors = 0  # 成功したらリセット
                    else:
                        day_failed += 1
                        self._handle_error()

                    # レート制限対策（ランダム要素追加）
                    wait_time = self.race_wait + random.uniform(0, self.random_wait)
                    time.sleep(wait_time)

                except Exception as e:
                    print(f"  {race_number}R エラー: {e}")
                    day_failed += 1
                    self._handle_error()

                    # 連続エラーの場合は長めに待機
                    if self.consecutive_errors >= 3:
                        print(f"  ⚠️  連続エラー{self.consecutive_errors}回 - 30秒待機")
                        time.sleep(30)

            if day_success > 0:
                success_days += 1
                print(f"  OK: {day_success}R成功 / {day_failed}R失敗")
            else:
                failed_days += 1
                print(f"  NG: 失敗")

            # コールバック実行
            if callback:
                callback(day_num, total_days, current_date, day_success)

            current_date += timedelta(days=1)

            # 日付間の待機（ランダム要素追加）
            day_wait_time = self.day_wait + random.uniform(0, self.random_wait)
            time.sleep(day_wait_time)

        print(f"\n{'='*70}")
        print(f"過去データ取得完了")
        print(f"成功: {success_days}日 / 失敗: {failed_days}日")
        print(f"エラー率: {self._get_error_rate():.1%}")
        print(f"{'='*70}\n")

        return success_days, failed_days

    def _handle_error(self):
        """エラー処理"""
        self.error_count += 1
        self.consecutive_errors += 1

    def _get_error_rate(self):
        """エラー率を取得"""
        if self.total_requests == 0:
            return 0.0
        return self.error_count / self.total_requests

    def _should_pause(self):
        """一時停止すべきか判定"""
        # エラー率が10%を超えたら一時停止
        return (self.total_requests > 100 and
                self._get_error_rate() > 0.1)

    def close(self):
        """スクレイパーをクローズ"""
        self.race_scraper.close()
        self.result_scraper.close()
