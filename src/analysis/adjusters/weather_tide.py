"""
天候・潮位補正モジュール

天候（風速、波高、風向）と潮位に基づくスコア補正を適用する。
race_predictor.pyから分離（2025-12-15）
"""

from datetime import datetime
from typing import Dict, List, Optional


class WeatherTideAdjuster:
    """
    天候・潮位補正を適用するクラス

    WeatherAdjusterとTideAdjusterを使用して、
    予測スコアに天候・潮位補正を適用する。
    """

    # 補正の最大影響値
    MAX_WEATHER_ADJUSTMENT = 5.0
    MAX_TIDE_ADJUSTMENT = 5.0

    def __init__(self, weather_adjuster, tide_adjuster):
        """
        Args:
            weather_adjuster: WeatherAdjusterインスタンス
            tide_adjuster: TideAdjusterインスタンス
        """
        self.weather_adjuster = weather_adjuster
        self.tide_adjuster = tide_adjuster

    def apply_weather_adjustment(
        self,
        predictions: List[Dict],
        venue_code: str,
        wind_speed: Optional[float],
        wave_height: Optional[float],
        wind_direction: Optional[str] = None,
        weather_condition: Optional[str] = None
    ) -> List[Dict]:
        """
        天候に基づくスコア補正を適用

        強風時（6m以上）は1コースにペナルティ、外コースにボーナスを付与。
        風向による補正（向い風は1コース有利、追い風はまくり有利）。

        Args:
            predictions: 予測結果リスト
            venue_code: 会場コード
            wind_speed: 風速（m/s）
            wave_height: 波高（cm）
            wind_direction: 風向（16方位）
            weather_condition: 天候条件（晴/曇/雨など）

        Returns:
            天候補正後の予測結果
        """
        if wind_speed is None and wave_height is None and wind_direction is None:
            return predictions

        for pred in predictions:
            pit_number = pred['pit_number']
            original_score = pred['total_score']

            adj_result = self.weather_adjuster.calculate_adjustment(
                venue_code,
                pit_number,
                wind_speed,
                wave_height,
                wind_direction,
                weather_condition
            )

            adjustment_percent = adj_result['adjustment']
            score_adjustment = original_score * adjustment_percent

            score_adjustment = max(
                -self.MAX_WEATHER_ADJUSTMENT,
                min(score_adjustment, self.MAX_WEATHER_ADJUSTMENT)
            )

            adjusted_score = original_score + score_adjustment
            adjusted_score = max(0.0, min(adjusted_score, 100.0))

            pred['total_score'] = round(adjusted_score, 1)

            if adjustment_percent != 0:
                pred['weather_adjustment'] = round(score_adjustment, 1)
                pred['weather_reason'] = adj_result['reason']
                pred['wind_category'] = adj_result['wind_category']
                pred['wave_category'] = adj_result['wave_category']
                pred['wind_direction_category'] = adj_result['wind_direction_category']

        return predictions

    def apply_tide_adjustment(
        self,
        predictions: List[Dict],
        venue_code: str,
        race_date: str,
        race_time: Optional[str]
    ) -> List[Dict]:
        """
        潮位に基づくスコア補正を適用

        満潮時は1コース有利、干潮時は荒れやすい。
        海水・汽水会場のみに適用。

        Args:
            predictions: 予測結果リスト
            venue_code: 会場コード
            race_date: レース日付（YYYY-MM-DD）
            race_time: レース時刻（HH:MM）

        Returns:
            潮位補正後の予測結果
        """
        # 海水会場でない場合は補正なし
        if venue_code not in self.tide_adjuster.SEAWATER_VENUES:
            return predictions

        # 潮位データがない会場は補正なし
        if venue_code not in self.tide_adjuster.TIDE_DATA_VENUES:
            return predictions

        # レース日時を構築
        race_datetime = self._parse_race_datetime(race_date, race_time)
        if race_datetime is None:
            return predictions

        # 潮位データを取得
        tide_data = self.tide_adjuster.get_tide_level(venue_code, race_datetime)
        if tide_data is None:
            return predictions

        for pred in predictions:
            pit_number = pred['pit_number']
            original_score = pred['total_score']

            adj_result = self.tide_adjuster.calculate_adjustment(
                venue_code,
                pit_number,
                tide_data=tide_data
            )

            adjustment_percent = adj_result['adjustment']
            if adjustment_percent != 0:
                score_adjustment = original_score * adjustment_percent

                score_adjustment = max(
                    -self.MAX_TIDE_ADJUSTMENT,
                    min(score_adjustment, self.MAX_TIDE_ADJUSTMENT)
                )

                adjusted_score = original_score + score_adjustment
                adjusted_score = max(0.0, min(adjusted_score, 100.0))

                pred['total_score'] = round(adjusted_score, 1)
                pred['tide_adjustment'] = round(score_adjustment, 1)
                pred['tide_reason'] = adj_result['reason']
                pred['tide_phase'] = adj_result['tide_phase']

        return predictions

    def _parse_race_datetime(
        self,
        race_date: str,
        race_time: Optional[str]
    ) -> Optional[datetime]:
        """レース日時をパース"""
        if not race_date:
            return None

        try:
            if race_time:
                return datetime.strptime(f"{race_date} {race_time}", "%Y-%m-%d %H:%M")
            else:
                return datetime.strptime(f"{race_date} 12:00", "%Y-%m-%d %H:%M")
        except ValueError:
            return None
