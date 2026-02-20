# V2モデル劣化問題 - 調査報告書

**作成日**: 2025-12-15
**ステータス**: 解決済み

## 1. 問題の概要

モデル改善（V2）を実施したところ、V1（改善前）よりも大幅に性能が悪化する問題が発生しました。

### 報告された症状
- 1着的中率: 63.84% → 61.69% (-2.15pt)
- 3連単的中率: 18.68% → 6.85% (-11.83pt)
- 推定収支影響: -264,000円

## 2. 調査結果

### 2.1 根本原因

**2つの異なるモデル体系が混在しており、V2として使用されていたモデルのAUCが元々低かった**

プロジェクトには2つの異なるモデル体系が存在していました：

| 体系 | ファイル形式 | 使用クラス | 用途 |
|------|-------------|-----------|------|
| **体系A** | `.joblib` (LightGBM) | TrifectaCalculator, TrifectaCalculatorOptimized | HierarchicalPredictorで使用 |
| **体系B** | `.json` (XGBoost) | ConditionalRankModel | 独立した予測用（未統合） |

### 2.2 AUCスコアの比較

| モデル | Stage1 AUC | Stage2 AUC | Stage3 AUC |
|--------|-----------|-----------|-----------|
| 体系A V1 (conditional_meta.json) | 0.9010 | **0.7423** | **0.6675** |
| 体系A V2 (conditional_meta_v2_20251209) | 0.8730 | **0.6935** | **0.6278** |

**V2のAUCがV1より低い:**
- Stage2: 0.7423 → 0.6935 (-4.9pt)
- Stage3: 0.6675 → 0.6278 (-4.0pt)

### 2.3 問題の発生メカニズム

```
HierarchicalPredictor(use_v2=True)
    ↓
TrifectaCalculatorOptimized._load_v2_models()
    ↓
conditional_stage*_v2_20251209_*.joblib を読み込み
    ↓
このモデルのAUCが元々低い → 予測精度が劣化
```

### 2.4 検証結果

10レースでの簡易テスト:

| 指標 | V1 | V2 (問題モデル) |
|------|-----|----------------|
| 1着的中 | 6/10 | 5/10 |
| 3連単的中 | 2/10 | **0/10** |

## 3. 実施した対策

### 3.1 即時対策

問題のV2モデルファイルを無効化フォルダに移動:

```bash
models/deprecated_v2_20251209/
├── conditional_stage1_v2_20251209_112052.joblib
├── conditional_stage2_v2_20251209_112052.joblib
├── conditional_stage3_v2_20251209_112052.joblib
└── conditional_meta_v2_20251209_112052.json
```

これにより、`use_v2=True`を指定しても自動的にV1にフォールバックします。

### 3.2 改善後の検証

| 指標 | V1 | V2 (フォールバック後) |
|------|-----|---------------------|
| 1着的中 | 6/10 | 6/10 |
| 3連単的中 | 2/10 | 2/10 |

V1と同等の性能が復元されました。

## 4. 今後の推奨事項

### 4.1 短期

1. **V2フラグの使用を避ける**: `use_v2=False` をデフォルトとして維持
2. **compare_model_versions.py の更新**: V2評価を無効化するか、警告を追加

### 4.2 中長期

1. **体系Bモデルの統合検討**:
   - `conditional_rank_v2_20251215_*.json` (XGBoost) をTrifectaCalculatorで使用可能にする
   - このモデルは別の特徴量セットを使用しており、潜在的に高性能の可能性あり

2. **モデル管理の改善**:
   - モデルバージョンとメタデータの一貫した命名規則
   - AUCスコアの自動検証（閾値以下なら警告）

3. **V2モデルの再学習**:
   - Stage2/Stage3のAUC劣化原因を特定
   - 特徴量選択、ハイパーパラメータの見直し
   - 学習データ期間の最適化

## 5. 関連ファイル

| ファイル | 説明 |
|---------|------|
| `src/prediction/trifecta_calculator.py` | V1/V2モデル読み込みロジック |
| `src/prediction/trifecta_calculator_optimized.py` | 最適化版（同上） |
| `src/prediction/hierarchical_predictor.py` | 統合予測パイプライン |
| `scripts/compare_model_versions.py` | V1/V2比較スクリプト |
| `scripts/diagnose_v2_issue.py` | 診断スクリプト（新規作成） |
| `models/deprecated_v2_20251209/` | 無効化されたV2モデル |

## 6. 結論

V2モデルの劣化は、**使用されていたV2モデル（体系A V2）のAUCが元々V1より低かった**ことが原因でした。

問題のモデルファイルを無効化することで、V1の性能が復元されました。今後は新しいV2モデルを作成する際に、必ずAUCスコアを確認し、V1を上回る場合のみデプロイする運用を推奨します。
