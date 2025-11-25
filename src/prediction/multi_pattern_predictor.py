"""
複数パターン予測モジュール

1レースに対して3〜10パターンの予測を生成
- 本命パターン（モデル予測）
- 展開別パターン（シナリオエンジン）
- 決まり手別パターン
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import sqlite3
import numpy as np

from .race_scenario_engine import RaceScenarioEngine, RaceScenario
from .kimarite_constants import Kimarite, KIMARITE_NAMES


@dataclass
class PredictionPattern:
    """予測パターン"""
    pattern_id: int
    pattern_name: str
    trifecta: Tuple[int, int, int]  # 3連単 (1着, 2着, 3着)
    probability: float  # 発生確率
    confidence: str  # 信頼度マーク（◎○▲△×）
    reasons: List[str]  # 予測根拠
    kimarite: Optional[str] = None  # 決まり手


class MultiPatternPredictor:
    """複数パターン予測クラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path
        self.scenario_engine = RaceScenarioEngine()

    def generate_patterns(
        self,
        race_id: int,
        base_predictions: List[Dict[str, Any]],
        num_patterns: int = 5
    ) -> List[PredictionPattern]:
        """
        複数パターンを生成

        Args:
            race_id: レースID
            base_predictions: 基本予測（pit_number順のスコアリスト）
            num_patterns: 生成するパターン数（3〜10）

        Returns:
            パターンリスト
        """
        num_patterns = max(3, min(10, num_patterns))

        patterns = []

        # 1. 本命パターン（モデル予測上位）
        main_pattern = self._create_main_pattern(base_predictions)
        patterns.append(main_pattern)

        # 2. シナリオベースのパターン生成
        scenario_patterns = self._create_scenario_patterns(
            base_predictions,
            num_patterns - 1
        )
        patterns.extend(scenario_patterns)

        # パターン数調整
        patterns = patterns[:num_patterns]

        # パターンIDを振り直し
        for i, pattern in enumerate(patterns):
            pattern.pattern_id = i + 1

        # 確率で正規化
        total_prob = sum(p.probability for p in patterns)
        if total_prob > 0:
            for pattern in patterns:
                pattern.probability = pattern.probability / total_prob

        return patterns

    def _create_main_pattern(
        self,
        predictions: List[Dict[str, Any]]
    ) -> PredictionPattern:
        """
        本命パターンを作成（モデル予測上位3艇）

        Args:
            predictions: 基本予測

        Returns:
            本命パターン
        """
        # スコア順にソート
        sorted_preds = sorted(
            predictions,
            key=lambda x: x.get('total_score', 0),
            reverse=True
        )

        top3 = sorted_preds[:3]
        trifecta = (
            top3[0]['pit_number'],
            top3[1]['pit_number'],
            top3[2]['pit_number']
        )

        # 確率計算（上位3艇のスコアから）
        prob = (
            top3[0].get('total_score', 0) *
            top3[1].get('total_score', 0) *
            top3[2].get('total_score', 0)
        ) / 1000000  # 正規化

        # 信頼度判定
        top_score = top3[0].get('total_score', 0)
        if top_score >= 40:
            confidence = "◎"
        elif top_score >= 30:
            confidence = "○"
        elif top_score >= 20:
            confidence = "▲"
        else:
            confidence = "△"

        # 根拠生成
        reasons = []
        for i, pred in enumerate(top3):
            pit = pred['pit_number']
            score = pred.get('total_score', 0)
            name = pred.get('racer_name', '選手名不明')
            reasons.append(f"{i+1}着: {pit}号艇 {name} (スコア{score:.1f})")

        # 決まり手推定
        if top3[0]['pit_number'] == 1:
            kimarite = "逃げ"
        elif top3[0]['pit_number'] == 2:
            kimarite = "差し"
        elif top3[0]['pit_number'] >= 4:
            kimarite = "まくり"
        else:
            kimarite = "差し"

        return PredictionPattern(
            pattern_id=1,
            pattern_name=f"本命予想（{top3[0]['pit_number']}号艇{kimarite}）",
            trifecta=trifecta,
            probability=max(0.01, min(0.5, prob)),
            confidence=confidence,
            reasons=reasons,
            kimarite=kimarite
        )

    def _create_scenario_patterns(
        self,
        predictions: List[Dict[str, Any]],
        num_patterns: int
    ) -> List[PredictionPattern]:
        """
        シナリオベースのパターンを作成

        Args:
            predictions: 基本予測
            num_patterns: 生成するパターン数

        Returns:
            パターンリスト
        """
        patterns = []

        # スコア順にソート
        sorted_preds = sorted(
            predictions,
            key=lambda x: x.get('total_score', 0),
            reverse=True
        )

        # 各決まり手パターンを生成
        kimarite_scenarios = [
            (1, "逃げ", "1号艇が逃げ切り"),
            (2, "差し", "2号艇が差し"),
            (3, "差し", "3号艇が差し"),
            (4, "まくり", "4号艇がまくり"),
            (5, "まくり差し", "5号艇がまくり差し"),
            (6, "まくり", "6号艇が大外まくり"),
        ]

        for winner, kimarite, description in kimarite_scenarios:
            if len(patterns) >= num_patterns:
                break

            # この艇のスコア
            winner_pred = next(
                (p for p in predictions if p['pit_number'] == winner),
                None
            )
            if not winner_pred:
                continue

            winner_score = winner_pred.get('total_score', 0)

            # スコアが低すぎる場合はスキップ
            if winner_score < 5:
                continue

            # 本命と同じパターンはスキップ
            if winner == sorted_preds[0]['pit_number']:
                continue

            # 2着・3着を決定
            remaining = [p for p in sorted_preds if p['pit_number'] != winner]
            second = remaining[0]['pit_number'] if remaining else 1
            third = remaining[1]['pit_number'] if len(remaining) > 1 else 2

            trifecta = (winner, second, third)

            # 確率計算
            prob = winner_score / 100 * 0.5  # ベース確率

            # 信頼度
            if winner_score >= 25:
                confidence = "○"
            elif winner_score >= 15:
                confidence = "▲"
            else:
                confidence = "△"

            # 根拠
            reasons = [
                f"{winner}号艇{kimarite}成功の場合",
                f"1着: {winner}号艇 (スコア{winner_score:.1f})",
                f"2着: {second}号艇",
                f"3着: {third}号艇"
            ]

            pattern = PredictionPattern(
                pattern_id=len(patterns) + 2,
                pattern_name=description,
                trifecta=trifecta,
                probability=max(0.01, min(0.3, prob)),
                confidence=confidence,
                reasons=reasons,
                kimarite=kimarite
            )
            patterns.append(pattern)

        # 荒れパターンを追加（5-6号艇の上位入着）
        if len(patterns) < num_patterns:
            # 5-6号艇で最もスコアが高い艇
            outer_boats = [p for p in predictions if p['pit_number'] in [5, 6]]
            if outer_boats:
                best_outer = max(outer_boats, key=lambda x: x.get('total_score', 0))
                outer_winner = best_outer['pit_number']
                outer_score = best_outer.get('total_score', 0)

                if outer_score >= 10:
                    remaining = [p for p in sorted_preds if p['pit_number'] != outer_winner]
                    second = remaining[0]['pit_number'] if remaining else 1
                    third = remaining[1]['pit_number'] if len(remaining) > 1 else 2

                    pattern = PredictionPattern(
                        pattern_id=len(patterns) + 2,
                        pattern_name=f"荒れ展開（{outer_winner}号艇激走）",
                        trifecta=(outer_winner, second, third),
                        probability=max(0.01, outer_score / 100 * 0.3),
                        confidence="×",
                        reasons=[
                            "荒れ展開の場合",
                            f"{outer_winner}号艇が上位に食い込む",
                            "高配当狙い"
                        ],
                        kimarite="まくり"
                    )
                    patterns.append(pattern)

        return patterns

    def generate_patterns_by_key(
        self,
        race_date: str,
        venue_code: str,
        race_number: int,
        num_patterns: int = 5
    ) -> List[PredictionPattern]:
        """
        レースキーから複数パターンを生成

        Args:
            race_date: レース日（YYYY-MM-DD）
            venue_code: 会場コード
            race_number: レース番号
            num_patterns: パターン数

        Returns:
            パターンリスト
        """
        # DBからレースIDと基本データを取得
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # レースID取得
            cursor.execute("""
                SELECT id FROM races
                WHERE race_date = ? AND venue_code = ? AND race_number = ?
            """, (race_date, venue_code, race_number))
            result = cursor.fetchone()

            if not result:
                return []

            race_id = result[0]

            # エントリー情報取得
            cursor.execute("""
                SELECT
                    pit_number,
                    racer_name,
                    racer_rank,
                    win_rate,
                    local_win_rate,
                    motor_second_rate,
                    boat_second_rate
                FROM entries
                WHERE race_id = ?
                ORDER BY pit_number
            """, (race_id,))

            entries = cursor.fetchall()

        if not entries:
            return []

        # 簡易スコア計算（本来はモデル予測を使用）
        predictions = []
        for entry in entries:
            pit_number = entry[0]
            racer_name = entry[1] or "選手名不明"
            win_rate = entry[3] or 5.0
            motor_rate = entry[5] or 30.0

            # 簡易スコア（コース有利 + 勝率 + モーター）
            course_bonus = {1: 20, 2: 5, 3: 3, 4: 2, 5: 1, 6: 0}
            score = (
                course_bonus.get(pit_number, 0) +
                win_rate * 2 +
                motor_rate * 0.3
            )

            predictions.append({
                'pit_number': pit_number,
                'racer_name': racer_name,
                'total_score': score,
                'win_rate': win_rate,
                'motor_rate': motor_rate
            })

        return self.generate_patterns(race_id, predictions, num_patterns)

    def format_patterns_text(
        self,
        patterns: List[PredictionPattern]
    ) -> str:
        """
        パターンをテキスト形式にフォーマット

        Args:
            patterns: パターンリスト

        Returns:
            フォーマット済みテキスト
        """
        lines = ["=" * 50, "複数パターン予測", "=" * 50, ""]

        for pattern in patterns:
            trifecta_str = f"{pattern.trifecta[0]}-{pattern.trifecta[1]}-{pattern.trifecta[2]}"

            lines.append(
                f"【パターン{pattern.pattern_id}】{pattern.pattern_name}"
            )
            lines.append(
                f"  3連単: {trifecta_str}  "
                f"確率: {pattern.probability*100:.1f}%  "
                f"信頼度: {pattern.confidence}"
            )
            lines.append("  根拠:")
            for reason in pattern.reasons[:3]:
                lines.append(f"    - {reason}")
            lines.append("")

        return "\n".join(lines)


if __name__ == "__main__":
    # テスト
    print("複数パターン予測 テスト")
    print("-" * 40)

    predictor = MultiPatternPredictor()

    # テストデータ
    test_predictions = [
        {'pit_number': 1, 'racer_name': '山田太郎', 'total_score': 35.5},
        {'pit_number': 2, 'racer_name': '鈴木次郎', 'total_score': 22.3},
        {'pit_number': 3, 'racer_name': '田中三郎', 'total_score': 18.7},
        {'pit_number': 4, 'racer_name': '佐藤四郎', 'total_score': 12.4},
        {'pit_number': 5, 'racer_name': '高橋五郎', 'total_score': 8.2},
        {'pit_number': 6, 'racer_name': '伊藤六郎', 'total_score': 6.1},
    ]

    # パターン生成
    patterns = predictor.generate_patterns(1, test_predictions, num_patterns=5)

    # 表示
    print(predictor.format_patterns_text(patterns))
