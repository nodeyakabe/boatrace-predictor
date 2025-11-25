"""
不足データ収集スクリプト
CSVから不足データを読み込み、並列で収集
"""

import csv
import sqlite3
import time
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/fetch_missing_data.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# プロジェクトルートをパスに追加
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.scraper.result_scraper import ResultScraper
from src.scraper.beforeinfo_scraper import BeforeInfoScraper
from src.database.data_manager import DataManager


class MissingDataFetcher:
    """不足データ収集クラス"""

    def __init__(self, max_workers=5):
        self.result_scraper = ResultScraper()
        self.beforeinfo_scraper = BeforeInfoScraper()
        self.data_manager = DataManager()
        self.max_workers = max_workers

        self.success_count = 0
        self.error_count = 0
        self.skip_count = 0

    def fetch_missing_results(self, csv_file='missing_results.csv'):
        """
        欠損している結果データを収集

        Args:
            csv_file: 欠損レースリストのCSVファイル
        """
        logger.info(f"結果データ収集開始: {csv_file}")

        # CSVから欠損レースを読み込み
        missing_races = []
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                missing_races.append({
                    'race_id': int(row['race_id']),
                    'venue_code': row['venue_code'],
                    'race_date': row['race_date'].replace('-', ''),  # YYYYMMDD形式に
                    'race_number': int(row['race_number'])
                })

        logger.info(f"対象レース数: {len(missing_races)}")

        # 並列処理で収集
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._fetch_single_result, race): race
                for race in missing_races
            }

            for future in as_completed(futures):
                race = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"エラー発生: {race} - {e}")
                    self.error_count += 1

                # 進捗表示
                if (self.success_count + self.error_count + self.skip_count) % 100 == 0:
                    logger.info(f"進捗: 成功={self.success_count}, エラー={self.error_count}, スキップ={self.skip_count}")

        logger.info(f"結果データ収集完了: 成功={self.success_count}, エラー={self.error_count}, スキップ={self.skip_count}")

    def _fetch_single_result(self, race):
        """単一レースの結果を取得"""
        try:
            # 結果データ取得
            result_data = self.result_scraper.get_race_result(
                race['venue_code'],
                race['race_date'],
                race['race_number']
            )

            if result_data:
                # race_statusが判明した場合、結果がなくても記録
                race_status = result_data.get('race_status', 'unknown')

                if result_data.get('results'):
                    # 結果データがある場合は保存
                    success = self.data_manager.save_race_result(result_data)
                    if success:
                        self.success_count += 1
                        time.sleep(0.5)  # レート制限
                    else:
                        self.error_count += 1
                elif race_status in ['cancelled', 'flying', 'accident', 'returned']:
                    # 開催中止などの場合もステータスを記録
                    success = self.data_manager.update_race_status_by_info(
                        race['venue_code'],
                        race['race_date'],
                        race['race_number'],
                        race_status
                    )
                    if success:
                        self.success_count += 1
                        logger.info(f"レースステータス記録: {race} -> {race_status}")
                        time.sleep(0.5)
                    else:
                        self.error_count += 1
                else:
                    # 結果もステータスも不明
                    self.skip_count += 1
                    logger.warning(f"データ取得失敗: {race}")
            else:
                # result_data自体がNone
                self.skip_count += 1
                logger.warning(f"データ取得失敗（HTTP失敗）: {race}")

        except Exception as e:
            logger.error(f"例外発生: {race} - {e}")
            self.error_count += 1

    def fetch_missing_details(self, csv_file='missing_details.csv'):
        """
        欠損している事前情報を収集

        Args:
            csv_file: 欠損レースリストのCSVファイル
        """
        logger.info(f"事前情報収集開始: {csv_file}")

        self.success_count = 0
        self.error_count = 0
        self.skip_count = 0

        # CSVから欠損レースを読み込み
        missing_races = []
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                missing_races.append({
                    'race_id': int(row['race_id']),
                    'venue_code': row['venue_code'],
                    'race_date': row['race_date'].replace('-', ''),
                    'race_number': int(row['race_number'])
                })

        logger.info(f"対象レース数: {len(missing_races)}")

        # 並列処理で収集
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._fetch_single_detail, race): race
                for race in missing_races
            }

            for future in as_completed(futures):
                race = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"エラー発生: {race} - {e}")
                    self.error_count += 1

                # 進捗表示
                if (self.success_count + self.error_count + self.skip_count) % 100 == 0:
                    logger.info(f"進捗: 成功={self.success_count}, エラー={self.error_count}, スキップ={self.skip_count}")

        logger.info(f"事前情報収集完了: 成功={self.success_count}, エラー={self.error_count}, スキップ={self.skip_count}")

    def _fetch_single_detail(self, race):
        """単一レースの事前情報を取得"""
        try:
            # 事前情報取得
            beforeinfo_data = self.beforeinfo_scraper.get_race_beforeinfo(
                race['venue_code'],
                race['race_date'],
                race['race_number']
            )

            if beforeinfo_data:
                # race_details用のデータ形式に変換
                race_details_data = []

                exhibition_times = beforeinfo_data.get('exhibition_times', {})
                tilt_angles = beforeinfo_data.get('tilt_angles', {})
                parts_replacements = beforeinfo_data.get('parts_replacements', {})

                for pit_number in range(1, 7):
                    detail = {
                        'pit_number': pit_number,
                        'exhibition_time': exhibition_times.get(pit_number),
                        'tilt_angle': tilt_angles.get(pit_number),
                        'parts_replacement': parts_replacements.get(pit_number, '')
                    }
                    race_details_data.append(detail)

                # データベースに保存
                success = self.data_manager.save_race_details(race['race_id'], race_details_data)
                if success:
                    self.success_count += 1
                    time.sleep(0.5)  # レート制限
                else:
                    self.error_count += 1
            else:
                self.skip_count += 1

        except Exception as e:
            logger.error(f"例外発生: {race} - {e}")
            self.error_count += 1


def main():
    """メイン処理"""
    # ログディレクトリ作成
    Path('logs').mkdir(exist_ok=True)

    fetcher = MissingDataFetcher(max_workers=8)

    # 結果データ収集
    if Path('missing_results.csv').exists():
        logger.info("=== 結果データ収集開始 ===")
        fetcher.fetch_missing_results('missing_results.csv')

    # 事前情報収集
    if Path('missing_details.csv').exists():
        logger.info("=== 事前情報収集開始 ===")
        fetcher.fetch_missing_details('missing_details.csv')

    logger.info("すべての不足データ収集完了")


if __name__ == '__main__':
    main()
