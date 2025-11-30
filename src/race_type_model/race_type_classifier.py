"""
レースタイプ分類
Phase 5: 水面特性に基づくレースタイプ分類（拡張版: 12モデル対応）
"""
from typing import Dict, List, Optional, Tuple
import numpy as np


class RaceTypeClassifier:
    """
    レースタイプ分類クラス（拡張版）

    レースタイプ（12種類）:
    === 水面特性ベース（8種類）===
    1. イン水面（大村/徳山/芦屋等）- 1着モデル最重要
    2. センター水面（平和島/多摩川）- 4カド攻め重視
    3. 差し水面（若松/宮島）- 2着モデルが重要
    4. 荒れ水面（戸田/江戸川）- モーター×ST×展示重視
    5. 静水面（下関/蒲郡）- 安定傾向
    6. 潮位影響大（住之江/尼崎）- 潮汐データ重視
    7. 強風影響（常滑/三国）- 風向重視
    8. 万能水面（その他）- 標準モデル

    === グレード・レース種別ベース（4種類）===
    9. SGレース - 最上位グレード、実力重視
    10. G1/G2レース - 上位グレード
    11. ナイターレース - 夜間特有の傾向
    12. 特殊レース（新人戦/女子戦）- 特殊な傾向
    """

    # 水面特性ベースのレースタイプ定義
    VENUE_RACE_TYPES = {
        'in_dominant': {
            'name': 'イン水面',
            'venues': ['18', '24', '21', '17', '19'],  # 徳山、大村、芦屋、宮島、下関
            'characteristics': '1着モデル最重要、イン勝率60%以上',
            'model_weight': {'first': 1.2, 'second': 0.9, 'third': 0.9},
        },
        'center_attack': {
            'name': 'センター水面',
            'venues': ['04', '05'],  # 平和島、多摩川
            'characteristics': '4カド攻め重視、まくり多発',
            'model_weight': {'first': 1.0, 'second': 1.1, 'third': 1.0},
        },
        'sashi_dominant': {
            'name': '差し水面',
            'venues': ['20', '17'],  # 若松、宮島
            'characteristics': '2着モデルが重要、差し決着多い',
            'model_weight': {'first': 0.9, 'second': 1.2, 'third': 1.1},
        },
        'rough_water': {
            'name': '荒れ水面',
            'venues': ['02', '03'],  # 戸田、江戸川
            'characteristics': 'モーター×ST×展示重視',
            'model_weight': {'first': 0.8, 'second': 1.0, 'third': 1.0},
            'feature_weight': {'motor': 1.3, 'exhibition': 1.2, 'st': 1.2},
        },
        'calm_water': {
            'name': '静水面',
            'venues': ['19', '07', '06'],  # 下関、蒲郡、浜名湖
            'characteristics': '安定傾向、実力通り',
            'model_weight': {'first': 1.0, 'second': 1.0, 'third': 1.0},
        },
        'tide_dependent': {
            'name': '潮位影響',
            'venues': ['12', '13', '14'],  # 住之江、尼崎、鳴門
            'characteristics': '潮汐データ重視',
            'model_weight': {'first': 1.0, 'second': 1.0, 'third': 1.0},
            'feature_weight': {'tide': 1.5},
        },
        'wind_dependent': {
            'name': '強風影響',
            'venues': ['08', '10', '11'],  # 常滑、三国、びわこ
            'characteristics': '風向重視',
            'model_weight': {'first': 0.9, 'second': 1.0, 'third': 1.0},
            'feature_weight': {'wind': 1.5},
        },
        'standard': {
            'name': '標準水面',
            'venues': ['01', '09', '15', '16', '22', '23'],  # 桐生、津、丸亀、児島、福岡、唐津
            'characteristics': '万能モデル',
            'model_weight': {'first': 1.0, 'second': 1.0, 'third': 1.0},
        },
    }

    # グレード・レース種別ベースのレースタイプ定義
    GRADE_RACE_TYPES = {
        'sg': {
            'name': 'SGレース',
            'grades': ['SG'],
            'characteristics': '最上位グレード、実力最重視、荒れにくい',
            'model_weight': {'first': 1.15, 'second': 1.0, 'third': 0.95},
            'feature_weight': {'win_rate': 1.3, 'rank': 1.2},
        },
        'g1_g2': {
            'name': 'G1/G2レース',
            'grades': ['G1', 'G2'],
            'characteristics': '上位グレード、実力重視',
            'model_weight': {'first': 1.1, 'second': 1.0, 'third': 1.0},
            'feature_weight': {'win_rate': 1.2, 'rank': 1.1},
        },
        'g3': {
            'name': 'G3レース',
            'grades': ['G3'],
            'characteristics': '中位グレード、やや荒れやすい',
            'model_weight': {'first': 1.0, 'second': 1.0, 'third': 1.0},
        },
        'general': {
            'name': '一般戦',
            'grades': ['一般', ''],
            'characteristics': '一般戦、荒れやすい',
            'model_weight': {'first': 0.95, 'second': 1.05, 'third': 1.05},
        },
        'nighter': {
            'name': 'ナイターレース',
            'characteristics': '夜間レース、照明下での傾向',
            'model_weight': {'first': 1.0, 'second': 1.0, 'third': 1.0},
            'feature_weight': {'exhibition': 1.1},  # 展示がより重要
        },
        'rookie': {
            'name': '新人戦',
            'characteristics': '新人選手限定、経験不足で荒れやすい',
            'model_weight': {'first': 0.8, 'second': 1.1, 'third': 1.1},
            'feature_weight': {'st': 1.3, 'motor': 1.2},  # ST・モーターが重要
        },
        'ladies': {
            'name': '女子戦',
            'characteristics': '女子選手限定、独自の傾向',
            'model_weight': {'first': 0.95, 'second': 1.1, 'third': 1.05},
            'feature_weight': {'win_rate': 1.1},
        },
    }

    # 全レースタイプを統合
    RACE_TYPES = {**VENUE_RACE_TYPES, **GRADE_RACE_TYPES}

    # ナイター開催場
    NIGHTER_VENUES = ['01', '02', '06', '07', '12', '17', '20', '21', '24']  # 桐生、戸田、浜名湖、蒲郡、住之江、宮島、若松、芦屋、大村

    # 会場コード→レースタイプのマッピング
    VENUE_TO_TYPE = {}
    for race_type, config in VENUE_RACE_TYPES.items():
        for venue in config.get('venues', []):
            VENUE_TO_TYPE[venue] = race_type

    def __init__(self):
        pass

    def classify(self, venue_code: str,
                 wind_speed: float = None,
                 wave_height: float = None,
                 tide_level: float = None,
                 season: int = None,
                 grade: str = None,
                 is_nighter: bool = False,
                 is_rookie: bool = False,
                 is_ladies: bool = False) -> str:
        """
        レースタイプを分類

        Args:
            venue_code: 会場コード
            wind_speed: 風速（m/s）
            wave_height: 波高（cm）
            tide_level: 潮位（cm）
            season: 季節（1-4）- 不使用（影響が小さいため）
            grade: グレード（SG/G1/G2/G3/一般）
            is_nighter: ナイターレースか
            is_ladies: 女子戦か
            is_rookie: 新人戦か

        Returns:
            レースタイプ名
        """
        # 特殊レース優先判定
        if is_rookie:
            return 'rookie'
        if is_ladies:
            return 'ladies'

        # グレード判定（上位グレード優先）
        if grade:
            grade_upper = grade.upper()
            if grade_upper == 'SG':
                return 'sg'
            elif grade_upper in ['G1', 'G2', 'GI', 'GII']:
                return 'g1_g2'
            elif grade_upper in ['G3', 'GIII']:
                return 'g3'

        # ナイター判定
        if is_nighter:
            return 'nighter'

        # 水面特性ベースの判定
        base_type = self.VENUE_TO_TYPE.get(venue_code, 'standard')

        # 条件で調整
        if wind_speed is not None and wind_speed >= 5:
            # 強風時は風影響タイプに
            base_type = 'wind_dependent'

        if wave_height is not None and wave_height >= 10:
            # 波高時は荒れ水面に
            base_type = 'rough_water'

        return base_type

    def classify_multi(self, venue_code: str,
                       wind_speed: float = None,
                       wave_height: float = None,
                       grade: str = None,
                       is_nighter: bool = False,
                       is_rookie: bool = False,
                       is_ladies: bool = False) -> List[str]:
        """
        複合レースタイプを分類（複数タイプを返す）

        SGレース＋イン水面のように複数の特性を持つ場合に有効

        Returns:
            レースタイプ名のリスト
        """
        types = []

        # 水面特性
        venue_type = self.VENUE_TO_TYPE.get(venue_code, 'standard')
        if wind_speed is not None and wind_speed >= 5:
            venue_type = 'wind_dependent'
        if wave_height is not None and wave_height >= 10:
            venue_type = 'rough_water'
        types.append(venue_type)

        # グレード
        if grade:
            grade_upper = grade.upper()
            if grade_upper == 'SG':
                types.append('sg')
            elif grade_upper in ['G1', 'G2', 'GI', 'GII']:
                types.append('g1_g2')
            elif grade_upper in ['G3', 'GIII']:
                types.append('g3')

        # ナイター
        if is_nighter:
            types.append('nighter')

        # 特殊レース
        if is_rookie:
            types.append('rookie')
        if is_ladies:
            types.append('ladies')

        return types

    def get_combined_weights(self, race_types: List[str]) -> Dict[str, float]:
        """
        複数タイプの重みを統合

        Args:
            race_types: レースタイプのリスト

        Returns:
            統合されたモデル重み
        """
        combined = {'first': 1.0, 'second': 1.0, 'third': 1.0}

        for race_type in race_types:
            config = self.get_type_config(race_type)
            weights = config.get('model_weight', {})
            for key in combined:
                if key in weights:
                    combined[key] *= weights[key]

        # 正規化（平均が1になるように）
        total = sum(combined.values())
        if total > 0:
            avg = total / len(combined)
            combined = {k: v / avg for k, v in combined.items()}

        return combined

    def get_combined_feature_weights(self, race_types: List[str]) -> Dict[str, float]:
        """
        複数タイプの特徴量重みを統合

        Args:
            race_types: レースタイプのリスト

        Returns:
            統合された特徴量重み
        """
        combined = {}

        for race_type in race_types:
            config = self.get_type_config(race_type)
            feature_weights = config.get('feature_weight', {})
            for key, value in feature_weights.items():
                if key in combined:
                    combined[key] = max(combined[key], value)  # 最大値を採用
                else:
                    combined[key] = value

        return combined

    def get_type_config(self, race_type: str) -> Dict:
        """レースタイプの設定を取得"""
        return self.RACE_TYPES.get(race_type, self.RACE_TYPES['standard'])

    def get_model_weights(self, race_type: str) -> Dict[str, float]:
        """レースタイプのモデル重みを取得"""
        config = self.get_type_config(race_type)
        return config.get('model_weight', {'first': 1.0, 'second': 1.0, 'third': 1.0})

    def get_feature_weights(self, race_type: str) -> Dict[str, float]:
        """レースタイプの特徴量重みを取得"""
        config = self.get_type_config(race_type)
        return config.get('feature_weight', {})

    def get_all_types(self) -> List[str]:
        """全レースタイプを取得"""
        return list(self.RACE_TYPES.keys())

    def get_venue_types(self) -> List[str]:
        """水面特性ベースのレースタイプを取得"""
        return list(self.VENUE_RACE_TYPES.keys())

    def get_grade_types(self) -> List[str]:
        """グレード・レース種別ベースのレースタイプを取得"""
        return list(self.GRADE_RACE_TYPES.keys())

    def get_venues_for_type(self, race_type: str) -> List[str]:
        """レースタイプの対象会場を取得"""
        config = self.get_type_config(race_type)
        return config.get('venues', [])

    def is_nighter_venue(self, venue_code: str) -> bool:
        """ナイター開催場かどうか"""
        return venue_code in self.NIGHTER_VENUES

    def classify_with_confidence(self, venue_code: str,
                                 wind_speed: float = None,
                                 wave_height: float = None,
                                 grade: str = None,
                                 is_nighter: bool = False,
                                 is_rookie: bool = False,
                                 is_ladies: bool = False) -> Tuple[str, float]:
        """
        レースタイプを分類（信頼度付き）

        Returns:
            (レースタイプ, 信頼度)
        """
        # 特殊レースは高信頼度
        if is_rookie:
            return 'rookie', 0.95
        if is_ladies:
            return 'ladies', 0.95

        # 上位グレードは高信頼度
        if grade:
            grade_upper = grade.upper()
            if grade_upper == 'SG':
                return 'sg', 0.95
            elif grade_upper in ['G1', 'G2', 'GI', 'GII']:
                return 'g1_g2', 0.9

        # ナイターは中程度の信頼度
        if is_nighter:
            return 'nighter', 0.8

        # 水面特性ベース
        base_type = self.VENUE_TO_TYPE.get(venue_code, 'standard')
        confidence = 0.8  # 基本信頼度

        # 条件による調整
        if wind_speed is not None:
            if wind_speed >= 5:
                if base_type == 'wind_dependent':
                    confidence = 0.95
                else:
                    confidence = 0.6  # タイプが変わる場合は信頼度低下

        if wave_height is not None:
            if wave_height >= 10:
                if base_type == 'rough_water':
                    confidence = 0.95
                else:
                    confidence = 0.6

        final_type = self.classify(venue_code, wind_speed, wave_height,
                                   grade=grade, is_nighter=is_nighter,
                                   is_rookie=is_rookie, is_ladies=is_ladies)

        return final_type, confidence


def get_race_type_for_race(venue_code: str,
                           race_date: str = None,
                           weather_data: Dict = None,
                           grade: str = None,
                           is_nighter: bool = None,
                           is_rookie: bool = False,
                           is_ladies: bool = False) -> str:
    """
    レースのタイプを判定（ユーティリティ関数）

    Args:
        venue_code: 会場コード
        race_date: レース日
        weather_data: 気象データ
        grade: グレード（SG/G1/G2/G3/一般）
        is_nighter: ナイターレースか（Noneの場合は会場から推定）
        is_rookie: 新人戦か
        is_ladies: 女子戦か

    Returns:
        レースタイプ
    """
    classifier = RaceTypeClassifier()

    wind_speed = None
    wave_height = None
    tide_level = None

    if weather_data:
        wind_speed = weather_data.get('wind_speed')
        wave_height = weather_data.get('wave_height')
        tide_level = weather_data.get('tide_level')

    # ナイター判定（指定がない場合は会場から推定）
    if is_nighter is None:
        is_nighter = classifier.is_nighter_venue(venue_code)

    return classifier.classify(
        venue_code,
        wind_speed,
        wave_height,
        tide_level,
        grade=grade,
        is_nighter=is_nighter,
        is_rookie=is_rookie,
        is_ladies=is_ladies
    )


def get_race_types_multi(venue_code: str,
                         weather_data: Dict = None,
                         grade: str = None,
                         is_nighter: bool = None,
                         is_rookie: bool = False,
                         is_ladies: bool = False) -> List[str]:
    """
    レースの複合タイプを判定（複数タイプを返す）

    Args:
        venue_code: 会場コード
        weather_data: 気象データ
        grade: グレード
        is_nighter: ナイターレースか
        is_rookie: 新人戦か
        is_ladies: 女子戦か

    Returns:
        レースタイプのリスト
    """
    classifier = RaceTypeClassifier()

    wind_speed = None
    wave_height = None

    if weather_data:
        wind_speed = weather_data.get('wind_speed')
        wave_height = weather_data.get('wave_height')

    if is_nighter is None:
        is_nighter = classifier.is_nighter_venue(venue_code)

    return classifier.classify_multi(
        venue_code,
        wind_speed,
        wave_height,
        grade=grade,
        is_nighter=is_nighter,
        is_rookie=is_rookie,
        is_ladies=is_ladies
    )
