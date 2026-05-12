# -*- coding: utf-8 -*-
"""
複数点買い生成モジュール

戦略Bの複数点買いパターンを生成する
バックテスト結果に基づく最適パターンを実装
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum


class MultiBetPattern(Enum):
    """複数点買いパターン"""
    SINGLE = "single"                    # 現行: 1点買い
    PATTERN_H = "pattern_h"              # H: 1-2軸傾斜（200/100/100）- 最高収支
    PATTERN_H2 = "pattern_h2"            # H2: 1-2軸傾斜2点（200/100）- p5除外版（2026-04-08）
    PATTERN_B = "pattern_b"              # B: 1-2軸均等（100x3）- 最高ROI
    PATTERN_L = "pattern_l"              # L: 重点買い（300+100）
    PATTERN_I = "pattern_i"              # I: 2点買い（200+100）
    PATTERN_K = "pattern_k"              # K: 総合（150+100+50）- 最低MaxDD
    PATTERN_P142 = "pattern_p142"        # P142: p1-p4-p2 穴狙い（100円1点）- 2026-04-17追加
    PATTERN_P143 = "pattern_p143"        # P143: p1-p4-p3 穴狙い（100円1点）- 2026-04-17追加
    PATTERN_P132 = "pattern_p132"        # P132: p1-p3-p2 穴狙い（100円1点）- 2026-04-17追加
    PATTERN_P124 = "pattern_p124"        # P124: p1-p2-p4 穴狙い（100円1点）- 2026-04-20追加


@dataclass
class MultiBet:
    """複数点買い情報"""
    combination: str        # 買い目（例: "1-2-3"）
    odds: float            # オッズ
    bet_amount: int        # 賭け金
    priority: int          # 優先度（1が最優先）


@dataclass
class MultiBetResult:
    """複数点買い生成結果"""
    pattern: MultiBetPattern
    bets: List[MultiBet]
    total_investment: int
    description: str
    expected_hit_rate: float    # 期待的中率
    expected_roi: float         # 期待ROI


class MultiBetGenerator:
    """
    複数点買い生成クラス

    バックテスト結果（2025年データ）:
    ================================================
    パターン             収支        ROI      的中率
    ------------------------------------------------
    H: 傾斜200/100/100   +68,030円   127.3%   9.0%   ★推奨（収支最大）
    B: 均等100x3         +55,680円   130.3%   9.0%   ★推奨（ROI最大）
    L: 重点300+100       +55,910円   121.9%   7.1%
    I: 2点200+100        +43,560円   123.0%   7.1%
    K: 総合150+100+50    +39,995円   122.8%   8.4%   （MaxDD最小）
    現行1点買い          +37,050円   118.9%   3.5%
    ================================================
    """

    # パターン別の期待値（2025年バックテスト結果）
    PATTERN_STATS = {
        MultiBetPattern.SINGLE: {
            'hit_rate': 3.5,
            'roi': 118.9,
            'profit': 37050,
            'max_dd': 55830,
        },
        MultiBetPattern.PATTERN_H: {
            'hit_rate': 9.0,
            'roi': 127.3,
            'profit': 68030,
            'max_dd': 53050,
        },
        MultiBetPattern.PATTERN_B: {
            'hit_rate': 9.0,
            'roi': 130.3,
            'profit': 55680,
            'max_dd': 35770,
        },
        MultiBetPattern.PATTERN_L: {
            'hit_rate': 7.1,
            'roi': 121.9,
            'profit': 55910,
            'max_dd': 55320,
        },
        MultiBetPattern.PATTERN_I: {
            'hit_rate': 7.1,
            'roi': 123.0,
            'profit': 43560,
            'max_dd': 37320,
        },
        MultiBetPattern.PATTERN_K: {
            'hit_rate': 8.4,
            'roi': 122.8,
            'profit': 39995,
            'max_dd': 33075,
        },
    }

    def __init__(self, default_pattern: MultiBetPattern = MultiBetPattern.PATTERN_H):
        """
        初期化

        Args:
            default_pattern: デフォルトのパターン（推奨: PATTERN_H）
        """
        self.default_pattern = default_pattern

    def generate(
        self,
        predictions: List[int],
        odds_dict: Dict[str, float],
        pattern: Optional[MultiBetPattern] = None,
        odds_min: float = 0,
        odds_max: float = 9999,
        require_p123: bool = False,
    ) -> MultiBetResult:
        """
        複数点買いを生成

        Args:
            predictions: 予測順位（1位〜6位の艇番リスト）
            odds_dict: オッズ辞書 {combination: odds}
            pattern: 使用するパターン（Noneならデフォルト）
            odds_min: オッズ下限（パターンH/H2の各買い目に適用）
            odds_max: オッズ上限（パターンH/H2の各買い目に適用）
            require_p123: Trueのとき、p1-p2-p3が範囲内でなければ全買い目をスキップ

        Returns:
            MultiBetResult: 複数点買い結果
        """
        if pattern is None:
            pattern = self.default_pattern

        if len(predictions) < 4:
            raise ValueError("予測は最低4艇必要です")

        if pattern == MultiBetPattern.SINGLE:
            return self._generate_single(predictions, odds_dict)
        elif pattern == MultiBetPattern.PATTERN_H:
            return self._generate_pattern_h(predictions, odds_dict, odds_min, odds_max)
        elif pattern == MultiBetPattern.PATTERN_H2:
            return self._generate_pattern_h2(predictions, odds_dict, odds_min, odds_max, require_p123)
        elif pattern == MultiBetPattern.PATTERN_B:
            return self._generate_pattern_b(predictions, odds_dict)
        elif pattern == MultiBetPattern.PATTERN_L:
            return self._generate_pattern_l(predictions, odds_dict)
        elif pattern == MultiBetPattern.PATTERN_I:
            return self._generate_pattern_i(predictions, odds_dict)
        elif pattern == MultiBetPattern.PATTERN_K:
            return self._generate_pattern_k(predictions, odds_dict)
        elif pattern == MultiBetPattern.PATTERN_P142:
            return self._generate_pattern_p142(predictions, odds_dict)
        elif pattern == MultiBetPattern.PATTERN_P143:
            return self._generate_pattern_p143(predictions, odds_dict)
        elif pattern == MultiBetPattern.PATTERN_P132:
            return self._generate_pattern_p132(predictions, odds_dict)
        elif pattern == MultiBetPattern.PATTERN_P124:
            return self._generate_pattern_p124(predictions, odds_dict)
        else:
            raise ValueError(f"未知のパターン: {pattern}")

    def _generate_single(
        self, predictions: List[int], odds_dict: Dict[str, float]
    ) -> MultiBetResult:
        """現行: 1点買い（予測1-2-3のみ 300円）"""
        p1, p2, p3 = predictions[0], predictions[1], predictions[2]
        combo = f"{p1}-{p2}-{p3}"
        odds = odds_dict.get(combo, 0)

        bets = [MultiBet(combination=combo, odds=odds, bet_amount=300, priority=1)]

        stats = self.PATTERN_STATS[MultiBetPattern.SINGLE]
        return MultiBetResult(
            pattern=MultiBetPattern.SINGLE,
            bets=bets,
            total_investment=300,
            description="現行戦略: 予測1-2-3の1点買い（300円）",
            expected_hit_rate=stats['hit_rate'],
            expected_roi=stats['roi'],
        )

    def _generate_pattern_h(
        self, predictions: List[int], odds_dict: Dict[str, float],
        odds_min: float = 0, odds_max: float = 9999,
    ) -> MultiBetResult:
        """
        パターンH: 1-2軸傾斜配分（200/100/100）

        【最高収支パターン】
        - 1-2着は予測1-2位で固定
        - 3着候補は予測3-5位
        - 配分: 1点目200円、2-3点目100円ずつ
        - 各買い目のオッズが odds_min 以上 odds_max 未満の場合のみ投資
        """
        p1, p2 = predictions[0], predictions[1]
        third_candidates = [predictions[2], predictions[3], predictions[4]]
        bet_amounts = [200, 100, 100]

        bets = []
        priority = 1
        for i, third in enumerate(third_candidates):
            if third != p1 and third != p2:
                combo = f"{p1}-{p2}-{third}"
                odds = odds_dict.get(combo, 0)
                if odds_min <= odds < odds_max:
                    bets.append(MultiBet(
                        combination=combo,
                        odds=odds,
                        bet_amount=bet_amounts[min(i, len(bet_amounts)-1)],
                        priority=priority
                    ))
                    priority += 1

        total = sum(b.bet_amount for b in bets)
        stats = self.PATTERN_STATS[MultiBetPattern.PATTERN_H]

        return MultiBetResult(
            pattern=MultiBetPattern.PATTERN_H,
            bets=bets,
            total_investment=total,
            description="パターンH: 1-2軸3点傾斜配分（200/100/100円）",
            expected_hit_rate=stats['hit_rate'],
            expected_roi=stats['roi'],
        )

    def _generate_pattern_h2(
        self, predictions: List[int], odds_dict: Dict[str, float],
        odds_min: float = 0, odds_max: float = 9999,
        require_p123: bool = False,
    ) -> MultiBetResult:
        """
        パターンH2: 1-2軸2点傾斜配分（200/100）- p5除外版

        【p5廃止対応・2026-04-08】
        - 1-2着は予測1-2位で固定
        - 3着候補は予測3-4位のみ（p5除外）
        - 配分: 1点目200円、2点目100円
        - 各買い目のオッズが odds_min 以上 odds_max 未満の場合のみ投資
        - require_p123=True: p1-p2-p3が範囲内でなければ全買い目をスキップ
        """
        p1, p2 = predictions[0], predictions[1]
        third_candidates = [predictions[2], predictions[3]]  # p3, p4のみ
        bet_amounts = [200, 100]

        stats = self.PATTERN_STATS[MultiBetPattern.PATTERN_H]

        # p123必須フラグ: p1-p2-p3のオッズが範囲外なら空リストを返す
        if require_p123:
            p3 = third_candidates[0]
            if p3 != p1 and p3 != p2:
                combo_p123 = f"{p1}-{p2}-{p3}"
                odds_p123 = odds_dict.get(combo_p123, 0)
                if not (odds_min <= odds_p123 < odds_max):
                    return MultiBetResult(
                        pattern=MultiBetPattern.PATTERN_H2,
                        bets=[],
                        total_investment=0,
                        description="パターンH2: p123範囲外のためスキップ",
                        expected_hit_rate=stats['hit_rate'],
                        expected_roi=stats['roi'],
                    )

        bets = []
        priority = 1
        for i, third in enumerate(third_candidates):
            if third != p1 and third != p2:
                combo = f"{p1}-{p2}-{third}"
                odds = odds_dict.get(combo, 0)
                if odds_min <= odds < odds_max:
                    bets.append(MultiBet(
                        combination=combo,
                        odds=odds,
                        bet_amount=bet_amounts[i],
                        priority=priority
                    ))
                    priority += 1

        total = sum(b.bet_amount for b in bets)

        return MultiBetResult(
            pattern=MultiBetPattern.PATTERN_H2,
            bets=bets,
            total_investment=total,
            description="パターンH2: 1-2軸2点傾斜配分（200/100円、p5除外）",
            expected_hit_rate=stats['hit_rate'],
            expected_roi=stats['roi'],
        )

    def _generate_pattern_b(
        self, predictions: List[int], odds_dict: Dict[str, float]
    ) -> MultiBetResult:
        """
        パターンB: 1-2軸均等配分（100x3）

        【最高ROIパターン】
        - 1-2着は予測1-2位で固定
        - 3着候補は予測3-5位
        - 配分: 各100円（合計300円）
        """
        p1, p2 = predictions[0], predictions[1]
        third_candidates = [predictions[2], predictions[3], predictions[4]]

        bets = []
        priority = 1
        for third in third_candidates:
            if third != p1 and third != p2:
                combo = f"{p1}-{p2}-{third}"
                odds = odds_dict.get(combo, 0)
                if odds > 0:
                    bets.append(MultiBet(
                        combination=combo,
                        odds=odds,
                        bet_amount=100,
                        priority=priority
                    ))
                    priority += 1

        total = sum(b.bet_amount for b in bets)
        stats = self.PATTERN_STATS[MultiBetPattern.PATTERN_B]

        return MultiBetResult(
            pattern=MultiBetPattern.PATTERN_B,
            bets=bets,
            total_investment=total,
            description="パターンB: 1-2軸3点均等配分（各100円）",
            expected_hit_rate=stats['hit_rate'],
            expected_roi=stats['roi'],
        )

    def _generate_pattern_l(
        self, predictions: List[int], odds_dict: Dict[str, float]
    ) -> MultiBetResult:
        """
        パターンL: 重点買い（300+100）

        - 1-2-3を重点（300円）
        - 1-2-4を補助（100円）
        """
        p1, p2, p3, p4 = predictions[0], predictions[1], predictions[2], predictions[3]

        bets = []
        # 1-2-3（重点）
        combo1 = f"{p1}-{p2}-{p3}"
        odds1 = odds_dict.get(combo1, 0)
        if odds1 > 0:
            bets.append(MultiBet(combination=combo1, odds=odds1, bet_amount=300, priority=1))

        # 1-2-4（補助）
        combo2 = f"{p1}-{p2}-{p4}"
        odds2 = odds_dict.get(combo2, 0)
        if odds2 > 0:
            bets.append(MultiBet(combination=combo2, odds=odds2, bet_amount=100, priority=2))

        total = sum(b.bet_amount for b in bets)
        stats = self.PATTERN_STATS[MultiBetPattern.PATTERN_L]

        return MultiBetResult(
            pattern=MultiBetPattern.PATTERN_L,
            bets=bets,
            total_investment=total,
            description="パターンL: 重点買い（1-2-3に300円、1-2-4に100円）",
            expected_hit_rate=stats['hit_rate'],
            expected_roi=stats['roi'],
        )

    def _generate_pattern_i(
        self, predictions: List[int], odds_dict: Dict[str, float]
    ) -> MultiBetResult:
        """
        パターンI: 2点買い（200+100）

        - 1-2-3を主力（200円）
        - 1-2-4を補助（100円）
        """
        p1, p2, p3, p4 = predictions[0], predictions[1], predictions[2], predictions[3]

        bets = []
        combo1 = f"{p1}-{p2}-{p3}"
        odds1 = odds_dict.get(combo1, 0)
        if odds1 > 0:
            bets.append(MultiBet(combination=combo1, odds=odds1, bet_amount=200, priority=1))

        combo2 = f"{p1}-{p2}-{p4}"
        odds2 = odds_dict.get(combo2, 0)
        if odds2 > 0:
            bets.append(MultiBet(combination=combo2, odds=odds2, bet_amount=100, priority=2))

        total = sum(b.bet_amount for b in bets)
        stats = self.PATTERN_STATS[MultiBetPattern.PATTERN_I]

        return MultiBetResult(
            pattern=MultiBetPattern.PATTERN_I,
            bets=bets,
            total_investment=total,
            description="パターンI: 2点買い（1-2-3に200円、1-2-4に100円）",
            expected_hit_rate=stats['hit_rate'],
            expected_roi=stats['roi'],
        )

    def _generate_pattern_k(
        self, predictions: List[int], odds_dict: Dict[str, float]
    ) -> MultiBetResult:
        """
        パターンK: 総合（150+100+50）

        【最低ドローダウンパターン】
        - 1-2-3（150円）
        - 1-2-4（100円）
        - 2-1-3（50円）：裏目も軽くカバー
        """
        p1, p2, p3, p4 = predictions[0], predictions[1], predictions[2], predictions[3]

        bets = []
        combos_bets = [
            (f"{p1}-{p2}-{p3}", 150),
            (f"{p1}-{p2}-{p4}", 100),
            (f"{p2}-{p1}-{p3}", 50),
        ]

        priority = 1
        for combo, bet in combos_bets:
            odds = odds_dict.get(combo, 0)
            if odds > 0:
                bets.append(MultiBet(combination=combo, odds=odds, bet_amount=bet, priority=priority))
                priority += 1

        total = sum(b.bet_amount for b in bets)
        stats = self.PATTERN_STATS[MultiBetPattern.PATTERN_K]

        return MultiBetResult(
            pattern=MultiBetPattern.PATTERN_K,
            bets=bets,
            total_investment=total,
            description="パターンK: 総合買い（1-2-3:150円、1-2-4:100円、2-1-3:50円）",
            expected_hit_rate=stats['hit_rate'],
            expected_roi=stats['roi'],
        )

    def get_recommended_pattern(self, priority: str = "profit") -> MultiBetPattern:
        """
        推奨パターンを取得

        Args:
            priority: 優先項目
                - "profit": 収支最大 → PATTERN_H
                - "roi": ROI最大 → PATTERN_B
                - "safety": ドローダウン最小 → PATTERN_K
                - "simple": シンプル → PATTERN_I

        Returns:
            推奨パターン
        """
        if priority == "profit":
            return MultiBetPattern.PATTERN_H
        elif priority == "roi":
            return MultiBetPattern.PATTERN_B
        elif priority == "safety":
            return MultiBetPattern.PATTERN_K
        elif priority == "simple":
            return MultiBetPattern.PATTERN_I
        else:
            return MultiBetPattern.PATTERN_H

    def get_pattern_info(self, pattern: MultiBetPattern) -> Dict[str, Any]:
        """パターンの情報を取得"""
        stats = self.PATTERN_STATS.get(pattern, {})
        descriptions = {
            MultiBetPattern.SINGLE: "現行戦略: 1点買い（300円）",
            MultiBetPattern.PATTERN_H: "1-2軸3点傾斜（200/100/100円）- 収支最大",
            MultiBetPattern.PATTERN_B: "1-2軸3点均等（100x3円）- ROI最大",
            MultiBetPattern.PATTERN_L: "重点買い（300+100円）",
            MultiBetPattern.PATTERN_I: "2点買い（200+100円）- シンプル",
            MultiBetPattern.PATTERN_K: "総合買い（150+100+50円）- 安全重視",
            MultiBetPattern.PATTERN_P142: "P142穴狙い（p1-p4-p2 100円1点）",
            MultiBetPattern.PATTERN_P143: "P143穴狙い（p1-p4-p3 100円1点）",
            MultiBetPattern.PATTERN_P132: "P132穴狙い（p1-p3-p2 100円1点）",
            MultiBetPattern.PATTERN_P124: "P124穴狙い（p1-p2-p4 100円1点）",
        }

        return {
            'pattern': pattern.value,
            'description': descriptions.get(pattern, ""),
            'expected_hit_rate': stats.get('hit_rate', 0),
            'expected_roi': stats.get('roi', 0),
            'expected_profit': stats.get('profit', 0),
            'max_drawdown': stats.get('max_dd', 0),
        }

    def _generate_pattern_p142(
        self, predictions: List[int], odds_dict: Dict[str, float]
    ) -> MultiBetResult:
        """
        パターンP142: p1-p4-p2 穴狙い 100円1点買い（2026-04-17追加）

        【穴狙い条件専用パターン】
        - 1着: 予測1位（p1）
        - 2着: 予測4位（p4）← 「サブ崩れ展開」狙い
        - 3着: 予測2位（p2）
        - 配分: 100円（1点）
        条件: A信頼度×スコア80-90×100-300倍×11月除外
        根拠: スコア80-90帯は教科書展開率9.7%（スコア90+の11.7%より低い）
              → p1-p2-p3が崩れた際にp4が2着に来る余地が高い
        """
        if len(predictions) < 4:
            raise ValueError("P142パターンには最低4艇の予測が必要です")

        p1, p2, p4 = predictions[0], predictions[1], predictions[3]
        combo = f"{p1}-{p4}-{p2}"
        odds = odds_dict.get(combo, 0)

        bets = []
        if odds > 0:
            bets.append(MultiBet(combination=combo, odds=odds, bet_amount=100, priority=1))

        total = sum(b.bet_amount for b in bets)

        return MultiBetResult(
            pattern=MultiBetPattern.PATTERN_P142,
            bets=bets,
            total_investment=total,
            description="パターンP142: p1-p4-p2 穴狙い1点買い（100円）",
            expected_hit_rate=1.2,   # 6年実績: 1595件/19的中 ≈ 1.2%
            expected_roi=187.6,      # 6年実績ROI
        )

    def _generate_pattern_p132(
        self, predictions: List[int], odds_dict: Dict[str, float]
    ) -> MultiBetResult:
        """
        パターンP132: p1-p3-p2 穴狙い 100円1点買い（2026-04-17追加）

        【穴狙い条件専用パターン】
        - 1着: 予測1位（p1）
        - 2着: 予測3位（p3）← 「2-3着入れ替わり展開」狙い
        - 3着: 予測2位（p2）
        - 配分: 100円（1点）
        条件: C信頼度×スコア74-84×200-300倍
        根拠: スコア74-84帯は教科書展開率5.2% → 2-3着の入れ替わりが起きやすい
              200-300倍帯: 40組み合わせスキャンでIS/OOS両方ROI100%超の唯一候補
        """
        if len(predictions) < 3:
            raise ValueError("P132パターンには最低3艇の予測が必要です")

        p1, p2, p3 = predictions[0], predictions[1], predictions[2]
        combo = f"{p1}-{p3}-{p2}"
        odds = odds_dict.get(combo, 0)

        bets = []
        if odds > 0:
            bets.append(MultiBet(combination=combo, odds=odds, bet_amount=100, priority=1))

        total = sum(b.bet_amount for b in bets)

        return MultiBetResult(
            pattern=MultiBetPattern.PATTERN_P132,
            bets=bets,
            total_investment=total,
            description="パターンP132: p1-p3-p2 穴狙い1点買い（100円）",
            expected_hit_rate=None,  # Tier2テスト後に更新
            expected_roi=None,       # Tier2テスト後に更新
        )

    def _generate_pattern_p143(
        self,
        predictions: List[int],
        odds_dict: Dict[str, float]
    ) -> MultiBetResult:
        """P143パターン生成（p1-p4-p3）
        - 1着: 予測1位（p1）
        - 2着: 予測4位（p4）← 4位が2着に台頭する展開
        - 3着: 予測3位（p3）
        - 配分: 100円（1点）
        条件: D信頼度×200-300倍
        根拠: IS/OOS両方ROI100%超、5/6年黒字
        """
        if len(predictions) < 4:
            raise ValueError("P143パターンには最低4艇の予測が必要です")

        p1, p3, p4 = predictions[0], predictions[2], predictions[3]
        combo = f"{p1}-{p4}-{p3}"
        odds = odds_dict.get(combo, 0)

        bets = []
        if odds > 0:
            bets.append(MultiBet(combination=combo, odds=odds, bet_amount=100, priority=1))

        total = sum(b.bet_amount for b in bets)

        return MultiBetResult(
            pattern=MultiBetPattern.PATTERN_P143,
            bets=bets,
            total_investment=total,
            description="パターンP143: p1-p4-p3 穴狙い1点買い（100円）",
            expected_hit_rate=None,
            expected_roi=None,
        )

    def _generate_pattern_p124(
        self,
        predictions: List[int],
        odds_dict: Dict[str, float]
    ) -> MultiBetResult:
        """P124パターン生成（p1-p2-p4）
        - 1着: 予測1位（p1）
        - 2着: 予測2位（p2）
        - 3着: 予測4位（p4）← 4位が3着に台頭する展開
        - 配分: 100円（1点）
        条件: C信頼度×150-200倍×スコア90-98
        根拠: IS/OOS両方ROI100%超、5/6年黒字
        """
        if len(predictions) < 4:
            raise ValueError("P124パターンには最低4艇の予測が必要です")

        p1, p2, p4 = predictions[0], predictions[1], predictions[3]
        combo = f"{p1}-{p2}-{p4}"
        odds = odds_dict.get(combo, 0)

        bets = []
        if odds > 0:
            bets.append(MultiBet(combination=combo, odds=odds, bet_amount=100, priority=1))

        total = sum(b.bet_amount for b in bets)

        return MultiBetResult(
            pattern=MultiBetPattern.PATTERN_P124,
            bets=bets,
            total_investment=total,
            description="パターンP124: p1-p2-p4 穴狙い1点買い（100円）",
            expected_hit_rate=None,
            expected_roi=None,
        )


# 使用例
if __name__ == '__main__':
    generator = MultiBetGenerator()

    # サンプルデータ
    predictions = [1, 2, 3, 4, 5, 6]  # 予測順位
    odds_dict = {
        "1-2-3": 35.0,
        "1-2-4": 42.0,
        "1-2-5": 55.0,
        "2-1-3": 38.0,
    }

    # パターンH（推奨）で生成
    result = generator.generate(predictions, odds_dict, MultiBetPattern.PATTERN_H)

    print(f"パターン: {result.pattern.value}")
    print(f"説明: {result.description}")
    print(f"合計投資: {result.total_investment}円")
    print(f"期待的中率: {result.expected_hit_rate}%")
    print(f"期待ROI: {result.expected_roi}%")
    print()
    print("買い目:")
    for bet in result.bets:
        print(f"  {bet.combination}: {bet.bet_amount}円（オッズ{bet.odds}倍）")
