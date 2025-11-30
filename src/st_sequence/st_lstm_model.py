"""
ST時系列モデル（LSTM/GRU）
Phase 4: STパターンからembeddingを生成

注意: PyTorchがインストールされていない場合は、
NumPyベースの簡易実装にフォールバックします
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
import json
import joblib

# PyTorchの有無をチェック
try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("PyTorchが利用できません。NumPyベースの簡易モデルを使用します。")


class STSequenceModel:
    """
    ST時系列モデルクラス

    直近30走のSTシーケンスから128次元のembeddingを生成
    """

    EMBEDDING_DIM = 128
    SEQUENCE_LENGTH = 30

    def __init__(self, model_dir: str = 'models'):
        self.model_dir = model_dir
        self.model = None
        self._loaded = False
        self._use_pytorch = TORCH_AVAILABLE

    def load(self, name: str = 'st_sequence') -> bool:
        """モデルを読み込み"""
        if self._loaded:
            return True

        if self._use_pytorch:
            return self._load_pytorch_model(name)
        else:
            return self._load_numpy_model(name)

    def _load_pytorch_model(self, name: str) -> bool:
        """PyTorchモデルを読み込み"""
        model_path = os.path.join(self.model_dir, f'{name}_lstm.pt')

        if os.path.exists(model_path):
            try:
                self.model = torch.load(model_path, map_location='cpu')
                self.model.eval()
                self._loaded = True
                print(f"ST LSTMモデル読み込み: {model_path}")
                return True
            except Exception as e:
                print(f"モデル読み込みエラー: {e}")

        # モデルがない場合は簡易実装を使用
        self._use_pytorch = False
        return self._load_numpy_model(name)

    def _load_numpy_model(self, name: str) -> bool:
        """NumPyベースの簡易モデルを読み込み"""
        # 事前学習済みの重みがあれば読み込み
        weights_path = os.path.join(self.model_dir, f'{name}_weights.joblib')

        if os.path.exists(weights_path):
            try:
                self.model = joblib.load(weights_path)
                self._loaded = True
                print(f"ST簡易モデル読み込み: {weights_path}")
                return True
            except Exception as e:
                print(f"モデル読み込みエラー: {e}")

        # デフォルトの重みを使用
        self.model = self._create_default_weights()
        self._loaded = True
        return True

    def _create_default_weights(self) -> Dict:
        """デフォルトの重みを作成"""
        return {
            'projection': np.random.randn(self.SEQUENCE_LENGTH, self.EMBEDDING_DIM) * 0.1,
            'mean_weight': 0.3,
            'std_weight': 0.2,
            'trend_weight': 0.2,
            'recent_weight': 0.3,
        }

    def get_embedding(self, st_sequence: np.ndarray) -> np.ndarray:
        """
        STシーケンスからembeddingを生成

        Args:
            st_sequence: STシーケンス（SEQUENCE_LENGTH次元）

        Returns:
            embedding ベクトル（EMBEDDING_DIM次元）
        """
        if not self._loaded:
            self.load()

        # シーケンス長を調整
        if len(st_sequence) < self.SEQUENCE_LENGTH:
            # パディング
            padding = np.full(self.SEQUENCE_LENGTH - len(st_sequence), np.mean(st_sequence))
            st_sequence = np.concatenate([padding, st_sequence])
        elif len(st_sequence) > self.SEQUENCE_LENGTH:
            st_sequence = st_sequence[-self.SEQUENCE_LENGTH:]

        if self._use_pytorch and isinstance(self.model, nn.Module):
            return self._get_embedding_pytorch(st_sequence)
        else:
            return self._get_embedding_numpy(st_sequence)

    def _get_embedding_pytorch(self, st_sequence: np.ndarray) -> np.ndarray:
        """PyTorchモデルでembeddingを計算"""
        with torch.no_grad():
            x = torch.FloatTensor(st_sequence).unsqueeze(0).unsqueeze(-1)
            embedding = self.model(x).squeeze(0).numpy()
        return embedding

    def _get_embedding_numpy(self, st_sequence: np.ndarray) -> np.ndarray:
        """NumPyベースでembeddingを計算"""
        weights = self.model

        # 正規化
        mean = np.mean(st_sequence)
        std = np.std(st_sequence) + 1e-10
        normalized = (st_sequence - mean) / std

        # 基本embedding（線形射影）
        embedding = np.dot(normalized, weights['projection'])

        # 統計特徴量を追加
        # 平均ST
        embedding[:16] += (mean - 0.15) * weights['mean_weight'] * 10

        # 標準偏差
        embedding[16:32] += std * weights['std_weight'] * 10

        # トレンド
        x = np.arange(len(st_sequence))
        trend = np.polyfit(x, st_sequence, 1)[0]
        embedding[32:48] += trend * weights['trend_weight'] * 100

        # 直近パターン
        recent = st_sequence[-5:]
        for i, st in enumerate(recent):
            embedding[48 + i*16:64 + i*16] += (st - mean) * weights['recent_weight']

        # 正規化
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def get_embedding_features(self, st_sequence: np.ndarray,
                                prefix: str = 'st_emb') -> Dict[str, float]:
        """
        embeddingを辞書形式で取得

        Args:
            st_sequence: STシーケンス
            prefix: 特徴量のプレフィックス

        Returns:
            embedding特徴量辞書
        """
        embedding = self.get_embedding(st_sequence)

        return {f'{prefix}_{i}': float(embedding[i]) for i in range(len(embedding))}

    def add_embedding_features(self, df: pd.DataFrame,
                                st_sequence_col: str = 'st_sequence',
                                prefix: str = 'st_emb') -> pd.DataFrame:
        """
        DataFrameにembedding特徴量を追加

        Args:
            df: 入力DataFrame
            st_sequence_col: STシーケンスのカラム名
            prefix: 特徴量のプレフィックス

        Returns:
            embedding特徴量が追加されたDataFrame
        """
        df = df.copy()

        embeddings = []
        for seq in df[st_sequence_col]:
            emb = self.get_embedding(np.array(seq))
            embeddings.append(emb)

        embeddings = np.array(embeddings)

        for i in range(self.EMBEDDING_DIM):
            df[f'{prefix}_{i}'] = embeddings[:, i]

        return df


if TORCH_AVAILABLE:
    class LSTMEncoder(nn.Module):
        """LSTM Encoder for ST sequence"""

        def __init__(self, input_dim: int = 1,
                     hidden_dim: int = 64,
                     num_layers: int = 2,
                     output_dim: int = 128):
            super().__init__()

            self.lstm = nn.LSTM(
                input_size=input_dim,
                hidden_size=hidden_dim,
                num_layers=num_layers,
                batch_first=True,
                bidirectional=True,
                dropout=0.2,
            )

            self.fc = nn.Sequential(
                nn.Linear(hidden_dim * 2, output_dim),
                nn.ReLU(),
                nn.LayerNorm(output_dim),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """
            Args:
                x: (batch, seq_len, 1)

            Returns:
                (batch, output_dim)
            """
            lstm_out, (h_n, _) = self.lstm(x)

            # 最後の隠れ状態を結合
            h_forward = h_n[-2]
            h_backward = h_n[-1]
            h_combined = torch.cat([h_forward, h_backward], dim=1)

            embedding = self.fc(h_combined)

            return embedding


    class GRUEncoder(nn.Module):
        """GRU Encoder for ST sequence"""

        def __init__(self, input_dim: int = 1,
                     hidden_dim: int = 64,
                     num_layers: int = 2,
                     output_dim: int = 128):
            super().__init__()

            self.gru = nn.GRU(
                input_size=input_dim,
                hidden_size=hidden_dim,
                num_layers=num_layers,
                batch_first=True,
                bidirectional=True,
                dropout=0.2,
            )

            self.fc = nn.Sequential(
                nn.Linear(hidden_dim * 2, output_dim),
                nn.ReLU(),
                nn.LayerNorm(output_dim),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """
            Args:
                x: (batch, seq_len, 1)

            Returns:
                (batch, output_dim)
            """
            _, h_n = self.gru(x)

            h_forward = h_n[-2]
            h_backward = h_n[-1]
            h_combined = torch.cat([h_forward, h_backward], dim=1)

            embedding = self.fc(h_combined)

            return embedding
