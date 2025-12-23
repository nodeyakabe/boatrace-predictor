# プリセット管理設計書

**作成日**: 2025-12-15
**バージョン**: 1.0
**関連ドキュメント**: PREDICTION_REFACTORING_PLAN.md

---

## 1. 概要

### 1.1 目的

予測システムで使用する各種プリセット（会場特性、天候ルール、補正値等）を体系的に管理し、以下を実現する：

1. **一元管理**: 分散した設定を統合
2. **検証可能性**: 各プリセットの効果を個別に検証
3. **最適化対応**: 自動チューニングが可能な構造
4. **バージョン管理**: 変更履歴の追跡

### 1.2 プリセットカテゴリ

| カテゴリ | 説明 | 現在のファイル |
|---------|------|---------------|
| 会場特性 | 24会場の基本特性、コース勝率 | venue_characteristics.py |
| 天候ルール | 風速/波高/風向による補正 | weather_rules.json |
| 潮位補正 | 満潮/干潮による影響 | tide_adjuster.py (内部定義) |
| 複合条件 | 複数条件組み合わせルール | compound_buff_system.py |
| 統合重み | PRE/BEFORE統合比率 | dynamic_integration.py |

---

## 2. ディレクトリ構造

```
config/
├── presets/
│   ├── venue_characteristics.yaml    # 会場特性
│   ├── weather_rules.yaml            # 天候ルール
│   ├── tide_adjustments.yaml         # 潮位補正
│   ├── compound_rules.yaml           # 複合条件ルール
│   ├── integration_weights.yaml      # 統合重み
│   └── optimization_history/         # 最適化履歴
│       ├── 2025-12-15_v1.yaml
│       └── 2025-12-20_v2.yaml
├── preset_schema.yaml                # スキーマ定義
└── optimization_targets.yaml         # 最適化対象定義
```

---

## 3. YAMLスキーマ定義

### 3.1 共通ヘッダー

```yaml
# 全プリセットファイルの共通ヘッダー
meta:
  version: "1.0"                      # スキーマバージョン
  updated_at: "2025-12-15"            # 最終更新日
  updated_by: "optimizer"             # 更新者（manual/optimizer）
  data_source: "2020-2025年実績"      # データソース
  validation_date: "2025-12-10"       # 検証日
  validation_result:                  # 検証結果
    hit_rate: 0.563
    recovery_rate: 0.751
    sample_size: 10000
```

### 3.2 会場特性スキーマ (`venue_characteristics.yaml`)

```yaml
meta:
  version: "1.0"
  updated_at: "2025-12-15"
  updated_by: "manual"
  data_source: "ボートレース公式 2020-2025年データ"

venues:
  "01":  # 桐生
    name: "桐生"
    region: "関東"
    water_type: "freshwater"       # freshwater | brackish | seawater

    # 基本特性（複数指定可）
    characteristics:
      - "標準的"
      - "ナイター開催"

    # コース別1着率（合計100%に近似）
    course_win_rates:
      1: 0.519
      2: 0.150
      3: 0.125
      4: 0.120
      5: 0.066
      6: 0.020

    # 全国平均との比較（1.0が基準）
    course_deviation:
      1: 0.94   # 全国平均55%に対し51.9% → 0.94
      2: 1.07
      3: 1.04
      4: 1.20
      5: 1.10
      6: 0.67

    # スコア補正値（直接加算される点数）
    adjustments:
      # 1コース補正
      course_1_base_bonus: 0.0       # 基本補正（-10〜+10）
      course_1_a1_bonus: 0.0         # A1選手時の追加補正
      course_1_b_penalty: 0.0        # B級選手時のペナルティ

      # 天候関連補正
      strong_wind_penalty: -3.0      # 強風時（6m以上）の1コースペナルティ
      high_wave_penalty: -2.0        # 高波時（6cm以上）の1コースペナルティ

      # アウトコース補正
      outer_course_strong_wind_bonus: 2.0   # 強風時の4-6コースボーナス

    # 会場固有の特記事項
    notes:
      - "ナイター開催のため気温変化に注意"
      - "インコース勝率は全国平均並み"

  "24":  # 大村
    name: "大村"
    region: "九州"
    water_type: "seawater"

    characteristics:
      - "インが非常に強い"
      - "静水面"
      - "イン逃げ決まりやすい"

    course_win_rates:
      1: 0.681
      2: 0.112
      3: 0.094
      4: 0.066
      5: 0.035
      6: 0.012

    course_deviation:
      1: 1.24
      2: 0.80
      3: 0.78
      4: 0.66
      5: 0.58
      6: 0.40

    adjustments:
      course_1_base_bonus: 8.0        # イン強会場のため大きなボーナス
      course_1_a1_bonus: 2.0
      course_1_b_penalty: -2.0
      strong_wind_penalty: -4.0
      high_wave_penalty: -3.0
      outer_course_strong_wind_bonus: 1.5
      outer_course_base_penalty: -5.0  # 大村はアウトが特に不利

    notes:
      - "1コース勝率全国トップ"
      - "B級でも1コースなら期待できる"
      - "5-6コースは厳しい"
```

### 3.3 天候ルールスキーマ (`weather_rules.yaml`)

```yaml
meta:
  version: "1.0"
  updated_at: "2025-12-15"
  data_source: "weatherテーブル + resultsテーブル (5640件)"

# 風速カテゴリ定義
wind_speed_categories:
  calm:
    min: 0
    max: 2
    label: "微風"
  moderate:
    min: 3
    max: 5
    label: "中風"
  strong:
    min: 6
    max: 99
    label: "強風"

# 波高カテゴリ定義
wave_height_categories:
  calm:
    min: 0
    max: 2
    label: "静穏"
  moderate:
    min: 3
    max: 5
    label: "中波"
  rough:
    min: 6
    max: 99
    label: "高波"

# 風向カテゴリ定義
wind_direction_categories:
  headwind:         # 向かい風（イン有利）
    directions: ["北", "北北西", "北西", "北北東", "北東"]
    description: "向かい風 - 1コース有利"
  tailwind:         # 追い風（まくり有利）
    directions: ["南", "南南西", "南西", "南南東", "南東"]
    description: "追い風 - まくり有利"
  crosswind:        # 横風
    directions: ["東", "西", "東北東", "西北西", "東南東", "西南西"]
    description: "横風 - 影響小"

# グローバル補正ルール（全会場共通）
global_rules:
  strong_wind:
    course_1_penalty: -5.0           # 1コースへのペナルティ
    course_2_bonus: 2.0              # 2コースへのボーナス
    course_3_bonus: 2.0
    course_4_bonus: 1.5
    course_5_bonus: 1.0
    course_6_bonus: 0.5

  high_wave:
    course_1_penalty: -3.0
    outer_course_bonus: 1.5          # 4-6コース共通

  headwind:
    course_1_bonus: 2.0              # イン有利
    course_2_penalty: -1.0           # 差し不利

  tailwind:
    course_1_penalty: -2.0           # イン不利
    makuri_bonus: 3.0                # まくり得意選手にボーナス

# 会場別オーバーライド（グローバルルールを上書き）
venue_overrides:
  "08":  # 常滑
    name: "常滑"
    description: "風の影響が非常に大きい会場"
    strong_wind:
      course_1_penalty: -15.0        # グローバルの3倍
      course_2_bonus: 5.0
      course_3_bonus: 5.0
      course_4_bonus: 4.0
      course_5_bonus: 3.0
      course_6_bonus: 2.0

  "02":  # 戸田
    name: "戸田"
    description: "強風時に荒れやすい"
    strong_wind:
      course_1_penalty: -10.0

# 複合条件ルール
compound_weather_rules:
  strong_wind_high_wave:
    description: "強風かつ高波 - 大荒れ"
    conditions:
      - wind_category: "strong"
      - wave_category: "rough"
    adjustments:
      course_1_penalty: -8.0
      outer_course_bonus: 4.0
```

### 3.4 潮位補正スキーマ (`tide_adjustments.yaml`)

```yaml
meta:
  version: "1.0"
  updated_at: "2025-12-15"
  data_source: "気象庁潮位データ + レース結果分析"

# 潮位フェーズ定義
tide_phases:
  high:
    label: "満潮"
    description: "潮位が最高付近"
  rising:
    label: "上げ潮"
    description: "潮位が上昇中"
  low:
    label: "干潮"
    description: "潮位が最低付近"
  falling:
    label: "下げ潮"
    description: "潮位が下降中"

# 対象会場（海水・汽水のみ）
applicable_venues:
  seawater:
    - "04"  # 平和島
    - "08"  # 常滑
    - "09"  # 津
    - "12"  # 住之江
    - "13"  # 尼崎
    - "14"  # 鳴門
    - "15"  # 丸亀
    - "16"  # 児島
    - "17"  # 宮島
    - "18"  # 徳山
    - "19"  # 下関
    - "20"  # 若松
    - "21"  # 芦屋
    - "22"  # 福岡
    - "23"  # 唐津
    - "24"  # 大村
  brackish:
    - "03"  # 江戸川
    - "06"  # 浜名湖
    - "07"  # 蒲郡

# グローバル補正ルール
global_rules:
  high:
    course_1_bonus: 3.0              # 満潮はイン有利
    outer_course_penalty: -1.0
  rising:
    course_1_bonus: 2.0
    outer_course_penalty: -0.5
  low:
    course_1_penalty: -2.0           # 干潮はイン不利
    outer_course_bonus: 1.5
  falling:
    course_1_penalty: -1.0
    outer_course_bonus: 1.0

# 会場別オーバーライド
venue_overrides:
  "18":  # 徳山
    name: "徳山"
    description: "潮位の影響が顕著"
    high:
      course_1_bonus: 5.0
      course_4_penalty: -2.0
    low:
      course_1_penalty: -4.0
      course_4_bonus: 3.0            # 干潮時は4コースまくり有利

  "22":  # 福岡
    name: "福岡"
    description: "満潮時にまくりが決まる特殊会場"
    high:
      course_1_penalty: -2.0         # 満潮でもイン不利
      course_3_bonus: 3.0            # 3コースまくり有利
```

### 3.5 複合条件ルールスキーマ (`compound_rules.yaml`)

```yaml
meta:
  version: "1.0"
  updated_at: "2025-12-15"
  data_source: "パターン分析 (30000レース)"

rules:
  - id: "tokuyama_a1_full_tide"
    name: "徳山満潮A1イン"
    description: "徳山で満潮時のA1選手1コースは鉄板"
    enabled: true

    conditions:
      venue: "18"
      tide_phase: ["high", "rising"]
      course: 1
      racer_rank: "A1"

    adjustment: 10.0                  # +10点

    statistics:
      sample_count: 300
      hit_rate: 0.78
      confidence: 0.90
      last_verified: "2025-12-10"

  - id: "fukuoka_makuri_3"
    name: "福岡まくり3コース"
    description: "福岡で満潮時に3号艇まくり巧者は1着率上昇"
    enabled: true

    conditions:
      venue: "22"
      tide_phase: ["high", "rising"]
      course: 3
      kimarite_skill: "makuri"        # まくり得意

    adjustment: 8.0

    statistics:
      sample_count: 150
      hit_rate: 0.25
      confidence: 0.85

  - id: "omura_out_weak"
    name: "大村アウト不利"
    description: "大村では5-6コースはA1でも厳しい"
    enabled: true

    conditions:
      venue: "24"
      course: [5, 6]
      racer_rank: "A1"

    adjustment: -5.0                  # マイナス補正

    statistics:
      sample_count: 200
      hit_rate: 0.08
      confidence: 0.85

  - id: "toda_b1_in"
    name: "戸田B級イン"
    description: "戸田でB級選手のインは信頼度低い"
    enabled: true

    conditions:
      venue: "02"
      course: 1
      racer_rank: ["B1", "B2"]

    adjustment: -6.0

    statistics:
      sample_count: 180
      hit_rate: 0.35
      confidence: 0.85
```

### 3.6 統合重みスキーマ (`integration_weights.yaml`)

```yaml
meta:
  version: "1.0"
  updated_at: "2025-12-15"

# 基本統合重み
base_weights:
  pre_weight: 0.6                     # 事前情報の重み
  before_weight: 0.4                  # 直前情報の重み

# 条件別統合重み
conditional_weights:
  # 直前情報重視ケース
  before_critical:
    description: "直前情報の重要度が高い状況"
    triggers:
      - exhibition_variance_high      # 展示タイム分散が高い
      - st_variance_high              # ST分散が高い
      - entry_changes                 # 進入変更あり
      - weather_changed               # 天候急変
    weights:
      pre_weight: 0.4
      before_weight: 0.6

  # 事前情報重視ケース
  pre_reliable:
    description: "事前予測の信頼度が高い状況"
    triggers:
      - pre_confidence_high           # 事前予測スコア差大
      - before_data_incomplete        # 直前情報不完全
    weights:
      pre_weight: 0.7
      before_weight: 0.3

  # 不確実ケース
  uncertain:
    description: "予測困難な状況"
    triggers:
      - low_data_quality              # データ不足
      - conflicting_signals           # 矛盾するシグナル
    weights:
      pre_weight: 0.5
      before_weight: 0.5

# 閾値定義
thresholds:
  exhibition_variance_threshold: 0.10  # 展示タイム標準偏差
  st_variance_threshold: 0.05          # ST標準偏差
  entry_change_threshold: 2            # 進入変更艇数
  pre_confidence_threshold: 0.85       # 事前予測信頼度
  before_completeness_threshold: 0.5   # 直前情報充実度
```

---

## 4. プリセットローダー実装

### 4.1 基本設計

```python
# src/utils/preset_loader.py
"""
プリセットローダーモジュール

YAMLファイルからプリセットを読み込み、検証、キャッシュを行う。
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import hashlib


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

    PRESET_DIR = Path("config/presets")

    def __init__(self, preset_dir: Optional[Path] = None):
        self.preset_dir = preset_dir or self.PRESET_DIR
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
            adjustment_key: 補正キー
            default: デフォルト値
        """
        data = self.load("venue_characteristics")
        venue = data.get("venues", {}).get(venue_code, {})
        adjustments = venue.get("adjustments", {})
        return adjustments.get(adjustment_key, default)

    def get_weather_rule(
        self,
        venue_code: str,
        wind_category: str,
        wave_category: str
    ) -> Dict[str, float]:
        """
        天候ルールに基づく補正値を取得

        Args:
            venue_code: 会場コード
            wind_category: 風速カテゴリ
            wave_category: 波高カテゴリ

        Returns:
            コース別補正値の辞書
        """
        data = self.load("weather_rules")

        # グローバルルールを取得
        global_rules = data.get("global_rules", {})
        adjustments = {}

        # 風速ルール適用
        if wind_category in global_rules:
            adjustments.update(global_rules[wind_category])

        # 波高ルール適用
        if wave_category in global_rules:
            for k, v in global_rules[wave_category].items():
                adjustments[k] = adjustments.get(k, 0) + v

        # 会場別オーバーライド
        overrides = data.get("venue_overrides", {}).get(venue_code, {})
        if wind_category in overrides:
            adjustments.update(overrides[wind_category])

        return adjustments

    def get_compound_rules(
        self,
        venue_code: str,
        course: int,
        racer_rank: str,
        **context
    ) -> List[Dict]:
        """
        条件に合致する複合ルールを取得

        Args:
            venue_code: 会場コード
            course: コース番号
            racer_rank: 選手ランク
            **context: その他のコンテキスト（tide_phase等）

        Returns:
            合致するルールのリスト
        """
        data = self.load("compound_rules")
        matched_rules = []

        for rule in data.get("rules", []):
            if not rule.get("enabled", True):
                continue

            conditions = rule.get("conditions", {})

            # 条件チェック
            if conditions.get("venue") and conditions["venue"] != venue_code:
                continue

            if conditions.get("course"):
                courses = conditions["course"]
                if isinstance(courses, list):
                    if course not in courses:
                        continue
                elif course != courses:
                    continue

            if conditions.get("racer_rank"):
                ranks = conditions["racer_rank"]
                if isinstance(ranks, list):
                    if racer_rank not in ranks:
                        continue
                elif racer_rank != ranks:
                    continue

            # その他の条件（tide_phase等）
            for key, value in conditions.items():
                if key in ["venue", "course", "racer_rank"]:
                    continue
                context_value = context.get(key)
                if context_value is None:
                    continue
                if isinstance(value, list):
                    if context_value not in value:
                        continue
                elif context_value != value:
                    continue

            matched_rules.append({
                "rule_id": rule["id"],
                "name": rule["name"],
                "adjustment": rule["adjustment"],
                "confidence": rule.get("statistics", {}).get("confidence", 1.0)
            })

        return matched_rules

    def _extract_meta(self, name: str, data: Dict, file_path: Path):
        """メタデータを抽出"""
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
            self.load(preset_name)
        return self._meta_cache.get(preset_name)

    def reload_all(self):
        """全プリセットを再読み込み"""
        self._cache.clear()
        self._meta_cache.clear()

        for yaml_file in self.preset_dir.glob("*.yaml"):
            preset_name = yaml_file.stem
            self.load(preset_name, force_reload=True)


# シングルトンインスタンス
_preset_loader: Optional[PresetLoader] = None

def get_preset_loader() -> PresetLoader:
    """プリセットローダーのシングルトンを取得"""
    global _preset_loader
    if _preset_loader is None:
        _preset_loader = PresetLoader()
    return _preset_loader
```

---

## 5. 追加・検証ワークフロー

### 5.1 新規プリセット追加フロー

```
1. データ分析
   ├── SQLクエリで傾向を確認
   ├── サンプル数・信頼区間を算出
   └── 既存ルールとの重複チェック

2. プリセット作成
   ├── 該当YAMLファイルを編集
   ├── スキーマに準拠した形式で記述
   └── statisticsセクションにサンプル数・的中率を記録

3. 検証
   ├── バックテスト実行（scripts/validate_preset.py）
   ├── 既存性能との比較
   └── 統計的有意性の確認

4. 適用
   ├── enabledフラグをtrueに設定
   ├── meta.updated_atを更新
   └── optimization_history/に履歴保存
```

### 5.2 検証スクリプト

```python
# scripts/validate_preset.py
"""
プリセット検証スクリプト

新規または変更されたプリセットの効果を検証する。
"""

import argparse
from src.utils.preset_loader import get_preset_loader
from src.analysis.backtest import run_backtest


def validate_preset(preset_name: str, rule_id: Optional[str] = None):
    """
    プリセットを検証

    Args:
        preset_name: プリセット名
        rule_id: 特定ルールのみ検証する場合のID
    """
    loader = get_preset_loader()

    # 変更前の性能を測定
    print("=== 変更前のバックテスト ===")
    baseline_result = run_backtest(use_preset=False)
    print(f"的中率: {baseline_result['hit_rate']:.1%}")
    print(f"回収率: {baseline_result['recovery_rate']:.1%}")

    # 変更後の性能を測定
    print("\n=== 変更後のバックテスト ===")
    with_preset_result = run_backtest(use_preset=True, preset_name=preset_name)
    print(f"的中率: {with_preset_result['hit_rate']:.1%}")
    print(f"回収率: {with_preset_result['recovery_rate']:.1%}")

    # 比較
    hit_diff = with_preset_result['hit_rate'] - baseline_result['hit_rate']
    recovery_diff = with_preset_result['recovery_rate'] - baseline_result['recovery_rate']

    print("\n=== 変化 ===")
    print(f"的中率: {hit_diff:+.1%}")
    print(f"回収率: {recovery_diff:+.1%}")

    # 判定
    if hit_diff >= 0 and recovery_diff >= 0:
        print("\n[OK] プリセットは有効です")
        return True
    elif recovery_diff < -0.02:
        print("\n[NG] 回収率が2%以上低下しています")
        return False
    else:
        print("\n[WARN] 性能が若干低下しています。要確認。")
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("preset_name", help="検証するプリセット名")
    parser.add_argument("--rule-id", help="特定ルールID（任意）")
    args = parser.parse_args()

    validate_preset(args.preset_name, args.rule_id)
```

---

## 6. 最適化手法

### 6.1 グリッドサーチ

```python
# scripts/optimize_preset_values.py の一部

def grid_search_optimization(
    preset_name: str,
    param_ranges: Dict[str, List[float]],
    evaluation_func: Callable
) -> Dict[str, float]:
    """
    グリッドサーチによるパラメータ最適化

    Args:
        preset_name: 最適化対象プリセット
        param_ranges: パラメータ名と探索範囲
        evaluation_func: 評価関数（回収率を返す）

    Returns:
        最適パラメータの辞書
    """
    from itertools import product

    # 全組み合わせを生成
    param_names = list(param_ranges.keys())
    param_values = list(param_ranges.values())

    best_score = -float('inf')
    best_params = {}

    for values in product(*param_values):
        params = dict(zip(param_names, values))

        # パラメータを適用
        apply_params(preset_name, params)

        # 評価
        score = evaluation_func()

        if score > best_score:
            best_score = score
            best_params = params.copy()
            print(f"New best: {score:.4f} with {params}")

    return best_params
```

### 6.2 ベイズ最適化

```python
def bayesian_optimization(
    preset_name: str,
    param_bounds: Dict[str, Tuple[float, float]],
    evaluation_func: Callable,
    n_iterations: int = 50
) -> Dict[str, float]:
    """
    ベイズ最適化によるパラメータ探索

    Args:
        preset_name: 最適化対象プリセット
        param_bounds: パラメータ名と(最小, 最大)
        evaluation_func: 評価関数
        n_iterations: 探索回数

    Returns:
        最適パラメータ
    """
    try:
        from bayes_opt import BayesianOptimization
    except ImportError:
        print("bayesian-optimization パッケージが必要です")
        return {}

    def objective(**params):
        apply_params(preset_name, params)
        return evaluation_func()

    optimizer = BayesianOptimization(
        f=objective,
        pbounds=param_bounds,
        random_state=42
    )

    optimizer.maximize(n_iter=n_iterations)

    return optimizer.max['params']
```

---

## 7. マイグレーション計画

### 7.1 Phase 1: 会場特性の移行

1. `venue_characteristics.py` の内容をYAMLに変換
2. `PresetLoader.get_venue_adjustment()` を実装
3. `race_predictor.py` の `get_venue_adjustment()` 呼び出しを置換
4. テスト実行、結果が同一であることを確認

### 7.2 Phase 2: 天候ルールの移行

1. `weather_rules.json` をYAML形式に変換・拡張
2. `PresetLoader.get_weather_rule()` を実装
3. `WeatherAdjuster` の読み込み元を変更
4. テスト実行

### 7.3 Phase 3: 潮位補正の移行

1. `tide_adjuster.py` 内の定数をYAMLに抽出
2. `PresetLoader` に潮位補正取得メソッドを追加
3. `TideAdjuster` を改修
4. テスト実行

### 7.4 Phase 4: 複合条件の移行

1. `compound_buff_system.py` のルールをYAMLに抽出
2. `PresetLoader.get_compound_rules()` を実装
3. `CompoundBuffSystem` の読み込み元を変更
4. テスト実行

---

*本設計書はPREDICTION_REFACTORING_PLAN.mdのPhase 1に対応する*
