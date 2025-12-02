"""
進入予測モデル

選手の過去進入パターンから、実際の進入コースを確率的に予測する。
前付け傾向のある選手を特定し、進入崩れの影響を正確に反映する。
"""

import sqlite3
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import math


@dataclass
class EntryPrediction:
    """進入予測結果"""
    pit_number: int
    predicted_course: int
    probabilities: Dict[int, float]  # {コース: 確率}
    confidence: float
    is_front_entry_prone: bool  # 前付け傾向
    front_entry_rate: float
    description: str


class EntryPredictionModel:
    """進入予測モデル"""

    # ベイズ更新用の事前分布（枠番=コースの確率）
    PRIOR_SAME_COURSE_PROB = 0.90  # 枠なりの事前確率

    # 選手タイプ別の前付け傾向
    FRONT_ENTRY_TYPES = {
        'aggressive': 0.7,   # 積極的前付け型
        'occasional': 0.3,   # 時々前付け型
        'passive': 0.05,     # 枠なり型
    }

    # 最低サンプル数（これ未満はベイズ更新の重みを下げる）
    MIN_SAMPLES = 10

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path
        self._entry_cache: Dict[str, Dict] = {}

    def predict_race_entries(
        self,
        race_id: int,
        entries: List[Dict]
    ) -> Dict[int, EntryPrediction]:
        """
        レースの進入隊形を予測

        Args:
            race_id: レースID
            entries: 出走選手リスト [{'pit_number', 'racer_number', ...}]

        Returns:
            {pit_number: EntryPrediction}
        """
        predictions = {}
        racer_patterns = {}

        # 各選手の進入パターンを取得
        for entry in entries:
            pit = entry['pit_number']
            racer_number = entry['racer_number']

            pattern = self._get_racer_entry_pattern(racer_number)
            racer_patterns[pit] = pattern

            # 個別予測を計算
            prediction = self._predict_single_entry(pit, pattern)
            predictions[pit] = prediction

        # 進入競合を解決（複数艇が同じコースを予測した場合）
        predictions = self._resolve_entry_conflicts(predictions, racer_patterns)

        return predictions

    def _get_racer_entry_pattern(self, racer_number: str) -> Dict:
        """
        選手の進入パターンを取得

        Returns:
            {
                'pit_course_matrix': {pit: {course: count}},
                'total_races': int,
                'front_entry_rate': float,
                'entry_type': str
            }
        """
        # キャッシュチェック
        if racer_number in self._entry_cache:
            return self._entry_cache[racer_number]

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 過去180日の進入パターンを集計
            cursor.execute('''
                SELECT
                    e.pit_number,
                    rd.actual_course,
                    COUNT(*) as cnt
                FROM entries e
                JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                JOIN races r ON e.race_id = r.id
                WHERE e.racer_number = ?
                  AND rd.actual_course IS NOT NULL
                  AND r.race_date >= date('now', '-180 days')
                GROUP BY e.pit_number, rd.actual_course
            ''', (racer_number,))

            rows = cursor.fetchall()

            if not rows:
                # データがない場合はデフォルトパターン
                return {
                    'pit_course_matrix': {},
                    'total_races': 0,
                    'front_entry_rate': 0.0,
                    'entry_type': 'passive'
                }

            # マトリクスを構築
            matrix = defaultdict(lambda: defaultdict(int))
            total = 0
            front_entry_count = 0

            for pit, course, cnt in rows:
                matrix[pit][course] = cnt
                total += cnt
                if course < pit:
                    front_entry_count += cnt

            # 前付け率
            front_entry_rate = front_entry_count / total if total > 0 else 0

            # 選手タイプ判定
            if front_entry_rate > 0.5:
                entry_type = 'aggressive'
            elif front_entry_rate > 0.2:
                entry_type = 'occasional'
            else:
                entry_type = 'passive'

            pattern = {
                'pit_course_matrix': dict(matrix),
                'total_races': total,
                'front_entry_rate': front_entry_rate,
                'entry_type': entry_type
            }

            # キャッシュに保存
            self._entry_cache[racer_number] = pattern

            return pattern

        finally:
            conn.close()

    def _predict_single_entry(
        self,
        pit_number: int,
        pattern: Dict
    ) -> EntryPrediction:
        """
        単一選手の進入を予測
        """
        matrix = pattern.get('pit_course_matrix', {})
        total_races = pattern.get('total_races', 0)

        # 事前分布
        prior = {c: 0.01 for c in range(1, 7)}
        prior[pit_number] = self.PRIOR_SAME_COURSE_PROB

        # 総和を1に正規化
        prior_sum = sum(prior.values())
        prior = {c: p / prior_sum for c, p in prior.items()}

        if pit_number in matrix and total_races >= self.MIN_SAMPLES:
            # ベイズ更新
            pit_data = matrix[pit_number]
            pit_total = sum(pit_data.values())

            # 尤度を計算
            likelihood = {}
            for course in range(1, 7):
                count = pit_data.get(course, 0)
                likelihood[course] = (count + 1) / (pit_total + 6)  # ラプラス平滑化

            # 事後分布
            posterior = {}
            for course in range(1, 7):
                posterior[course] = prior[course] * likelihood[course]

            # 正規化
            post_sum = sum(posterior.values())
            probabilities = {c: p / post_sum for c, p in posterior.items()}
        else:
            # データ不足の場合は事前分布を使用
            probabilities = prior

        # 最も確率の高いコースを予測
        predicted_course = max(probabilities, key=probabilities.get)
        confidence = probabilities[predicted_course]

        # 前付け傾向フラグ
        is_front_entry_prone = pattern.get('front_entry_rate', 0) > 0.3

        # 説明文生成
        if is_front_entry_prone:
            desc = f"{pit_number}号艇: 前付け傾向({pattern['front_entry_rate']*100:.0f}%)→{predicted_course}コース予測"
        elif predicted_course != pit_number:
            desc = f"{pit_number}号艇: {predicted_course}コース予測({confidence*100:.0f}%)"
        else:
            desc = f"{pit_number}号艇: 枠なり({confidence*100:.0f}%)"

        return EntryPrediction(
            pit_number=pit_number,
            predicted_course=predicted_course,
            probabilities=probabilities,
            confidence=confidence,
            is_front_entry_prone=is_front_entry_prone,
            front_entry_rate=pattern.get('front_entry_rate', 0),
            description=desc
        )

    def _resolve_entry_conflicts(
        self,
        predictions: Dict[int, EntryPrediction],
        racer_patterns: Dict[int, Dict]
    ) -> Dict[int, EntryPrediction]:
        """
        進入競合を解決

        複数の艇が同じコースを予測した場合、前付け傾向や確率から調整
        """
        # コースごとの予測をグループ化
        course_predictions = defaultdict(list)
        for pit, pred in predictions.items():
            course_predictions[pred.predicted_course].append((pit, pred))

        # 競合があるコースを処理
        final_predictions = dict(predictions)

        for course, preds in course_predictions.items():
            if len(preds) <= 1:
                continue

            # 競合がある場合、前付け傾向と確率でソート
            sorted_preds = sorted(
                preds,
                key=lambda x: (
                    x[1].is_front_entry_prone,
                    x[1].front_entry_rate,
                    x[1].confidence
                ),
                reverse=True
            )

            # 最も前付け傾向の強い艇がそのコースを取得
            winner_pit = sorted_preds[0][0]

            # 他の艇は次のコースに移動
            for i, (pit, pred) in enumerate(sorted_preds[1:], 1):
                # 次に確率の高いコースを割り当て
                available_courses = [c for c in range(1, 7)
                                   if c != course and
                                   not any(p.predicted_course == c
                                          for p in final_predictions.values()
                                          if p.pit_number != pit)]

                if available_courses:
                    # 確率が最も高い利用可能コース
                    new_course = max(available_courses,
                                    key=lambda c: pred.probabilities.get(c, 0))

                    # 予測を更新
                    final_predictions[pit] = EntryPrediction(
                        pit_number=pit,
                        predicted_course=new_course,
                        probabilities=pred.probabilities,
                        confidence=pred.probabilities.get(new_course, 0.1),
                        is_front_entry_prone=pred.is_front_entry_prone,
                        front_entry_rate=pred.front_entry_rate,
                        description=f"{pit}号艇: 競合により{new_course}コースに調整"
                    )

        return final_predictions

    def calculate_entry_impact_score(
        self,
        pit_number: int,
        prediction: EntryPrediction,
        max_score: float = 10.0
    ) -> Dict:
        """
        進入予測による影響スコアを計算

        Args:
            pit_number: 枠番
            prediction: 進入予測
            max_score: 最大スコア

        Returns:
            {
                'score': float,
                'impact_type': str,  # 'positive' / 'negative' / 'neutral'
                'description': str
            }
        """
        predicted_course = prediction.predicted_course
        confidence = prediction.confidence

        # コース変化による影響
        if predicted_course < pit_number:
            # 内コースを取得 → 有利
            course_gain = pit_number - predicted_course
            base_score = max_score * 0.5 + (course_gain * 0.15 * max_score)
            impact_type = 'positive'
            desc = f"内コース取得({pit_number}→{predicted_course})"
        elif predicted_course > pit_number:
            # 外コースに追いやられる → 不利
            course_loss = predicted_course - pit_number
            base_score = max_score * 0.5 - (course_loss * 0.15 * max_score)
            impact_type = 'negative'
            desc = f"外コースに流出({pit_number}→{predicted_course})"
        else:
            # 枠なり → 中立
            base_score = max_score * 0.5
            impact_type = 'neutral'
            desc = f"枠なり({pit_number}コース)"

        # 信頼度で調整
        score = base_score * (0.5 + 0.5 * confidence)

        # 前付け傾向による不安定性ペナルティ
        if prediction.is_front_entry_prone and confidence < 0.7:
            score *= 0.9  # 10%ペナルティ
            desc += "（進入不安定）"

        return {
            'score': max(0, min(max_score, score)),
            'impact_type': impact_type,
            'description': desc,
            'predicted_course': predicted_course,
            'confidence': confidence
        }

    def clear_cache(self):
        """キャッシュをクリア"""
        self._entry_cache.clear()
