# 次回セッション クイックスタート

**最終更新**: 2025-11-13 22:45

---

## 🏆 今すぐ読むべき情報

### 最重要な結論

**実験#007が新たな最推奨モデル！**

1. **実験#007: ベースライン8ヶ月学習版（最推奨）**
   - **AUC: 0.8473**（時系列分割版で最高！）
   - **的中率（0.8+）: 66.45%**
   - **的中率（0.9+）: 72.21%**
   - 特徴量: 30個（シンプル）
   - 学習データ: **39,771件（8ヶ月分）**
   - モデル: [stage2_baseline_8months.json](models/stage2_baseline_8months.json)

2. **データ量の重要性を実証**
   - 2ヶ月（9,881件）→ 8ヶ月（39,771件）
   - AUC: 0.8393 → 0.8473（+0.95%）
   - 的中率（0.8+）: 64.77% → 66.45%（+1.68pt）

3. **次の目標: AUC 0.85達成**
   - 実験#008で会場・級別特徴量を追加
   - データ量が十分なため、効果が大きい可能性

---

## 全実験の結果（一覧）

### 時系列分割版（信頼できる性能）

| 実験ID | 学習期間 | 学習データ数 | 特徴量数 | AUC | 的中率(0.8+) | 状態 |
|:---:|:---:|---:|:---:|:---:|:---:|:---:|
| #005 | 2ヶ月 | 9,881件 | 44 | 0.8322 | 66.85% | 会場・級別あり |
| #006 | 2ヶ月 | 9,881件 | 30 | 0.8393 | 64.77% | ベースライン |
| **#007** | **8ヶ月** | **39,771件** | 30 | **0.8473** | **66.45%** | **最推奨** ⭐ |

### ランダム分割版（過学習の可能性あり）

| 実験ID | 学習期間 | 特徴量数 | AUC | 的中率(0.8+) | 状態 |
|:---:|:---:|:---:|:---:|:---:|:---:|
| #001 | 3ヶ月 | 30 | 0.8551 | 77.87% | 要再検証 |
| #004 | 3ヶ月 | 44 | 0.8589 | 80.17% | **過学習確定** |

---

## 次にやるべきこと（優先順）

### 優先度：最高（即実施）

#### 1. 実験#008: 会場・級別8ヶ月学習版
```bash
# 目的: 実験#007に会場・級別特徴量を追加して最高性能を目指す
学習期間: 2023-10-01 〜 2024-05-31（8ヶ月）
テスト期間: 2024-06-01 〜 2024-06-30（1ヶ月）
特徴量: 44個（ベースライン30 + 会場・級別14）
学習データ: 39,771件

期待効果:
- AUC 0.85以上
- 的中率（0.8+）70%以上

実行コマンド:
python train_stage2_venue_grade_8months.py  # 新規作成が必要
```

#### 2. 実験#008: ベースライン3ヶ月時系列版
```bash
# 目的: 実験#001が過学習か確認
学習期間: 2024-04-01 〜 2024-06-30（3ヶ月）
テスト期間: 2024-07-01 〜 2024-07-31（1ヶ月）
特徴量: 30個

実行コマンド:
python train_stage2_baseline_3months_timeseries.py  # 新規作成が必要
```

### 優先度：高（1週間以内）

#### 3. 統計的有意性検定
```python
# 実験#005 vs #006の差が統計的に有意か確認
# ブートストラップ法でAUCの95%信頼区間を計算
```

#### 4. SHAP分析
```python
# 特徴量重要度の詳細分析
# 会場・級別特徴量の実際の寄与度を確認
python analyze_shap_values.py  # 既存スクリプト
```

---

## 重要なファイル

### モデルファイル
```
models/stage2_baseline_timeseries.json        # 実験#006（最推奨）
models/stage2_venue_grade_timeseries.json     # 実験#005（的中率優先）
models/stage2_baseline_3months.json           # 実験#001（要再検証）
```

### レポート
```
EXPERIMENTS_SUMMARY_REPORT.md                 # 全実験の総括（必読）
EXPERIMENT_006_REPORT.md                      # 実験#006詳細
EXPERIMENT_005_REPORT.md                      # 実験#005詳細
```

### スクリプト
```
train_stage2_baseline_timeseries.py           # 実験#006
train_stage2_venue_grade_timeseries.py        # 実験#005
```

---

## クイックコマンド

### 状況確認
```bash
# モデルファイル確認
ls -lh models/*.json

# レポート確認
ls -lh EXPERIMENT_*.md EXPERIMENTS_*.md

# データベース確認
python -c "import sqlite3; conn = sqlite3.connect('data/boatrace.db'); cur = conn.cursor(); print(cur.execute('SELECT MIN(race_date), MAX(race_date), COUNT(*) FROM race_results').fetchone())"
```

### 実験#007の作成（次回やること）
```bash
# train_stage2_baseline_timeseries.py をベースに作成
# 学習期間を2023-10-01から8ヶ月に変更
```

---

## 重要な技術的注意事項

### 1. 時系列分割を厳守
```python
# ✅ 良い例
df_train = df[df['race_date'] < '2024-06-01']
df_test = df[df['race_date'] >= '2024-06-01']

# ❌ 悪い例
train_test_split(df, test_size=0.2)
```

### 2. 統計は学習データのみから計算
```python
# ✅ 良い例
venue_stats = df_train_raw.groupby('venue_code')['is_win'].mean()
df_test['venue_win_rate'] = df_test['venue_code'].map(venue_stats)

# ❌ 悪い例
venue_stats = df_all.groupby('venue_code')['is_win'].mean()  # 未来データ混入
```

### 3. 特徴量は30〜40個程度が最適
- 44個 vs 30個で、30個の方がAUCが高い（実験#006）
- データ量が少ない場合、過学習のリスク

---

## 成功の定義

- **短期目標**: AUC 0.84以上 ✅（達成: 0.8393）
- **中期目標**: AUC 0.85以上、的中率（0.8+）70%以上（実験#007で挑戦）
- **長期目標**: 実運用で継続的にプラス収益

---

## 問い合わせ先

詳細は以下のレポートを参照:
- [EXPERIMENTS_SUMMARY_REPORT.md](EXPERIMENTS_SUMMARY_REPORT.md) - 全実験の総括
- [EXPERIMENT_006_REPORT.md](EXPERIMENT_006_REPORT.md) - 実験#006詳細
- [EXPERIMENT_005_REPORT.md](EXPERIMENT_005_REPORT.md) - 実験#005詳細

---

**次回セッション開始時は、まずこのファイルを確認してください！**
