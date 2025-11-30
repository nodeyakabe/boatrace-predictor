"""
走法embedding生成
Phase 3: 選手の走法をembeddingベクトルに変換
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
import json


class StyleEmbedding:
    """
    走法embeddingクラス

    選手の走法をベクトル表現に変換
    Stage2/Stage3モデルの入力特徴量として使用
    """

    EMBEDDING_DIM = 16  # embedding次元

    def __init__(self, model_dir: str = 'models'):
        self.model_dir = model_dir
        self.racer_styles = {}  # racer_number -> style_cluster
        self.style_embeddings = {}  # style_cluster -> embedding vector
        self._loaded = False

    def load(self, name: str = 'style_cluster') -> bool:
        """走法データを読み込み"""
        if self._loaded:
            return True

        # 選手×クラスタ対応表
        mapping_path = os.path.join(self.model_dir, 'racer_style_mapping.csv')
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')

        if os.path.exists(mapping_path):
            try:
                df = pd.read_csv(mapping_path)
                self.racer_styles = dict(zip(df['racer_number'].astype(str), df['style_cluster']))
                print(f"選手走法データ読み込み: {len(self.racer_styles)}人")
            except Exception as e:
                print(f"選手走法データ読み込みエラー: {e}")

        # クラスタ中心
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)

                centers = meta.get('cluster_centers', [])
                cluster_names = meta.get('cluster_names', {})

                for i, center in enumerate(centers):
                    # クラスタ中心を正規化してembeddingに
                    embedding = self._create_embedding(center, i, len(centers))
                    self.style_embeddings[i] = embedding

                print(f"走法embedding読み込み: {len(self.style_embeddings)}クラスタ")

            except Exception as e:
                print(f"メタ情報読み込みエラー: {e}")

        self._loaded = True
        return len(self.racer_styles) > 0

    def _create_embedding(self, center: List[float],
                           cluster_id: int,
                           n_clusters: int) -> np.ndarray:
        """
        クラスタ中心からembeddingを生成

        Args:
            center: クラスタ中心の特徴量
            cluster_id: クラスタID
            n_clusters: 総クラスタ数

        Returns:
            embedding ベクトル
        """
        embedding = np.zeros(self.EMBEDDING_DIM)

        if center:
            # 特徴量の重要部分をembeddingに
            center_arr = np.array(center)
            n_features = len(center_arr)

            # 特徴量を圧縮
            for i, val in enumerate(center_arr):
                embedding[i % self.EMBEDDING_DIM] += val / (n_features / self.EMBEDDING_DIM)

        # クラスタIDのone-hot要素を追加
        cluster_idx = min(cluster_id, self.EMBEDDING_DIM - 1)
        embedding[cluster_idx] += 1.0

        # 正規化
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def get_racer_embedding(self, racer_number: str) -> np.ndarray:
        """
        選手のembeddingを取得

        Args:
            racer_number: 選手番号

        Returns:
            embedding ベクトル（EMBEDDING_DIM次元）
        """
        if not self._loaded:
            self.load()

        racer_number = str(racer_number)

        if racer_number in self.racer_styles:
            cluster_id = self.racer_styles[racer_number]
            if cluster_id in self.style_embeddings:
                return self.style_embeddings[cluster_id]

        # 未知の選手はゼロベクトル
        return np.zeros(self.EMBEDDING_DIM)

    def get_racer_style_name(self, racer_number: str) -> str:
        """
        選手の走法名を取得
        """
        from src.style_cluster.style_clustering import StyleClusterer

        if not self._loaded:
            self.load()

        racer_number = str(racer_number)

        if racer_number in self.racer_styles:
            cluster_id = self.racer_styles[racer_number]
            return StyleClusterer.STYLE_NAMES.get(cluster_id, f'タイプ{cluster_id+1}')

        return '不明'

    def get_style_embedding(self, cluster_id: int) -> np.ndarray:
        """
        走法クラスタのembeddingを取得

        Args:
            cluster_id: クラスタID

        Returns:
            embedding ベクトル
        """
        if not self._loaded:
            self.load()

        if cluster_id in self.style_embeddings:
            return self.style_embeddings[cluster_id]

        return np.zeros(self.EMBEDDING_DIM)

    def add_embedding_features(self, df: pd.DataFrame,
                                racer_col: str = 'racer_number',
                                prefix: str = 'style_emb') -> pd.DataFrame:
        """
        DataFrameにembedding特徴量を追加

        Args:
            df: 入力DataFrame
            racer_col: 選手番号カラム名
            prefix: 特徴量のプレフィックス

        Returns:
            embedding特徴量が追加されたDataFrame
        """
        if not self._loaded:
            self.load()

        df = df.copy()

        # 各選手のembeddingを計算
        embeddings = []
        for racer in df[racer_col]:
            emb = self.get_racer_embedding(str(racer))
            embeddings.append(emb)

        embeddings = np.array(embeddings)

        # DataFrameに追加
        for i in range(self.EMBEDDING_DIM):
            df[f'{prefix}_{i}'] = embeddings[:, i]

        return df

    def calculate_style_compatibility(self, racer1: str, racer2: str) -> float:
        """
        2選手間の走法相性を計算

        Args:
            racer1: 選手1の番号
            racer2: 選手2の番号

        Returns:
            相性スコア（-1〜1、高いほど相性が良い/競合しにくい）
        """
        emb1 = self.get_racer_embedding(racer1)
        emb2 = self.get_racer_embedding(racer2)

        # コサイン類似度
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = np.dot(emb1, emb2) / (norm1 * norm2)

        # 類似度が高い = 同じ走法 = 競合しやすい = 相性が悪い
        # よって、相性 = 1 - 類似度
        compatibility = 1 - similarity

        return float(compatibility)


class StyleInteractionCalculator:
    """
    走法間の相互作用を計算するクラス

    1着艇と残り艇の走法相性を計算し、
    2着・3着予測の補助特徴量を生成
    """

    def __init__(self, style_embedding: StyleEmbedding = None, model_dir: str = 'models'):
        self.style_embedding = style_embedding or StyleEmbedding(model_dir)

    def calculate_race_interactions(self, race_features: pd.DataFrame,
                                      winner_idx: int) -> Dict[int, Dict[str, float]]:
        """
        レース内の走法相互作用を計算

        Args:
            race_features: 6艇分の特徴量
            winner_idx: 1着艇のインデックス

        Returns:
            各艇の相互作用特徴量
        """
        winner_racer = str(race_features.iloc[winner_idx].get('racer_number', ''))

        interactions = {}

        for i, row in race_features.iterrows():
            if i == winner_idx:
                continue

            racer = str(row.get('racer_number', ''))

            # 1着艇との相性
            compatibility = self.style_embedding.calculate_style_compatibility(
                racer, winner_racer
            )

            # 走法名
            style_name = self.style_embedding.get_racer_style_name(racer)

            interactions[i] = {
                'winner_compatibility': compatibility,
                'style_name': style_name,
            }

        return interactions

    def add_interaction_features(self, df: pd.DataFrame,
                                   winner_racer: str,
                                   racer_col: str = 'racer_number') -> pd.DataFrame:
        """
        DataFrameに相互作用特徴量を追加
        """
        df = df.copy()

        compatibilities = []
        for racer in df[racer_col]:
            compat = self.style_embedding.calculate_style_compatibility(
                str(racer), str(winner_racer)
            )
            compatibilities.append(compat)

        df['winner_style_compatibility'] = compatibilities

        return df
