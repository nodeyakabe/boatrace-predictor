# データ収集後の残タスク

**作成日**: 2025-12-03
**前提条件**: データ収集完了（目標2,000-3,000レース）

---

## 📋 実施順序

### ステップ1: データ確認 ✅

```bash
python check_db_schema.py
```

**確認項目**:
- [ ] race_detailsレース数が2,000以上
- [ ] 結果データ（results）が紐付いている
- [ ] 直前情報（is_published=1）が含まれている

**現在の状況**:
- race_details: 1,353レース（2025-12-03時点）
- 目標: 2,000-3,000レース

---

### ステップ2: LightGBMモデル再訓練 🔄

**理由**: ST×course交互作用など新特徴量を学習させるため

```bash
# 条件付きランクモデル訓練
python src/ml/train_conditional_models.py
```

**所要時間**: 30分-1時間

**新しく学習する特徴量**:
- ✅ ST×course交互作用（beforeinfo_scorer.py:207-210）
- ✅ tilt×outer_course交互作用
- ✅ tilt×wind交互作用
- ✅ 120種類以上の交互作用特徴（interaction_features.py）

**期待される改善**:
- 階層的確率モデル: P(1-2-3) = P(1) × P(2|1) × P(3|1,2)
- 三連単的中率の向上

---

### ステップ3: Optunaハイパーパラメータ最適化 🔧

**理由**: 新特徴量に対する最適なパラメータを探索

```bash
# ハイパーパラメータ最適化
python src/ml/optimization_loop.py
```

**所要時間**: 1-2時間

**最適化対象**:
- `learning_rate`: 学習率
- `num_leaves`: 葉の数
- `max_depth`: 木の深さ
- `min_child_samples`: 最小サンプル数
- `subsample`: サブサンプリング比率
- `colsample_bytree`: 特徴量サンプリング比率

**評価指標**:
- AUC（Area Under Curve）
- Accuracy（精度）
- Brier Score（確率予測精度）

---

### ステップ4: バックテストで性能検証 📊

**理由**: 実際の過去データで改善効果を測定

```bash
# Walk-forwardバックテスト
python test_walkforward.py

# A/Bテスト（動的統合 vs 固定比率）
python run_proper_ab_test.py
```

**所要時間**: 各30分-1時間

**検証項目**:
- [ ] 単勝的中率が向上したか（目標: 25%→29%）
- [ ] ROIが向上したか（目標: 75%→105%）
- [ ] Brier Scoreが改善したか（目標: ≤0.18）
- [ ] 動的統合が固定比率より優れているか

---

### ステップ5: スコアリング微調整（必要な場合のみ） 🎛️

**前提**: バックテスト結果で特定のスコア要素に問題が見つかった場合

**調整対象**（優先度順）:

#### 5.1 ST×course交互作用の係数調整

**現在の設定**: `beforeinfo_scorer.py:209`
```python
course_importance = 0.8 + (6 - course) * 0.1
```

**調整例**:
```python
# より強い効果
course_importance = 0.7 + (6 - course) * 0.15

# より弱い効果
course_importance = 0.85 + (6 - course) * 0.05
```

#### 5.2 動的w_beforeの閾値調整

**現在の設定**: `dynamic_integration.py:47-49`
```python
EXHIBITION_VARIANCE_THRESHOLD = 0.10  # 展示タイム分散
ST_VARIANCE_THRESHOLD = 0.05          # ST分散
ENTRY_CHANGE_THRESHOLD = 2            # 進入変更艇数
```

**調整例**: バックテストで「BEFORE重視が多すぎる/少なすぎる」場合

#### 5.3 スコア配分の微調整

**現在の設定**: `beforeinfo_scorer.py` Opus推奨値
```python
展示タイム: 25点満点
ST: 25点満点
進入: 20点満点
前走: 15点満点
チルト・風: 10点満点
部品・重量: 5点満点
```

**注意**: これはOpus AIが最適化した値なので、調整の優先度は**低い**

---

## 🎯 期待される最終効果

| 指標 | 現状 | Phase 1後 | Phase 2後 | Phase 3後 |
|------|------|-----------|-----------|-----------|
| **単勝的中率** | 25% | 26% | 27-28% | **29%** |
| **3着内的中率** | 60% | 62% | 65% | **68%** |
| **ROI** | 75% | 85% | 95% | **105%** |
| **Brier Score** | - | 0.22 | 0.20 | **0.18** |
| **三連単的中率** | - | - | 3% | **5%** |

---

## ⚠️ 注意事項

### データ量と精度の関係

| データ量 | モデル精度 | 推奨アクション |
|---------|----------|--------------|
| 1,000-1,500レース | 基本的 | もう少しデータ収集 |
| **2,000-3,000レース** | **十分** | **再訓練推奨** ✅ |
| 5,000レース以上 | 最高 | 定期的な再訓練 |

### 再訓練のタイミング

- **初回再訓練**: データ2,000-3,000レース到達時
- **定期再訓練**: 以降1,000レース増えるごと、または月1回

### Feature Flagsの設定

**注意**: 現在、Phase 2-3の多くの機能がFalseに戻されています

再訓練後、以下を有効化する必要があります：

```python
# config/feature_flags.py

'st_course_interaction': True,    # ST×course交互作用
'lightgbm_ranking': True,         # LightGBMランキングモデル
'interaction_features': True,     # 交互作用特徴量
'venue_specific_models': True,    # 会場別専用モデル
'hierarchical_predictor': True,   # 階層的条件確率モデル
```

---

## 📊 進捗チェックリスト

### データ収集フェーズ

- [ ] データ収集スクリプト実行中
- [ ] 目標2,000レース到達
- [ ] 結果データが紐付いている

### モデル再訓練フェーズ

- [ ] LightGBMモデル訓練完了
- [ ] Optunaパラメータ最適化完了
- [ ] モデルファイル保存確認（models/ディレクトリ）

### 性能検証フェーズ

- [ ] Walk-forwardバックテスト実行
- [ ] A/Bテスト実行
- [ ] 的中率・ROI測定
- [ ] Brier Score測定

### 本番適用フェーズ

- [ ] Feature Flags有効化
- [ ] 本番環境で試験運用（10%）
- [ ] 性能モニタリング
- [ ] 段階的展開（50%→100%）

---

## 🔧 トラブルシューティング

### Q1: モデル訓練がエラーになる

**原因**: データ不足、または特徴量に欠損値が多い

**対処法**:
```bash
# データの完全性をチェック
python src/analysis/data_coverage_checker.py

# 欠損値処理を確認
# src/features/feature_transforms.py
```

### Q2: バックテストで性能が悪化

**原因**: 過学習、またはハイパーパラメータ不適切

**対処法**:
1. Optunaで再最適化
2. 正則化パラメータ調整（`min_child_samples`増加）
3. Feature Flagsで段階的に機能を無効化して原因特定

### Q3: 予測時にエラーが出る

**原因**: モデルファイルが見つからない、または特徴量の次元不一致

**対処法**:
```bash
# モデルファイルの存在確認
ls models/

# モデルロード時のエラーログ確認
# src/prediction/hierarchical_predictor.py
```

---

## 📁 参考資料

- [phase1-3_implementation_complete.md](phase1-3_implementation_complete.md) - 実装詳細レポート
- [FINAL_IMPLEMENTATION_SUMMARY.md](../FINAL_IMPLEMENTATION_SUMMARY.md) - 実装完了サマリー
- [improvement_implementation_plan.md](improvement_implementation_plan.md) - Opusマスタープラン

---

## 📞 困ったときは

1. **ドキュメント確認**: 上記の参考資料を参照
2. **ログ確認**: エラーメッセージを詳細に読む
3. **Feature Flags無効化**: 問題の機能を一時的にFalseに
4. **Gitロールバック**: `git revert <commit_hash>`で前のバージョンに戻す

---

**作成日**: 2025-12-03
**最終更新**: 2025-12-03
**ステータス**: データ収集待機中 🔄
