"""
天候補正モジュール

風速・風向・波高に基づいて予測スコアを補正する
config/weather_rules.json の法則性を適用
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple


class WeatherAdjuster:
    """天候に基づくスコア補正クラス"""

    # 風向を分類するマッピング（16方位 → カテゴリ）
    WIND_DIRECTION_MAP = {
        # 向い風（スタート方向に向かって吹く風）→ 1コース有利
        '北': 'headwind',
        '北北東': 'headwind',
        '北北西': 'headwind',
        # 追い風（スタート方向から吹く風）→ まくり有利
        '南': 'tailwind',
        '南南東': 'tailwind',
        '南南西': 'tailwind',
        # 左横風
        '西': 'crosswind_left',
        '西北西': 'crosswind_left',
        '西南西': 'crosswind_left',
        '北西': 'crosswind_left',
        # 右横風
        '東': 'crosswind_right',
        '東北東': 'crosswind_right',
        '東南東': 'crosswind_right',
        '北東': 'crosswind_right',
        # 斜め風（影響少）
        '南東': 'diagonal',
        '南西': 'diagonal',
        # 旧フォーマット（手動入力用）
        '向い風': 'headwind',
        '追い風': 'tailwind',
        '横風': 'crosswind_right',
        '無風': 'calm'
    }

    def __init__(self, config_path: str = "config/weather_rules.json"):
        self.config_path = Path(config_path)
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict:
        """天候ルールをロード"""
        if not self.config_path.exists():
            return {}

        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_wind_category(self, wind_speed: float) -> str:
        """
        風速からカテゴリを判定

        Args:
            wind_speed: 風速（m/s）

        Returns:
            'low' / 'mid' / 'high'
        """
        if wind_speed is None:
            return 'unknown'

        categories = self.rules.get('wind_speed_categories', {})
        if wind_speed <= categories.get('low', {}).get('max', 2):
            return 'low'
        elif wind_speed <= categories.get('mid', {}).get('max', 5):
            return 'mid'
        else:
            return 'high'

    def get_wave_category(self, wave_height: float) -> str:
        """
        波高からカテゴリを判定

        Args:
            wave_height: 波高（cm）

        Returns:
            'calm' / 'mid' / 'rough'
        """
        if wave_height is None:
            return 'unknown'

        categories = self.rules.get('wave_height_categories', {})
        if wave_height <= categories.get('calm', {}).get('max', 2):
            return 'calm'
        elif wave_height <= categories.get('mid', {}).get('max', 5):
            return 'mid'
        else:
            return 'rough'

    def get_wind_direction_category(self, wind_direction: Optional[str]) -> str:
        """
        風向からカテゴリを判定

        Args:
            wind_direction: 風向（16方位または旧フォーマット）

        Returns:
            'headwind' / 'tailwind' / 'crosswind_left' / 'crosswind_right' / 'diagonal' / 'calm' / 'unknown'
        """
        if wind_direction is None:
            return 'unknown'

        return self.WIND_DIRECTION_MAP.get(wind_direction, 'unknown')

    def calculate_adjustment(
        self,
        venue_code: str,
        course: int,
        wind_speed: Optional[float] = None,
        wave_height: Optional[float] = None,
        wind_direction: Optional[str] = None
    ) -> Dict:
        """
        天候に基づくスコア補正を計算

        Args:
            venue_code: 会場コード（'01'-'24'）
            course: コース番号（1-6）
            wind_speed: 風速（m/s）
            wave_height: 波高（cm）
            wind_direction: 風向（16方位）

        Returns:
            {
                'adjustment': 補正値（-0.3 ~ +0.1）,
                'reason': 補正理由,
                'wind_category': 風速カテゴリ,
                'wave_category': 波高カテゴリ,
                'wind_direction_category': 風向カテゴリ
            }
        """
        result = {
            'adjustment': 0.0,
            'reason': '',
            'wind_category': 'unknown',
            'wave_category': 'unknown',
            'wind_direction_category': 'unknown'
        }

        if not self.rules:
            result['reason'] = '天候ルール未設定'
            return result

        wind_cat = self.get_wind_category(wind_speed)
        wave_cat = self.get_wave_category(wave_height)
        wind_dir_cat = self.get_wind_direction_category(wind_direction)
        result['wind_category'] = wind_cat
        result['wave_category'] = wave_cat
        result['wind_direction_category'] = wind_dir_cat

        reasons = []
        adjustment = 0.0

        # === 風向による補正 ===
        # 風速が一定以上の場合のみ風向の影響を考慮
        if wind_speed is not None and wind_speed >= 2.0:
            if wind_dir_cat == 'headwind':
                # 向い風: 1コース有利（スタート時に加速しやすい）
                if course == 1:
                    bonus = 0.03  # +3%
                    adjustment += bonus
                    reasons.append(f'向い風1コースボーナス({bonus:+.0%})')
                elif course in [4, 5, 6]:
                    # 外コースはやや不利
                    penalty = -0.02  # -2%
                    adjustment += penalty
                    reasons.append(f'向い風外コースペナルティ({penalty:+.0%})')

            elif wind_dir_cat == 'tailwind':
                # 追い風: まくりが決まりやすい（2-4コース有利）
                if course == 1:
                    penalty = -0.05  # -5%
                    adjustment += penalty
                    reasons.append(f'追い風1コースペナルティ({penalty:+.0%})')
                elif course in [2, 3, 4]:
                    bonus = 0.03  # +3%
                    adjustment += bonus
                    reasons.append(f'追い風{course}コースボーナス({bonus:+.0%})')

        # === 強風時の補正 ===
        if wind_cat == 'high':
            scoring_adj = self.rules.get('scoring_adjustments', {})
            wind_penalty = scoring_adj.get('strong_wind_course1_penalty', {})

            if course == 1:
                # 1コースへのペナルティ
                venue_specific = wind_penalty.get('venue_specific', {})
                if venue_code in venue_specific:
                    penalty = venue_specific[venue_code]
                    reasons.append(f'強風時1コースペナルティ({penalty:+.0%})')
                else:
                    penalty = wind_penalty.get('default', -0.10)
                    reasons.append(f'強風時1コースペナルティ(全国平均{penalty:+.0%})')
                adjustment += penalty
            else:
                # 外コースへのボーナス
                outer_bonus = scoring_adj.get('strong_wind_outer_bonus', {})
                bonus_key = f'course_{course}'
                if bonus_key in outer_bonus:
                    bonus = outer_bonus[bonus_key]
                    adjustment += bonus
                    reasons.append(f'強風時{course}コースボーナス({bonus:+.0%})')

        # === 高波時の補正（強風と同様のロジック） ===
        if wave_cat == 'rough':
            wave_rules = self.rules.get('venue_wave_rules', {})
            if venue_code in wave_rules:
                if course == 1:
                    diff = wave_rules[venue_code].get('diff', 0)
                    # 差異をペナルティとして反映（最大-0.15）
                    penalty = min(-diff * 0.5, -0.05)
                    adjustment += penalty
                    reasons.append(f'高波時1コースペナルティ({penalty:+.0%})')

        result['adjustment'] = adjustment
        result['reason'] = ', '.join(reasons) if reasons else '補正なし'

        return result

    def apply_to_predictions(
        self,
        predictions: list,
        venue_code: str,
        wind_speed: Optional[float] = None,
        wave_height: Optional[float] = None
    ) -> list:
        """
        予測結果に天候補正を適用

        Args:
            predictions: predict_race()の結果リスト
            venue_code: 会場コード
            wind_speed: 風速（m/s）
            wave_height: 波高（cm）

        Returns:
            天候補正適用後の予測結果
        """
        if wind_speed is None and wave_height is None:
            return predictions

        adjusted_predictions = []

        for pred in predictions:
            course = pred.get('pit_number', pred.get('course', 1))
            adj_result = self.calculate_adjustment(
                venue_code, course, wind_speed, wave_height
            )

            adjusted_pred = pred.copy()

            if adj_result['adjustment'] != 0:
                # total_scoreに補正を適用（パーセント）
                original_score = pred.get('total_score', 50)
                adjusted_score = original_score * (1 + adj_result['adjustment'])
                adjusted_pred['total_score'] = round(adjusted_score, 1)

                # 補正情報を追加
                adjusted_pred['weather_adjustment'] = adj_result['adjustment']
                adjusted_pred['weather_reason'] = adj_result['reason']

            adjusted_predictions.append(adjusted_pred)

        return adjusted_predictions


# テスト用
if __name__ == "__main__":
    adjuster = WeatherAdjuster()

    print("=== 天候補正テスト ===")
    print()

    # テストケース
    test_cases = [
        ("08", 1, 7.0, 3),   # 常滑、1コース、強風、中波
        ("08", 2, 7.0, 3),   # 常滑、2コース、強風、中波
        ("02", 1, 8.0, 2),   # 戸田、1コース、強風、静穏
        ("24", 1, 2.0, 1),   # 大村、1コース、弱風、静穏
    ]

    for venue, course, wind, wave in test_cases:
        result = adjuster.calculate_adjustment(venue, course, wind, wave)
        print(f"会場{venue} {course}コース 風速{wind}m 波高{wave}cm:")
        print(f"  補正: {result['adjustment']:+.1%}")
        print(f"  理由: {result['reason']}")
        print()
