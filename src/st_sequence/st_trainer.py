"""
ST時系列モデルのトレーナー
Phase 4: LSTM/GRUモデルの学習
"""
import os
import sys
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
import json
import joblib
from datetime import datetime

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.st_sequence.st_sequence_features import create_st_training_dataset

# PyTorchの有無をチェック
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class STModelTrainer:
    """
    ST時系列モデルのトレーナー

    PyTorchが利用可能な場合はLSTM/GRUを学習
    そうでない場合はNumPyベースの簡易モデルを学習
    """

    def __init__(self, db_path: str, model_dir: str = 'models'):
        self.db_path = db_path
        self.model_dir = model_dir
        self.model = None
        self.metrics = {}
        self._use_pytorch = TORCH_AVAILABLE

    def load_training_data(self, start_date: str = None,
                           end_date: str = None,
                           sequence_length: int = 30) -> Tuple[np.ndarray, np.ndarray]:
        """学習データを読み込み"""
        print("=== ST時系列学習データ読み込み ===")
        X, y = create_st_training_dataset(
            self.db_path, start_date, end_date, sequence_length
        )
        return X, y

    def train(self, X: np.ndarray, y: np.ndarray,
              epochs: int = 50,
              batch_size: int = 256,
              learning_rate: float = 0.001) -> Dict:
        """
        モデルを学習

        Args:
            X: 入力シーケンス (n_samples, sequence_length)
            y: ターゲット（次のST）
            epochs: エポック数
            batch_size: バッチサイズ
            learning_rate: 学習率

        Returns:
            学習メトリクス
        """
        if len(X) == 0:
            print("学習データがありません")
            return {}

        if self._use_pytorch:
            return self._train_pytorch(X, y, epochs, batch_size, learning_rate)
        else:
            return self._train_numpy(X, y)

    def _train_pytorch(self, X: np.ndarray, y: np.ndarray,
                       epochs: int, batch_size: int,
                       learning_rate: float) -> Dict:
        """PyTorchモデルを学習"""
        from src.st_sequence.st_lstm_model import LSTMEncoder

        print(f"\n=== ST LSTMモデル学習 (PyTorch) ===")
        print(f"データサイズ: {len(X):,}")
        print(f"シーケンス長: {X.shape[1]}")

        # データ準備
        X_tensor = torch.FloatTensor(X).unsqueeze(-1)  # (N, seq, 1)
        y_tensor = torch.FloatTensor(y)

        # Train/Val split
        n_train = int(len(X) * 0.8)
        train_dataset = TensorDataset(X_tensor[:n_train], y_tensor[:n_train])
        val_dataset = TensorDataset(X_tensor[n_train:], y_tensor[n_train:])

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size)

        # モデル初期化
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = LSTMEncoder(output_dim=128).to(device)

        # Autoencoder形式で学習（embedding → 次のST予測）
        decoder = nn.Linear(128, 1).to(device)
        optimizer = optim.Adam(
            list(self.model.parameters()) + list(decoder.parameters()),
            lr=learning_rate
        )
        criterion = nn.MSELoss()

        train_losses = []
        val_losses = []

        for epoch in range(epochs):
            # Training
            self.model.train()
            decoder.train()
            train_loss = 0

            for batch_x, batch_y in train_loader:
                batch_x = batch_x.to(device)
                batch_y = batch_y.to(device)

                optimizer.zero_grad()
                embedding = self.model(batch_x)
                pred = decoder(embedding).squeeze()
                loss = criterion(pred, batch_y)
                loss.backward()
                optimizer.step()

                train_loss += loss.item()

            train_loss /= len(train_loader)
            train_losses.append(train_loss)

            # Validation
            self.model.eval()
            decoder.eval()
            val_loss = 0

            with torch.no_grad():
                for batch_x, batch_y in val_loader:
                    batch_x = batch_x.to(device)
                    batch_y = batch_y.to(device)
                    embedding = self.model(batch_x)
                    pred = decoder(embedding).squeeze()
                    loss = criterion(pred, batch_y)
                    val_loss += loss.item()

            val_loss /= len(val_loader)
            val_losses.append(val_loss)

            if (epoch + 1) % 10 == 0:
                print(f"Epoch {epoch+1}/{epochs}: Train Loss = {train_loss:.6f}, Val Loss = {val_loss:.6f}")

        self.metrics = {
            'final_train_loss': train_losses[-1],
            'final_val_loss': val_losses[-1],
            'best_val_loss': min(val_losses),
            'n_samples': len(X),
            'epochs': epochs,
        }

        return self.metrics

    def _train_numpy(self, X: np.ndarray, y: np.ndarray) -> Dict:
        """NumPyベースの簡易モデルを学習"""
        print(f"\n=== ST簡易モデル学習 (NumPy) ===")
        print(f"データサイズ: {len(X):,}")

        sequence_length = X.shape[1]
        embedding_dim = 128

        # 正規化パラメータを計算
        X_mean = X.mean()
        X_std = X.std()

        X_normalized = (X - X_mean) / (X_std + 1e-10)

        # ランダム射影行列を作成（学習可能な重みの代わり）
        np.random.seed(42)
        projection = np.random.randn(sequence_length, embedding_dim) * 0.1

        # 射影の最適化（線形回帰で近似）
        # X @ projection を使って y を予測
        embeddings = X_normalized @ projection
        decoder = np.linalg.lstsq(embeddings, y, rcond=None)[0]

        # 予測誤差
        y_pred = embeddings @ decoder
        mse = np.mean((y - y_pred) ** 2)

        self.model = {
            'projection': projection,
            'decoder': decoder,
            'mean': float(X_mean),
            'std': float(X_std),
            'mean_weight': 0.3,
            'std_weight': 0.2,
            'trend_weight': 0.2,
            'recent_weight': 0.3,
        }

        self.metrics = {
            'mse': float(mse),
            'rmse': float(np.sqrt(mse)),
            'n_samples': len(X),
        }

        print(f"MSE: {mse:.6f}, RMSE: {np.sqrt(mse):.4f}")

        return self.metrics

    def save(self, name: str = 'st_sequence') -> None:
        """モデルを保存"""
        os.makedirs(self.model_dir, exist_ok=True)

        if self._use_pytorch and isinstance(self.model, nn.Module):
            model_path = os.path.join(self.model_dir, f'{name}_lstm.pt')
            torch.save(self.model, model_path)
            print(f"PyTorchモデル保存: {model_path}")
        else:
            weights_path = os.path.join(self.model_dir, f'{name}_weights.joblib')
            joblib.dump(self.model, weights_path)
            print(f"NumPyモデル保存: {weights_path}")

        meta = {
            'metrics': self.metrics,
            'created_at': datetime.now().isoformat(),
            'model_type': 'pytorch' if self._use_pytorch else 'numpy',
        }
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        print(f"メタ情報保存: {meta_path}")


def main():
    """メイン実行"""
    import argparse

    parser = argparse.ArgumentParser(description='ST時系列モデルの学習')
    parser.add_argument('--db', default='data/boatrace.db', help='DBパス')
    parser.add_argument('--start-date', default='2024-01-01', help='開始日')
    parser.add_argument('--end-date', default=None, help='終了日')
    parser.add_argument('--epochs', type=int, default=50, help='エポック数')
    parser.add_argument('--output-name', default='st_sequence', help='出力モデル名')

    args = parser.parse_args()

    trainer = STModelTrainer(args.db)

    # データ読み込み
    X, y = trainer.load_training_data(args.start_date, args.end_date)

    if len(X) == 0:
        print("学習データがありません")
        return

    # 学習
    metrics = trainer.train(X, y, epochs=args.epochs)

    # 保存
    trainer.save(args.output_name)

    print("\n=== ST時系列モデル学習完了 ===")


if __name__ == '__main__':
    main()
