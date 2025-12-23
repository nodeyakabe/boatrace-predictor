# モデル学習ガイド

**最終更新**: 2025-12-07

---

## 概要

競艇予想システムには2種類のモデルがあります。

| モデル | 目的 | 出力 |
|--------|------|------|
| **Stage1** | 「予想しやすいレース」を判定 | buy_score（0〜1） |
| **Stage2** | 各艇の勝率を予測 | 勝率（0〜1） |

---

## Stage1モデル（レース選別）

### 何をするモデル？
- **目的**: 予想が当たりやすいレースを見つける
- **出力**: `buy_score`（0〜1の数値）
  - 高い = 予想しやすい → 購入推奨
  - 低い = 波乱が多い → 見送り推奨

### 判定に使う情報
1. **データの充実度**: 展示タイム・選手成績・モーター性能がそろっているか
2. **レースの安定性**: 実力差が明確か、混戦か
3. **波乱の起きにくさ**: 1コースが強いか、荒れやすい条件か

### CLI学習コマンド
```bash
python scripts/train_stage1_model.py --start-date 2025-06-01 --end-date 2025-11-30
```

### 主なパラメータ
| パラメータ | 意味 | 推奨値 |
|-----------|------|--------|
| max_depth | 木の深さ | 6 |
| learning_rate | 学習速度 | 0.1 |
| n_estimators | 木の数 | 200 |

---

## Stage2モデル（勝率予測）

### 何をするモデル？
- **目的**: 各艇の1着確率を予測
- **出力**: 6艇それぞれの勝率（合計100%）

### 予測に使う情報
1. **選手の実力**: 全国勝率、当地勝率、級別（A1/A2/B1/B2）
2. **機材の性能**: モーター2連率、ボート2連率
3. **コースの有利度**: 1コース〜6コースの統計的な勝ちやすさ
4. **直前情報**: 展示タイム、スタートタイミング

### CLI学習コマンド
```bash
# 基本の学習
python scripts/train_all_models.py

# 期間指定
python tests/train_stage2_with_racer_features.py --start-date 2025-01-01 --end-date 2025-11-30
```

### 主なパラメータ
| パラメータ | 意味 | 推奨値 |
|-----------|------|--------|
| max_depth | 木の深さ | 6 |
| learning_rate | 学習速度 | 0.05 |
| n_estimators | 木の数 | 1000 |
| early_stopping | 過学習防止 | 50 |

---

## 確率校正（Calibration）

### 何をするもの？
- モデルの「予測確率」を「実際の勝率」に近づける補正
- 例: 予測60%の艇が実際は50%しか勝たない → 50%に補正

### なぜ必要？
- 期待値計算が正確になる
- 賭け金配分（Kelly基準）が適切になる

### CLI実行コマンド
```bash
python scripts/calibrate_model.py --method platt
```

### 校正方法
| 方法 | 特徴 |
|------|------|
| **Platt Scaling** | 高速、少量データでも有効（推奨） |
| **Isotonic** | 大量データで精度が高い |

---

## モデルファイルの場所

```
models/
├── race_selector.json          # Stage1モデル
├── race_selector.meta.json     # Stage1のメタ情報
├── stage2_xgboost.json         # Stage2モデル（XGBoost）
├── stage2_lightgbm.txt         # Stage2モデル（LightGBM）
└── *_calibrator.pkl            # 確率校正モデル
```

---

## 学習の流れ

```
1. データ準備（過去6ヶ月分推奨）
      ↓
2. Stage1学習（レース選別）
      ↓
3. Stage2学習（勝率予測）
      ↓
4. 確率校正（オプション）
      ↓
5. バックテストで精度確認
```

---

## バックテスト

学習したモデルの精度を過去データで検証します。

```bash
# 基本のバックテスト
python tests/backtest_with_racer_features.py

# 期間指定
python scripts/walkforward_backtest.py --start-date 2025-11-01 --end-date 2025-11-30
```

### 評価指標
| 指標 | 目安 |
|------|------|
| 1着的中率 | 50%以上で優秀 |
| AUC | 0.85以上で優秀 |
| 回収率 | 75%以上で運用可能 |

---

## よくある質問

### Q: どのくらいの頻度で再学習が必要？
**A**: 月1回程度。選手の調子やモーターの入れ替えがあるため。

### Q: 学習データはどのくらい必要？
**A**: 最低3ヶ月、推奨6ヶ月。古すぎるデータは逆効果。

### Q: UIとCLIどちらを使うべき？
**A**: 基本はCLI推奨。UIはパラメータ確認や簡易実行向け。

---

## 関連ファイル

- [train_stage1_model.py](../scripts/train_stage1_model.py) - Stage1学習スクリプト
- [train_all_models.py](../scripts/train_all_models.py) - Stage2学習スクリプト
- [backtest_with_racer_features.py](../tests/backtest_with_racer_features.py) - バックテスト
- [model_training.py](../ui/components/model_training.py) - UI実装
