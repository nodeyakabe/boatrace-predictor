"""
レース開催日のみの潮位データを取得（最適化版）
不要な日のデータをスキップして容量を大幅削減

従来版: 全日のデータ（約20-30GB、3-4億レコード）
最適化版: レース開催日のみ（推定5-8GB、5000万-8000万レコード）
"""

import os
import sqlite3
import requests
import time
from datetime import datetime
from typing import List, Dict, Set
from pathlib import Path


class OptimizedTideDataFetcher:
    """レース開催日のみの潮位データを取得"""

    VENUE_TO_STATION = {
        '15': {'name': '丸亀', 'station': 'Marugame'},
        '16': {'name': '児島', 'station': 'Kojima'},
        '17': {'name': '宮島', 'station': 'Hiroshima'},
        '18': {'name': '徳山', 'station': 'Tokuyama'},
        '20': {'name': '若松', 'station': 'Wakamatsu'},
        '22': {'name': '福岡', 'station': 'Hakata'},
        '24': {'name': '大村', 'station': 'Sasebo'},
    }

    def __init__(self, db_path="data/boatrace.db", download_dir="rdmdb_optimized", delay=2.0):
        """
        初期化

        Args:
            db_path: データベースパス
            download_dir: ダウンロードディレクトリ
            delay: リクエスト間隔（秒）
        """
        self.db_path = db_path
        self.download_dir = download_dir
        self.delay = delay
        self.base_url = "https://www.data.jma.go.jp/gmd/kaiyou/db/tide/genbo"

        Path(self.download_dir).mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def get_race_dates_by_venue_month(self, start_date: str, end_date: str) -> Dict[str, Dict[str, Set[int]]]:
        """
        レース開催日を会場・年月別に取得

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)

        Returns:
            dict: {
                '22': {  # 会場コード
                    '2015-01': {1, 3, 5, ...},  # 年月: {開催日のセット}
                    '2015-02': {2, 4, ...},
                    ...
                }
            }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 海水場のレース開催日を取得
        cursor.execute("""
            SELECT DISTINCT
                venue_code,
                race_date
            FROM races
            WHERE race_date >= ? AND race_date <= ?
              AND venue_code IN ('15', '16', '17', '18', '20', '22', '24')
            ORDER BY venue_code, race_date
        """, (start_date, end_date))

        rows = cursor.fetchall()
        conn.close()

        # データ構造化
        race_dates = {}
        for venue_code, race_date in rows:
            if venue_code not in race_dates:
                race_dates[venue_code] = {}

            # YYYY-MM-DD → YYYY-MM と 日
            year_month = race_date[:7]  # '2015-01'
            day = int(race_date[8:10])  # 1-31

            if year_month not in race_dates[venue_code]:
                race_dates[venue_code][year_month] = set()

            race_dates[venue_code][year_month].add(day)

        return race_dates

    def download_and_filter_month_data(self, station_name: str, year: int, month: int,
                                       target_days: Set[int]) -> int:
        """
        指定された年月のデータをダウンロードし、レース開催日のみをインポート

        Args:
            station_name: 観測点名
            year: 年
            month: 月
            target_days: 対象日のセット（例: {1, 3, 5, 15, 20}）

        Returns:
            int: インポートしたレコード数
        """
        from src.scraper.rdmdb_tide_parser import RDMDBTideParser

        # ファイル名生成
        if year < 2023 or (year == 2022 and month <= 12):
            file_suffix = f".30s_{station_name}"
        else:
            file_suffix = f".1m_{station_name}"

        filename = f"{year}_{month:02d}{file_suffix}"
        filepath = os.path.join(self.download_dir, filename)

        # ダウンロード
        url = f"{self.base_url}/{year}/{filename}"

        try:
            if not os.path.exists(filepath):
                print(f"    ダウンロード中...")
                response = self.session.get(url, timeout=30)

                if response.status_code == 200:
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    time.sleep(self.delay)
                elif response.status_code == 404:
                    print(f"    [SKIP] データなし (404)")
                    return 0
                else:
                    print(f"    [ERROR] HTTPステータス {response.status_code}")
                    return 0

            # ファイルをパースして、レース開催日のみをフィルタリング
            print(f"    パース中... (対象日: {sorted(target_days)})")
            tide_data = RDMDBTideParser.parse_file(filepath, year, month)

            # レース開催日のみをフィルタリング
            filtered_data = []
            for data in tide_data:
                # datetimeから日を抽出
                dt_str = data['datetime']  # '2015-01-03 12:34:56'
                day = int(dt_str[8:10])

                if day in target_days:
                    filtered_data.append(data)

            print(f"    フィルタ結果: {len(tide_data):,} → {len(filtered_data):,} レコード")

            # データベースにインポート
            if len(filtered_data) > 0:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                imported = 0
                for data in filtered_data:
                    try:
                        cursor.execute("""
                            INSERT INTO rdmdb_tide (
                                station_name,
                                observation_datetime,
                                sea_level_cm,
                                air_pressure_hpa,
                                temperature_c,
                                sea_level_smoothed_cm,
                                created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                        """, (
                            station_name,
                            data['datetime'],
                            data['sea_level_cm'],
                            data['air_pressure_hpa'],
                            data['temperature_c'],
                            data['sea_level_smoothed_cm']
                        ))
                        imported += 1
                    except sqlite3.IntegrityError:
                        pass  # 重複はスキップ

                conn.commit()
                conn.close()

                print(f"    [OK] {imported:,} レコードをインポート")
                return imported
            else:
                print(f"    [WARN] フィルタ後のデータが0件")
                return 0

        except Exception as e:
            print(f"    [ERROR] {e}")
            return 0

    def fetch_optimized(self, start_date: str, end_date: str):
        """
        レース開催日のみのデータを取得（最適化版）

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)
        """
        print("="*80)
        print("潮位データ取得（最適化版 - レース開催日のみ）")
        print("="*80)
        print(f"期間: {start_date} ～ {end_date}")
        print("="*80)

        # レース開催日を取得
        print("\n【ステップ1】 レース開催日を取得中...")
        race_dates = self.get_race_dates_by_venue_month(start_date, end_date)

        # 統計情報
        total_race_days = 0
        total_months = 0
        for venue_code, months_data in race_dates.items():
            venue_name = self.VENUE_TO_STATION[venue_code]['name']
            month_count = len(months_data)
            day_count = sum(len(days) for days in months_data.values())
            total_race_days += day_count
            total_months += month_count

            print(f"  {venue_name}({venue_code}): {month_count}ヶ月, {day_count}日")

        print(f"\n合計:")
        print(f"  対象会場: {len(race_dates)} 会場")
        print(f"  対象月: {total_months} ヶ月")
        print(f"  レース開催日: {total_race_days} 日")

        # 推定データ量
        records_per_day = 2880  # 30秒値の場合
        estimated_records = total_race_days * records_per_day
        estimated_size_mb = estimated_records * 50 / 1024 / 1024  # 1レコード約50バイト

        print(f"\n推定データ量:")
        print(f"  レコード数: 約{estimated_records:,}件")
        print(f"  データベース増加量: 約{estimated_size_mb:.1f}MB")
        print(f"\n※ 全日取得の場合の約1/5～1/7の容量です")

        # ダウンロード・インポート
        print("\n【ステップ2】 データダウンロード・インポート")
        print("="*80)

        start_time = time.time()
        total_imported = 0
        processed_months = 0
        errors = 0

        for venue_code, months_data in sorted(race_dates.items()):
            station_info = self.VENUE_TO_STATION[venue_code]
            station_name = station_info['station']
            venue_name = station_info['name']

            print(f"\n【{venue_name}（{station_name}）】")

            for year_month, target_days in sorted(months_data.items()):
                year, month = map(int, year_month.split('-'))

                print(f"  {year}年{month}月 (レース開催: {len(target_days)}日)")

                try:
                    imported = self.download_and_filter_month_data(
                        station_name, year, month, target_days
                    )
                    total_imported += imported
                    processed_months += 1

                except Exception as e:
                    print(f"    [ERROR] {e}")
                    errors += 1

        elapsed = time.time() - start_time

        # サマリー
        print("\n" + "="*80)
        print("取得完了")
        print("="*80)
        print(f"処理月数: {processed_months}/{total_months}")
        print(f"インポートレコード数: {total_imported:,}")
        print(f"エラー: {errors}")
        print(f"実行時間: {elapsed/60:.1f}分")
        print(f"ダウンロード先: {os.path.abspath(self.download_dir)}")
        print("="*80)

        print(f"\n次のステップ:")
        print(f"  python link_tide_to_races.py --start {start_date} --end {end_date}")


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='潮位データ取得（最適化版 - レース開催日のみ）'
    )
    parser.add_argument('--start', default='2015-01-01', help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2021-12-31', help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')
    parser.add_argument('--delay', type=float, default=2.0, help='リクエスト間隔（秒）')

    args = parser.parse_args()

    fetcher = OptimizedTideDataFetcher(
        db_path=args.db,
        delay=args.delay
    )

    fetcher.fetch_optimized(
        start_date=args.start,
        end_date=args.end
    )


if __name__ == '__main__':
    main()
