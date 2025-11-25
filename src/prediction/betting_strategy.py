"""
2段階構造の買い目生成システム

第1層：各艇の1着率・2着率・3着率を予測
第2層：舟券戦略レイヤーで買い目を生成
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import sqlite3
import numpy as np
from itertools import permutations


@dataclass
class BettingPattern:
    """買い目パターン"""
    trifecta: Tuple[int, int, int]  # 3連単 (1着, 2着, 3着)
    probability: float  # 合成確率
    confidence: str  # 信頼度マーク
    reasons: List[str]  # 絞り込み根拠
    category: str  # 本命/抑え/穴


class PlacementPredictor:
    """
    第1層：着順確率予測
    各艇の1着率・2着率・3着率を予測
    """

    # コース別基準着率（過去データから算出）
    COURSE_BASE_RATES = {
        1: {'1st': 0.555, '2nd': 0.177, '3rd': 0.091},
        2: {'1st': 0.137, '2nd': 0.247, '3rd': 0.187},
        3: {'1st': 0.132, '2nd': 0.216, '3rd': 0.202},
        4: {'1st': 0.099, '2nd': 0.171, '3rd': 0.199},
        5: {'1st': 0.060, '2nd': 0.120, '3rd': 0.182},
        6: {'1st': 0.030, '2nd': 0.082, '3rd': 0.153},
    }

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def predict_placement_rates(
        self,
        predictions: List[Dict[str, Any]]
    ) -> Dict[int, Dict[str, float]]:
        """
        各艇の1着率・2着率・3着率を予測

        Args:
            predictions: 基本予測データ（pit_number, total_score, win_rate等）

        Returns:
            {pit_number: {'1st': 確率, '2nd': 確率, '3rd': 確率}}
        """
        placement_rates = {}

        for pred in predictions:
            pit = pred['pit_number']
            base_rates = self.COURSE_BASE_RATES[pit].copy()

            # 選手能力による補正
            win_rate = pred.get('win_rate', 5.0)
            motor_rate = pred.get('motor_second_rate', 30.0)

            # 補正係数計算
            # 勝率が高い選手は1着率を上げ、2着・3着率を下げる
            win_rate_factor = (win_rate - 5.0) / 10.0  # -0.5 to +0.5程度
            motor_factor = (motor_rate - 30.0) / 100.0  # -0.3 to +0.3程度

            # 1着率補正
            first_adj = base_rates['1st'] * (1 + win_rate_factor * 0.3 + motor_factor * 0.1)

            # 2着率補正（1着率が上がると2着率は相対的に下がる）
            second_adj = base_rates['2nd'] * (1 + win_rate_factor * 0.15 + motor_factor * 0.05)

            # 3着率補正
            third_adj = base_rates['3rd'] * (1 + win_rate_factor * 0.1 + motor_factor * 0.03)

            # 確率の正規化（合計が1を超えないように）
            total = first_adj + second_adj + third_adj
            if total > 0.95:  # 4着以下の余地を残す
                scale = 0.95 / total
                first_adj *= scale
                second_adj *= scale
                third_adj *= scale

            placement_rates[pit] = {
                '1st': max(0.01, min(0.90, first_adj)),
                '2nd': max(0.01, min(0.50, second_adj)),
                '3rd': max(0.01, min(0.40, third_adj)),
            }

        return placement_rates

    def calculate_trifecta_probabilities(
        self,
        placement_rates: Dict[int, Dict[str, float]]
    ) -> List[Tuple[Tuple[int, int, int], float]]:
        """
        全120通りの3連単確率を計算

        Args:
            placement_rates: 各艇の着率

        Returns:
            [(trifecta, probability), ...] 確率順
        """
        pits = list(placement_rates.keys())
        trifecta_probs = []

        for perm in permutations(pits, 3):
            first, second, third = perm

            # P(1着A) × P(2着B|Aが1着) × P(3着C|A,Bが1,2着)
            # 簡易計算：独立と仮定して掛け算
            prob = (
                placement_rates[first]['1st'] *
                placement_rates[second]['2nd'] *
                placement_rates[third]['3rd']
            )

            trifecta_probs.append((perm, prob))

        # 確率順にソート
        trifecta_probs.sort(key=lambda x: x[1], reverse=True)

        # 正規化
        total_prob = sum(p for _, p in trifecta_probs)
        if total_prob > 0:
            trifecta_probs = [
                (tri, prob / total_prob)
                for tri, prob in trifecta_probs
            ]

        return trifecta_probs


class BettingStrategyEngine:
    """
    第2層：舟券戦略レイヤー
    AIの確率 × コース着率 × 除外ルールで買い目生成
    """

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path
        self.predictor = PlacementPredictor(db_path)

    def generate_betting_patterns(
        self,
        predictions: List[Dict[str, Any]],
        min_probability: float = 0.01,
        max_patterns: int = 10
    ) -> List[BettingPattern]:
        """
        買い目パターンを生成

        Args:
            predictions: 基本予測データ
            min_probability: 最低確率閾値
            max_patterns: 最大パターン数

        Returns:
            買い目パターンリスト
        """
        # 第1層：着率予測
        placement_rates = self.predictor.predict_placement_rates(predictions)

        # 全組み合わせの確率計算
        trifecta_probs = self.predictor.calculate_trifecta_probabilities(
            placement_rates
        )

        # 第2層：戦略ルール適用
        patterns = self._apply_strategy_rules(
            trifecta_probs,
            placement_rates,
            predictions,
            min_probability
        )

        # パターン数制限
        patterns = patterns[:max_patterns]

        return patterns

    def _apply_strategy_rules(
        self,
        trifecta_probs: List[Tuple[Tuple[int, int, int], float]],
        placement_rates: Dict[int, Dict[str, float]],
        predictions: List[Dict[str, Any]],
        min_probability: float
    ) -> List[BettingPattern]:
        """
        舟券戦略ルールを適用
        """
        patterns = []
        pred_dict = {p['pit_number']: p for p in predictions}

        for trifecta, prob in trifecta_probs:
            if prob < min_probability:
                continue

            first, second, third = trifecta
            reasons = []

            # ルール1: 1着の根拠
            first_rate = placement_rates[first]['1st']
            if first == 1 and first_rate > 0.50:
                reasons.append(f"1号艇1着率{first_rate*100:.1f}%で1着固定")
            else:
                reasons.append(
                    f"{first}号艇の1着率{first_rate*100:.1f}%"
                )

            # ルール2: 2着の根拠
            second_rate = placement_rates[second]['2nd']
            if second in [2, 3] and second_rate > 0.20:
                reasons.append(f"{second}号艇2着率{second_rate*100:.1f}%で有力")
            elif second == 6 and second_rate < 0.10:
                reasons.append(f"{second}号艇2着率低め（{second_rate*100:.1f}%）穴狙い")
            else:
                reasons.append(f"{second}号艇2着率{second_rate*100:.1f}%")

            # ルール3: 3着の根拠
            third_rate = placement_rates[third]['3rd']
            if third == 6:
                reasons.append(f"6号艇3着率{third_rate*100:.1f}%（低確率）")
            else:
                reasons.append(f"{third}号艇3着率{third_rate*100:.1f}%")

            # カテゴリ分類
            if prob >= 0.05:
                category = "本命"
                confidence = "◎"
            elif prob >= 0.02:
                category = "対抗"
                confidence = "○"
            elif prob >= 0.01:
                category = "抑え"
                confidence = "▲"
            else:
                category = "穴"
                confidence = "△"

            pattern = BettingPattern(
                trifecta=trifecta,
                probability=prob,
                confidence=confidence,
                reasons=reasons,
                category=category
            )
            patterns.append(pattern)

        return patterns

    def generate_trifecta_combinations(
        self,
        predictions: List[Dict[str, Any]],
        min_probability: float = 0.005
    ) -> List[BettingPattern]:
        """
        3連複の組み合わせも生成

        Returns:
            3連複パターンリスト
        """
        # 3連単パターンを取得
        trifecta_patterns = self.generate_betting_patterns(
            predictions,
            min_probability=0.001,
            max_patterns=120
        )

        # 3連複に変換（順番を無視）
        trio_probs = {}
        for pattern in trifecta_patterns:
            trio = tuple(sorted(pattern.trifecta))
            if trio not in trio_probs:
                trio_probs[trio] = {
                    'prob': 0,
                    'patterns': []
                }
            trio_probs[trio]['prob'] += pattern.probability
            trio_probs[trio]['patterns'].append(pattern.trifecta)

        # 3連複パターンを生成
        trio_patterns = []
        for trio, data in sorted(
            trio_probs.items(),
            key=lambda x: x[1]['prob'],
            reverse=True
        ):
            if data['prob'] < min_probability:
                continue

            prob = data['prob']
            if prob >= 0.10:
                category = "本命"
                confidence = "◎"
            elif prob >= 0.05:
                category = "対抗"
                confidence = "○"
            elif prob >= 0.02:
                category = "抑え"
                confidence = "▲"
            else:
                category = "穴"
                confidence = "△"

            pattern = BettingPattern(
                trifecta=trio,
                probability=prob,
                confidence=confidence,
                reasons=[
                    f"組み合わせ: {trio[0]}-{trio[1]}-{trio[2]}",
                    f"含む3連単: {len(data['patterns'])}通り"
                ],
                category=category
            )
            trio_patterns.append(pattern)

        return trio_patterns


def format_betting_patterns(patterns: List[BettingPattern]) -> str:
    """買い目パターンをテキスト形式でフォーマット"""
    lines = ["=" * 50, "推奨買い目", "=" * 50, ""]

    # カテゴリ別に分類
    by_category = {}
    for p in patterns:
        if p.category not in by_category:
            by_category[p.category] = []
        by_category[p.category].append(p)

    for category in ["本命", "対抗", "抑え", "穴"]:
        if category not in by_category:
            continue

        lines.append(f"【{category}】")
        for p in by_category[category]:
            tri = f"{p.trifecta[0]}-{p.trifecta[1]}-{p.trifecta[2]}"
            lines.append(f"  {p.confidence} {tri} ({p.probability*100:.1f}%)")
            for reason in p.reasons[:2]:
                lines.append(f"     - {reason}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    # テスト
    print("2段階構造 買い目生成システム テスト")
    print("-" * 50)

    # テストデータ
    test_predictions = [
        {'pit_number': 1, 'racer_name': '山田太郎', 'total_score': 35.5,
         'win_rate': 7.5, 'motor_second_rate': 35.0},
        {'pit_number': 2, 'racer_name': '鈴木次郎', 'total_score': 22.3,
         'win_rate': 6.2, 'motor_second_rate': 32.0},
        {'pit_number': 3, 'racer_name': '田中三郎', 'total_score': 18.7,
         'win_rate': 5.8, 'motor_second_rate': 28.0},
        {'pit_number': 4, 'racer_name': '佐藤四郎', 'total_score': 12.4,
         'win_rate': 5.0, 'motor_second_rate': 30.0},
        {'pit_number': 5, 'racer_name': '高橋五郎', 'total_score': 8.2,
         'win_rate': 4.5, 'motor_second_rate': 25.0},
        {'pit_number': 6, 'racer_name': '伊藤六郎', 'total_score': 6.1,
         'win_rate': 3.8, 'motor_second_rate': 22.0},
    ]

    engine = BettingStrategyEngine()

    # 3連単パターン生成
    print("\n【3連単 推奨買い目】")
    patterns = engine.generate_betting_patterns(
        test_predictions,
        min_probability=0.01,
        max_patterns=10
    )

    for p in patterns:
        tri = f"{p.trifecta[0]}-{p.trifecta[1]}-{p.trifecta[2]}"
        print(f"{p.confidence} {tri} ({p.probability*100:.1f}%) [{p.category}]")
        for reason in p.reasons:
            print(f"   - {reason}")

    # 3連複パターン生成
    print("\n【3連複 推奨買い目】")
    trio_patterns = engine.generate_trifecta_combinations(
        test_predictions,
        min_probability=0.02
    )

    for p in trio_patterns[:5]:
        tri = f"{p.trifecta[0]}-{p.trifecta[1]}-{p.trifecta[2]}"
        print(f"{p.confidence} {tri} ({p.probability*100:.1f}%) [{p.category}]")
