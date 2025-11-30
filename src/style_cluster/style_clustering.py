"""
走法クラスタリング
Phase 3: KMeans / HDBSCANによる選手の走法分類
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import joblib
import json


class StyleClusterer:
    """
    走法クラスタリングクラス

    8種類の走法に分類:
    0: まくり特化（攻め手）
    1: まくり差し
    2: 差し屋
    3: 逃げ屋
    4: 外マイ型
    5: 2着拾い型
    6: ST爆発型
    7: 調整型（気象依存）
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

    # クラスタリングに使用する特徴量
    FEATURE_COLS = [
        'win_rate', 'second_rate', 'third_rate',
        'inner_win_rate', 'center_win_rate', 'outer_win_rate',
        'nige_rate', 'makuri_rate', 'sashi_rate',
        'avg_st', 'fast_st_rate',
        'inner_ratio', 'outer_ratio',
        'aggression_score', 'consistency_score',
        'calm_performance', 'rough_performance',
    ]

    def __init__(self, model_dir: str = 'models', n_clusters: int = 8):
        self.model_dir = model_dir
        self.n_clusters = n_clusters
        self.kmeans = None
        self.scaler = None
        self.pca = None
        self.cluster_centers = None
        self.cluster_names = None
        self._loaded = False

    def fit(self, features_df: pd.DataFrame) -> Dict:
        """
        クラスタリングモデルを学習

        Args:
            features_df: 選手特徴量DataFrame

        Returns:
            学習結果のメトリクス
        """
        print(f"\n=== 走法クラスタリング学習 ===")
        print(f"選手数: {len(features_df):,}")

        # 特徴量を抽出
        feature_cols = [c for c in self.FEATURE_COLS if c in features_df.columns]
        X = features_df[feature_cols].fillna(0).values

        print(f"特徴量数: {len(feature_cols)}")

        # 標準化
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # PCAで次元削減（可視化・ノイズ除去用）
        self.pca = PCA(n_components=min(10, len(feature_cols)))
        X_pca = self.pca.fit_transform(X_scaled)

        explained_var = self.pca.explained_variance_ratio_.sum()
        print(f"PCA累積寄与率: {explained_var:.4f}")

        # KMeansクラスタリング
        self.kmeans = KMeans(
            n_clusters=self.n_clusters,
            random_state=42,
            n_init=20,
            max_iter=500,
        )
        labels = self.kmeans.fit_predict(X_pca)

        # クラスタ中心を元の特徴量空間に逆変換
        centers_pca = self.kmeans.cluster_centers_
        centers_scaled = self.pca.inverse_transform(centers_pca)
        self.cluster_centers = self.scaler.inverse_transform(centers_scaled)

        # クラスタの命名（特徴量から自動判定）
        self.cluster_names = self._assign_cluster_names(
            self.cluster_centers, feature_cols
        )

        # 結果を表示
        print("\nクラスタ分布:")
        for i in range(self.n_clusters):
            count = (labels == i).sum()
            print(f"  {i}: {self.cluster_names[i]} - {count}人 ({100*count/len(labels):.1f}%)")

        # メトリクス
        metrics = {
            'n_clusters': self.n_clusters,
            'n_samples': len(labels),
            'inertia': float(self.kmeans.inertia_),
            'explained_variance': float(explained_var),
            'cluster_sizes': {i: int((labels == i).sum()) for i in range(self.n_clusters)},
            'cluster_names': self.cluster_names,
        }

        # 結果をDataFrameに追加して返す
        features_df = features_df.copy()
        features_df['style_cluster'] = labels
        features_df['style_name'] = [self.cluster_names[l] for l in labels]

        self._loaded = True

        return metrics, features_df

    def _assign_cluster_names(self, centers: np.ndarray,
                               feature_cols: List[str]) -> Dict[int, str]:
        """
        クラスタ中心の特徴量からクラスタ名を自動判定
        """
        names = {}

        for i, center in enumerate(centers):
            features = dict(zip(feature_cols, center))

            # 特徴量から走法タイプを判定
            if features.get('nige_rate', 0) > 0.5 and features.get('inner_win_rate', 0) > 0.4:
                names[i] = '逃げ屋'
            elif features.get('makuri_rate', 0) > 0.15:
                if features.get('sashi_rate', 0) > 0.1:
                    names[i] = 'まくり差し'
                else:
                    names[i] = 'まくり特化'
            elif features.get('sashi_rate', 0) > 0.15:
                names[i] = '差し屋'
            elif features.get('outer_ratio', 0) > 0.4:
                names[i] = '外マイ型'
            elif features.get('fast_st_rate', 0) > 0.3:
                names[i] = 'ST爆発型'
            elif features.get('second_rate', 0) > features.get('win_rate', 0) * 1.5:
                names[i] = '2着拾い型'
            elif abs(features.get('calm_performance', 0.5) - features.get('rough_performance', 0.5)) > 0.15:
                names[i] = '調整型'
            else:
                names[i] = f'タイプ{i+1}'

        return names

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """
        選手の走法クラスタを予測

        Args:
            features: 選手特徴量DataFrame

        Returns:
            クラスタラベル
        """
        if not self._loaded:
            self.load()

        feature_cols = [c for c in self.FEATURE_COLS if c in features.columns]
        X = features[feature_cols].fillna(0).values

        X_scaled = self.scaler.transform(X)
        X_pca = self.pca.transform(X_scaled)

        return self.kmeans.predict(X_pca)

    def predict_single(self, style_features: Dict[str, float]) -> Tuple[int, str]:
        """
        単一選手の走法クラスタを予測

        Args:
            style_features: 走法特徴量辞書

        Returns:
            (クラスタID, クラスタ名)
        """
        df = pd.DataFrame([style_features])
        labels = self.predict(df)
        label = labels[0]
        return int(label), self.cluster_names.get(label, f'タイプ{label+1}')

    def get_style_embedding(self, cluster_id: int) -> np.ndarray:
        """
        クラスタIDからembeddingベクトルを取得

        Args:
            cluster_id: クラスタID

        Returns:
            embedding ベクトル
        """
        if self.cluster_centers is None:
            return np.zeros(len(self.FEATURE_COLS))

        return self.cluster_centers[cluster_id]

    def save(self, name: str = 'style_cluster') -> None:
        """モデルを保存"""
        os.makedirs(self.model_dir, exist_ok=True)

        model_data = {
            'kmeans': self.kmeans,
            'scaler': self.scaler,
            'pca': self.pca,
        }
        model_path = os.path.join(self.model_dir, f'{name}.joblib')
        joblib.dump(model_data, model_path)
        print(f"モデル保存: {model_path}")

        meta = {
            'n_clusters': self.n_clusters,
            'cluster_names': self.cluster_names,
            'cluster_centers': self.cluster_centers.tolist() if self.cluster_centers is not None else None,
            'feature_cols': self.FEATURE_COLS,
        }
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        print(f"メタ情報保存: {meta_path}")

    def load(self, name: str = 'style_cluster') -> bool:
        """モデルを読み込み"""
        model_path = os.path.join(self.model_dir, f'{name}.joblib')
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')

        if not os.path.exists(model_path):
            print(f"モデルが見つかりません: {model_path}")
            return False

        try:
            model_data = joblib.load(model_path)
            self.kmeans = model_data['kmeans']
            self.scaler = model_data['scaler']
            self.pca = model_data['pca']

            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                self.n_clusters = meta.get('n_clusters', 8)
                self.cluster_names = {int(k): v for k, v in meta.get('cluster_names', {}).items()}
                centers = meta.get('cluster_centers')
                self.cluster_centers = np.array(centers) if centers else None

            self._loaded = True
            print(f"モデル読み込み: {model_path}")
            return True

        except Exception as e:
            print(f"モデル読み込みエラー: {e}")
            return False


def train_style_clustering(db_path: str,
                           model_dir: str = 'models',
                           n_clusters: int = 8,
                           target_date: str = None) -> Tuple[StyleClusterer, pd.DataFrame]:
    """
    走法クラスタリングモデルを学習

    Args:
        db_path: DBパス
        model_dir: モデル保存先
        n_clusters: クラスタ数
        target_date: 基準日

    Returns:
        (学習済みクラスタラー, 選手×クラスタのDataFrame)
    """
    from src.style_cluster.style_features import create_style_training_dataset

    # データセット作成
    features_df = create_style_training_dataset(db_path, target_date)

    if len(features_df) < 100:
        print("データが不足しています")
        return None, None

    # クラスタリング
    clusterer = StyleClusterer(model_dir, n_clusters)
    metrics, result_df = clusterer.fit(features_df)

    # 保存
    clusterer.save()

    # 選手×クラスタ対応表を保存
    mapping_path = os.path.join(model_dir, 'racer_style_mapping.csv')
    result_df[['racer_number', 'style_cluster', 'style_name']].to_csv(
        mapping_path, index=False, encoding='utf-8-sig'
    )
    print(f"選手×クラスタ対応表保存: {mapping_path}")

    return clusterer, result_df
