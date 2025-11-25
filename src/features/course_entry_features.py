"""
進入コース予測のための特徴量生成
Phase 1.2: 枠番と実際のコース取りのズレを予測
"""
import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from collections import defaultdict


class CourseEntryFeatureGenerator:
    """進入コース予測用の特徴量を生成するクラス"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._cache = {}

    def get_racer_entry_tendency(self, racer_number: str, lookback_races: int = 50) -> Dict[str, float]:
        """選手の進入傾向を取得"""
        cache_key = f"tendency_{racer_number}_{lookback_races}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        with sqlite3.connect(self.db_path) as conn:
            query = """
                SELECT
                    e.pit_number,
                    rd.actual_course
                FROM entries e
                JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                JOIN races r ON e.race_id = r.id
                WHERE e.racer_number = ?
                    AND rd.actual_course IS NOT NULL
                ORDER BY r.race_date DESC, r.race_number DESC
                LIMIT ?
            """
            df = pd.read_sql_query(query, conn, params=(racer_number, lookback_races))

        if len(df) == 0:
            result = {
                'avg_course_change': 0.0,
                'inside_tendency': 0.0,  # イン取り傾向
                'outside_tendency': 0.0,  # アウト取り傾向
                'stable_course_rate': 1.0,  # 枠番通り率
                'aggressive_entry': 0.0,  # 積極的進入率
            }
        else:
            # コース変動の分析
            course_changes = (df['actual_course'] - df['pit_number']).values
            avg_change = np.mean(course_changes)

            # イン取り傾向 (枠より内側に入る)
            inside_tendency = np.mean(course_changes < 0)

            # アウト取り傾向 (枠より外側に出る)
            outside_tendency = np.mean(course_changes > 0)

            # 枠番通り率
            stable_rate = np.mean(course_changes == 0)

            # 積極的進入率 (2コース以上変動)
            aggressive = np.mean(np.abs(course_changes) >= 2)

            result = {
                'avg_course_change': float(avg_change),
                'inside_tendency': float(inside_tendency),
                'outside_tendency': float(outside_tendency),
                'stable_course_rate': float(stable_rate),
                'aggressive_entry': float(aggressive),
            }

        self._cache[cache_key] = result
        return result

    def get_pit_course_conversion_rate(self, pit_number: int, venue_code: str = None) -> Dict[int, float]:
        """枠番から各コースへの変換確率を取得"""
        with sqlite3.connect(self.db_path) as conn:
            if venue_code:
                query = """
                    SELECT rd.actual_course, COUNT(*) as cnt
                    FROM race_details rd
                    JOIN races r ON rd.race_id = r.id
                    WHERE rd.pit_number = ?
                        AND r.venue_code = ?
                        AND rd.actual_course IS NOT NULL
                    GROUP BY rd.actual_course
                """
                df = pd.read_sql_query(query, conn, params=(pit_number, venue_code))
            else:
                query = """
                    SELECT actual_course, COUNT(*) as cnt
                    FROM race_details
                    WHERE pit_number = ?
                        AND actual_course IS NOT NULL
                    GROUP BY actual_course
                """
                df = pd.read_sql_query(query, conn, params=(pit_number,))

        if len(df) == 0:
            # デフォルト: 枠番通り100%
            return {i: (1.0 if i == pit_number else 0.0) for i in range(1, 7)}

        total = df['cnt'].sum()
        conversion_rates = {i: 0.0 for i in range(1, 7)}

        for _, row in df.iterrows():
            course = int(row['actual_course'])
            conversion_rates[course] = row['cnt'] / total

        return conversion_rates

    def generate_entry_features(self, race_data: Dict) -> pd.DataFrame:
        """レースの全艇の進入特徴量を生成"""
        features_list = []

        for entry in race_data['entries']:
            racer_number = entry.get('racer_number', '')
            pit_number = entry['pit_number']
            venue_code = race_data.get('venue_code', '')

            # 選手の進入傾向
            tendency = self.get_racer_entry_tendency(racer_number)

            # 枠番からの変換確率
            conversion = self.get_pit_course_conversion_rate(pit_number, venue_code)

            features = {
                'pit_number': pit_number,
                'racer_number': racer_number,
                'avg_course_change': tendency['avg_course_change'],
                'inside_tendency': tendency['inside_tendency'],
                'outside_tendency': tendency['outside_tendency'],
                'stable_course_rate': tendency['stable_course_rate'],
                'aggressive_entry': tendency['aggressive_entry'],
            }

            # 各コースへの変換確率
            for course in range(1, 7):
                features[f'prob_to_course_{course}'] = conversion[course]

            # 予測されるコース（最大確率）
            predicted_course = max(conversion.items(), key=lambda x: x[1])[0]
            features['predicted_course'] = predicted_course

            # コース変更の可能性スコア
            features['course_change_likelihood'] = 1.0 - conversion[pit_number]

            features_list.append(features)

        return pd.DataFrame(features_list)

    def predict_course_distribution(self, race_data: Dict) -> np.ndarray:
        """
        レース全体の進入コース分布を予測

        Returns:
            6x6の確率行列 (pit_number x actual_course)
        """
        distribution = np.zeros((6, 6))

        for entry in race_data['entries']:
            pit_idx = entry['pit_number'] - 1
            racer_number = entry.get('racer_number', '')
            venue_code = race_data.get('venue_code', '')

            # 選手の傾向
            tendency = self.get_racer_entry_tendency(racer_number)

            # 基本変換確率
            conversion = self.get_pit_course_conversion_rate(entry['pit_number'], venue_code)

            for course in range(1, 7):
                distribution[pit_idx, course - 1] = conversion[course]

        # 正規化（各コースに1艇のみ入る制約を近似）
        # 簡易的に行と列の両方を正規化
        for _ in range(10):  # 反復正規化
            # 行正規化
            row_sums = distribution.sum(axis=1, keepdims=True)
            row_sums = np.where(row_sums > 0, row_sums, 1)
            distribution = distribution / row_sums

            # 列正規化
            col_sums = distribution.sum(axis=0, keepdims=True)
            col_sums = np.where(col_sums > 0, col_sums, 1)
            distribution = distribution / col_sums

        return distribution

    def get_entry_conflict_score(self, race_data: Dict) -> float:
        """進入競合スコアを計算（高いほど混乱が起きやすい）"""
        features_df = self.generate_entry_features(race_data)

        # 各艇のイン取り傾向の合計（高いほど競合）
        inside_conflict = features_df['inside_tendency'].sum()

        # 積極的進入者数
        aggressive_count = (features_df['aggressive_entry'] > 0.3).sum()

        # コース変更可能性の平均
        change_likelihood = features_df['course_change_likelihood'].mean()

        conflict_score = (
            inside_conflict * 0.4 +
            aggressive_count * 0.1 +
            change_likelihood * 0.5
        )

        return min(1.0, conflict_score)


class CourseEntryDatasetBuilder:
    """進入コース予測用のデータセットを構築"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def build_training_dataset(self, start_date: str, end_date: str) -> pd.DataFrame:
        """学習用データセットを構築"""
        with sqlite3.connect(self.db_path) as conn:
            query = """
                SELECT
                    r.id as race_id,
                    r.venue_code,
                    r.race_date,
                    e.pit_number,
                    e.racer_number,
                    e.racer_rank,
                    e.win_rate,
                    rd.actual_course,
                    rd.st_time
                FROM races r
                JOIN entries e ON r.id = e.race_id
                JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
                WHERE r.race_date BETWEEN ? AND ?
                    AND rd.actual_course IS NOT NULL
                ORDER BY r.race_date, r.id, e.pit_number
            """
            df = pd.read_sql_query(query, conn, params=(start_date, end_date))

        if len(df) == 0:
            return df

        # 特徴量追加
        feature_gen = CourseEntryFeatureGenerator(self.db_path)

        # コース変更フラグ（ターゲット変数）
        df['course_changed'] = (df['pit_number'] != df['actual_course']).astype(int)

        # コース変更量
        df['course_change_amount'] = df['actual_course'] - df['pit_number']

        # 選手級別のエンコーディング
        rank_map = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
        df['racer_rank_score'] = df['racer_rank'].map(rank_map).fillna(2)

        print(f"データセット構築完了: {len(df)}件")
        print(f"コース変更率: {df['course_changed'].mean() * 100:.2f}%")

        return df

    def get_statistics(self) -> Dict:
        """進入コースの統計情報を取得"""
        with sqlite3.connect(self.db_path) as conn:
            # 枠番→実コースの変換統計
            query = """
                SELECT
                    pit_number,
                    actual_course,
                    COUNT(*) as cnt
                FROM race_details
                WHERE actual_course IS NOT NULL
                GROUP BY pit_number, actual_course
            """
            df = pd.read_sql_query(query, conn)

        stats = {}

        # 枠番通り率
        for pit in range(1, 7):
            pit_data = df[df['pit_number'] == pit]
            total = pit_data['cnt'].sum()
            same_course = pit_data[pit_data['actual_course'] == pit]['cnt'].sum()
            stats[f'pit_{pit}_same_course_rate'] = same_course / total if total > 0 else 0

        # 全体のコース変更率
        total_entries = df['cnt'].sum()
        same_course_total = df[df['pit_number'] == df['actual_course']]['cnt'].sum()
        stats['overall_same_course_rate'] = same_course_total / total_entries if total_entries > 0 else 0

        return stats
