"""
走法分類用特徴量生成
Phase 3: 選手の走法パターンを特徴量化
"""
import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta


class StyleFeatureGenerator:
    """
    走法分類用特徴量生成クラス

    走法クラス（8種類）:
    1. まくり特化（攻め手）
    2. まくり差し
    3. 差し屋
    4. 逃げ屋
    5. 外マイ型
    6. 2着拾い型
    7. スタート爆発型
    8. 調整型（気象依存）
    """

    STYLE_NAMES = {
        0: 'まくり特化',
        1: 'まくり差し',
        2: '差し屋',
        3: '逃げ屋',
        4: '外マイ型',
        5: '2着拾い型',
        6: 'ST爆発型',
        7: '調整型',
    }

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def calculate_racer_style_features(self, racer_number: str,
                                         target_date: str = None,
                                         n_races: int = 200) -> Dict[str, float]:
        """
        選手の走法特徴量を計算

        Args:
            racer_number: 選手番号
            target_date: 基準日（Noneの場合は全期間）
            n_races: 参照するレース数

        Returns:
            走法関連特徴量
        """
        query = """
            SELECT
                rd.actual_course,
                rd.st_time,
                res.rank,
                e.pit_number
            FROM results res
            JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
            JOIN races r ON res.race_id = r.id
            LEFT JOIN race_details rd ON res.race_id = rd.race_id AND res.pit_number = rd.pit_number
            WHERE e.racer_number = ?
        """

        params = [racer_number]
        if target_date:
            query += " AND r.race_date < ?"
            params.append(target_date)

        query += " ORDER BY r.race_date DESC LIMIT ?"
        params.append(n_races)

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()

        if len(results) < 20:
            return self._default_style_features()

        # 統計を計算
        stats = {
            'total': 0,
            'wins': 0,
            'seconds': 0,
            'thirds': 0,
            'inner_wins': 0,  # 1-2コースからの勝ち
            'center_wins': 0,  # 3-4コースからの勝ち
            'outer_wins': 0,  # 5-6コースからの勝ち
            'inner_races': 0,
            'center_races': 0,
            'outer_races': 0,
            'nige_wins': 0,  # 1コース1着（逃げ）
            'makuri_wins': 0,  # 外から1着
            'sashi_wins': 0,  # 内側からまくられても2-3着
            'fast_st_count': 0,  # ST 0.12以下
            'slow_st_count': 0,  # ST 0.18以上
            'st_sum': 0.0,
            'st_count': 0,
        }

        for row in results:
            course = row['actual_course'] or row['pit_number'] or 3
            st = row['st_time']

            try:
                rank = int(row['rank'])
            except (ValueError, TypeError):
                continue

            stats['total'] += 1

            # コース分類
            if course <= 2:
                stats['inner_races'] += 1
                if rank == 1:
                    stats['inner_wins'] += 1
                    if course == 1:
                        stats['nige_wins'] += 1
            elif course <= 4:
                stats['center_races'] += 1
                if rank == 1:
                    stats['center_wins'] += 1
                    stats['makuri_wins'] += 1
            else:
                stats['outer_races'] += 1
                if rank == 1:
                    stats['outer_wins'] += 1
                    stats['makuri_wins'] += 1

            # 着順
            if rank == 1:
                stats['wins'] += 1
            elif rank == 2:
                stats['seconds'] += 1
                # 外コースからの2着は差しの可能性
                if course >= 3:
                    stats['sashi_wins'] += 1
            elif rank == 3:
                stats['thirds'] += 1

            # ST
            if st:
                stats['st_sum'] += st
                stats['st_count'] += 1
                if st <= 0.12:
                    stats['fast_st_count'] += 1
                elif st >= 0.18:
                    stats['slow_st_count'] += 1

        n = stats['total']
        if n == 0:
            return self._default_style_features()

        # 特徴量を計算
        features = {
            # 勝率系
            'win_rate': stats['wins'] / n,
            'second_rate': stats['seconds'] / n,
            'third_rate': stats['thirds'] / n,
            'rentai_rate': (stats['wins'] + stats['seconds']) / n,
            'fukusho_rate': (stats['wins'] + stats['seconds'] + stats['thirds']) / n,

            # コース別勝率
            'inner_win_rate': stats['inner_wins'] / stats['inner_races'] if stats['inner_races'] > 0 else 0,
            'center_win_rate': stats['center_wins'] / stats['center_races'] if stats['center_races'] > 0 else 0,
            'outer_win_rate': stats['outer_wins'] / stats['outer_races'] if stats['outer_races'] > 0 else 0,

            # 走法指標
            'nige_rate': stats['nige_wins'] / stats['inner_races'] if stats['inner_races'] > 0 else 0,
            'makuri_rate': stats['makuri_wins'] / n,
            'sashi_rate': stats['sashi_wins'] / n,

            # ST系
            'avg_st': stats['st_sum'] / stats['st_count'] if stats['st_count'] > 0 else 0.15,
            'fast_st_rate': stats['fast_st_count'] / stats['st_count'] if stats['st_count'] > 0 else 0,
            'slow_st_rate': stats['slow_st_count'] / stats['st_count'] if stats['st_count'] > 0 else 0,

            # コース偏り
            'inner_ratio': stats['inner_races'] / n,
            'center_ratio': stats['center_races'] / n,
            'outer_ratio': stats['outer_races'] / n,

            # 特殊指標
            'aggression_score': (stats['makuri_wins'] + stats['center_wins']) / n,  # 攻め度
            'consistency_score': (stats['wins'] + stats['seconds'] + stats['thirds']) / n,  # 安定度
            'amari_score': stats['thirds'] / n if stats['wins'] < stats['thirds'] else 0,  # 余り目度
        }

        return features

    def _default_style_features(self) -> Dict[str, float]:
        """デフォルトの特徴量"""
        return {
            'win_rate': 0.15,
            'second_rate': 0.15,
            'third_rate': 0.15,
            'rentai_rate': 0.30,
            'fukusho_rate': 0.45,
            'inner_win_rate': 0.25,
            'center_win_rate': 0.12,
            'outer_win_rate': 0.05,
            'nige_rate': 0.50,
            'makuri_rate': 0.05,
            'sashi_rate': 0.10,
            'avg_st': 0.15,
            'fast_st_rate': 0.20,
            'slow_st_rate': 0.10,
            'inner_ratio': 0.30,
            'center_ratio': 0.40,
            'outer_ratio': 0.30,
            'aggression_score': 0.10,
            'consistency_score': 0.45,
            'amari_score': 0.10,
        }

    def calculate_weather_dependency(self, racer_number: str,
                                       target_date: str = None,
                                       n_races: int = 200) -> Dict[str, float]:
        """
        気象条件への依存度を計算

        風や波の影響を受けやすいかどうか

        Args:
            racer_number: 選手番号
            target_date: 基準日
            n_races: 参照するレース数

        Returns:
            気象依存特徴量
        """
        query = """
            SELECT
                res.rank,
                w.wind_speed,
                w.wave_height
            FROM results res
            JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
            JOIN races r ON res.race_id = r.id
            LEFT JOIN weather w ON r.venue_code = w.venue_code AND r.race_date = w.weather_date
            WHERE e.racer_number = ?
        """

        params = [racer_number]
        if target_date:
            query += " AND r.race_date < ?"
            params.append(target_date)

        query += " ORDER BY r.race_date DESC LIMIT ?"
        params.append(n_races)

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()

        if len(results) < 20:
            return {
                'wind_dependency': 0.5,
                'wave_dependency': 0.5,
                'calm_performance': 0.5,
                'rough_performance': 0.5,
            }

        calm_wins = 0
        calm_total = 0
        rough_wins = 0
        rough_total = 0

        for row in results:
            try:
                rank = int(row['rank'])
            except (ValueError, TypeError):
                continue

            wind = row['wind_speed'] or 0
            wave = row['wave_height'] or 0

            is_calm = wind < 3 and wave < 5
            is_rough = wind >= 5 or wave >= 10

            if is_calm:
                calm_total += 1
                if rank <= 2:
                    calm_wins += 1
            elif is_rough:
                rough_total += 1
                if rank <= 2:
                    rough_wins += 1

        calm_perf = calm_wins / calm_total if calm_total > 0 else 0.3
        rough_perf = rough_wins / rough_total if rough_total > 0 else 0.3

        # 依存度 = パフォーマンス差
        wind_dep = abs(calm_perf - rough_perf)

        return {
            'wind_dependency': wind_dep,
            'wave_dependency': wind_dep,
            'calm_performance': calm_perf,
            'rough_performance': rough_perf,
        }

    def get_all_racers_features(self, target_date: str = None,
                                 min_races: int = 50) -> pd.DataFrame:
        """
        全選手の走法特徴量を取得

        Args:
            target_date: 基準日
            min_races: 最低レース数

        Returns:
            選手ごとの特徴量DataFrame
        """
        # アクティブな選手を取得
        conn = self._get_connection()

        query = """
            SELECT DISTINCT e.racer_number
            FROM entries e
            JOIN races r ON e.race_id = r.id
        """
        if target_date:
            query += f" WHERE r.race_date < '{target_date}'"

        query += " GROUP BY e.racer_number HAVING COUNT(*) >= ?"

        cursor = conn.cursor()
        cursor.execute(query, (min_races,))
        racers = [row[0] for row in cursor.fetchall()]
        conn.close()

        print(f"対象選手数: {len(racers)}")

        # 各選手の特徴量を計算
        all_features = []
        for i, racer in enumerate(racers):
            style_features = self.calculate_racer_style_features(racer, target_date)
            weather_features = self.calculate_weather_dependency(racer, target_date)

            features = {'racer_number': racer}
            features.update(style_features)
            features.update(weather_features)
            all_features.append(features)

            if (i + 1) % 500 == 0:
                print(f"進捗: {i + 1}/{len(racers)}")

        return pd.DataFrame(all_features)


def create_style_training_dataset(db_path: str,
                                   target_date: str = None,
                                   min_races: int = 50) -> pd.DataFrame:
    """
    走法クラスタリング用のデータセットを作成

    Args:
        db_path: DBパス
        target_date: 基準日
        min_races: 最低レース数

    Returns:
        学習用DataFrame
    """
    generator = StyleFeatureGenerator(db_path)
    return generator.get_all_racers_features(target_date, min_races)
