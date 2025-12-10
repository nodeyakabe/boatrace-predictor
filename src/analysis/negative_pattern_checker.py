"""
ネガティブパターンチェッカー（軽量版）

予測が外れやすい条件を検出し、警告フラグを立てる。
Phase 1の重い抽出スクリプトの結果をハードコードして高速化。
"""

from typing import Dict, List, Optional
import logging


class NegativePatternChecker:
    """ネガティブパターン検出クラス"""

    def __init__(self):
        """
        初期化

        ネガティブパターン:
        - 予測1位だが展示・ST両方がワースト2
        - 展示とSTの順位乖離が4ランク以上
        - STタイミングが大幅にずれている
        """
        self.logger = logging.getLogger(__name__)

        # ネガティブパターンの定義
        self.patterns = {
            'both_bad': {
                'name': '展示・ST両方不良',
                'check': self._check_both_bad,
                'severity': 'high',
                'score_multiplier': 0.85,  # スコアを15%減算
                'description': '展示タイム・STタイミング両方がワースト2以内'
            },
            'rank_divergence': {
                'name': '展示・ST順位乖離',
                'check': self._check_rank_divergence,
                'severity': 'medium',
                'score_multiplier': 0.90,  # スコアを10%減算
                'description': '展示順位とST順位の差が4ランク以上'
            },
            'st_timing_off': {
                'name': 'STタイミング大幅ずれ',
                'check': self._check_st_timing_off,
                'severity': 'medium',
                'score_multiplier': 0.90,
                'description': 'STタイミングが±0.15秒以上ずれ'
            },
            'ex_worst': {
                'name': '展示タイムワースト',
                'check': self._check_ex_worst,
                'severity': 'low',
                'score_multiplier': 0.95,
                'description': '展示タイムがワースト2以内'
            },
        }

    def _check_both_bad(self, ex_rank: int, st_rank: int, st_time: float) -> bool:
        """展示・ST両方が不良かチェック"""
        return ex_rank >= 5 and st_rank >= 5

    def _check_rank_divergence(self, ex_rank: int, st_rank: int, st_time: float) -> bool:
        """展示とSTの順位乖離をチェック"""
        return abs(ex_rank - st_rank) >= 4

    def _check_st_timing_off(self, ex_rank: int, st_rank: int, st_time: float) -> bool:
        """STタイミングの大幅ずれをチェック"""
        if st_time is None:
            return False
        return st_time < -0.15 or st_time > 0.20

    def _check_ex_worst(self, ex_rank: int, st_rank: int, st_time: float) -> bool:
        """展示タイムワーストをチェック"""
        return ex_rank >= 5

    def check_prediction(
        self,
        pit_number: int,
        ex_rank: Optional[int],
        st_rank: Optional[int],
        st_time: Optional[float],
        pre_rank: int
    ) -> Dict:
        """
        予測に対するネガティブパターンをチェック

        Args:
            pit_number: 艇番
            ex_rank: 展示タイム順位（1-6）
            st_rank: STタイミング順位（1-6、0に近い順）
            st_time: STタイミング（秒）
            pre_rank: PRE予測順位

        Returns:
            {
                'has_negative': bool,
                'matched_patterns': List[str],
                'severity': str,  # 'high', 'medium', 'low'
                'recommended_multiplier': float,
                'warnings': List[str]
            }
        """
        result = {
            'has_negative': False,
            'matched_patterns': [],
            'severity': 'none',
            'recommended_multiplier': 1.0,
            'warnings': []
        }

        # BEFORE情報が不完全な場合はスキップ
        if ex_rank is None or st_rank is None:
            return result

        matched_patterns = []
        max_severity = 'none'
        min_multiplier = 1.0

        # 各ネガティブパターンをチェック
        for pattern_id, pattern_config in self.patterns.items():
            if pattern_config['check'](ex_rank, st_rank, st_time):
                matched_patterns.append(pattern_id)

                # 最も重い severity を採用
                severity = pattern_config['severity']
                if self._compare_severity(severity, max_severity) > 0:
                    max_severity = severity

                # 最も小さい multiplier を採用
                multiplier = pattern_config['score_multiplier']
                if multiplier < min_multiplier:
                    min_multiplier = multiplier

                # 警告メッセージを追加
                result['warnings'].append(
                    f"{pattern_config['name']}: {pattern_config['description']}"
                )

        if matched_patterns:
            result['has_negative'] = True
            result['matched_patterns'] = matched_patterns
            result['severity'] = max_severity
            result['recommended_multiplier'] = min_multiplier

            self.logger.debug(
                f"艇{pit_number} (PRE順位{pre_rank}): "
                f"ネガティブパターン検出 {matched_patterns} → "
                f"multiplier {min_multiplier:.2f}"
            )

        return result

    def _compare_severity(self, sev1: str, sev2: str) -> int:
        """
        severity を比較

        Returns:
            1: sev1 > sev2
            0: sev1 == sev2
            -1: sev1 < sev2
        """
        order = {'none': 0, 'low': 1, 'medium': 2, 'high': 3}
        return (order.get(sev1, 0) > order.get(sev2, 0)) - (order.get(sev1, 0) < order.get(sev2, 0))

    def apply_negative_adjustments(
        self,
        predictions: List[Dict],
        before_ranks: Dict[int, Dict]
    ) -> List[Dict]:
        """
        予測リストにネガティブパターン調整を適用

        Args:
            predictions: 予測結果リスト
            before_ranks: {pit_number: {'ex_rank': int, 'st_rank': int, 'st_time': float}}

        Returns:
            調整後の予測リスト
        """
        for pred in predictions:
            pit_number = pred.get('pit_number')
            pre_rank = pred.get('rank_prediction', 99)

            if pit_number not in before_ranks:
                continue

            ranks = before_ranks[pit_number]
            ex_rank = ranks.get('ex_rank')
            st_rank = ranks.get('st_rank')
            st_time = ranks.get('st_time')

            # ネガティブパターンチェック
            check_result = self.check_prediction(
                pit_number, ex_rank, st_rank, st_time, pre_rank
            )

            if check_result['has_negative']:
                # スコアを調整
                current_score = pred.get('total_score', 0)
                multiplier = check_result['recommended_multiplier']
                adjusted_score = current_score * multiplier

                pred['negative_pattern_applied'] = True
                pred['negative_patterns'] = check_result['matched_patterns']
                pred['negative_severity'] = check_result['severity']
                pred['negative_multiplier'] = multiplier
                pred['negative_warnings'] = check_result['warnings']
                pred['score_before_negative'] = current_score
                pred['total_score'] = round(adjusted_score, 1)

                self.logger.info(
                    f"艇{pit_number}: ネガティブ調整 "
                    f"{current_score:.1f} → {adjusted_score:.1f} "
                    f"({check_result['severity']}: {', '.join(check_result['matched_patterns'])})"
                )
            else:
                pred['negative_pattern_applied'] = False
                pred['negative_patterns'] = []

        # スコア降順で再ソート
        predictions.sort(key=lambda x: x.get('total_score', 0), reverse=True)

        return predictions
