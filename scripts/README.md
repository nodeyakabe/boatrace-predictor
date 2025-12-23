# scripts/ディレクトリ索引

## 推奨スクリプト（ルート直下）

| スクリプト | 説明 | 使用頻度 |
|------------|------|----------|
| **benchmark_prediction_system.py** | 予測システムベンチマーク | 高 |
| **search_knowledge.py** | 知見DB検索 | 高 |
| **register_experiment.py** | 施策登録 | 中 |
| **query_knowledge_db.py** | 知見DB詳細検索 | 中 |
| **safety_check.py** | 安全性チェック | 低 |

---

## ベンチマーク・性能管理

予測ロジック変更時の標準ワークフロー。詳細は [PREDICTION_SYSTEM_STATUS.md](../docs/guides/PREDICTION_SYSTEM_STATUS.md) 参照。

### ステップ1: ベースライン保存

```bash
# 変更前の性能をベースラインとして保存
python scripts/benchmark_prediction_system.py --save-baseline
```

### ステップ2: フラグ変更

```python
# config/feature_flags.py を編集
'kimarite_flow_prediction': True,  # 有効化
```

### ステップ3: 再測定・比較

```bash
# 再測定（自動保存）
python scripts/benchmark_prediction_system.py

# 前回（ベースライン）と比較
python scripts/benchmark_prediction_system.py --compare
```

### ステップ4: 履歴記録

```bash
# 変更内容を履歴に記録
python scripts/maintenance/track_performance_change.py \
    --description "kimarite_flow_prediction を有効化"
```

### 現状確認

```bash
# 現在の設定・性能をドキュメントに反映
python scripts/maintenance/extract_current_config.py

# 結果は docs/guides/PREDICTION_SYSTEM_STATUS.md に出力
```

### ベンチマーク結果

- 保存先: `data/benchmark_results/`
- ベースライン: `data/benchmark_results/baseline_2025.json`
- 履歴ログ: `data/benchmark_results/change_logs/`

---

## ディレクトリ構造

### prediction/ - 予測生成系
```bash
# 推奨スクリプト
python scripts/prediction/generate_predictions.py

# その他
regenerate_predictions_*.py - 予測再生成
universal_prediction_generator.py - 汎用予測生成
```

### backtest/ - バックテスト系
```bash
# 推奨スクリプト
python scripts/backtest/backtest_standard.py

# 検証系
validate_*.py - バリデーション
verify_*.py - 検証
```

### analysis/ - 分析系
```bash
# よく使うスクリプト
analyze_*.py - 各種分析
compare_*.py - 比較分析
evaluate_*.py - 評価
```

### data_collection/ - データ収集系
```bash
# データ収集
fetch_*.py - データ取得
collect_*.py - データ収集
worker_*.py - ワーカー

# データ補完
import_*.py - インポート
fill_*.py - 補完
```

### maintenance/ - メンテナンス系
```bash
# ベンチマーク・設定管理
extract_current_config.py - 設定抽出・ステータス更新
track_performance_change.py - 変更追跡・履歴記録

# モデル学習
train_*.py - モデル学習
optimize_*.py - 最適化

# クリーンアップ
cleanup_*.py - クリーンアップ
```

### batch/ - バッチファイル
```bash
# Windows用バッチ
run_*.bat - 実行バッチ
setup_*.ps1 - PowerShellセットアップ
```

### _deprecated/ - 非推奨
- test_*.py - テストスクリプト（開発用）
- debug_*.py - デバッグスクリプト
- check_*.py - チェックスクリプト
- *_v2.py, *_v3.py - 旧バージョン

## 使用例

```bash
# ベンチマーク実行
python scripts/benchmark_prediction_system.py

# ベンチマーク比較
python scripts/benchmark_prediction_system.py --compare

# 知見検索
python scripts/search_knowledge.py "オッズ"

# 標準バックテスト
python scripts/backtest/backtest_standard.py

# 予測生成
python scripts/prediction/generate_predictions.py
```
