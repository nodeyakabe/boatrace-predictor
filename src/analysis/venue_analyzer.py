"""
会場別データ解析モジュール

各競艇場の特性を分析し、予測精度向上に活用
"""

import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta


class VenueAnalyzer:
    """
    会場別のデータ分析クラス

    機能:
    - 会場別のコース勝率分析
    - 季節別パフォーマンス分析
    - 決まり手パターン分析
    - 枠番別有利不利分析
    """

    def __init__(self, db_path: str):
        """
        初期化

        Args:
            db_path: データベースファイルのパス
        """
        self.db_path = db_path

    def get_venue_course_stats(self, venue_code: str, days_back: int = 90) -> pd.DataFrame:
        """
        会場別のコース別統計を取得

        Args:
            venue_code: 会場コード（'01'〜'24'）
            days_back: 過去何日分のデータを使用するか

        Returns:
            DataFrame: コース別の統計情報
            columns: ['course', 'total_races', 'win_count', 'win_rate',
                     'place2_count', 'place2_rate', 'place3_count', 'place3_rate']
        """
        try:
            conn = sqlite3.connect(self.db_path)

            # 過去N日分のレース結果を取得
            start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

            query = """
                SELECT
                    rd.actual_course AS course,
                    COUNT(*) as total_races,
                    SUM(CASE WHEN r2.rank = '1' THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN r2.rank IN ('1', '2') THEN 1 ELSE 0 END) as place2_count,
                    SUM(CASE WHEN r2.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) as place3_count
                FROM races r
                JOIN race_details rd ON r.id = rd.race_id
                LEFT JOIN results r2 ON r.id = r2.race_id AND rd.pit_number = r2.pit_number
                WHERE r.venue_code = ?
                  AND r.race_date >= ?
                  AND rd.actual_course IS NOT NULL
                GROUP BY rd.actual_course
                ORDER BY rd.actual_course
            """

            df = pd.read_sql_query(query, conn, params=(venue_code, start_date))
            conn.close()

            if df.empty:
                return pd.DataFrame()

            # 勝率・連対率・3連対率を計算
            df['win_rate'] = (df['win_count'] / df['total_races'] * 100).round(2)
            df['place2_rate'] = (df['place2_count'] / df['total_races'] * 100).round(2)
            df['place3_rate'] = (df['place3_count'] / df['total_races'] * 100).round(2)

            return df

        except Exception as e:
            print(f"[ERROR] エラー: {e}")
            return pd.DataFrame()

    def get_venue_kimarite_pattern(self, venue_code: str, days_back: int = 90) -> Dict[str, Dict]:
        """
        会場別の決まり手パターンを分析

        Args:
            venue_code: 会場コード
            days_back: 過去何日分のデータを使用するか

        Returns:
            {
                '1': {'逃げ': 120, '差し': 5, '捲り': 3, '捲り差し': 2, '抜き': 1},
                '2': {'差し': 50, '捲り': 40, '捲り差し': 10, ...},
                ...
            }
        """
        try:
            conn = sqlite3.connect(self.db_path)
            start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

            query = """
                SELECT
                    rd.actual_course as waku,
                    r2.kimarite,
                    COUNT(*) as count
                FROM races r
                JOIN race_details rd ON r.id = rd.race_id
                JOIN results r2 ON r.id = r2.race_id AND rd.pit_number = r2.pit_number
                WHERE r.venue_code = ?
                  AND r.race_date >= ?
                  AND r2.rank = '1'
                  AND r2.kimarite IS NOT NULL
                  AND r2.kimarite != ''
                  AND rd.actual_course IS NOT NULL
                GROUP BY rd.actual_course, r2.kimarite
                ORDER BY rd.actual_course, count DESC
            """

            df = pd.read_sql_query(query, conn, params=(venue_code, start_date))
            conn.close()

            if df.empty:
                return {}

            # 枠番ごとに決まり手を集計
            result = {}
            for waku in df['waku'].unique():
                waku_data = df[df['waku'] == waku]
                result[str(waku)] = dict(zip(waku_data['kimarite'], waku_data['count']))

            return result

        except Exception as e:
            print(f"[ERROR] エラー: {e}")
            return {}

    def get_seasonal_performance(self, venue_code: str) -> Dict[str, pd.DataFrame]:
        """
        季節別パフォーマンスを分析

        Args:
            venue_code: 会場コード

        Returns:
            {
                'spring': DataFrame (3-5月),
                'summer': DataFrame (6-8月),
                'autumn': DataFrame (9-11月),
                'winter': DataFrame (12-2月)
            }
        """
        seasons = {
            'spring': [3, 4, 5],
            'summer': [6, 7, 8],
            'autumn': [9, 10, 11],
            'winter': [12, 1, 2]
        }

        result = {}

        try:
            conn = sqlite3.connect(self.db_path)

            for season_name, months in seasons.items():
                # 月のリストをSQLのIN句用に変換
                months_str = ','.join(map(str, months))

                query = f"""
                    SELECT
                        rd.actual_course AS course,
                        COUNT(*) as total_races,
                        SUM(CASE WHEN r2.rank = '1' THEN 1 ELSE 0 END) as win_count,
                        CAST(SUM(CASE WHEN r2.rank = '1' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100 as win_rate
                    FROM races r
                    JOIN race_details rd ON r.id = rd.race_id
                    LEFT JOIN results r2 ON r.id = r2.race_id AND rd.pit_number = r2.pit_number
                    WHERE r.venue_code = ?
                      AND CAST(strftime('%m', r.race_date) AS INTEGER) IN ({months_str})
                      AND rd.actual_course IS NOT NULL
                    GROUP BY rd.actual_course
                    ORDER BY rd.actual_course
                """

                df = pd.read_sql_query(query, conn, params=(venue_code,))
                df['win_rate'] = df['win_rate'].round(2)
                result[season_name] = df

            conn.close()
            return result

        except Exception as e:
            print(f"[ERROR] エラー: {e}")
            return {}

    def calculate_course_advantage(self, venue_code: str, days_back: int = 90) -> Dict[int, float]:
        """
        コース別の有利不利指数を計算

        Args:
            venue_code: 会場コード
            days_back: 過去何日分のデータを使用するか

        Returns:
            {1: 1.25, 2: 0.95, 3: 0.88, 4: 0.76, 5: 0.65, 6: 0.51}
            （全会場平均を1.0とした場合の補正係数）
        """
        stats = self.get_venue_course_stats(venue_code, days_back)

        if stats.empty:
            # デフォルト値（全会場平均）
            return {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0}

        # 全会場平均（理論値）
        avg_win_rates = {
            1: 16.67,  # 1/6
            2: 16.67,
            3: 16.67,
            4: 16.67,
            5: 16.67,
            6: 16.67
        }

        advantage = {}
        for _, row in stats.iterrows():
            course = int(row['course'])
            venue_win_rate = row['win_rate']
            avg_rate = avg_win_rates.get(course, 16.67)

            # 補正係数 = 会場勝率 / 全会場平均
            if avg_rate > 0:
                advantage[course] = round(venue_win_rate / avg_rate, 2)
            else:
                advantage[course] = 1.0

        return advantage

    def get_venue_comparison(self, days_back: int = 90) -> pd.DataFrame:
        """
        全会場のコース別勝率を比較

        Args:
            days_back: 過去何日分のデータを使用するか

        Returns:
            DataFrame: 全会場のコース別勝率比較
            columns: ['venue_code', 'venue_name', 'course_1_rate', ..., 'course_6_rate']
        """
        try:
            from src.database.venue_data import VenueDataManager

            manager = VenueDataManager(self.db_path)
            all_venues = manager.get_all_venues()

            comparison_data = []

            for venue in all_venues:
                venue_code = venue['venue_code']
                venue_name = venue['venue_name']

                stats = self.get_venue_course_stats(venue_code, days_back)

                row_data = {
                    'venue_code': venue_code,
                    'venue_name': venue_name
                }

                # コース別勝率を追加
                for i in range(1, 7):
                    course_stat = stats[stats['course'] == i]
                    if not course_stat.empty:
                        row_data[f'course_{i}_rate'] = course_stat.iloc[0]['win_rate']
                    else:
                        row_data[f'course_{i}_rate'] = 0.0

                comparison_data.append(row_data)

            df = pd.DataFrame(comparison_data)
            return df

        except Exception as e:
            print(f"[ERROR] エラー: {e}")
            return pd.DataFrame()

    def analyze_venue_characteristics(self, venue_code: str) -> Dict:
        """
        会場の総合的な特性を分析

        Args:
            venue_code: 会場コード

        Returns:
            {
                'venue_code': '01',
                'venue_name': '桐生',
                'is_inner_advantage': True,  # インコース有利
                'course_1_dominance': 'high',  # 1コース支配度（high/medium/low）
                'kimarite_diversity': 0.65,  # 決まり手の多様性（0-1）
                'seasonal_variation': 'medium',  # 季節変動（high/medium/low）
                'characteristics_summary': '...'
            }
        """
        try:
            from src.database.venue_data import VenueDataManager

            manager = VenueDataManager(self.db_path)
            venue_info = manager.get_venue_data(venue_code)

            if not venue_info:
                return {}

            # 1. コース別勝率取得
            stats = self.get_venue_course_stats(venue_code, days_back=90)

            if stats.empty:
                course_1_rate = venue_info.get('course_1_win_rate', 0) or 0
            else:
                course_1_stat = stats[stats['course'] == 1]
                course_1_rate = course_1_stat.iloc[0]['win_rate'] if not course_1_stat.empty else 0

            # 2. インコース有利判定（1コース勝率が45%以上）
            is_inner_advantage = course_1_rate >= 45.0

            # 3. 1コース支配度
            if course_1_rate >= 50.0:
                course_1_dominance = 'high'
            elif course_1_rate >= 40.0:
                course_1_dominance = 'medium'
            else:
                course_1_dominance = 'low'

            # 4. 決まり手パターン
            kimarite = self.get_venue_kimarite_pattern(venue_code, days_back=90)

            # 決まり手の多様性（シャノンエントロピー風の計算）
            kimarite_diversity = 0.5  # デフォルト値
            if kimarite and '1' in kimarite:
                total = sum(kimarite['1'].values())
                if total > 0:
                    probs = [count/total for count in kimarite['1'].values()]
                    entropy = -sum(p * np.log2(p) if p > 0 else 0 for p in probs)
                    max_entropy = np.log2(len(kimarite['1']))
                    kimarite_diversity = round(entropy / max_entropy if max_entropy > 0 else 0.5, 2)

            # 5. 季節変動
            seasonal = self.get_seasonal_performance(venue_code)
            seasonal_variation = 'medium'  # 暫定値

            if seasonal:
                # 季節ごとの1コース勝率の標準偏差を計算
                rates = []
                for season_df in seasonal.values():
                    season_1 = season_df[season_df['course'] == 1]
                    if not season_1.empty:
                        rates.append(season_1.iloc[0]['win_rate'])

                if len(rates) >= 2:
                    std_dev = np.std(rates)
                    if std_dev >= 5.0:
                        seasonal_variation = 'high'
                    elif std_dev <= 2.0:
                        seasonal_variation = 'low'

            # 6. 特性サマリーの生成
            characteristics = []

            if is_inner_advantage:
                characteristics.append("インコース有利")
            else:
                characteristics.append("差し・捲りが有効")

            characteristics.append(f"1コース支配度: {course_1_dominance}")
            characteristics.append(f"水質: {venue_info.get('water_type', '不明')}")
            characteristics.append(f"干満差: {venue_info.get('tidal_range', '不明')}")

            summary = "、".join(characteristics)

            return {
                'venue_code': venue_code,
                'venue_name': venue_info.get('venue_name', '不明'),
                'is_inner_advantage': is_inner_advantage,
                'course_1_dominance': course_1_dominance,
                'kimarite_diversity': kimarite_diversity,
                'seasonal_variation': seasonal_variation,
                'characteristics_summary': summary,
                'course_1_win_rate': course_1_rate,
                'water_type': venue_info.get('water_type'),
                'tidal_range': venue_info.get('tidal_range')
            }

        except Exception as e:
            print(f"[ERROR] エラー: {e}")
            import traceback
            traceback.print_exc()
            return {}


if __name__ == "__main__":
    # テスト実行
    from config.settings import DATABASE_PATH

    print("="*80)
    print("会場別データ解析モジュール テスト")
    print("="*80)

    analyzer = VenueAnalyzer(DATABASE_PATH)

    # テスト1: 桐生（01）のコース別統計
    print("\n【テスト1: 桐生のコース別統計（過去90日）】")
    stats = analyzer.get_venue_course_stats('01', days_back=90)
    if not stats.empty:
        print(stats.to_string(index=False))
    else:
        print("  データなし（まだレース結果が登録されていない可能性）")

    # テスト2: 決まり手パターン
    print("\n【テスト2: 桐生の決まり手パターン】")
    kimarite = analyzer.get_venue_kimarite_pattern('01', days_back=90)
    if kimarite:
        for waku, patterns in kimarite.items():
            print(f"  {waku}コース: {patterns}")
    else:
        print("  データなし")

    # テスト3: 会場特性分析
    print("\n【テスト3: 桐生の会場特性分析】")
    characteristics = analyzer.analyze_venue_characteristics('01')
    if characteristics:
        for key, value in characteristics.items():
            print(f"  {key}: {value}")
    else:
        print("  データなし")

    print("\n" + "="*80)
    print("テスト完了")
    print("="*80)
