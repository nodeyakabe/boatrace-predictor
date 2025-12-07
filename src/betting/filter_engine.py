# -*- coding: utf-8 -*-
"""
レース選別エンジン（除外条件強化版）

Phase A-⑤: 買わない条件の明文化
"""

from typing import Dict, Any, Tuple, List, Optional
from dataclasses import dataclass

from .config import (
    EXCLUDED_CONFIDENCE,
    EXCLUDED_C1_RANKS,
    MAX_WIND_GAP,
    MIN_ENTRY_CONFIDENCE,
    MIN_EDGE,
    BET_CONDITIONS,
    EXACTA_CONDITIONS,
    get_odds_range,
    get_venue_type,
    get_feature,
)


@dataclass
class FilterResult:
    """フィルタ結果"""
    is_target: bool          # 購入対象か
    exclusion_reason: str    # 除外理由（対象の場合は空文字）
    applied_rules: List[str] # 適用したルール名


class FilterEngine:
    """
    レース選別エンジン

    除外条件を一元管理し、購入対象かどうかを判定
    """

    def __init__(self):
        """初期化"""
        self._build_exclusion_rules()

    def _build_exclusion_rules(self):
        """除外ルールを構築"""
        self.exclusion_rules = []

        # 基本除外条件（常に適用）
        self.exclusion_rules.extend([
            {
                'name': 'confidence',
                'description': '信頼度フィルター',
                'check': lambda r: r.get('confidence', 'D') in EXCLUDED_CONFIDENCE,
                'message': lambda r: f'信頼度{r.get("confidence")}は対象外',
                'always_apply': True,
            },
            {
                'name': 'c1_rank',
                'description': '1コース級別フィルター',
                'check': lambda r: r.get('c1_rank', 'B1') in EXCLUDED_C1_RANKS
                                   or r.get('c1_rank', 'B1') not in ['A1', 'A2'],
                'message': lambda r: f'1コース{r.get("c1_rank")}級は対象外',
                'always_apply': True,
            },
        ])

        # 強化除外条件（use_exclusion_rulesがTrueの時のみ）
        if get_feature('use_exclusion_rules'):
            self.exclusion_rules.extend([
                {
                    'name': 'wind_gap',
                    'description': '風速差フィルター',
                    'check': lambda r: (
                        abs(r.get('wind_forecast', 0) - r.get('wind_actual', 0)) > MAX_WIND_GAP
                        if r.get('wind_actual') is not None else False
                    ),
                    'message': lambda r: f'風速差が{MAX_WIND_GAP}m/s超',
                    'always_apply': False,
                },
                {
                    'name': 'low_entry_conf',
                    'description': '進入信頼度フィルター',
                    'check': lambda r: (
                        r.get('entry_confidence', 1.0) < MIN_ENTRY_CONFIDENCE
                        if r.get('entry_confidence') is not None else False
                    ),
                    'message': lambda r: f'進入信頼度{r.get("entry_confidence", 0):.2f}が{MIN_ENTRY_CONFIDENCE}未満',
                    'always_apply': False,
                },
                {
                    'name': 'no_edge',
                    'description': 'Edge不足フィルター',
                    'check': lambda r: (
                        r.get('edge', 0) < MIN_EDGE
                        if r.get('edge') is not None and get_feature('use_edge_filter') else False
                    ),
                    'message': lambda r: f'Edge {r.get("edge", 0):.3f}がマイナス',
                    'always_apply': False,
                },
                {
                    'name': 'odds_out_of_range',
                    'description': 'オッズ範囲外フィルター',
                    'check': self._check_odds_range,
                    'message': lambda r: self._get_odds_range_message(r),
                    'always_apply': False,
                },
            ])

    def _check_odds_range(self, race_data: Dict[str, Any]) -> bool:
        """オッズが範囲外かチェック"""
        odds = race_data.get('odds')
        if odds is None or odds == 0:
            return False  # オッズ不明は除外しない（別途判定）

        venue_code = race_data.get('venue_code', 0)
        if isinstance(venue_code, str):
            venue_code = int(venue_code) if venue_code.isdigit() else 0
        if get_feature('use_venue_odds') and venue_code > 0:
            min_odds, max_odds = get_odds_range(venue_code)
        else:
            min_odds, max_odds = 20, 60

        return not (min_odds <= odds < max_odds)

    def _get_odds_range_message(self, race_data: Dict[str, Any]) -> str:
        """オッズ範囲外のメッセージ"""
        odds = race_data.get('odds', 0)
        venue_code = race_data.get('venue_code', 0)
        if isinstance(venue_code, str):
            venue_code = int(venue_code) if venue_code.isdigit() else 0
        if get_feature('use_venue_odds') and venue_code > 0:
            min_odds, max_odds = get_odds_range(venue_code)
            venue_type = get_venue_type(venue_code)
            return f'オッズ{odds:.1f}倍が{venue_type}場の範囲({min_odds}-{max_odds})外'
        else:
            return f'オッズ{odds:.1f}倍が範囲(20-60)外'

    def is_target_race(self, race_data: Dict[str, Any]) -> FilterResult:
        """
        購入対象レースか判定

        Args:
            race_data: レース情報
                {
                    'confidence': 'D',
                    'c1_rank': 'A1',
                    'odds': 35.5,
                    'venue_code': 18,
                    'wind_forecast': 3,
                    'wind_actual': 4,
                    'entry_confidence': 0.85,
                    'edge': 0.12,
                    ...
                }

        Returns:
            FilterResult: フィルタ結果
        """
        applied_rules = []

        for rule in self.exclusion_rules:
            if rule['check'](race_data):
                return FilterResult(
                    is_target=False,
                    exclusion_reason=rule['message'](race_data),
                    applied_rules=[rule['name']]
                )
            applied_rules.append(rule['name'])

        return FilterResult(
            is_target=True,
            exclusion_reason='',
            applied_rules=applied_rules
        )

    def get_applicable_conditions(
        self,
        confidence: str,
        c1_rank: str,
        odds: Optional[float] = None,
        venue_code: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        適用可能な購入条件を取得

        Args:
            confidence: 信頼度 (C/D)
            c1_rank: 1コース級別 (A1/A2)
            odds: オッズ
            venue_code: 会場コード

        Returns:
            適用可能な条件リスト
        """
        if confidence in EXCLUDED_CONFIDENCE:
            return []

        if c1_rank in EXCLUDED_C1_RANKS or c1_rank not in ['A1', 'A2']:
            return []

        conditions = BET_CONDITIONS.get(confidence, [])
        applicable = []

        for cond in conditions:
            if c1_rank not in cond['c1_rank']:
                continue

            # オッズ範囲
            if odds is not None:
                # 場タイプ別オッズレンジを使用する場合
                if get_feature('use_venue_odds') and venue_code:
                    min_odds, max_odds = get_odds_range(venue_code)
                else:
                    min_odds = cond['odds_min']
                    max_odds = cond['odds_max']

                if not (min_odds <= odds < max_odds):
                    continue

            applicable.append(cond)

        return applicable

    def check_exacta_condition(
        self,
        confidence: str,
        c1_rank: str
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        2連単の購入条件をチェック

        Args:
            confidence: 信頼度
            c1_rank: 1コース級別

        Returns:
            (is_target, condition)
        """
        cond = EXACTA_CONDITIONS.get(confidence)
        if not cond:
            return False, None

        if c1_rank not in cond['c1_rank']:
            return False, None

        return True, cond

    def get_active_rules(self) -> List[Dict[str, str]]:
        """
        現在有効なルールの一覧を取得

        Returns:
            [{'name': 'xxx', 'description': 'yyy'}, ...]
        """
        return [
            {'name': r['name'], 'description': r['description']}
            for r in self.exclusion_rules
        ]
