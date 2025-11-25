# 特徴量エンジニアリング設計

**作成日**: 2024-10-30
**目的**: Phase 3で使用する特徴量の設計

---

## 特徴量の分類

### 1. 選手関連特徴量

#### 1.1 基本情報
- `racer_number`: 選手登録番号
- `racer_rank`: 級別（A1, A2, B1, B2）
- `racer_age`: 年齢
- `racer_weight`: 体重
- `racer_home`: 所属支部

#### 1.2 成績指標
- `win_rate`: 勝率（全国）
- `second_rate`: 2連対率（全国）
- `third_rate`: 3連対率（全国）
- `local_win_rate`: 勝率（当地）
- `local_second_rate`: 2連対率（当地）
- `local_third_rate`: 3連対率（当地）

#### 1.3 スタート関連
- `avg_st`: 平均スタートタイミング
- `f_count`: フライング回数
- `l_count`: 出遅れ回数

#### 1.4 派生特徴量（追加）
- `experience_score`: 経験値スコア（レース出場回数から算出）
- `recent_form`: 直近の成績（過去10レースの平均着順）
- `venue_compatibility`: 当該競艇場での相性（過去成績）
- `class_advantage`: 級別による優位性スコア

---

### 2. モーター・ボート関連特徴量

#### 2.1 モーター
- `motor_number`: モーター番号
- `motor_second_rate`: モーター2連対率
- `motor_third_rate`: モーター3連対率

#### 2.2 ボート
- `boat_number`: ボート番号
- `boat_second_rate`: ボート2連対率
- `boat_third_rate`: ボート3連対率

#### 2.3 派生特徴量（追加）
- `motor_performance_score`: モーター総合性能スコア
- `boat_performance_score`: ボート総合性能スコア
- `equipment_advantage`: 機材優位性（モーター＋ボート）

---

### 3. レース条件関連特徴量

#### 3.1 基本情報
- `venue_code`: 競艇場コード
- `race_number`: レース番号（1R-12R）
- `race_date`: 日付
- `race_time`: 締切時刻

#### 3.2 枠番
- `pit_number`: 枠番（1-6）

#### 3.3 派生特徴量（追加）
- `pit_advantage`: 枠番による優位性（統計的優位性）
- `race_grade`: レースグレード（推定）
- `time_of_day`: 時間帯（午前/午後/ナイター）

---

### 4. 天候・水面関連特徴量（Phase 3で追加予定）

#### 4.1 気象条件
- `weather`: 天候
- `temperature`: 気温
- `wind_speed`: 風速
- `wind_direction`: 風向
- `wave_height`: 波高

#### 4.2 水面条件
- `water_temp`: 水温
- `tide`: 潮

---

### 5. 対戦関連特徴量（高度な特徴量）

#### 5.1 選手間の対戦成績
- `head_to_head_win_rate`: 対戦相手との勝率
- `head_to_head_count`: 対戦回数

#### 5.2 同レース内の相対評価
- `rank_in_race_by_win_rate`: レース内での勝率順位
- `rank_in_race_by_avg_st`: レース内でのST順位
- `rank_in_race_by_class`: レース内での級別順位

---

## 特徴量生成の優先順位

### Phase 3.1（最優先）
1. 選手基本情報（1.1, 1.2, 1.3）
2. モーター・ボート（2.1, 2.2）
3. レース条件（3.1, 3.2）
4. 枠番優位性（3.3.pit_advantage）

### Phase 3.2（中優先）
5. 選手派生特徴量（1.4）
6. 機材派生特徴量（2.3）
7. レース内相対評価（5.2）

### Phase 3.3（低優先）
8. 天候・水面（4）
9. 対戦成績（5.1）

---

## データ変換

### カテゴリカル変数のエンコーディング

#### One-Hot Encoding
- `racer_rank`: A1, A2, B1, B2 → 4次元ベクトル
- `venue_code`: 01-24 → 24次元ベクトル
- `pit_number`: 1-6 → 6次元ベクトル

#### Label Encoding
- `racer_home`: 支部 → 数値（1-N）

### 数値変数の正規化

#### StandardScaler
- `win_rate`, `second_rate`, `third_rate`
- `motor_second_rate`, `boat_second_rate`
- `avg_st`

#### MinMaxScaler
- `racer_age`: 0-1
- `racer_weight`: 0-1

---

## 特徴量選択

### 重要度評価手法
1. **相関分析**: 目的変数（着順）との相関係数
2. **Feature Importance**: ランダムフォレスト/XGBoostの特徴量重要度
3. **SHAP値**: モデル予測への寄与度

### 次元削減
- **PCA**: 主成分分析（必要に応じて）
- **特徴量選択**: 上位N個の重要な特徴量を選択

---

## 実装方針

### データパイプライン
```python
1. 生データ読み込み（SQL）
2. 欠損値処理
3. 特徴量生成
4. エンコーディング
5. 正規化
6. 特徴量選択
7. 訓練/テストデータ分割
```

### スクリプト構成
- `feature_generator.py`: 特徴量生成
- `feature_selector.py`: 特徴量選択
- `data_preprocessor.py`: 前処理パイプライン

---

## 次のステップ

1. ✅ 特徴量設計（このドキュメント）
2. 🔄 `feature_generator.py`の実装
3. 🔄 `data_preprocessor.py`の実装
4. データ探索による特徴量の妥当性検証
5. ベースラインモデルでの特徴量重要度評価
