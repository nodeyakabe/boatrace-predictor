"""
競艇場独自データ収集スクリプト（CSV出力）

優先度高データを収集:
1. 潮汐表（海水面競艇場のみ）
2. リアルタイム気象データ
3. 前検タイムランキング
4. 進入コース別成績

使用方法:
    python scripts/data_collection/fetch_venue_specific_data.py \\
        --start 2024-01-01 \\
        --end 2024-12-31 \\
        --output data/csv/venue_specific_2024 \\
        --types tide,weather,zenken,course
"""

import argparse
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.scraper.tide_scraper import TideScraper
from src.scraper.venue_specific_scraper import VenueSpecificScraper, MarugameScraper, KojimaScraper


class VenueSpecificDataCollector:
    """競艇場独自データ収集クラス"""

    # 海水面競艇場リスト
    SEAWATER_VENUES = ['14', '15', '16', '17', '18', '19', '20', '22', '23']

    # 全競艇場リスト
    ALL_VENUES = [f"{i:02d}" for i in range(1, 25)]

    def __init__(self, output_dir, data_types=None):
        """
        初期化

        Args:
            output_dir: CSV出力先ディレクトリ
            data_types: 収集するデータタイプのリスト ['tide', 'weather', 'zenken', 'course']
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.data_types = data_types or ['tide', 'weather', 'zenken', 'course']

        # スクレイパー初期化
        self.tide_scraper = TideScraper(delay=2.0) if 'tide' in self.data_types else None
        self.venue_scraper = VenueSpecificScraper()

        # CSVファイルの準備
        self.csv_writers = {}
        self.csv_files = {}
        self._init_csv_files()

    def _init_csv_files(self):
        """CSVファイルを初期化"""
        if 'tide' in self.data_types:
            tide_file = self.output_dir / 'tide_data.csv'
            self.csv_files['tide'] = open(tide_file, 'w', newline='', encoding='utf-8')
            self.csv_writers['tide'] = csv.writer(self.csv_files['tide'])
            self.csv_writers['tide'].writerow([
                'venue_code', 'race_date', 'tide_time', 'tide_type', 'tide_level_cm'
            ])

        if 'weather' in self.data_types:
            weather_file = self.output_dir / 'weather_data.csv'
            self.csv_files['weather'] = open(weather_file, 'w', newline='', encoding='utf-8')
            self.csv_writers['weather'] = csv.writer(self.csv_files['weather'])
            self.csv_writers['weather'].writerow([
                'venue_code', 'race_date', 'wind_speed', 'wind_direction',
                'temperature', 'water_temperature', 'weather', 'wave_height'
            ])

        if 'zenken' in self.data_types:
            zenken_file = self.output_dir / 'zenken_time.csv'
            self.csv_files['zenken'] = open(zenken_file, 'w', newline='', encoding='utf-8')
            self.csv_writers['zenken'] = csv.writer(self.csv_files['zenken'])
            self.csv_writers['zenken'].writerow([
                'venue_code', 'race_date', 'racer_id', 'pit', 'zenken_time', 'motor_no'
            ])

        if 'course' in self.data_types:
            course_file = self.output_dir / 'course_stats.csv'
            self.csv_files['course'] = open(course_file, 'w', newline='', encoding='utf-8')
            self.csv_writers['course'] = csv.writer(self.csv_files['course'])
            self.csv_writers['course'].writerow([
                'venue_code', 'year', 'month', 'course',
                'win_rate', 'place_rate_2', 'place_rate_3', 'samples'
            ])

    def collect_tide_data(self, venue_code, date_str):
        """
        潮汐表データを収集

        Args:
            venue_code: 競艇場コード
            date_str: 日付文字列（YYYY-MM-DD）

        Returns:
            int: 収集件数
        """
        if venue_code not in self.SEAWATER_VENUES:
            return 0

        try:
            tide_data = self.tide_scraper.get_tide_data(venue_code, date_str)

            if not tide_data:
                return 0

            count = 0
            for tide in tide_data:
                self.csv_writers['tide'].writerow([
                    venue_code,
                    date_str,
                    tide['time'],
                    tide['type'],
                    tide['level']
                ])
                count += 1

            return count

        except Exception as e:
            print(f"  潮汐データ収集エラー ({venue_code}, {date_str}): {e}")
            return 0

    def collect_weather_data(self, venue_code, date_str):
        """
        気象データを収集

        Args:
            venue_code: 競艇場コード
            date_str: 日付文字列（YYYY-MM-DD）

        Returns:
            int: 収集件数
        """
        try:
            weather_data = self.venue_scraper.get_weather_data(venue_code, date_str)

            if not weather_data:
                return 0

            self.csv_writers['weather'].writerow([
                venue_code,
                date_str,
                weather_data.get('wind_speed'),
                weather_data.get('wind_direction'),
                weather_data.get('temperature'),
                weather_data.get('water_temperature'),
                weather_data.get('weather'),
                weather_data.get('wave_height')
            ])

            return 1

        except Exception as e:
            print(f"  気象データ収集エラー ({venue_code}, {date_str}): {e}")
            return 0

    def collect_zenken_time(self, venue_code, date_str):
        """
        前検タイムランキングを収集

        Args:
            venue_code: 競艇場コード
            date_str: 日付文字列（YYYY-MM-DD）

        Returns:
            int: 収集件数
        """
        try:
            zenken_data = self.venue_scraper.get_zenken_time_ranking(venue_code, date_str)

            if not zenken_data:
                return 0

            count = 0
            for racer in zenken_data:
                self.csv_writers['zenken'].writerow([
                    venue_code,
                    date_str,
                    racer['racer_id'],
                    racer['pit'],
                    racer['time'],
                    racer['motor_no']
                ])
                count += 1

            return count

        except Exception as e:
            print(f"  前検タイム収集エラー ({venue_code}, {date_str}): {e}")
            return 0

    def collect_course_stats(self, venue_code, year, month):
        """
        進入コース別成績を収集

        Args:
            venue_code: 競艇場コード
            year: 年
            month: 月

        Returns:
            int: 収集件数
        """
        try:
            course_data = self.venue_scraper.get_course_stats(venue_code, year, month)

            if not course_data:
                return 0

            count = 0
            for course in course_data:
                self.csv_writers['course'].writerow([
                    venue_code,
                    year,
                    month,
                    course['course'],
                    course['win_rate'],
                    course['place_rate_2'],
                    course['place_rate_3'],
                    course['samples']
                ])
                count += 1

            return count

        except Exception as e:
            print(f"  進入コース別成績収集エラー ({venue_code}, {year}-{month}): {e}")
            return 0

    def collect_date_range(self, start_date, end_date, venues=None):
        """
        期間指定でデータを収集

        Args:
            start_date: 開始日（YYYY-MM-DD）
            end_date: 終了日（YYYY-MM-DD）
            venues: 対象競艇場リスト（Noneの場合は全競艇場）
        """
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        venues = venues or self.ALL_VENUES

        total_days = (end - start).days + 1
        print(f"\n収集開始: {start_date} ～ {end_date} ({total_days}日間)")
        print(f"対象競艇場: {len(venues)}場")
        print(f"収集データタイプ: {', '.join(self.data_types)}")
        print("=" * 70)

        current = start
        day_count = 0

        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            day_count += 1

            print(f"\n[{day_count}/{total_days}] {date_str}")

            for venue_code in venues:
                # 潮汐表（海水面のみ）
                if 'tide' in self.data_types:
                    count = self.collect_tide_data(venue_code, date_str)
                    if count > 0:
                        print(f"  {venue_code}: 潮汐データ {count}件")

                # 気象データ
                if 'weather' in self.data_types:
                    count = self.collect_weather_data(venue_code, date_str)
                    if count > 0:
                        print(f"  {venue_code}: 気象データ {count}件")

                # 前検タイム
                if 'zenken' in self.data_types:
                    count = self.collect_zenken_time(venue_code, date_str)
                    if count > 0:
                        print(f"  {venue_code}: 前検タイム {count}件")

            # 50日ごとにフラッシュ（データ保存）
            if day_count % 50 == 0:
                self.flush()
                print(f"\n✓ 中間保存完了 ({day_count}/{total_days}日)")

            current += timedelta(days=1)

        # 進入コース別成績（月次データ）
        if 'course' in self.data_types:
            print("\n進入コース別成績を収集中...")
            for venue_code in venues:
                for year in range(start.year, end.year + 1):
                    for month in range(1, 13):
                        count = self.collect_course_stats(venue_code, year, month)
                        if count > 0:
                            print(f"  {venue_code} {year}-{month:02d}: {count}件")

        print("\n" + "=" * 70)
        print("収集完了")

    def flush(self):
        """CSV書き込みをフラッシュ"""
        for f in self.csv_files.values():
            f.flush()

    def close(self):
        """リソースをクローズ"""
        for f in self.csv_files.values():
            f.close()

        if self.tide_scraper:
            self.tide_scraper.close()
        self.venue_scraper.close()


def main():
    parser = argparse.ArgumentParser(description='競艇場独自データ収集（CSV出力）')
    parser.add_argument('--start', required=True, help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--output', required=True, help='CSV出力先ディレクトリ')
    parser.add_argument('--types', default='tide,weather,zenken,course',
                        help='収集データタイプ (カンマ区切り: tide,weather,zenken,course)')
    parser.add_argument('--venues', default=None,
                        help='対象競艇場コード (カンマ区切り、省略時は全競艇場)')

    args = parser.parse_args()

    # データタイプをリストに変換
    data_types = [t.strip() for t in args.types.split(',')]

    # 競艇場リスト
    venues = None
    if args.venues:
        venues = [v.strip() for v in args.venues.split(',')]

    # 収集実行
    collector = VenueSpecificDataCollector(args.output, data_types)

    try:
        collector.collect_date_range(args.start, args.end, venues)
    except KeyboardInterrupt:
        print("\n\n中断されました")
    finally:
        collector.close()

    print(f"\nCSVファイル: {args.output}/")


if __name__ == "__main__":
    main()
