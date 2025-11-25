"""
データ検証モジュール
データベースへの挿入前にスキーマと妥当性を検証
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import pandas as pd


@dataclass
class ValidationRule:
    """検証ルールの定義"""
    field_name: str
    field_type: type
    required: bool = True
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None
    pattern: Optional[str] = None


class DataValidator:
    """データ検証クラス"""

    # レース基本情報の検証ルール
    RACE_SCHEMA = [
        ValidationRule('venue_code', str, required=True, pattern=r'^\d{2}$'),
        ValidationRule('race_date', str, required=True, pattern=r'^\d{4}-\d{2}-\d{2}$'),
        ValidationRule('race_number', int, required=True, min_value=1, max_value=12),
        ValidationRule('race_time', str, required=False),
    ]

    # 出走表の検証ルール
    ENTRY_SCHEMA = [
        ValidationRule('pit_number', int, required=True, min_value=1, max_value=6),
        ValidationRule('racer_number', str, required=True, pattern=r'^\d{4}$'),
        ValidationRule('racer_name', str, required=True),
        ValidationRule('racer_rank', str, required=False, allowed_values=['A1', 'A2', 'B1', 'B2']),
        ValidationRule('racer_age', int, required=False, min_value=18, max_value=70),
        ValidationRule('racer_weight', float, required=False, min_value=40, max_value=75),
        ValidationRule('motor_number', int, required=False, min_value=1, max_value=100),
        ValidationRule('boat_number', int, required=False, min_value=1, max_value=100),
        ValidationRule('win_rate', float, required=False, min_value=0, max_value=10),
        ValidationRule('second_rate', float, required=False, min_value=0, max_value=1),
    ]

    # 結果の検証ルール
    RESULT_SCHEMA = [
        ValidationRule('pit_number', int, required=True, min_value=1, max_value=6),
        ValidationRule('rank', str, required=True, allowed_values=['1', '2', '3', '4', '5', '6', 'F', 'L', 'K', 'S']),
        ValidationRule('winning_technique', int, required=False, allowed_values=[1, 2, 3, 4, 5, 6]),
        ValidationRule('trifecta_odds', float, required=False, min_value=1.0),
    ]

    # レース詳細の検証ルール
    RACE_DETAIL_SCHEMA = [
        ValidationRule('pit_number', int, required=True, min_value=1, max_value=6),
        ValidationRule('exhibition_time', float, required=False, min_value=6.0, max_value=8.0),
        ValidationRule('tilt_angle', float, required=False, min_value=-3.0, max_value=3.0),
        ValidationRule('actual_course', int, required=False, min_value=1, max_value=6),
        ValidationRule('st_time', float, required=False, min_value=-0.5, max_value=1.0),
    ]

    # 気象情報の検証ルール
    WEATHER_SCHEMA = [
        ValidationRule('venue_code', str, required=True, pattern=r'^\d{2}$'),
        ValidationRule('weather_date', str, required=True, pattern=r'^\d{4}-\d{2}-\d{2}$'),
        ValidationRule('temperature', float, required=False, min_value=-20, max_value=50),
        ValidationRule('weather_condition', str, required=False, allowed_values=['晴', '曇', '雨', '雪']),
        ValidationRule('wind_speed', float, required=False, min_value=0, max_value=30),
        ValidationRule('wave_height', float, required=False, min_value=0, max_value=50),
        ValidationRule('water_temperature', float, required=False, min_value=0, max_value=40),
        ValidationRule('humidity', int, required=False, min_value=0, max_value=100),
    ]

    @staticmethod
    def validate_field(value: Any, rule: ValidationRule) -> tuple[bool, Optional[str]]:
        """
        単一フィールドの検証

        Returns:
            (is_valid, error_message)
        """
        # 必須チェック
        if rule.required and (value is None or value == ''):
            return False, f"{rule.field_name} は必須項目です"

        # 値がNoneの場合、以降のチェックをスキップ
        if value is None or value == '':
            return True, None

        # 型チェック
        if not isinstance(value, rule.field_type):
            try:
                # 型変換を試みる
                if rule.field_type == int:
                    value = int(value)
                elif rule.field_type == float:
                    value = float(value)
                elif rule.field_type == str:
                    value = str(value)
            except (ValueError, TypeError):
                return False, f"{rule.field_name} の型が不正です（期待: {rule.field_type.__name__}）"

        # 数値範囲チェック
        if rule.min_value is not None and value < rule.min_value:
            return False, f"{rule.field_name} が最小値 {rule.min_value} 未満です: {value}"

        if rule.max_value is not None and value > rule.max_value:
            return False, f"{rule.field_name} が最大値 {rule.max_value} を超えています: {value}"

        # 許可値チェック
        if rule.allowed_values is not None and value not in rule.allowed_values:
            return False, f"{rule.field_name} が許可値に含まれていません: {value} (許可値: {rule.allowed_values})"

        # パターンチェック（正規表現）
        if rule.pattern is not None:
            import re
            if not re.match(rule.pattern, str(value)):
                return False, f"{rule.field_name} がパターンに一致しません: {value} (パターン: {rule.pattern})"

        return True, None

    @classmethod
    def validate_data(cls, data: Dict[str, Any], schema: List[ValidationRule]) -> tuple[bool, List[str]]:
        """
        データ全体の検証

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        for rule in schema:
            value = data.get(rule.field_name)
            is_valid, error_msg = cls.validate_field(value, rule)

            if not is_valid:
                errors.append(error_msg)

        return len(errors) == 0, errors

    @classmethod
    def validate_race(cls, race_data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """レース基本情報の検証"""
        return cls.validate_data(race_data, cls.RACE_SCHEMA)

    @classmethod
    def validate_entry(cls, entry_data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """出走表の検証"""
        return cls.validate_data(entry_data, cls.ENTRY_SCHEMA)

    @classmethod
    def validate_result(cls, result_data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """結果の検証"""
        return cls.validate_data(result_data, cls.RESULT_SCHEMA)

    @classmethod
    def validate_race_detail(cls, detail_data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """レース詳細の検証"""
        return cls.validate_data(detail_data, cls.RACE_DETAIL_SCHEMA)

    @classmethod
    def validate_weather(cls, weather_data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """気象情報の検証"""
        return cls.validate_data(weather_data, cls.WEATHER_SCHEMA)

    @classmethod
    def validate_race_entries_count(cls, entries: List[Dict[str, Any]]) -> tuple[bool, str]:
        """
        レースのエントリー数が6であることを検証

        Returns:
            (is_valid, error_message)
        """
        if len(entries) != 6:
            return False, f"エントリー数が6でありません: {len(entries)}"

        # ピット番号が1-6であることを確認
        pit_numbers = [e.get('pit_number') for e in entries]
        expected_pits = set(range(1, 7))
        actual_pits = set(pit_numbers)

        if expected_pits != actual_pits:
            return False, f"ピット番号が1-6でありません: {actual_pits}"

        return True, ""

    @classmethod
    def validate_dataframe(cls, df: pd.DataFrame, schema: List[ValidationRule]) -> tuple[bool, List[str]]:
        """
        DataFrameの検証

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        for rule in schema:
            if rule.field_name not in df.columns:
                if rule.required:
                    errors.append(f"必須カラム '{rule.field_name}' が存在しません")
                continue

            # 各行を検証
            for idx, value in enumerate(df[rule.field_name]):
                is_valid, error_msg = cls.validate_field(value, rule)
                if not is_valid:
                    errors.append(f"行{idx}: {error_msg}")

                # エラーが多すぎる場合は打ち切り
                if len(errors) > 100:
                    errors.append("エラーが100件を超えたため、検証を中断しました")
                    return False, errors

        return len(errors) == 0, errors


class FeatureValidator:
    """特徴量の検証"""

    REQUIRED_FEATURES = [
        'pit_number',
        'win_rate',
        'motor_number',
    ]

    FEATURE_RANGES = {
        'pit_number': (1, 6),
        'win_rate': (0, 10),
        'racer_age': (18, 70),
        'racer_weight': (40, 75),
        'wind_speed': (0, 30),
        'wave_height': (0, 50),
        'temperature': (-20, 50),
        'water_temperature': (0, 40),
        'humidity': (0, 100),
        'motor_2ren_rate': (0, 1),
        'boat_2ren_rate': (0, 1),
    }

    @classmethod
    def validate_features(cls, features: pd.DataFrame) -> tuple[bool, List[str]]:
        """
        特徴量DataFrameの検証

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        # 必須カラムの存在確認
        for col in cls.REQUIRED_FEATURES:
            if col not in features.columns:
                errors.append(f"必須特徴量 '{col}' が存在しません")

        # 値の範囲チェック
        for col, (min_val, max_val) in cls.FEATURE_RANGES.items():
            if col not in features.columns:
                continue

            out_of_range = (
                (features[col] < min_val) | (features[col] > max_val)
            ).sum()

            if out_of_range > 0:
                errors.append(
                    f"特徴量 '{col}' の値が範囲外: {out_of_range}件 "
                    f"(範囲: {min_val}-{max_val})"
                )

        # NaN/Infチェック
        nan_cols = features.columns[features.isna().any()].tolist()
        if nan_cols:
            errors.append(f"NaN値を含むカラム: {nan_cols}")

        inf_cols = features.columns[features.isin([float('inf'), float('-inf')]).any()].tolist()
        if inf_cols:
            errors.append(f"Inf値を含むカラム: {inf_cols}")

        return len(errors) == 0, errors


if __name__ == "__main__":
    # テスト用
    test_race = {
        'venue_code': '07',
        'race_date': '2025-01-01',
        'race_number': 1,
        'race_time': '10:00'
    }

    is_valid, errors = DataValidator.validate_race(test_race)
    print(f"検証結果: {'合格' if is_valid else '不合格'}")
    if errors:
        for error in errors:
            print(f"  - {error}")
