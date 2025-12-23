# 予測データ生成スクリプト ガイド

**最終更新**: 2025-12-22

---

## 🎯 推奨スクリプト

### **generate_predictions.py** ⭐ 統合スクリプト（推奨）

全ての予測生成タスクに対応する統合スクリプトです。

**特徴**:
- ✅ hierarchical_predictor 自動チェック（D/Eのみ生成を**100%防止**）
- ✅ ドライラン機能（`--dry-run`）
- ✅ ロックファイル（並列実行制御）
- ✅ UPSERT方式（既存データを削除しない）
- ✅ 進捗表示と推定完了時刻

**使用例**:
```bash
# ドライラン（10件サンプル生成で信頼度分布を確認）
python scripts/generate_predictions.py --dry-run

# 2024年のadvance予測を再生成
python scripts/generate_predictions.py --years 2024 --type advance

# 2022-2025年の全予測を再生成
python scripts/generate_predictions.py --years 2022,2023,2024,2025 --type both

# 未生成分のみ生成
python scripts/generate_predictions.py --years 2024 --type advance --skip-existing
```

---

### **regenerate_predictions_optimized.py** ⭐ 最適化版（推奨）

バッチコミットと進捗表示に優れた最適化版スクリプトです。

**特徴**:
- ✅ hierarchical_predictor 自動チェック
- ✅ `--dry-run` オプション対応
- ✅ バッチコミット（100件ごと）で高速化
- ✅ UPDATE方式（DELETEしない）

**使用例**:
```bash
# ドライラン
python scripts/regenerate_predictions_optimized.py --dry-run

# 本実行（2022-2025年）
python scripts/regenerate_predictions_optimized.py

# 本実行（2024年のみ）
python scripts/regenerate_predictions_optimized.py --years 2024
```

---

## ⚠️ 注意が必要なスクリプト

### **generate_advance_fast.py**

**状態**: ⚠️ 安全チェック追加済み（2025-12-22）

**特徴**:
- ✅ hierarchical_predictor チェック追加済み
- 年度指定が必要（`--year XXXX`）
- UPSERT方式（削除なし）

**使用例**:
```bash
python scripts/generate_advance_fast.py --year 2024
```

---

## 🔴 使用禁止スクリプト

### **generate_advance_ultrafast.py** ❌ アーカイブ済み

**状態**: ❌ **使用禁止**（`scripts_archive/generate_advance_D_E_ONLY_DEPRECATED.py` に移動）

**問題点**:
- ❌ hierarchical_predictor を**強制的にOFF**にする
- ❌ 信頼度が D/E のみになる
- ❌ A, B, C の信頼度が生成されない

**移動先**: `scripts_archive/generate_advance_D_E_ONLY_DEPRECATED.py`

---

## 📊 スクリプト比較表

| スクリプト名 | hierarchical | ドライラン | ロック | 信頼度分布 | 推奨度 |
|-------------|-------------|----------|--------|-----------|--------|
| **generate_predictions.py** | ✅ 自動チェック | ✅ | ✅ | A-E 全て | ⭐⭐⭐ |
| **regenerate_predictions_optimized.py** | ✅ 自動チェック | ✅ | ❌ | A-E 全て | ⭐⭐⭐ |
| generate_advance_fast.py | ✅ 自動チェック | ❌ | ❌ | A-E 全て | ⭐⭐ |
| ~~generate_advance_ultrafast.py~~ | ❌ **強制OFF** | ❌ | ❌ | **D/E のみ** | ❌ 使用禁止 |

---

## 🛡️ 安全チェック機構

### hierarchical_predictor 自動チェック

全ての推奨スクリプトは、起動時に `hierarchical_predictor` の状態をチェックします。

**OFFの場合**:
```
======================================================================
🔴 FATAL ERROR: hierarchical_predictor is OFF
======================================================================

このまま続行すると、信頼度が D/E のみになります。
A, B, C の信頼度が生成されません。

対処方法:
  1. config/feature_flags.py を開く
  2. 'hierarchical_predictor': True に設定
  3. スクリプトを再実行

======================================================================
```

**処理は自動停止**され、D/Eのみのデータが生成されることを**100%防止**します。

---

## 🔒 ロックファイル機構

`generate_predictions.py` は、年度別にロックファイルを作成し、並列実行を制御します。

**ロックファイルの場所**:
```
data/.lock_prediction_2024
data/.lock_prediction_2025
```

**並列実行時の動作**:
```bash
# ターミナル1
python scripts/generate_predictions.py --years 2024

# ターミナル2（同時実行）
python scripts/generate_predictions.py --years 2024
# → ❌ 2024年は既に処理中です（ロックファイル: data/.lock_prediction_2024）
```

**異常終了時の対処**:
```bash
# ロックファイルを手動削除
del data\.lock_prediction_2024

# または
rm data/.lock_prediction_2024
```

---

## 📋 作業開始前の必須確認

### ⚠️ 最重要: 何を作るか明確にする

**過去の失敗事例**:
- オプション指定ミスで想定外のデータを生成
- 作成後に「使い道がない」と判明
- 作成前の整理不足で無駄な生成

**対策**: 作業前に必ず計画書を記入

📄 **テンプレート**: [docs/templates/PREDICTION_GENERATION_PLAN.md](../docs/templates/PREDICTION_GENERATION_PLAN.md)
📄 **簡易版**: [docs/templates/QUICK_CHECKLIST.md](../docs/templates/QUICK_CHECKLIST.md)

**最低限確認すべき3つの質問**:
1. **何を作る？** → 年度、タイプ、範囲を明確に
2. **なぜ作る？** → 目的を明確に
3. **どう使う？** → 具体的な使用方法を明確に

**使わないデータは作らない！**

---

## 📝 生成前チェックリスト

推奨スクリプトを使う場合でも、以下を確認することを推奨します。

### 1. フィーチャーフラグ確認

```python
# config/feature_flags.py
FEATURE_FLAGS = {
    'hierarchical_predictor': True,  # ✅ 必須
    'lightgbm_ranking': True,
    'pairwise_scoring': True,
    # ...
}
```

### 2. ドライラン実行

```bash
# 必ずドライランで信頼度分布を確認
python scripts/generate_predictions.py --dry-run
```

**期待される出力**:
```
🔍 DRY RUN: 2024年 advance 予測のサンプル生成検証（10件）
======================================================================

サンプル生成結果:
  成功: 10/10
  信頼度分布: {'A': 5, 'B': 12, 'C': 18, 'D': 15, 'E': 10}

✅ 検証成功: A-E 全ての信頼度が確認されました
本実行に進んで問題ありません。
```

### 3. DBバックアップ

```bash
copy data\boatrace.db data\boatrace_backup_20251222.db
```

---

## ❓ トラブルシューティング

### Q1. "hierarchical_predictor is OFF" エラー

**原因**: `config/feature_flags.py` で `hierarchical_predictor` が False

**対処**:
```python
# config/feature_flags.py
FEATURE_FLAGS = {
    'hierarchical_predictor': True,  # False → True に変更
    # ...
}
```

---

### Q2. ロックファイルエラー

```
❌ 2024年は既に処理中です（ロックファイル: data/.lock_prediction_2024）
```

**原因**: 前回の処理が異常終了してロックファイルが残っている

**対処**:
```bash
# ロックファイルを削除
del data\.lock_prediction_2024
```

---

### Q3. D/E のみの信頼度になってしまった

**原因**: 推奨スクリプト以外を使用した可能性

**対処**:
1. ✅ 推奨スクリプト（`generate_predictions.py` または `regenerate_predictions_optimized.py`）を使用
2. ✅ `--dry-run` で検証してから本実行
3. ✅ `hierarchical_predictor: True` を確認

---

## 📚 関連ドキュメント

- [安全チェックモジュール](safety_check.py) - 共通安全チェック機能
- [残タスク一覧](../docs/残タスク一覧.md) - プロジェクト管理
- [HANDOVER_20251221.md](../docs/HANDOVER_20251221.md) - 引継ぎ資料

---

**作成日**: 2025-12-22
**作成者**: Claude Sonnet 4.5
**目的**: 予測データ生成の3日間の無駄を防止する
