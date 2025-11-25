"""
rdmdb_tideデータをrace_tide_dataに紐付け
レース開始時刻に最も近い潮位データを各レースに関連付ける
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict


class TideRaceLinker:
    """潮位データとレースの紐付け"""

    # ボートレース場と気象庁観測地点のマッピング
    VENUE_TO_STATION = {
        '15': 'Marugame',   # 丸亀
        '16': 'Kojima',     # 児島
        '17': 'Hiroshima',  # 宮島 → 広島
        '18': 'Tokuyama',   # 徳山
        '20': 'Wakamatsu',  # 若松
        '22': 'Hakata',     # 福岡 → 博多
        '24': 'Sasebo',     # 大村 → 佐世保
    }

    def __init__(self, db_path="data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path

    def link_races(self, start_date: str, end_date: str, venue_codes: list = None):
        """
        指定期間のレースに潮位データを紐付け

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)
            venue_codes: 対象会場コードのリスト（None の場合は海水場のみ）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if venue_codes is None:
            venue_codes = list(self.VENUE_TO_STATION.keys())

        print("="*80)
        print("潮位データ紐付け")
        print("="*80)
        print(f"期間: {start_date} ～ {end_date}")
        print(f"対象会場: {len(venue_codes)} 会場（海水場のみ）")
        print("="*80)

        # 対象レースを取得
        cursor.execute("""
            SELECT id, venue_code, race_date, race_number
            FROM races
            WHERE race_date >= ? AND race_date <= ?
              AND venue_code IN ({})
            ORDER BY race_date, venue_code, race_number
        """.format(','.join(['?']*len(venue_codes))),
        [start_date, end_date] + venue_codes)

        races = cursor.fetchall()
        print(f"\n対象レース数: {len(races):,}")

        if len(races) == 0:
            print("対象レースがありません")
            conn.close()
            return

        # 処理統計
        linked = 0
        skipped = 0
        errors = 0

        start_time = datetime.now()

        for race_id, venue_code, race_date, race_number in races:
            try:
                # すでにRDMDB実測データが紐付けられているかチェック
                cursor.execute("""
                    SELECT data_source FROM race_tide_data
                    WHERE race_id = ?
                """, (race_id,))

                existing = cursor.fetchone()
                if existing and existing[0].startswith('rdmdb:'):
                    # すでにRDMDB実測値がある場合はスキップ
                    skipped += 1
                    if skipped % 1000 == 0:
                        print(f"  処理中... {linked + skipped + errors}/{len(races)} (紐付け:{linked}, スキップ:{skipped})")
                    continue
                # PyTides推定値がある場合は実測値で上書き

                # レース開始時刻を推定
                # 1R: 15:00, 2R: 15:30, ... (30分間隔と仮定)
                # ※ 実際のレース時刻はrace_timeカラムがあれば使用する
                estimated_hour = 15 + (race_number - 1) // 2
                estimated_minute = 0 if (race_number - 1) % 2 == 0 else 30

                race_datetime = f"{race_date} {estimated_hour:02d}:{estimated_minute:02d}:00"

                # 観測点を取得
                station_name = self.VENUE_TO_STATION.get(venue_code)
                if not station_name:
                    errors += 1
                    continue

                # 最も近い潮位データを取得
                # レース時刻の前後30分以内のデータを検索
                cursor.execute("""
                    SELECT sea_level_cm, observation_datetime
                    FROM rdmdb_tide
                    WHERE station_name = ?
                      AND observation_datetime >= datetime(?, '-30 minutes')
                      AND observation_datetime <= datetime(?, '+30 minutes')
                    ORDER BY ABS(julianday(observation_datetime) - julianday(?))
                    LIMIT 1
                """, (station_name, race_datetime, race_datetime, race_datetime))

                tide_record = cursor.fetchone()

                if tide_record:
                    sea_level_cm, obs_datetime = tide_record

                    # race_tide_dataに保存（PyTides推定値がある場合は上書き）
                    if existing:
                        cursor.execute("""
                            UPDATE race_tide_data
                            SET sea_level_cm = ?,
                                data_source = ?,
                                updated_at = datetime('now')
                            WHERE race_id = ?
                        """, (sea_level_cm, f'rdmdb:{station_name}', race_id))
                    else:
                        cursor.execute("""
                            INSERT INTO race_tide_data (
                                race_id,
                                sea_level_cm,
                                data_source,
                                created_at,
                                updated_at
                            ) VALUES (?, ?, ?, datetime('now'), datetime('now'))
                        """, (race_id, sea_level_cm, f'rdmdb:{station_name}'))

                    linked += 1

                    if linked % 1000 == 0:
                        conn.commit()
                        print(f"  処理中... {linked + skipped + errors}/{len(races)} (紐付け:{linked})")
                else:
                    errors += 1

            except Exception as e:
                print(f"\n  [ERROR] レースID {race_id}: {e}")
                errors += 1

        conn.commit()
        conn.close()

        elapsed = (datetime.now() - start_time).total_seconds()

        # サマリー
        print("\n" + "="*80)
        print("紐付け完了")
        print("="*80)
        print(f"対象レース数: {len(races):,}")
        print(f"  紐付け成功: {linked:,} ({linked/len(races)*100:.1f}%)")
        print(f"  スキップ: {skipped:,} ({skipped/len(races)*100:.1f}%)")
        print(f"  エラー: {errors:,} ({errors/len(races)*100:.1f}%)")
        print(f"実行時間: {elapsed/60:.1f}分")
        print("="*80)


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='潮位データをレースに紐付け')
    parser.add_argument('--start', default='2015-01-01', help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2021-12-31', help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--venues', nargs='+', help='対象会場コード（例: 15 22 24）')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')

    args = parser.parse_args()

    linker = TideRaceLinker(db_path=args.db)
    linker.link_races(
        start_date=args.start,
        end_date=args.end,
        venue_codes=args.venues
    )


if __name__ == '__main__':
    main()
