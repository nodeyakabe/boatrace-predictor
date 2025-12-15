"""
プリセットローダーモジュール

YAMLファイルからプリセット（会場特性、天候ルール、潮位補正等）を読み込み、
検証、キャッシュを行う。

使用例:
    from src.utils.preset_loader import get_preset_loader

    loader = get_preset_loader()

    # 会場特性を取得
    venue = loader.get_venue("24")
    print(venue['name'])  # "大村"

    # 補正値を取得
    bonus = loader.get_venue_adjustment("24", "course_1_base_bonus")
    print(bonus)  # 10.0

    # 天候ルールを取得
    weather = loader.get_weather_adjustment("08", "strong", wind_direction="北北西")

    # 潮位補正を取得
    tide = loader.get_tide_adjustment("17", "rising", 1)
"""

import yaml
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class PresetMeta:
    """プリセットメタデータ"""
    version: str
    updated_at: str
    updated_by: str
    data_source: str
    file_hash: str


class PresetLoader:
    """プリセットローダー"""

    # デフォルトのプリセットディレクトリ
    DEFAULT_PRESET_DIR = Path(__file__).parent.parent.parent / "config" / "presets"

    def __init__(self, preset_dir: Optional[Path] = None):
        """
        初期化

        Args:
            preset_dir: プリセットディレクトリのパス（省略時はデフォルト）
        """
        self.preset_dir = preset_dir or self.DEFAULT_PRESET_DIR
        self._cache: Dict[str, Any] = {}
        self._meta_cache: Dict[str, PresetMeta] = {}

    def load(self, preset_name: str, force_reload: bool = False) -> Dict[str, Any]:
        """
        プリセットを読み込む

        Args:
            preset_name: プリセット名（拡張子なし）
            force_reload: キャッシュを無視して再読み込み

        Returns:
            プリセットデータ（辞書）

        Raises:
            FileNotFoundError: プリセットファイルが見つからない場合
        """
        if not force_reload and preset_name in self._cache:
            return self._cache[preset_name]

        file_path = self.preset_dir / f"{preset_name}.yaml"

        if not file_path.exists():
            raise FileNotFoundError(f"Preset not found: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # メタデータ抽出
        self._extract_meta(preset_name, data, file_path)

        # キャッシュに保存
        self._cache[preset_name] = data

        return data

    def _extract_meta(self, name: str, data: Dict, file_path: Path):
        """メタデータを抽出してキャッシュ"""
        meta = data.get("meta", {})

        # ファイルハッシュ計算
        with open(file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        self._meta_cache[name] = PresetMeta(
            version=meta.get("version", "unknown"),
            updated_at=meta.get("updated_at", "unknown"),
            updated_by=meta.get("updated_by", "unknown"),
            data_source=meta.get("data_source", "unknown"),
            file_hash=file_hash
        )

    def get_meta(self, preset_name: str) -> Optional[PresetMeta]:
        """プリセットのメタデータを取得"""
        if preset_name not in self._meta_cache:
            try:
                self.load(preset_name)
            except FileNotFoundError:
                return None
        return self._meta_cache.get(preset_name)

    # ========== 会場特性関連 ==========

    def get_venue(self, venue_code: str) -> Optional[Dict]:
        """
        会場情報を取得

        Args:
            venue_code: 会場コード（'01'～'24'）

        Returns:
            会場情報の辞書（見つからない場合はNone）
        """
        data = self.load("venue_characteristics")
        venues = data.get("venues", {})
        return venues.get(venue_code)

    def get_venue_adjustment(
        self,
        venue_code: str,
        adjustment_key: str,
        default: float = 0.0
    ) -> float:
        """
        会場別補正値を取得

        Args:
            venue_code: 会場コード
            adjustment_key: 補正キー（例: 'course_1_base_bonus', 'strong_wind_penalty'）
            default: デフォルト値

        Returns:
            補正値
        """
        venue = self.get_venue(venue_code)
        if not venue:
            return default

        adjustments = venue.get("adjustments", {})
        return adjustments.get(adjustment_key, default)

    def get_venue_wind_direction_adjustment(
        self,
        venue_code: str,
        wind_direction: str
    ) -> Optional[float]:
        """
        会場×風向の補正値を取得

        Args:
            venue_code: 会場コード
            wind_direction: 風向（'北', '南東'など）

        Returns:
            補正値（該当なしはNone）
        """
        venue = self.get_venue(venue_code)
        if not venue:
            return None

        wind_adj = venue.get("wind_direction_adjustments", {})
        return wind_adj.get(wind_direction)

    def get_all_venues(self) -> Dict[str, Dict]:
        """全会場情報を取得"""
        data = self.load("venue_characteristics")
        return data.get("venues", {})

    # ========== 天候ルール関連 ==========

    def get_wind_category(self, wind_speed: float) -> str:
        """
        風速をカテゴリ化

        Args:
            wind_speed: 風速(m/s)

        Returns:
            カテゴリ名（'calm', 'moderate', 'strong', 'storm'）
        """
        data = self.load("weather_rules")
        categories = data.get("wind_speed_categories", {})

        for cat_name, cat_info in categories.items():
            if cat_info["min"] <= wind_speed <= cat_info["max"]:
                return cat_name

        return "moderate"  # フォールバック

    def get_wave_category(self, wave_height: float) -> str:
        """
        波高をカテゴリ化

        Args:
            wave_height: 波高(cm)

        Returns:
            カテゴリ名（'calm', 'moderate', 'rough'）
        """
        data = self.load("weather_rules")
        categories = data.get("wave_height_categories", {})

        for cat_name, cat_info in categories.items():
            if cat_info["min"] <= wave_height <= cat_info["max"]:
                return cat_name

        return "calm"  # フォールバック

    def get_weather_adjustment(
        self,
        venue_code: str,
        wind_category: str,
        wave_category: Optional[str] = None,
        wind_direction: Optional[str] = None
    ) -> Dict[str, float]:
        """
        天候ルールに基づく補正値を取得

        Args:
            venue_code: 会場コード
            wind_category: 風速カテゴリ
            wave_category: 波高カテゴリ（任意）
            wind_direction: 風向（任意）

        Returns:
            コース別補正値の辞書（例: {'course_1_penalty': -5.0, 'course_2_bonus': 2.5}）
        """
        data = self.load("weather_rules")
        adjustments = {}

        # グローバルルール適用
        global_rules = data.get("global_rules", {})

        # 強風ルール
        if wind_category in ["strong", "storm"]:
            strong_rules = global_rules.get("strong_wind", {})
            for key, value in strong_rules.items():
                adjustments[key] = value

        # 高波ルール
        if wave_category == "rough":
            wave_rules = global_rules.get("high_wave", {})
            for key, value in wave_rules.items():
                adjustments[key] = adjustments.get(key, 0) + value

        # 会場別オーバーライド
        venue_overrides = data.get("venue_overrides", {}).get(venue_code, {})
        if wind_category in ["strong", "storm"] and "strong_wind" in venue_overrides:
            for key, value in venue_overrides["strong_wind"].items():
                adjustments[key] = value  # オーバーライド

        # 暴風時の風向別補正
        if wind_category == "storm" and wind_direction:
            storm_adj = data.get("storm_wind_adjustments", {})
            lookup_key = f"{venue_code}_{wind_direction}"

            for impact_level in ["high_impact", "medium_impact"]:
                impact_data = storm_adj.get(impact_level, {})
                if lookup_key in impact_data:
                    adj_data = impact_data[lookup_key]
                    adjustments["storm_course_1_adjustment"] = adj_data.get("score_adjustment", 0)
                    break

        return adjustments

    def get_storm_wind_adjustment(
        self,
        venue_code: str,
        wind_direction: str
    ) -> Optional[Dict]:
        """
        暴風時（8m+）の会場×風向別補正を取得

        Args:
            venue_code: 会場コード
            wind_direction: 風向

        Returns:
            補正情報（見つからない場合はNone）
        """
        data = self.load("weather_rules")
        storm_adj = data.get("storm_wind_adjustments", {})
        lookup_key = f"{venue_code}_{wind_direction}"

        for impact_level in ["high_impact", "medium_impact"]:
            impact_data = storm_adj.get(impact_level, {})
            if lookup_key in impact_data:
                return impact_data[lookup_key]

        return None

    # ========== 潮位補正関連 ==========

    def get_tide_adjustment(
        self,
        venue_code: str,
        tide_phase: str,
        course: int
    ) -> float:
        """
        潮位に基づく補正値を取得

        Args:
            venue_code: 会場コード
            tide_phase: 潮位フェーズ（'rising', 'falling', 'high', 'low'）
            course: コース番号（1-6）

        Returns:
            補正値（点）
        """
        data = self.load("tide_adjustments")

        # 対象会場かチェック
        applicable = data.get("applicable_venues", {})
        seawater = applicable.get("seawater", [])
        brackish = applicable.get("brackish", [])

        if venue_code not in seawater + brackish:
            return 0.0  # 淡水会場は補正なし

        # 会場別係数を取得
        venue_coef = data.get("venue_coefficients", {}).get(venue_code, {})

        # 会場別データがなければデフォルトを使用
        if not venue_coef:
            venue_coef = data.get("default_rules", {})

        # 該当フェーズの補正を取得
        phase_adj = venue_coef.get(tide_phase, {})

        # コースに応じた補正キーを探す
        course_keys = [
            f"course_{course}_bonus",
            f"course_{course}_penalty",
        ]

        for key in course_keys:
            if key in phase_adj:
                return phase_adj[key]

        return 0.0

    def is_tide_applicable(self, venue_code: str) -> bool:
        """
        潮位補正が適用される会場かを判定

        Args:
            venue_code: 会場コード

        Returns:
            True: 海水/汽水会場、False: 淡水会場
        """
        data = self.load("tide_adjustments")
        applicable = data.get("applicable_venues", {})
        seawater = applicable.get("seawater", [])
        brackish = applicable.get("brackish", [])

        return venue_code in seawater + brackish

    def get_tide_venue_coefficient(self, venue_code: str) -> Optional[Dict]:
        """
        会場の潮位補正係数を取得

        Args:
            venue_code: 会場コード

        Returns:
            補正係数の辞書（見つからない場合はNone）
        """
        data = self.load("tide_adjustments")
        return data.get("venue_coefficients", {}).get(venue_code)

    # ========== ユーティリティ ==========

    def reload_all(self):
        """全プリセットを再読み込み"""
        self._cache.clear()
        self._meta_cache.clear()

        for yaml_file in self.preset_dir.glob("*.yaml"):
            preset_name = yaml_file.stem
            try:
                self.load(preset_name, force_reload=True)
            except Exception as e:
                print(f"Warning: Failed to load {preset_name}: {e}")

    def list_presets(self) -> List[str]:
        """利用可能なプリセット一覧を取得"""
        presets = []
        for yaml_file in self.preset_dir.glob("*.yaml"):
            presets.append(yaml_file.stem)
        return sorted(presets)

    def validate_all(self) -> Dict[str, bool]:
        """
        全プリセットの読み込み検証

        Returns:
            プリセット名 -> 成功/失敗 の辞書
        """
        results = {}
        for preset_name in self.list_presets():
            try:
                self.load(preset_name)
                results[preset_name] = True
            except Exception:
                results[preset_name] = False
        return results


# シングルトンインスタンス
_preset_loader: Optional[PresetLoader] = None


def get_preset_loader() -> PresetLoader:
    """
    プリセットローダーのシングルトンを取得

    Returns:
        PresetLoaderインスタンス
    """
    global _preset_loader
    if _preset_loader is None:
        _preset_loader = PresetLoader()
    return _preset_loader


# テスト用
if __name__ == "__main__":
    print("=" * 80)
    print("プリセットローダー テスト")
    print("=" * 80)

    loader = get_preset_loader()

    # プリセット一覧
    print("\n【利用可能なプリセット】")
    for preset in loader.list_presets():
        meta = loader.get_meta(preset)
        if meta:
            print(f"  - {preset} (v{meta.version}, {meta.updated_at})")
        else:
            print(f"  - {preset}")

    # 検証
    print("\n【プリセット検証】")
    results = loader.validate_all()
    for name, success in results.items():
        status = "OK" if success else "NG"
        print(f"  {name}: {status}")

    # 会場特性テスト
    print("\n【会場特性テスト】")
    for venue_code in ["01", "08", "24"]:
        venue = loader.get_venue(venue_code)
        if venue:
            bonus = loader.get_venue_adjustment(venue_code, "course_1_base_bonus")
            print(f"  {venue_code} {venue['name']}: "
                  f"1コース勝率{venue['base_course1_rate']:.1%}, "
                  f"基本ボーナス{bonus:+.1f}点")

    # 天候ルールテスト
    print("\n【天候ルールテスト】")
    test_weather = [
        ("08", 8.0, "北北西"),  # 常滑・暴風
        ("02", 8.5, "北"),       # 戸田・暴風
        ("24", 6.0, None),       # 大村・強風
    ]
    for venue, wind_speed, wind_dir in test_weather:
        wind_cat = loader.get_wind_category(wind_speed)
        adj = loader.get_weather_adjustment(venue, wind_cat, wind_direction=wind_dir)
        venue_name = loader.get_venue(venue)['name']
        print(f"  {venue} {venue_name} 風速{wind_speed}m {wind_dir or '-'}: {adj}")

    # 潮位補正テスト
    print("\n【潮位補正テスト】")
    test_tide = [
        ("17", "rising", 1),   # 徳山・上げ潮・1コース
        ("17", "falling", 4),  # 徳山・下げ潮・4コース
        ("01", "rising", 1),   # 桐生（淡水）
    ]
    for venue, phase, course in test_tide:
        adj = loader.get_tide_adjustment(venue, phase, course)
        venue_info = loader.get_venue(venue)
        venue_name = venue_info['name'] if venue_info else venue
        applicable = "○" if loader.is_tide_applicable(venue) else "×"
        print(f"  {venue} {venue_name} {phase} {course}コース: "
              f"{adj:+.1f}点 (潮位適用: {applicable})")

    print("\n" + "=" * 80)
    print("テスト完了")
    print("=" * 80)
