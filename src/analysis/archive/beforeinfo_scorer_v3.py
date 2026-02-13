"""
直前情報スコアリングモジュール v3

展示スコアラーv3を統合したバージョン

変更点:
- BeforeInfoScorerを継承
- _calc_exhibition_time_score() をオーバーライドしてExhibitionScorerV3を使用
- v3スコア(-30～+50点)を0-25点に正規化
"""

from typing import Dict, List, Optional, Tuple
import sqlite3
from pathlib import Path
import sys
import os

# パス設定
if __name__ != '__main__':
    from src.analysis.beforeinfo_scorer import BeforeInfoScorer
    from src.scoring.exhibition_scorer_v3 import ExhibitionScorerV3
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from src.analysis.beforeinfo_scorer import BeforeInfoScorer
    from src.scoring.exhibition_scorer_v3 import ExhibitionScorerV3


class BeforeInfoScorerV3(BeforeInfoScorer):
    """直前情報スコアリングクラス v3（展示スコアラーv3統合版）"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        # 親クラス初期化
        super().__init__(db_path)

        # 展示スコアラーv3インスタンス
        self.exhibition_scorer = ExhibitionScorerV3(db_path=db_path)

    def calculate_beforeinfo_score(
        self,
        race_id: int,
        pit_number: int,
        beforeinfo_data: Optional[Dict] = None
    ) -> Dict:
        """
        直前情報スコアを計算（展示スコアv3使用版）

        Args:
            race_id: レースID
            pit_number: 艇番（1-6）
            beforeinfo_data: BeforeInfoScraper.get_race_beforeinfo()の戻り値

        Returns:
            dict: スコア詳細
        """
        # データ取得
        if beforeinfo_data is None:
            beforeinfo_data = self._load_beforeinfo_from_db(race_id)

        if not beforeinfo_data or not beforeinfo_data.get('is_published'):
            return self._get_empty_score()

        # 会場コード・コース・級別などを取得
        venue_code, racer_rank, actual_course = self._get_race_context(race_id, pit_number)

        # 展示タイムスコア（v3使用）
        exhibition_score = self._calc_exhibition_time_score_v3(
            venue_code=venue_code,
            pit_number=pit_number,
            exhibition_times=beforeinfo_data.get('exhibition_times', {}),
            racer_rank=racer_rank,
            actual_course=actual_course,
            st_time=beforeinfo_data.get('start_timings', {}).get(pit_number)
        )

        # 他のスコアは親クラスのメソッドを使用
        st_score = self._calc_st_score(
            pit_number,
            beforeinfo_data.get('start_timings', {}),
            beforeinfo_data.get('exhibition_courses', {})
        )
        entry_score = self._calc_entry_score(
            pit_number, beforeinfo_data.get('exhibition_courses', {})
        )
        prev_race_score = self._calc_prev_race_score(
            pit_number, beforeinfo_data.get('previous_race', {})
        )
        tilt_wind_score = self._calc_tilt_wind_score(
            pit_number,
            beforeinfo_data.get('tilt_angles', {}),
            beforeinfo_data.get('exhibition_courses', {}),
            beforeinfo_data.get('weather', {})
        )
        parts_weight_score = self._calc_parts_weight_score(
            pit_number,
            beforeinfo_data.get('parts_replacements', {}),
            beforeinfo_data.get('adjusted_weights', {}),
            beforeinfo_data.get('exhibition_courses', {})
        )

        # 総合スコア
        total_score = (
            exhibition_score +
            st_score +
            entry_score +
            prev_race_score +
            tilt_wind_score +
            parts_weight_score
        )

        # データ充実度・信頼度
        data_completeness = self._calc_data_completeness(beforeinfo_data, pit_number)
        confidence = self._calc_confidence(total_score, data_completeness)

        return {
            'total_score': total_score,
            'exhibition_time_score': exhibition_score,
            'st_score': st_score,
            'entry_score': entry_score,
            'prev_race_score': prev_race_score,
            'tilt_wind_score': tilt_wind_score,
            'parts_weight_score': parts_weight_score,
            'confidence': confidence,
            'data_completeness': data_completeness
        }

    def _get_race_context(self, race_id: int, pit_number: int) -> tuple:
        """
        レース・選手のコンテキスト情報取得

        Returns:
            (venue_code, racer_rank, actual_course)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                r.venue_code,
                e.racer_rank,
                rd.actual_course
            FROM races r
            JOIN entries e ON r.id = e.race_id AND e.pit_number = ?
            LEFT JOIN race_details rd ON r.id = rd.race_id AND rd.pit_number = ?
            WHERE r.id = ?
        """, (pit_number, pit_number, race_id))

        row = cursor.fetchone()
        conn.close()

        if row:
            return row[0], row[1], row[2]
        else:
            return None, None, None

    def _calc_exhibition_time_score_v3(
        self,
        venue_code: str,
        pit_number: int,
        exhibition_times: Dict[int, float],
        racer_rank: Optional[str] = None,
        actual_course: Optional[int] = None,
        st_time: Optional[float] = None
    ) -> float:
        """
        展示タイムスコア計算 v3（ExhibitionScorerV3使用）

        Args:
            venue_code: 会場コード
            pit_number: 艇番
            exhibition_times: {pit: time} の辞書
            racer_rank: 級別（'A1', 'A2', ...）
            actual_course: 実際のコース（1-6）
            st_time: STタイム

        Returns:
            float: 0-25点のスコア
        """
        if not exhibition_times or pit_number not in exhibition_times:
            return 0.0

        if not venue_code:
            # venue_codeがない場合は親クラスのメソッド使用
            return super()._calc_exhibition_time_score(pit_number, exhibition_times)

        # ExhibitionScorerV3でスコア計算
        beforeinfo = {'exhibition_times': exhibition_times}
        racer_data = {'rank': racer_rank} if racer_rank else None

        v3_result = self.exhibition_scorer.calculate_exhibition_score(
            venue_code,
            pit_number,
            beforeinfo,
            racer_data=racer_data,
            actual_course=actual_course,
            st_time=st_time
        )

        v3_score = v3_result['exhibition_score']

        # v3スコア範囲: -30 ～ +50 (計80点幅)
        # これを 0-25点に正規化
        # 変換式: (v3_score + 30) / 80 * 25
        normalized_score = (v3_score + 30) / 80.0 * self.EXHIBITION_TIME_WEIGHT

        # クリップ
        return max(0.0, min(self.EXHIBITION_TIME_WEIGHT, normalized_score))


# 簡易テスト用
if __name__ == '__main__':
    import sys
    import os

    # プロジェクトルートに移動
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    sys.path.append(project_root)

    scorer = BeforeInfoScorerV3()

    # テストデータ
    test_exhibition_times = {
        1: 6.70,  # 1位
        2: 6.75,
        3: 6.80,
        4: 6.85,
        5: 6.90,
        6: 7.00
    }

    # v3スコア計算
    score = scorer._calc_exhibition_time_score_v3(
        venue_code='01',  # 桐生
        pit_number=1,
        exhibition_times=test_exhibition_times,
        racer_rank='A1',
        actual_course=1,
        st_time=0.10
    )

    print(f"展示1位 × A1級 × コース1 × ST良好のスコア: {score:.2f}点 / 25.0点")

    # 最悪ケース
    score_worst = scorer._calc_exhibition_time_score_v3(
        venue_code='01',
        pit_number=6,
        exhibition_times=test_exhibition_times,
        racer_rank='B2',
        actual_course=6,
        st_time=0.50
    )

    print(f"展示6位 × B2級 × コース6 × ST不良のスコア: {score_worst:.2f}点 / 25.0点")
