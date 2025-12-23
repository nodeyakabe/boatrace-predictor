# 予測ロジック改善の効率化ガイド

**作成日**: 2025-12-22
**目的**: 予測ロジック変更時の検証を効率化し、開発サイクルを高速化

---

## 📌 課題

予測ロジックを変更するたびに、以下の作業が必要で時間がかかる：

1. 全期間の予測データ再生成（1-2時間）
2. バックテスト実行（10-30分）
3. 効果測定・分析（10-30分）

**合計**: 2-3時間

↓

**問題**: 効果がない変更でも2-3時間かかってしまい、試行錯誤が遅い

---

## ✅ 解決策：段階的バリデーション

### 新しいワークフロー（推奨）

```
Step 1: サンプル検証（5-10分）
  ↓ 効果ありなら進む
Step 2: 1ヶ月検証（10-20分）
  ↓ 効果ありなら進む
Step 3: 全期間再生成（1-2時間）
  ↓ 本採用
```

**効果**:
- ✅ ダメな変更を5-10分で見切れる（従来: 2-3時間）
- ✅ 試行錯誤のサイクルが **12倍高速化**（2時間 → 10分）
- ✅ 複数の改善案を1日で検証可能（従来: 1-2案/日 → 4-8案/日）

---

## 🚀 使い方

### Step 1: サンプル検証（5-10分）

**目的**: ロジック変更の効果を素早く確認

```bash
# 200件のランダムサンプルで検証
python scripts/quick_validation_test.py --year 2025 --sample-size 200
```

**確認ポイント**:
- ✅ 的中率が 4.0% 以上
- ✅ ROI が 100% 以上（購入対象がある場合）
- ✅ 購入対象が 0 件でないこと（フィルターが厳しすぎない）

**判断**:
- ✅ 効果あり → Step 2 へ
- ❌ 効果なし → ロジック見直し（5-10分で判断）

---

### Step 2: 1ヶ月検証（10-20分）

**目的**: 詳細な効果測定（約1,500レース）

```bash
# 2025年6月で検証（約1,500レース）
python scripts/monthly_validation_test.py --year 2025 --month 6
```

**確認ポイント**:
- ✅ ROI が 120% 以上
- ✅ 信頼度別の内訳が健全（特定の信頼度だけに偏っていない）
- ✅ 購入レース数が適切（多すぎず少なすぎず）

**判断**:
- ✅ ROI 120%+ → Step 3 へ（全期間再生成）
- ⚠️ ROI 100-120% → 他の月でも検証（念のため）
- ❌ ROI 100%未満 → ロジック調整

---

### Step 3: 全期間再生成（1-2時間）

**目的**: 本採用のための全期間データ生成

```bash
# 2025年全期間を並列処理で再生成
python scripts/regenerate_predictions_2025_parallel.py

# 複数年まとめて再生成（2022-2025年）
python scripts/regenerate_predictions_2022_2024.py
```

**注意**:
- ⚠️ DB競合を避けるため、他のプロセスを停止してから実行
- ⚠️ バックアップ推奨: `copy data\boatrace.db data\boatrace_backup_YYYYMMDD.db`

---

## 🎯 効率化の追加テクニック

### 【テクニック1】キャッシュの活用

予測生成時に `use_cache=True` を使うことで、DB読み込みを90%削減：

```python
# キャッシュ有効（推奨）
predictor = RacePredictor(use_cache=True)

# キャッシュ無効（遅い）
predictor = RacePredictor(use_cache=False)
```

**効果**: 1レースあたり 11秒 → 3秒（70%削減）

---

### 【テクニック2】並列処理の活用

複数年の再生成は並列処理で高速化：

```bash
# 並列版（8コア使用）
python scripts/regenerate_predictions_2025_parallel.py

# 逐次版（遅い）
python scripts/regenerate_predictions_2025.py
```

**効果**: 2時間 → 40分（67%削減）

**注意**: 並列処理中は他のPythonプロセスを停止すること（DB競合防止）

---

### 【テクニック3】特定月のみ再生成

全期間ではなく、特定月のみ再生成してテスト：

```bash
# 2025年6月のみ再生成
python scripts/fast_prediction_generator.py --date 2025-06-01 --force

# 2025年6月全体をループで再生成
for day in {01..30}; do
    python scripts/fast_prediction_generator.py --date 2025-06-$day --force
done
```

**効果**: 1ヶ月（約1,500レース）= 約10-15分

---

## 📊 処理時間の比較

| 手法 | 対象レース数 | 処理時間 | 適用場面 |
|------|------------|---------|---------|
| **サンプル検証** | 200件 | **5-10分** | 効果の有無を素早く判断 |
| **1ヶ月検証** | 1,500件 | **10-20分** | 詳細な効果測定 |
| **全期間再生成（並列）** | 18,000件 | **40-60分** | 本採用 |
| **全期間再生成（逐次）** | 18,000件 | **2-3時間** | 非推奨 |

---

## 🔄 開発サイクルの改善例

### 従来のワークフロー（遅い）

```
アイデア
  ↓
コード変更
  ↓
全期間再生成（2時間）← ここで時間がかかる
  ↓
バックテスト（30分）
  ↓
結果確認 → ダメなら最初から（合計2.5時間のロス）
```

**1日の試行錯誤**: 2-3回

---

### 新しいワークフロー（速い）✅

```
アイデア
  ↓
コード変更
  ↓
サンプル検証（10分）← 効果なしなら即中止
  ↓ 効果あり
1ヶ月検証（20分）
  ↓ 効果あり
全期間再生成（1時間）
  ↓
本採用
```

**1日の試行錯誤**: 6-8回（3-4倍の生産性）

---

## 💡 実践例

### 例1: 「2着・3着の決まり手別展開予測」を検証

```bash
# 1. コード変更
vim src/prediction/kimarite_flow_predictor.py

# 2. サンプル検証（5分）
python scripts/quick_validation_test.py --year 2025 --sample-size 200

# 結果: ROI +4.1pt → 効果あり！

# 3. 1ヶ月検証（15分）
python scripts/monthly_validation_test.py --year 2025 --month 6

# 結果: ROI 124.5% → 高効果確認！

# 4. 全期間再生成（1時間）
python scripts/regenerate_predictions_2025_parallel.py

# 5. 本採用
vim config/feature_flags.py
# kimarite_flow_prediction: True に変更
```

**従来**: 2-3時間かかっていた → **新方式**: 1.5時間（40%削減）

---

### 例2: 「選手調子係数」を検証

```bash
# 1. コード変更
vim src/analysis/extended_scorer.py

# 2. サンプル検証（5分）
python scripts/quick_validation_test.py --year 2025 --sample-size 200

# 結果: ROI -9.5pt → 効果なし！

# → ここで中止（5分で判断）
```

**従来**: 2-3時間かかっていた → **新方式**: 5分（**96%削減**）

---

## ⚠️ 注意事項

### 1. サンプリングバイアスに注意

- ランダムサンプリングを使用（偏りを防ぐ）
- サンプル数は最低200件以上推奨
- 統計的な信頼性を確保

### 2. 複数月での検証を推奨

1ヶ月だけだと偶然高ROIになる可能性があるため：

```bash
# 複数月で検証
python scripts/monthly_validation_test.py --year 2025 --month 3
python scripts/monthly_validation_test.py --year 2025 --month 6
python scripts/monthly_validation_test.py --year 2025 --month 9
```

**3ヶ月すべてでROI 110%以上** → 採用

---

## 📈 期待される効果

### 開発効率の向上

| 指標 | 従来 | 改善後 | 改善率 |
|------|------|--------|--------|
| ダメな案の見切り時間 | 2-3時間 | **5-10分** | **96%削減** |
| 1日の試行錯誤回数 | 2-3回 | **6-8回** | **3-4倍** |
| アイデアの検証スピード | 遅い | **速い** | ✅ |

### ROI改善の加速

- より多くのアイデアを試せる → 良い施策が見つかりやすい
- 試行錯誤が速い → 最適化が進む
- データに基づく判断 → 無駄な作業が減る

---

## 📚 関連スクリプト

| スクリプト | 処理時間 | 目的 |
|-----------|---------|------|
| [scripts/quick_validation_test.py](../scripts/quick_validation_test.py) | 5-10分 | サンプル検証 |
| [scripts/monthly_validation_test.py](../scripts/monthly_validation_test.py) | 10-20分 | 1ヶ月詳細検証 |
| [scripts/regenerate_predictions_2025_parallel.py](../scripts/regenerate_predictions_2025_parallel.py) | 40-60分 | 全期間並列再生成 |
| [scripts/fast_prediction_generator.py](../scripts/fast_prediction_generator.py) | 2-3分/日 | 1日分の高速生成 |

---

**作成者**: Claude Sonnet 4.5
