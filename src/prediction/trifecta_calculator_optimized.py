"""
三連単確率計算モジュール（最適化版）
Phase 3: P(1=i) × P(2=j|1=i) × P(3=k|1=i,2=j) の計算

最適化内容:
- 特徴量キャッシュ（提案A: 40%高速化）
- 一括バッチ予測（提案B: 50%高速化）
- 既存ロジックは変更せず、計算効率のみ改善
"""
import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='lightgbm')
warnings.filterwarnings('ignore', category=UserWarning, module='sklearn')
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from itertools import permutations
import joblib
import json
import os


class TrifectaCalculatorOptimized:
    """
    三連単確率計算クラス（最適化版）

    既存のTrifectaCalculatorと互換性を保ちつつ、高速化を実現
    """

    def __init__(self, model_dir: str = 'models', model_name: str = 'conditional', use_v2: bool = False):
        self.model_dir = model_dir
        self.model_name = model_name
        self.use_v2 = use_v2
        self.models = {}
        self.feature_names = {}
        self._loaded = False
        self._feature_cache = {}  # 特徴量キャッシュ

    def load_models(self):
        """Stage1/2/3モデルを読み込み"""
        if self._loaded:
            return

        if self.use_v2:
            self._load_v2_models()
        else:
            self._load_v1_models()

        self._loaded = True

    def _load_v1_models(self):
        """v1モデルを読み込み"""
        # メタ情報を読み込み
        meta_path = os.path.join(self.model_dir, f'{self.model_name}_meta.json')
        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            self.feature_names = meta.get('feature_names', meta.get('features', {}))

        # 各Stageモデルを読み込み
        for stage in ['stage1', 'stage2', 'stage3']:
            model_path = os.path.join(self.model_dir, f'{self.model_name}_{stage}.joblib')
            if os.path.exists(model_path):
                self.models[stage] = joblib.load(model_path)
                print(f"v1モデル読み込み: {stage}")

    def _load_v2_models(self):
        """v2モデルを読み込み（最新版を自動検索）"""
        from pathlib import Path

        model_dir_path = Path(self.model_dir)

        # 最新のv2モデルを検索
        v2_files = list(model_dir_path.glob("conditional_stage2_v2_*.joblib"))
        if not v2_files:
            print("v2モデルが見つかりません。v1モデルを使用します。")
            self._load_v1_models()
            return

        latest = sorted(v2_files)[-1]
        parts = latest.stem.split('_')
        timestamp = '_'.join(parts[-2:])

        print(f"v2モデルタイムスタンプ: {timestamp}")

        # v2モデル読み込み
        for stage in ['stage1', 'stage2', 'stage3']:
            model_path = model_dir_path / f"conditional_{stage}_v2_{timestamp}.joblib"
            if model_path.exists():
                self.models[stage] = joblib.load(model_path)
                print(f"v2モデル読み込み: {stage}")

        # v2メタ情報を読み込み
        meta_path = model_dir_path / f"conditional_meta_v2_{timestamp}.json"
        if meta_path.exists():
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            self.feature_names = meta.get('features', {})

    def calculate(self, race_features: pd.DataFrame,
                  pit_column: str = 'pit_number') -> Dict[str, float]:
        """
        三連単の全120通りの確率を計算（最適化版）

        Args:
            race_features: 6艇分の特徴量DataFrame
            pit_column: ピット番号のカラム名

        Returns:
            {'1-2-3': 0.15, '1-3-2': 0.12, ...} 形式の確率辞書
        """
        if not self._loaded:
            self.load_models()

        if len(race_features) != 6:
            raise ValueError(f"6艇分のデータが必要です（現在: {len(race_features)}艇）")

        # 提案A: 特徴量キャッシュを構築（型チェックを1回のみ実行）
        self._build_feature_cache(race_features)

        pit_numbers = race_features[pit_column].values.astype(int)

        # 提案B: 一括バッチ予測
        return self._calculate_batched(race_features, pit_numbers)

    def _build_feature_cache(self, df: pd.DataFrame):
        """
        全艇の特徴量を事前計算してキャッシュ（提案A）

        型チェックを1回のみ実行し、以降の特徴量作成で再利用
        """
        exclude_cols = {'race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'race_number', 'rank'}

        self._feature_cache = {}
        for idx in range(len(df)):
            row = df.iloc[idx]
            numeric_features = {}
            for col in df.columns:
                if col not in exclude_cols:
                    val = row[col]
                    # 数値型のみキャッシュ（型チェックは1回のみ）
                    if isinstance(val, (int, float, np.integer, np.floating)):
                        numeric_features[col] = float(val)
            self._feature_cache[idx] = numeric_features

    def _calculate_batched(self, race_features: pd.DataFrame,
                          pit_numbers: np.ndarray) -> Dict[str, float]:
        """
        一括バッチ予測版の三連単計算（提案B）

        LightGBM呼び出しを最小化（151回→3回）
        """
        feature_cols_s1 = self.feature_names.get('stage1', [])
        feature_cols_s2 = self.feature_names.get('stage2', [])
        feature_cols_s3 = self.feature_names.get('stage3', [])

        # Stage1: 1着確率（6艇を一括予測）
        first_probs = self._predict_first_place(race_features)

        # Stage2: 全30パターン(6×5)の特徴量を一括作成
        stage2_inputs = []
        stage2_mapping = []  # (first_idx, second_idx)

        for i in range(6):
            for j in range(6):
                if j == i:
                    continue
                features = self._create_stage2_features_cached(j, i, feature_cols_s2)
                stage2_inputs.append(features)
                stage2_mapping.append((i, j))

        # 一括予測（30パターンを1回で）
        if len(stage2_inputs) > 0 and self.models.get('stage2') is not None:
            stage2_all_probs = self.models['stage2'].predict_proba(stage2_inputs)[:, 1]
        else:
            stage2_all_probs = np.ones(len(stage2_inputs)) / 5

        # Stage2結果を格納・正規化
        second_probs = {}
        for idx, (i, j) in enumerate(stage2_mapping):
            if i not in second_probs:
                second_probs[i] = {}
            second_probs[i][j] = stage2_all_probs[idx]

        # 各1着候補ごとに2着確率を正規化
        for i in second_probs:
            total = sum(second_probs[i].values())
            if total > 0:
                second_probs[i] = {j: p/total for j, p in second_probs[i].items()}

        # Stage3: 全120パターン(6×5×4)の特徴量を一括作成
        stage3_inputs = []
        stage3_mapping = []  # (first_idx, second_idx, third_idx)

        for i in range(6):
            for j in range(6):
                if j == i:
                    continue
                for k in range(6):
                    if k == i or k == j:
                        continue
                    features = self._create_stage3_features_cached(k, i, j, feature_cols_s3)
                    stage3_inputs.append(features)
                    stage3_mapping.append((i, j, k))

        # 一括予測（120パターンを1回で）
        if len(stage3_inputs) > 0 and self.models.get('stage3') is not None:
            stage3_all_probs = self.models['stage3'].predict_proba(stage3_inputs)[:, 1]
        else:
            stage3_all_probs = np.ones(len(stage3_inputs)) / 4

        # Stage3の正規化用: 同一(1着,2着)ペアのインデックスを事前グループ化
        # これにより O(120*120) → O(120) に高速化
        pair_groups = {}  # (i, j) -> [index, ...]
        for idx, (i, j, k) in enumerate(stage3_mapping):
            key = (i, j)
            if key not in pair_groups:
                pair_groups[key] = []
            pair_groups[key].append(idx)

        # 各ペアの確率合計を事前計算
        pair_sums = {}
        for key, indices in pair_groups.items():
            pair_sums[key] = sum(stage3_all_probs[n] for n in indices)

        # 三連単確率を計算
        trifecta_probs = {}
        for idx, (i, j, k) in enumerate(stage3_mapping):
            p_first = first_probs[i]
            p_second = second_probs.get(i, {}).get(j, 0)

            # Stage3の正規化（同一1-2着ペアで合計1になるように）
            same_pair_sum = pair_sums.get((i, j), 0)
            p_third = stage3_all_probs[idx] / same_pair_sum if same_pair_sum > 0 else 0.25

            # ベイズの連鎖則: P(i,j,k) = P(i) × P(j|i) × P(k|i,j)
            prob = p_first * p_second * p_third
            combination = f"{pit_numbers[i]}-{pit_numbers[j]}-{pit_numbers[k]}"
            trifecta_probs[combination] = float(prob)

        # 最終正規化
        total = sum(trifecta_probs.values())
        if total > 0:
            trifecta_probs = {k: v/total for k, v in trifecta_probs.items()}

        return trifecta_probs

    def _predict_first_place(self, race_features: pd.DataFrame) -> np.ndarray:
        """1着確率を予測（既存ロジックと同じ）"""
        if 'stage1' not in self.models or self.models['stage1'] is None:
            return np.ones(6) / 6

        feature_cols = self.feature_names.get('stage1', [])
        X = self._prepare_features(race_features, feature_cols)
        probs = self.models['stage1'].predict_proba(X)[:, 1]
        return probs / probs.sum()

    def _prepare_features(self, df: pd.DataFrame, feature_cols: List[str]) -> pd.DataFrame:
        """特徴量を準備"""
        exclude_cols = ['race_id', 'pit_number', 'race_date', 'venue_code',
                       'racer_number', 'race_number', 'rank']

        if not feature_cols:
            X = df.drop([c for c in exclude_cols if c in df.columns], axis=1)
            X = X.select_dtypes(include=[np.number])
        else:
            X = df.reindex(columns=feature_cols, fill_value=0)

        return X

    def _create_stage2_features_cached(self, candidate_idx: int,
                                        winner_idx: int,
                                        feature_cols: List[str]) -> np.ndarray:
        """
        キャッシュを使用したStage2特徴量作成（高速版）

        従来の型チェックを省略してキャッシュから直接取得
        """
        candidate = self._feature_cache[candidate_idx]
        winner = self._feature_cache[winner_idx]

        features = {}

        # 候補艇の特徴量
        for col, val in candidate.items():
            features[col] = val

        # 1着艇の特徴量
        for col, val in winner.items():
            features[f'winner_{col}'] = val

        # 差分特徴量（共通カラムのみ）
        common_cols = set(candidate.keys()) & set(winner.keys())
        for col in common_cols:
            features[f'diff_{col}'] = candidate[col] - winner[col]

        # 特徴量リストに合わせて並び替え
        return np.array([features.get(col, 0) for col in feature_cols])

    def _create_stage3_features_cached(self, candidate_idx: int,
                                        winner_idx: int,
                                        second_idx: int,
                                        feature_cols: List[str]) -> np.ndarray:
        """
        キャッシュを使用したStage3特徴量作成（高速版）
        """
        candidate = self._feature_cache[candidate_idx]
        winner = self._feature_cache[winner_idx]
        second = self._feature_cache[second_idx]

        features = {}

        # 候補艇の特徴量
        for col, val in candidate.items():
            features[col] = val

        # 1着艇の特徴量
        for col, val in winner.items():
            features[f'winner_{col}'] = val

        # 2着艇の特徴量
        for col, val in second.items():
            features[f'second_{col}'] = val

        # 差分特徴量
        common_cols = set(candidate.keys()) & set(winner.keys()) & set(second.keys())
        for col in common_cols:
            features[f'diff_winner_{col}'] = candidate[col] - winner[col]
            features[f'diff_second_{col}'] = candidate[col] - second[col]

        return np.array([features.get(col, 0) for col in feature_cols])

    def calculate_multi_race(self, race_features_list: List[pd.DataFrame],
                             pit_column: str = 'pit_number') -> List[Dict[str, float]]:
        """
        複数レースの三連単確率を一括計算（マルチレースバッチ推論）

        全レース分の特徴量を集めてLightGBMに1回で投入し、
        レース単位でのpredict_proba呼び出しオーバーヘッドを排除する。

        Args:
            race_features_list: 各レースの6艇分特徴量DataFrameのリスト
            pit_column: ピット番号のカラム名

        Returns:
            各レースの三連単確率辞書のリスト
        """
        if not self._loaded:
            self.load_models()

        n_races = len(race_features_list)
        if n_races == 0:
            return []

        # 単一レースの場合は通常のcalculateにフォールバック
        if n_races == 1:
            try:
                return [self.calculate(race_features_list[0], pit_column)]
            except Exception:
                return [{}]

        feature_cols_s1 = self.feature_names.get('stage1', [])
        feature_cols_s2 = self.feature_names.get('stage2', [])
        feature_cols_s3 = self.feature_names.get('stage3', [])

        # ==== Phase 1: 全レース分の特徴量キャッシュを構築 ====
        all_feature_caches = []  # race_idx -> {boat_idx -> {col: val}}
        all_pit_numbers = []     # race_idx -> np.ndarray(6,)
        valid_race_mask = []     # True if race has 6 boats

        for race_features in race_features_list:
            if len(race_features) != 6:
                all_feature_caches.append(None)
                all_pit_numbers.append(None)
                valid_race_mask.append(False)
                continue

            # 特徴量キャッシュ構築（_build_feature_cache相当）
            exclude_cols = {'race_id', 'pit_number', 'race_date', 'venue_code',
                           'racer_number', 'race_number', 'rank'}
            cache = {}
            for idx in range(6):
                row = race_features.iloc[idx]
                numeric_features = {}
                for col in race_features.columns:
                    if col not in exclude_cols:
                        val = row[col]
                        if isinstance(val, (int, float, np.integer, np.floating)):
                            numeric_features[col] = float(val)
                cache[idx] = numeric_features

            all_feature_caches.append(cache)
            all_pit_numbers.append(race_features[pit_column].values.astype(int))
            valid_race_mask.append(True)

        valid_indices = [i for i, v in enumerate(valid_race_mask) if v]
        if not valid_indices:
            return [{} for _ in range(n_races)]

        # ==== Phase 2: Stage1 一括推論 (6 * n_valid_races 行) ====
        all_stage1_inputs = []
        stage1_race_offsets = []  # 各レースのStage1入力開始位置

        for race_idx in valid_indices:
            race_features = race_features_list[race_idx]
            offset = len(all_stage1_inputs)
            stage1_race_offsets.append(offset)
            # _prepare_features 相当
            if not feature_cols_s1:
                exclude = ['race_id', 'pit_number', 'race_date', 'venue_code',
                           'racer_number', 'race_number', 'rank']
                X = race_features.drop([c for c in exclude if c in race_features.columns], axis=1)
                X = X.select_dtypes(include=[np.number])
            else:
                X = race_features.reindex(columns=feature_cols_s1, fill_value=0)
            all_stage1_inputs.append(X)

        if all_stage1_inputs and self.models.get('stage1') is not None:
            combined_s1 = pd.concat(all_stage1_inputs, ignore_index=True)
            all_s1_probs = self.models['stage1'].predict_proba(combined_s1)[:, 1]
        else:
            total_rows = sum(len(x) for x in all_stage1_inputs)
            all_s1_probs = np.ones(total_rows) / 6

        # Stage1結果をレースごとに分割・正規化
        first_probs_per_race = {}  # race_idx -> np.ndarray(6,)
        for vi, race_idx in enumerate(valid_indices):
            offset = stage1_race_offsets[vi]
            probs = all_s1_probs[offset:offset + 6]
            total = probs.sum()
            if total > 0:
                probs = probs / total
            first_probs_per_race[race_idx] = probs

        # ==== Phase 3: Stage2 一括推論 (30 * n_valid_races 行) ====
        all_stage2_inputs = []
        stage2_mapping = []  # (race_idx, first_idx, second_idx)

        for race_idx in valid_indices:
            cache = all_feature_caches[race_idx]
            for i in range(6):
                for j in range(6):
                    if j == i:
                        continue
                    # _create_stage2_features_cached 相当（インライン化）
                    candidate = cache[j]
                    winner = cache[i]
                    features = {}
                    for col, val in candidate.items():
                        features[col] = val
                    for col, val in winner.items():
                        features[f'winner_{col}'] = val
                    common_cols = set(candidate.keys()) & set(winner.keys())
                    for col in common_cols:
                        features[f'diff_{col}'] = candidate[col] - winner[col]
                    all_stage2_inputs.append(
                        np.array([features.get(col, 0) for col in feature_cols_s2])
                    )
                    stage2_mapping.append((race_idx, i, j))

        if all_stage2_inputs and self.models.get('stage2') is not None:
            stage2_array = np.array(all_stage2_inputs)
            all_s2_probs = self.models['stage2'].predict_proba(stage2_array)[:, 1]
        else:
            all_s2_probs = np.ones(len(all_stage2_inputs)) / 5

        # Stage2結果をレースごとに分割・正規化
        second_probs_per_race = {}  # race_idx -> {i: {j: prob}}
        for idx, (race_idx, i, j) in enumerate(stage2_mapping):
            if race_idx not in second_probs_per_race:
                second_probs_per_race[race_idx] = {}
            if i not in second_probs_per_race[race_idx]:
                second_probs_per_race[race_idx][i] = {}
            second_probs_per_race[race_idx][i][j] = all_s2_probs[idx]

        for race_idx in valid_indices:
            sp = second_probs_per_race.get(race_idx, {})
            for i in sp:
                total = sum(sp[i].values())
                if total > 0:
                    sp[i] = {j: p / total for j, p in sp[i].items()}

        # ==== Phase 4: Stage3 一括推論 (120 * n_valid_races 行) ====
        all_stage3_inputs = []
        stage3_mapping = []  # (race_idx, first_idx, second_idx, third_idx)

        for race_idx in valid_indices:
            cache = all_feature_caches[race_idx]
            for i in range(6):
                for j in range(6):
                    if j == i:
                        continue
                    for k in range(6):
                        if k == i or k == j:
                            continue
                        # _create_stage3_features_cached 相当（インライン化）
                        candidate = cache[k]
                        winner = cache[i]
                        second = cache[j]
                        features = {}
                        for col, val in candidate.items():
                            features[col] = val
                        for col, val in winner.items():
                            features[f'winner_{col}'] = val
                        for col, val in second.items():
                            features[f'second_{col}'] = val
                        common_cols = set(candidate.keys()) & set(winner.keys()) & set(second.keys())
                        for col in common_cols:
                            features[f'diff_winner_{col}'] = candidate[col] - winner[col]
                            features[f'diff_second_{col}'] = candidate[col] - second[col]
                        all_stage3_inputs.append(
                            np.array([features.get(col, 0) for col in feature_cols_s3])
                        )
                        stage3_mapping.append((race_idx, i, j, k))

        if all_stage3_inputs and self.models.get('stage3') is not None:
            stage3_array = np.array(all_stage3_inputs)
            all_s3_probs = self.models['stage3'].predict_proba(stage3_array)[:, 1]
        else:
            all_s3_probs = np.ones(len(all_stage3_inputs)) / 4

        # ==== Phase 5: 三連単確率を計算（レースごと） ====
        # Stage3の正規化用: (race_idx, i, j) ごとのグループ化
        pair_groups = {}  # (race_idx, i, j) -> [global_idx, ...]
        for idx, (race_idx, i, j, k) in enumerate(stage3_mapping):
            key = (race_idx, i, j)
            if key not in pair_groups:
                pair_groups[key] = []
            pair_groups[key].append(idx)

        pair_sums = {}
        for key, indices in pair_groups.items():
            pair_sums[key] = sum(all_s3_probs[n] for n in indices)

        trifecta_probs_per_race = {race_idx: {} for race_idx in valid_indices}
        for idx, (race_idx, i, j, k) in enumerate(stage3_mapping):
            pit_numbers = all_pit_numbers[race_idx]
            p_first = first_probs_per_race[race_idx][i]
            p_second = second_probs_per_race.get(race_idx, {}).get(i, {}).get(j, 0)

            same_pair_sum = pair_sums.get((race_idx, i, j), 0)
            p_third = all_s3_probs[idx] / same_pair_sum if same_pair_sum > 0 else 0.25

            prob = p_first * p_second * p_third
            combination = f"{pit_numbers[i]}-{pit_numbers[j]}-{pit_numbers[k]}"
            trifecta_probs_per_race[race_idx][combination] = float(prob)

        # 各レースの最終正規化
        for race_idx in valid_indices:
            probs = trifecta_probs_per_race[race_idx]
            total = sum(probs.values())
            if total > 0:
                trifecta_probs_per_race[race_idx] = {k: v / total for k, v in probs.items()}

        # 結果を元のリスト順に返却
        results = []
        for i in range(n_races):
            if valid_race_mask[i]:
                results.append(trifecta_probs_per_race.get(i, {}))
            else:
                results.append({})

        return results

    def get_top_combinations(self, probs: Dict[str, float],
                             top_n: int = 10) -> List[Tuple[str, float]]:
        """上位N件の組み合わせを取得"""
        sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)
        return sorted_probs[:top_n]
