"""
天候補正モジュール

風速・風向・波高に基づいて予測スコアを補正する
config/weather_rules.json の法則性を適用
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

# 16方位を角度（度）にマッピング（北=0度、時計回り）
DIRECTION_ANGLES: Dict[str, float] = {
    '北': 0.0, '北北東': 22.5, '北東': 45.0, '東北東': 67.5,
    '東': 90.0, '東南東': 112.5, '南東': 135.0, '南南東': 157.5,
    '南': 180.0, '南南西': 202.5, '南西': 225.0, '西南西': 247.5,
    '西': 270.0, '西北西': 292.5, '北西': 315.0, '北北西': 337.5,
}

# 会場別の追い風方向（DBの実データで1コース勝率が最も高い風向 = 追い風）
# 2026-03-27 DB実データ再検証（6年分・n>=200、全24会場を網羅的に確認）
# 追い風 = C1（インコース）有利 = C1勝率最高の風向（boatrace.jp公式定義に基づく）
VENUE_TAILWIND_DIRECTIONS: Dict[str, str] = {
    '01': '南東',    # 桐生   n=871,  C1=57.2% ✅変更なし
    '02': '北東',    # 戸田   n=494,  C1=46.4% ✅変更なし
    # '03': 未定義,  # 江戸川  風向によるC1差が小さく(46-50%)・全データn<300で根拠不足 → crosswind扱い
    '04': '東南東',  # 平和島  n=4540, C1=46.8% ✅変更なし
    '05': '南南西',  # 多摩川  n=2434, C1=55.5% ✅変更なし
    '06': '西南西',  # 浜名湖  n=981,  C1=58.3% ✅変更なし
    '07': '東北東',  # 蒲郡   n=576,  C1=60.9% 修正
    '08': '南南西',  # 常滑   n=2529, C1=61.5% 修正
    '09': '北北東',  # 津    n=1089, C1=64.6% 修正
    '10': '北北東',  # 三国   n=412,  C1=61.7% 修正 ※nやや少
    '11': '北北東',  # 琵琶湖  n=1800, C1=57.2% 修正
    '12': '北北東',  # 住之江  n=5080, C1=60.9% 修正
    '13': '南西',    # 尼崎   n=1156, C1=63.6% ✅変更なし
    '14': '南南東',  # 鳴門   n=986,  C1=54.6% 修正（旧定義と逆）
    '15': '東南東',  # 丸亀   n=1334, C1=62.5% 修正
    '16': '西南西',  # 児島   n=4024, C1=57.9% ✅変更なし
    '17': '北北東',  # 宮島   n=1672, C1=61.0% 修正
    '18': '南南東',  # 徳山   n=2551, C1=65.4% 修正
    '19': '南南西',  # 下関   n=1375, C1=65.0% 修正（旧定義と逆）
    '20': '北北東',  # 若松   n=983,  C1=65.3% 修正
    '21': '西南西',  # 芦屋   n=945,  C1=65.8% 修正
    '22': '南西',    # 福岡   n=5820, C1=57.0% 修正（旧定義と逆）
    '23': '北北東',  # 唐津   n=364,  C1=63.5% 修正 ※nやや少
    '24': '西南西',  # 大村   n=2570, C1=67.9% ✅変更なし
}


def classify_wind_direction(wind_direction: Optional[str], venue_code: Optional[str] = None) -> str:
    """
    風向を会場別に追い風/向かい風/横風/無風/不明に分類する

    Args:
        wind_direction: 16方位の風向文字列（例: '北北東'）
        venue_code: 会場コード（'01'～'24'）。Noneの場合は旧来の全会場共通分類を使用

    Returns:
        'tailwind' / 'headwind' / 'crosswind' / 'calm' / 'unknown'
    """
    if wind_direction is None:
        return 'unknown'
    if wind_direction in ('無風', 'calm'):
        return 'calm'
    # 旧フォーマット（手動入力）
    if wind_direction == '向い風':
        return 'headwind'
    if wind_direction == '追い風':
        return 'tailwind'
    if wind_direction == '横風':
        return 'crosswind'

    wind_angle = DIRECTION_ANGLES.get(wind_direction)
    if wind_angle is None:
        return 'unknown'

    if venue_code and venue_code in VENUE_TAILWIND_DIRECTIONS:
        tailwind_dir = VENUE_TAILWIND_DIRECTIONS[venue_code]
        tailwind_angle = DIRECTION_ANGLES.get(tailwind_dir)
        if tailwind_angle is not None:
            diff = abs((wind_angle - tailwind_angle + 360) % 360)
            if diff > 180:
                diff = 360 - diff
            if diff <= 45:
                return 'tailwind'
            elif diff >= 135:
                return 'headwind'
            else:
                return 'crosswind'

    # venue_code未指定または不明会場: 旧来の全会場共通分類（後方互換）
    legacy_tailwind = {'南', '南南東', '南南西', '南東', '南西'}
    legacy_headwind = {'北', '北北東', '北北西', '北東', '北西'}
    legacy_crosswind_left = {'西', '西北西', '西南西'}
    legacy_crosswind_right = {'東', '東北東', '東南東'}
    if wind_direction in legacy_tailwind:
        return 'tailwind'
    if wind_direction in legacy_headwind:
        return 'headwind'
    if wind_direction in legacy_crosswind_left:
        return 'crosswind'
    if wind_direction in legacy_crosswind_right:
        return 'crosswind'
    return 'unknown'


class WeatherAdjuster:
    """天候に基づくスコア補正クラス"""

    # 風向を分類するマッピング（16方位 → カテゴリ）
    # 2025-12-15 データ分析に基づく修正:
    # - 追い風（南系）: 1C勝率59.2% → 1コース有利
    # - 向い風（北系）: 1C勝率56.9% → まくり・差し有利
    WIND_DIRECTION_MAP = {
        # 追い風（スタート方向から吹く風）→ 1コース有利（伸びが効く）
        '南': 'tailwind',
        '南南東': 'tailwind',
        '南南西': 'tailwind',
        '南東': 'tailwind',      # 南東も追い風グループに追加
        '南西': 'tailwind',      # 南西も追い風グループに追加
        # 向い風（スタート方向に向かって吹く風）→ まくり・差し有利
        '北': 'headwind',
        '北北東': 'headwind',
        '北北西': 'headwind',
        '北東': 'headwind',      # 北東も向い風グループに追加
        '北西': 'headwind',      # 北西も向い風グループに追加
        # 左横風
        '西': 'crosswind_left',
        '西北西': 'crosswind_left',
        '西南西': 'crosswind_left',
        # 右横風
        '東': 'crosswind_right',
        '東北東': 'crosswind_right',
        '東南東': 'crosswind_right',
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

    def get_wind_direction_category(self, wind_direction: Optional[str], venue_code: Optional[str] = None) -> str:
        """
        風向からカテゴリを判定（会場別対応版）

        Args:
            wind_direction: 風向（16方位または旧フォーマット）
            venue_code: 会場コード（省略時は後方互換の全会場共通分類）

        Returns:
            'headwind' / 'tailwind' / 'crosswind' / 'calm' / 'unknown'
        """
        return classify_wind_direction(wind_direction, venue_code)

    def calculate_adjustment(
        self,
        venue_code: str,
        course: int,
        wind_speed: Optional[float] = None,
        wave_height: Optional[float] = None,
        wind_direction: Optional[str] = None,
        weather_condition: Optional[str] = None  # NEW: 天候（晴/曇/雨）
    ) -> Dict:
        """
        天候に基づくスコア補正を計算

        Args:
            venue_code: 会場コード（'01'-'24'）
            course: コース番号（1-6）
            wind_speed: 風速（m/s）
            wave_height: 波高（cm）
            wind_direction: 風向（16方位）
            weather_condition: 天候（晴/曇/雨/雪/霧/台風）

        Returns:
            {
                'adjustment': 補正値（-0.3 ~ +0.1）,
                'reason': 補正理由,
                'wind_category': 風速カテゴリ,
                'wave_category': 波高カテゴリ,
                'wind_direction_category': 風向カテゴリ,
                'weather_condition': 天候
            }
        """
        result = {
            'adjustment': 0.0,
            'reason': '',
            'wind_category': 'unknown',
            'wave_category': 'unknown',
            'wind_direction_category': 'unknown',
            'weather_condition': weather_condition or 'unknown'  # NEW
        }

        if not self.rules:
            result['reason'] = '天候ルール未設定'
            return result

        wind_cat = self.get_wind_category(wind_speed)
        wave_cat = self.get_wave_category(wave_height)
        wind_dir_cat = self.get_wind_direction_category(wind_direction, venue_code)
        result['wind_category'] = wind_cat
        result['wave_category'] = wave_cat
        result['wind_direction_category'] = wind_dir_cat

        reasons = []
        adjustment = 0.0

        # === 風向による補正 ===
        # 2025-12-15 データ分析結果に基づく補正:
        # - 追い風（南系）: 1C勝率59.2%（弱風時60.6%）→ 1コース有利
        # - 向い風（北系）: 1C勝率56.9%（強風時55.4%）→ まくり・差し有利
        # 風速が一定以上の場合のみ風向の影響を考慮
        if wind_speed is not None and wind_speed >= 2.0:
            # 風速による補正係数（風速が強いほど影響大）
            wind_multiplier = min(wind_speed / 5.0, 1.5)  # 5mで1.0、7.5m以上で1.5

            if wind_dir_cat == 'tailwind':
                # 追い風: 1コース有利（伸びが効く、スリットで有利）
                # データ: 追い風×中風で1C勝率60.1%（向い風より+2.5%）
                if course == 1:
                    bonus = 0.03 * wind_multiplier  # +3%（基準）
                    adjustment += bonus
                    reasons.append(f'追い風1コースボーナス({bonus:+.1%})')
                elif course in [5, 6]:
                    # 追い風強風時は外コースがやや不利（1コースの伸びに負ける）
                    penalty = -0.02 * wind_multiplier  # -2%
                    adjustment += penalty
                    reasons.append(f'追い風外コースペナルティ({penalty:+.1%})')

            elif wind_dir_cat == 'headwind':
                # 向い風: まくり・差しが決まりやすい（4-6コース有利）
                # データ: 向い風×強風で4C 10.6%、6C 3.4%（追い風より高い）
                if course == 1:
                    penalty = -0.03 * wind_multiplier  # -3%
                    adjustment += penalty
                    reasons.append(f'向い風1コースペナルティ({penalty:+.1%})')
                elif course in [4, 5, 6]:
                    # 外コースにボーナス（差し・まくりが決まりやすい）
                    bonus = 0.02 * wind_multiplier  # +2%
                    adjustment += bonus
                    reasons.append(f'向い風{course}コースボーナス({bonus:+.1%})')

        # === 強風時の補正（風速6m以上） ===
        # 2025-12-15 データ分析結果:
        # - 風速2m以下: 1C勝率59.7%
        # - 風速6m以上: 1C勝率52.3% → 差分-7.4%
        # - 荒れ率: 弱風40.3% → 強風47.7%（1.18倍）
        # - 2-4コースは強風時にやや勝率上昇
        if wind_cat == 'high':
            scoring_adj = self.rules.get('scoring_adjustments', {})
            wind_penalty = scoring_adj.get('strong_wind_course1_penalty', {})

            if course == 1:
                # 1コースへのペナルティ（会場別）
                venue_specific = wind_penalty.get('venue_specific', {})
                if venue_code in venue_specific:
                    penalty = venue_specific[venue_code]
                    reasons.append(f'強風時1コースペナルティ({penalty:+.0%})')
                else:
                    penalty = wind_penalty.get('default', -0.10)
                    reasons.append(f'強風時1コースペナルティ(全国平均{penalty:+.0%})')
                adjustment += penalty
            else:
                # 外コースへのボーナス（データ分析に基づく最適化）
                # 風速6m以上のデータ:
                # - 2C: 15.3%（弱風13.4%比+1.9%）
                # - 3C: 13.4%（弱風11.0%比+2.4%）
                # - 4C: 11.2%（弱風9.4%比+1.8%）
                # - 5C: 6.0%（弱風5.1%比+0.9%）
                # - 6C: 3.6%（弱風2.8%比+0.8%）
                outer_bonus_enhanced = {
                    2: 0.05,   # +5%
                    3: 0.06,   # +6%（最も改善）
                    4: 0.05,   # +5%
                    5: 0.03,   # +3%
                    6: 0.02    # +2%
                }
                bonus = outer_bonus_enhanced.get(course, 0.0)
                if bonus > 0:
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

        # === 天候条件による補正（NEW） ===
        if weather_condition:
            if '雨' in weather_condition:
                # 雨天: 視界不良、スタート難化
                # → 経験豊富な選手有利、インコースやや有利
                if course == 1:
                    bonus = 0.02  # +2%
                    adjustment += bonus
                    reasons.append(f'雨天1コースボーナス({bonus:+.0%})')
                elif course in [5, 6]:
                    penalty = -0.03  # -3%
                    adjustment += penalty
                    reasons.append(f'雨天外コースペナルティ({penalty:+.0%})')

            elif '雪' in weather_condition:
                # 雪天: 視界不良、スタート難化（雨天より影響大）
                if course == 1:
                    bonus = 0.03  # +3%
                    adjustment += bonus
                    reasons.append(f'雪天1コースボーナス({bonus:+.0%})')
                elif course >= 4:
                    penalty = -0.05  # -5%
                    adjustment += penalty
                    reasons.append(f'雪天外コースペナルティ({penalty:+.0%})')

            elif '霧' in weather_condition:
                # 霧: 視界不良（雪天と同等）
                if course == 1:
                    bonus = 0.03  # +3%
                    adjustment += bonus
                    reasons.append(f'霧1コースボーナス({bonus:+.0%})')
                elif course >= 4:
                    penalty = -0.04  # -4%
                    adjustment += penalty
                    reasons.append(f'霧外コースペナルティ({penalty:+.0%})')

            elif '台風' in weather_condition:
                # 台風: 極端な天候、レース自体が中止される可能性
                # → 開催されている場合、インコース大幅有利
                if course == 1:
                    bonus = 0.05  # +5%
                    adjustment += bonus
                    reasons.append(f'台風1コースボーナス({bonus:+.0%})')
                else:
                    penalty = -0.10  # -10%
                    adjustment += penalty
                    reasons.append(f'台風外コースペナルティ({penalty:+.0%})')

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

    print("=== 天候補正テスト（2025-12-15更新版） ===")
    print()

    # テストケース: (会場, コース, 風速, 波高, 風向, 天候)
    test_cases = [
        ("08", 1, 7.0, 3, "南", None),     # 常滑、1コース、強風、中波、追い風
        ("08", 1, 7.0, 3, "北", None),     # 常滑、1コース、強風、中波、向い風
        ("08", 4, 7.0, 3, "北", None),     # 常滑、4コース、強風、中波、向い風
        ("02", 1, 5.0, 2, "南南西", None), # 戸田、1コース、中風、追い風
        ("02", 1, 5.0, 2, "北北東", None), # 戸田、1コース、中風、向い風
        ("24", 1, 2.0, 1, None, None),     # 大村、1コース、弱風（風向なし）
        ("10", 3, 6.0, 4, "北西", None),   # 三国、3コース、強風、向い風
    ]

    for venue, course, wind, wave, wind_dir, weather_cond in test_cases:
        result = adjuster.calculate_adjustment(venue, course, wind, wave, wind_dir, weather_cond)
        wind_dir_str = wind_dir if wind_dir else "なし"
        print(f"会場{venue} {course}コース 風速{wind}m 波高{wave}cm 風向:{wind_dir_str}")
        print(f"  補正: {result['adjustment']:+.1%}")
        print(f"  風向分類: {result['wind_direction_category']}")
        print(f"  理由: {result['reason']}")
        print()
