# -*- coding: utf-8 -*-
"""
レース選別エンジン（除外条件強化版）

Phase A-⑤: 買わない条件の明文化
P-1タスク: 前付け常習者除外フィルター追加（2025-12-20）
P-2タスク: 4年間パターン分析に基づくネガティブフィルタ追加（2025-12-21）
P-2追加: ポジティブフィルタ（穴狙い条件）追加（2025-12-21）
"""

import json
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional, Set
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

# 機能フラグ（config/feature_flags.pyから取得）
try:
    from config.feature_flags import is_feature_enabled
except ImportError:
    def is_feature_enabled(name: str) -> bool:
        return False


def load_forward_movers() -> Set[str]:
    """前付け常習者リストを読み込む"""
    forward_movers_path = Path(__file__).parent.parent.parent / "config" / "forward_movers.json"
    try:
        with open(forward_movers_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(str(rn) for rn in data.get('racer_numbers', []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


# 前付け常習者リスト（モジュール読み込み時に一度だけロード）
FORWARD_MOVERS = load_forward_movers()


@dataclass
class FilterResult:
    """フィルタ結果"""
    is_target: bool          # 購入対象か
    exclusion_reason: str    # 除外理由（対象の場合は空文字）
    applied_rules: List[str] # 適用したルール名
    is_upset_pattern: bool = False  # 穴狙いパターンで復活したか
    upset_reason: str = ''   # 穴狙い理由


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

        # 前付け常習者フィルター（P-1タスク: 2025-12-20追加）
        if is_feature_enabled('forward_mover_filter'):
            self.exclusion_rules.append({
                'name': 'forward_mover',
                'description': '前付け常習者フィルター',
                'check': self._check_forward_mover,
                'message': self._get_forward_mover_message,
                'always_apply': True,
            })

        # ネガティブパターンフィルター（P-2タスク: 2025-12-21追加）
        # 4年間パターン分析（Opus）で発見された安定マイナスROIパターンを除外
        if is_feature_enabled('negative_pattern_filter'):
            self.exclusion_rules.extend([
                {
                    'name': 'mid_odds_outer_course',
                    'description': 'オッズ10-30倍×予測1着3/4コース除外',
                    'check': self._check_mid_odds_outer_course,
                    'message': lambda r: f'オッズ{r.get("odds", 0):.1f}倍×予測1着{r.get("predicted_1st_course")}コース（ROI-40%パターン）',
                    'always_apply': True,
                },
                {
                    'name': 'high_odds_6th_course',
                    'description': 'オッズ100倍以上×予測1着6コース除外',
                    'check': self._check_high_odds_6th_course,
                    'message': lambda r: 'オッズ100倍以上×予測1着6コース（的中率0%）',
                    'always_apply': True,
                },
                {
                    'name': 'chaotic_venue_1st_course',
                    'description': '荒れ会場×予測1着1コース除外',
                    'check': self._check_chaotic_venue_1st_course,
                    'message': lambda r: f'荒れ会場（{r.get("venue_code")}）×予測1着1コース（的中率1.5-2%）',
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

    def _check_forward_mover(self, race_data: Dict[str, Any]) -> bool:
        """前付け常習者がいるかチェック"""
        racer_numbers = race_data.get('racer_numbers', [])
        if not racer_numbers:
            return False

        # レース出走者の中に前付け常習者がいるか
        for rn in racer_numbers:
            if str(rn) in FORWARD_MOVERS:
                return True
        return False

    def _get_forward_mover_message(self, race_data: Dict[str, Any]) -> str:
        """前付け常習者フィルターのメッセージ"""
        racer_numbers = race_data.get('racer_numbers', [])
        found_movers = [str(rn) for rn in racer_numbers if str(rn) in FORWARD_MOVERS]
        return f'前付け常習者あり（選手番号: {", ".join(found_movers)}）'

    def _check_mid_odds_outer_course(self, race_data: Dict[str, Any]) -> bool:
        """オッズ10-30倍×予測1着3/4コースをチェック（ROI-40%パターン）"""
        odds = race_data.get('odds')
        predicted_1st_course = race_data.get('predicted_1st_course')

        if odds is None or predicted_1st_course is None:
            return False

        # オッズ10-30倍かつ予測1着が3コースまたは4コース
        if 10 <= odds < 30 and predicted_1st_course in [3, 4]:
            return True
        return False

    def _check_high_odds_6th_course(self, race_data: Dict[str, Any]) -> bool:
        """オッズ100倍以上×予測1着6コースをチェック（的中率0%パターン）"""
        odds = race_data.get('odds')
        predicted_1st_course = race_data.get('predicted_1st_course')

        if odds is None or predicted_1st_course is None:
            return False

        # オッズ100倍以上かつ予測1着が6コース
        if odds >= 100 and predicted_1st_course == 6:
            return True
        return False

    def _check_chaotic_venue_1st_course(self, race_data: Dict[str, Any]) -> bool:
        """荒れ会場（江戸川/戸田/平和島）×予測1着1コースをチェック（的中率1.5-2%）"""
        venue_code = race_data.get('venue_code')
        predicted_1st_course = race_data.get('predicted_1st_course')

        if venue_code is None or predicted_1st_course is None:
            return False

        # venue_codeを文字列に統一
        venue_str = str(venue_code).zfill(2)

        # 荒れ会場: 江戸川(03), 戸田(02), 平和島(04)
        chaotic_venues = {'02', '03', '04'}

        if venue_str in chaotic_venues and predicted_1st_course == 1:
            return True
        return False

    def _check_upset_pattern_5th_course(self, race_data: Dict[str, Any]) -> bool:
        """穴狙いパターン: オッズ30-100倍×予測1着5コース（安定ROI +10%以上）"""
        odds = race_data.get('odds')
        predicted_1st_course = race_data.get('predicted_1st_course')

        if odds is None or predicted_1st_course is None:
            return False

        # オッズ30-100倍かつ予測1着が5コース
        if 30 <= odds < 100 and predicted_1st_course == 5:
            return True
        return False

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
                    'predicted_1st_course': 5,  # 穴狙い判定用
                    ...
                }

        Returns:
            FilterResult: フィルタ結果
        """
        applied_rules = []
        exclusion_reason = ''
        excluded_by_rule = None

        for rule in self.exclusion_rules:
            if rule['check'](race_data):
                exclusion_reason = rule['message'](race_data)
                excluded_by_rule = rule['name']
                break
            applied_rules.append(rule['name'])

        # 除外された場合でも、ポジティブフィルタ（穴狙い条件）をチェック
        if excluded_by_rule and is_feature_enabled('upset_pattern_filter'):
            # オッズ30-100倍×予測1着5コース → 安定ROI +10%以上
            if self._check_upset_pattern_5th_course(race_data):
                return FilterResult(
                    is_target=True,
                    exclusion_reason='',
                    applied_rules=applied_rules + ['upset_pattern_5th_course'],
                    is_upset_pattern=True,
                    upset_reason='オッズ30-100倍×予測1着5コース（安定ROI+10%以上）で復活'
                )
            # 除外を適用
            return FilterResult(
                is_target=False,
                exclusion_reason=exclusion_reason,
                applied_rules=[excluded_by_rule]
            )

        if excluded_by_rule:
            return FilterResult(
                is_target=False,
                exclusion_reason=exclusion_reason,
                applied_rules=[excluded_by_rule]
            )

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
