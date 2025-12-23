# モデル管理ガイド

**最終更新**: 2025-12-15
**ドキュメント管理者**: Claude Code

---

## 1. モデル体系

### 1.1 現在のモデル一覧

| 体系 | バージョン | ファイル | AUC (Stage2) | AUC (Stage3) | 状態 |
|-----|-----------|---------|-------------|-------------|------|
| **体系A (LightGBM)** | V1 | `conditional_stage*.joblib` | **0.7423** | **0.6675** | **本番使用中** |
| 体系B (XGBoost) | V1 | `conditional_rank_v1_*.json` | - | - | 予備 |
| 体系B (XGBoost) | V2 | `conditional_rank_v2_20251215_*.json` | - | - | 実験中 |
| ~~体系A (LightGBM)~~ | ~~V2~~ | `deprecated_v2_20251209/*` | 0.6935 | 0.6278 | **非推奨** |

### 1.2 本番モデル詳細

#### 体系A V1 (本番使用中)

```
models/
├── conditional_stage1.joblib    # 1着予測モデル (LightGBM)
├── conditional_stage2.joblib    # 2着予測モデル (LightGBM)
├── conditional_stage3.joblib    # 3着予測モデル (LightGBM)
└── conditional_meta.json        # メタ情報
```

**メタ情報 (`conditional_meta.json`)**:
```json
{
  "metrics": {
    "stage1": {"cv_auc_mean": 0.9010, "n_features": 17},
    "stage2": {"cv_auc_mean": 0.7423, "n_features": 51},
    "stage3": {"cv_auc_mean": 0.6675, "n_features": 85}
  },
  "created_at": "2025-12-04T14:10:38"
}
```

**使用方法**:
```python
from src.prediction.hierarchical_predictor import HierarchicalPredictor

predictor = HierarchicalPredictor(
    db_path='data/boatrace.db',
    model_dir='models',
    use_v2=False  # V1を使用（デフォルト）
)
```

### 1.3 非推奨モデル

#### deprecated_v2_20251209 (使用禁止)

**非推奨の理由**:
- AUC Stage2: 0.6935 (V1より **-4.88pt**)
- AUC Stage3: 0.6278 (V1より **-3.97pt**)
- バックテストで性能劣化を確認

**移動日**: 2025-12-15
**移動先**: `models/deprecated_v2_20251209/`

---

## 2. モデル更新手順

### 2.1 新モデル学習前のチェックリスト

```bash
# 1. 既存モデルのAUCを確認
cat models/conditional_meta.json | python -m json.tool

# 2. 既存の改善実装を確認（重複防止）
grep -r "改善" src/ml/ docs/
git log --oneline --grep="改善" | head -20

# 3. 現在のモデル読み込み設定を確認
grep -r "use_v2" src/prediction/
```

**確認事項チェックリスト**:
- [ ] 現在のAUC基準値を確認した（Stage2 >= 0.7423, Stage3 >= 0.6675）
- [ ] 類似の改善が既に実装されていないか確認した
- [ ] 学習データ期間を決定した（推奨: 2020-2025年）
- [ ] クロスバリデーション設定を決定した（推奨: TimeSeriesSplit(5)）

### 2.2 学習実行

```bash
# 条件付きモデルの学習
python scripts/train_conditional_models.py

# または、既存のV1と比較しながら学習
python src/ml/train_conditional_models.py --compare-v1
```

**学習スクリプトの推奨設定**:
```python
# scripts/train_conditional_models.py
params = {
    'objective': 'binary:logistic',
    'eval_metric': 'auc',
    'max_depth': 6,
    'learning_rate': 0.05,
    'n_estimators': 500,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'min_child_weight': 3,
    'gamma': 0.1,
    'random_state': 42,
    'n_jobs': -1,
}
```

### 2.3 学習後の検証（必須）

```bash
# AUC確認
python -c "
import json
with open('models/conditional_meta.json') as f:
    meta = json.load(f)
print('Stage2 AUC:', meta['metrics']['stage2']['cv_auc_mean'])
print('Stage3 AUC:', meta['metrics']['stage3']['cv_auc_mean'])
"

# バックテスト実行（2024年11月データ）
python scripts/backtest_pattern_h_with_venue_course_adjustment.py
```

**検証チェックリスト**:
- [ ] Stage2 AUC >= 0.7423（現行基準）
- [ ] Stage3 AUC >= 0.6675（現行基準）
- [ ] バックテストROI >= 129.9%（現行基準）
- [ ] 3連単的中率が低下していないか確認

### 2.4 本番適用手順

```bash
# 1. 旧モデルをバックアップ
mkdir -p models/backup_$(date +%Y%m%d)
cp models/conditional_stage*.joblib models/backup_$(date +%Y%m%d)/
cp models/conditional_meta.json models/backup_$(date +%Y%m%d)/

# 2. 新モデルファイルを適切な名前でコピー
cp models/new_conditional_stage1.joblib models/conditional_stage1.joblib
cp models/new_conditional_stage2.joblib models/conditional_stage2.joblib
cp models/new_conditional_stage3.joblib models/conditional_stage3.joblib
cp models/new_conditional_meta.json models/conditional_meta.json

# 3. モデル読み込みテスト
python -c "
from src.prediction.hierarchical_predictor import HierarchicalPredictor
p = HierarchicalPredictor('data/boatrace.db', 'models', use_v2=False)
p.load_models()
print('Model loaded successfully')
"

# 4. このドキュメントを更新
# - 「現在のモデル一覧」セクションを更新
# - 変更履歴に記載
```

---

## 3. モデル命名規則

### 3.1 標準命名規則

```
{model_type}_{stage}_{version}_{timestamp}.{ext}
```

**例**:
- `conditional_stage1.joblib` - 本番モデル（無印は最新）
- `conditional_stage2_v2_20251215_120000.joblib` - V2版、2025/12/15 12:00:00作成
- `conditional_rank_v1_first.json` - XGBoost版V1、1着モデル

### 3.2 バージョン管理

| バージョン | 説明 | 命名例 |
|-----------|------|-------|
| 無印 | 本番使用中の最新版 | `conditional_stage1.joblib` |
| v1 | 初期安定版 | `conditional_rank_v1_first.json` |
| v2 | 改善版（要検証） | `conditional_stage1_v2_*.joblib` |
| deprecated | 非推奨 | `deprecated_v2_20251209/` |

### 3.3 メタ情報ファイル

必ずメタ情報ファイル（`*.meta.json` or `*_meta.json`）を作成:

```json
{
  "version": "v1",
  "created_at": "2025-12-15T12:00:00",
  "training_period": {
    "start": "2020-01-01",
    "end": "2025-12-31"
  },
  "feature_names": {
    "stage1": ["win_rate", "second_rate", ...],
    "stage2": ["win_rate", ..., "first_place_win_rate", ...],
    "stage3": [...]
  },
  "metrics": {
    "stage1": {"cv_auc_mean": 0.90, "n_features": 17},
    "stage2": {"cv_auc_mean": 0.74, "n_features": 51},
    "stage3": {"cv_auc_mean": 0.67, "n_features": 85}
  },
  "improvements": "改善内容の説明"
}
```

---

## 4. AUC基準値

### 4.1 最低基準（これを下回ったら却下）

| Stage | 最低AUC | 現行AUC | 根拠 |
|-------|--------|--------|------|
| Stage1 | 0.85 | 0.9010 | 1着予測は高精度必須 |
| Stage2 | **0.72** | **0.7423** | 三連単的中に直結 |
| Stage3 | **0.65** | **0.6675** | 三連単的中に直結 |

### 4.2 改善目標（これを超えたら適用検討）

| Stage | 改善閾値 | 説明 |
|-------|---------|------|
| Stage2 | 0.7523 (+1pt) | 1pt以上改善で適用検討 |
| Stage3 | 0.6775 (+1pt) | 1pt以上改善で適用検討 |

---

## 5. 禁止事項

### 5.1 絶対にやってはいけないこと

| 禁止事項 | 理由 | 代替策 |
|---------|------|-------|
| AUC未確認でのモデル差し替え | 性能劣化の可能性 | 必ずAUC確認後に適用 |
| バックテスト未実施での本番適用 | ROI低下の可能性 | 必ずバックテスト実施 |
| 旧モデル削除 | ロールバック不可 | `backup_YYYYMMDD/` にバックアップ |
| 命名規則無視 | 管理混乱 | 標準命名規則に従う |
| 重複改善の実装 | 開発時間の無駄 | 既存実装を事前確認 |

### 5.2 やる前に確認すべきこと

```bash
# 重複改善チェック
grep -r "追加した改善内容のキーワード" src/ docs/

# 既存モデルとの比較
python scripts/compare_model_versions.py

# Git履歴確認
git log --oneline --all --grep="model" | head -20
```

---

## 6. トラブルシューティング

### 6.1 モデル性能劣化時の対応

```bash
# 1. 現在のモデル性能確認
python -c "
from src.prediction.hierarchical_predictor import HierarchicalPredictor
p = HierarchicalPredictor('data/boatrace.db', 'models', use_v2=False)
p.load_models()
# テスト予測実行
"

# 2. バックアップからロールバック
cp models/backup_YYYYMMDD/conditional_stage*.joblib models/
cp models/backup_YYYYMMDD/conditional_meta.json models/

# 3. 動作確認
python scripts/run_daily_betting_pattern_h.py --dry-run
```

### 6.2 モデル読み込みエラー

**症状**: `FileNotFoundError` または `ValueError`

**確認手順**:
```bash
# ファイル存在確認
ls -la models/conditional_*.joblib
ls -la models/conditional_meta.json

# メタ情報の整合性確認
python -c "
import json
with open('models/conditional_meta.json') as f:
    meta = json.load(f)
print('feature_names keys:', list(meta.get('feature_names', {}).keys()))
"
```

### 6.3 AUCが突然低下した場合

**確認事項**:
1. 学習データの期間が適切か
2. 欠損値処理が正しいか
3. 特徴量の順序が一致しているか

```bash
# 特徴量の確認
python -c "
import json
with open('models/conditional_meta.json') as f:
    meta = json.load(f)
for stage, features in meta.get('feature_names', {}).items():
    print(f'{stage}: {len(features)} features')
"
```

---

## 7. 変更履歴

| 日付 | バージョン | 変更内容 | AUC Stage2 | 担当者 |
|-----|-----------|---------|-----------|--------|
| 2025-12-15 | V2実験 | 相対特徴量追加（XGBoost） | - | Claude |
| 2025-12-09 | V2（非推奨） | 予測値条件付き特徴量 | 0.6935 | Claude |
| 2025-12-04 | V1（本番） | 初期安定版 | **0.7423** | Claude |
| 2025-11-17 | V0 | 初期モデル（XGBoost） | - | - |

---

## 関連ドキュメント

- [システムアーキテクチャ](SYSTEM_ARCHITECTURE.md)
- [予測ロジック詳細](PREDICTION_LOGIC.md)
- [開発ワークフロー](DEVELOPMENT_WORKFLOW.md)
- [V2モデル劣化レポート](V2_MODEL_DEGRADATION_REPORT.md) ※存在する場合
