"""
気象庁RDMDB から過去の潮位データを取得
2015-2021年の欠損データを補完

RDMDB (Real-time Database): 気象庁リアルタイムデータベース
URL: https://www.data.jma.go.jp/gmd/kaiyou/db/tide/genbo/index.php
"""

import os
import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import sqlite3
from pathlib import Path


class HistoricalTideDataFetcher:
    """気象庁から過去の潮位データを取得"""

    # ボートレース場と気象庁観測地点のマッピング
    VENUE_TO_STATION = {
        '15': {'name': '丸亀', 'station': 'Marugame', 'jma_name': '丸亀'},
        '16': {'name': '児島', 'station': 'Kojima', 'jma_name': '児島'},
        '17': {'name': '宮島', 'station': 'Hiroshima', 'jma_name': '広島'},
        '18': {'name': '徳山', 'station': 'Tokuyama', 'jma_name': '徳山'},
        '20': {'name': '若松', 'station': 'Wakamatsu', 'jma_name': '若松'},
        '22': {'name': '福岡', 'station': 'Hakata', 'jma_name': '博多'},
        '24': {'name': '大村', 'station': 'Sasebo', 'jma_name': '佐世保'},
    }

    def __init__(self, download_dir="rdmdb_downloads_historical", delay=2.0):
        """
        初期化

        Args:
            download_dir: ダウンロードディレクトリ
            delay: リクエスト間の待機時間（秒）
        """
        self.download_dir = download_dir
        self.delay = delay
        self.base_url = "https://www.data.jma.go.jp/gmd/kaiyou/db/tide/genbo"

        # ダウンロードディレクトリを作成
        Path(self.download_dir).mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def download_month_data(self, station_name: str, year: int, month: int) -> Optional[str]:
        """
        指定された観測点・年月のデータをダウンロード

        Args:
            station_name: 観測点名（英語、例: "Hakata"）
            year: 年
            month: 月

        Returns:
            str: ダウンロードしたファイルパス（成功時）、None（失敗時）
        """
        # ファイル名生成
        # 2022年12月まで: 30秒値（.30s_）
        # 2023年1月以降: 1分値（.1m_）
        if year < 2023 or (year == 2022 and month <= 12):
            interval = "30s"
            file_suffix = f".30s_{station_name}"
        else:
            interval = "1m"
            file_suffix = f".1m_{station_name}"

        filename = f"{year}_{month:02d}{file_suffix}"
        filepath = os.path.join(self.download_dir, filename)

        # すでにダウンロード済みの場合はスキップ
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            if file_size > 1000:  # 1KB以上あれば有効なファイルとみなす
                print(f"  スキップ: {filename} (すでに存在)")
                return filepath

        # ダウンロードURL構築
        # 例: https://www.data.jma.go.jp/gmd/kaiyou/db/tide/genbo/2022/2022_11.30s_Hakata
        url = f"{self.base_url}/{year}/{filename}"

        try:
            print(f"  ダウンロード中: {filename}")
            response = self.session.get(url, timeout=30)

            if response.status_code == 200:
                # ファイルに保存
                with open(filepath, 'wb') as f:
                    f.write(response.content)

                file_size = os.path.getsize(filepath)
                print(f"    [OK] {file_size:,} バイト")

                time.sleep(self.delay)
                return filepath

            elif response.status_code == 404:
                print(f"    [SKIP] データなし (404)")
                return None
            else:
                print(f"    [ERROR] HTTPステータス {response.status_code}")
                return None

        except Exception as e:
            print(f"    [ERROR] {e}")
            return None

    def download_period(self, start_date: str, end_date: str, venues: List[str] = None):
        """
        指定期間のデータをダウンロード

        Args:
            start_date: 開始日（YYYY-MM-DD）
            end_date: 終了日（YYYY-MM-DD）
            venues: 対象会場コードのリスト（None の場合は全会場）
        """
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')

        if venues is None:
            venues = list(self.VENUE_TO_STATION.keys())

        print("="*80)
        print("気象庁RDMDB 過去データダウンロード")
        print("="*80)
        print(f"期間: {start_date} ～ {end_date}")
        print(f"対象会場: {len(venues)} 会場")
        print(f"  {', '.join([self.VENUE_TO_STATION[v]['name'] for v in venues])}")
        print("="*80)

        # 年月のリストを生成
        current_dt = start_dt.replace(day=1)
        end_month = end_dt.replace(day=1)

        months = []
        while current_dt <= end_month:
            months.append((current_dt.year, current_dt.month))
            # 次の月へ
            if current_dt.month == 12:
                current_dt = current_dt.replace(year=current_dt.year + 1, month=1)
            else:
                current_dt = current_dt.replace(month=current_dt.month + 1)

        total_files = len(months) * len(venues)
        print(f"\n総ダウンロード数: {total_files} ファイル")
        print(f"  {len(months)} ヶ月 × {len(venues)} 会場")

        # ダウンロード実行
        downloaded = 0
        skipped = 0
        errors = 0

        start_time = time.time()

        for year, month in months:
            print(f"\n【{year}年{month}月】")

            for venue_code in venues:
                station_info = self.VENUE_TO_STATION[venue_code]
                station_name = station_info['station']
                jma_name = station_info['jma_name']

                print(f"  {station_info['name']}（{jma_name}）")

                filepath = self.download_month_data(station_name, year, month)

                if filepath:
                    if "スキップ" in str(filepath):
                        skipped += 1
                    else:
                        downloaded += 1
                else:
                    errors += 1

        elapsed = time.time() - start_time

        # サマリー
        print("\n" + "="*80)
        print("ダウンロード完了")
        print("="*80)
        print(f"総ファイル数: {total_files}")
        print(f"  新規ダウンロード: {downloaded}")
        print(f"  スキップ: {skipped}")
        print(f"  エラー: {errors}")
        print(f"実行時間: {elapsed/60:.1f}分")
        print("="*80)

        print(f"\nダウンロード先: {os.path.abspath(self.download_dir)}")

    def import_to_database(self, db_path="data/boatrace.db"):
        """
        ダウンロードしたファイルをデータベースにインポート

        Args:
            db_path: データベースパス
        """
        from src.scraper.rdmdb_tide_parser import RDMDBTideParser

        print("\n" + "="*80)
        print("データベースインポート")
        print("="*80)

        # ダウンロードディレクトリ内のファイルを取得
        files = [f for f in os.listdir(self.download_dir) if not f.startswith('.')]
        print(f"ファイル数: {len(files)}")

        if len(files) == 0:
            print("インポートするファイルがありません")
            return

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        imported_records = 0
        processed_files = 0

        start_time = time.time()

        for filename in sorted(files):
            filepath = os.path.join(self.download_dir, filename)

            # ファイル名から年月を抽出
            # 例: 2015_01.30s_Hakata → 2015年1月
            match = os.path.basename(filename).split('.')
            if len(match) < 2:
                continue

            year_month = match[0]
            parts = year_month.split('_')
            if len(parts) != 2:
                continue

            year = int(parts[0])
            month = int(parts[1])

            # 観測点名を抽出
            station_name = filename.split('_')[-1]

            print(f"\n処理中: {filename}")
            print(f"  年月: {year}年{month}月")
            print(f"  観測点: {station_name}")

            # ファイルをパース
            try:
                tide_data = RDMDBTideParser.parse_file(filepath, year, month)
                print(f"  パース結果: {len(tide_data):,} レコード")

                if len(tide_data) == 0:
                    print(f"  [WARN] データが空です")
                    continue

                # データベースに保存
                for data in tide_data:
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
                    except sqlite3.IntegrityError:
                        # 重複データはスキップ
                        pass

                conn.commit()
                imported_records += len(tide_data)
                processed_files += 1

                print(f"  [OK] {len(tide_data):,} レコードをインポート")

            except Exception as e:
                print(f"  [ERROR] {e}")
                import traceback
                traceback.print_exc()

        elapsed = time.time() - start_time

        conn.close()

        # サマリー
        print("\n" + "="*80)
        print("インポート完了")
        print("="*80)
        print(f"処理ファイル数: {processed_files}/{len(files)}")
        print(f"インポートレコード数: {imported_records:,}")
        print(f"実行時間: {elapsed/60:.1f}分")
        print("="*80)


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='気象庁RDMDB 過去潮位データ取得')
    parser.add_argument('--start', default='2015-01-01', help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2021-12-31', help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--venues', nargs='+', help='対象会場コード（例: 15 22 24）')
    parser.add_argument('--download-only', action='store_true', help='ダウンロードのみ（インポートなし）')
    parser.add_argument('--import-only', action='store_true', help='インポートのみ（ダウンロードなし）')
    parser.add_argument('--delay', type=float, default=2.0, help='リクエスト間隔（秒）')

    args = parser.parse_args()

    fetcher = HistoricalTideDataFetcher(delay=args.delay)

    # ダウンロード
    if not args.import_only:
        fetcher.download_period(
            start_date=args.start,
            end_date=args.end,
            venues=args.venues
        )

    # インポート
    if not args.download_only:
        fetcher.import_to_database()


if __name__ == '__main__':
    main()
