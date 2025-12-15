"""
スコア統合モジュール（ScoreIntegrator）

事前情報（PreInfoScorer）と直前情報（BeforeInfoScorer）を
明確に分離した上で統合し、最終予測スコアを算出する。

設計思想:
1. 事前情報をベーススコアとして使用
2. 直前情報は「ベースからの差分」として加算
3. 全ての補正は加算・減算方式で統一
4. 補正履歴を完全にトレース可能

作成日: 2025-12-15
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


class IntegrationMode(Enum):
    """統合モード"""
    FIXED = 'fixed'           # 固定重み（PRE:BEFORE = 0.6:0.4）
    DYNAMIC = 'dynamic'       # 動的重み（状況に応じて調整）
    ADDITIVE = 'additive'     # 加算方式（PRE + BEFORE補正）
    GATED = 'gated'           # ゲート方式（PRE拮抗時のみBEFORE使用）


@dataclass
class IntegrationDetail:
    """統合詳細"""
    mode: IntegrationMode
    pre_score: float
    before_score: float
    adjustments: List[Dict] = field(default_factory=list)
    final_score: float = 0.0

    # 重み情報
    pre_weight: float = 0.6
    before_weight: float = 0.4

    # 補正情報
    total_adjustment: float = 0.0
    adjustment_reasons: List[str] = field(default_factory=list)


@dataclass
class IntegrationWeights:
    """統合重み"""
    pre_weight: float = 0.6
    before_weight: float = 0.4
    before_factor: float = 1.0  # 直前情報の影響係数

    @classmethod
    def from_context(
        cls,
        venue_code: str = None,
        race_grade: str = None,
        wind_speed: float = None,
        is_contested: bool = False
    ) -> 'IntegrationWeights':
        """
        コンテキストに応じた重みを生成

        Args:
            venue_code: 会場コード
            race_grade: レースグレード
            wind_speed: 風速
            is_contested: PRE拮抗状態か
        """
        pre_weight = 0.6
        before_weight = 0.4
        before_factor = 1.0

        # 荒れやすい条件では直前情報を重視
        if wind_speed and wind_speed >= 6.0:
            pre_weight = 0.5
            before_weight = 0.5
            before_factor = 1.2

        # 重賞レースでは選手実力（事前）を重視
        if race_grade in ['SG', 'G1']:
            pre_weight = 0.7
            before_weight = 0.3
            before_factor = 0.8

        # PRE拮抗時は直前情報を重視
        if is_contested:
            pre_weight = 0.5
            before_weight = 0.5
            before_factor = 1.3

        return cls(
            pre_weight=pre_weight,
            before_weight=before_weight,
            before_factor=before_factor
        )


class ScoreIntegrator:
    """
    スコア統合クラス

    事前情報と直前情報を統合して最終スコアを算出。
    複数の統合モードをサポートし、補正履歴を完全にトレース可能。
    """

    # PRE拮抗判定の閾値
    CONTESTED_THRESHOLD = 5.0  # 点

    # BEFORE基準値（中央値）
    BEFORE_BASELINE = 50.0

    def __init__(
        self,
        default_mode: IntegrationMode = IntegrationMode.ADDITIVE,
        pre_weight: float = 0.6,
        before_weight: float = 0.4
    ):
        """
        初期化

        Args:
            default_mode: デフォルトの統合モード
            pre_weight: 事前スコアの重み（FIXED/DYNAMICモード用）
            before_weight: 直前スコアの重み（FIXED/DYNAMICモード用）
        """
        self.default_mode = default_mode
        self.default_weights = IntegrationWeights(
            pre_weight=pre_weight,
            before_weight=before_weight
        )

    def integrate(
        self,
        pre_score: float,
        before_score: float,
        mode: Optional[IntegrationMode] = None,
        weights: Optional[IntegrationWeights] = None,
        context: Optional[Dict] = None
    ) -> Tuple[float, IntegrationDetail]:
        """
        スコアを統合

        Args:
            pre_score: 事前情報スコア（0-100）
            before_score: 直前情報スコア（0-100または0-115）
            mode: 統合モード（Noneの場合はdefault_mode）
            weights: 統合重み（Noneの場合はdefault_weights）
            context: 追加コンテキスト（会場、グレード等）

        Returns:
            (最終スコア, 統合詳細)
        """
        mode = mode or self.default_mode
        weights = weights or self.default_weights

        if mode == IntegrationMode.FIXED:
            return self._integrate_fixed(pre_score, before_score, weights)
        elif mode == IntegrationMode.DYNAMIC:
            return self._integrate_dynamic(pre_score, before_score, weights, context)
        elif mode == IntegrationMode.ADDITIVE:
            return self._integrate_additive(pre_score, before_score, weights)
        elif mode == IntegrationMode.GATED:
            return self._integrate_gated(pre_score, before_score, weights, context)
        else:
            return self._integrate_fixed(pre_score, before_score, weights)

    def _integrate_fixed(
        self,
        pre_score: float,
        before_score: float,
        weights: IntegrationWeights
    ) -> Tuple[float, IntegrationDetail]:
        """
        固定重み方式

        FINAL_SCORE = PRE_SCORE * pre_weight + BEFORE_SCORE * before_weight
        """
        # BEFORE_SCOREを100点満点に正規化（115点満点の場合）
        normalized_before = min(before_score * (100.0 / 115.0), 100.0)

        final_score = (
            pre_score * weights.pre_weight +
            normalized_before * weights.before_weight
        )

        final_score = max(0.0, min(100.0, final_score))

        detail = IntegrationDetail(
            mode=IntegrationMode.FIXED,
            pre_score=pre_score,
            before_score=before_score,
            final_score=final_score,
            pre_weight=weights.pre_weight,
            before_weight=weights.before_weight,
            adjustments=[
                {'type': 'fixed_weight', 'pre': pre_score * weights.pre_weight,
                 'before': normalized_before * weights.before_weight}
            ]
        )

        return final_score, detail

    def _integrate_dynamic(
        self,
        pre_score: float,
        before_score: float,
        weights: IntegrationWeights,
        context: Optional[Dict] = None
    ) -> Tuple[float, IntegrationDetail]:
        """
        動的重み方式

        コンテキスト（会場、天候等）に応じて重みを動的に調整
        """
        if context:
            dynamic_weights = IntegrationWeights.from_context(
                venue_code=context.get('venue_code'),
                race_grade=context.get('race_grade'),
                wind_speed=context.get('wind_speed'),
                is_contested=context.get('is_contested', False)
            )
        else:
            dynamic_weights = weights

        # BEFORE_SCOREを100点満点に正規化
        normalized_before = min(before_score * (100.0 / 115.0), 100.0)

        final_score = (
            pre_score * dynamic_weights.pre_weight +
            normalized_before * dynamic_weights.before_weight
        )

        final_score = max(0.0, min(100.0, final_score))

        detail = IntegrationDetail(
            mode=IntegrationMode.DYNAMIC,
            pre_score=pre_score,
            before_score=before_score,
            final_score=final_score,
            pre_weight=dynamic_weights.pre_weight,
            before_weight=dynamic_weights.before_weight,
            adjustments=[
                {'type': 'dynamic_weight',
                 'context': context,
                 'weights_used': {
                     'pre': dynamic_weights.pre_weight,
                     'before': dynamic_weights.before_weight,
                     'factor': dynamic_weights.before_factor
                 }}
            ]
        )

        return final_score, detail

    def _integrate_additive(
        self,
        pre_score: float,
        before_score: float,
        weights: IntegrationWeights
    ) -> Tuple[float, IntegrationDetail]:
        """
        加算方式（推奨）

        事前スコアをベースとし、直前情報を「ベースラインからの差分」として加算。
        これにより、直前情報がスコアに依存しない固定的な補正として機能する。

        FINAL_SCORE = PRE_SCORE + (BEFORE_SCORE - BASELINE) * before_factor
        """
        # BEFORE_SCOREを100点満点に正規化（115点満点の場合）
        normalized_before = min(before_score * (100.0 / 115.0), 100.0)

        # 直前情報の差分を計算
        before_adjustment = (normalized_before - self.BEFORE_BASELINE) * weights.before_factor

        # 最終スコア
        final_score = pre_score + before_adjustment

        # 範囲を制限
        final_score = max(0.0, min(100.0, final_score))

        detail = IntegrationDetail(
            mode=IntegrationMode.ADDITIVE,
            pre_score=pre_score,
            before_score=before_score,
            final_score=final_score,
            pre_weight=1.0,  # 加算方式ではPREが100%ベース
            before_weight=weights.before_factor,
            total_adjustment=before_adjustment,
            adjustments=[
                {
                    'type': 'additive',
                    'base_score': pre_score,
                    'before_normalized': normalized_before,
                    'baseline': self.BEFORE_BASELINE,
                    'before_adjustment': before_adjustment,
                    'before_factor': weights.before_factor
                }
            ],
            adjustment_reasons=[
                f'直前情報補正: {before_adjustment:+.1f}点 '
                f'(BEFORE {normalized_before:.1f} - 基準 {self.BEFORE_BASELINE:.1f}) × {weights.before_factor:.2f}'
            ]
        )

        return final_score, detail

    def _integrate_gated(
        self,
        pre_score: float,
        before_score: float,
        weights: IntegrationWeights,
        context: Optional[Dict] = None
    ) -> Tuple[float, IntegrationDetail]:
        """
        ゲート方式

        PRE拮抗時のみBEFORE情報を使用。
        拮抗していない場合はPREスコアのみ使用。
        """
        # PRE拮抗判定
        is_contested = context.get('is_contested', False) if context else False
        pre_margin = context.get('pre_margin', 999.9) if context else 999.9

        if pre_margin < self.CONTESTED_THRESHOLD:
            is_contested = True

        # BEFORE_SCOREを100点満点に正規化
        normalized_before = min(before_score * (100.0 / 115.0), 100.0)

        if is_contested:
            # 拮抗時: 加算方式を適用
            before_adjustment = (normalized_before - self.BEFORE_BASELINE) * weights.before_factor
            final_score = pre_score + before_adjustment
            gate_applied = True
        else:
            # 非拮抗時: PREスコアのみ
            before_adjustment = 0.0
            final_score = pre_score
            gate_applied = False

        final_score = max(0.0, min(100.0, final_score))

        detail = IntegrationDetail(
            mode=IntegrationMode.GATED,
            pre_score=pre_score,
            before_score=before_score,
            final_score=final_score,
            pre_weight=1.0,
            before_weight=weights.before_factor if gate_applied else 0.0,
            total_adjustment=before_adjustment,
            adjustments=[
                {
                    'type': 'gated',
                    'is_contested': is_contested,
                    'pre_margin': pre_margin,
                    'threshold': self.CONTESTED_THRESHOLD,
                    'gate_applied': gate_applied,
                    'before_adjustment': before_adjustment
                }
            ],
            adjustment_reasons=[
                f'ゲート方式: {"拮抗→BEFORE適用" if gate_applied else "非拮抗→PREのみ"}'
                f' (差分: {pre_margin:.1f}点, 閾値: {self.CONTESTED_THRESHOLD}点)'
            ]
        )

        return final_score, detail

    def integrate_batch(
        self,
        scores: List[Dict],
        mode: Optional[IntegrationMode] = None,
        context: Optional[Dict] = None
    ) -> List[Dict]:
        """
        バッチ統合（1レース6艇分）

        Args:
            scores: [{'pit_number': int, 'pre_score': float, 'before_score': float}, ...]
            mode: 統合モード
            context: コンテキスト

        Returns:
            統合後のスコアリスト
        """
        mode = mode or self.default_mode

        # PRE拮抗判定（GATED/DYNAMICモード用）
        if len(scores) >= 2:
            sorted_by_pre = sorted(scores, key=lambda x: x.get('pre_score', 0), reverse=True)
            pre_margin = sorted_by_pre[0]['pre_score'] - sorted_by_pre[1]['pre_score']
            is_contested = pre_margin < self.CONTESTED_THRESHOLD
        else:
            pre_margin = 999.9
            is_contested = False

        # コンテキストを更新
        if context is None:
            context = {}
        context['is_contested'] = is_contested
        context['pre_margin'] = pre_margin

        # 各艇のスコアを統合
        results = []
        for score_data in scores:
            pre_score = score_data.get('pre_score', 50.0)
            before_score = score_data.get('before_score', 50.0)

            final_score, detail = self.integrate(
                pre_score, before_score, mode, context=context
            )

            results.append({
                **score_data,
                'final_score': final_score,
                'integration_detail': detail
            })

        # 最終スコア降順でソート
        results.sort(key=lambda x: x['final_score'], reverse=True)

        return results


# 便利関数
def integrate_scores(
    pre_score: float,
    before_score: float,
    mode: str = 'additive',
    context: Dict = None
) -> float:
    """
    スコア統合の便利関数

    Args:
        pre_score: 事前スコア
        before_score: 直前スコア
        mode: 統合モード（'fixed', 'dynamic', 'additive', 'gated'）
        context: コンテキスト

    Returns:
        統合後のスコア
    """
    mode_map = {
        'fixed': IntegrationMode.FIXED,
        'dynamic': IntegrationMode.DYNAMIC,
        'additive': IntegrationMode.ADDITIVE,
        'gated': IntegrationMode.GATED,
    }

    integrator = ScoreIntegrator()
    final_score, _ = integrator.integrate(
        pre_score, before_score,
        mode=mode_map.get(mode, IntegrationMode.ADDITIVE),
        context=context
    )
    return final_score


# テスト用
if __name__ == "__main__":
    print("=" * 80)
    print("ScoreIntegrator テスト")
    print("=" * 80)

    integrator = ScoreIntegrator()

    test_cases = [
        {'name': 'PRE優勢', 'pre': 75.0, 'before': 50.0},
        {'name': 'BEFORE優勢', 'pre': 50.0, 'before': 90.0},
        {'name': '均等', 'pre': 60.0, 'before': 60.0},
        {'name': 'PRE低・BEFORE高', 'pre': 30.0, 'before': 80.0},
    ]

    for mode in [IntegrationMode.FIXED, IntegrationMode.ADDITIVE, IntegrationMode.GATED]:
        print(f"\n【{mode.value}モード】")

        for case in test_cases:
            final_score, detail = integrator.integrate(
                case['pre'], case['before'], mode=mode
            )
            print(f"  {case['name']}: PRE={case['pre']:.1f}, BEFORE={case['before']:.1f} "
                  f"→ FINAL={final_score:.1f}")

    print("\n" + "=" * 80)
    print("バッチ統合テスト")
    print("=" * 80)

    batch_scores = [
        {'pit_number': 1, 'pre_score': 75.0, 'before_score': 80.0},
        {'pit_number': 2, 'pre_score': 72.0, 'before_score': 60.0},
        {'pit_number': 3, 'pre_score': 55.0, 'before_score': 70.0},
        {'pit_number': 4, 'pre_score': 50.0, 'before_score': 55.0},
        {'pit_number': 5, 'pre_score': 45.0, 'before_score': 50.0},
        {'pit_number': 6, 'pre_score': 40.0, 'before_score': 45.0},
    ]

    results = integrator.integrate_batch(batch_scores, mode=IntegrationMode.ADDITIVE)

    print("\n【加算方式バッチ統合結果】")
    for r in results:
        print(f"  {r['pit_number']}号艇: PRE={r['pre_score']:.1f}, BEFORE={r['before_score']:.1f} "
              f"→ FINAL={r['final_score']:.1f}")

    print("\n" + "=" * 80)
    print("テスト完了")
    print("=" * 80)
