# 新特徴量提案書

**作成日**: 2025-11-13
**目的**: 予測精度とROIの向上

---

## 📊 現在実装済みの特徴量（要約）

### 基本特徴量
- 選手情報: 級別、年齢、体重、勝率、連対率
- モーター・ボート: 2連率、3連率
- レース条件: 枠番、展示タイム、ST時間、チルト角度
- 気象情報: 気温、天候、風速、風向、水温、波高

### 派生特徴量
- 枠番ダミー、実際のコース、枠-コース差分
- レース内相対順位（展示タイム順位、ST順位、勝率順位）
- 年齢グループ
- **選手特徴量（新規追加済み）**:
  - 直近N戦平均着順（N=3,5,10）
  - 直近N戦勝率（N=3,5,10）
  - モーター直近2連率差分

---

## 💡 追加すべき新特徴量（優先度順）

### 🔴 優先度: 高

#### 1. **会場別成績（Venue-specific Performance）**

**根拠**: 競艇場ごとに特性が大きく異なる（水面の広さ、潮の影響、風の向きなど）

```python
# 実装案
'racer_venue_win_rate': 選手の特定会場での勝率
'racer_venue_avg_rank': 選手の特定会場での平均着順
'racer_venue_races': 選手の特定会場での出走回数
```

**期待効果**: AUC +0.02〜0.03, ROI +5〜8%

#### 2. **相対的モーター性能（Relative Motor Performance）**

**根拠**: モーター性能は絶対値よりも「そのレース内での相対的な良し悪し」が重要

```python
# 実装案
'motor_2rate_rank': レース内でのモーター2連率の順位（1-6）
'motor_2rate_percentile': レース内でのモーター2連率のパーセンタイル
'motor_vs_avg_diff': モーター2連率 - レース平均モーター2連率
```

**期待効果**: AUC +0.015〜0.02, ROI +3〜5%

#### 3. **コース取り予測（Course Prediction）**

**根拠**: 実際のコース（進入コース）は勝敗に極めて大きな影響を与える

```python
# 実装案
'expected_course': 過去の傾向から予測される進入コース
'pit_to_course_historical_prob': 枠番→コースの歴史的確率
'course_1_probability': 1コースを取る確率
```

**期待効果**: AUC +0.03〜0.05, ROI +8〜12%

---

### 🟡 優先度: 中

#### 4. **選手間の相対評価（Head-to-Head Features）**

**根拠**: 同じレース内での選手間の実力差が重要

```python
# 実装案
'win_rate_rank': レース内での勝率順位
'win_rate_diff_from_top': 1位選手との勝率差
'win_rate_diff_from_avg': レース平均勝率との差
```

**期待効果**: AUC +0.01〜0.015, ROI +2〜4%

#### 5. **連続出走の影響（Consecutive Race Effects）**

**根拠**: 同日内での連続出走は選手のコンディションに影響

```python
# 実装案
'is_consecutive_race': 同日2レース目以降かどうか
'races_today_count': その日の出走回数
'rest_time_from_prev_race': 前レースからの休憩時間
```

**期待効果**: AUC +0.005〜0.01, ROI +1〜2%

#### 6. **天候・水面条件の交互作用（Weather Interactions）**

**根拠**: 風の強さ×風向き、気温×水温など の組み合わせが重要

```python
# 実装案
'wind_strength_category': 風速カテゴリ（弱/中/強）
'temp_water_diff': 気温 - 水温
'adverse_weather': 悪天候フラグ（雨 かつ 強風）
```

**期待効果**: AUC +0.008〜0.012, ROI +1〜3%

---

### 🟢 優先度: 低（将来的に検討）

#### 7. **時系列パターン（Temporal Patterns）**

```python
'day_of_week': 曜日（土日は客層が異なる可能性）
'season': 季節（夏/冬での違い）
'hour_of_race': レース時刻（朝/昼/夜）
```

**期待効果**: AUC +0.003〜0.005, ROI +0.5〜1%

#### 8. **高次特徴量（Advanced Features）**

```python
'win_rate_motor_2rate_interaction': 勝率 × モーター2連率
'age_experience_score': 年齢 × 総出走回数
'pit_course_match_rate': 枠番=コース の一致率
```

**期待効果**: AUC +0.005〜0.008, ROI +1〜2%

---

## 🎯 実装優先順位と期待ROI改善

| 順位 | 特徴量カテゴリ | 実装難易度 | 期待ROI改善 | 総合スコア |
|------|---------------|-----------|------------|-----------|
| 1 | コース取り予測 | 中 | +8〜12% | ⭐⭐⭐⭐⭐ |
| 2 | 会場別成績 | 低 | +5〜8% | ⭐⭐⭐⭐⭐ |
| 3 | 相対的モーター性能 | 低 | +3〜5% | ⭐⭐⭐⭐ |
| 4 | 選手間相対評価 | 低 | +2〜4% | ⭐⭐⭐ |
| 5 | 連続出走の影響 | 中 | +1〜2% | ⭐⭐⭐ |
| 6 | 天候交互作用 | 低 | +1〜3% | ⭐⭐ |

**合計期待ROI改善**: +20〜34%（全て実装した場合）

---

## 📋 実装ロードマップ

### Phase 1（即時実装可能）
- [x] 選手特徴量（直近N戦成績）- **実装済み**
- [ ] 会場別成績
- [ ] 相対的モーター性能

**期待効果**: ROI +8〜13%

### Phase 2（中期）
- [ ] コース取り予測
- [ ] 選手間相対評価
- [ ] 連続出走の影響

**期待効果**: ROI +11〜18%（累積）

### Phase 3（長期）
- [ ] 天候交互作用
- [ ] 時系列パターン
- [ ] 高次特徴量

**期待効果**: ROI +13〜22%（累積）

---

## 🔬 検証方法

各特徴量追加後に以下を確認：

1. **単変量分析**: 特徴量と目的変数の相関
2. **特徴量重要度**: XGBoostのgain importanceで確認
3. **AUCスコア**: テストデータでの改善を確認
4. **バックテストROI**: 実際の投資戦略での改善を確認
5. **過学習チェック**: Train/Validのスコア差を監視

---

## 📝 実装例：会場別成績

```python
def add_venue_specific_features(df, conn):
    """
    会場別成績の特徴量を追加

    Args:
        df: DataFram (racer_number, venue_code, race_date を含む)
        conn: DB接続

    Returns:
        追加された特徴量を含むDataFrame
    """
    df = df.copy()

    racer_venue_stats = []

    for idx, row in df.iterrows():
        racer_number = row['racer_number']
        venue_code = row['venue_code']
        race_date = row['race_date']

        # その会場での過去成績を取得（そのレースより前）
        query = """
            SELECT
                COUNT(*) as races,
                AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as win_rate,
                AVG(CAST(res.rank AS FLOAT)) as avg_rank
            FROM results res
            JOIN races r ON res.race_id = r.id
            JOIN entries e ON res.race_id = e.race_id AND res.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND r.venue_code = ?
              AND r.race_date < ?
              AND res.rank IN ('1', '2', '3', '4', '5', '6')
        """

        cursor = conn.execute(query, (racer_number, venue_code, race_date))
        result = cursor.fetchone()

        stats = {
            'racer_venue_races': result[0] if result[0] else 0,
            'racer_venue_win_rate': result[1] if result[1] else 0.0,
            'racer_venue_avg_rank': result[2] if result[2] else 3.5
        }

        racer_venue_stats.append(stats)

    df_stats = pd.DataFrame(racer_venue_stats, index=df.index)
    df = pd.concat([df, df_stats], axis=1)

    return df
```

---

## ⚠️ 注意事項

1. **データリーケージに注意**: 特徴量は「そのレースより前」のデータのみ使用
2. **欠損値処理**: 新選手や初出場会場の場合のデフォルト値を設定
3. **計算コスト**: 特徴量追加で学習時間が増加する可能性
4. **過学習リスク**: 特徴量が多すぎると過学習のリスク

---

## 📈 期待される最終成果

**現状（選手特徴量のみ追加）**:
- AUC: 0.70 → 0.73〜0.75（目標）
- ROI: 100% → 110〜115%（目標）

**Phase 1完了後**:
- AUC: 0.75〜0.78
- ROI: 118〜123%

**全Phase完了後**:
- AUC: 0.78〜0.82
- ROI: 120〜134%

---

**次のアクション**:
1. Phase 1の特徴量を実装
2. 各特徴量の効果を個別に検証
3. 最も効果の高い特徴量を本番モデルに統合
