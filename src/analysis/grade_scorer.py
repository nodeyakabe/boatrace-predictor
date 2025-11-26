"""
グレード適性スコア計算モジュール
レースグレードに対する選手の適応力を評価
"""

import sqlite3
from typing import Dict, Optional
from datetime import datetime, timedelta


def laplace_smoothing(wins: int, trials: int, alpha: float = 1.5, k: int = 6) -> float:
    """
    ラプラス平滑化による確率推定

    Args:
        wins: 成功数（勝利数、複勝数など）
        trials: 総試行数（レース数）
        alpha: 平滑化パラメータ（デフォルト1.5）
        k: カテゴリ数（着順なので6）

    Returns:
        平滑化された確率
    """
    return (wins + alpha) / (trials + alpha * k)


class GradeScorer:
    """グレード適性スコア計算クラス"""

    # レースグレードの定義
    GRADE_HIERARCHY = {
        'SG': 6,        # 最高峰
        'G1': 5,
        'G2': 4,
        'G3': 3,
        'ルーキーシリーズ': 2,
        '一般': 1
    }

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def _connect(self):
        """データベース接続"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def calculate_grade_affinity_score(
        self,
        racer_number: int,
        race_grade: str,
        days: int = 365,
        max_score: float = 10.0
    ) -> Dict:
        """
        グレード適性スコアを計算

        Args:
            racer_number: 選手登録番号
            race_grade: レースグレード（SG, G1, G2, G3, 一般など）
            days: 過去何日間のデータを使用するか
            max_score: 最大スコア（デフォルト10点）

        Returns:
            {
                'score': 8.5,
                'grade': 'G1',
                'win_rate': 15.2,
                'top3_rate': 42.5,
                'total_races': 25,
                'confidence': 'High',
                'grade_level': 5
            }
        """
        conn = self._connect()
        cursor = conn.cursor()

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        # グレードが指定されていない場合は一般として扱う
        if not race_grade:
            race_grade = '一般'

        # 選手のそのグレードでの成績を取得
        query = """
            SELECT
                COUNT(*) as total_races,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN r.rank <= 3 THEN 1 ELSE 0 END) as top3,
                AVG(r.rank) as avg_rank
            FROM entries e
            JOIN races ra ON e.race_id = ra.id
            LEFT JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
            WHERE e.racer_number = ?
              AND ra.race_grade = ?
              AND ra.race_date BETWEEN ? AND ?
              AND r.rank IS NOT NULL
        """

        cursor.execute(query, (racer_number, race_grade, start_date.isoformat(), end_date.isoformat()))
        row = cursor.fetchone()

        conn.close()

        total_races = row['total_races'] if row else 0
        wins = row['wins'] if row else 0
        top3 = row['top3'] if row else 0
        avg_rank = row['avg_rank'] if row and row['avg_rank'] else 3.5

        # データがない場合の処理
        if total_races == 0:
            # グレードレベルに応じたデフォルトスコア
            grade_level = self.GRADE_HIERARCHY.get(race_grade, 1)

            # 高グレードほどデフォルトスコアを低く
            if grade_level >= 5:  # SG, G1
                default_score = max_score * 0.3
                confidence = 'Very Low'
            elif grade_level == 4:  # G2
                default_score = max_score * 0.4
                confidence = 'Low'
            elif grade_level == 3:  # G3
                default_score = max_score * 0.5
                confidence = 'Low'
            else:  # 一般、ルーキー
                default_score = max_score * 0.6
                confidence = 'Medium'

            return {
                'score': round(default_score, 2),
                'grade': race_grade,
                'win_rate': 0.0,
                'top3_rate': 0.0,
                'total_races': 0,
                'confidence': confidence,
                'grade_level': grade_level,
                'reason': 'no_experience'
            }

        # 成績指標を計算（ラプラス平滑化を適用）
        # データが少ない場合でも安定した推定値を得る
        smoothed_win_rate = laplace_smoothing(wins, total_races, alpha=1.5, k=6) * 100
        smoothed_top3_rate = laplace_smoothing(top3, total_races, alpha=1.5, k=2) * 100

        # 表示用は生の値
        win_rate = wins / total_races * 100
        top3_rate = top3 / total_races * 100

        # スコア計算ロジック（平滑化した値を使用）
        # 1. 勝率ベーススコア（0-60%）
        win_score = min(smoothed_win_rate / 20 * max_score * 0.6, max_score * 0.6)

        # 2. 複勝率ベーススコア（0-30%）
        top3_score = min(smoothed_top3_rate / 50 * max_score * 0.3, max_score * 0.3)

        # 3. 平均着順ベーススコア（0-10%）
        # 平均着順が良いほど高得点（1着=満点、6着=0点）
        rank_score = max(0, (6 - avg_rank) / 5 * max_score * 0.1)

        score = win_score + top3_score + rank_score

        # 信頼度の判定
        if total_races >= 20:
            if win_rate >= 15:
                confidence = 'High'
            elif win_rate >= 8:
                confidence = 'Medium'
            else:
                confidence = 'Low'
        elif total_races >= 10:
            confidence = 'Medium'
        else:
            confidence = 'Low'

        grade_level = self.GRADE_HIERARCHY.get(race_grade, 1)

        return {
            'score': round(score, 2),
            'grade': race_grade,
            'win_rate': round(win_rate, 1),
            'top3_rate': round(top3_rate, 1),
            'avg_rank': round(avg_rank, 2),
            'total_races': total_races,
            'confidence': confidence,
            'grade_level': grade_level
        }

    def calculate_batch_scores(
        self,
        racer_numbers: list,
        race_grade: str,
        days: int = 365,
        max_score: float = 10.0
    ) -> Dict[int, Dict]:
        """
        複数の選手のグレード適性スコアを一括計算

        Args:
            racer_numbers: [4320, 4321, ...]
            race_grade: レースグレード
            days: 過去何日間のデータを使用するか
            max_score: 最大スコア

        Returns:
            {
                4320: {'score': 8.5, ...},
                4321: {'score': 6.2, ...},
                ...
            }
        """
        results = {}

        for racer_number in racer_numbers:
            score_data = self.calculate_grade_affinity_score(
                racer_number, race_grade, days, max_score
            )
            results[racer_number] = score_data

        return results

    def get_racer_grade_versatility(
        self,
        racer_number: int,
        days: int = 365
    ) -> Dict:
        """
        選手のグレード汎用性を評価
        複数グレードでの成績を総合的に評価

        Args:
            racer_number: 選手登録番号
            days: 過去何日間のデータを使用するか

        Returns:
            {
                'versatility_score': 7.5,
                'grade_scores': {
                    'SG': 5.2,
                    'G1': 6.8,
                    'G2': 7.5,
                    'G3': 8.1,
                    '一般': 8.9
                },
                'best_grade': 'G3',
                'consistency': 'Medium'
            }
        """
        grades = ['SG', 'G1', 'G2', 'G3', '一般']
        grade_scores = {}

        for grade in grades:
            result = self.calculate_grade_affinity_score(racer_number, grade, days)
            if result['total_races'] > 0:
                grade_scores[grade] = result['score']

        if not grade_scores:
            return {
                'versatility_score': 0.0,
                'grade_scores': {},
                'best_grade': None,
                'consistency': 'Unknown'
            }

        # 汎用性スコア: 全グレードの平均
        versatility_score = sum(grade_scores.values()) / len(grade_scores)

        # 最も成績が良いグレード
        best_grade = max(grade_scores, key=grade_scores.get)

        # 一貫性: スコアの標準偏差で判定
        if len(grade_scores) > 1:
            import statistics
            std_dev = statistics.stdev(grade_scores.values())

            if std_dev < 1.5:
                consistency = 'High'
            elif std_dev < 2.5:
                consistency = 'Medium'
            else:
                consistency = 'Low'
        else:
            consistency = 'Unknown'

        return {
            'versatility_score': round(versatility_score, 2),
            'grade_scores': {g: round(s, 2) for g, s in grade_scores.items()},
            'best_grade': best_grade,
            'consistency': consistency
        }


if __name__ == "__main__":
    # テスト
    scorer = GradeScorer()

    print("=" * 80)
    print("グレード適性スコア計算テスト")
    print("=" * 80)

    # テストケース
    racer_number = 4320
    race_grade = "G3"

    print(f"\n選手番号: {racer_number}")
    print(f"レースグレード: {race_grade}")

    result = scorer.calculate_grade_affinity_score(racer_number, race_grade)

    print("\n【結果】")
    print(f"スコア: {result['score']:.2f}/10.0")
    print(f"グレード: {result['grade']} (レベル: {result['grade_level']})")
    print(f"出走数: {result['total_races']}回")

    if result['total_races'] > 0:
        print(f"勝率: {result['win_rate']}%")
        print(f"複勝率: {result['top3_rate']}%")
        print(f"平均着順: {result['avg_rank']}")
    else:
        print(f"理由: {result.get('reason', 'N/A')}")

    print(f"信頼度: {result['confidence']}")

    # 汎用性テスト
    print("\n" + "=" * 80)
    print("グレード汎用性評価")
    print("=" * 80)

    versatility = scorer.get_racer_grade_versatility(racer_number)

    print(f"\n選手番号: {racer_number}")
    print(f"汎用性スコア: {versatility['versatility_score']:.2f}/10.0")
    print(f"最も得意なグレード: {versatility['best_grade']}")
    print(f"一貫性: {versatility['consistency']}")

    if versatility['grade_scores']:
        print("\nグレード別スコア:")
        for grade, score in versatility['grade_scores'].items():
            print(f"  {grade}: {score:.2f}")

    print("\n" + "=" * 80)
