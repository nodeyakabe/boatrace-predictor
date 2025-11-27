"""
潮位データ紐付けスクリプト

RDMDB潮位データをレースに紐付けし、不足分は気象データから推論する
"""
import sqlite3
from datetime import datetime, timedelta
import logging

# ロギング設定
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


class TideDataLinker:
    def __init__(self, db_path='data/boatrace.db'):
        self.db_path = db_path
        self.conn = None
        self.cursor = None

        # 統計情報
        self.total_races = 0
        self.rdmdb_matched = 0
        self.weather_inferred = 0
        self.no_data = 0

    def connect(self):
        """データベース接続"""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        logger.info(f"データベース接続: {self.db_path}")

    def close(self):
        """データベース切断"""
        if self.conn:
            self.conn.commit()
            self.conn.close()
            logger.info("データベース切断")

    def get_rdmdb_tide_range(self):
        """RDMDB潮位データの期間を取得"""
        self.cursor.execute('''
            SELECT MIN(observation_datetime), MAX(observation_datetime)
            FROM rdmdb_tide
        ''')
        min_dt, max_dt = self.cursor.fetchone()
        logger.info(f"RDMDB潮位データ期間: {min_dt} ~ {max_dt}")
        return min_dt, max_dt

    def get_target_races(self, limit=None):
        """
        対象会場のレースを取得

        Args:
            limit: 取得件数制限（None=全件）
        """
        query = '''
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
        '''

        if limit:
            query += f' LIMIT {limit}'

        self.cursor.execute(query)
        races = self.cursor.fetchall()
        logger.info(f"対象レース数: {len(races):,}件")
        return races

    def find_rdmdb_tide(self, venue_code, race_date, race_time):
        """
        RDMDB潮位データから最も近い潮位を検索（±5分以内）

        Returns:
            (sea_level_cm, time_diff_minutes) or None
        """
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
            return result[0], result[1]  # sea_level_cm, diff_min
        return None

    def infer_tide_from_weather(self, venue_code, race_date):
        """
        気象データから潮位を推論（簡易版）

        現時点では月齢ベースの簡易推定
        後で実測データで上書き可能にする
        """
        # 月齢から大まかな潮位を推定
        # 新月・満月 → 大潮（潮位変動大）
        # 上弦・下弦 → 小潮（潮位変動小）

        try:
            date_obj = datetime.strptime(race_date, '%Y-%m-%d')

            # 簡易的な月齢計算（2000年1月6日が新月）
            base_new_moon = datetime(2000, 1, 6)
            days_since = (date_obj - base_new_moon).days
            moon_age = days_since % 29.53  # 朔望月周期

            # 潮位を推定（-100cm ~ +100cm）
            # 新月・満月付近（大潮）: 大きな潮位変動
            # 上弦・下弦（小潮）: 小さな潮位変動

            if moon_age < 2 or moon_age > 27:  # 新月付近
                base_tide = 80
            elif 13 < moon_age < 16:  # 満月付近
                base_tide = 80
            elif 6 < moon_age < 9:  # 上弦
                base_tide = 30
            elif 20 < moon_age < 23:  # 下弦
                base_tide = 30
            else:
                base_tide = 50

            # 会場による補正（海水/淡水）
            if venue_code in ['15', '16', '17', '18']:  # 瀬戸内海
                tide_cm = base_tide * 0.8
            elif venue_code in ['19', '20', '21', '22']:  # 玄界灘
                tide_cm = base_tide * 1.2
            elif venue_code in ['23', '24']:  # 大村湾・唐津
                tide_cm = base_tide * 0.6
            else:
                tide_cm = base_tide

            return int(tide_cm), 'inferred_from_moon_phase'

        except Exception as e:
            logger.warning(f"月齢推論エラー: {e}")
            return None

    def update_race_tide(self, race_id, sea_level_cm, data_source):
        """
        レースの潮位情報を更新

        Args:
            race_id: レースID
            sea_level_cm: 潮位（cm）
            data_source: データソース ('rdmdb' or 'inferred')
        """
        # まず既存の潮位データを確認
        self.cursor.execute('''
            SELECT id FROM race_tide_data
            WHERE race_id = ?
        ''', (race_id,))

        existing = self.cursor.fetchone()

        if existing:
            # 既存データがRDMDB実測値の場合は上書きしない
            # 推論値の場合のみ、実測値で上書き可能
            if data_source == 'rdmdb':
                self.cursor.execute('''
                    UPDATE race_tide_data
                    SET sea_level_cm = ?, data_source = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE race_id = ?
                ''', (sea_level_cm, data_source, race_id))
        else:
            # 新規登録
            self.cursor.execute('''
                INSERT INTO race_tide_data (race_id, sea_level_cm, data_source)
                VALUES (?, ?, ?)
            ''', (race_id, sea_level_cm, data_source))

    def create_tide_table_if_not_exists(self):
        """潮位データテーブルを作成（存在しない場合）"""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS race_tide_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL UNIQUE,
                sea_level_cm INTEGER NOT NULL,
                data_source TEXT NOT NULL,  -- 'rdmdb' or 'inferred'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (race_id) REFERENCES races(id)
            )
        ''')
        self.conn.commit()
        logger.info("潮位データテーブル準備完了")

    def link_tide_data(self, limit=None):
        """
        潮位データを紐付け

        Args:
            limit: 処理件数制限（None=全件）
        """
        self.connect()

        try:
            # テーブル作成
            self.create_tide_table_if_not_exists()

            # RDMDB期間確認
            rdmdb_min, rdmdb_max = self.get_rdmdb_tide_range()

            # 対象レース取得
            races = self.get_target_races(limit)
            self.total_races = len(races)

            logger.info("=" * 80)
            logger.info("潮位データ紐付け開始")
            logger.info("=" * 80)

            for idx, (race_id, venue_code, race_date, race_time) in enumerate(races, 1):
                if idx % 100 == 0:
                    logger.info(f"進捗: {idx}/{self.total_races} ({idx/self.total_races*100:.1f}%)")

                # 1. RDMDB実測値を検索
                rdmdb_result = self.find_rdmdb_tide(venue_code, race_date, race_time)

                if rdmdb_result:
                    sea_level_cm, diff_min = rdmdb_result
                    self.update_race_tide(race_id, sea_level_cm, 'rdmdb')
                    self.rdmdb_matched += 1

                    if idx <= 10:  # 最初の10件はログ出力
                        logger.info(f"  レースID {race_id}: RDMDB潮位={sea_level_cm}cm (時刻差{diff_min}分)")

                else:
                    # 2. 気象データから推論
                    inferred_result = self.infer_tide_from_weather(venue_code, race_date)

                    if inferred_result:
                        sea_level_cm, source = inferred_result
                        self.update_race_tide(race_id, sea_level_cm, 'inferred')
                        self.weather_inferred += 1

                        if idx <= 10:
                            logger.info(f"  レースID {race_id}: 推論潮位={sea_level_cm}cm (月齢推定)")
                    else:
                        self.no_data += 1

                # 100件ごとにコミット
                if idx % 100 == 0:
                    self.conn.commit()

            # 最終コミット
            self.conn.commit()

            # 結果サマリー
            logger.info("=" * 80)
            logger.info("潮位データ紐付け完了")
            logger.info("=" * 80)
            logger.info(f"総レース数: {self.total_races:,}件")
            logger.info(f"RDMDB実測値: {self.rdmdb_matched:,}件 ({self.rdmdb_matched/self.total_races*100:.1f}%)")
            logger.info(f"月齢推論値: {self.weather_inferred:,}件 ({self.weather_inferred/self.total_races*100:.1f}%)")
            logger.info(f"データなし: {self.no_data:,}件 ({self.no_data/self.total_races*100:.1f}%)")
            logger.info("=" * 80)

        finally:
            self.close()


if __name__ == '__main__':
    linker = TideDataLinker()

    # 本番実行: 全件処理
    logger.info("全件実行: 対象会場の全レースで潮位紐付け")
    linker.link_tide_data()  # 全件処理
