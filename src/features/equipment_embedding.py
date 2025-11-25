"""
モーター/ボートEmbeddingモジュール
Phase 3.1: 機材固有の特性を学習
"""
import numpy as np
import pandas as pd
import sqlite3
from typing import Dict, List, Optional
from collections import defaultdict
import json
import os


class EquipmentEmbedding:
    """モーター/ボートの埋め込み表現を生成"""

    def __init__(self, db_path: str, embedding_dim: int = 8):
        self.db_path = db_path
        self.embedding_dim = embedding_dim
        self.motor_embeddings = {}
        self.boat_embeddings = {}
        self.motor_stats = {}
        self.boat_stats = {}

    def build_embeddings(self, lookback_days: int = 180):
        """埋め込みを構築"""
        print("=== モーター/ボートEmbedding構築 ===")

        with sqlite3.connect(self.db_path) as conn:
            # モーター統計
            query = """
                SELECT
                    e.motor_number,
                    r.venue_code,
                    COUNT(*) as race_count,
                    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN res.rank IN ('1', '2') THEN 1 ELSE 0 END) as place_2_count,
                    SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) as place_3_count,
                    AVG(CAST(res.rank AS FLOAT)) as avg_rank
                FROM entries e
                JOIN races r ON e.race_id = r.id
                JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
                WHERE r.race_date >= date('now', '-{} days')
                    AND res.rank IN ('1', '2', '3', '4', '5', '6')
                    AND e.motor_number IS NOT NULL
                GROUP BY e.motor_number, r.venue_code
            """.format(lookback_days)

            motor_df = pd.read_sql_query(query, conn)

            # ボート統計
            query = """
                SELECT
                    e.boat_number,
                    r.venue_code,
                    COUNT(*) as race_count,
                    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN res.rank IN ('1', '2') THEN 1 ELSE 0 END) as place_2_count,
                    SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) as place_3_count,
                    AVG(CAST(res.rank AS FLOAT)) as avg_rank
                FROM entries e
                JOIN races r ON e.race_id = r.id
                JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
                WHERE r.race_date >= date('now', '-{} days')
                    AND res.rank IN ('1', '2', '3', '4', '5', '6')
                    AND e.boat_number IS NOT NULL
                GROUP BY e.boat_number, r.venue_code
            """.format(lookback_days)

            boat_df = pd.read_sql_query(query, conn)

        # モーターEmbedding生成
        self._generate_motor_embeddings(motor_df)

        # ボートEmbedding生成
        self._generate_boat_embeddings(boat_df)

        print(f"モーターEmbedding: {len(self.motor_embeddings)}件")
        print(f"ボートEmbedding: {len(self.boat_embeddings)}件")

    def _generate_motor_embeddings(self, df: pd.DataFrame):
        """モーターの埋め込みを生成"""
        if len(df) == 0:
            return

        # 会場ごとにグループ化
        for venue_code in df['venue_code'].unique():
            venue_df = df[df['venue_code'] == venue_code]

            for _, row in venue_df.iterrows():
                motor_id = f"{venue_code}_{row['motor_number']}"

                # 統計情報を保存
                self.motor_stats[motor_id] = {
                    'venue_code': venue_code,
                    'motor_number': int(row['motor_number']),
                    'race_count': int(row['race_count']),
                    'win_rate': row['win_count'] / row['race_count'] if row['race_count'] > 0 else 0,
                    'place_2_rate': row['place_2_count'] / row['race_count'] if row['race_count'] > 0 else 0,
                    'place_3_rate': row['place_3_count'] / row['race_count'] if row['race_count'] > 0 else 0,
                    'avg_rank': row['avg_rank'] if pd.notna(row['avg_rank']) else 3.5,
                }

                # 埋め込みベクトルを生成
                # 統計情報を基に特徴ベクトルを作成
                embedding = self._stats_to_embedding(self.motor_stats[motor_id])
                self.motor_embeddings[motor_id] = embedding

    def _generate_boat_embeddings(self, df: pd.DataFrame):
        """ボートの埋め込みを生成"""
        if len(df) == 0:
            return

        for venue_code in df['venue_code'].unique():
            venue_df = df[df['venue_code'] == venue_code]

            for _, row in venue_df.iterrows():
                boat_id = f"{venue_code}_{row['boat_number']}"

                self.boat_stats[boat_id] = {
                    'venue_code': venue_code,
                    'boat_number': int(row['boat_number']),
                    'race_count': int(row['race_count']),
                    'win_rate': row['win_count'] / row['race_count'] if row['race_count'] > 0 else 0,
                    'place_2_rate': row['place_2_count'] / row['race_count'] if row['race_count'] > 0 else 0,
                    'place_3_rate': row['place_3_count'] / row['race_count'] if row['race_count'] > 0 else 0,
                    'avg_rank': row['avg_rank'] if pd.notna(row['avg_rank']) else 3.5,
                }

                embedding = self._stats_to_embedding(self.boat_stats[boat_id])
                self.boat_embeddings[boat_id] = embedding

    def _stats_to_embedding(self, stats: Dict) -> np.ndarray:
        """統計情報を埋め込みベクトルに変換"""
        # 基本特徴量
        base_features = [
            stats['win_rate'],
            stats['place_2_rate'],
            stats['place_3_rate'],
            (7 - stats['avg_rank']) / 6,  # 正規化（高いほど良い）
            min(stats['race_count'] / 100, 1.0),  # 経験値（最大100レース）
        ]

        # 派生特徴量
        derived_features = [
            stats['place_2_rate'] - stats['win_rate'],  # 2着になりやすさ
            stats['place_3_rate'] - stats['place_2_rate'],  # 3着になりやすさ
            stats['win_rate'] * min(stats['race_count'] / 50, 1.0),  # 信頼度加重勝率
        ]

        embedding = np.array(base_features + derived_features)

        # 次元調整（埋め込み次元に合わせる）
        if len(embedding) < self.embedding_dim:
            # ゼロパディング
            padding = np.zeros(self.embedding_dim - len(embedding))
            embedding = np.concatenate([embedding, padding])
        elif len(embedding) > self.embedding_dim:
            embedding = embedding[:self.embedding_dim]

        return embedding

    def get_motor_embedding(self, venue_code: str, motor_number: int) -> np.ndarray:
        """モーターの埋め込みを取得"""
        motor_id = f"{venue_code}_{motor_number}"
        if motor_id in self.motor_embeddings:
            return self.motor_embeddings[motor_id]
        else:
            # デフォルト埋め込み（平均的な性能）
            return np.array([0.167, 0.333, 0.5, 0.5, 0.5, 0.167, 0.167, 0.083])

    def get_boat_embedding(self, venue_code: str, boat_number: int) -> np.ndarray:
        """ボートの埋め込みを取得"""
        boat_id = f"{venue_code}_{boat_number}"
        if boat_id in self.boat_embeddings:
            return self.boat_embeddings[boat_id]
        else:
            return np.array([0.167, 0.333, 0.5, 0.5, 0.5, 0.167, 0.167, 0.083])

    def add_embedding_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """データフレームにEmbedding特徴量を追加"""
        result_df = df.copy()

        motor_embeds = []
        boat_embeds = []

        for _, row in df.iterrows():
            venue_code = row.get('venue_code', '01')
            motor_number = row.get('motor_number', 1)
            boat_number = row.get('boat_number', 1)

            # モーターEmbedding
            motor_emb = self.get_motor_embedding(venue_code, motor_number)
            motor_embeds.append(motor_emb)

            # ボートEmbedding
            boat_emb = self.get_boat_embedding(venue_code, boat_number)
            boat_embeds.append(boat_emb)

        # 特徴量として追加
        motor_embeds = np.array(motor_embeds)
        boat_embeds = np.array(boat_embeds)

        for i in range(self.embedding_dim):
            result_df[f'motor_emb_{i}'] = motor_embeds[:, i]
            result_df[f'boat_emb_{i}'] = boat_embeds[:, i]

        return result_df

    def get_equipment_score(self, venue_code: str, motor_number: int, boat_number: int) -> float:
        """機材の総合スコアを取得（0-1）"""
        motor_emb = self.get_motor_embedding(venue_code, motor_number)
        boat_emb = self.get_boat_embedding(venue_code, boat_number)

        # 勝率と2連率の加重平均
        motor_score = motor_emb[0] * 0.5 + motor_emb[1] * 0.3 + motor_emb[2] * 0.2
        boat_score = boat_emb[0] * 0.5 + boat_emb[1] * 0.3 + boat_emb[2] * 0.2

        combined_score = motor_score * 0.7 + boat_score * 0.3  # モーター重視

        return float(combined_score)

    def save(self, path: str = 'models/equipment_embeddings.json'):
        """埋め込みを保存"""
        os.makedirs(os.path.dirname(path), exist_ok=True)

        data = {
            'embedding_dim': self.embedding_dim,
            'motor_embeddings': {k: v.tolist() for k, v in self.motor_embeddings.items()},
            'boat_embeddings': {k: v.tolist() for k, v in self.boat_embeddings.items()},
            'motor_stats': self.motor_stats,
            'boat_stats': self.boat_stats,
        }

        with open(path, 'w') as f:
            json.dump(data, f)

        print(f"Embeddingを {path} に保存しました")

    def load(self, path: str = 'models/equipment_embeddings.json'):
        """埋め込みを読み込み"""
        with open(path, 'r') as f:
            data = json.load(f)

        self.embedding_dim = data['embedding_dim']
        self.motor_embeddings = {k: np.array(v) for k, v in data['motor_embeddings'].items()}
        self.boat_embeddings = {k: np.array(v) for k, v in data['boat_embeddings'].items()}
        self.motor_stats = data['motor_stats']
        self.boat_stats = data['boat_stats']

        print(f"Embeddingを {path} から読み込みました")
