# 予測ロジック改善の標準ワークフロー

**作成日**: 2025-12-22
**目的**: 予測ロジック変更時の効率的な検証手順を標準化

---

## 📋 ワークフローの全体像

```
予測ロジック変更
  ↓
予測データ生成（汎用スクリプト使用）
  ↓
バックテスト実行（汎用スクリプト使用）
  ↓
効果判定
  ↓
採用 or 不採用
```

---

## 🚀 標準ワークフロー（推奨）

### Step 1: 予測ロジックの変更

```python
# 例: extended_scorer.py でスコアリングロジックを変更
vim src/analysis/extended_scorer.py

# または: フィーチャーフラグで制御
vim config/feature_flags.py
```

---

### Step 2: 予測データの生成

**汎用スクリプトを使用**:

#### ケースA: 単一年度で検証

```bash
# 2025年のみ生成（並列処理で高速）
python scripts/universal_prediction_generator.py \
    --year 2025 \
    --parallel \
    --workers 8 \
    --force
```

**処理時間**: 30-40分

#### ケースB: 複数年度で検証

```bash
# 2022-2025年の4年分を生成
python scripts/universal_prediction_generator.py \
    --years 2022,2023,2024,2025 \
    --parallel \
    --workers 8 \
    --force
```

**処理時間**: 1.5-2.5時間

#### ケースC: 特定期間のみ検証

```bash
# 2025年6月のみ生成
python scripts/universal_prediction_generator.py \
    --start-date 2025-06-01 \
    --end-date 2025-06-30 \
    --parallel \
    --force
```

**処理時間**: 5-10分

---

### Step 3: バックテスト実行

**汎用スクリプトを使用**:

#### ケースA: 単一年度

```bash
# 2025年のバックテスト
python scripts/backtest_with_predictions.py \
    --year 2025 \
    --report output/backtest_2025.md
```

**処理時間**: 5-10分

#### ケースB: 複数年度

```bash
# 2022-2025年のバックテスト
python scripts/backtest_with_predictions.py \
    --years 2022,2023,2024,2025 \
    --report output/backtest_2022_2025.md
```

**処理時間**: 10-20分

#### ケースC: 特定期間

```bash
# 2025年6月のバックテスト
python scripts/backtest_with_predictions.py \
    --start-date 2025-06-01 \
    --end-date 2025-06-30
```

**処理時間**: 1-2分

---

### Step 4: 効果判定

バックテスト結果から判定：

#### ✅ 採用条件

- **全年度でROI 100%以上**
- **信頼度別の内訳が健全**（特定の信頼度に偏っていない）
- **年度間で安定している**（2024年だけプラス、などではない）

#### ❌ 不採用条件

- いずれかの年度でROI 100%未満
- 特定の年度のみ極端に良い/悪い（過学習の疑い）
- 購入レース数が極端に少ない（フィルターが厳しすぎる）

---

### Step 5: 採用 or 不採用

#### 採用の場合

```bash
# フィーチャーフラグを本番化
vim config/feature_flags.py
# 該当フラグを True に設定

# Gitにコミット
git add .
git commit -m "新予測ロジック採用: [変更内容]

## 効果
- ROI: XXX%
- 収支: +XXX円

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

git push origin main
```

#### 不採用の場合

```bash
# 変更を元に戻す
git restore .

# または、フィーチャーフラグをFalseに設定
vim config/feature_flags.py
```

---

## 📊 処理時間の比較

| フェーズ | 単一年度 | 複数年度（4年） | 特定期間（1ヶ月） |
|---------|---------|----------------|-----------------|
| **予測データ生成** | 30-40分 | 1.5-2.5時間 | 5-10分 |
| **バックテスト** | 5-10分 | 10-20分 | 1-2分 |
| **合計** | **35-50分** | **1.5-3時間** | **6-12分** |

---

## 🎯 実践例

### 例1: 「決まり手別展開予測」を実装

#### 1. ロジック変更

```python
# config/feature_flags.py
'kimarite_flow_prediction': True,
'makuri_risk_adjustment': True,
```

#### 2. 2025年で検証

```bash
# 予測データ生成（40分）
python scripts/universal_prediction_generator.py \
    --year 2025 \
    --parallel \
    --workers 8 \
    --force

# バックテスト（5分）
python scripts/backtest_with_predictions.py \
    --year 2025
```

**結果**: ROI +4.1pt → 効果あり！

#### 3. 全年度で検証

```bash
# 予測データ生成（2時間）
python scripts/universal_prediction_generator.py \
    --years 2022,2023,2024,2025 \
    --parallel \
    --workers 8 \
    --force

# バックテスト（15分）
python scripts/backtest_with_predictions.py \
    --years 2022,2023,2024,2025 \
    --report output/kimarite_flow_backtest.md
```

**結果**: 全年度でROI 110%以上 → **採用**

**合計時間**: 約2.5時間

---

### 例2: 「選手調子係数」を検証

#### 1. ロジック変更

```python
# config/feature_flags.py
'condition_factor': True,
```

#### 2. 2025年で検証

```bash
# 予測データ生成（40分）
python scripts/universal_prediction_generator.py \
    --year 2025 \
    --parallel \
    --workers 8 \
    --force

# バックテスト（5分）
python scripts/backtest_with_predictions.py \
    --year 2025
```

**結果**: ROI -9.5pt → 効果なし

#### 3. 不採用

```python
# フィーチャーフラグを戻す
'condition_factor': False,
```

**合計時間**: 約45分（全年度検証不要）

---

## 🔧 高度な使い方

### 段階的な検証（推奨）

全年度を一気に処理せず、順次確認：

```bash
# Step 1: 2025年のみ（40分）
python scripts/universal_prediction_generator.py --year 2025 --parallel --force
python scripts/backtest_with_predictions.py --year 2025

# → ROI 110%以上なら次へ

# Step 2: 2024年も追加（1時間）
python scripts/universal_prediction_generator.py --year 2024 --parallel --force
python scripts/backtest_with_predictions.py --years 2024,2025

# → 両年度でプラスなら次へ

# Step 3: 2022-2023年も追加（1.5時間）
python scripts/universal_prediction_generator.py --years 2022,2023 --parallel --force
python scripts/backtest_with_predictions.py --years 2022,2023,2024,2025
```

**効果**: 2025年でマイナスなら40分で中止可能（全年度生成: 2.5時間 → 85%削減）

---

### フィルター変更のみの場合

**予測データは再利用、フィルターだけ変更して検証**:

```bash
# 予測データ生成は不要！

# フィルター変更
vim src/betting/bet_target_evaluator.py

# バックテストのみ実行（10分）
python scripts/backtest_with_predictions.py --years 2022,2023,2024,2025
```

**効果**: 2.5時間 → 10分（**96%削減**）

---

### 直前情報を使った予測の検証

```bash
# 直前情報を使った予測データ生成
python scripts/universal_prediction_generator.py \
    --year 2025 \
    --parallel \
    --use-beforeinfo \
    --force

# バックテスト（prediction_type=before）
python scripts/backtest_with_predictions.py \
    --year 2025 \
    --prediction-type before
```

---

## ⚠️ 注意事項

### 1. 並列処理中は他のプロセスを停止

```bash
# 並列処理開始前に確認
tasklist /FI "IMAGENAME eq python.exe"

# 必要なら停止
taskkill /F /IM python.exe
```

**理由**: DB競合を防ぐため

---

### 2. バックアップ推奨

大規模な変更前にDBバックアップ：

```bash
copy data\boatrace.db data\boatrace_backup_20251222.db
```

---

### 3. 既存データの扱い

**--force オプション**:
- あり: 既存データを上書き（ロジック変更時は必須）
- なし: 既存データをスキップ（新しい日付のみ生成）

```bash
# ロジック変更後は --force 必須
python scripts/universal_prediction_generator.py --year 2025 --force

# 新しい日付を追加する場合は不要
python scripts/universal_prediction_generator.py --year 2025
```

---

## 📚 スクリプト一覧

| スクリプト | 目的 | 処理時間 |
|-----------|------|---------|
| [universal_prediction_generator.py](../scripts/universal_prediction_generator.py) | 予測データ生成（汎用） | 30分-2.5時間 |
| [backtest_with_predictions.py](../scripts/backtest_with_predictions.py) | バックテスト（汎用） | 5-20分 |

---

## ✅ チェックリスト

### 予測ロジック変更時

- [ ] ロジック変更内容をコメント・ドキュメント化
- [ ] フィーチャーフラグで制御可能にする
- [ ] 2025年で効果確認（40-50分）
- [ ] 効果あり → 全年度で検証（2.5時間）
- [ ] 全年度でプラス → 採用・コミット
- [ ] 効果なし → 不採用・元に戻す

### フィルター変更時

- [ ] フィルター変更内容をドキュメント化
- [ ] 予測データはそのまま（再生成不要）
- [ ] バックテストのみ実行（10分）
- [ ] 効果確認 → 採用 or 不採用

---

**作成者**: Claude Sonnet 4.5
