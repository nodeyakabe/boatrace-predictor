"""
2着専用スコアリングモデル

差し・まくり差し特化型特徴量を使用して2着予測精度を向上させる。

背景:
- 現在の2着的中率: 21.58%（ランダム20%とほぼ同等）
- 1着予測と2着予測では異なる勝ち方のパターンがある
  - 1着: 逃げ、まくり
  - 2着: 差し、まくり差し

アプローチ:
- 2着特化型の特徴量を追加
- 差し・まくり差しの適性を評価
- 既存のConditionalRankModelと統合

期待効果: 2着的中率 +3pt以上
"""

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from typing import Dict, List, Tuple, Optional
import json
import os
from datetime import datetime
import logging


class SecondPlaceSpecializedScorer:
    """
    2着専用スコアラー

    差し・まくり差しに特化した特徴量を使用して
    2着予測の精度を向上させる。
    """

    def __init__(self, model_dir: str = 'models', db_path: str = 'data/boatrace.db'):
        """
        初期化

        Args:
            model_dir: モデル保存ディレクトリ
            db_path: データベースパス
        """
        self.model_dir = model_dir
        self.db_path = db_path
        self.model = None
        self.feature_names = None
        self.logger = logging.getLogger(__name__)

        # 2着特化型特徴量のリスト
        self.specialized_features = [
            # 差し適性
            'sashi_rate',           # 差し率
            'makurisashi_rate',     # まくり差し率
            'sashi_makurisashi_rate',  # 差し+まくり差し率（複合）
            # 相対特徴量
            'score_diff_from_first',     # 1着予測艇とのスコア差
            'win_rate_diff_from_first',  # 1着予測艇との勝率差
            'motor_diff_from_first',     # 1着予測艇とのモーター2連対率差
            # コース特徴量
            'course_distance_from_first',  # 1着艇からのコース距離
            'is_inner_than_first',        # 1着艇より内か
            'is_outer_than_first',        # 1着艇より外か
            # 展示・ST特徴量
            'exhibition_rank',     # 展示タイム順位
            'st_rank',             # ST順位
            'exhibition_diff_from_first',  # 1着艇との展示タイム差
            'st_diff_from_first',         # 1着艇とのST差
            # 2着実績
            'recent_2nd_place_rate',  # 直近2着率
            'second_rate',            # 2連対率
            # コース適性
            'course_second_rate',  # コース別2着率
            # 1着艇の特性（条件として）
            'first_nige_rate',     # 1着予測艇の逃げ率
            'first_course',        # 1着予測艇のコース
            'first_rank',          # 1着予測艇のランク（A1=4, A2=3, B1=2, B2=1）
        ]

    def prepare_training_data(
        self,
        df: pd.DataFrame,
        predicted_first_col: str = 'predicted_first_pit'
    ) -> Tuple[pd.DataFrame, np.ndarray]:
        """
        学習用データを準備

        予想1着を条件として2着予測データを作成。
        学習時と予測時のデータ分布を一致させる。

        Args:
            df: レースデータ（各艇の特徴量を含む）
            predicted_first_col: 予測1着艇のカラム名

        Returns:
            (特徴量DataFrame, ラベル配列)
        """
        # 6艇完備のレースのみ抽出
        race_counts = df.groupby('race_id').size()
        valid_races = race_counts[race_counts == 6].index
        df = df[df['race_id'].isin(valid_races)].copy()

        if len(df) == 0:
            return pd.DataFrame(), np.array([])

        # 予想1着がない場合は総合スコアで計算
        if predicted_first_col not in df.columns:
            score_col = 'total_score' if 'total_score' in df.columns else 'win_rate'
            if score_col in df.columns:
                idx_max = df.groupby('race_id')[score_col].idxmax()
                df['is_predicted_first'] = df.index.isin(idx_max).astype(int)
                df.loc[df['is_predicted_first'] == 1, predicted_first_col] = df.loc[
                    df['is_predicted_first'] == 1, 'pit_number'
                ]
                # race_idごとに予想1着艇を伝播
                first_pits = df[df['is_predicted_first'] == 1][['race_id', 'pit_number']].copy()
                first_pits.columns = ['race_id', predicted_first_col]
                df = df.drop(columns=[predicted_first_col], errors='ignore')
                df = df.merge(first_pits, on='race_id', how='left')
            else:
                self.logger.warning("スコアカラムが見つかりません")
                return pd.DataFrame(), np.array([])

        # 予想1着艇の情報を取得
        first_info = df[df['pit_number'] == df[predicted_first_col]].copy()
        first_info = first_info[[
            'race_id', 'pit_number', 'win_rate', 'motor_second_rate',
            'total_score', 'exhibition_time', 'avg_st', 'racer_rank'
        ]].rename(columns={
            'pit_number': 'first_pit',
            'win_rate': 'first_win_rate',
            'motor_second_rate': 'first_motor_2rate',
            'total_score': 'first_score',
            'exhibition_time': 'first_exhibition',
            'avg_st': 'first_st',
            'racer_rank': 'first_rank_str'
        })

        # 予想1着を除外した5艇
        remaining = df[df['pit_number'] != df[predicted_first_col]].copy()
        remaining = remaining.merge(first_info, on='race_id', how='left')

        # 2着特化型特徴量を計算
        features_df = self._calculate_specialized_features(remaining)

        # ラベル: 実際の2着かどうか
        y = (remaining['rank'] == 2).astype(int).values

        return features_df, y

    def _calculate_specialized_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        2着特化型特徴量を計算

        Args:
            df: マージ済みデータ（1着艇情報含む）

        Returns:
            特徴量DataFrame
        """
        features = pd.DataFrame(index=df.index)

        # 基本特徴量
        basic_cols = [
            'win_rate', 'second_rate', 'third_rate',
            'motor_second_rate', 'boat_second_rate',
            'avg_st', 'f_count', 'l_count'
        ]
        for col in basic_cols:
            if col in df.columns:
                features[col] = df[col].fillna(0)

        # 差し・まくり差し率（データベースから取得する場合）
        # 注: 実際のデータにない場合は勝率から推定
        if 'sashi_rate' in df.columns:
            features['sashi_rate'] = df['sashi_rate'].fillna(0)
        else:
            # 推定: 2着率が高く勝率が低いほど差し傾向
            features['sashi_rate'] = np.where(
                df['win_rate'] > 0,
                df['second_rate'] / (df['win_rate'] + 0.01),
                0
            )

        if 'makurisashi_rate' in df.columns:
            features['makurisashi_rate'] = df['makurisashi_rate'].fillna(0)
        else:
            # 推定: 外コース + 高い2連対率 → まくり差し傾向
            features['makurisashi_rate'] = np.where(
                df['pit_number'] >= 4,
                df['second_rate'] * 0.3,
                df['second_rate'] * 0.1
            )

        # 差し + まくり差し率
        features['sashi_makurisashi_rate'] = (
            features.get('sashi_rate', 0) + features.get('makurisashi_rate', 0)
        )

        # 相対特徴量（1着予測艇との差）
        if 'first_score' in df.columns and 'total_score' in df.columns:
            features['score_diff_from_first'] = df['total_score'] - df['first_score']

        if 'first_win_rate' in df.columns and 'win_rate' in df.columns:
            features['win_rate_diff_from_first'] = df['win_rate'] - df['first_win_rate']

        if 'first_motor_2rate' in df.columns and 'motor_second_rate' in df.columns:
            features['motor_diff_from_first'] = df['motor_second_rate'] - df['first_motor_2rate']

        # コース特徴量
        if 'first_pit' in df.columns:
            features['course_distance_from_first'] = (
                df['pit_number'] - df['first_pit']
            ).abs()
            features['is_inner_than_first'] = (df['pit_number'] < df['first_pit']).astype(int)
            features['is_outer_than_first'] = (df['pit_number'] > df['first_pit']).astype(int)
            features['first_course'] = df['first_pit']

        # 展示・ST特徴量
        if 'exhibition_time' in df.columns:
            # 展示タイム順位（レース内）
            if 'race_id' in df.columns:
                features['exhibition_rank'] = df.groupby('race_id')['exhibition_time'].rank(
                    ascending=True, method='min', na_option='bottom'
                )
            else:
                # 単一レースの場合は全体でランク付け
                features['exhibition_rank'] = df['exhibition_time'].rank(
                    ascending=True, method='min', na_option='bottom'
                )
            if 'first_exhibition' in df.columns:
                features['exhibition_diff_from_first'] = (
                    df['exhibition_time'] - df['first_exhibition']
                )

        if 'avg_st' in df.columns:
            # ST順位（レース内、小さいほど良い）
            if 'race_id' in df.columns:
                features['st_rank'] = df.groupby('race_id')['avg_st'].rank(
                    ascending=True, method='min', na_option='bottom'
                )
            else:
                # 単一レースの場合は全体でランク付け
                features['st_rank'] = df['avg_st'].rank(
                    ascending=True, method='min', na_option='bottom'
                )
            if 'first_st' in df.columns:
                features['st_diff_from_first'] = df['avg_st'] - df['first_st']

        # 2着実績
        if 'second_rate' in df.columns:
            features['recent_2nd_place_rate'] = df['second_rate'] / 100.0

        # コース別2着率（推定）
        course_second_rates = {
            1: 0.18,  # 1コースは逃げが多いため2着率低め
            2: 0.22,  # 差し狙いで2着多い
            3: 0.20,
            4: 0.18,
            5: 0.12,
            6: 0.10
        }
        features['course_second_rate'] = df['pit_number'].map(course_second_rates)

        # 1着予測艇の特性
        if 'first_rank_str' in df.columns:
            rank_map = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
            features['first_rank'] = df['first_rank_str'].map(rank_map).fillna(1)

        # 逃げ率の推定（1コースの勝率をベースに）
        if 'first_pit' in df.columns:
            # 1コースA1の逃げ率は約70%、その他は低い
            features['first_nige_rate'] = np.where(
                df['first_pit'] == 1,
                0.7 * (features.get('first_rank', 2) / 4),
                0.1
            )

        # 欠損値処理
        features = features.fillna(0)

        return features

    def train(
        self,
        train_df: pd.DataFrame,
        valid_df: pd.DataFrame = None,
        params: Dict = None
    ) -> Dict[str, float]:
        """
        モデルを学習

        Args:
            train_df: 学習データ
            valid_df: 検証データ
            params: LightGBMパラメータ

        Returns:
            学習結果（AUCなど）
        """
        if params is None:
            params = {
                'objective': 'binary',
                'metric': 'auc',
                'boosting_type': 'gbdt',
                'num_leaves': 31,
                'learning_rate': 0.05,
                'feature_fraction': 0.8,
                'bagging_fraction': 0.8,
                'bagging_freq': 5,
                'min_child_samples': 20,
                'random_state': 42,
                'verbose': -1
            }

        # 学習データ準備
        X_train, y_train = self.prepare_training_data(train_df)

        if len(X_train) == 0:
            self.logger.error("学習データが空です")
            return {'error': 'empty_data'}

        self.feature_names = list(X_train.columns)
        self.logger.info(f"学習データ: {len(X_train)}件, 特徴量数: {len(self.feature_names)}")
        self.logger.info(f"正例率: {y_train.mean():.2%}")

        # LightGBMデータセット
        train_data = lgb.Dataset(X_train, label=y_train)

        results = {}

        if valid_df is not None:
            X_valid, y_valid = self.prepare_training_data(valid_df)
            if len(X_valid) > 0:
                # 特徴量を揃える
                for col in self.feature_names:
                    if col not in X_valid.columns:
                        X_valid[col] = 0
                X_valid = X_valid[self.feature_names]

                valid_data = lgb.Dataset(X_valid, label=y_valid, reference=train_data)

                self.model = lgb.train(
                    params,
                    train_data,
                    num_boost_round=500,
                    valid_sets=[valid_data],
                    callbacks=[
                        lgb.early_stopping(stopping_rounds=50),
                        lgb.log_evaluation(period=100)
                    ]
                )

                # 検証スコア
                pred_valid = self.model.predict(X_valid)
                auc = roc_auc_score(y_valid, pred_valid)
                results['valid_auc'] = auc
                self.logger.info(f"検証AUC: {auc:.4f}")
        else:
            self.model = lgb.train(
                params,
                train_data,
                num_boost_round=500
            )

        # 特徴量重要度
        importance = self.model.feature_importance(importance_type='gain')
        feature_importance = dict(zip(self.feature_names, importance))
        sorted_importance = sorted(
            feature_importance.items(), key=lambda x: x[1], reverse=True
        )

        self.logger.info("=== 特徴量重要度 Top 10 ===")
        for fname, imp in sorted_importance[:10]:
            self.logger.info(f"  {fname}: {imp:.2f}")

        results['feature_importance'] = feature_importance

        return results

    def predict(
        self,
        race_features: pd.DataFrame,
        predicted_first_pit: int
    ) -> Dict[int, float]:
        """
        2着確率を予測

        Args:
            race_features: 6艇の特徴量
            predicted_first_pit: 予測1着艇の艇番

        Returns:
            {艇番: 2着確率} の辞書
        """
        if self.model is None:
            raise ValueError("モデルが学習されていません")

        # 1着候補を除外
        remaining = race_features[race_features['pit_number'] != predicted_first_pit].copy()

        if len(remaining) == 0:
            return {}

        # 1着艇の情報を取得
        first_row = race_features[race_features['pit_number'] == predicted_first_pit].iloc[0]
        remaining['first_pit'] = predicted_first_pit
        remaining['first_win_rate'] = first_row.get('win_rate', 0)
        remaining['first_motor_2rate'] = first_row.get('motor_second_rate', 0)
        remaining['first_score'] = first_row.get('total_score', 0)
        remaining['first_exhibition'] = first_row.get('exhibition_time', 0)
        remaining['first_st'] = first_row.get('avg_st', 0)
        remaining['first_rank_str'] = first_row.get('racer_rank', 'B1')

        # 特徴量計算
        features_df = self._calculate_specialized_features(remaining)

        # 特徴量を揃える
        for col in self.feature_names:
            if col not in features_df.columns:
                features_df[col] = 0
        features_df = features_df[self.feature_names]

        # 予測
        probs = self.model.predict(features_df)

        # 正規化
        probs = probs / probs.sum()

        return {
            int(remaining.iloc[i]['pit_number']): float(probs[i])
            for i in range(len(remaining))
        }

    def get_second_place_scores(
        self,
        predictions: List[Dict],
        race_features: pd.DataFrame
    ) -> List[Dict]:
        """
        既存の予測結果に2着専用スコアを追加

        Args:
            predictions: 予測結果リスト
            race_features: レース特徴量

        Returns:
            2着スコアが追加された予測結果
        """
        if self.model is None or len(predictions) == 0:
            return predictions

        # 予測1着艇を取得
        predicted_first = predictions[0]['pit_number']

        try:
            # 2着確率を予測
            second_probs = self.predict(race_features, predicted_first)

            # 予測結果に追加
            for pred in predictions:
                pit = pred['pit_number']
                if pit == predicted_first:
                    pred['specialized_2nd_prob'] = 0.0
                else:
                    pred['specialized_2nd_prob'] = round(
                        second_probs.get(pit, 0.0), 4
                    )

        except Exception as e:
            self.logger.warning(f"2着専用スコア計算エラー: {e}")
            for pred in predictions:
                pred['specialized_2nd_prob'] = 0.0

        return predictions

    def save(self, name: str = 'second_place_specialized'):
        """モデルを保存"""
        os.makedirs(self.model_dir, exist_ok=True)

        if self.model is not None:
            model_path = os.path.join(self.model_dir, f'{name}.txt')
            self.model.save_model(model_path)

        # メタ情報を保存
        meta = {
            'feature_names': self.feature_names,
            'specialized_features': self.specialized_features,
            'created_at': datetime.now().isoformat()
        }
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        self.logger.info(f"モデルを {self.model_dir} に保存しました")

    def load(self, name: str = 'second_place_specialized'):
        """モデルを読み込み"""
        model_path = os.path.join(self.model_dir, f'{name}.txt')
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')

        if os.path.exists(model_path):
            self.model = lgb.Booster(model_file=model_path)

        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            self.feature_names = meta.get('feature_names', [])
            self.specialized_features = meta.get('specialized_features', [])

        self.logger.info(f"モデルを {self.model_dir} から読み込みました")


class SecondPlaceIntegrator:
    """
    2着予測の統合器

    条件付きモデル（ConditionalRankModel）と
    2着専用モデル（SecondPlaceSpecializedScorer）を統合する。
    """

    def __init__(
        self,
        specialized_scorer: SecondPlaceSpecializedScorer = None,
        integration_weight: float = 0.5
    ):
        """
        Args:
            specialized_scorer: 2着専用スコアラー
            integration_weight: 統合重み（専用モデルの重み、0.0-1.0）
        """
        self.specialized_scorer = specialized_scorer
        self.integration_weight = integration_weight
        self.logger = logging.getLogger(__name__)

    def integrate_second_place_predictions(
        self,
        predictions: List[Dict],
        conditional_second_probs: Dict[int, float],
        race_features: pd.DataFrame
    ) -> Dict[int, float]:
        """
        2着予測を統合

        Args:
            predictions: 予測結果リスト
            conditional_second_probs: 条件付きモデルの2着確率
            race_features: レース特徴量

        Returns:
            統合された2着確率
        """
        if len(predictions) == 0:
            return {}

        predicted_first = predictions[0]['pit_number']

        # 専用モデルの予測
        specialized_probs = {}
        if self.specialized_scorer is not None and self.specialized_scorer.model is not None:
            try:
                specialized_probs = self.specialized_scorer.predict(
                    race_features, predicted_first
                )
            except Exception as e:
                self.logger.warning(f"専用モデル予測エラー: {e}")

        # 統合
        integrated = {}
        all_pits = set(conditional_second_probs.keys()) | set(specialized_probs.keys())

        for pit in all_pits:
            if pit == predicted_first:
                continue

            cond_prob = conditional_second_probs.get(pit, 0.0)
            spec_prob = specialized_probs.get(pit, 0.0)

            if spec_prob > 0:
                # 両方ある場合は統合
                integrated[pit] = (
                    (1 - self.integration_weight) * cond_prob +
                    self.integration_weight * spec_prob
                )
            else:
                # 専用モデルがない場合は条件付きモデルのみ
                integrated[pit] = cond_prob

        # 正規化
        total = sum(integrated.values())
        if total > 0:
            integrated = {pit: prob / total for pit, prob in integrated.items()}

        return integrated


# データ準備用ヘルパー関数
def prepare_training_dataset(
    db_path: str,
    start_date: str = '2024-01-01',
    end_date: str = '2025-12-01'
) -> pd.DataFrame:
    """
    学習用データセットを準備

    Args:
        db_path: データベースパス
        start_date: 開始日
        end_date: 終了日

    Returns:
        学習用DataFrame
    """
    import sqlite3

    conn = sqlite3.connect(db_path)

    # レース情報、出走表、結果を結合
    query = """
    SELECT
        r.id AS race_id,
        r.venue_code,
        r.race_date,
        r.race_grade,
        e.pit_number,
        e.racer_number,
        e.racer_rank,
        e.win_rate,
        e.second_rate,
        e.third_rate,
        e.motor_number,
        e.motor_second_rate,
        e.boat_second_rate,
        e.avg_st,
        e.f_count,
        e.l_count,
        rd.exhibition_time,
        rd.st_time,
        rd.actual_course,
        rd.tilt_angle,
        res.rank
    FROM races r
    INNER JOIN entries e ON r.id = e.race_id
    INNER JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
    LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
    WHERE r.race_date BETWEEN ? AND ?
        AND res.is_invalid = 0
        AND res.rank IS NOT NULL
        AND CAST(res.rank AS INTEGER) BETWEEN 1 AND 6
    ORDER BY r.race_date, r.id, e.pit_number
    """

    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()

    # rankを整数に変換
    df['rank'] = df['rank'].astype(int)

    # 総合スコアを簡易計算（勝率ベース）
    df['total_score'] = df['win_rate'] * 10 + df['motor_second_rate'] * 0.5

    return df


if __name__ == '__main__':
    # テスト用
    import sys
    sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(__name__)
    logger.info("=== 2着専用スコアリングモデル テスト ===")

    # データ準備
    db_path = 'data/boatrace.db'

    logger.info("学習データを準備中...")
    train_df = prepare_training_dataset(db_path, '2024-01-01', '2024-10-31')
    valid_df = prepare_training_dataset(db_path, '2024-11-01', '2024-12-31')

    logger.info(f"学習データ: {len(train_df)}件, 検証データ: {len(valid_df)}件")

    # モデル学習
    scorer = SecondPlaceSpecializedScorer(db_path=db_path)
    results = scorer.train(train_df, valid_df)

    logger.info(f"学習結果: {results}")

    # モデル保存
    scorer.save()

    logger.info("=== テスト完了 ===")
