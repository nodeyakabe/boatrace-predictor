"""
進入コース予測モデル
Phase 2.2: 枠番から実際のコース取りを予測
"""
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, classification_report
from typing import Dict, List, Optional
import sqlite3
import json
import os


class EntryCoursePredictor:
    """進入コース予測モデル"""

    def __init__(self, db_path: str, model_dir: str = 'models'):
        self.db_path = db_path
        self.model_dir = model_dir
        self.model = None
        self.feature_names = None

    def build_training_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """学習用データを構築"""
        with sqlite3.connect(self.db_path) as conn:
            query = """
                SELECT
                    r.id as race_id,
                    r.venue_code,
                    r.race_date,
                    r.race_number,
                    e.pit_number,
                    e.racer_number,
                    e.racer_rank,
                    e.win_rate,
                    e.motor_number,
                    COALESCE(e.motor_2ren_rate, 0) as motor_2ren_rate,
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
        df = self._add_features(df)

        # ターゲット: コース変更したかどうか
        df['course_changed'] = (df['pit_number'] != df['actual_course']).astype(int)

        return df

    def _add_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """特徴量を追加"""
        result_df = df.copy()

        # 選手級別のエンコーディング
        rank_map = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
        result_df['racer_rank_score'] = df['racer_rank'].map(rank_map).fillna(2)

        # 枠番の内外フラグ
        result_df['is_inner_pit'] = (df['pit_number'] <= 3).astype(int)
        result_df['is_outer_pit'] = (df['pit_number'] >= 4).astype(int)

        # 会場コードを数値化
        result_df['venue_numeric'] = df['venue_code'].astype(int)

        # レース番号特徴量
        result_df['is_late_race'] = (df['race_number'] > 8).astype(int)

        return result_df

    def train(self, train_df: pd.DataFrame, valid_df: pd.DataFrame = None) -> Dict:
        """モデルを学習"""
        feature_cols = [
            'pit_number', 'racer_rank_score', 'win_rate', 'motor_2ren_rate',
            'is_inner_pit', 'is_outer_pit', 'venue_numeric', 'is_late_race'
        ]

        # 存在する列のみ使用
        feature_cols = [c for c in feature_cols if c in train_df.columns]
        self.feature_names = feature_cols

        X_train = train_df[feature_cols]
        y_train = train_df['course_changed']

        params = {
            'objective': 'binary:logistic',
            'eval_metric': 'auc',
            'max_depth': 4,
            'learning_rate': 0.1,
            'n_estimators': 200,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'random_state': 42,
            'use_label_encoder': False,
        }

        self.model = xgb.XGBClassifier(**params)

        if valid_df is not None:
            X_valid = valid_df[feature_cols]
            y_valid = valid_df['course_changed']
            self.model.fit(
                X_train, y_train,
                eval_set=[(X_valid, y_valid)],
                verbose=False
            )
            pred = self.model.predict(X_valid)
            accuracy = accuracy_score(y_valid, pred)
            print(f"進入予測精度: {accuracy:.4f}")
            return {'accuracy': accuracy}
        else:
            self.model.fit(X_train, y_train, verbose=False)
            return {}

    def predict_course_change_prob(self, features: pd.DataFrame) -> np.ndarray:
        """コース変更確率を予測"""
        if self.model is None:
            raise ValueError("モデルが学習されていません")

        X = features[self.feature_names]
        return self.model.predict_proba(X)[:, 1]

    def predict_actual_courses(self, race_features: pd.DataFrame) -> Dict[int, int]:
        """各艇の実際のコースを予測"""
        if len(race_features) != 6:
            raise ValueError("6艇のデータが必要です")

        # コース変更確率を取得
        change_probs = self.predict_course_change_prob(race_features)

        pit_numbers = race_features['pit_number'].values

        # 簡易的な予測: 変更確率が高い艇は内側のコースを取る傾向
        # より高度な実装では、マルコフ連鎖やシミュレーションを使用
        predicted_courses = {}

        # 基本: 枠番通り
        for i, pit in enumerate(pit_numbers):
            predicted_courses[int(pit)] = int(pit)

        # 変更確率が高い艇を調整
        sorted_indices = np.argsort(-change_probs)  # 高い順

        # 最も変更確率が高い艇が内側を取ると仮定
        for idx in sorted_indices[:2]:  # 上位2艇のみ調整
            if change_probs[idx] > 0.3:  # 閾値
                pit = int(pit_numbers[idx])
                # 内側に移動を試みる
                for target_course in range(1, pit):
                    if target_course not in predicted_courses.values():
                        predicted_courses[pit] = target_course
                        break

        return predicted_courses

    def save(self, name: str = 'entry_course'):
        """モデルを保存"""
        os.makedirs(self.model_dir, exist_ok=True)

        if self.model is not None:
            model_path = os.path.join(self.model_dir, f'{name}.json')
            self.model.save_model(model_path)

        meta = {
            'feature_names': self.feature_names,
        }
        meta_path = os.path.join(self.model_dir, f'{name}.meta.json')
        with open(meta_path, 'w') as f:
            json.dump(meta, f)

    def load(self, name: str = 'entry_course'):
        """モデルを読み込み"""
        model_path = os.path.join(self.model_dir, f'{name}.json')
        self.model = xgb.XGBClassifier()
        self.model.load_model(model_path)

        meta_path = os.path.join(self.model_dir, f'{name}.meta.json')
        with open(meta_path, 'r') as f:
            meta = json.load(f)
        self.feature_names = meta['feature_names']
