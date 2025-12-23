# システム概要（1ページサマリー）

**最終更新**: 2025-12-15

---

## システム全体図

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           競艇予想システム                                │
│                                                                          │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐  │
│  │ データ収集  │ -> │ 予測エンジン │ -> │ ベッティング │ -> │  出力/UI   │  │
│  │  Scrapers  │    │RacePredictor│    │  Evaluator  │    │ Streamlit  │  │
│  └────────────┘    └────────────┘    └────────────┘    └────────────┘  │
│         │                │                  │                           │
│         v                v                  v                           │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐                    │
│  │  SQLite DB │    │ ML Models  │    │ 戦略B設定  │                    │
│  │boatrace.db │    │ (LightGBM) │    │ パターンH  │                    │
│  └────────────┘    └────────────┘    └────────────┘                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 本番システム構成

| 役割 | ファイル | 説明 |
|-----|---------|------|
| **UI** | `ui/app.py` | Streamlit WebUI（メインエントリーポイント） |
| **予測エンジン** | `src/analysis/race_predictor.py` | ルールベース+ML統合予測 |
| **MLモデル** | `models/conditional_stage*.joblib` | LightGBM V1（本番） |
| **ベッティング** | `src/betting/bet_target_evaluator.py` | 戦略B + パターンH |
| **日次スクリプト** | `scripts/run_daily_betting_pattern_h.py` | 日次ベッティング分析 |

---

## モデル体系（早見表）

| 体系 | ファイル | AUC Stage2 | 状態 |
|-----|---------|-----------|------|
| **V1 (本番)** | `conditional_stage*.joblib` | **0.7423** | 使用中 |
| V2 (実験) | `conditional_rank_v2_*.json` | - | 実験中 |
| ~~V2 (非推奨)~~ | `deprecated_v2_20251209/*` | 0.6935 | 使用禁止 |

**重要**: `use_v2=False` がデフォルト（V1使用）

---

## ベッティング設定（早見表）

### 購入条件（戦略B）

| 信頼度 | 級別 | オッズ | 賭け金 |
|-------|-----|-------|-------|
| C | B1 | 30-40倍 | 300円 |
| C | A1 | 30-40倍 | 300円 |
| D | B1 | 40-50倍 | 300円 |
| D | A1 | 40-50倍 | 300円 |
| D | A2 | 20-30倍 | 300円 |

### パターンH（複数点買い）

```
1-2-3: 200円  # 予測そのまま
1-2-4: 100円  # 3着を4位に変更
1-2-5: 100円  # 3着を5位に変更
合計: 400円/レース
```

---

## 主要ファイル一覧

### 予測系
```
src/analysis/race_predictor.py      # メイン予測エンジン
src/prediction/hierarchical_predictor.py  # 階層的確率モデル
src/ml/conditional_rank_model.py    # 条件付き着順予測
```

### ベッティング系
```
src/betting/bet_target_evaluator.py # 購入判定
src/betting/multi_bet_generator.py  # 複数点買い
src/betting/venue_course_adjuster.py # 会場コース調整
```

### 設定
```
config/model_config.py              # モデル設定（新規）
config/settings.py                  # 基本設定
config/venue_wind_adjustments.py    # 風速・会場調整
```

### ユーティリティ
```
src/utils/model_loader.py           # 統一モデルローダー（新規）
src/utils/job_manager.py            # ジョブ管理
```

---

## クイックリファレンス

### UI起動
```bash
cd ui && python -m streamlit run app.py
```

### 日次ベッティング分析
```bash
python scripts/run_daily_betting_pattern_h.py
```

### モデル学習
```bash
python scripts/train_conditional_models.py
```

### モデル検証
```bash
python scripts/validate_model_update.py --new-model models/new_meta.json
```

### バックテスト
```bash
python scripts/backtest_pattern_h_with_venue_course_adjustment.py
```

### 現在のモデルAUC確認
```bash
python -c "
import json
with open('models/conditional_meta.json') as f:
    meta = json.load(f)
print('Stage2 AUC:', meta['metrics']['stage2']['cv_auc_mean'])
print('Stage3 AUC:', meta['metrics']['stage3']['cv_auc_mean'])
"
```

---

## AUC基準値

| Stage | 最低基準 | 現行値 |
|-------|---------|-------|
| Stage1 | 0.85 | **0.9010** |
| Stage2 | 0.72 | **0.7423** |
| Stage3 | 0.65 | **0.6675** |

---

## ドキュメントリンク

| ドキュメント | 内容 |
|------------|------|
| [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) | システム全体構成、依存関係 |
| [MODEL_MANAGEMENT.md](MODEL_MANAGEMENT.md) | モデル管理、更新手順 |
| [PREDICTION_LOGIC.md](PREDICTION_LOGIC.md) | 予測ロジック詳細 |
| [DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md) | 開発ワークフロー |
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | データベース構造 |
| [残タスク一覧.md](残タスク一覧.md) | 残タスク |
| [betting_implementation_status.md](betting_implementation_status.md) | 戦略実装状況 |

---

## 連絡先・問い合わせ

- 技術的な質問: Claude Code（このシステムを構築）
- ドキュメント更新: docs/ 配下のファイルを編集

---

**このドキュメントは 2025-12-15 に作成されました。**
