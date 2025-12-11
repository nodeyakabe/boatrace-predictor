# 環境要因減点システム 設定ファイル

## 概要

このディレクトリには環境要因減点システムの設定ファイルが含まれています。

## ファイル

### environmental_penalty_rules.yaml

信頼度Bの予測に対して、環境要因（会場、時間帯、風向、風速、波高、天候）に基づき減点を適用し、調整後スコアと信頼度を算出するためのルール定義ファイル。

## 設定ファイルの構造

```yaml
rules:                    # 減点ルール一覧
  - category: "..."       # ルールカテゴリ
    venue: "02"          # 会場コード（オプション）
    time: "午前"          # 時間帯（オプション）
    wind_direction: "北"  # 風向（オプション）
    wind_category: "強風" # 風速カテゴリ（オプション）
    wave: "大波"          # 波高カテゴリ（オプション）
    weather: "雨"         # 天候（オプション）
    penalty: 7           # 減点ポイント
    description: "..."   # ルール説明
    sample_size: 41      # サンプル数（参考値）
    hit_rate: 29.27      # 的中率（参考値）
    enabled: true        # 有効/無効フラグ

thresholds:              # カテゴリ化の閾値
  time: ...              # 時間帯分類
  wind_speed: ...        # 風速分類
  wave_height: ...       # 波高分類

confidence_thresholds:   # 信頼度調整の閾値
  B: { min_score: 100 }
  C: { min_score: 80 }
  D: { max_score: 79 }

system:                  # システム設定
  enabled: true          # システム全体の有効/無効
  min_sample_size: 5     # 最小サンプル数
  baseline_hit_rate: 66.81  # ベースライン的中率
```

## ルールの追加・編集方法

### 1. 新しいルールの追加

```yaml
rules:
  - category: "会場×時間帯"
    venue: "05"
    time: "午前"
    penalty: 5
    description: "多摩川×午前（n=30, 的中率45%）"
    sample_size: 30
    hit_rate: 45.0
    enabled: true
```

### 2. ルールの無効化

```yaml
  - category: "..."
    # ... 他の設定 ...
    enabled: false  # これでルールを無効化
```

### 3. 閾値の調整

```yaml
thresholds:
  time:
    午前:
      start: "09:00"  # 開始時刻を変更
      end: "12:00"    # 終了時刻を変更
```

## 減点計算の基準

- **計算式**: 5%的中率低下 = 1pt減点
- **基準値**: 2025年BEFORE予測 信頼度B データ (n=5,537)
- **全体的中率**: 66.81%

例：
- 的中率40% → 差分26.81% → 減点5pt
- 的中率30% → 差分36.81% → 減点7pt

## 信頼度の再判定

調整後スコアに基づいて信頼度を再判定：

| 調整後スコア | 信頼度 | 動作 |
|------------|--------|------|
| 100以上 | B | 信頼度B維持 |
| 80-99 | C | 信頼度Cに降格 |
| 79以下 | D | 信頼度Dに降格（投票対象外） |

## 使用方法

### Pythonコードからの使用

```python
from src.analysis.environmental_penalty import EnvironmentalPenaltySystem

# デフォルトの設定ファイルを使用
penalty_system = EnvironmentalPenaltySystem()

# カスタム設定ファイルを使用
penalty_system = EnvironmentalPenaltySystem(
    config_path='path/to/custom_rules.yaml'
)

# 減点計算
result = penalty_system.should_accept_bet(
    venue_code='02',
    race_time='11:30',
    wind_direction='北',
    wind_speed=5.0,
    wave_height=8.0,
    weather='雨',
    original_score=105.0
)

print(f"減点: {result['penalty']}pt")
print(f"調整後スコア: {result['adjusted_score']}")
print(f"信頼度: {result['adjusted_confidence']}")
```

### ConfidenceBFilterとの統合

```python
from src.analysis.confidence_filter import ConfidenceBFilter

# 環境要因減点システムを有効化
filter_system = ConfidenceBFilter(use_environmental_penalty=True)

result = filter_system.should_accept_bet(
    venue_code=2,
    race_date='2025-01-15',
    confidence_score=110.0,
    race_time='10:30',
    wind_direction='北東',
    wind_speed=5.0,
    wave_height=8.0,
    weather='雨'
)
```

## 検証結果

2025年BEFORE予測データ（n=5,537）での検証結果：

| パターン | 残レース数 | 的中率 | 改善 |
|---------|-----------|--------|------|
| ベースライン | 100% (5,537) | 66.81% | - |
| 調整後D除外 | 95.8% (5,302) | 67.10% | +0.29pt |
| **調整後Bのみ** | **51.1% (2,830)** | **73.61%** | **+6.81pt** |
| 減点7pt以上除外 | 97.7% (5,408) | 67.60% | +0.80pt |

調整後Bのみの買い目に絞ることで、的中率が**66.81% → 73.61%（+10.2%改善）**

## 更新履歴

- 2025-01-15: 初版作成
  - 21個の減点ルールを実装
  - 2025年データに基づく検証完了

## 注意事項

1. **データ更新時**: 新しいデータで検証を行い、`sample_size`と`hit_rate`を更新してください
2. **ベースライン更新**: 年度が変わったら`baseline_hit_rate`を再計算してください
3. **ルールの追加**: サンプル数が少ない（n<5）パターンは避けてください
4. **バックアップ**: 設定ファイルを編集する前に、必ずバックアップを取ってください

## 関連ファイル

- [src/analysis/environmental_penalty.py](../src/analysis/environmental_penalty.py) - 減点システム実装
- [src/analysis/confidence_filter.py](../src/analysis/confidence_filter.py) - フィルタ統合
- [scripts/validate_penalty_system.py](../scripts/validate_penalty_system.py) - 検証スクリプト
- [scripts/test_environmental_integration.py](../scripts/test_environmental_integration.py) - 統合テスト
