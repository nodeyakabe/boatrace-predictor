"""
1着固定ルール判定
1号艇の勝率が高く、データ充実度が十分な場合に1着確定とマーク
"""

import json
from pathlib import Path
from typing import Dict, List, Optional


class FirstPlaceLockAnalyzer:
    """1着固定判定"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Args:
            config_path: 設定ファイルのパス
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / 'config' / 'prediction_improvements.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        self.enabled = config['first_place_lock']['enabled']
        self.win_rate_threshold = config['first_place_lock']['win_rate_threshold']
        self.min_data_completeness = config['first_place_lock']['min_data_completeness']

    def should_lock_first_place(
        self,
        pit_number: int,
        estimated_win_rate: float,
        data_completeness_score: float
    ) -> Dict[str, any]:
        """
        1着固定すべきかを判定

        Args:
            pit_number: 艇番
            estimated_win_rate: 推定勝率（0.0-1.0）
            data_completeness_score: データ充実度スコア（0-100）

        Returns:
            {
                'should_lock': bool,  # 固定すべきか
                'reason': str,  # 判定理由
                'win_rate': float,  # 勝率
                'data_completeness': float  # データ充実度
            }
        """
        if not self.enabled:
            return {
                'should_lock': False,
                'reason': '1着固定ルール無効',
                'win_rate': estimated_win_rate,
                'data_completeness': data_completeness_score
            }

        # 1号艇以外は固定しない
        if pit_number != 1:
            return {
                'should_lock': False,
                'reason': '1号艇以外',
                'win_rate': estimated_win_rate,
                'data_completeness': data_completeness_score
            }

        # 勝率閾値チェック
        if estimated_win_rate < self.win_rate_threshold:
            return {
                'should_lock': False,
                'reason': f'勝率不足（{estimated_win_rate*100:.1f}% < {self.win_rate_threshold*100:.1f}%）',
                'win_rate': estimated_win_rate,
                'data_completeness': data_completeness_score
            }

        # データ充実度チェック
        if data_completeness_score < self.min_data_completeness:
            return {
                'should_lock': False,
                'reason': f'データ不足（充実度{data_completeness_score:.1f} < {self.min_data_completeness}）',
                'win_rate': estimated_win_rate,
                'data_completeness': data_completeness_score
            }

        # 両方の条件を満たす場合は固定
        return {
            'should_lock': True,
            'reason': f'1着固定（勝率{estimated_win_rate*100:.1f}%, 充実度{data_completeness_score:.1f}）',
            'win_rate': estimated_win_rate,
            'data_completeness': data_completeness_score
        }

    def calculate_win_rate_from_predictions(
        self,
        predictions: List[Dict]
    ) -> Dict[int, float]:
        """
        予測結果から各艇の推定勝率を計算

        Args:
            predictions: 予測結果リスト
                [
                    {'pit_number': 1, 'total_score': 75.5, ...},
                    {'pit_number': 2, 'total_score': 55.2, ...},
                    ...
                ]

        Returns:
            {1: 0.55, 2: 0.14, ...}  # 艇番: 推定勝率
        """
        # スコアをソフトマックスで確率に変換
        total_scores = {p['pit_number']: p['total_score'] for p in predictions}

        # スコアを正規化（最小値を0に）
        min_score = min(total_scores.values())
        adjusted_scores = {pit: score - min_score for pit, score in total_scores.items()}

        # 合計が100になるように正規化
        total = sum(adjusted_scores.values())

        if total == 0:
            # すべて同じスコアの場合は均等分配
            return {pit: 1.0 / len(predictions) for pit in total_scores.keys()}

        win_rates = {pit: score / total for pit, score in adjusted_scores.items()}

        return win_rates

    def apply_first_place_lock_to_predictions(
        self,
        predictions: List[Dict]
    ) -> List[Dict]:
        """
        予測結果に1着固定ルールを適用

        Args:
            predictions: 予測結果リスト

        Returns:
            1着固定フラグが追加された予測結果
        """
        if not self.enabled:
            # 無効の場合はそのまま返す
            for pred in predictions:
                pred['first_place_locked'] = False
                pred['lock_reason'] = '1着固定ルール無効'
            return predictions

        # 推定勝率を計算
        win_rates = self.calculate_win_rate_from_predictions(predictions)

        # 各艇について判定
        for pred in predictions:
            pit_number = pred['pit_number']
            estimated_win_rate = win_rates.get(pit_number, 0.0)
            data_completeness = pred.get('data_completeness_score', 0.0)

            lock_result = self.should_lock_first_place(
                pit_number,
                estimated_win_rate,
                data_completeness
            )

            pred['first_place_locked'] = lock_result['should_lock']
            pred['lock_reason'] = lock_result['reason']
            pred['estimated_win_rate'] = estimated_win_rate

        return predictions
