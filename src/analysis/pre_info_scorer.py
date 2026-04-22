"""
事前情報スコアリングモジュール（PreInfoScorer）

レース前に確定している情報のみでスコアリングを行う。
直前情報（BeforeInfoScorer）との役割分離を明確化し、重複加点を防止。

【事前情報の定義】
- 選手情報: 全国成績、コース別成績、当地成績、グレード適性、決まり手適性
- モーター情報: モーター勝率、2連率、ボート成績
- 静的情報: 級別（A1/A2/B1/B2）、F/L持ち、平均ST

【直前情報との境界】
- 展示タイム → BeforeInfoScorer（直前情報）
- 展示ST → BeforeInfoScorer（直前情報）
- チルト角度 → BeforeInfoScorer（直前情報）
- 進入コース → BeforeInfoScorer（直前情報）
- 前走成績（当日） → BeforeInfoScorer（直前情報）

作成日: 2025-12-15
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from src.utils.db_connection_pool import get_connection


@dataclass
class PreInfoResult:
    """事前情報スコア結果"""
    total_score: float = 0.0

    # 選手成績系
    overall_score: float = 0.0      # 全国成績スコア
    course_score: float = 0.0       # コース別成績スコア
    venue_score: float = 0.0        # 当地成績スコア
    recent_form_score: float = 0.0  # 直近成績スコア

    # 級別・リスク系
    class_score: float = 0.0        # 級別スコア（A1/A2/B1/B2）
    fl_penalty: float = 0.0         # F/L持ちペナルティ
    avg_st_score: float = 0.0       # 平均STスコア

    # モーター系
    motor_score: float = 0.0        # モーター成績スコア
    boat_score: float = 0.0         # ボート成績スコア

    # 適性系
    grade_affinity_score: float = 0.0   # グレード適性スコア
    kimarite_affinity_score: float = 0.0  # 決まり手適性スコア

    # 連対率系
    rentai_score: float = 0.0       # 連対率スコア

    # メタ情報
    data_completeness: float = 0.0  # データ充実度（0-1）
    confidence: float = 0.0         # 信頼度（0-1）

    # 詳細情報
    details: Dict = field(default_factory=dict)


class PreInfoScorer:
    """
    事前情報スコアリングクラス

    ExtendedScorerから直前情報に関する要素を除外し、
    純粋な事前情報のみでスコアリングを行う。
    """

    # スコア配分（100点満点）
    SCORE_WEIGHTS = {
        'overall': 15.0,      # 全国成績
        'course': 15.0,       # コース別成績
        'venue': 10.0,        # 当地成績
        'recent_form': 10.0,  # 直近成績（過去5走）
        'class': 12.0,        # 級別
        'fl_penalty': -10.0,  # F/L持ちペナルティ（最大-10点）
        'avg_st': 8.0,        # 平均ST
        'motor': 10.0,        # モーター成績
        'boat': 5.0,          # ボート成績
        'grade_affinity': 5.0,  # グレード適性
        'kimarite': 5.0,      # 決まり手適性
        'rentai': 5.0,        # 連対率
    }

    # 級別基準スコア
    CLASS_SCORES = {
        'A1': 1.0,   # 12点
        'A2': 0.7,   # 8.4点
        'B1': 0.4,   # 4.8点
        'B2': 0.1,   # 1.2点
    }

    # F/Lペナルティ
    FL_PENALTIES = {
        'F': -5.0,   # フライング1回で-5点
        'L': -2.0,   # 出遅れ1回で-2点
    }

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path

    def calculate_pre_info_score(
        self,
        race_id: int,
        pit_number: int,
        racer_number: str,
        venue_code: str,
        race_date: str,
        race_grade: str = '一般',
        course: Optional[int] = None
    ) -> PreInfoResult:
        """
        事前情報スコアを計算

        Args:
            race_id: レースID
            pit_number: 艇番（1-6）
            racer_number: 選手番号
            venue_code: 会場コード
            race_date: レース日付
            race_grade: レースグレード
            course: 予測コース（Noneの場合はpit_number）

        Returns:
            PreInfoResult: スコア結果
        """
        result = PreInfoResult()

        # コースはデフォルトで枠なり
        if course is None:
            course = pit_number

        # 各スコア計算
        result.overall_score = self._calc_overall_score(racer_number, race_date)
        result.course_score = self._calc_course_score(racer_number, course, race_date)
        result.venue_score = self._calc_venue_score(racer_number, venue_code, race_date)
        result.recent_form_score = self._calc_recent_form_score(racer_number, race_date)
        result.class_score = self._calc_class_score(race_id, pit_number)
        result.fl_penalty = self._calc_fl_penalty(race_id, pit_number)
        result.avg_st_score = self._calc_avg_st_score(race_id, pit_number, course)
        result.motor_score = self._calc_motor_score(race_id, pit_number)
        result.boat_score = self._calc_boat_score(race_id, pit_number)
        result.grade_affinity_score = self._calc_grade_affinity_score(racer_number, race_grade, race_date)
        result.kimarite_affinity_score = self._calc_kimarite_affinity_score(racer_number, course, race_date)
        result.rentai_score = self._calc_rentai_score(racer_number, race_date)

        # 総合スコア計算
        result.total_score = (
            result.overall_score +
            result.course_score +
            result.venue_score +
            result.recent_form_score +
            result.class_score +
            result.fl_penalty +
            result.avg_st_score +
            result.motor_score +
            result.boat_score +
            result.grade_affinity_score +
            result.kimarite_affinity_score +
            result.rentai_score
        )

        # 0-100範囲に正規化
        result.total_score = max(0.0, min(100.0, result.total_score))

        # データ充実度と信頼度を計算
        result.data_completeness = self._calc_data_completeness(result)
        result.confidence = self._calc_confidence(result)

        return result

    def _calc_overall_score(self, racer_number: str, race_date: str) -> float:
        """
        全国成績スコア（15点満点）

        racer_featuresテーブルの直近勝率を使用
        ※ racer_featuresに win_rate カラムは存在しないため recent_win_rate_5 を使用
        """
        max_score = self.SCORE_WEIGHTS['overall']

        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT recent_win_rate_5, race_date
                FROM racer_features
                WHERE racer_number = ? AND race_date <= ?
                ORDER BY race_date DESC
                LIMIT 1
            ''', (racer_number, race_date))

            row = cursor.fetchone()
            cursor.close()

            if not row or row[0] is None:
                return max_score * 0.5  # データなしは中間値

            win_rate, feature_date = row[0], row[1]

            # 鮮度チェック: 14日以上古いデータは中間値にフォールバック
            if feature_date:
                try:
                    from datetime import datetime as _dt
                    if (_dt.strptime(str(race_date), '%Y-%m-%d') - _dt.strptime(str(feature_date), '%Y-%m-%d')).days > 14:
                        return max_score * 0.5
                except Exception:
                    pass

            # 勝率16.7%（1/6）を基準に、30%で満点
            normalized_rate = min(win_rate / 30.0, 1.0)
            return max_score * normalized_rate

        except Exception:
            return max_score * 0.5

    def _calc_course_score(self, racer_number: str, course: int, race_date: str) -> float:
        """
        コース別成績スコア（15点満点）

        特定コースでの勝率を評価
        """
        max_score = self.SCORE_WEIGHTS['course']

        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            # コース別勝率を取得
            cursor.execute('''
                SELECT course_win_rate
                FROM racer_course_features
                WHERE racer_number = ? AND course = ? AND race_date <= ?
                ORDER BY race_date DESC
                LIMIT 1
            ''', (racer_number, course, race_date))

            row = cursor.fetchone()
            cursor.close()

            if not row or row[0] is None:
                return max_score * 0.5

            course_win_rate = row[0]

            # コース別の平均勝率を基準（1コース: 56%, 6コース: 2%）
            course_avg_rates = {
                1: 0.56, 2: 0.14, 3: 0.12, 4: 0.10, 5: 0.06, 6: 0.02
            }
            avg_rate = course_avg_rates.get(course, 0.167)

            # 平均より高ければ高評価
            if avg_rate > 0:
                ratio = course_win_rate / avg_rate
                normalized = min(ratio / 2.0, 1.0)  # 平均の2倍で満点
                return max_score * normalized

            return max_score * 0.5

        except Exception:
            return max_score * 0.5

    def _calc_venue_score(self, racer_number: str, venue_code: str, race_date: str) -> float:
        """
        当地成績スコア（10点満点）

        特定会場での勝率を評価
        """
        max_score = self.SCORE_WEIGHTS['venue']

        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT venue_win_rate, venue_races
                FROM racer_venue_features
                WHERE racer_number = ? AND venue_code = ? AND race_date <= ?
                ORDER BY race_date DESC
                LIMIT 1
            ''', (racer_number, venue_code, race_date))

            row = cursor.fetchone()
            cursor.close()

            if not row or row[0] is None or row[1] < 5:
                return max_score * 0.5  # 5レース未満はデータ不足

            venue_win_rate = row[0]

            # 全国平均16.7%との比較
            national_avg = 0.167
            ratio = venue_win_rate / national_avg if national_avg > 0 else 1.0

            # 平均の2倍（33%）で満点
            normalized = min(ratio / 2.0, 1.0)
            return max_score * normalized

        except Exception:
            return max_score * 0.5

    def _calc_recent_form_score(self, racer_number: str, race_date: str) -> float:
        """
        直近成績スコア（10点満点）

        直近5走の成績を評価
        """
        max_score = self.SCORE_WEIGHTS['recent_form']

        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT recent_win_rate_5, recent_avg_rank_5, race_date
                FROM racer_features
                WHERE racer_number = ? AND race_date <= ?
                ORDER BY race_date DESC
                LIMIT 1
            ''', (racer_number, race_date))

            row = cursor.fetchone()
            cursor.close()

            if not row or row[0] is None:
                return max_score * 0.5

            recent_win_rate, recent_avg_rank, feature_date = row[0], row[1], row[2]
            recent_avg_rank = recent_avg_rank if recent_avg_rank else 3.5

            # 鮮度チェック: 14日以上古いデータは中間値にフォールバック
            if feature_date:
                try:
                    from datetime import datetime as _dt
                    if (_dt.strptime(str(race_date), '%Y-%m-%d') - _dt.strptime(str(feature_date), '%Y-%m-%d')).days > 14:
                        return max_score * 0.5
                except Exception:
                    pass

            # 勝率ベース（60%の重み）
            win_rate_score = min(recent_win_rate / 30.0, 1.0) * max_score * 0.6

            # 平均着順ベース（40%の重み）
            rank_score = max(0, (4.5 - recent_avg_rank) / 3.5) * max_score * 0.4

            return win_rate_score + rank_score

        except Exception:
            return max_score * 0.5

    def _calc_class_score(self, race_id: int, pit_number: int) -> float:
        """
        級別スコア（12点満点）
        """
        max_score = self.SCORE_WEIGHTS['class']

        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT racer_rank
                FROM entries
                WHERE race_id = ? AND pit_number = ?
            ''', (race_id, pit_number))

            row = cursor.fetchone()
            cursor.close()

            if not row or not row[0]:
                return max_score * 0.4  # 不明はB1相当

            racer_rank = row[0].upper()
            factor = self.CLASS_SCORES.get(racer_rank, 0.4)
            return max_score * factor

        except Exception:
            return max_score * 0.4

    def _calc_fl_penalty(self, race_id: int, pit_number: int) -> float:
        """
        F/L持ちペナルティ（最大-10点）
        """
        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT f_count, l_count
                FROM entries
                WHERE race_id = ? AND pit_number = ?
            ''', (race_id, pit_number))

            row = cursor.fetchone()
            cursor.close()

            if not row:
                return 0.0

            f_count = row[0] or 0
            l_count = row[1] or 0

            penalty = (
                f_count * self.FL_PENALTIES['F'] +
                l_count * self.FL_PENALTIES['L']
            )

            # 最大-10点
            return max(penalty, -10.0)

        except Exception:
            return 0.0

    def _calc_avg_st_score(self, race_id: int, pit_number: int, course: int) -> float:
        """
        平均STスコア（8点満点）

        スタートタイミングは勝率に強く影響する。
        0.10-0.15秒が最も勝率が高い。
        """
        max_score = self.SCORE_WEIGHTS['avg_st']

        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT avg_st
                FROM entries
                WHERE race_id = ? AND pit_number = ?
            ''', (race_id, pit_number))

            row = cursor.fetchone()
            cursor.close()

            if not row or row[0] is None:
                return max_score * 0.5

            avg_st = row[0]

            # ST範囲別スコア
            if avg_st < 0.10:
                factor = 0.7   # 早すぎ（Fリスク）
            elif avg_st < 0.15:
                factor = 1.0   # 最適
            elif avg_st < 0.18:
                factor = 0.8   # 良好
            elif avg_st < 0.20:
                factor = 0.6   # やや遅い
            else:
                factor = 0.4   # 遅い

            # 1コースはSTが特に重要
            if course == 1:
                factor = min(1.0, factor * 1.2)

            return max_score * factor

        except Exception:
            return max_score * 0.5

    def _calc_motor_score(self, race_id: int, pit_number: int) -> float:
        """
        モーター成績スコア（10点満点）
        """
        max_score = self.SCORE_WEIGHTS['motor']

        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT motor_second_rate
                FROM entries
                WHERE race_id = ? AND pit_number = ?
            ''', (race_id, pit_number))

            row = cursor.fetchone()
            cursor.close()

            if not row or row[0] is None:
                return max_score * 0.5

            motor_rate = row[0]

            # 平均30%を基準に、50%で満点
            normalized = min(motor_rate / 50.0, 1.0)
            return max_score * normalized

        except Exception:
            return max_score * 0.5

    def _calc_boat_score(self, race_id: int, pit_number: int) -> float:
        """
        ボート成績スコア（5点満点）
        """
        max_score = self.SCORE_WEIGHTS['boat']

        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT boat_second_rate
                FROM entries
                WHERE race_id = ? AND pit_number = ?
            ''', (race_id, pit_number))

            row = cursor.fetchone()
            cursor.close()

            if not row or row[0] is None:
                return max_score * 0.5

            boat_rate = row[0]

            # 平均30%を基準
            normalized = min(boat_rate / 50.0, 1.0)
            return max_score * normalized

        except Exception:
            return max_score * 0.5

    def _calc_grade_affinity_score(
        self,
        racer_number: str,
        race_grade: str,
        race_date: str
    ) -> float:
        """
        グレード適性スコア（5点満点）

        SG/G1経験者はグレード戦に強い
        """
        max_score = self.SCORE_WEIGHTS['grade_affinity']

        # 一般戦は全員同じ
        if race_grade == '一般':
            return max_score * 0.5

        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            # 過去1年のグレード別出走回数
            cursor.execute('''
                SELECT race_grade, COUNT(*) as cnt
                FROM entries e
                JOIN races r ON e.race_id = r.id
                WHERE e.racer_number = ?
                  AND r.race_date < ?
                  AND r.race_date >= date(?, '-365 days')
                GROUP BY race_grade
            ''', (racer_number, race_date, race_date))

            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                return max_score * 0.3

            grade_counts = {row[0]: row[1] for row in rows}

            # グレード経験に応じてスコア
            sg_count = grade_counts.get('SG', 0)
            g1_count = grade_counts.get('G1', 0)
            g2_count = grade_counts.get('G2', 0)

            # SG/G1経験が多いほど高評価
            experience_score = min((sg_count * 3 + g1_count * 2 + g2_count) / 30.0, 1.0)
            return max_score * experience_score

        except Exception:
            return max_score * 0.3

    def _calc_kimarite_affinity_score(
        self,
        racer_number: str,
        course: int,
        race_date: str
    ) -> float:
        """
        決まり手適性スコア（5点満点）

        コースに応じた決まり手の得意・不得意を評価
        """
        max_score = self.SCORE_WEIGHTS['kimarite']

        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            # コース別の決まり手を取得
            cursor.execute('''
                SELECT kimarite, COUNT(*) as cnt
                FROM results res
                JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
                JOIN races r ON res.race_id = r.id
                JOIN race_details rd ON res.race_id = rd.race_id AND res.pit_number = rd.pit_number
                WHERE e.racer_number = ?
                  AND rd.actual_course = ?
                  AND res.rank = '1'
                  AND r.race_date < ?
                  AND r.race_date >= date(?, '-365 days')
                GROUP BY kimarite
            ''', (racer_number, course, race_date, race_date))

            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                return max_score * 0.5

            # コースに適した決まり手をカウント
            kimarite_counts = {row[0]: row[1] for row in rows}
            total = sum(kimarite_counts.values())

            # コース別の有効な決まり手
            effective_kimarite = {
                1: ['逃げ'],
                2: ['差し', '逃げ'],
                3: ['差し', 'まくり差し'],
                4: ['まくり', 'まくり差し', '差し'],
                5: ['まくり', 'まくり差し'],
                6: ['まくり', 'まくり差し'],
            }

            effective = effective_kimarite.get(course, [])
            effective_count = sum(kimarite_counts.get(k, 0) for k in effective)

            if total > 0:
                ratio = effective_count / total
                return max_score * ratio

            return max_score * 0.5

        except Exception:
            return max_score * 0.5

    def _calc_rentai_score(self, racer_number: str, race_date: str) -> float:
        """
        連対率スコア（5点満点）

        2連対率・3連対率を評価
        ※ racer_featuresにはsecond_rate/third_rateカラムが存在しないため
          entriesテーブルから最新の出走時連対率を取得する（毎日更新・鮮度チェック不要）
        """
        max_score = self.SCORE_WEIGHTS['rentai']

        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            # entriesテーブルから当該選手の直近出走での連対率を取得
            # second_rate / third_rate はパーセント形式（0〜100）で格納されている
            cursor.execute('''
                SELECT e.second_rate, e.third_rate
                FROM entries e
                JOIN races r ON e.race_id = r.id
                WHERE e.racer_number = ?
                  AND r.race_date <= ?
                  AND e.second_rate IS NOT NULL
                ORDER BY r.race_date DESC, r.race_number DESC
                LIMIT 1
            ''', (racer_number, race_date))

            row = cursor.fetchone()
            cursor.close()

            if not row or row[0] is None:
                return max_score * 0.5

            second_rate = row[0] or 33.3   # パーセント形式: 平均33.3%
            third_rate  = row[1] or 50.0   # パーセント形式: 平均50.0%

            # 2連対率を重視（60%の重み）。全国平均33.3%を基準に評価
            avg_second = 33.3
            second_score = (second_rate / avg_second) * (max_score * 0.6)

            # 3連対率（40%の重み）。全国平均50.0%を基準に評価
            avg_third = 50.0
            third_score = (third_rate / avg_third) * (max_score * 0.4)

            return min(max_score, second_score + third_score)

        except Exception:
            return max_score * 0.5

    def _calc_data_completeness(self, result: PreInfoResult) -> float:
        """データ充実度を計算（0-1）"""
        # 各スコアが0より大きいかをチェック
        scores = [
            result.overall_score,
            result.course_score,
            result.venue_score,
            result.recent_form_score,
            result.class_score,
            result.avg_st_score,
            result.motor_score,
        ]

        available = sum(1 for s in scores if s > 0)
        return available / len(scores)

    def _calc_confidence(self, result: PreInfoResult) -> float:
        """信頼度を計算（0-1）"""
        # データ充実度ベース
        base_confidence = result.data_completeness

        # スコアが極端な場合は信頼度を上げる
        if result.total_score > 80 or result.total_score < 20:
            base_confidence = min(1.0, base_confidence * 1.2)

        return base_confidence


# 便利関数
def calculate_pre_score(
    race_id: int,
    pit_number: int,
    racer_number: str,
    venue_code: str,
    race_date: str,
    race_grade: str = '一般',
    db_path: str = "data/boatrace.db"
) -> float:
    """
    事前スコアを計算する便利関数

    Returns:
        総合スコア（0-100）
    """
    scorer = PreInfoScorer(db_path)
    result = scorer.calculate_pre_info_score(
        race_id, pit_number, racer_number, venue_code, race_date, race_grade
    )
    return result.total_score


# テスト用
if __name__ == "__main__":
    print("=" * 80)
    print("PreInfoScorer テスト")
    print("=" * 80)

    scorer = PreInfoScorer()

    # テストケース（実際のDBデータが必要）
    print("\n【スコア配分（設計値）】")
    total_max = sum(abs(v) for v in PreInfoScorer.SCORE_WEIGHTS.values())
    print(f"最大合計: {total_max}点")

    for name, weight in PreInfoScorer.SCORE_WEIGHTS.items():
        print(f"  {name}: {weight}点")

    print("\n" + "=" * 80)
    print("テスト完了")
    print("=" * 80)
