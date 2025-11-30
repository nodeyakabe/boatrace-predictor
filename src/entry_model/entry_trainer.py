"""
進入予測モデルの学習
Phase 1: XGBoost multi-classモデル
"""
import os
import sys
import sqlite3
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, classification_report
from datetime import datetime
import json
import joblib
from typing import Dict, List, Tuple, Optional

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.entry_model.entry_features import create_entry_training_dataset


class EntryModelTrainer:
    """
    進入予測モデルのトレーナー

    XGBoost multi-class で各艇の進入コース（1-6）を予測
    """

    def __init__(self, db_path: str, model_dir: str = 'models'):
        self.db_path = db_path
        self.model_dir = model_dir
        self.model = None
        self.feature_names = None
        self.metrics = {}

    def load_training_data(self, start_date: str = None,
                           end_date: str = None) -> pd.DataFrame:
        """学習データを読み込み"""
        print("=== 進入予測学習データ読み込み ===")
        df = create_entry_training_dataset(self.db_path, start_date, end_date)
        return df

    def prepare_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
        """学習用データを準備"""
        # ターゲット: actual_course (1-6) → 0-5 に変換
        y = df['actual_course'].values - 1

        # 特徴量
        exclude_cols = ['race_id', 'pit_number', 'actual_course', 'race_date',
                       'venue_code', 'racer_number']
        X = df.drop([c for c in exclude_cols if c in df.columns], axis=1)
        X = X.select_dtypes(include=[np.number])

        # NaN処理
        X = X.fillna(0)

        self.feature_names = list(X.columns)

        return X, y

    def train(self, df: pd.DataFrame, params: Dict = None) -> Dict:
        """モデルを学習"""
        if params is None:
            params = {
                'objective': 'multi:softprob',
                'num_class': 6,
                'eval_metric': 'mlogloss',
                'max_depth': 6,
                'learning_rate': 0.05,
                'n_estimators': 300,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'min_child_weight': 5,
                'gamma': 0.1,
                'random_state': 42,
                'n_jobs': -1,
            }

        X, y = self.prepare_data(df)

        print(f"\n=== 進入予測モデル学習 ===")
        print(f"データサイズ: {len(X):,}件")
        print(f"特徴量数: {len(X.columns)}")
        print(f"クラス分布: {np.bincount(y)}")

        # TimeSeriesSplitでCV
        tscv = TimeSeriesSplit(n_splits=5)
        cv_accuracies = []
        cv_reports = []

        for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            model = xgb.XGBClassifier(**params)
            model.fit(X_train, y_train, verbose=False)

            y_pred = model.predict(X_val)
            acc = accuracy_score(y_val, y_pred)
            cv_accuracies.append(acc)

            # 枠なり率（予測が枠番と一致する割合）
            pit_numbers = df.iloc[val_idx]['pit_number'].values - 1
            frame_match = (y_pred == pit_numbers).mean()

            print(f"Fold {fold+1}: Accuracy = {acc:.4f}, 枠なり予測率 = {frame_match:.4f}")

        mean_acc = np.mean(cv_accuracies)
        print(f"\nCV平均Accuracy: {mean_acc:.4f} (+/- {np.std(cv_accuracies):.4f})")

        # 全データで最終モデルを学習
        self.model = xgb.XGBClassifier(**params)
        self.model.fit(X, y, verbose=False)

        # 特徴量重要度
        importances = self.model.feature_importances_
        importance_df = pd.DataFrame({
            'feature': self.feature_names,
            'importance': importances
        }).sort_values('importance', ascending=False)

        print("\n特徴量重要度 Top10:")
        for _, row in importance_df.head(10).iterrows():
            print(f"  {row['feature']}: {row['importance']:.4f}")

        self.metrics = {
            'cv_accuracy_mean': float(mean_acc),
            'cv_accuracy_std': float(np.std(cv_accuracies)),
            'cv_accuracies': cv_accuracies,
            'n_features': len(self.feature_names),
            'n_samples': len(X),
            'feature_importances': importance_df.to_dict('records')[:20],
        }

        return self.metrics

    def save(self, name: str = 'entry_model') -> None:
        """モデルを保存"""
        os.makedirs(self.model_dir, exist_ok=True)

        model_path = os.path.join(self.model_dir, f'{name}.joblib')
        joblib.dump(self.model, model_path)
        print(f"モデル保存: {model_path}")

        meta = {
            'feature_names': self.feature_names,
            'metrics': self.metrics,
            'created_at': datetime.now().isoformat(),
        }
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        print(f"メタ情報保存: {meta_path}")

    def load(self, name: str = 'entry_model') -> bool:
        """モデルを読み込み"""
        model_path = os.path.join(self.model_dir, f'{name}.joblib')
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')

        if not os.path.exists(model_path):
            return False

        self.model = joblib.load(model_path)

        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            self.feature_names = meta.get('feature_names', [])
            self.metrics = meta.get('metrics', {})

        return True

    def evaluate_on_test(self, test_df: pd.DataFrame) -> Dict:
        """テストデータで評価"""
        X, y = self.prepare_data(test_df)
        X = X.reindex(columns=self.feature_names, fill_value=0)

        y_pred = self.model.predict(X)
        y_prob = self.model.predict_proba(X)

        accuracy = accuracy_score(y, y_pred)

        # 枠なり率
        pit_numbers = test_df['pit_number'].values - 1
        actual_frame_rate = (y == pit_numbers).mean()
        predicted_frame_rate = (y_pred == pit_numbers).mean()

        # コース別精度
        course_accuracies = {}
        for course in range(6):
            mask = y == course
            if mask.sum() > 0:
                course_accuracies[course + 1] = float((y_pred[mask] == y[mask]).mean())

        results = {
            'accuracy': float(accuracy),
            'actual_frame_rate': float(actual_frame_rate),
            'predicted_frame_rate': float(predicted_frame_rate),
            'course_accuracies': course_accuracies,
            'n_samples': len(y),
        }

        print(f"\n=== テスト評価 ===")
        print(f"Accuracy: {accuracy:.4f}")
        print(f"実際の枠なり率: {actual_frame_rate:.4f}")
        print(f"予測の枠なり率: {predicted_frame_rate:.4f}")
        print(f"コース別精度: {course_accuracies}")

        return results


def main():
    """メイン実行"""
    import argparse

    parser = argparse.ArgumentParser(description='進入予測モデルの学習')
    parser.add_argument('--db', default='data/boatrace.db', help='DBパス')
    parser.add_argument('--start-date', default='2024-01-01', help='開始日')
    parser.add_argument('--end-date', default=None, help='終了日')
    parser.add_argument('--output-name', default='entry_model', help='出力モデル名')

    args = parser.parse_args()

    trainer = EntryModelTrainer(args.db)

    # データ読み込み
    df = trainer.load_training_data(args.start_date, args.end_date)

    if len(df) == 0:
        print("学習データがありません")
        return

    # 学習
    metrics = trainer.train(df)

    # 保存
    trainer.save(args.output_name)

    print("\n=== 進入予測モデル学習完了 ===")
    print(f"CV Accuracy: {metrics['cv_accuracy_mean']:.4f}")


if __name__ == '__main__':
    main()
