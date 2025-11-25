"""
Stage1: レース選別モデル

「予想しやすいレース」を判定するモデル
buy_score（0〜1）を出力し、スコアが高いレースのみ予想対象とする
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import sqlite3
from datetime import datetime, timedelta
import xgboost as xgb
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import roc_auc_score, precision_score, recall_score, classification_report
import joblib
from pathlib import Path
import optuna


class RaceSelector:
    """
    レース選別モデル（Stage1）

    目的: 予想しやすいレースを選定
    出力: buy_score（0〜1の確率）
          1に近い = 予想しやすいレース
          0に近い = 予想困難なレース
    """

    def __init__(self, db_path: str = "data/boatrace.db", model_dir: str = "models"):
        self.db_path = db_path
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(exist_ok=True)
        self.model = None
        self.feature_names = None

    def calculate_predictability_features(
        self,
        race_id: int,
        conn: sqlite3.Connection
    ) -> Dict:
        """
        予想しやすさを判定する特徴量を計算

        Args:
            race_id: レースID
            conn: データベース接続

        Returns:
            Dict: 予想しやすさ特徴量
        """
        features = {}

        # ===== 1. データ充足率 =====
        # 展示タイムデータの有無
        query_exh = """
            SELECT
                COUNT(CASE WHEN tenji_time IS NOT NULL THEN 1 END) as exh_count,
                COUNT(*) as total_count
            FROM race_details
            WHERE race_id = ?
        """
        df_exh = pd.read_sql_query(query_exh, conn, params=[race_id])
        features['exh_data_completeness'] = df_exh['exh_count'].iloc[0] / df_exh['total_count'].iloc[0] if df_exh['total_count'].iloc[0] > 0 else 0

        # 選手成績データの充実度（全選手の平均出走回数）
        query_racer = """
            SELECT AVG(race_count) as avg_race_count
            FROM (
                SELECT e.racer_number, COUNT(DISTINCT r2.id) as race_count
                FROM entries e
                JOIN races r ON e.race_id = r.id
                JOIN races r2 ON r2.race_date BETWEEN date(r.race_date, '-180 days') AND r.race_date
                JOIN entries e2 ON e2.race_id = r2.id AND e2.racer_number = e.racer_number
                WHERE e.race_id = ?
                GROUP BY e.racer_number
            )
        """
        df_racer = pd.read_sql_query(query_racer, conn, params=[race_id])
        features['racer_data_quality'] = df_racer['avg_race_count'].iloc[0] if not df_racer.empty else 0

        # モーター成績データの充実度
        query_motor = """
            SELECT AVG(motor_races) as avg_motor_races
            FROM (
                SELECT COUNT(*) as motor_races
                FROM entries e
                JOIN races r ON e.race_id = r.id
                WHERE e.race_id = ?
                  AND e.motor_number IS NOT NULL
                GROUP BY e.motor_number
            )
        """
        df_motor = pd.read_sql_query(query_motor, conn, params=[race_id])
        features['motor_data_quality'] = df_motor['avg_motor_races'].iloc[0] if not df_motor.empty else 0

        # ===== 2. レースの安定性 =====
        # コース別勝率の分散（小さいほど安定）
        query_course_var = """
            SELECT
                rd.actual_course,
                AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as win_rate
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.venue_code = (SELECT venue_code FROM races WHERE id = ?)
              AND r.race_date >= date((SELECT race_date FROM races WHERE id = ?), '-90 days')
              AND r.race_date < (SELECT race_date FROM races WHERE id = ?)
            GROUP BY rd.actual_course
        """
        df_course_var = pd.read_sql_query(query_course_var, conn, params=[race_id, race_id, race_id])
        features['course_winrate_variance'] = df_course_var['win_rate'].var() if not df_course_var.empty else 0

        # 選手実力差（勝率の最大-最小）
        query_racer_gap = """
            SELECT
                MAX(win_rate) - MIN(win_rate) as skill_gap
            FROM (
                SELECT
                    e.racer_number,
                    AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as win_rate
                FROM entries e
                JOIN races r ON e.race_id = r.id
                JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                WHERE r.race_date >= date((SELECT race_date FROM races WHERE id = ?), '-180 days')
                  AND r.race_date < (SELECT race_date FROM races WHERE id = ?)
                  AND e.racer_number IN (
                      SELECT racer_number FROM entries WHERE race_id = ?
                  )
                GROUP BY e.racer_number
            )
        """
        df_racer_gap = pd.read_sql_query(query_racer_gap, conn, params=[race_id, race_id, race_id])
        features['racer_skill_gap'] = df_racer_gap['skill_gap'].iloc[0] if not df_racer_gap.empty else 0

        # モーター性能差
        query_motor_gap = """
            SELECT
                MAX(motor_perf) - MIN(motor_perf) as motor_gap
            FROM (
                SELECT
                    e.motor_number,
                    AVG(CASE WHEN res.rank <= 2 THEN 1.0 ELSE 0.0 END) as motor_perf
                FROM entries e
                JOIN races r ON e.race_id = r.id
                JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                WHERE r.venue_code = (SELECT venue_code FROM races WHERE id = ?)
                  AND r.race_date >= date((SELECT race_date FROM races WHERE id = ?), '-90 days')
                  AND r.race_date < (SELECT race_date FROM races WHERE id = ?)
                  AND e.motor_number IN (
                      SELECT motor_number FROM entries WHERE race_id = ?
                  )
                GROUP BY e.motor_number
            )
        """
        df_motor_gap = pd.read_sql_query(query_motor_gap, conn, params=[race_id, race_id, race_id, race_id])
        features['motor_perf_gap'] = df_motor_gap['motor_gap'].iloc[0] if not df_motor_gap.empty else 0

        # ===== 3. 荒れにくさ指標 =====
        # 1号艇逃げ率（会場・直近90日）
        query_escape = """
            SELECT
                AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as escape_rate
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.venue_code = (SELECT venue_code FROM races WHERE id = ?)
              AND rd.actual_course = 1
              AND r.race_date >= date((SELECT race_date FROM races WHERE id = ?), '-90 days')
              AND r.race_date < (SELECT race_date FROM races WHERE id = ?)
        """
        df_escape = pd.read_sql_query(query_escape, conn, params=[race_id, race_id, race_id])
        features['escape_rate'] = df_escape['escape_rate'].iloc[0] if not df_escape.empty else 0

        # インコース勝率（1-3コース）
        query_inside = """
            SELECT
                AVG(CASE WHEN res.rank = 1 THEN 1.0 ELSE 0.0 END) as inside_winrate
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.venue_code = (SELECT venue_code FROM races WHERE id = ?)
              AND rd.actual_course IN (1, 2, 3)
              AND r.race_date >= date((SELECT race_date FROM races WHERE id = ?), '-90 days')
              AND r.race_date < (SELECT race_date FROM races WHERE id = ?)
        """
        df_inside = pd.read_sql_query(query_inside, conn, params=[race_id, race_id, race_id])
        features['inside_winrate'] = df_inside['inside_winrate'].iloc[0] if not df_inside.empty else 0

        # 万舟率（低いほど安定）
        query_upset = """
            SELECT
                AVG(CASE WHEN res.trifecta_odds >= 10000 THEN 1.0 ELSE 0.0 END) as upset_rate
            FROM results res
            JOIN races r ON res.race_id = r.id
            WHERE r.venue_code = (SELECT venue_code FROM races WHERE id = ?)
              AND res.rank = 1
              AND res.trifecta_odds IS NOT NULL
              AND r.race_date >= date((SELECT race_date FROM races WHERE id = ?), '-90 days')
              AND r.race_date < (SELECT race_date FROM races WHERE id = ?)
        """
        df_upset = pd.read_sql_query(query_upset, conn, params=[race_id, race_id, race_id])
        features['upset_rate'] = df_upset['upset_rate'].iloc[0] if not df_upset.empty else 0

        # ===== 4. オッズ・配当関連 =====
        # 会場別平均オッズ（三連単1着）
        query_avg_odds = """
            SELECT AVG(res.trifecta_odds) as avg_odds
            FROM results res
            JOIN races r ON res.race_id = r.id
            WHERE r.venue_code = (SELECT venue_code FROM races WHERE id = ?)
              AND res.rank = 1
              AND res.trifecta_odds IS NOT NULL
              AND r.race_date >= date((SELECT race_date FROM races WHERE id = ?), '-90 days')
              AND r.race_date < (SELECT race_date FROM races WHERE id = ?)
        """
        df_avg_odds = pd.read_sql_query(query_avg_odds, conn, params=[race_id, race_id, race_id])
        features['avg_trifecta_odds'] = df_avg_odds['avg_odds'].iloc[0] if not df_avg_odds.empty else 5000

        # オッズの標準偏差（低いほど安定）
        query_odds_std = """
            SELECT
                AVG(res.trifecta_odds) as avg_odds,
                COUNT(*) as count
            FROM results res
            JOIN races r ON res.race_id = r.id
            WHERE r.venue_code = (SELECT venue_code FROM races WHERE id = ?)
              AND res.rank = 1
              AND res.trifecta_odds IS NOT NULL
              AND r.race_date >= date((SELECT race_date FROM races WHERE id = ?), '-90 days')
              AND r.race_date < (SELECT race_date FROM races WHERE id = ?)
        """
        df_odds_std = pd.read_sql_query(query_odds_std, conn, params=[race_id, race_id, race_id])
        features['odds_volatility'] = df_odds_std['avg_odds'].iloc[0] / 5000 if not df_odds_std.empty and df_odds_std['avg_odds'].iloc[0] > 0 else 1.0

        # ===== 5. 決着パターン =====
        # 1-2-3決着率（順当決着の頻度）
        query_順当 = """
            SELECT
                AVG(CASE WHEN res.combination = '1-2-3' THEN 1.0 ELSE 0.0 END) as jun決着率
            FROM results res
            JOIN races r ON res.race_id = r.id
            WHERE r.venue_code = (SELECT venue_code FROM races WHERE id = ?)
              AND r.race_date >= date((SELECT race_date FROM races WHERE id = ?), '-30 days')
              AND r.race_date < (SELECT race_date FROM races WHERE id = ?)
        """
        df_順当 = pd.read_sql_query(query_順当, conn, params=[race_id, race_id, race_id])
        features['jun決着率'] = df_順当['jun決着率'].iloc[0] if not df_順当.empty else 0

        # インコース決着率（1-2-3, 1-3-2, 2-1-3など）
        query_in決着 = """
            SELECT
                AVG(CASE
                    WHEN res.combination IN ('1-2-3', '1-3-2', '2-1-3', '1-2-4', '1-4-2', '2-1-4')
                    THEN 1.0 ELSE 0.0
                END) as in決着率
            FROM results res
            JOIN races r ON res.race_id = r.id
            WHERE r.venue_code = (SELECT venue_code FROM races WHERE id = ?)
              AND r.race_date >= date((SELECT race_date FROM races WHERE id = ?), '-30 days')
              AND r.race_date < (SELECT race_date FROM races WHERE id = ?)
        """
        df_in決着 = pd.read_sql_query(query_in決着, conn, params=[race_id, race_id, race_id])
        features['in決着率'] = df_in決着['in決着率'].iloc[0] if not df_in決着.empty else 0

        # ===== 6. 気象・時間帯 =====
        # 悪天候率（風速5m/s以上、波高30cm以上）
        query_weather = """
            SELECT
                AVG(CASE WHEN w.wind_speed >= 5 OR w.wave_height >= 30 THEN 1.0 ELSE 0.0 END) as bad_weather_rate
            FROM weather w
            JOIN races r ON w.race_id = r.id
            WHERE r.venue_code = (SELECT venue_code FROM races WHERE id = ?)
              AND r.race_date >= date((SELECT race_date FROM races WHERE id = ?), '-90 days')
              AND r.race_date < (SELECT race_date FROM races WHERE id = ?)
        """
        df_weather = pd.read_sql_query(query_weather, conn, params=[race_id, race_id, race_id])
        features['bad_weather_rate'] = df_weather['bad_weather_rate'].iloc[0] if not df_weather.empty else 0

        # 時間帯（午前/午後/ナイター）
        query_time = """
            SELECT
                r.race_number,
                CASE
                    WHEN r.race_number <= 6 THEN 'morning'
                    WHEN r.race_number <= 10 THEN 'afternoon'
                    ELSE 'night'
                END as time_slot
            FROM races r
            WHERE r.id = ?
        """
        df_time = pd.read_sql_query(query_time, conn, params=[race_id])
        time_slot = df_time['time_slot'].iloc[0] if not df_time.empty else 'afternoon'

        # One-hot encoding
        features['is_morning'] = 1.0 if time_slot == 'morning' else 0.0
        features['is_afternoon'] = 1.0 if time_slot == 'afternoon' else 0.0
        features['is_night'] = 1.0 if time_slot == 'night' else 0.0

        # ===== 7. レースグレード・賞金 =====
        # 高グレードレース（賞金額が高い）
        query_grade = """
            SELECT r.race_number
            FROM races r
            WHERE r.id = ?
        """
        df_grade = pd.read_sql_query(query_grade, conn, params=[race_id])
        race_number = df_grade['race_number'].iloc[0] if not df_grade.empty else 6

        # 最終レース（12R）や特別レース（11R）は荒れやすい傾向
        features['is_final_race'] = 1.0 if race_number == 12 else 0.0
        features['is_special_race'] = 1.0 if race_number >= 11 else 0.0

        return features

    def prepare_training_data(
        self,
        start_date: str,
        end_date: str
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """
        学習データを準備

        Args:
            start_date: 開始日（YYYY-MM-DD）
            end_date: 終了日（YYYY-MM-DD）

        Returns:
            X: 特徴量データ
            y: ラベル（予想が成功したか）
        """
        conn = sqlite3.connect(self.db_path)

        # 対象レースを取得
        query_races = """
            SELECT DISTINCT r.id as race_id
            FROM races r
            WHERE r.race_date >= ?
              AND r.race_date <= ?
            ORDER BY r.race_date, r.race_number
        """
        df_races = pd.read_sql_query(query_races, conn, params=[start_date, end_date])

        print(f"対象レース数: {len(df_races)}")

        # 各レースの特徴量を計算
        features_list = []
        labels_list = []

        for idx, row in df_races.iterrows():
            race_id = row['race_id']

            if idx % 100 == 0:
                print(f"処理中: {idx}/{len(df_races)}")

            # 特徴量計算
            features = self.calculate_predictability_features(race_id, conn)

            # ラベル: このレースで1着を予想できたか
            # （ここでは簡易的に1号艇が1着になったかを使用）
            # 実際には、Stage2モデルの予測が的中したかを使用
            query_label = """
                SELECT
                    CASE WHEN res.rank = 1 AND rd.actual_course = 1 THEN 1 ELSE 0 END as label
                FROM race_details rd
                JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
                WHERE rd.race_id = ?
                  AND rd.actual_course = 1
            """
            df_label = pd.read_sql_query(query_label, conn, params=[race_id])

            if not df_label.empty:
                features['race_id'] = race_id
                features_list.append(features)
                labels_list.append(df_label['label'].iloc[0])

        conn.close()

        X = pd.DataFrame(features_list)
        y = pd.Series(labels_list)

        return X, y

    def train(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_valid: Optional[pd.DataFrame] = None,
        y_valid: Optional[pd.Series] = None,
        params: Optional[Dict] = None
    ) -> Dict:
        """
        モデルを学習

        Args:
            X_train: 訓練データ特徴量
            y_train: 訓練データラベル
            X_valid: 検証データ特徴量
            y_valid: 検証データラベル
            params: XGBoostパラメータ

        Returns:
            Dict: 学習結果サマリー
        """
        # race_idを除外
        feature_cols = [col for col in X_train.columns if col != 'race_id']
        self.feature_names = feature_cols

        X_train_features = X_train[feature_cols]

        # デフォルトパラメータ
        if params is None:
            params = {
                'objective': 'binary:logistic',
                'eval_metric': 'auc',
                'max_depth': 4,
                'learning_rate': 0.05,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'random_state': 42
            }

        # DMatrix作成
        dtrain = xgb.DMatrix(X_train_features, label=y_train, feature_names=self.feature_names)
        evals = [(dtrain, 'train')]

        if X_valid is not None and y_valid is not None:
            X_valid_features = X_valid[feature_cols]
            dvalid = xgb.DMatrix(X_valid_features, label=y_valid, feature_names=self.feature_names)
            evals.append((dvalid, 'valid'))

        # 学習
        self.model = xgb.train(
            params,
            dtrain,
            num_boost_round=1000,
            evals=evals,
            early_stopping_rounds=50 if X_valid is not None else None,
            verbose_eval=False
        )

        # 評価
        train_pred = self.model.predict(dtrain)
        summary = {
            'train_auc': roc_auc_score(y_train, train_pred),
            'train_samples': len(X_train)
        }

        if X_valid is not None:
            valid_pred = self.model.predict(dvalid)
            summary['valid_auc'] = roc_auc_score(y_valid, valid_pred)
            summary['valid_samples'] = len(X_valid)

        return summary

    def predict(self, race_id: int) -> float:
        """
        レースの予想しやすさスコアを予測

        Args:
            race_id: レースID

        Returns:
            float: buy_score（0〜1）
        """
        if self.model is None:
            raise ValueError("モデルが学習されていません")

        conn = sqlite3.connect(self.db_path)
        features = self.calculate_predictability_features(race_id, conn)
        conn.close()

        df_features = pd.DataFrame([features])
        df_features = df_features[self.feature_names]

        dmatrix = xgb.DMatrix(df_features, feature_names=self.feature_names)
        buy_score = self.model.predict(dmatrix)[0]

        return buy_score

    def predict_by_key(self, race_date: str, venue_code: str, race_number: int) -> float:
        """
        日付・会場・レース番号からレースの予想しやすさを予測

        Args:
            race_date: レース日（YYYY-MM-DD）
            venue_code: 会場コード（例: '01'）
            race_number: レース番号

        Returns:
            float: buy_score（0〜1）
        """
        conn = sqlite3.connect(self.db_path)

        # race_idを取得
        query = """
            SELECT id FROM races
            WHERE race_date = ? AND venue_code = ? AND race_number = ?
        """
        df = pd.read_sql_query(query, conn, params=[race_date, venue_code, race_number])
        conn.close()

        if df.empty:
            return 0.5  # デフォルト値

        race_id = df['id'].iloc[0]
        return self.predict(race_id)

    def save_model(self, filename: str = "race_selector.json") -> str:
        """
        モデルを保存

        Args:
            filename: ファイル名

        Returns:
            str: 保存パス
        """
        if self.model is None:
            raise ValueError("モデルが学習されていません")

        filepath = self.model_dir / filename
        self.model.save_model(str(filepath))

        # メタデータ保存
        import json
        meta_path = filepath.with_suffix('.meta.json')
        metadata = {
            'feature_names': self.feature_names,
            'model_type': 'race_selector'
        }

        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        return str(filepath)

    def load_model(self, filename: str = "race_selector.json") -> None:
        """
        モデルを読み込み

        Args:
            filename: ファイル名
        """
        filepath = self.model_dir / filename

        self.model = xgb.Booster()
        self.model.load_model(str(filepath))

        # メタデータ読み込み
        import json
        meta_path = filepath.with_suffix('.meta.json')
        if meta_path.exists():
            with open(meta_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                self.feature_names = metadata.get('feature_names', [])

    def optimize_hyperparameters(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_valid: pd.DataFrame,
        y_valid: pd.Series,
        n_trials: int = 50
    ) -> Dict:
        """
        Optunaでハイパーパラメータ最適化

        Args:
            X_train: 訓練データ特徴量
            y_train: 訓練データラベル
            X_valid: 検証データ特徴量
            y_valid: 検証データラベル
            n_trials: 試行回数

        Returns:
            Dict: 最適パラメータとスコア
        """
        # race_idを除外
        feature_cols = [col for col in X_train.columns if col != 'race_id']
        X_train_features = X_train[feature_cols]
        X_valid_features = X_valid[feature_cols]

        def objective(trial):
            params = {
                'objective': 'binary:logistic',
                'eval_metric': 'auc',
                'max_depth': trial.suggest_int('max_depth', 3, 8),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
                'subsample': trial.suggest_float('subsample', 0.6, 1.0),
                'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
                'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
                'gamma': trial.suggest_float('gamma', 0, 5),
                'reg_alpha': trial.suggest_float('reg_alpha', 0, 10),
                'reg_lambda': trial.suggest_float('reg_lambda', 0, 10),
                'random_state': 42
            }

            dtrain = xgb.DMatrix(X_train_features, label=y_train, feature_names=feature_cols)
            dvalid = xgb.DMatrix(X_valid_features, label=y_valid, feature_names=feature_cols)

            model = xgb.train(
                params,
                dtrain,
                num_boost_round=1000,
                evals=[(dvalid, 'valid')],
                early_stopping_rounds=50,
                verbose_eval=False
            )

            # 検証AUCを最大化
            y_pred = model.predict(dvalid)
            auc = roc_auc_score(y_valid, y_pred)

            return auc

        # Optuna最適化
        study = optuna.create_study(direction='maximize', study_name='stage1_optimization')
        study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

        print(f"\n【最適化完了】")
        print(f"  Best AUC: {study.best_value:.4f}")
        print(f"  Best Params:")
        for key, value in study.best_params.items():
            print(f"    {key}: {value}")

        return {
            'best_params': study.best_params,
            'best_auc': study.best_value,
            'study': study
        }


if __name__ == "__main__":
    # テスト実行
    selector = RaceSelector()

    print("=" * 60)
    print("Stage1: レース選別モデル テスト")
    print("=" * 60)

    # 学習データ準備
    print("\n学習データを準備中...")
    X, y = selector.prepare_training_data(
        start_date='2024-01-01',
        end_date='2024-06-30'
    )

    print(f"データ数: {len(X)}")
    print(f"正例率: {y.mean():.1%}")

    # 訓練/検証分割
    X_train, X_valid, y_train, y_valid = train_test_split(
        X, y, test_size=0.2, random_state=42, shuffle=False
    )

    # 学習
    print("\nモデルを学習中...")
    summary = selector.train(X_train, y_train, X_valid, y_valid)

    print("\n学習結果:")
    print(f"  Train AUC: {summary['train_auc']:.4f}")
    print(f"  Valid AUC: {summary['valid_auc']:.4f}")

    # モデル保存
    path = selector.save_model()
    print(f"\nモデルを保存: {path}")

    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
