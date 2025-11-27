"""
潮位データ紐付けスクリプト（高速版）

効率化ポイント:
1. 既存データをスキップ
2. バッチINSERT
3. トランザクション最適化
"""
import sqlite3
from datetime import datetime
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 会場と観測地点のマッピング（距離ベースで最適化）
VENUE_STATION_MAP = {
    '15': 'Hiroshima',  # 丸亀 (118.6km)
    '16': 'Hiroshima',  # 児島 (120.2km)
    '17': 'Hiroshima',  # 宮島 (21.1km)
    '18': 'Tokuyama',   # 徳山 (5.8km)
    '19': 'Hakata',     # 下関 (63.3km)
    '20': 'Hakata',     # 若松 (50.9km)
    '21': 'Hakata',     # 芦屋 (39.8km)
    '22': 'Hakata',     # 福岡 (10.9km)
    '23': 'Sasebo',     # 唐津 (37.9km)
    '24': 'Sasebo',     # 大村 (38.8km)
}


class FastTideDataLinker:
    def __init__(self, db_path='data/boatrace.db'):
        self.db_path = db_path
        self.conn = None
        self.cursor = None

        # 統計
        self.total_races = 0
        self.skipped = 0
        self.rdmdb_matched = 0
        self.inferred = 0

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        logger.info(f"データベース接続: {self.db_path}")

    def close(self):
        if self.conn:
            self.conn.commit()
            self.conn.close()
            logger.info("データベース切断")

    def get_existing_race_ids(self):
        """既に潮位データがあるレースIDを取得"""
        self.cursor.execute('SELECT race_id FROM race_tide_data')
        return set(row[0] for row in self.cursor.fetchall())

    def get_target_races(self):
        """対象レースを取得（既存データを除外）"""
        # 既存データを取得
        existing_ids = self.get_existing_race_ids()
        logger.info(f"既存潮位データ: {len(existing_ids):,}件")

        # 対象レースを取得
        self.cursor.execute('''
            SELECT
                r.id,
                r.venue_code,
                r.race_date,
                r.race_time
            FROM races r
            WHERE r.venue_code IN ('15', '16', '17', '18', '19', '20', '21', '22', '23', '24')
            AND r.race_status = 'completed'
            AND r.race_time IS NOT NULL
            ORDER BY r.race_date DESC, r.race_number DESC
        ''')

        # 既存データを除外
        all_races = self.cursor.fetchall()
        new_races = [r for r in all_races if r[0] not in existing_ids]

        logger.info(f"総対象レース: {len(all_races):,}件")
        logger.info(f"処理済みスキップ: {len(existing_ids):,}件")
        logger.info(f"新規処理対象: {len(new_races):,}件")

        self.skipped = len(existing_ids)
        return new_races

    def find_rdmdb_tide(self, venue_code, race_date, race_time):
        """RDMDB潮位データから最も近い潮位を検索"""
        station = VENUE_STATION_MAP.get(venue_code)
        if not station:
            return None

        self.cursor.execute('''
            SELECT
                sea_level_cm,
                ABS(ROUND((JULIANDAY(? || ' ' || ?) - JULIANDAY(observation_datetime)) * 1440)) as diff_min
            FROM rdmdb_tide
            WHERE station_name = ?
            AND DATE(observation_datetime) = ?
            AND ABS(ROUND((JULIANDAY(? || ' ' || ?) - JULIANDAY(observation_datetime)) * 1440)) <= 5
            ORDER BY diff_min
            LIMIT 1
        ''', (race_date, race_time, station, race_date, race_date, race_time))

        result = self.cursor.fetchone()
        if result:
            return result[0], result[1], 'rdmdb'
        return None

    def infer_tide_from_moon(self, venue_code, race_date):
        """月齢から潮位を推論"""
        try:
            date_obj = datetime.strptime(race_date, '%Y-%m-%d')
            base_new_moon = datetime(2000, 1, 6)
            days_since = (date_obj - base_new_moon).days
            moon_age = days_since % 29.53

            if moon_age < 2 or moon_age > 27:
                base_tide = 80
            elif 13 < moon_age < 16:
                base_tide = 80
            elif 6 < moon_age < 9:
                base_tide = 30
            elif 20 < moon_age < 23:
                base_tide = 30
            else:
                base_tide = 50

            if venue_code in ['15', '16', '17', '18']:
                tide_cm = base_tide * 0.8
            elif venue_code in ['19', '20', '21', '22']:
                tide_cm = base_tide * 1.2
            elif venue_code in ['23', '24']:
                tide_cm = base_tide * 0.6
            else:
                tide_cm = base_tide

            return int(tide_cm), 0, 'inferred'

        except Exception as e:
            logger.warning(f"月齢推論エラー: {e}")
            return None

    def process_races(self):
        """レースを高速処理"""
        self.connect()

        try:
            # 対象レース取得
            races = self.get_target_races()
            self.total_races = len(races)

            if self.total_races == 0:
                logger.info("処理対象なし")
                return

            logger.info("=" * 80)
            logger.info("潮位データ紐付け開始（高速版）")
            logger.info("=" * 80)

            # バッチ挿入用リスト
            batch_data = []
            batch_size = 1000

            for idx, (race_id, venue_code, race_date, race_time) in enumerate(races, 1):
                if idx % 100 == 0:
                    logger.info(f"進捗: {idx}/{self.total_races} ({idx/self.total_races*100:.1f}%)")

                # RDMDB実測値を検索
                tide_result = self.find_rdmdb_tide(venue_code, race_date, race_time)

                if tide_result:
                    sea_level, diff_min, source = tide_result
                    batch_data.append((race_id, sea_level, source))
                    self.rdmdb_matched += 1
                else:
                    # 月齢推論
                    tide_result = self.infer_tide_from_moon(venue_code, race_date)
                    if tide_result:
                        sea_level, diff_min, source = tide_result
                        batch_data.append((race_id, sea_level, source))
                        self.inferred += 1

                # バッチ挿入
                if len(batch_data) >= batch_size:
                    self._batch_insert(batch_data)
                    batch_data = []

            # 残りを挿入
            if batch_data:
                self._batch_insert(batch_data)

            # 最終コミット
            self.conn.commit()

            # サマリー
            logger.info("=" * 80)
            logger.info("潮位データ紐付け完了")
            logger.info("=" * 80)
            logger.info(f"総対象レース: {self.total_races:,}件")
            logger.info(f"処理済みスキップ: {self.skipped:,}件")
            logger.info(f"RDMDB実測値: {self.rdmdb_matched:,}件")
            logger.info(f"月齢推論値: {self.inferred:,}件")
            logger.info("=" * 80)

        finally:
            self.close()

    def _batch_insert(self, batch_data):
        """バッチINSERT"""
        if not batch_data:
            return

        self.cursor.executemany('''
            INSERT OR REPLACE INTO race_tide_data (race_id, sea_level_cm, data_source)
            VALUES (?, ?, ?)
        ''', batch_data)
        self.conn.commit()


if __name__ == '__main__':
    linker = FastTideDataLinker()
    linker.process_races()
