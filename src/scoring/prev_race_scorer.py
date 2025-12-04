"""
前走成績スコアラー
前回レースの結果から選手の調子を評価

仕様:
- 前走順位: 1着が最も有利、6着が不利
- 前走コース: 不利なコースからの好走は高評価
- 前走ST: 前回のスタート状況
"""

import sqlite3
from typing import Dict, Optional
from src.utils.db_connection_pool import get_connection


class PrevRaceScorer:
    """前走成績スコアラー"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path

        # 前走順位スコア
        self.RANK_SCORES = {
            1: 20.0,   # 1着（調子良い）
            2: 12.0,   # 2着
            3: 6.0,    # 3着
            4: 0.0,    # 4着
            5: -6.0,   # 5着
            6: -12.0   # 6着（調子悪い）
        }

        # コース別補正（不利なコースから好走は高評価）
        self.COURSE_DIFFICULTY = {
            1: 1.0,   # 1コースは有利（補正なし）
            2: 1.1,
            3: 1.2,
            4: 1.3,
            5: 1.4,
            6: 1.5    # 6コースは不利（高評価）
        }

        # スコアリングパラメータ
        self.MAX_SCORE = 25.0
        self.MIN_SCORE = -25.0

    def calculate_prev_race_score(
        self,
        race_id: int,
        pit_number: int
    ) -> Dict:
        """
        前走成績スコアを計算

        Args:
            race_id: レースID
            pit_number: 艇番（1-6）

        Returns:
            {'prev_race_score': float, 'prev_rank': int, 'prev_course': int, 'prev_st': float}
        """
        # 前走データを取得
        prev_data = self._get_prev_race_data(race_id, pit_number)

        if not prev_data:
            return {
                'prev_race_score': 0.0,
                'prev_rank': None,
                'prev_course': None,
                'prev_st': None,
                'reason': 'no_prev_data'
            }

        prev_rank = prev_data.get('prev_race_rank')
        prev_course = prev_data.get('prev_race_course')
        prev_st = prev_data.get('prev_race_st')

        # 前走順位スコア
        rank_score = 0.0
        if prev_rank and 1 <= prev_rank <= 6:
            rank_score = self.RANK_SCORES.get(prev_rank, 0.0)

            # コース補正（不利なコースからの好走は高評価）
            if prev_course and 1 <= prev_course <= 6 and prev_rank <= 3:
                difficulty = self.COURSE_DIFFICULTY.get(prev_course, 1.0)
                rank_score *= difficulty

        # STスコア（前走で良いSTを刻んだかどうか）
        st_score = 0.0
        if prev_st is not None:
            if prev_st <= 0.15:
                st_score = 5.0    # 良いST
            elif prev_st <= 0.18:
                st_score = 2.0
            elif prev_st >= 0.20:
                st_score = -5.0   # 悪いST

        # 総合スコア
        total_score = rank_score * 0.8 + st_score * 0.2

        # スコアをクリップ
        total_score = max(min(total_score, self.MAX_SCORE), self.MIN_SCORE)

        return {
            'prev_race_score': round(total_score, 1),
            'prev_rank': prev_rank,
            'prev_course': prev_course,
            'prev_st': prev_st
        }

    def _get_prev_race_data(self, race_id: int, pit_number: int) -> Optional[Dict]:
        """
        前走データを取得

        Args:
            race_id: レースID
            pit_number: 艇番

        Returns:
            前走データ辞書、なければNone
        """
        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            query = """
                SELECT prev_race_rank, prev_race_course, prev_race_st
                FROM race_details
                WHERE race_id = ? AND pit_number = ?
            """
            cursor.execute(query, (race_id, pit_number))
            row = cursor.fetchone()
            cursor.close()

            if row and any(r is not None for r in row):
                return {
                    'prev_race_rank': row[0],
                    'prev_race_course': row[1],
                    'prev_race_st': row[2]
                }
            return None
        except Exception as e:
            print(f"Warning: 前走データ取得エラー (race_id={race_id}, pit={pit_number}): {e}")
            return None


if __name__ == '__main__':
    # テスト実行
    scorer = PrevRaceScorer()

    print("=== 前走成績スコアラー テスト ===")

    # サンプルレースIDでテスト
    test_race_id = 133159

    for pit in range(1, 7):
        result = scorer.calculate_prev_race_score(test_race_id, pit)
        score = result.get('prev_race_score', 0)
        rank = result.get('prev_rank', '?')
        course = result.get('prev_course', '?')
        st = result.get('prev_st', '?')
        print(f"艇{pit}: 前走{rank}着（{course}コース、ST={st}）→ スコア={score:.1f}点")
