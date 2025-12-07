# -*- coding: utf-8 -*-
"""
戦略エンジン（全体制御）

全モジュールを統合し、レースカードから買い目リストを生成
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from .config import (
    FEATURES,
    LOGIC_VERSION,
    SAFETY_CONFIG,
    BET_UNIT,
)
from .filter_engine import FilterEngine
from .ev_calculator import EVCalculator
from .bet_selector import BetSelector, RaceBetPlan, BetDecision
from .kelly_calculator import KellyCalculator
from .bet_logger import BetLogger, BetRecord


@dataclass
class DailyBetSummary:
    """日次購入サマリー"""
    date: str
    total_races: int
    target_races: int
    total_bets: int
    trifecta_bets: int
    exacta_bets: int
    total_amount: int
    avg_ev: float
    avg_edge: float
    logic_version: str


@dataclass
class StrategyResult:
    """戦略実行結果"""
    bet_plans: List[RaceBetPlan]
    summary: DailyBetSummary
    logs: List[BetRecord]
    warnings: List[str] = field(default_factory=list)


class StrategyEngine:
    """
    戦略エンジン

    フロー:
    1. filter_engine → 対象レース絞り込み
    2. ev_calculator → 期待値算出
    3. bet_selector → 買い目決定
    4. kelly_calculator → 賭け金調整（オプション）
    5. bet_logger → 記録
    """

    def __init__(
        self,
        bankroll: int = 100000,
        db_path: str = 'data/boatrace.db',
        log_dir: str = 'logs/betting'
    ):
        """
        初期化

        Args:
            bankroll: 資金（円）
            db_path: データベースパス
            log_dir: ログディレクトリ
        """
        self.bankroll = bankroll
        self.db_path = db_path

        # モジュール初期化
        self.filter_engine = FilterEngine()
        self.ev_calculator = EVCalculator()
        self.bet_selector = BetSelector()
        self.kelly_calculator = KellyCalculator(bankroll=bankroll)
        self.bet_logger = BetLogger(log_dir=log_dir)

        # 連敗カウンター
        self.loss_streak = 0
        self.daily_bet_count = 0

    def run(
        self,
        race_cards: List[Dict[str, Any]],
        date: str = None
    ) -> StrategyResult:
        """
        戦略を実行

        Args:
            race_cards: レースカードのリスト
                [
                    {
                        'race_data': {...},
                        'predictions': {...},
                        'odds_data': {...},
                    },
                    ...
                ]
            date: 日付（YYYY-MM-DD）

        Returns:
            StrategyResult
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        bet_plans = []
        logs = []
        warnings = []

        # 安全チェック
        if self._check_safety_stop():
            warnings.append(f'連敗{self.loss_streak}回で自動停止中')
            return StrategyResult(
                bet_plans=[],
                summary=self._create_empty_summary(date),
                logs=[],
                warnings=warnings
            )

        total_ev = 0
        total_edge = 0
        ev_count = 0

        for card in race_cards:
            # 日次購入上限チェック
            if self.daily_bet_count >= SAFETY_CONFIG['max_daily_bets']:
                warnings.append(f'日次購入上限{SAFETY_CONFIG["max_daily_bets"]}件に到達')
                break

            race_data = card.get('race_data', {})
            predictions = card.get('predictions', {})
            odds_data = card.get('odds_data', {})

            # 買い目選択
            plan = self.bet_selector.select_bets(
                race_data=race_data,
                predictions=predictions,
                odds_data=odds_data
            )

            # Kelly調整（機能ONの場合）
            if FEATURES.get('use_kelly', False) and plan.total_bet > 0:
                plan = self._apply_kelly(plan)

            # 購入対象がある場合
            if plan.total_bet > 0:
                bet_plans.append(plan)
                self.daily_bet_count += 1

                # EV/Edge集計
                if plan.trifecta:
                    total_ev += plan.trifecta.ev
                    total_edge += plan.trifecta.edge
                    ev_count += 1
                if plan.exacta:
                    total_ev += plan.exacta.ev
                    total_edge += plan.exacta.edge
                    ev_count += 1

                # ログ記録
                log = self._create_log(plan, date, race_data)
                logs.append(log)

        # サマリー作成
        summary = DailyBetSummary(
            date=date,
            total_races=len(race_cards),
            target_races=len(bet_plans),
            total_bets=len(bet_plans),
            trifecta_bets=sum(1 for p in bet_plans if p.trifecta),
            exacta_bets=sum(1 for p in bet_plans if p.exacta),
            total_amount=sum(p.total_bet for p in bet_plans),
            avg_ev=total_ev / ev_count if ev_count > 0 else 0,
            avg_edge=total_edge / ev_count if ev_count > 0 else 0,
            logic_version=LOGIC_VERSION
        )

        # ログ保存
        if logs:
            self.bet_logger.save_logs(logs, date)

        return StrategyResult(
            bet_plans=bet_plans,
            summary=summary,
            logs=logs,
            warnings=warnings
        )

    def run_single(
        self,
        race_data: Dict[str, Any],
        predictions: Dict[str, Any],
        odds_data: Optional[Dict[str, float]] = None
    ) -> RaceBetPlan:
        """
        単一レースの戦略を実行

        Args:
            race_data: レース情報
            predictions: 予測情報
            odds_data: オッズデータ

        Returns:
            RaceBetPlan
        """
        plan = self.bet_selector.select_bets(
            race_data=race_data,
            predictions=predictions,
            odds_data=odds_data
        )

        if FEATURES.get('use_kelly', False) and plan.total_bet > 0:
            plan = self._apply_kelly(plan)

        return plan

    def _apply_kelly(self, plan: RaceBetPlan) -> RaceBetPlan:
        """Kelly基準を適用して賭け金を調整"""
        # 3連単
        if plan.trifecta and plan.trifecta.odds:
            result = self.kelly_calculator.calc_optimal_bet(
                confidence=plan.trifecta.confidence,
                odds=plan.trifecta.odds
            )
            if result.is_bet:
                plan.trifecta = BetDecision(
                    should_buy=plan.trifecta.should_buy,
                    bet_type=plan.trifecta.bet_type,
                    combination=plan.trifecta.combination,
                    odds=plan.trifecta.odds,
                    bet_amount=result.bet_amount,
                    ev=plan.trifecta.ev,
                    edge=result.edge,
                    confidence=plan.trifecta.confidence,
                    method=plan.trifecta.method,
                    reason=plan.trifecta.reason + f' [Kelly:{result.reason}]',
                    logic_version=plan.trifecta.logic_version
                )

        # 合計再計算
        tri_amount = plan.trifecta.bet_amount if plan.trifecta else 0
        exa_amount = plan.exacta.bet_amount if plan.exacta else 0
        plan.total_bet = tri_amount + exa_amount

        return plan

    def _check_safety_stop(self) -> bool:
        """安全停止条件をチェック"""
        if self.loss_streak >= SAFETY_CONFIG['max_loss_streak']:
            return True
        if self.bankroll < SAFETY_CONFIG['min_bankroll']:
            return True
        return False

    def update_result(self, hit: bool, payout: int = 0):
        """
        結果を更新

        Args:
            hit: 的中したか
            payout: 払戻金
        """
        if hit:
            self.loss_streak = 0
            self.bankroll += payout
        else:
            self.loss_streak += 1

    def reset_daily(self):
        """日次カウンターをリセット"""
        self.daily_bet_count = 0

    def _create_log(
        self,
        plan: RaceBetPlan,
        date: str,
        race_data: Dict[str, Any]
    ) -> BetRecord:
        """ログレコードを作成"""
        return BetRecord(
            date=date,
            race_id=plan.race_id,
            venue_code=race_data.get('venue_code', 0),
            race_number=race_data.get('race_number', 0),
            bet_type='trifecta' if plan.trifecta else 'exacta',
            combination=plan.trifecta.combination if plan.trifecta else (plan.exacta.combination if plan.exacta else ''),
            odds=plan.trifecta.odds if plan.trifecta else None,
            bet_amount=plan.total_bet,
            ev=plan.trifecta.ev if plan.trifecta else (plan.exacta.ev if plan.exacta else 0),
            edge=plan.trifecta.edge if plan.trifecta else (plan.exacta.edge if plan.exacta else 0),
            confidence=plan.trifecta.confidence if plan.trifecta else (plan.exacta.confidence if plan.exacta else ''),
            method=plan.trifecta.method if plan.trifecta else 'exacta',
            logic_version=LOGIC_VERSION,
            result=None,
            payout=None,
            roi=None
        )

    def _create_empty_summary(self, date: str) -> DailyBetSummary:
        """空のサマリーを作成"""
        return DailyBetSummary(
            date=date,
            total_races=0,
            target_races=0,
            total_bets=0,
            trifecta_bets=0,
            exacta_bets=0,
            total_amount=0,
            avg_ev=0,
            avg_edge=0,
            logic_version=LOGIC_VERSION
        )

    def get_status(self) -> Dict[str, Any]:
        """エンジンの状態を取得"""
        return {
            'logic_version': LOGIC_VERSION,
            'features': FEATURES,
            'bankroll': self.bankroll,
            'loss_streak': self.loss_streak,
            'daily_bet_count': self.daily_bet_count,
            'safety_config': SAFETY_CONFIG,
            'active_rules': self.filter_engine.get_active_rules(),
        }

    def get_feature_status(self) -> Dict[str, bool]:
        """機能フラグの状態を取得"""
        return FEATURES.copy()


def create_engine(
    bankroll: int = 100000,
    use_edge: bool = True,
    use_venue_odds: bool = True,
    use_kelly: bool = False
) -> StrategyEngine:
    """
    カスタム設定でエンジンを作成

    Args:
        bankroll: 資金
        use_edge: Edge計算を使用するか
        use_venue_odds: 場タイプ別オッズを使用するか
        use_kelly: Kelly基準を使用するか

    Returns:
        StrategyEngine
    """
    # 一時的に設定を上書き
    FEATURES['use_edge_filter'] = use_edge
    FEATURES['use_venue_odds'] = use_venue_odds
    FEATURES['use_kelly'] = use_kelly

    return StrategyEngine(bankroll=bankroll)
