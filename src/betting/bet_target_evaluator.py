# -*- coding: utf-8 -*-
"""
購入対象判定モジュール

最終運用戦略に基づいて、レースが購入対象かどうかを判定する
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Any


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
    # 購入条件定義（2025年12月12日更新 - 戦略A再定義版）
    # ============================================================
    # 3連単完全一致方式によるバックテスト結果に基づく実運用可能な条件
    # - 戦略A（バランス型）: 年間ROI 159.9%, 収支 +53,190円
    # - 3層構造: Tier1(高配当主力) + Tier2(中配当補助) + Tier3(穴条件)
    # - 検証期間: 2025年全期間（296レース購入、12回的中、的中率4.1%）
    # - 注意: 収支が少ないため、今後の改善が必要
    # ============================================================
    BET_CONDITIONS = {
        # 信頼度C: 中配当補助（Tier2）
        'C': [
            # C × B1 × 40-60倍: ROI 188.3%, 収支 +7,950円
            # → Tier2: 中配当補助A
            {
                'method': '両方式',
                'odds_min': 40, 'odds_max': 60,
                'c1_rank': ['B1'],
                'expected_roi': 188.3,
                'bet_amount': 300,
                'priority': 1,
                'description': 'Tier2: C×B1級中配当A',
            },
            # C × B1 × 80-120倍: ROI 122.5%, 収支 +6,270円
            # → Tier2: 中配当補助B
            {
                'method': '両方式',
                'odds_min': 80, 'odds_max': 120,
                'c1_rank': ['B1'],
                'expected_roi': 122.5,
                'bet_amount': 300,
                'priority': 2,
                'description': 'Tier2: C×B1級中配当B',
            },
        ],
        # 信頼度D: 高配当主力（Tier1）+ 穴条件（Tier3）
        'D': [
            # ===== Tier 1: 高配当主力（ROI 192.8%） =====

            # D × B1 × 60-100倍: ROI 192.8%, 収支 +37,020円
            # → 最も収益貢献が大きい主力条件
            {
                'method': '両方式',
                'odds_min': 60, 'odds_max': 100,
                'c1_rank': ['B1'],
                'expected_roi': 192.8,
                'bet_amount': 300,
                'priority': 1,
                'description': 'Tier1: D×B1級高配当主力',
            },

            # ===== Tier 3: 穴条件（ROI 116.3%） =====

            # D × A2 × 30-100倍: ROI 116.3%, 収支 +1,950円
            # → 的中率7.5%で的中頻度向上に寄与
            {
                'method': '両方式',
                'odds_min': 30, 'odds_max': 100,
                'c1_rank': ['A2'],
                'expected_roi': 116.3,
                'bet_amount': 300,
                'priority': 2,
                'description': 'Tier3: D×A2級穴条件',
            },
        ],
    }

    # 除外条件
    # - 信頼度A, B: サンプル不足・安定性低
    EXCLUDED_CONFIDENCE = ['A', 'B']
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

    def __init__(self):
        pass

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
        # 信頼度チェック
        if confidence in self.EXCLUDED_CONFIDENCE:
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
                reason=f'信頼度{confidence}は購入対象外（サンプル不足）'
            )

        # 信頼度に応じた条件をチェック
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

        # 予測情報
        confidence = predictions.get('confidence', 'D')
        old_pred = predictions.get('old_prediction', [1, 2, 3])
        new_pred = predictions.get('new_prediction', [1, 2, 3])

        # 買い目
        old_combo = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
        new_combo = f"{new_pred[0]}-{new_pred[1]}-{new_pred[2]}"

        # オッズ
        old_odds = odds_data.get(old_combo, 0) if odds_data else 0
        new_odds = odds_data.get(new_combo, 0) if odds_data else 0

        return self.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=old_combo,
            new_combo=new_combo,
            old_odds=old_odds,
            new_odds=new_odds,
            has_beforeinfo=has_beforeinfo,
            venue_code=venue_code
        )

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
