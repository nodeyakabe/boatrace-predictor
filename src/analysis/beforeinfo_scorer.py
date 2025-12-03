"""
直前情報スコアリングモジュール

統合ガイド（改善点/直前情報の予想モデルへの統合ガイド_20251202.md）に基づき、
直前情報を100点満点でスコアリングし、事前スコアと統合する。

スコア構成（100点満点）:
- 展示タイム: 25%
- ST（スタート）: 25%
- 進入隊形: 20%
- 前走成績: 15%
- チルト・風: 10%
- 調整重量/部品交換: 5%

最終統合: FINAL_SCORE = PRE_SCORE * 0.6 + BEFORE_SCORE * 0.4
"""

from typing import Dict, List, Optional, Tuple
import sqlite3
from pathlib import Path
from src.utils.db_connection_pool import get_connection


class BeforeInfoScorer:
    """直前情報スコアリングクラス"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path

        # スコア配分（100点満点）
        self.EXHIBITION_TIME_WEIGHT = 25.0  # 展示タイム
        self.ST_WEIGHT = 25.0               # スタートタイミング
        self.ENTRY_WEIGHT = 20.0            # 進入隊形
        self.PREV_RACE_WEIGHT = 15.0        # 前走成績
        self.TILT_WIND_WEIGHT = 10.0        # チルト・風
        self.PARTS_WEIGHT_WEIGHT = 5.0      # 部品交換・調整重量

    def calculate_beforeinfo_score(
        self,
        race_id: int,
        pit_number: int,
        beforeinfo_data: Optional[Dict] = None
    ) -> Dict:
        """
        直前情報スコアを計算

        Args:
            race_id: レースID
            pit_number: 艇番（1-6）
            beforeinfo_data: BeforeInfoScraper.get_race_beforeinfo()の戻り値
                            Noneの場合はDBから読み込み

        Returns:
            dict: {
                'total_score': float,           # 総合スコア（0-100点）
                'exhibition_time_score': float, # 展示タイムスコア
                'st_score': float,              # STスコア
                'entry_score': float,           # 進入隊形スコア
                'prev_race_score': float,       # 前走成績スコア
                'tilt_wind_score': float,       # チルト・風スコア
                'parts_weight_score': float,    # 部品・重量スコア
                'confidence': float,            # 信頼度（0.0-1.0）
                'data_completeness': float      # データ充実度（0.0-1.0）
            }
        """
        # データ取得
        if beforeinfo_data is None:
            beforeinfo_data = self._load_beforeinfo_from_db(race_id)

        if not beforeinfo_data or not beforeinfo_data.get('is_published'):
            # 直前情報がない場合は0点
            return self._get_empty_score()

        # 各項目のスコア計算
        exhibition_score = self._calc_exhibition_time_score(
            pit_number, beforeinfo_data.get('exhibition_times', {})
        )
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

        # データ充実度
        data_completeness = self._calc_data_completeness(beforeinfo_data, pit_number)

        # 信頼度（シグモイド関数）
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

    def _calc_exhibition_time_score(
        self,
        pit_number: int,
        exhibition_times: Dict[int, float]
    ) -> float:
        """
        展示タイムスコア計算（25点満点）

        相対順位で評価:
        1位: 25点, 2位: 18点, 3位: 12点, 4位: 6点, 5位: 3点, 6位: 0点
        """
        if not exhibition_times or pit_number not in exhibition_times:
            return 0.0

        # 順位を計算（タイムが速い順）
        sorted_pits = sorted(exhibition_times.items(), key=lambda x: x[1])
        rank = next((i + 1 for i, (pit, _) in enumerate(sorted_pits) if pit == pit_number), 6)

        # 順位別スコア
        rank_scores = {
            1: 25.0,
            2: 18.0,
            3: 12.0,
            4: 6.0,
            5: 3.0,
            6: 0.0
        }

        return rank_scores.get(rank, 0.0)

    def _calc_st_score(
        self,
        pit_number: int,
        start_timings: Dict[int, float],
        exhibition_courses: Dict[int, int]
    ) -> float:
        """
        STスコア計算（25点満点）

        範囲別評価:
        ST ≤ 0.10: +30点
        0.11-0.14: +20点
        0.15-0.18: +10点
        0.19-0.25: 0点
        0.26-: -10点
        フライング（負の値）: -25点追加

        交互作用（Opus推奨）:
        ST×(6-course): 外コースほどSTの重要度が高い
        """
        if not start_timings or pit_number not in start_timings:
            return 0.0

        st = start_timings[pit_number]
        course = exhibition_courses.get(pit_number, pit_number)  # デフォルトは枠なり

        # フライングチェック
        if st < 0:
            return -25.0  # フライング大幅減点

        # ST範囲別スコア
        if st <= 0.10:
            score = 30.0
        elif st <= 0.14:
            score = 20.0
        elif st <= 0.18:
            score = 10.0
        elif st <= 0.25:
            score = 0.0
        else:
            score = -10.0

        # ST×courseの交互作用（外コースほどSTが重要）
        # course 1-3: 係数0.8-1.0, course 4-6: 係数1.0-1.3
        course_importance = 0.8 + (6 - course) * 0.1
        score = score * course_importance

        # 25点満点に正規化（30点が最大なので調整）
        return min(score * (25.0 / 30.0), 25.0)

    def _calc_entry_score(
        self,
        pit_number: int,
        exhibition_courses: Dict[int, int]
    ) -> float:
        """
        進入隊形スコア計算（20点満点）

        枠なりとの差分で評価:
        - イン奪取（1コース取得）: +30点
        - 前づけで内へ（2コース取得）: +15点
        - 外へ追いやられる: -20点
        """
        if not exhibition_courses or pit_number not in exhibition_courses:
            return 0.0

        actual_course = exhibition_courses[pit_number]

        # 枠なり（pit_number == actual_course）からの変化
        if actual_course == 1 and pit_number != 1:
            # 1コース奪取
            score = 30.0
        elif actual_course == 2 and pit_number >= 3:
            # 2コース前づけ
            score = 15.0
        elif pit_number <= 2 and actual_course >= 4:
            # インから外に追いやられた
            score = -20.0
        elif pit_number == actual_course:
            # 枠なり（標準）
            score = 0.0
        else:
            # その他の進入変更（微調整）
            if actual_course < pit_number:
                # 内に入った
                score = 5.0
            else:
                # 外に出た
                score = -5.0

        # 20点満点に正規化
        return min(max(score * (20.0 / 30.0), -20.0), 20.0)

    def _calc_prev_race_score(
        self,
        pit_number: int,
        previous_race: Dict[int, Dict]
    ) -> float:
        """
        前走成績スコア計算（15点満点）

        着順評価:
        1着: +15点, 2着: +10点, 3着: +5点
        遅スタ（ST 0.20以上）: -5点
        """
        if not previous_race or pit_number not in previous_race:
            return 0.0

        prev = previous_race[pit_number]
        score = 0.0

        # 着順評価
        rank = prev.get('rank')
        if rank == 1:
            score += 15.0
        elif rank == 2:
            score += 10.0
        elif rank == 3:
            score += 5.0

        # 前走ST評価
        prev_st = prev.get('st')
        if prev_st and prev_st >= 0.20:
            score -= 5.0

        return min(max(score, -5.0), 15.0)

    def _calc_tilt_wind_score(
        self,
        pit_number: int,
        tilt_angles: Dict[int, float],
        exhibition_courses: Dict[int, int],
        weather: Dict
    ) -> float:
        """
        チルト・風スコア計算（10点満点）

        コース依存の非線形評価:
        - 外コース（4-6）: 伸び型（+チルト）を高評価
        - 内コース（1-3）: 乗り心地・差し型（-チルト）を高評価
        - 伸び型 + 向かい風強め: シナジー効果
        """
        if not tilt_angles or pit_number not in tilt_angles:
            return 0.0

        tilt = tilt_angles[pit_number]
        course = exhibition_courses.get(pit_number, pit_number)  # デフォルトは枠なり
        wind_speed = weather.get('wind_speed', 0)

        score = 0.0

        # コース依存スコア
        if course >= 4:
            # 外コース: 伸び型を評価
            if tilt >= 0.5:
                score += 5.0
            elif tilt >= 0.0:
                score += 0.0
            else:  # tilt < 0
                score -= 3.0
        else:
            # 内コース（1-3）: 差し・逃げは乗り心地重視
            if tilt >= 0.5:
                score -= 3.0
            elif tilt >= 0.0:
                score += 2.0
            else:  # tilt < 0
                score += 4.0

        # 伸び型 + 向かい風のシナジー効果
        # （向かい風は風向コードで判定するのが理想だが、ここでは風速で簡易判定）
        if tilt >= 0.5 and wind_speed >= 3:
            score += 3.0

        # 10点満点に正規化
        return min(max(score, -10.0), 10.0)

    def _calc_parts_weight_score(
        self,
        pit_number: int,
        parts_replacements: Dict[int, str],
        adjusted_weights: Dict[int, float],
        exhibition_courses: Dict[int, int]
    ) -> float:
        """
        部品交換・調整重量スコア計算（5点満点）

        ペナルティ方式:
        - ピストン交換（P）: -10点
        - リング交換（R）: -5点
        - 調整重量増（2kg以上）: -3点
        - 調整重量微増（1-2kg）: -1点

        ※統合ガイドの推奨は「過剰評価しない」
        """
        score = 0.0

        # 部品交換ペナルティ
        parts = parts_replacements.get(pit_number, '')
        if 'P' in parts:
            score -= 10.0
        if 'R' in parts:
            score -= 5.0

        # 調整重量ペナルティ
        weight = adjusted_weights.get(pit_number, 0.0)
        course = exhibition_courses.get(pit_number, pit_number)

        if weight >= 2.0:
            # 2kg以上の重量差（特に外コースで不利）
            if course >= 4:
                score -= 3.0
            else:
                score -= 2.0
        elif weight >= 1.0:
            score -= 1.0

        # 5点満点に正規化
        return min(max(score, -5.0), 5.0)

    def _calc_data_completeness(
        self,
        beforeinfo_data: Dict,
        pit_number: int
    ) -> float:
        """
        データ充実度を計算（0.0-1.0）

        各データ要素の有無をチェック
        """
        completeness_score = 0
        max_score = 7

        # 展示タイム
        if pit_number in beforeinfo_data.get('exhibition_times', {}):
            completeness_score += 1

        # ST
        if pit_number in beforeinfo_data.get('start_timings', {}):
            completeness_score += 1

        # 進入コース
        if pit_number in beforeinfo_data.get('exhibition_courses', {}):
            completeness_score += 1

        # チルト
        if pit_number in beforeinfo_data.get('tilt_angles', {}):
            completeness_score += 1

        # 調整重量
        if pit_number in beforeinfo_data.get('adjusted_weights', {}):
            completeness_score += 1

        # 前走成績
        if pit_number in beforeinfo_data.get('previous_race', {}):
            completeness_score += 1

        # 気象データ
        weather = beforeinfo_data.get('weather', {})
        if weather and weather.get('wind_speed') is not None:
            completeness_score += 1

        return completeness_score / max_score

    def _calc_confidence(self, total_score: float, data_completeness: float) -> float:
        """
        信頼度を計算（0.0-1.0）

        シグモイド関数を使用:
        confidence = sigmoid((total_score - 30) / 15) * data_completeness
        """
        import math

        # シグモイド関数
        def sigmoid(x):
            return 1 / (1 + math.exp(-x))

        # スコアベースの信頼度
        score_confidence = sigmoid((total_score - 30) / 15)

        # データ充実度で重み付け
        return score_confidence * data_completeness

    def _load_beforeinfo_from_db(self, race_id: int) -> Dict:
        """
        DBから直前情報を読み込み

        Args:
            race_id: レースID

        Returns:
            BeforeInfoScraper.get_race_beforeinfo()と同じ形式
        """
        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            # race_detailsから選手別データを取得
            cursor.execute("""
                SELECT
                    pit_number,
                    exhibition_time,
                    st_time,
                    tilt_angle,
                    parts_replacement,
                    adjusted_weight,
                    exhibition_course,
                    prev_race_course,
                    prev_race_st,
                    prev_race_rank
                FROM race_details
                WHERE race_id = ?
                ORDER BY pit_number
            """, (race_id,))

            rows = cursor.fetchall()

            if not rows:
                return {'is_published': False}

            # データを辞書形式に変換
            exhibition_times = {}
            start_timings = {}
            tilt_angles = {}
            parts_replacements = {}
            adjusted_weights = {}
            exhibition_courses = {}
            previous_race = {}

            for row in rows:
                pit = row[0]
                if row[1] is not None:
                    exhibition_times[pit] = row[1]
                if row[2] is not None:
                    start_timings[pit] = row[2]
                if row[3] is not None:
                    tilt_angles[pit] = row[3]
                if row[4]:
                    parts_replacements[pit] = row[4]
                if row[5] is not None:
                    adjusted_weights[pit] = row[5]
                if row[6] is not None:
                    exhibition_courses[pit] = row[6]

                # 前走成績
                if any([row[7], row[8], row[9]]):
                    previous_race[pit] = {}
                    if row[7] is not None:
                        previous_race[pit]['course'] = row[7]
                    if row[8] is not None:
                        previous_race[pit]['st'] = row[8]
                    if row[9] is not None:
                        previous_race[pit]['rank'] = row[9]

            # weatherテーブルから気象データを取得
            cursor.execute("""
                SELECT temperature, water_temperature, wind_speed, wave_height
                FROM weather w
                JOIN races r ON w.venue_code = r.venue_code AND w.weather_date = r.race_date
                WHERE r.id = ?
            """, (race_id,))

            weather_row = cursor.fetchone()
            weather = {}
            if weather_row:
                weather = {
                    'temperature': weather_row[0],
                    'water_temp': weather_row[1],
                    'wind_speed': weather_row[2],
                    'wave_height': weather_row[3]
                }

            cursor.close()

            # データが1つでもあれば公開済みとみなす
            is_published = bool(exhibition_times or start_timings or tilt_angles)

            return {
                'exhibition_times': exhibition_times,
                'start_timings': start_timings,
                'tilt_angles': tilt_angles,
                'parts_replacements': parts_replacements,
                'adjusted_weights': adjusted_weights,
                'exhibition_courses': exhibition_courses,
                'previous_race': previous_race,
                'weather': weather,
                'is_published': is_published
            }

        except Exception as e:
            print(f"DB読み込みエラー (race_id={race_id}): {e}")
            return {'is_published': False}

    def _get_empty_score(self) -> Dict:
        """空のスコアを返す"""
        return {
            'total_score': 0.0,
            'exhibition_time_score': 0.0,
            'st_score': 0.0,
            'entry_score': 0.0,
            'prev_race_score': 0.0,
            'tilt_wind_score': 0.0,
            'parts_weight_score': 0.0,
            'confidence': 0.0,
            'data_completeness': 0.0
        }


if __name__ == "__main__":
    # テスト実行
    scorer = BeforeInfoScorer()

    # サンプルデータでテスト
    sample_data = {
        'is_published': True,
        'exhibition_times': {1: 6.77, 2: 6.82, 3: 6.78, 4: 6.72, 5: 6.78, 6: 6.75},
        'start_timings': {1: 0.09, 2: 0.15, 3: 0.12, 4: -0.03, 5: 0.14, 6: 0.06},
        'exhibition_courses': {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
        'tilt_angles': {1: -0.5, 2: -0.5, 3: -0.5, 4: 0.0, 5: -0.5, 6: -0.5},
        'adjusted_weights': {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 1.0, 6: 0.0},
        'parts_replacements': {1: 'R', 2: 'R', 3: 'R', 4: 'R', 5: 'R', 6: 'R'},
        'previous_race': {5: {'course': 4, 'st': 0.17, 'rank': 5}},
        'weather': {'temperature': 13.0, 'wind_speed': 1, 'wave_height': 1}
    }

    print("="*70)
    print("BeforeInfoScorer テスト")
    print("="*70)

    for pit in range(1, 7):
        result = scorer.calculate_beforeinfo_score(
            race_id=999999,  # ダミー
            pit_number=pit,
            beforeinfo_data=sample_data
        )

        print(f"\n【{pit}号艇】")
        print(f"  総合スコア: {result['total_score']:.2f}点")
        print(f"  - 展示タイム: {result['exhibition_time_score']:.2f}点")
        print(f"  - ST: {result['st_score']:.2f}点")
        print(f"  - 進入: {result['entry_score']:.2f}点")
        print(f"  - 前走: {result['prev_race_score']:.2f}点")
        print(f"  - チルト・風: {result['tilt_wind_score']:.2f}点")
        print(f"  - 部品・重量: {result['parts_weight_score']:.2f}点")
        print(f"  信頼度: {result['confidence']:.3f}")
        print(f"  データ充実度: {result['data_completeness']:.3f}")
