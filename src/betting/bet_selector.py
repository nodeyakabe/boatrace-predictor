# -*- coding: utf-8 -*-
"""
買い目選択エンジン（動的配分対応版）

Phase B-④: 動的資金配分
レースコンテキストに応じて3連単/2連単の配分を動的に調整
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .config import (
    BET_UNIT,
    BET_CONDITIONS,
    EXACTA_CONDITIONS,
    ALLOCATION_CONFIG,
    get_odds_range,
    get_feature,
)
from .ev_calculator import EVCalculator, EVResult
from .filter_engine import FilterEngine, FilterResult


class BetType(Enum):
    """賭け式"""
    TRIFECTA = 'trifecta'  # 3連単
    EXACTA = 'exacta'      # 2連単


@dataclass
class BetDecision:
    """購入判定結果"""
    should_buy: bool             # 購入するか
    bet_type: BetType            # 賭け式
    combination: str             # 買い目（例: "1-2-3"）
    odds: Optional[float]        # オッズ
    bet_amount: int              # 賭け金（円）
    ev: float                    # 期待値
    edge: float                  # Edge
    confidence: str              # 信頼度
    method: str                  # 方式（従来/新方式）
    reason: str                  # 判定理由
    logic_version: str           # ロジックバージョン


@dataclass
class RaceBetPlan:
    """レース単位の購入計画"""
    race_id: str                 # レースID
    trifecta: Optional[BetDecision]   # 3連単
    exacta: Optional[BetDecision]     # 2連単
    total_bet: int               # 合計賭け金
    allocation: Dict[str, float] # 配分比率


class DynamicAllocator:
    """
    動的資金配分

    レースコンテキストに応じて3連単/2連単の配分を調整
    """

    def __init__(self):
        """初期化"""
        self.base_ratio = ALLOCATION_CONFIG['base_ratio']
        self.high_edge_ratio = ALLOCATION_CONFIG['high_edge_ratio']
        self.upset_ratio = ALLOCATION_CONFIG['upset_ratio']

    def calc_allocation(self, race_context: Dict[str, Any]) -> Dict[str, float]:
        """
        レースコンテキストから配分を決定

        Args:
            race_context: {
                'confidence': 'D',
                'edge': 0.15,
                'is_upset_likely': False,
                'venue_type': 'high_in',
            }

        Returns:
            {'trifecta': 0.7, 'exacta': 0.3}
        """
        if not get_feature('use_dynamic_alloc'):
            return self.base_ratio

        edge = race_context.get('edge', 0)
        is_upset_likely = race_context.get('is_upset_likely', False)
        venue_type = race_context.get('venue_type', 'default')

        # Edge高い日: 3連単に寄せる（確信度が高い）
        if edge > 0.20:
            return self.high_edge_ratio

        # 荒れそうな場（差し場、荒れ水面）: 2連単に寄せる
        if venue_type in ['sashi', 'rough'] or is_upset_likely:
            return self.upset_ratio

        # 通常
        return self.base_ratio

    def apply_allocation(
        self,
        trifecta_amount: int,
        exacta_amount: int,
        allocation: Dict[str, float]
    ) -> Tuple[int, int]:
        """
        配分比率を適用して賭け金を調整

        Args:
            trifecta_amount: 3連単の基本賭け金
            exacta_amount: 2連単の基本賭け金
            allocation: 配分比率

        Returns:
            (調整後の3連単賭け金, 調整後の2連単賭け金)
        """
        total = trifecta_amount + exacta_amount
        if total == 0:
            return 0, 0

        # 配分比率に応じて再計算
        tri_ratio = allocation.get('trifecta', 0.7)
        exa_ratio = allocation.get('exacta', 0.3)

        # 実際に購入する方に合わせて調整
        if trifecta_amount > 0 and exacta_amount > 0:
            # 両方購入する場合
            new_trifecta = int(total * tri_ratio / 100) * 100
            new_exacta = int(total * exa_ratio / 100) * 100
            return max(100, new_trifecta), max(100, new_exacta)
        elif trifecta_amount > 0:
            return trifecta_amount, 0
        else:
            return 0, exacta_amount


class BetSelector:
    """
    買い目選択エンジン

    フィルタリング → EV計算 → 動的配分 → 買い目決定
    """

    def __init__(self):
        """初期化"""
        self.filter_engine = FilterEngine()
        self.ev_calculator = EVCalculator()
        self.allocator = DynamicAllocator()

    def select_bets(
        self,
        race_data: Dict[str, Any],
        predictions: Dict[str, Any],
        odds_data: Optional[Dict[str, float]] = None
    ) -> RaceBetPlan:
        """
        レースの買い目を選択

        Args:
            race_data: レース情報
                {
                    'race_id': 'xxxxx',
                    'venue_code': 18,
                    'entries': [...],
                    ...
                }
            predictions: 予測情報
                {
                    'confidence': 'D',
                    'old_prediction': [1, 2, 3],
                    'new_prediction': [1, 3, 2],
                }
            odds_data: オッズデータ
                {'1-2-3': 35.5, ...}

        Returns:
            RaceBetPlan
        """
        race_id = race_data.get('race_id', 'unknown')
        venue_code = race_data.get('venue_code', 0)
        confidence = predictions.get('confidence', 'D')

        # 1コース選手の級別を取得
        entries = race_data.get('entries', [])
        c1_entry = next((e for e in entries if e.get('pit_number') == 1), None)
        c1_rank = c1_entry.get('racer_rank', 'B1') if c1_entry else 'B1'

        # 予測買い目
        old_pred = predictions.get('old_prediction', [1, 2, 3])
        new_pred = predictions.get('new_prediction', [1, 2, 3])
        old_combo = f"{old_pred[0]}-{old_pred[1]}-{old_pred[2]}"
        new_combo = f"{new_pred[0]}-{new_pred[1]}-{new_pred[2]}"

        # オッズ取得
        old_odds = odds_data.get(old_combo, 0) if odds_data else 0
        new_odds = odds_data.get(new_combo, 0) if odds_data else 0

        # 3連単の判定
        trifecta_decision = self._evaluate_trifecta(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=old_combo,
            new_combo=new_combo,
            old_odds=old_odds,
            new_odds=new_odds,
            venue_code=venue_code
        )

        # 2連単の判定
        exacta_decision = self._evaluate_exacta(
            confidence=confidence,
            c1_rank=c1_rank,
            pred_1st=old_pred[0],
            pred_2nd=old_pred[1]
        )

        # 動的配分
        race_context = {
            'confidence': confidence,
            'edge': trifecta_decision.edge if trifecta_decision.should_buy else 0,
            'is_upset_likely': c1_rank not in ['A1', 'A2'],
            'venue_type': self._get_venue_type(venue_code),
        }
        allocation = self.allocator.calc_allocation(race_context)

        # 賭け金調整
        tri_amount = trifecta_decision.bet_amount if trifecta_decision.should_buy else 0
        exa_amount = exacta_decision.bet_amount if exacta_decision.should_buy else 0

        if get_feature('use_dynamic_alloc'):
            tri_amount, exa_amount = self.allocator.apply_allocation(
                tri_amount, exa_amount, allocation
            )
            # 調整後の金額を反映
            if trifecta_decision.should_buy:
                trifecta_decision = BetDecision(
                    should_buy=trifecta_decision.should_buy,
                    bet_type=trifecta_decision.bet_type,
                    combination=trifecta_decision.combination,
                    odds=trifecta_decision.odds,
                    bet_amount=tri_amount,
                    ev=trifecta_decision.ev,
                    edge=trifecta_decision.edge,
                    confidence=trifecta_decision.confidence,
                    method=trifecta_decision.method,
                    reason=trifecta_decision.reason,
                    logic_version=trifecta_decision.logic_version
                )
            if exacta_decision.should_buy:
                exacta_decision = BetDecision(
                    should_buy=exacta_decision.should_buy,
                    bet_type=exacta_decision.bet_type,
                    combination=exacta_decision.combination,
                    odds=exacta_decision.odds,
                    bet_amount=exa_amount,
                    ev=exacta_decision.ev,
                    edge=exacta_decision.edge,
                    confidence=exacta_decision.confidence,
                    method=exacta_decision.method,
                    reason=exacta_decision.reason,
                    logic_version=exacta_decision.logic_version
                )

        return RaceBetPlan(
            race_id=race_id,
            trifecta=trifecta_decision if trifecta_decision.should_buy else None,
            exacta=exacta_decision if exacta_decision.should_buy else None,
            total_bet=tri_amount + exa_amount,
            allocation=allocation
        )

    def _evaluate_trifecta(
        self,
        confidence: str,
        c1_rank: str,
        old_combo: str,
        new_combo: str,
        old_odds: float,
        new_odds: float,
        venue_code: int
    ) -> BetDecision:
        """3連単の購入判定"""
        from .config import LOGIC_VERSION

        # フィルタチェック用のデータ作成
        filter_data = {
            'confidence': confidence,
            'c1_rank': c1_rank,
            'venue_code': venue_code,
        }
        filter_result = self.filter_engine.is_target_race(filter_data)

        if not filter_result.is_target:
            return BetDecision(
                should_buy=False,
                bet_type=BetType.TRIFECTA,
                combination='',
                odds=None,
                bet_amount=0,
                ev=0,
                edge=0,
                confidence=confidence,
                method='',
                reason=filter_result.exclusion_reason,
                logic_version=LOGIC_VERSION
            )

        # 購入条件をチェック
        conditions = BET_CONDITIONS.get(confidence, [])
        for cond in conditions:
            if c1_rank not in cond['c1_rank']:
                continue

            # 方式と買い目の決定
            if cond['method'] == '従来':
                combo = old_combo
                odds = old_odds
            else:
                combo = new_combo
                odds = new_odds

            # オッズ範囲
            if get_feature('use_venue_odds') and venue_code > 0:
                min_odds, max_odds = get_odds_range(venue_code)
            else:
                min_odds = cond['odds_min']
                max_odds = cond['odds_max']

            if odds is None or odds == 0:
                continue

            if not (min_odds <= odds < max_odds):
                continue

            # EV/Edge計算
            ev_result = self.ev_calculator.calc_ev_with_edge(
                confidence=confidence,
                odds=odds,
                bet_type='trifecta'
            )

            # Edge条件（use_edge_filterがONの場合）
            if get_feature('use_edge_filter') and ev_result.edge < 0:
                continue

            return BetDecision(
                should_buy=True,
                bet_type=BetType.TRIFECTA,
                combination=combo,
                odds=odds,
                bet_amount=cond['bet_amount'],
                ev=ev_result.ev,
                edge=ev_result.edge,
                confidence=confidence,
                method=cond['method'],
                reason=f'{confidence} × {cond["method"]} × {min_odds}-{max_odds}倍 × {c1_rank}',
                logic_version=LOGIC_VERSION
            )

        return BetDecision(
            should_buy=False,
            bet_type=BetType.TRIFECTA,
            combination='',
            odds=None,
            bet_amount=0,
            ev=0,
            edge=0,
            confidence=confidence,
            method='',
            reason='条件不一致',
            logic_version=LOGIC_VERSION
        )

    def _evaluate_exacta(
        self,
        confidence: str,
        c1_rank: str,
        pred_1st: int,
        pred_2nd: int
    ) -> BetDecision:
        """
        2連単の購入判定

        厳密な条件:
        - 信頼度Dのみ
        - 1コースA1級のみ
        - EV >= 1.0
        """
        from .config import LOGIC_VERSION, EV_THRESHOLD

        combo = f"{pred_1st}-{pred_2nd}"

        # ① 信頼度チェック: Dのみ
        if confidence != 'D':
            return BetDecision(
                should_buy=False,
                bet_type=BetType.EXACTA,
                combination=combo,
                odds=None,
                bet_amount=0,
                ev=0,
                edge=0,
                confidence=confidence,
                method='従来',
                reason=f'信頼度{confidence}は2連単対象外（Dのみ）',
                logic_version=LOGIC_VERSION
            )

        # ② 1コース級別チェック: A1のみ
        if c1_rank != 'A1':
            return BetDecision(
                should_buy=False,
                bet_type=BetType.EXACTA,
                combination=combo,
                odds=None,
                bet_amount=0,
                ev=0,
                edge=0,
                confidence=confidence,
                method='従来',
                reason=f'1コース{c1_rank}級は2連単対象外（A1のみ）',
                logic_version=LOGIC_VERSION
            )

        # EXACTA_CONDITIONS から条件取得
        cond = EXACTA_CONDITIONS.get(confidence)
        if not cond:
            return BetDecision(
                should_buy=False,
                bet_type=BetType.EXACTA,
                combination=combo,
                odds=None,
                bet_amount=0,
                ev=0,
                edge=0,
                confidence=confidence,
                method='従来',
                reason='2連単条件未定義',
                logic_version=LOGIC_VERSION
            )

        # ③ EV計算（2連単用）
        ev_result = self.ev_calculator.calc_ev_with_edge(
            confidence=confidence,
            odds=cond['expected_roi'] / 100 * 10,  # 仮のオッズ
            bet_type='exacta'
        )

        # ④ EV閾値チェック: EV >= 1.0
        if ev_result.ev < EV_THRESHOLD:
            return BetDecision(
                should_buy=False,
                bet_type=BetType.EXACTA,
                combination=combo,
                odds=None,
                bet_amount=0,
                ev=ev_result.ev,
                edge=ev_result.edge,
                confidence=confidence,
                method='従来',
                reason=f'EV {ev_result.ev:.2f}が閾値{EV_THRESHOLD}未満',
                logic_version=LOGIC_VERSION
            )

        return BetDecision(
            should_buy=True,
            bet_type=BetType.EXACTA,
            combination=combo,
            odds=None,  # 2連単は固定賭け
            bet_amount=cond['bet_amount'],
            ev=ev_result.ev,
            edge=ev_result.edge,
            confidence=confidence,
            method='従来',
            reason=f'D × A1 × 2連単 (EV={ev_result.ev:.2f})',
            logic_version=LOGIC_VERSION
        )

    def _get_venue_type(self, venue_code: int) -> str:
        """会場タイプを取得"""
        from .config import get_venue_type
        return get_venue_type(venue_code)

    def get_top_n_bets(
        self,
        bets: List[Dict[str, Any]],
        n: int = 5
    ) -> List[Dict[str, Any]]:
        """
        EV上位N件の買い目を取得

        Args:
            bets: 買い目リスト
            n: 上位件数

        Returns:
            上位N件
        """
        sorted_bets = self.ev_calculator.compare_bets(bets)
        return sorted_bets[:n]
