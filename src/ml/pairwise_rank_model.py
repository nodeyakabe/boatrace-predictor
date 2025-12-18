"""
ペアワイズ相対スコアリングによる順位予測モデル

アプローチ3: 艇間の直接対決スコアで予測精度を改善

理論的根拠:
- 現在のモデルは各艇の絶対スコアを計算しているが、実際のレースは相対的な強さで決まる
- 艇1が艇2に勝つ確率 P(1 > 2) を直接モデル化することで、より精度の高い順位予測が可能

実装方針:
- 各艇ペア(i, j)に対してペアワイズ特徴量を計算
- LightGBM二値分類で艇iが艇jより上位かを予測
- 全ペアの勝率から最終順位を復元

期待効果: 2着・3着的中率の向上
"""

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, log_loss
from typing import Dict, List, Tuple, Optional
from itertools import combinations, permutations
import json
import os
from datetime import datetime
import logging


class PairwiseRankModel:
    """
    ペアワイズ順位予測モデル

    艇間の直接対決確率をモデル化し、全ペアの勝率から最終順位を予測する。
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

        # ペアワイズ特徴量の定義
        # 差分特徴量（艇i - 艇j）
        self.diff_features = [
            'win_rate',             # 勝率差
            'second_rate',          # 2連対率差
            'third_rate',           # 3連対率差
            'motor_second_rate',    # モーター2連対率差
            'boat_second_rate',     # ボート2連対率差
            'avg_st',               # 平均ST差
            'exhibition_time',      # 展示タイム差
            'total_score',          # 総合スコア差
        ]

        # コース有利度マップ（1コースが最も有利）
        self.course_advantage = {
            1: 1.0,   # 1コース: 基準
            2: 0.4,   # 2コース
            3: 0.35,  # 3コース
            4: 0.30,  # 4コース
            5: 0.25,  # 5コース
            6: 0.20   # 6コース
        }

        # ランク値マップ
        self.rank_values = {
            'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1
        }

    def _calculate_pairwise_features(
        self,
        boat_i: Dict,
        boat_j: Dict
    ) -> Dict[str, float]:
        """
        2艇間のペアワイズ特徴量を計算

        Args:
            boat_i: 艇iのデータ
            boat_j: 艇jのデータ

        Returns:
            ペアワイズ特徴量の辞書
        """
        features = {}

        # 差分特徴量
        for feat in self.diff_features:
            val_i = boat_i.get(feat, 0) or 0
            val_j = boat_j.get(feat, 0) or 0
            features[f'diff_{feat}'] = val_i - val_j

        # 級別差（A1=4, A2=3, B1=2, B2=1）
        rank_i = self.rank_values.get(boat_i.get('racer_rank', 'B2'), 1)
        rank_j = self.rank_values.get(boat_j.get('racer_rank', 'B2'), 1)
        features['diff_class'] = rank_i - rank_j

        # コース有利度差
        course_i = boat_i.get('pit_number', 1)
        course_j = boat_j.get('pit_number', 1)
        adv_i = self.course_advantage.get(course_i, 0.3)
        adv_j = self.course_advantage.get(course_j, 0.3)
        features['diff_course_advantage'] = adv_i - adv_j

        # コース番号差（内側ほど有利）
        features['diff_course'] = course_j - course_i  # 負なら艇iが内側

        # 艇iが艇jより内側か
        features['is_inner'] = 1 if course_i < course_j else 0

        # 級別×コースの交互作用
        features['class_x_course_i'] = rank_i * adv_i
        features['class_x_course_j'] = rank_j * adv_j
        features['diff_class_x_course'] = features['class_x_course_i'] - features['class_x_course_j']

        # 絶対値特徴量（艇iの強さ）
        features['abs_win_rate_i'] = boat_i.get('win_rate', 0) or 0
        features['abs_motor_rate_i'] = boat_i.get('motor_second_rate', 0) or 0
        features['abs_score_i'] = boat_i.get('total_score', 50) or 50

        # 艇jの強さ
        features['abs_win_rate_j'] = boat_j.get('win_rate', 0) or 0
        features['abs_motor_rate_j'] = boat_j.get('motor_second_rate', 0) or 0
        features['abs_score_j'] = boat_j.get('total_score', 50) or 50

        # 平均ST差の絶対値（どちらがスタート上手か）
        st_i = boat_i.get('avg_st', 0.15) or 0.15
        st_j = boat_j.get('avg_st', 0.15) or 0.15
        features['diff_st'] = st_j - st_i  # 小さいほど良いSTなので符号反転

        # F/L回数の差
        f_count_i = boat_i.get('f_count', 0) or 0
        f_count_j = boat_j.get('f_count', 0) or 0
        l_count_i = boat_i.get('l_count', 0) or 0
        l_count_j = boat_j.get('l_count', 0) or 0
        features['diff_f_count'] = f_count_j - f_count_i  # 多いほど悪いので符号反転
        features['diff_l_count'] = l_count_j - l_count_i

        return features

    def prepare_training_data(
        self,
        df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, np.ndarray]:
        """
        学習用データを準備

        各レースで全ペア(i, j)を生成し、ラベルは艇iが艇jより上位なら1

        Args:
            df: レースデータ（各艇の特徴量と順位を含む）

        Returns:
            (特徴量DataFrame, ラベル配列)
        """
        # 6艇完備のレースのみ抽出
        race_counts = df.groupby('race_id').size()
        valid_races = race_counts[race_counts == 6].index
        df = df[df['race_id'].isin(valid_races)].copy()

        if len(df) == 0:
            return pd.DataFrame(), np.array([])

        all_features = []
        all_labels = []

        race_ids = df['race_id'].unique()
        self.logger.info(f"ペアワイズデータ生成中: {len(race_ids)}レース")

        for i, race_id in enumerate(race_ids):
            race_df = df[df['race_id'] == race_id]

            if len(race_df) != 6:
                continue

            # 各艇のデータを辞書形式に変換
            boats = []
            for _, row in race_df.iterrows():
                boat = row.to_dict()
                boats.append(boat)

            # 全ペアを生成（15ペア = 6C2 * 2方向）
            for idx_i in range(6):
                for idx_j in range(6):
                    if idx_i == idx_j:
                        continue

                    boat_i = boats[idx_i]
                    boat_j = boats[idx_j]

                    # ペアワイズ特徴量を計算
                    pairwise_features = self._calculate_pairwise_features(boat_i, boat_j)
                    all_features.append(pairwise_features)

                    # ラベル: 艇iが艇jより上位（順位が小さい）なら1
                    rank_i = boat_i.get('rank', 6)
                    rank_j = boat_j.get('rank', 6)
                    label = 1 if rank_i < rank_j else 0
                    all_labels.append(label)

            if (i + 1) % 1000 == 0:
                self.logger.info(f"  進捗: {i + 1}/{len(race_ids)}")

        features_df = pd.DataFrame(all_features)
        labels = np.array(all_labels)

        self.logger.info(f"ペアワイズデータ生成完了: {len(features_df)}件")
        self.logger.info(f"正例率: {labels.mean():.2%}")

        return features_df, labels

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
                'verbose': -1,
                'force_col_wise': True
            }

        # 学習データ準備
        X_train, y_train = self.prepare_training_data(train_df)

        if len(X_train) == 0:
            self.logger.error("学習データが空です")
            return {'error': 'empty_data'}

        self.feature_names = list(X_train.columns)
        self.logger.info(f"学習データ: {len(X_train)}件, 特徴量数: {len(self.feature_names)}")

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
                results['valid_logloss'] = log_loss(y_valid, pred_valid)
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

    def predict_pairwise_probs(
        self,
        race_features: pd.DataFrame
    ) -> np.ndarray:
        """
        レース内の全ペアの勝率を予測

        Args:
            race_features: 6艇の特徴量DataFrame

        Returns:
            6x6のペアワイズ勝率行列（P[i,j] = 艇iが艇jより上位の確率）
        """
        if self.model is None:
            raise ValueError("モデルが学習されていません")

        if len(race_features) != 6:
            raise ValueError("レースは6艇必要です")

        # 各艇のデータを辞書形式に変換
        boats = []
        for _, row in race_features.iterrows():
            boat = row.to_dict()
            boats.append(boat)

        # 全ペアの特徴量を計算
        pairwise_features_list = []
        pair_indices = []

        for i in range(6):
            for j in range(6):
                if i == j:
                    continue

                pairwise_features = self._calculate_pairwise_features(boats[i], boats[j])
                pairwise_features_list.append(pairwise_features)
                pair_indices.append((i, j))

        # 特徴量DataFrameを作成
        features_df = pd.DataFrame(pairwise_features_list)

        # 特徴量を揃える
        for col in self.feature_names:
            if col not in features_df.columns:
                features_df[col] = 0
        features_df = features_df[self.feature_names]

        # 予測
        probs = self.model.predict(features_df)

        # 6x6行列に変換
        prob_matrix = np.zeros((6, 6))
        for (i, j), prob in zip(pair_indices, probs):
            prob_matrix[i, j] = prob

        return prob_matrix

    def predict_ranks(
        self,
        race_features: pd.DataFrame,
        method: str = 'win_count'
    ) -> Dict[int, float]:
        """
        ペアワイズ確率から順位スコアを予測

        Args:
            race_features: 6艇の特徴量DataFrame
            method: 順位復元方法
                - 'win_count': 勝数カウント（デフォルト）
                - 'score_diff': スコア差集計
                - 'copeland': コープランドスコア

        Returns:
            {艇番: スコア}の辞書（スコアが高いほど上位予想）
        """
        prob_matrix = self.predict_pairwise_probs(race_features)
        pit_numbers = race_features['pit_number'].values

        scores = {}

        if method == 'win_count':
            # 方法A: 勝数カウント
            # 各艇について、他の艇に勝つ確率の合計
            for i in range(6):
                win_count = 0
                for j in range(6):
                    if i != j:
                        win_count += prob_matrix[i, j]
                scores[int(pit_numbers[i])] = win_count

        elif method == 'score_diff':
            # 方法B: スコア差集計
            # P(i > j) - P(j > i) の合計
            for i in range(6):
                score = 0
                for j in range(6):
                    if i != j:
                        score += prob_matrix[i, j] - prob_matrix[j, i]
                scores[int(pit_numbers[i])] = score

        elif method == 'copeland':
            # 方法C: コープランドスコア
            # P(i > j) > 0.5 なら勝ち点1、< 0.5 なら負け点-1
            for i in range(6):
                copeland = 0
                for j in range(6):
                    if i != j:
                        if prob_matrix[i, j] > 0.5:
                            copeland += 1
                        elif prob_matrix[i, j] < 0.5:
                            copeland -= 1
                scores[int(pit_numbers[i])] = copeland
        else:
            raise ValueError(f"未知のmethod: {method}")

        return scores

    def predict_rank_order(
        self,
        race_features: pd.DataFrame,
        method: str = 'win_count'
    ) -> List[int]:
        """
        ペアワイズ確率から順位順序を予測

        Args:
            race_features: 6艇の特徴量DataFrame
            method: 順位復元方法

        Returns:
            艇番のリスト（1位から6位の順）
        """
        scores = self.predict_ranks(race_features, method)

        # スコアの降順でソート
        sorted_boats = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        return [pit for pit, _ in sorted_boats]

    def get_second_place_probs(
        self,
        race_features: pd.DataFrame,
        predicted_first: int
    ) -> Dict[int, float]:
        """
        1着が確定した条件下での2着確率を計算

        Args:
            race_features: 6艇の特徴量DataFrame
            predicted_first: 予測1着の艇番

        Returns:
            {艇番: 2着確率}の辞書
        """
        prob_matrix = self.predict_pairwise_probs(race_features)
        pit_numbers = race_features['pit_number'].values

        # 予測1着のインデックスを取得
        first_idx = np.where(pit_numbers == predicted_first)[0]
        if len(first_idx) == 0:
            return {}
        first_idx = first_idx[0]

        # 残り5艇の2着確率を計算
        # 2着になるためには、1着艇以外の4艇に勝つ必要がある
        second_probs = {}

        for i in range(6):
            if i == first_idx:
                continue

            pit = int(pit_numbers[i])

            # 艇iが残りの4艇に勝つ確率の積（簡略化）
            # より正確には、2位になる確率は複雑な積分になるが、
            # ここでは「他の艇に勝つ確率の合計」を近似として使用
            win_sum = 0
            for j in range(6):
                if j != i and j != first_idx:
                    win_sum += prob_matrix[i, j]

            second_probs[pit] = win_sum

        # 正規化
        total = sum(second_probs.values())
        if total > 0:
            second_probs = {k: v / total for k, v in second_probs.items()}

        return second_probs

    def get_third_place_probs(
        self,
        race_features: pd.DataFrame,
        predicted_first: int,
        predicted_second: int
    ) -> Dict[int, float]:
        """
        1着・2着が確定した条件下での3着確率を計算

        Args:
            race_features: 6艇の特徴量DataFrame
            predicted_first: 予測1着の艇番
            predicted_second: 予測2着の艇番

        Returns:
            {艇番: 3着確率}の辞書
        """
        prob_matrix = self.predict_pairwise_probs(race_features)
        pit_numbers = race_features['pit_number'].values

        # 予測1着・2着のインデックスを取得
        first_idx = np.where(pit_numbers == predicted_first)[0]
        second_idx = np.where(pit_numbers == predicted_second)[0]

        if len(first_idx) == 0 or len(second_idx) == 0:
            return {}

        first_idx = first_idx[0]
        second_idx = second_idx[0]

        # 残り4艇の3着確率を計算
        third_probs = {}

        for i in range(6):
            if i == first_idx or i == second_idx:
                continue

            pit = int(pit_numbers[i])

            # 艇iが残りの3艇に勝つ確率の合計
            win_sum = 0
            for j in range(6):
                if j != i and j != first_idx and j != second_idx:
                    win_sum += prob_matrix[i, j]

            third_probs[pit] = win_sum

        # 正規化
        total = sum(third_probs.values())
        if total > 0:
            third_probs = {k: v / total for k, v in third_probs.items()}

        return third_probs

    def save(self, name: str = 'pairwise_rank'):
        """モデルを保存"""
        os.makedirs(self.model_dir, exist_ok=True)

        if self.model is not None:
            model_path = os.path.join(self.model_dir, f'{name}.txt')
            self.model.save_model(model_path)

        # メタ情報を保存
        meta = {
            'feature_names': self.feature_names,
            'diff_features': self.diff_features,
            'course_advantage': self.course_advantage,
            'rank_values': self.rank_values,
            'created_at': datetime.now().isoformat()
        }
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        self.logger.info(f"モデルを {self.model_dir} に保存しました")

    def load(self, name: str = 'pairwise_rank'):
        """モデルを読み込み"""
        model_path = os.path.join(self.model_dir, f'{name}.txt')
        meta_path = os.path.join(self.model_dir, f'{name}_meta.json')

        if os.path.exists(model_path):
            self.model = lgb.Booster(model_file=model_path)

        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            self.feature_names = meta.get('feature_names', [])
            self.diff_features = meta.get('diff_features', self.diff_features)
            self.course_advantage = meta.get('course_advantage', self.course_advantage)
            self.rank_values = meta.get('rank_values', self.rank_values)

        self.logger.info(f"モデルを {self.model_dir} から読み込みました")


class PairwiseScoreIntegrator:
    """
    ペアワイズスコアの統合器

    既存の絶対スコア予測とペアワイズ予測を統合する。
    """

    def __init__(
        self,
        pairwise_model: PairwiseRankModel = None,
        integration_weight: float = 0.5
    ):
        """
        Args:
            pairwise_model: ペアワイズモデル
            integration_weight: 統合重み（ペアワイズモデルの重み、0.0-1.0）
        """
        self.pairwise_model = pairwise_model
        self.integration_weight = integration_weight
        self.logger = logging.getLogger(__name__)

    def integrate_predictions(
        self,
        predictions: List[Dict],
        race_features: pd.DataFrame
    ) -> List[Dict]:
        """
        既存の予測結果にペアワイズスコアを統合

        Args:
            predictions: 予測結果リスト（スコア順にソート済み）
            race_features: レース特徴量

        Returns:
            統合後の予測結果
        """
        if self.pairwise_model is None or self.pairwise_model.model is None:
            return predictions

        if len(predictions) != 6 or len(race_features) != 6:
            return predictions

        try:
            # レース特徴量にtotal_scoreを追加
            for pred in predictions:
                pit = pred['pit_number']
                idx = race_features[race_features['pit_number'] == pit].index
                if len(idx) > 0:
                    race_features.loc[idx[0], 'total_score'] = pred['total_score']

            # ペアワイズスコアを計算
            pairwise_scores = self.pairwise_model.predict_ranks(
                race_features, method='win_count'
            )

            # スコアを0-100に正規化
            min_score = min(pairwise_scores.values())
            max_score = max(pairwise_scores.values())
            score_range = max_score - min_score

            if score_range > 0:
                pairwise_scores_normalized = {
                    pit: (score - min_score) / score_range * 100
                    for pit, score in pairwise_scores.items()
                }
            else:
                pairwise_scores_normalized = {pit: 50 for pit in pairwise_scores}

            # 統合スコアを計算
            gamma = 1 - self.integration_weight  # 絶対スコアの重み

            for pred in predictions:
                pit = pred['pit_number']
                absolute_score = pred['total_score']
                pairwise_score = pairwise_scores_normalized.get(pit, 50)

                # 統合スコア
                integrated_score = gamma * absolute_score + self.integration_weight * pairwise_score

                pred['pairwise_score'] = round(pairwise_score, 1)
                pred['original_total_score'] = pred['total_score']
                pred['total_score'] = round(integrated_score, 1)
                pred['pairwise_integrated'] = True

            # スコア順に再ソート
            predictions.sort(key=lambda x: x['total_score'], reverse=True)

            # 順位を再付与
            for rank, pred in enumerate(predictions, 1):
                pred['rank_prediction'] = rank

        except Exception as e:
            self.logger.warning(f"ペアワイズスコア統合エラー: {e}")

        return predictions

    def get_enhanced_second_probs(
        self,
        predictions: List[Dict],
        race_features: pd.DataFrame,
        existing_second_probs: Dict[int, float] = None
    ) -> Dict[int, float]:
        """
        ペアワイズモデルで2着確率を強化

        Args:
            predictions: 予測結果リスト
            race_features: レース特徴量
            existing_second_probs: 既存の2着確率

        Returns:
            強化された2着確率
        """
        if self.pairwise_model is None or self.pairwise_model.model is None:
            return existing_second_probs or {}

        if len(predictions) == 0:
            return existing_second_probs or {}

        predicted_first = predictions[0]['pit_number']

        try:
            # ペアワイズモデルから2着確率を取得
            pairwise_second_probs = self.pairwise_model.get_second_place_probs(
                race_features, predicted_first
            )

            if not existing_second_probs:
                return pairwise_second_probs

            # 既存確率とペアワイズ確率を統合
            integrated = {}
            all_pits = set(existing_second_probs.keys()) | set(pairwise_second_probs.keys())

            for pit in all_pits:
                existing = existing_second_probs.get(pit, 0)
                pairwise = pairwise_second_probs.get(pit, 0)

                integrated[pit] = (
                    (1 - self.integration_weight) * existing +
                    self.integration_weight * pairwise
                )

            # 正規化
            total = sum(integrated.values())
            if total > 0:
                integrated = {k: v / total for k, v in integrated.items()}

            return integrated

        except Exception as e:
            self.logger.warning(f"2着確率強化エラー: {e}")
            return existing_second_probs or {}


# データ準備用ヘルパー関数
def prepare_training_dataset(
    db_path: str,
    start_date: str,
    end_date: str
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
        e.motor_third_rate,
        e.boat_second_rate,
        e.boat_third_rate,
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

    # 総合スコアを簡易計算
    df['total_score'] = (
        df['win_rate'].fillna(0) * 8 +
        df['motor_second_rate'].fillna(0) * 0.3 +
        df['pit_number'].map({1: 15, 2: 5, 3: 3, 4: 2, 5: 1, 6: 0}).fillna(0)
    )

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
    logger.info("=== ペアワイズ順位予測モデル テスト ===")

    # データ準備
    db_path = 'data/boatrace.db'

    if os.path.exists(db_path):
        logger.info("学習データを準備中...")
        train_df = prepare_training_dataset(db_path, '2024-01-01', '2024-10-31')
        valid_df = prepare_training_dataset(db_path, '2024-11-01', '2024-12-31')

        logger.info(f"学習データ: {len(train_df)}件, 検証データ: {len(valid_df)}件")

        # モデル学習
        model = PairwiseRankModel(db_path=db_path)
        results = model.train(train_df, valid_df)

        logger.info(f"学習結果: {results}")

        # モデル保存
        model.save()

        logger.info("=== テスト完了 ===")
    else:
        logger.warning(f"データベースが見つかりません: {db_path}")
