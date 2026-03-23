"""
ペアワイズ相対スコアリングモデル

アプローチ3: 艇間の直接対決確率をモデル化して順位を予測

理論的根拠:
- 現在のモデルは各艇の絶対スコアを計算するが、実際のレースは相対的な強さで決まる
- 艇1が艇2に勝つ確率: P(1 > 2) を直接モデル化
- 全ペアの勝率から最終順位を復元することで、より精度の高い予測が可能

特徴:
- ペアワイズ特徴量: スコア差、級別差、ST差、勝率差などの相対特徴量
- LightGBM二値分類: 艇iが艇jより上位かを予測
- 順位復元: 全ペアの勝率から勝数カウントまたはスコア集計で順位決定

期待効果: 2着・3着的中率 +2pt以上
"""

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, accuracy_score
from typing import Dict, List, Tuple, Optional
import json
import os
from datetime import datetime
import logging
from itertools import combinations


class PairwiseRankModel:
    """
    ペアワイズ順位予測モデル

    各艇ペア(i, j)に対して「艇iが艇jより上位になる確率」を予測し、
    全ペアの確率から最終順位を復元する。
    """

    # 級別の数値マッピング
    RANK_VALUES = {
        'A1': 4,
        'A2': 3,
        'B1': 2,
        'B2': 1
    }

    # コース別基準勝率（全国平均）
    COURSE_WIN_RATES = {
        1: 0.55,
        2: 0.15,
        3: 0.12,
        4: 0.10,
        5: 0.05,
        6: 0.03
    }

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
        self.pairwise_features = [
            # スコア差
            'score_diff',           # 総合スコア差（i - j）
            'win_rate_diff',        # 勝率差
            'second_rate_diff',     # 2連対率差
            # 級別差
            'class_diff',           # 級別差（A1=4, A2=3, B1=2, B2=1）
            # ST・展示差
            'avg_st_diff',          # 平均ST差
            'exhibition_diff',      # 展示タイム差
            # モーター・ボート差
            'motor_2rate_diff',     # モーター2連対率差
            'boat_2rate_diff',      # ボート2連対率差
            # コース特徴量
            'course_diff',          # コース差（i - j）
            'course_advantage',     # コース有利度差
            'is_inner',             # iがjより内側か
            # 絶対値特徴量
            'i_score',              # 艇iのスコア
            'j_score',              # 艇jのスコア
            'i_course',             # 艇iのコース
            'j_course',             # 艇jのコース
            'i_class',              # 艇iの級別
            'j_class',              # 艇jの級別
            # 直近成績差
            'recent_form_diff',     # 直近成績差
            # 当節成績差
            'current_term_diff',    # 当節成績差
        ]

    def _get_class_value(self, rank_str: str) -> int:
        """級別を数値に変換"""
        if pd.isna(rank_str) or rank_str == '':
            return 1  # デフォルトB2
        return self.RANK_VALUES.get(str(rank_str).upper(), 1)

    def _get_course_advantage(self, course: int) -> float:
        """コース有利度を取得（内側ほど高い）"""
        return self.COURSE_WIN_RATES.get(course, 0.1)

    def prepare_pairwise_data(
        self,
        df: pd.DataFrame,
        include_labels: bool = True
    ) -> Tuple[pd.DataFrame, Optional[np.ndarray]]:
        """
        ペアワイズ特徴量データを準備

        各レースで6艇から15ペアを生成し、
        各ペアに対して相対特徴量を計算する。

        Args:
            df: レースデータ（各艇の特徴量を含む）
            include_labels: ラベル（順位比較結果）を含めるか

        Returns:
            (ペアワイズ特徴量DataFrame, ラベル配列)
        """
        # 6艇完備のレースのみ抽出
        race_counts = df.groupby('race_id').size()
        valid_races = race_counts[race_counts == 6].index
        df = df[df['race_id'].isin(valid_races)].copy()

        if len(df) == 0:
            return pd.DataFrame(), np.array([]) if include_labels else None

        # スコア列の準備（なければ勝率ベースで計算）
        if 'total_score' not in df.columns:
            df['total_score'] = df['win_rate'] * 10 + df.get('motor_second_rate', 0) * 0.5

        # 級別の数値変換
        if 'racer_rank' in df.columns:
            df['class_value'] = df['racer_rank'].apply(self._get_class_value)
        else:
            df['class_value'] = 2  # デフォルトB1

        # コース有利度
        df['course_advantage'] = df['pit_number'].apply(self._get_course_advantage)

        # ペアワイズデータの生成
        pairs_data = []
        labels = [] if include_labels else None

        race_ids = df['race_id'].unique()

        for race_id in race_ids:
            race_df = df[df['race_id'] == race_id].reset_index(drop=True)

            if len(race_df) != 6:
                continue

            # 全ペア（15通り）を生成
            for i, j in combinations(range(6), 2):
                boat_i = race_df.iloc[i]
                boat_j = race_df.iloc[j]

                pair_features = self._calculate_pair_features(boat_i, boat_j)
                pair_features['race_id'] = race_id
                pair_features['boat_i_pit'] = int(boat_i['pit_number'])
                pair_features['boat_j_pit'] = int(boat_j['pit_number'])
                pairs_data.append(pair_features)

                if include_labels and 'rank' in df.columns:
                    # ラベル: 艇iが艇jより上位なら1、そうでなければ0
                    label = 1 if boat_i['rank'] < boat_j['rank'] else 0
                    labels.append(label)

        pairs_df = pd.DataFrame(pairs_data)

        # 特徴量列のみ抽出
        feature_cols = [c for c in pairs_df.columns
                       if c not in ['race_id', 'boat_i_pit', 'boat_j_pit']]

        X = pairs_df[feature_cols]
        self.feature_names = list(X.columns)

        if include_labels:
            y = np.array(labels)
            return X, y
        else:
            return pairs_df, None

    def _calculate_pair_features(
        self,
        boat_i: pd.Series,
        boat_j: pd.Series
    ) -> Dict[str, float]:
        """
        艇ペアの相対特徴量を計算

        Args:
            boat_i: 艇iのデータ
            boat_j: 艇jのデータ

        Returns:
            ペアワイズ特徴量の辞書
        """
        features = {}

        # スコア差
        features['score_diff'] = float(
            boat_i.get('total_score', 50) - boat_j.get('total_score', 50)
        )

        # 勝率差
        features['win_rate_diff'] = float(
            boat_i.get('win_rate', 0) - boat_j.get('win_rate', 0)
        )

        # 2連対率差
        features['second_rate_diff'] = float(
            boat_i.get('second_rate', 0) - boat_j.get('second_rate', 0)
        )

        # 級別差
        i_class = self._get_class_value(boat_i.get('racer_rank', 'B1'))
        j_class = self._get_class_value(boat_j.get('racer_rank', 'B1'))
        features['class_diff'] = float(i_class - j_class)

        # ST差
        features['avg_st_diff'] = float(
            boat_i.get('avg_st', 0.15) - boat_j.get('avg_st', 0.15)
        )

        # 展示タイム差（小さい方が速い）
        i_exhibition = boat_i.get('exhibition_time', 6.8)
        j_exhibition = boat_j.get('exhibition_time', 6.8)
        features['exhibition_diff'] = float(
            j_exhibition - i_exhibition  # jの方が大きい（遅い）ならiが有利
        )

        # モーター2連対率差
        features['motor_2rate_diff'] = float(
            boat_i.get('motor_second_rate', 30) - boat_j.get('motor_second_rate', 30)
        )

        # ボート2連対率差
        features['boat_2rate_diff'] = float(
            boat_i.get('boat_second_rate', 30) - boat_j.get('boat_second_rate', 30)
        )

        # コース差
        i_course = int(boat_i.get('pit_number', 3))
        j_course = int(boat_j.get('pit_number', 3))
        features['course_diff'] = float(i_course - j_course)

        # コース有利度差
        i_course_adv = self._get_course_advantage(i_course)
        j_course_adv = self._get_course_advantage(j_course)
        features['course_advantage'] = float(i_course_adv - j_course_adv)

        # iがjより内側か
        features['is_inner'] = 1.0 if i_course < j_course else 0.0

        # 絶対値特徴量
        features['i_score'] = float(boat_i.get('total_score', 50))
        features['j_score'] = float(boat_j.get('total_score', 50))
        features['i_course'] = float(i_course)
        features['j_course'] = float(j_course)
        features['i_class'] = float(i_class)
        features['j_class'] = float(j_class)

        # 直近成績差（あれば）
        i_recent = boat_i.get('recent_win_rate', boat_i.get('win_rate', 0))
        j_recent = boat_j.get('recent_win_rate', boat_j.get('win_rate', 0))
        features['recent_form_diff'] = float(i_recent - j_recent)

        # 当節成績差（あれば）
        i_term = boat_i.get('term_win_rate', 0)
        j_term = boat_j.get('term_win_rate', 0)
        features['current_term_diff'] = float(i_term - j_term)

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
        X_train, y_train = self.prepare_pairwise_data(train_df, include_labels=True)

        if len(X_train) == 0:
            self.logger.error("学習データが空です")
            return {'error': 'empty_data'}

        self.logger.info(f"学習データ: {len(X_train)}ペア, 特徴量数: {len(self.feature_names)}")
        self.logger.info(f"正例率: {y_train.mean():.2%}")

        # LightGBMデータセット
        train_data = lgb.Dataset(X_train, label=y_train)

        results = {}

        if valid_df is not None:
            X_valid, y_valid = self.prepare_pairwise_data(valid_df, include_labels=True)
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
                accuracy = accuracy_score(y_valid, (pred_valid > 0.5).astype(int))
                results['valid_auc'] = auc
                results['valid_accuracy'] = accuracy
                self.logger.info(f"検証AUC: {auc:.4f}, 精度: {accuracy:.4f}")
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
    ) -> Dict[Tuple[int, int], float]:
        """
        全ペアの勝率P(i > j)を予測

        Args:
            race_features: 6艇の特徴量

        Returns:
            {(pit_i, pit_j): P(i > j)} の辞書
        """
        if self.model is None:
            raise ValueError("モデルが学習されていません")

        if len(race_features) != 6:
            raise ValueError("6艇のデータが必要です")

        race_features = race_features.reset_index(drop=True)

        # スコア列の準備
        if 'total_score' not in race_features.columns:
            race_features = race_features.copy()
            race_features['total_score'] = (
                race_features['win_rate'] * 10 +
                race_features.get('motor_second_rate', pd.Series([0]*6)) * 0.5
            )

        # ペアワイズ特徴量を計算
        pairs_data = []
        pair_indices = []

        for i, j in combinations(range(6), 2):
            boat_i = race_features.iloc[i]
            boat_j = race_features.iloc[j]

            pair_features = self._calculate_pair_features(boat_i, boat_j)
            pairs_data.append(pair_features)

            pit_i = int(boat_i['pit_number'])
            pit_j = int(boat_j['pit_number'])
            pair_indices.append((pit_i, pit_j))

        # 予測
        pairs_df = pd.DataFrame(pairs_data)

        # 特徴量を揃える
        for col in self.feature_names:
            if col not in pairs_df.columns:
                pairs_df[col] = 0
        pairs_df = pairs_df[self.feature_names]

        probs = self.model.predict(pairs_df)

        # 結果を辞書に格納
        pairwise_probs = {}
        for (pit_i, pit_j), prob in zip(pair_indices, probs):
            pairwise_probs[(pit_i, pit_j)] = float(prob)
            # 逆方向も計算（P(j > i) = 1 - P(i > j)）
            pairwise_probs[(pit_j, pit_i)] = 1.0 - float(prob)

        return pairwise_probs

    def reconstruct_rankings(
        self,
        pairwise_probs: Dict[Tuple[int, int], float],
        method: str = 'win_count'
    ) -> Dict[int, float]:
        """
        ペアワイズ確率から順位スコアを復元

        Args:
            pairwise_probs: {(pit_i, pit_j): P(i > j)}
            method: 復元方法
                - 'win_count': 期待勝数（デフォルト）
                - 'score_diff': スコア集計

        Returns:
            {艇番: 順位スコア} の辞書（スコアが高いほど上位）
        """
        # 全艇番を取得
        all_pits = set()
        for pit_i, pit_j in pairwise_probs.keys():
            all_pits.add(pit_i)
            all_pits.add(pit_j)

        scores = {}

        if method == 'win_count':
            # 方法A: 期待勝数カウント
            for pit_i in all_pits:
                win_count = 0.0
                for pit_j in all_pits:
                    if pit_j != pit_i:
                        win_count += pairwise_probs.get((pit_i, pit_j), 0.5)
                scores[pit_i] = win_count

        elif method == 'score_diff':
            # 方法B: スコア差分集計
            for pit_i in all_pits:
                score = 0.0
                for pit_j in all_pits:
                    if pit_j != pit_i:
                        p_ij = pairwise_probs.get((pit_i, pit_j), 0.5)
                        p_ji = pairwise_probs.get((pit_j, pit_i), 0.5)
                        score += p_ij - p_ji
                scores[pit_i] = score
        else:
            raise ValueError(f"Unknown method: {method}")

        return scores

    def predict_rankings(
        self,
        race_features: pd.DataFrame,
        method: str = 'win_count'
    ) -> List[Dict]:
        """
        順位予測を実行

        Args:
            race_features: 6艇の特徴量
            method: 順位復元方法

        Returns:
            予測順位付きの艇データリスト
        """
        # ペアワイズ確率を予測
        pairwise_probs = self.predict_pairwise_probs(race_features)

        # 順位スコアを復元
        rank_scores = self.reconstruct_rankings(pairwise_probs, method=method)

        # 結果を整形
        results = []
        race_features = race_features.reset_index(drop=True)

        for i in range(len(race_features)):
            boat = race_features.iloc[i]
            pit = int(boat['pit_number'])

            results.append({
                'pit_number': pit,
                'pairwise_score': rank_scores.get(pit, 0.0),
                'total_score': boat.get('total_score', 50.0),
                'win_rate': boat.get('win_rate', 0),
                'racer_rank': boat.get('racer_rank', 'B1')
            })

        # ペアワイズスコアで降順ソート
        results.sort(key=lambda x: x['pairwise_score'], reverse=True)

        # 予測順位を付与
        for rank, r in enumerate(results, 1):
            r['pairwise_rank'] = rank

        return results

    def get_pairwise_adjusted_predictions(
        self,
        predictions: List[Dict],
        race_features: pd.DataFrame,
        gamma: float = 0.5
    ) -> List[Dict]:
        """
        既存の予測結果をペアワイズスコアで調整

        Args:
            predictions: 既存の予測結果（total_score含む）
            race_features: レース特徴量
            gamma: 統合重み（0.0-1.0）
                   1.0: 完全に絶対スコア
                   0.0: 完全にペアワイズスコア

        Returns:
            調整後の予測結果
        """
        if self.model is None:
            # モデルがない場合は元の予測をそのまま返す
            return predictions

        try:
            # ペアワイズ予測を実行
            pairwise_results = self.predict_rankings(race_features)

            # ペアワイズスコアを辞書に変換
            pairwise_scores = {
                r['pit_number']: r['pairwise_score']
                for r in pairwise_results
            }

            # スコアを正規化（0-100スケール）
            max_pw = max(pairwise_scores.values()) if pairwise_scores else 1
            min_pw = min(pairwise_scores.values()) if pairwise_scores else 0
            pw_range = max_pw - min_pw if max_pw != min_pw else 1

            normalized_pairwise = {
                pit: ((score - min_pw) / pw_range) * 100
                for pit, score in pairwise_scores.items()
            }

            # 予測結果を調整
            for pred in predictions:
                pit = pred['pit_number']
                abs_score = pred.get('total_score', 50)
                pw_score = normalized_pairwise.get(pit, 50)

                # 統合スコア
                integrated_score = gamma * abs_score + (1 - gamma) * pw_score

                # 情報を追加
                pred['pairwise_score'] = round(pw_score, 2)
                pred['integrated_score'] = round(integrated_score, 2)
                pred['pairwise_adjusted'] = True

            # 統合スコアで再ソート
            predictions.sort(key=lambda x: x.get('integrated_score', 0), reverse=True)

            # 予測順位を更新
            for rank, pred in enumerate(predictions, 1):
                pred['rank_prediction'] = rank

        except Exception as e:
            self.logger.warning(f"ペアワイズ調整エラー: {e}")
            # エラー時は元の予測を維持
            for pred in predictions:
                pred['pairwise_adjusted'] = False

        return predictions

    def save(self, name: str = 'pairwise_rank'):
        """モデルを保存"""
        os.makedirs(self.model_dir, exist_ok=True)

        if self.model is not None:
            model_path = os.path.join(self.model_dir, f'{name}.txt')
            self.model.save_model(model_path)

        # メタ情報を保存
        meta = {
            'feature_names': self.feature_names,
            'pairwise_features': self.pairwise_features,
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
            self.pairwise_features = meta.get('pairwise_features', [])

        self.logger.info(f"モデルを {self.model_dir} から読み込みました")


class PairwiseScoreIntegrator:
    """
    ペアワイズスコアの統合器

    既存の予測システムとペアワイズ予測を統合する。
    """

    def __init__(
        self,
        pairwise_model: PairwiseRankModel = None,
        integration_weight: float = 0.5
    ):
        """
        Args:
            pairwise_model: ペアワイズモデル
            integration_weight: ペアワイズスコアの重み（0.0-1.0）
        """
        self.pairwise_model = pairwise_model
        self.integration_weight = integration_weight
        self.logger = logging.getLogger(__name__)

    def integrate_predictions(
        self,
        predictions: List[Dict],
        race_features: pd.DataFrame,
        method: str = 'win_count'
    ) -> List[Dict]:
        """
        予測結果にペアワイズスコアを統合

        Args:
            predictions: 元の予測結果
            race_features: レース特徴量
            method: 順位復元方法

        Returns:
            統合後の予測結果
        """
        if self.pairwise_model is None or self.pairwise_model.model is None:
            return predictions

        # gamma = 1 - integration_weight で統合
        # integration_weight が大きいほどペアワイズスコアの影響が大きい
        gamma = 1.0 - self.integration_weight

        return self.pairwise_model.get_pairwise_adjusted_predictions(
            predictions,
            race_features,
            gamma=gamma
        )

    def get_second_place_probs(
        self,
        predictions: List[Dict],
        race_features: pd.DataFrame
    ) -> Dict[int, float]:
        """
        ペアワイズ確率から2着確率を計算

        1着候補を除いた5艇で、各艇が2着になる確率を計算

        Args:
            predictions: 予測結果（1位が1着候補）
            race_features: レース特徴量

        Returns:
            {艇番: 2着確率} の辞書
        """
        if self.pairwise_model is None or self.pairwise_model.model is None:
            return {}

        if len(predictions) == 0:
            return {}

        try:
            # ペアワイズ確率を取得
            pairwise_probs = self.pairwise_model.predict_pairwise_probs(race_features)

            # 1着候補
            first_pit = predictions[0]['pit_number']

            # 残り5艇の2着確率を計算
            remaining_pits = [p['pit_number'] for p in predictions[1:]]

            second_probs = {}
            for pit in remaining_pits:
                # この艇が他の4艇（1着候補以外）全てに勝つ確率の積
                prob = 1.0
                for other_pit in remaining_pits:
                    if other_pit != pit:
                        prob *= pairwise_probs.get((pit, other_pit), 0.5)
                second_probs[pit] = prob

            # 正規化
            total = sum(second_probs.values())
            if total > 0:
                second_probs = {k: v / total for k, v in second_probs.items()}

            return second_probs

        except Exception as e:
            self.logger.warning(f"2着確率計算エラー: {e}")
            return {}

    def get_third_place_probs(
        self,
        predictions: List[Dict],
        race_features: pd.DataFrame,
        predicted_second: int
    ) -> Dict[int, float]:
        """
        ペアワイズ確率から3着確率を計算

        1着・2着候補を除いた4艇で、各艇が3着になる確率を計算

        Args:
            predictions: 予測結果
            race_features: レース特徴量
            predicted_second: 予測2着の艇番

        Returns:
            {艇番: 3着確率} の辞書
        """
        if self.pairwise_model is None or self.pairwise_model.model is None:
            return {}

        if len(predictions) < 3:
            return {}

        try:
            # ペアワイズ確率を取得
            pairwise_probs = self.pairwise_model.predict_pairwise_probs(race_features)

            # 1着・2着候補
            first_pit = predictions[0]['pit_number']
            excluded = {first_pit, predicted_second}

            # 残り4艇の3着確率を計算
            remaining_pits = [
                p['pit_number'] for p in predictions
                if p['pit_number'] not in excluded
            ]

            third_probs = {}
            for pit in remaining_pits:
                # この艇が他の3艇全てに勝つ確率の積
                prob = 1.0
                for other_pit in remaining_pits:
                    if other_pit != pit:
                        prob *= pairwise_probs.get((pit, other_pit), 0.5)
                third_probs[pit] = prob

            # 正規化
            total = sum(third_probs.values())
            if total > 0:
                third_probs = {k: v / total for k, v in third_probs.items()}

            return third_probs

        except Exception as e:
            self.logger.warning(f"3着確率計算エラー: {e}")
            return {}


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

    # race_predictionsから実際のtotal_scoreを取得（推論時と同スケールにする）
    score_query = """
    SELECT race_id, pit_number, total_score
    FROM race_predictions
    WHERE prediction_type = 'before'
    """
    try:
        score_df = pd.read_sql_query(score_query, conn)
        df = df.merge(score_df, on=['race_id', 'pit_number'], how='left')
        # 取得できなかった行のみ簡易計算でフォールバック
        missing = df['total_score'].isna()
        df.loc[missing, 'total_score'] = (
            df.loc[missing, 'win_rate'] * 10 + df.loc[missing, 'motor_second_rate'] * 0.5
        )
    except Exception:
        # race_predictionsが使えない場合は簡易計算
        df['total_score'] = df['win_rate'] * 10 + df['motor_second_rate'] * 0.5

    conn.close()

    # rankを整数に変換
    df['rank'] = df['rank'].astype(int)

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
    logger.info("=== ペアワイズ相対スコアリングモデル テスト ===")

    # データ準備
    db_path = 'data/boatrace.db'

    logger.info("学習データを準備中...")
    train_df = prepare_training_dataset(db_path, '2024-01-01', '2024-10-31')
    valid_df = prepare_training_dataset(db_path, '2024-11-01', '2024-12-31')

    logger.info(f"学習データ: {len(train_df)}件, 検証データ: {len(valid_df)}件")

    # モデル学習
    model = PairwiseRankModel(db_path=db_path)
    results = model.train(train_df, valid_df)

    logger.info(f"学習結果: AUC={results.get('valid_auc', 0):.4f}")

    # モデル保存
    model.save()

    logger.info("=== テスト完了 ===")
