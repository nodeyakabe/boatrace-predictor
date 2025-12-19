"""
レース物理モデル

ボートレースの物理的要素を簡易モデルで再現し、
シミュレーションの基盤を提供する。

主要な物理要素:
1. スタートタイミング: 各艇のST（±誤差）
2. 第1ターンまでの距離: コースによる有利不利
3. ターン成功率: 級別・気象条件で変動
4. 追い上げ/失速: モーター性能・選手技量
"""

import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional


@dataclass
class BoatState:
    """艇の状態を表すクラス"""
    pit_number: int
    course: int
    position: float  # ゴールまでの仮想的な「進み具合」（大きいほど先行）
    speed: float  # 相対速度
    turn_success_rate: float  # ターン成功率
    st_mean: float  # 平均ST
    st_std: float  # STの標準偏差
    is_stalled: bool = False  # 失速フラグ


class RacePhysicsModel:
    """
    レース物理シミュレーションモデル

    ボートレースの主要な物理要素を簡易モデル化:
    - スタート: コース別の位置とSTによるタイミング
    - 第1ターン: コース別の有利不利、ターン成功率
    - バックストレッチ〜ゴール: 速度と追い上げ
    """

    # コース別の第1ターンまでの相対距離（1コースを1.0として）
    # 1コースが最も近く、6コースが最も遠い
    COURSE_DISTANCE_TO_TURN = {
        1: 1.00,  # 1コースは最短
        2: 1.05,  # 2コースはやや遠い
        3: 1.10,
        4: 1.15,
        5: 1.20,
        6: 1.25,  # 6コースは最も遠い
    }

    # コース別のスタート位置（インが有利）
    # 数値が大きいほど先行しやすい
    COURSE_START_ADVANTAGE = {
        1: 1.00,  # 1コースは最も有利
        2: 0.85,
        3: 0.70,
        4: 0.55,
        5: 0.40,
        6: 0.30,  # 6コースは最も不利
    }

    # 級別のターン成功率ベース（通常時）
    GRADE_TURN_SUCCESS_RATE = {
        'A1': 0.95,
        'A2': 0.90,
        'B1': 0.85,
        'B2': 0.75,
    }

    # 強風時のターン成功率低下係数
    WIND_TURN_PENALTY = {
        'calm': 1.00,      # 無風〜微風（0-3m）
        'moderate': 0.95,  # 中風（4-5m）
        'strong': 0.85,    # 強風（6-7m）
        'storm': 0.70,     # 暴風（8m+）
    }

    # ターン失敗時のペナルティ（位置の遅れ）
    TURN_FAILURE_PENALTY = 0.15

    # 追い上げ/失速の確率
    COMEBACK_PROBABILITY = 0.10  # 追い上げ成功確率
    STALL_PROBABILITY = 0.05    # 失速確率

    def __init__(
        self,
        wind_speed: float = 0.0,
        wave_height: float = 0.0,
        wind_direction: Optional[str] = None
    ):
        """
        物理モデルの初期化

        Args:
            wind_speed: 風速（m/s）
            wave_height: 波高（cm）
            wind_direction: 風向
        """
        self.wind_speed = wind_speed
        self.wave_height = wave_height
        self.wind_direction = wind_direction
        self.wind_category = self._categorize_wind(wind_speed)

    def _categorize_wind(self, wind_speed: float) -> str:
        """風速をカテゴリに分類"""
        if wind_speed >= 8.0:
            return 'storm'
        elif wind_speed >= 6.0:
            return 'strong'
        elif wind_speed >= 4.0:
            return 'moderate'
        else:
            return 'calm'

    def get_turn_success_rate(self, grade: str) -> float:
        """
        級別と気象条件からターン成功率を計算

        Args:
            grade: 選手級別（A1, A2, B1, B2）

        Returns:
            ターン成功率（0-1）
        """
        base_rate = self.GRADE_TURN_SUCCESS_RATE.get(grade, 0.80)
        wind_factor = self.WIND_TURN_PENALTY.get(self.wind_category, 1.0)

        # 波高も考慮（10cm以上で影響）
        if self.wave_height >= 20:
            wave_factor = 0.90
        elif self.wave_height >= 10:
            wave_factor = 0.95
        else:
            wave_factor = 1.0

        return base_rate * wind_factor * wave_factor

    def estimate_boat_parameters(
        self,
        total_score: float,
        grade: str,
        avg_st: Optional[float] = None,
        motor_score: Optional[float] = None
    ) -> Dict:
        """
        スコアから艇のパラメータを推定

        Args:
            total_score: 総合スコア（0-100）
            grade: 選手級別
            avg_st: 平均ST（秒）
            motor_score: モータースコア

        Returns:
            艇のパラメータ辞書
        """
        # 速度係数（スコアから推定）
        # スコア100 -> 速度1.0、スコア50 -> 速度0.85
        speed = 0.70 + (total_score / 100.0) * 0.30

        # モータースコアで速度を補正
        if motor_score is not None:
            motor_factor = 1.0 + (motor_score - 10.0) / 100.0  # 基準10点
            speed *= motor_factor

        # STの標準偏差（級別で異なる）
        st_std_map = {
            'A1': 0.02,  # A1級は安定
            'A2': 0.03,
            'B1': 0.04,
            'B2': 0.06,  # B2級は不安定
        }
        st_std = st_std_map.get(grade, 0.04)

        # 平均STがない場合は級別デフォルト
        if avg_st is None:
            avg_st_map = {
                'A1': 0.12,
                'A2': 0.14,
                'B1': 0.16,
                'B2': 0.20,
            }
            avg_st = avg_st_map.get(grade, 0.15)

        # ターン成功率
        turn_rate = self.get_turn_success_rate(grade)

        return {
            'speed': speed,
            'st_mean': avg_st,
            'st_std': st_std,
            'turn_success_rate': turn_rate,
        }

    def simulate_start(
        self,
        boats: List[BoatState],
        rng: np.random.Generator
    ) -> List[BoatState]:
        """
        スタートをシミュレート

        Args:
            boats: 艇のリスト
            rng: 乱数生成器

        Returns:
            スタート後の艇リスト
        """
        for boat in boats:
            # STのゆらぎを追加
            st_error = rng.normal(0, boat.st_std)
            actual_st = boat.st_mean + st_error

            # スタート位置を計算
            # コースの有利さ + ST（小さいほど良い） + 速度
            course_advantage = self.COURSE_START_ADVANTAGE[boat.course]

            # STペナルティ（0.15秒が基準、それより遅いとペナルティ）
            st_penalty = max(0, actual_st - 0.15) * 2.0

            # フライング判定（STが0未満）
            if actual_st < 0:
                # フライングは大幅なペナルティ
                boat.position = -10.0
            else:
                # スタート後の位置
                boat.position = (
                    course_advantage * 0.5 +
                    boat.speed * 0.3 -
                    st_penalty * 0.2
                )

        return boats

    def simulate_first_turn(
        self,
        boats: List[BoatState],
        rng: np.random.Generator
    ) -> List[BoatState]:
        """
        第1ターンをシミュレート

        Args:
            boats: 艇のリスト
            rng: 乱数生成器

        Returns:
            ターン後の艇リスト
        """
        for boat in boats:
            # 第1ターンまでの距離ペナルティ
            distance_factor = self.COURSE_DISTANCE_TO_TURN[boat.course]
            boat.position -= (distance_factor - 1.0) * 0.3

            # ターン成功判定
            if rng.random() > boat.turn_success_rate:
                # ターン失敗: ペナルティを適用
                boat.position -= self.TURN_FAILURE_PENALTY
            else:
                # ターン成功: ややボーナス
                boat.position += 0.02

        return boats

    def simulate_back_stretch(
        self,
        boats: List[BoatState],
        rng: np.random.Generator
    ) -> List[BoatState]:
        """
        バックストレッチ〜ゴールをシミュレート

        Args:
            boats: 艇のリスト
            rng: 乱数生成器

        Returns:
            ゴール後の艇リスト
        """
        for boat in boats:
            # 追い上げ/失速判定
            if rng.random() < self.COMEBACK_PROBABILITY:
                # 追い上げ成功
                boat.position += 0.10 * boat.speed

            if rng.random() < self.STALL_PROBABILITY:
                # 失速
                boat.position -= 0.15
                boat.is_stalled = True

            # 速度による進行
            boat.position += boat.speed * 0.2

        return boats

    def simulate_race(
        self,
        boat_params: List[Dict],
        rng: np.random.Generator
    ) -> List[int]:
        """
        1レースをシミュレート

        Args:
            boat_params: 各艇のパラメータリスト
            rng: 乱数生成器

        Returns:
            順位リスト（ピット番号順）[1着艇のピット, 2着艇のピット, ...]
        """
        # 艇の状態を初期化
        boats = []
        for i, params in enumerate(boat_params):
            pit_number = i + 1
            course = params.get('course', pit_number)  # コースがなければピット番号

            boat = BoatState(
                pit_number=pit_number,
                course=course,
                position=0.0,
                speed=params['speed'],
                turn_success_rate=params['turn_success_rate'],
                st_mean=params['st_mean'],
                st_std=params['st_std'],
            )
            boats.append(boat)

        # レースフェーズをシミュレート
        boats = self.simulate_start(boats, rng)
        boats = self.simulate_first_turn(boats, rng)
        boats = self.simulate_back_stretch(boats, rng)

        # 位置で降順ソート（大きいほど先行）
        boats.sort(key=lambda b: b.position, reverse=True)

        # 順位を返す（ピット番号順）
        return [boat.pit_number for boat in boats]

    def get_position_from_result(self, result: List[int], pit_number: int) -> int:
        """
        結果からピット番号の順位を取得

        Args:
            result: シミュレーション結果（[1着ピット, 2着ピット, ...]）
            pit_number: 対象ピット番号

        Returns:
            順位（1-6）
        """
        try:
            return result.index(pit_number) + 1
        except ValueError:
            return 6  # 見つからない場合は最下位
