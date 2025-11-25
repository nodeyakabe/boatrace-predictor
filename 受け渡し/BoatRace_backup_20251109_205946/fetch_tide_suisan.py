"""
気象庁潮位表（潮汐表）から満潮・干潮データを取得
2015-2021年の過去データ取得用

データソース: 気象庁 潮位観測資料（潮汐表）
URL: https://www.data.jma.go.jp/gmd/kaiyou/db/tide/suisan/
"""

import requests
import time
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from bs4 import BeautifulSoup


class TideSuisanFetcher:
    """気象庁潮位表データ取得"""

    # ボートレース場と気象庁観測地点のマッピング
    VENUE_TO_STATION = {
        '15': {'name': '丸亀', 'station_id': '74', 'station_name': '高松'},      # 丸亀 → 高松
        '16': {'name': '児島', 'station_id': '71', 'station_name': '宇野'},      # 児島 → 宇野
        '17': {'name': '宮島', 'station_id': '69', 'station_name': '広島'},      # 宮島 → 広島
        '18': {'name': '徳山', 'station_id': '67', 'station_name': '徳山'},      # 徳山
        '20': {'name': '若松', 'station_id': '64', 'station_name': '若松'},      # 若松
        '22': {'name': '福岡', 'station_id': '61', 'station_name': '博多'},      # 福岡 → 博多
        '24': {'name': '大村', 'station_id': '51', 'station_name': '長崎'},      # 大村 → 長崎
    }

    def __init__(self, db_path="data/boatrace.db", delay=2.0):
        """
        初期化

        Args:
            db_path: データベースパス
            delay: リクエスト間隔（秒）
        """
        self.db_path = db_path
        self.delay = delay
        self.base_url = "https://www.data.jma.go.jp/kaiyou/db/tide/suisan/txt"

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def fetch_month_data(self, station_id: str, year: int, month: int) -> List[Dict]:
        """
        指定された観測点・年月の潮位データを取得

        Args:
            station_id: 観測点ID（例: "61" = 博多）
            year: 年
            month: 月

        Returns:
            list: [
                {
                    'date': '2015-11-08',
                    'time': '03:45',
                    'type': '満潮',
                    'level_cm': 352
                },
                ...
            ]
        """
        # URL構築
        # 例: https://www.data.jma.go.jp/gmd/kaiyou/db/tide/suisan/txt/2015/TK201511.txt
        url = f"{self.base_url}/{year}/TK{year}{month:02d}.txt"

        try:
            print(f"    ダウンロード中: {url}")
            response = self.session.get(url, timeout=30)

            if response.status_code == 404:
                print(f"    [SKIP] データなし (404)")
                return []
            elif response.status_code != 200:
                print(f"    [ERROR] HTTPステータス {response.status_code}")
                return []

            response.encoding = 'shift_jis'
            text = response.text

            # データをパース
            tide_data = self._parse_tide_text(text, station_id, year, month)

            time.sleep(self.delay)
            return tide_data

        except Exception as e:
            print(f"    [ERROR] {e}")
            return []

    def _parse_tide_text(self, text: str, station_id: str, year: int, month: int) -> List[Dict]:
        """
        潮位テキストファイルをパース

        Args:
            text: テキストデータ
            station_id: 観測点ID
            year: 年
            month: 月

        Returns:
            list: 潮位データ
        """
        tide_data = []
        lines = text.split('\n')

        # 観測地点のセクションを探す
        in_target_station = False

        for line in lines:
            # 観測地点IDが含まれる行をチェック
            if station_id in line and '観測点' not in line:
                in_target_station = True
                continue

            if not in_target_station:
                continue

            # データ行のパース
            # フォーマット例: " 1 03:45  352 H  10:12   28 L  16:30  340 H  22:45   50 L"
            parts = line.split()
            if not parts:
                continue

            # 最初の要素が日付（数字）かチェック
            try:
                day = int(parts[0])
            except (ValueError, IndexError):
                # 数字でない場合は次の観測地点に移った可能性
                if in_target_station and len(parts) > 0:
                    # データ行でない場合は終了
                    if not any(c.isdigit() for c in parts[0]):
                        break
                continue

            # 日付文字列を生成
            date_str = f"{year:04d}-{month:02d}-{day:02d}"

            # 潮位データを抽出
            # 形式: 時:分 潮位(cm) タイプ(H=満潮, L=干潮)
            i = 1
            while i < len(parts):
                if ':' in parts[i]:
                    time_str = parts[i]
                    if i + 2 < len(parts):
                        try:
                            level = int(parts[i + 1])
                            tide_type_code = parts[i + 2]

                            tide_data.append({
                                'date': date_str,
                                'time': time_str,
                                'type': '満潮' if tide_type_code == 'H' else '干潮',
                                'level_cm': level
                            })
                            i += 3
                        except (ValueError, IndexError):
                            i += 1
                    else:
                        break
                else:
                    i += 1

        return tide_data

    def fetch_and_save(self, start_date: str, end_date: str, venues: List[str] = None):
        """
        指定期間のデータを取得してデータベースに保存

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)
            venues: 対象会場コードのリスト（None の場合は全海水場）
        """
        if venues is None:
            venues = list(self.VENUE_TO_STATION.keys())

        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')

        print("="*80)
        print("気象庁潮位表データ取得")
        print("="*80)
        print(f"期間: {start_date} ～ {end_date}")
        print(f"対象会場: {len(venues)} 会場")
        print("="*80)

        # 年月リストを生成
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

        total_tasks = len(months) * len(venues)
        print(f"\n総ダウンロード数: {total_tasks} タスク")
        print(f"  {len(months)} ヶ月 × {len(venues)} 会場")

        # データベース接続
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # tideテーブルにデータを保存
        total_records = 0
        processed = 0
        errors = 0

        start_time = time.time()

        for year, month in months:
            print(f"\n【{year}年{month}月】")

            for venue_code in venues:
                station_info = self.VENUE_TO_STATION[venue_code]
                station_id = station_info['station_id']
                venue_name = station_info['name']
                station_name = station_info['station_name']

                print(f"  {venue_name}（{station_name}）")

                try:
                    tide_data = self.fetch_month_data(station_id, year, month)

                    if tide_data:
                        # データベースに保存
                        for data in tide_data:
                            try:
                                cursor.execute("""
                                    INSERT INTO tide (
                                        venue_code,
                                        tide_date,
                                        tide_time,
                                        tide_type,
                                        tide_level,
                                        created_at
                                    ) VALUES (?, ?, ?, ?, ?, datetime('now'))
                                """, (
                                    venue_code,
                                    data['date'],
                                    data['time'],
                                    data['type'],
                                    data['level_cm']
                                ))
                                total_records += 1
                            except sqlite3.IntegrityError:
                                pass  # 重複はスキップ

                        conn.commit()
                        print(f"    [OK] {len(tide_data)} レコード")
                        processed += 1
                    else:
                        errors += 1

                except Exception as e:
                    print(f"    [ERROR] {e}")
                    errors += 1

        conn.close()

        elapsed = time.time() - start_time

        # サマリー
        print("\n" + "="*80)
        print("取得完了")
        print("="*80)
        print(f"処理タスク数: {processed}/{total_tasks}")
        print(f"インポートレコード数: {total_records:,}")
        print(f"エラー: {errors}")
        print(f"実行時間: {elapsed/60:.1f}分")
        print("="*80)

        print(f"\n次のステップ:")
        print(f"  python link_tide_to_races.py --start {start_date} --end {end_date}")


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='気象庁潮位表データ取得（満潮・干潮）'
    )
    parser.add_argument('--start', default='2015-11-01', help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2021-12-31', help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--venues', nargs='+', help='対象会場コード（例: 22 24）')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')
    parser.add_argument('--delay', type=float, default=2.0, help='リクエスト間隔（秒）')

    args = parser.parse_args()

    fetcher = TideSuisanFetcher(
        db_path=args.db,
        delay=args.delay
    )

    fetcher.fetch_and_save(
        start_date=args.start,
        end_date=args.end,
        venues=args.venues
    )


if __name__ == '__main__':
    main()
