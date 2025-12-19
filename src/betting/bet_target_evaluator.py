# -*- coding: utf-8 -*-
"""
購入対象判定モジュール

最終運用戦略に基づいて、レースが購入対象かどうかを判定する
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Any
from .multi_bet_generator import MultiBetGenerator, MultiBetPattern, MultiBetResult
from .venue_evaluator import VenueEvaluator
from .venue_course_adjuster import VenueCourseAdjuster, AdjustmentResult
from config.venue_wind_adjustments import should_exclude_race


class BetStatus(Enum):
    """購入判定状態"""
    TARGET_ADVANCE = "対象（事前）"      # 事前情報のみで購入条件を満たす
    CANDIDATE = "候補"                   # 直前情報次第で対象に入る可能性
    TARGET_CONFIRMED = "対象（確定）"    # 直前情報取得後、最終的に購入対象
    EXCLUDED = "対象外"                  # 購入条件を満たさない


@dataclass
class BetTarget:
    """購入対象情報"""
    status: BetStatus
    confidence: str                      # 信頼度 (A/B/C/D)
    method: str                          # 方式 (従来/新方式)
    combination: str                     # 買い目 (例: "1-2-3")
    odds: Optional[float]                # オッズ
    odds_range: str                      # オッズ範囲条件
    c1_rank: str                         # 1コース選手の級別
    expected_roi: float                  # 期待回収率
    bet_amount: int                      # 推奨賭け金
    reason: str                          # 判定理由
    needs_beforeinfo: bool = False       # 直前情報が必要か
    bet_type: str = 'trifecta'           # 賭け式 (trifecta/exacta)
    multi_bet_result: Optional[MultiBetResult] = None  # 複数点買い情報
    venue_course_adjustment: Optional[AdjustmentResult] = None  # 会場コース調整情報


@dataclass
class ExactaBetTarget:
    """2連単購入対象情報"""
    status: BetStatus
    confidence: str                      # 信頼度 (A/B/C/D)
    combination: str                     # 買い目 (例: "1-2")
    c1_rank: str                         # 1コース選手の級別
    expected_roi: float                  # 期待回収率
    bet_amount: int                      # 推奨賭け金
    reason: str                          # 判定理由


class BetTargetEvaluator:
    """購入対象判定クラス"""

    # ============================================================
    # イン強会場定義（2025年12月8日 Opus分析結果）
    # ============================================================
    # 1コース勝率が高い会場（大村/下関/徳山）
    # 信頼度D × イン強会場で ROI +53.1% を確認
    HIGH_IN_VENUES = [24, 19, 18]  # 大村、下関、徳山

    # ============================================================
    # 購入条件定義（2025年12月14日更新 - 全条件マトリクス分析版）
    # ============================================================
    # 全条件マトリクス分析（ALL_CONDITIONS_MATRIX_2025.md）に基づく戦略
    # - 戦略B（バランス型・推奨）: 年間ROI 149.7%, 収支 +165,960円
    # - 月間的中3回で精神的安定を確保しつつ高収益
    # - 検証期間: 2025年全期間（833レース購入、36回的中、的中率4.3%）
    # - 追加条件: D×A1（超有望）、C×B1×30-40倍（安定）、C×A1×30-40倍（バランス）
    # ============================================================
    BET_CONDITIONS = {
        # 信頼度C: 中配当〜安定型
        'C': [
            # C × B1 × 30-40倍: ROI 158.6%, 収支 +52,560円（299件/15的中）
            # → 最も安定した条件。月1回以上の的中で精神的安定に寄与
            {
                'method': '両方式',
                'odds_min': 30, 'odds_max': 40,
                'c1_rank': ['B1'],
                'expected_roi': 158.6,
                'bet_amount': 300,
                'priority': 1,
                'description': 'C×B1級×30-40倍（安定主力）',
            },
            # C × A1 × 30-40倍: ROI 141.7%, 収支 +24,120円（193件/8的中）
            # → A1級でバランス型
            {
                'method': '両方式',
                'odds_min': 30, 'odds_max': 40,
                'c1_rank': ['A1'],
                'expected_roi': 141.7,
                'bet_amount': 300,
                'priority': 2,
                'description': 'C×A1級×30-40倍（バランス）',
            },
        ],
        # 信頼度D: 高配当＋安定配当の複合
        'D': [
            # D × B1 × 40-50倍: ROI 132.0%, 収支 +17,550円（183件/5的中）
            # → 比較的安定した条件
            {
                'method': '両方式',
                'odds_min': 40, 'odds_max': 50,
                'c1_rank': ['B1'],
                'expected_roi': 132.0,
                'bet_amount': 300,
                'priority': 1,
                'description': 'D×B1級×40-50倍（安定補助）',
            },
            # D × A1 × 40-50倍: ROI 405.8%, 収支 +48,630円（53件/1的中）
            # → 高配当狙い。サンプル少ないが期待値大
            {
                'method': '両方式',
                'odds_min': 40, 'odds_max': 50,
                'c1_rank': ['A1'],
                'expected_roi': 405.8,
                'bet_amount': 300,
                'priority': 2,
                'description': 'D×A1級×40-50倍（高配当）',
            },
            # D × A2 × 20-30倍: ROI 173.3%, 収支 +23,100円（105件/7的中）
            # → 的中頻度高め（月0.6回）、安定収益
            {
                'method': '両方式',
                'odds_min': 20, 'odds_max': 30,
                'c1_rank': ['A2'],
                'expected_roi': 173.3,
                'bet_amount': 300,
                'priority': 3,
                'description': 'D×A2級×20-30倍（安定収益）',
            },
        ],
    }

    # ============================================================
    # A・Bランク特別条件（2025年12月19日追加）
    # ============================================================
    # サンプル数増加（A:約7,500件、B:約39,000件）により統計的に有効と判断
    # Aランク全体ROI 60%、Bランク全体ROI 74%は赤字だが、
    # 以下の特定条件でROI 100%以上を確認
    # ============================================================
    AB_RANK_SPECIAL_CONDITIONS = {
        # Bランク × 50-100倍帯: ROI 512% (n=14, 的中率7.14%)
        'B': [
            {
                'method': '両方式',
                'odds_min': 50, 'odds_max': 100,
                'c1_rank': ['A1', 'A2', 'B1'],  # B2除外
                'expected_roi': 512.1,
                'bet_amount': 300,
                'priority': 1,
                'description': 'B×50-100倍（高配当特化）',
            },
        ],
        # A・Bランク × 1コースB1級: ROI 154% (n=82, 的中率6.10%)
        'A': [
            {
                'method': '両方式',
                'odds_min': 10, 'odds_max': 100,  # 幅広いオッズ帯
                'c1_rank': ['B1'],  # B1級限定
                'expected_roi': 154.1,
                'bet_amount': 300,
                'priority': 1,
                'description': 'A×B1級（特別条件）',
            },
        ],
    }
    # Bランク × B1級も追加（A+BランクでB1級が有効）
    AB_RANK_SPECIAL_CONDITIONS['B'].append({
        'method': '両方式',
        'odds_min': 10, 'odds_max': 100,
        'c1_rank': ['B1'],
        'expected_roi': 154.1,
        'bet_amount': 300,
        'priority': 2,
        'description': 'B×B1級（特別条件）',
    })

    # 除外条件
    # - B2級のみ除外（B1級は高配当範囲で超優秀なため使用）
    EXCLUDED_C1_RANKS = ['B2']

    # ============================================================
    # 2連単 購入条件定義（2025年12月追加）
    # ============================================================
    # バックテスト検証結果:
    # - D × A1 × 2連単: 的中率14.6%, ROI 106.7%
    # - 月間的中数を増やし、収支安定化を図る補助戦略
    # ============================================================
    EXACTA_CONDITIONS = {
        'D': {
            'c1_rank': ['A1'],
            'expected_roi': 106.7,
            'bet_amount': 200,
            'sample_count': 907,
            'hit_rate': 14.6,
        },
    }

    def __init__(
        self,
        use_multi_bet: bool = True,
        multi_bet_pattern: MultiBetPattern = MultiBetPattern.PATTERN_H,
        enable_venue_wind_filter: bool = True,
        enable_venue_course_adjustment: bool = True,
        venue_course_adjustment_scale: float = 1.0,
    ):
        """
        初期化

        Args:
            use_multi_bet: 複数点買いを使用するか（デフォルト: True）
            multi_bet_pattern: 複数点買いパターン（デフォルト: PATTERN_H - 収支最大）
            enable_venue_wind_filter: 風速・会場フィルターを有効化するか（デフォルト: True）
            enable_venue_course_adjustment: 会場×コース別調整を有効化するか（デフォルト: True）
            venue_course_adjustment_scale: 調整値のスケール（デフォルト: 1.0 = 100%適用）
        """
        self.use_multi_bet = use_multi_bet
        self.multi_bet_generator = MultiBetGenerator(default_pattern=multi_bet_pattern) if use_multi_bet else None
        self.enable_venue_wind_filter = enable_venue_wind_filter
        self.venue_evaluator = VenueEvaluator() if enable_venue_wind_filter else None

        # 会場×コース別調整
        self.enable_venue_course_adjustment = enable_venue_course_adjustment
        self.venue_course_adjuster = VenueCourseAdjuster(
            enabled=enable_venue_course_adjustment,
            adjustment_scale=venue_course_adjustment_scale,
        ) if enable_venue_course_adjustment else None

    def evaluate(
        self,
        confidence: str,
        c1_rank: str,
        old_combo: str,
        new_combo: str,
        old_odds: Optional[float] = None,
        new_odds: Optional[float] = None,
        has_beforeinfo: bool = False,
        venue_code: Optional[int] = None
    ) -> BetTarget:
        """
        購入対象を判定する

        Args:
            confidence: 信頼度 (A/B/C/D)
            c1_rank: 1コース選手の級別 (A1/A2/B1/B2)
            old_combo: 従来方式の買い目 (例: "1-2-3")
            new_combo: 新方式の買い目 (例: "1-2-3")
            old_odds: 従来方式買い目のオッズ
            new_odds: 新方式買い目のオッズ
            has_beforeinfo: 直前情報が取得済みか
            venue_code: 会場コード（イン強会場条件チェック用）

        Returns:
            BetTarget: 購入対象情報
        """
        # A・Bランクは特別条件をチェック（feature_flagで制御）
        from config.feature_flags import is_feature_enabled

        if confidence in ['A', 'B']:
            if not is_feature_enabled('ab_rank_special_betting'):
                return BetTarget(
                    status=BetStatus.EXCLUDED,
                    confidence=confidence,
                    method='-',
                    combination='-',
                    odds=None,
                    odds_range='-',
                    c1_rank=c1_rank,
                    expected_roi=0,
                    bet_amount=0,
                    reason=f'信頼度{confidence}は購入対象外（フラグ無効）'
                )
            # 特別条件をチェック
            conditions = self.AB_RANK_SPECIAL_CONDITIONS.get(confidence, [])
        else:
            # 信頼度に応じた条件をチェック（C, D）
            conditions = self.BET_CONDITIONS.get(confidence, [])

        # 1コース級別チェック（条件定義で許可されている級別かチェック）
        # 条件定義に合致する級別があるかを先に確認
        has_matching_rank = any(c1_rank in cond.get('c1_rank', []) for cond in conditions)

        # デフォルトの除外条件（条件定義にない場合のみ適用）
        if not has_matching_rank and (c1_rank in self.EXCLUDED_C1_RANKS or c1_rank not in ['A1', 'A2', 'B1', 'B2']):
            return BetTarget(
                status=BetStatus.EXCLUDED,
                confidence=confidence,
                method='-',
                combination='-',
                odds=None,
                odds_range='-',
                c1_rank=c1_rank,
                expected_roi=0,
                bet_amount=0,
                reason=f'1コース{c1_rank}級は購入対象外（回収率低）'
            )

        if not conditions:
            return BetTarget(
                status=BetStatus.EXCLUDED,
                confidence=confidence,
                method='-',
                combination='-',
                odds=None,
                odds_range='-',
                c1_rank=c1_rank,
                expected_roi=0,
                bet_amount=0,
                reason=f'信頼度{confidence}は購入対象外'
            )

        # 各条件をチェック（優先度順にソート）
        sorted_conditions = sorted(conditions, key=lambda x: x.get('priority', 999))

        for i, cond in enumerate(sorted_conditions):
            # 級別チェック
            if c1_rank not in cond['c1_rank']:
                continue

            # 会場コードチェック（venue_codes が指定されている場合）
            if 'venue_codes' in cond:
                if venue_code is None or venue_code not in cond['venue_codes']:
                    continue

            # 方式と買い目の決定
            if cond['method'] == '従来':
                combo = old_combo
                odds = old_odds
            elif cond['method'] == '新方式':
                combo = new_combo
                odds = new_odds
            else:  # '両方式'の場合、オッズが高い方を選択
                if old_odds and new_odds:
                    if old_odds >= new_odds:
                        combo = old_combo
                        odds = old_odds
                    else:
                        combo = new_combo
                        odds = new_odds
                elif old_odds:
                    combo = old_combo
                    odds = old_odds
                elif new_odds:
                    combo = new_combo
                    odds = new_odds
                else:
                    combo = old_combo
                    odds = old_odds

            odds_min = cond['odds_min']
            odds_max = cond['odds_max']
            odds_range = f"{odds_min}倍+" if odds_max >= 9999 else f"{odds_min}-{odds_max}倍"

            # オッズが不明な場合
            if odds is None or odds == 0:
                # 直前情報がまだなら「候補」
                if not has_beforeinfo:
                    return BetTarget(
                        status=BetStatus.CANDIDATE,
                        confidence=confidence,
                        method=cond['method'],
                        combination=combo,
                        odds=None,
                        odds_range=odds_range,
                        c1_rank=c1_rank,
                        expected_roi=cond['expected_roi'],
                        bet_amount=cond['bet_amount'],
                        reason=f'オッズ未取得。{odds_range}なら購入対象',
                        needs_beforeinfo=True
                    )
                else:
                    # 直前情報取得後もオッズ不明なら対象外
                    continue

            # オッズ範囲チェック
            if odds_min <= odds < odds_max:
                status = BetStatus.TARGET_CONFIRMED if has_beforeinfo else BetStatus.TARGET_ADVANCE
                # 理由の構築
                reason_parts = [f'信頼度{confidence}', cond['method'], odds_range, f'1コース{c1_rank}']
                if 'venue_codes' in cond:
                    reason_parts.append('イン強会場')
                reason = ' + '.join(reason_parts)

                return BetTarget(
                    status=status,
                    confidence=confidence,
                    method=cond['method'],
                    combination=combo,
                    odds=odds,
                    odds_range=odds_range,
                    c1_rank=c1_rank,
                    expected_roi=cond['expected_roi'],
                    bet_amount=cond['bet_amount'],
                    reason=reason
                )

        # オッズが範囲外の場合、候補として返す（直前情報でオッズが変動する可能性）
        if not has_beforeinfo and (old_odds or new_odds):
            # 最も近い条件を探す
            best_cond = conditions[0]
            method = best_cond['method']
            combo = old_combo if method == '従来' else new_combo
            odds = old_odds if method == '従来' else new_odds
            odds_range = f"{best_cond['odds_min']}倍+" if best_cond['odds_max'] >= 9999 else f"{best_cond['odds_min']}-{best_cond['odds_max']}倍"

            if odds and odds < best_cond['odds_min']:
                return BetTarget(
                    status=BetStatus.CANDIDATE,
                    confidence=confidence,
                    method=method,
                    combination=combo,
                    odds=odds,
                    odds_range=odds_range,
                    c1_rank=c1_rank,
                    expected_roi=best_cond['expected_roi'],
                    bet_amount=best_cond['bet_amount'],
                    reason=f'オッズ{odds:.1f}倍（{odds_range}で対象）。直前情報で変動の可能性',
                    needs_beforeinfo=True
                )

        # 条件を満たさない
        return BetTarget(
            status=BetStatus.EXCLUDED,
            confidence=confidence,
            method='-',
            combination='-',
            odds=old_odds or new_odds,
            odds_range='-',
            c1_rank=c1_rank,
            expected_roi=0,
            bet_amount=0,
            reason='オッズ範囲外または条件不一致'
        )

    def evaluate_race(
        self,
        race_data: Dict[str, Any],
        predictions: Dict[str, Any],
        odds_data: Optional[Dict[str, float]] = None,
        has_beforeinfo: bool = False
    ) -> BetTarget:
        """
        レースデータから購入対象を判定する

        Args:
            race_data: レース情報（entries含む）
            predictions: 予測情報（confidence, old_pred, new_pred）
            odds_data: オッズデータ {combination: odds}
            has_beforeinfo: 直前情報が取得済みか

        Returns:
            BetTarget: 購入対象情報
        """
        # 1コース選手の級別を取得
        entries = race_data.get('entries', [])
        c1_entry = next((e for e in entries if e.get('pit_number') == 1), None)
        c1_rank = c1_entry.get('racer_rank', 'B1') if c1_entry else 'B1'

        # 会場コードを取得
        venue_code = race_data.get('venue_code')

        # 気象データを取得
        wind_speed = race_data.get('wind_speed', 0.0)

        # 予測情報
        confidence = predictions.get('confidence', 'D')
        old_pred = predictions.get('old_prediction', [1, 2, 3])
        new_pred = predictions.get('new_prediction', [1, 2, 3])

        # 風速・会場フィルター（2024-2025年分析ベース）
        if self.enable_venue_wind_filter and venue_code and wind_speed is not None:
            # venue_codeを文字列化（'01'-'24'形式）
            venue_code_str = f"{venue_code:02d}" if isinstance(venue_code, int) else str(venue_code).zfill(2)

            # 除外判定
            should_exclude, exclude_reason = should_exclude_race(
                venue_code=venue_code_str,
                wind_speed=wind_speed,
                confidence=confidence
            )

            if should_exclude:
                return BetTarget(
                    status=BetStatus.EXCLUDED,
                    confidence=confidence,
                    method='-',
                    combination='-',
                    odds=0,
                    odds_range='-',
                    c1_rank=c1_rank,
                    expected_roi=0,
                    bet_amount=0,
                    reason=f'風速・会場除外: {exclude_reason}'
                )

        # 買い目
        old_combo = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
        new_combo = f"{new_pred[0]}-{new_pred[1]}-{new_pred[2]}"

        # オッズ
        old_odds = odds_data.get(old_combo, 0) if odds_data else 0
        new_odds = odds_data.get(new_combo, 0) if odds_data else 0

        # 基本的な購入対象判定
        bet_target = self.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=old_combo,
            new_combo=new_combo,
            old_odds=old_odds,
            new_odds=new_odds,
            has_beforeinfo=has_beforeinfo,
            venue_code=venue_code
        )

        # 会場×コース別調整を適用
        venue_course_adj_result = None
        if self.enable_venue_course_adjustment and self.venue_course_adjuster and venue_code:
            venue_code_str = f"{venue_code:02d}" if isinstance(venue_code, int) else str(venue_code).zfill(2)

            # 1着予測のコースに対する調整を計算
            first_course = old_pred[0] if old_pred else 1
            venue_course_adj_result = self.venue_course_adjuster.apply_adjustment_with_details(
                base_score=0,  # 調整量のみを取得
                venue_code=venue_code_str,
                course=first_course
            )

            # 理由に会場コース調整情報を追加
            if bet_target.status in [BetStatus.TARGET_CONFIRMED, BetStatus.TARGET_ADVANCE]:
                if venue_course_adj_result.adjustment != 0:
                    adj_str = f"+{venue_course_adj_result.adjustment}" if venue_course_adj_result.adjustment > 0 else str(venue_course_adj_result.adjustment)
                    bet_target.reason = f"{bet_target.reason} | 会場調整: {venue_course_adj_result.venue_name}{first_course}コース{adj_str}pt"

            bet_target.venue_course_adjustment = venue_course_adj_result

        # 購入対象の場合、複数点買いを生成
        if self.use_multi_bet and bet_target.status in [BetStatus.TARGET_CONFIRMED, BetStatus.TARGET_ADVANCE]:
            # 予測の全順位を取得（最低4艇必要）
            full_prediction = predictions.get('full_prediction')
            if full_prediction is None:
                # old_predictionから推測（拡張が必要な場合）
                full_prediction = list(old_pred)
                # 不足分は1-6から補填
                for i in range(1, 7):
                    if i not in full_prediction:
                        full_prediction.append(i)
                full_prediction = full_prediction[:6]

            if len(full_prediction) >= 4 and odds_data:
                try:
                    multi_bet_result = self.multi_bet_generator.generate(
                        predictions=full_prediction,
                        odds_dict=odds_data
                    )
                    bet_target.multi_bet_result = multi_bet_result
                except Exception as e:
                    # 複数点買い生成失敗時は1点買いのまま継続
                    pass

        return bet_target

    def get_summary(self, targets: List[BetTarget]) -> Dict[str, Any]:
        """
        複数レースの購入対象サマリーを取得

        Args:
            targets: BetTargetのリスト

        Returns:
            サマリー情報
        """
        summary = {
            'total': len(targets),
            'target_advance': 0,
            'candidate': 0,
            'target_confirmed': 0,
            'excluded': 0,
            'total_bet': 0,
            'expected_return': 0,
        }

        for t in targets:
            if t.status == BetStatus.TARGET_ADVANCE:
                summary['target_advance'] += 1
                summary['total_bet'] += t.bet_amount
                summary['expected_return'] += t.bet_amount * t.expected_roi / 100
            elif t.status == BetStatus.CANDIDATE:
                summary['candidate'] += 1
            elif t.status == BetStatus.TARGET_CONFIRMED:
                summary['target_confirmed'] += 1
                summary['total_bet'] += t.bet_amount
                summary['expected_return'] += t.bet_amount * t.expected_roi / 100
            else:
                summary['excluded'] += 1

        return summary

    def evaluate_exacta(
        self,
        confidence: str,
        c1_rank: str,
        pred_1st: int,
        pred_2nd: int,
    ) -> ExactaBetTarget:
        """
        2連単の購入対象を判定する

        Args:
            confidence: 信頼度 (A/B/C/D)
            c1_rank: 1コース選手の級別 (A1/A2/B1/B2)
            pred_1st: 1着予測の艇番
            pred_2nd: 2着予測の艇番

        Returns:
            ExactaBetTarget: 2連単購入対象情報
        """
        combination = f"{pred_1st}-{pred_2nd}"

        # 2連単の条件をチェック
        cond = self.EXACTA_CONDITIONS.get(confidence)
        if not cond:
            return ExactaBetTarget(
                status=BetStatus.EXCLUDED,
                confidence=confidence,
                combination=combination,
                c1_rank=c1_rank,
                expected_roi=0,
                bet_amount=0,
                reason=f'信頼度{confidence}は2連単対象外'
            )

        # 級別チェック
        if c1_rank not in cond['c1_rank']:
            return ExactaBetTarget(
                status=BetStatus.EXCLUDED,
                confidence=confidence,
                combination=combination,
                c1_rank=c1_rank,
                expected_roi=0,
                bet_amount=0,
                reason=f'1コース{c1_rank}級は2連単対象外'
            )

        # 条件を満たす
        return ExactaBetTarget(
            status=BetStatus.TARGET_ADVANCE,
            confidence=confidence,
            combination=combination,
            c1_rank=c1_rank,
            expected_roi=cond['expected_roi'],
            bet_amount=cond['bet_amount'],
            reason=f'信頼度{confidence} × 1コース{c1_rank} × 2連単'
        )

    def evaluate_race_exacta(
        self,
        race_data: Dict[str, Any],
        predictions: Dict[str, Any],
    ) -> ExactaBetTarget:
        """
        レースデータから2連単の購入対象を判定する

        Args:
            race_data: レース情報（entries含む）
            predictions: 予測情報（confidence, old_pred）

        Returns:
            ExactaBetTarget: 2連単購入対象情報
        """
        # 1コース選手の級別を取得
        entries = race_data.get('entries', [])
        c1_entry = next((e for e in entries if e.get('pit_number') == 1), None)
        c1_rank = c1_entry.get('racer_rank', 'B1') if c1_entry else 'B1'

        # 予測情報
        confidence = predictions.get('confidence', 'D')
        old_pred = predictions.get('old_prediction', [1, 2, 3])

        return self.evaluate_exacta(
            confidence=confidence,
            c1_rank=c1_rank,
            pred_1st=old_pred[0],
            pred_2nd=old_pred[1],
        )

    def evaluate_all(
        self,
        race_data: Dict[str, Any],
        predictions: Dict[str, Any],
        odds_data: Optional[Dict[str, float]] = None,
        has_beforeinfo: bool = False
    ) -> Dict[str, Any]:
        """
        レースの全購入対象を判定する（3連単 + 2連単）

        Args:
            race_data: レース情報（entries含む）
            predictions: 予測情報
            odds_data: オッズデータ
            has_beforeinfo: 直前情報が取得済みか

        Returns:
            {'trifecta': BetTarget, 'exacta': ExactaBetTarget}
        """
        trifecta = self.evaluate_race(race_data, predictions, odds_data, has_beforeinfo)
        exacta = self.evaluate_race_exacta(race_data, predictions)

        return {
            'trifecta': trifecta,
            'exacta': exacta,
        }
