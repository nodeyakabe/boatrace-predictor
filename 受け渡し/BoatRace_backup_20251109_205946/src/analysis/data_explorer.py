"""
データ探索ツール

Phase 3の準備として、収集済みデータの探索・統計量算出を行う
"""

import sqlite3
import pandas as pd
from pathlib import Path


class DataExplorer:
    """データ探索クラス"""

    def __init__(self, db_path="data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースファイルのパス
        """
        self.db_path = db_path
        self.conn = None

    def connect(self):
        """データベースに接続"""
        self.conn = sqlite3.connect(self.db_path)
        return self.conn

    def close(self):
        """データベース接続を閉じる"""
        if self.conn:
            self.conn.close()

    def get_race_count(self):
        """
        収集済みレース数を取得

        Returns:
            dict: レース数の統計
        """
        if not self.conn:
            self.connect()

        # 総レース数
        total_races = pd.read_sql_query(
            "SELECT COUNT(*) as count FROM races",
            self.conn
        )['count'][0]

        # 結果がある レース数
        races_with_results = pd.read_sql_query(
            "SELECT COUNT(*) as count FROM races WHERE result_1st IS NOT NULL",
            self.conn
        )['count'][0]

        # 日付範囲
        date_range = pd.read_sql_query(
            "SELECT MIN(race_date) as min_date, MAX(race_date) as max_date FROM races",
            self.conn
        )

        return {
            'total_races': total_races,
            'races_with_results': races_with_results,
            'min_date': date_range['min_date'][0],
            'max_date': date_range['max_date'][0]
        }

    def get_racer_count(self):
        """
        選手数を取得

        Returns:
            int: ユニークな選手数
        """
        if not self.conn:
            self.connect()

        racer_count = pd.read_sql_query(
            "SELECT COUNT(DISTINCT racer_number) as count FROM race_details",
            self.conn
        )['count'][0]

        return racer_count

    def get_venue_distribution(self):
        """
        競艇場ごとのレース数分布を取得

        Returns:
            DataFrame: 競艇場ごとのレース数
        """
        if not self.conn:
            self.connect()

        venue_dist = pd.read_sql_query(
            """
            SELECT venue_code, COUNT(*) as race_count
            FROM races
            GROUP BY venue_code
            ORDER BY venue_code
            """,
            self.conn
        )

        return venue_dist

    def get_sample_race(self):
        """
        サンプルレースデータを取得

        Returns:
            dict: サンプルレースの情報
        """
        if not self.conn:
            self.connect()

        # 結果がある最新のレース
        race = pd.read_sql_query(
            """
            SELECT *
            FROM races
            WHERE result_1st IS NOT NULL
            ORDER BY race_date DESC, race_number DESC
            LIMIT 1
            """,
            self.conn
        )

        if len(race) == 0:
            return None

        race_id = race['race_id'][0]

        # レース詳細（選手情報）
        race_details = pd.read_sql_query(
            f"""
            SELECT *
            FROM race_details
            WHERE race_id = {race_id}
            ORDER BY pit_number
            """,
            self.conn
        )

        return {
            'race_info': race.to_dict('records')[0],
            'race_details': race_details.to_dict('records')
        }

    def get_win_rate_stats(self):
        """
        勝率の統計を取得

        Returns:
            dict: 勝率の統計情報
        """
        if not self.conn:
            self.connect()

        win_rate_stats = pd.read_sql_query(
            """
            SELECT
                AVG(win_rate) as avg_win_rate,
                MIN(win_rate) as min_win_rate,
                MAX(win_rate) as max_win_rate,
                AVG(second_rate) as avg_second_rate,
                AVG(third_rate) as avg_third_rate
            FROM race_details
            WHERE win_rate > 0
            """,
            self.conn
        )

        return win_rate_stats.to_dict('records')[0]

    def generate_summary_report(self):
        """
        データサマリーレポートを生成

        Returns:
            str: レポート文字列
        """
        self.connect()

        report = []
        report.append("=" * 80)
        report.append("ボートレースデータ 探索レポート")
        report.append("=" * 80)

        # レース数
        race_count = self.get_race_count()
        report.append("\n【レース数】")
        report.append(f"  総レース数: {race_count['total_races']:,}")
        report.append(f"  結果あり: {race_count['races_with_results']:,}")
        report.append(f"  日付範囲: {race_count['min_date']} ～ {race_count['max_date']}")

        # 選手数
        racer_count = self.get_racer_count()
        report.append(f"\n【選手数】")
        report.append(f"  ユニーク選手数: {racer_count:,}")

        # 競艇場分布
        venue_dist = self.get_venue_distribution()
        report.append(f"\n【競艇場分布】（上位5場）")
        for idx, row in venue_dist.head(5).iterrows():
            report.append(f"  競艇場{row['venue_code']}: {row['race_count']:,}レース")

        # 勝率統計
        win_rate_stats = self.get_win_rate_stats()
        report.append(f"\n【勝率統計】")
        report.append(f"  平均勝率: {win_rate_stats['avg_win_rate']:.2f}%")
        report.append(f"  最小勝率: {win_rate_stats['min_win_rate']:.2f}%")
        report.append(f"  最大勝率: {win_rate_stats['max_win_rate']:.2f}%")
        report.append(f"  平均2連対率: {win_rate_stats['avg_second_rate']:.2f}%")
        report.append(f"  平均3連対率: {win_rate_stats['avg_third_rate']:.2f}%")

        # サンプルレース
        sample_race = self.get_sample_race()
        if sample_race:
            race_info = sample_race['race_info']
            report.append(f"\n【サンプルレース】")
            report.append(f"  日付: {race_info['race_date']}")
            report.append(f"  競艇場: {race_info['venue_code']}")
            report.append(f"  レース番号: {race_info['race_number']}R")
            report.append(f"  結果: {race_info['result_1st']}-{race_info['result_2nd']}-{race_info['result_3rd']}")
            report.append(f"  出走選手数: {len(sample_race['race_details'])}")

        report.append("\n" + "=" * 80)

        self.close()

        return "\n".join(report)


if __name__ == "__main__":
    # データ探索実行
    explorer = DataExplorer()
    print(explorer.generate_summary_report())
