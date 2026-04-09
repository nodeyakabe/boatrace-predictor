# バックテスト実行ガイド

**作成日**: 2025-12-02
**目的**: 動的統合モジュールの効果検証

---

## 概要

バックテストフレームワークを使用して、過去データで予測精度を評価します。
動的統合モード vs レガシーモードの A/Bテストにより、実際の精度向上を測定します。

---

## バックテスト環境構築完了

### 作成ファイル

1. **`src/evaluation/backtest_framework.py`** (450行)
   - 過去データでレース予測を実行し、実結果と比較
   - 的中率、スコア精度（スピアマン相関）を計算
   - モード別・条件別の統計を集計

2. **`src/evaluation/ab_test_dynamic_integration.py`** (260行)
   - 動的統合とレガシーモードの並列実行
   - 改善率の自動計算とレポート生成
   - JSON + テキスト形式で結果保存

### 主な機能

#### BacktestFramework
```python
from src.evaluation.backtest_framework import BacktestFramework

framework = BacktestFramework(db_path="data/boatrace.db")
summary = framework.run_backtest(
    start_date="2025-10-01",
    end_date="2025-10-31",
    venue_codes=None,  # 全会場
    output_dir="temp/backtest/october"
)
```

**評価指標**:
- 1着的中率
- 3連単的中率
- スコア精度（スピアマン相関係数）
- モード別統計（dynamic / legacy / legacy_adjusted）
- 条件別統計（normal / before_critical / pre_reliable / uncertain）

#### ABTestDynamicIntegration
```python
from src.evaluation.ab_test_dynamic_integration import ABTestDynamicIntegration

ab_test = ABTestDynamicIntegration(db_path="data/boatrace.db")
comparison = ab_test.run_ab_test(
    start_date="2025-10-01",
    end_date="2025-10-31",
    output_dir="temp/ab_test/october"
)
```

**比較内容**:
- 動的統合モードの精度
- レガシーモードの精度
- 改善率（%）
- 結論判定（優秀 / 良好 / 改善 / 中立 / 要改善）

---

## 実行手順

### 1. シンプルなバックテスト実行

```bash
# プロジェクトルートで実行
cd c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032

# 過去1週間でテスト
python src/evaluation/backtest_framework.py
```

**出力**:
- `temp/backtest/test/detailed_results.json` - レース毎の詳細結果
- `temp/backtest/test/summary.json` - 集計サマリー

### 2. A/Bテスト実行

```bash
# 動的統合 vs レガシーモード比較
python src/evaluation/ab_test_dynamic_integration.py
```

**出力**:
- `temp/ab_test/dynamic/` - 動的統合モード結果
- `temp/ab_test/legacy/` - レガシーモード結果
- `temp/ab_test/ab_test_report.json` - 比較レポート（JSON）
- `temp/ab_test/ab_test_report.txt` - 比較レポート（テキスト）

### 3. カスタム期間でのバックテスト

```python
from datetime import datetime, timedelta
from src.evaluation.ab_test_dynamic_integration import ABTestDynamicIntegration

# 過去1ヶ月間でA/Bテスト
end_date = datetime.now()
start_date = end_date - timedelta(days=30)

ab_test = ABTestDynamicIntegration()
comparison = ab_test.run_ab_test(
    start_date=start_date.strftime('%Y-%m-%d'),
    end_date=end_date.strftime('%Y-%m-%d'),
    output_dir="temp/ab_test/1month"
)

print(f"1着的中率改善: {comparison['improvement']['hit_rate_1st']:+.2f}%")
print(f"結論: {comparison['conclusion']}")
```

---

## 出力例

### summary.json

```json
{
  "total_races": 1234,
  "date_range": ["2025-10-01", "2025-10-31"],
  "hit_rate_1st": 0.3245,
  "hit_rate_top3": 0.0456,
  "avg_score_accuracy": 0.6123,
  "mode_stats": {
    "dynamic": {
      "count": 823,
      "hit_rate_1st": 0.3512,
      "hit_rate_top3": 0.0523,
      "avg_score_accuracy": 0.6345
    },
    "legacy": {
      "count": 411,
      "hit_rate_1st": 0.2987,
      "hit_rate_top3": 0.0412,
      "avg_score_accuracy": 0.5876
    }
  },
  "condition_stats": {
    "before_critical": {
      "count": 156,
      "hit_rate_1st": 0.3846,
      "hit_rate_top3": 0.0641,
      "avg_score_accuracy": 0.6523
    },
    "pre_reliable": {
      "count": 234,
      "hit_rate_1st": 0.3504,
      "hit_rate_top3": 0.0512,
      "avg_score_accuracy": 0.6287
    },
    "normal": {
      "count": 433,
      "hit_rate_1st": 0.3371,
      "hit_rate_top3": 0.0485,
      "avg_score_accuracy": 0.6201
    }
  }
}
```

### ab_test_report.txt

```
======================================================================
動的統合 vs レガシーモード A/Bテスト結果
======================================================================

テスト実行日時: 2025-12-02 15:30:45
テスト期間: 2025-10-01 ~ 2025-10-31
対象レース数: 1234

【動的統合モード】
  1着的中率: 35.12%
  3連単的中率: 5.23%
  平均スコア精度: 0.6345

【レガシーモード】
  1着的中率: 29.87%
  3連単的中率: 4.12%
  平均スコア精度: 0.5876

【改善率】
  1着的中率: +17.58%
  3連単的中率: +26.94%
  スコア精度: +7.98%

【結論】
  優秀 - 動的統合は大幅な精度向上を実現

【動的統合 - 条件別統計】
  before_critical:
    レース数: 156
    1着的中率: 38.46%
    3連単的中率: 6.41%
    平均スコア精度: 0.6523

  pre_reliable:
    レース数: 234
    1着的中率: 35.04%
    3連単的中率: 5.12%
    平均スコア精度: 0.6287

  normal:
    レース数: 433
    1着的中率: 33.71%
    3連単的中率: 4.85%
    平均スコア精度: 0.6201

======================================================================
```

---

## 評価指標の説明

### 1. 1着的中率 (hit_rate_1st)
- 予測1位の艇が実際に1着になった割合
- **目標**: 30-40%（一般的なボートレース予測の水準）
- **動的統合の期待値**: +5-15%の向上

### 2. 3連単的中率 (hit_rate_top3)
- 予測上位3艇が実際の上位3艇と完全一致した割合
- **目標**: 3-7%（難易度が高い）
- **動的統合の期待値**: +10-30%の向上

### 3. スコア精度 (avg_score_accuracy)
- スピアマン順位相関係数の平均
- **範囲**: -1.0 ~ 1.0（1.0が完全一致）
- **目標**: 0.5以上
- **動的統合の期待値**: +5-10%の向上

### 4. 改善率の判定基準

| 結論 | 1着的中率改善 | スコア精度改善 | 評価 |
|-----|------------|-------------|------|
| **優秀** | +10%以上 | +5%以上 | 大幅な精度向上 |
| **良好** | +5%以上 | +2%以上 | 明確な精度向上 |
| **改善** | +0%以上 | +0%以上 | 小幅な精度向上 |
| **中立** | -5%以内 | - | 効果は限定的 |
| **要改善** | -5%以下 | - | 調整が必要 |

---

## トラブルシューティング

### エラー: "no such table: results"

**原因**: DBスキーマの違い

**対処法**: `backtest_framework.py`内のテーブル名を確認
```python
# resultsテーブルが存在するか確認
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
print([row[0] for row in cursor.fetchall()])
```

### エラー: "対象レース数: 0"

**原因**: 指定期間にデータが存在しない

**対処法**: データが存在する期間を確認
```python
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()
cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
print(cursor.fetchone())
```

### 処理が遅い

**原因**: 大量のレースを処理している

**対処法**:
1. 期間を短縮（1週間程度でテスト）
2. 特定会場のみに絞る
3. バックグラウンド実行

---

## 次のステップ

### ステップ1: 小規模テスト（完了確認）
```bash
# 過去1週間でクイックテスト
python src/evaluation/ab_test_dynamic_integration.py
```

### ステップ2: 本格バックテスト
```python
# 過去1-3ヶ月で本格評価
from datetime import datetime, timedelta
from src.evaluation.ab_test_dynamic_integration import ABTestDynamicIntegration

end_date = datetime.now()
start_date = end_date - timedelta(days=90)  # 3ヶ月

ab_test = ABTestDynamicIntegration()
comparison = ab_test.run_ab_test(
    start_date=start_date.strftime('%Y-%m-%d'),
    end_date=end_date.strftime('%Y-%m-%d'),
    output_dir="temp/ab_test/3months"
)
```

### ステップ3: 会場別分析
```python
# 特定会場の精度を詳細分析
for venue in ['01', '02', '03']:  # 桐生、戸田、江戸川
    comparison = ab_test.run_ab_test(
        start_date="2025-10-01",
        end_date="2025-10-31",
        venue_codes=[venue],
        output_dir=f"temp/ab_test/venue_{venue}"
    )
    print(f"会場{venue}: 改善率{comparison['improvement']['hit_rate_1st']:+.2f}%")
```

### ステップ4: 継続モニタリング
- 週次でバックテストを実行
- 精度が低下した場合は閾値調整
- 新たな条件パターンの発見

---

## まとめ

✅ **バックテスト環境構築完了**

- BacktestFramework実装完了（450行）
- ABTestDynamicIntegration実装完了（260行）
- DBスキーマに対応したクエリ修正完了
- 評価指標とレポート生成機能完備

**次の作業**: 実データでA/Bテストを実行し、動的統合の効果を測定
