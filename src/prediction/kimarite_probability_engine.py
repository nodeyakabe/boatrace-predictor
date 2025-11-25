"""
決まり手確率計算エンジン

ベイズ推定を用いて各艇の決まり手確率を計算
"""

import sqlite3
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

from .kimarite_constants import (
    Kimarite,
    KIMARITE_NAMES,
    COURSE_KIMARITE_PRIOR,
    VENUE_WATER_QUALITY,
    VENUE_INNER_ADVANTAGE,
    get_wind_effect,
    estimate_motor_output_type,
    ST_EXCELLENT,
    ST_GOOD,
    ST_AVERAGE,
    ST_POOR,
    KIMARITE_SUCCESS_FACTORS
)

logger = logging.getLogger(__name__)


@dataclass
class KimariteFactors:
    """決まり手確率に影響する要因"""
    # 選手要因
    racer_number: str
    racer_kimarite_history: Dict[Kimarite, float]
    racer_st_average: float
    racer_win_rate: float

    # コース・会場要因
    pit_number: int
    actual_course: int
    venue_code: str
    venue_water_quality: str
    venue_inner_advantage: float

    # 環境要因
    wind_speed: float
    wind_direction: str
    wave_height: float
    water_temperature: float

    # モーター要因
    motor_number: int
    motor_2tan_rate: float
    motor_output_type: str
    exhibition_time: Optional[float] = None


class KimariteProbabilityEngine:
    """決まり手確率計算エンジン"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path
        self._kimarite_stats_cache = {}  # 選手別決まり手統計のキャッシュ

    def calculate_kimarite_probabilities(
        self,
        race_id: int
    ) -> Dict[int, Dict[Kimarite, float]]:
        """
        レースの各艇について決まり手確率を計算

        Args:
            race_id: レースID

        Returns:
            {pit_number: {Kimarite.NIGE: 0.75, ...}}
        """
        # レース情報とエントリー情報を取得
        race_info = self._get_race_info(race_id)
        entries = self._get_entries(race_id)
        weather_info = self._get_weather_info(race_info['venue_code'], race_info['race_date'])

        probabilities = {}

        for entry in entries:
            pit_number = entry['pit_number']
            actual_course = entry.get('actual_course')

            # actual_courseがNoneの場合はpit_numberを使用
            if actual_course is None:
                actual_course = pit_number

            # 要因データを収集
            factors = self._collect_factors(entry, actual_course, race_info, weather_info)

            # ベイズ推定で確率計算
            kimarite_probs = self._bayesian_estimation(factors)

            probabilities[pit_number] = kimarite_probs

        return probabilities

    def _get_race_info(self, race_id: int) -> Dict:
        """レース情報を取得"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT venue_code, race_date, race_number, race_grade
            FROM races
            WHERE id = ?
        """, (race_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            raise ValueError(f"Race ID {race_id} not found")

        return dict(row)

    def _get_entries(self, race_id: int) -> List[Dict]:
        """エントリー情報を取得"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                e.*,
                rd.actual_course,
                rd.st_time,
                rd.exhibition_time
            FROM entries e
            LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            WHERE e.race_id = ?
            ORDER BY e.pit_number
        """, (race_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def _get_weather_info(self, venue_code: str, race_date: str) -> Dict:
        """天候情報を取得"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM weather
            WHERE venue_code = ? AND weather_date = ?
        """, (venue_code, race_date))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        else:
            # デフォルト値
            return {
                'wind_speed': 0.0,
                'wind_direction': None,
                'wave_height': 0.0,
                'water_temperature': 25.0
            }

    def _collect_factors(
        self,
        entry: Dict,
        actual_course: int,
        race_info: Dict,
        weather_info: Dict
    ) -> KimariteFactors:
        """要因データを収集"""
        racer_number = entry['racer_number']
        venue_code = race_info['venue_code']

        # 選手の決まり手履歴を取得
        kimarite_history = self._get_racer_kimarite_history(racer_number, venue_code)

        # モーター出力タイプを推定
        motor_2tan_rate = entry.get('motor_second_rate')
        if motor_2tan_rate is None:
            motor_2tan_rate = 0.30  # デフォルト値

        motor_output_type = estimate_motor_output_type(
            motor_2tan_rate,
            entry.get('exhibition_time')
        )

        return KimariteFactors(
            racer_number=racer_number,
            racer_kimarite_history=kimarite_history,
            racer_st_average=entry.get('avg_st', 0.17),
            racer_win_rate=entry.get('win_rate', 0.0),
            pit_number=entry['pit_number'],
            actual_course=actual_course,
            venue_code=venue_code,
            venue_water_quality=VENUE_WATER_QUALITY.get(venue_code, '淡水'),
            venue_inner_advantage=VENUE_INNER_ADVANTAGE.get(venue_code, 1.0),
            wind_speed=weather_info.get('wind_speed', 0.0),
            wind_direction=weather_info.get('wind_direction'),
            wave_height=weather_info.get('wave_height', 0.0),
            water_temperature=weather_info.get('water_temperature', 25.0),
            motor_number=entry.get('motor_number', 0),
            motor_2tan_rate=motor_2tan_rate,
            motor_output_type=motor_output_type,
            exhibition_time=entry.get('exhibition_time')
        )

    def _get_racer_kimarite_history(
        self,
        racer_number: str,
        venue_code: str = None,
        days: int = 180
    ) -> Dict[Kimarite, float]:
        """
        選手の決まり手履歴を取得

        Args:
            racer_number: 選手登録番号
            venue_code: 会場コード（Noneなら全会場）
            days: 集計期間（日数）

        Returns:
            {Kimarite.NIGE: 0.80, Kimarite.SASHI: 0.10, ...}
        """
        cache_key = f"{racer_number}_{venue_code}_{days}"
        if cache_key in self._kimarite_stats_cache:
            return self._kimarite_stats_cache[cache_key]

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT winning_technique, COUNT(*) as count
            FROM results r
            JOIN races rc ON r.race_id = rc.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
                AND r.rank = '1'
                AND r.winning_technique IS NOT NULL
                AND rc.race_date >= date('now', '-' || ? || ' days')
        """
        params = [racer_number, days]

        if venue_code:
            query += " AND rc.venue_code = ?"
            params.append(venue_code)

        query += " GROUP BY winning_technique"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # 集計
        total_wins = sum(row[1] for row in rows)
        kimarite_stats = {}

        if total_wins > 0:
            for kimarite_code, count in rows:
                if kimarite_code in [k.value for k in Kimarite]:
                    kimarite = Kimarite(kimarite_code)
                    kimarite_stats[kimarite] = count / total_wins

        # デフォルト値で補完
        for k in Kimarite:
            if k not in kimarite_stats:
                kimarite_stats[k] = 0.01

        self._kimarite_stats_cache[cache_key] = kimarite_stats
        return kimarite_stats

    def _bayesian_estimation(
        self,
        factors: KimariteFactors
    ) -> Dict[Kimarite, float]:
        """
        ベイズ推定による決まり手確率計算

        P(決まり手|条件) = P(条件|決まり手) × P(決まり手) / P(条件)
        """
        course = factors.actual_course

        # 事前確率（コース別基本確率）
        prior_probs = COURSE_KIMARITE_PRIOR.get(course, COURSE_KIMARITE_PRIOR[1])

        # 尤度計算
        likelihoods = {}
        for kimarite in Kimarite:
            likelihood = 1.0

            # 選手の決まり手実績による尤度
            racer_factor = factors.racer_kimarite_history.get(kimarite, 0.01)
            likelihood *= self._adjust_likelihood(racer_factor, weight=0.3)

            # STによる尤度
            st_likelihood = self._st_likelihood(factors.racer_st_average, kimarite, course)
            likelihood *= st_likelihood

            # 会場特性による尤度
            venue_likelihood = self._venue_likelihood(factors.venue_inner_advantage, kimarite, course)
            likelihood *= venue_likelihood

            # 風の影響
            wind_likelihood = self._wind_likelihood(
                factors.wind_direction,
                factors.wind_speed,
                kimarite,
                course
            )
            likelihood *= wind_likelihood

            # モーター性能の影響
            motor_likelihood = self._motor_likelihood(
                factors.motor_2tan_rate,
                factors.motor_output_type,
                kimarite
            )
            likelihood *= motor_likelihood

            likelihoods[kimarite] = likelihood

        # 事後確率計算
        posterior_probs = {}
        total = 0.0

        for kimarite in Kimarite:
            posterior = prior_probs.get(kimarite, 0.01) * likelihoods[kimarite]
            posterior_probs[kimarite] = posterior
            total += posterior

        # 正規化
        if total > 0:
            for kimarite in posterior_probs:
                posterior_probs[kimarite] /= total

        return posterior_probs

    def _adjust_likelihood(self, factor: float, weight: float = 0.3) -> float:
        """要因の尤度を調整"""
        # 1.0を中心に、weightの範囲で変動
        return 1.0 + (factor - 0.5) * weight * 2

    def _st_likelihood(self, st_average: float, kimarite: Kimarite, course: int) -> float:
        """STタイミングが決まり手に与える影響"""
        if st_average is None:
            return 1.0

        # STが速い（0.10以下）場合
        if st_average <= ST_EXCELLENT:
            if course == 1 and kimarite == Kimarite.NIGE:
                return 1.3  # 1コースの逃げが決まりやすい
            elif course >= 3 and kimarite in [Kimarite.MAKURI, Kimarite.MAKURI_SASHI]:
                return 1.25  # まくりが決まりやすい
            elif kimarite == Kimarite.SASHI:
                return 0.9  # 差しが決まりにくい

        # STが良好（0.10-0.15）
        elif st_average <= ST_GOOD:
            if course == 1 and kimarite == Kimarite.NIGE:
                return 1.15
            elif course >= 3 and kimarite in [Kimarite.MAKURI, Kimarite.MAKURI_SASHI]:
                return 1.1

        # STが遅い（0.20以上）場合
        elif st_average >= ST_POOR:
            if kimarite == Kimarite.SASHI:
                return 1.2  # 差しが決まりやすい
            elif kimarite in [Kimarite.NIGE, Kimarite.MAKURI]:
                return 0.75  # 逃げ・まくりが決まりにくい

        return 1.0

    def _venue_likelihood(self, inner_advantage: float, kimarite: Kimarite, course: int) -> float:
        """会場特性（インコース有利度）が決まり手に与える影響"""
        if course == 1:
            if kimarite == Kimarite.NIGE:
                return inner_advantage
            else:
                return 2.0 - inner_advantage  # 逆補正
        elif course >= 3:
            if kimarite in [Kimarite.MAKURI, Kimarite.MAKURI_SASHI]:
                return 2.0 - inner_advantage  # センター有利なら高まる

        return 1.0

    def _wind_likelihood(
        self,
        wind_direction: str,
        wind_speed: float,
        kimarite: Kimarite,
        course: int
    ) -> float:
        """風が決まり手に与える影響"""
        if wind_speed is None or wind_speed < 1.0:
            return 1.0

        wind_effect = get_wind_effect(wind_direction, wind_speed, None)

        # 追い風の場合
        if wind_effect['追い風'] > 3:  # 3m/s以上の追い風
            if course == 1 and kimarite == Kimarite.NIGE:
                return 0.85  # 1コース逃げが決まりにくい
            elif course >= 2 and kimarite in [Kimarite.SASHI, Kimarite.MAKURI]:
                return 1.15  # 差し・まくりが決まりやすい

        # 向かい風の場合
        if wind_effect['向かい風'] > 3:  # 3m/s以上の向かい風
            if course == 1 and kimarite == Kimarite.NIGE:
                return 1.15  # 1コース逃げが決まりやすい
            elif kimarite == Kimarite.MAKURI:
                return 0.85  # まくりが決まりにくい

        return 1.0

    def _motor_likelihood(
        self,
        motor_2tan_rate: float,
        motor_output_type: str,
        kimarite: Kimarite
    ) -> float:
        """モーター性能が決まり手に与える影響"""
        if motor_2tan_rate is None:
            return 1.0

        likelihood = 1.0

        # 高性能モーター（2連率40%以上）
        if motor_2tan_rate >= 0.40:
            if motor_output_type == '出足型' and kimarite in [Kimarite.NIGE, Kimarite.SASHI]:
                likelihood = 1.25
            elif motor_output_type == '伸び型' and kimarite in [Kimarite.MAKURI, Kimarite.MAKURI_SASHI]:
                likelihood = 1.25
            elif motor_output_type == 'バランス型':
                likelihood = 1.15  # 全決まり手に対してやや有利

        # 低性能モーター（2連率25%以下）
        elif motor_2tan_rate <= 0.25:
            if kimarite in [Kimarite.NIGE, Kimarite.MAKURI]:
                likelihood = 0.75
            elif kimarite == Kimarite.MEGUMARE:
                likelihood = 1.3  # 恵まれが増える

        # 中性能モーター
        else:
            likelihood = 1.0

        return likelihood

    def calculate_win_probability(
        self,
        kimarite_probs: Dict[int, Dict[Kimarite, float]]
    ) -> Dict[int, float]:
        """
        決まり手確率から各艇の1着確率を計算

        Args:
            kimarite_probs: 各艇の決まり手確率

        Returns:
            {pit_number: win_probability}
        """
        win_probs = {}

        for pit, kimarite_dict in kimarite_probs.items():
            # 1着に繋がる決まり手の確率を合計
            # 恵まれは除外（恵まれは基本的に1着にならない）
            win_prob = sum(
                prob for k, prob in kimarite_dict.items()
                if k != Kimarite.MEGUMARE
            )
            win_probs[pit] = win_prob

        # 正規化
        total = sum(win_probs.values())
        if total > 0:
            for pit in win_probs:
                win_probs[pit] /= total

        return win_probs
