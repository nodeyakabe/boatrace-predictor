# スコアリングロジック改善タスク

## 🚨 緊急課題

**現状:** 予測の79%がE判定（信頼度最低）
- 平均スコア: 33.8点（E判定レベル）
- A判定: 0件、B判定: 4件のみ

**根本原因:** スコアリングロジック自体が低スコアを生成している

---

## Phase 1: 現状分析スクリプトの作成

### タスク1.1 各スコア要素の分布分析
**ファイル:** `analyze_score_components.py`

```python
"""
各スコア要素の実際の値と分布を分析

- コーススコア: 実際の値範囲、平均値
- 選手スコア: 実際の値範囲、平均値
- モータースコア: 実際の値範囲、平均値
- 決まり手スコア: 実際の値範囲、平均値
- グレードスコア: 実際の値範囲、平均値

各要素が理論上の最大値（35点、35点、20点、5点、5点）に
どれくらい到達しているかを確認
"""
```

**期待される発見:**
- どの要素が特に低いか
- 正規化が不足している要素の特定

### タスク1.2 的中率と各要素の相関分析
**ファイル:** `analyze_accuracy_by_factor.py`

```python
"""
過去データで以下を分析:

1. 各スコア要素と的中率の相関
   - コーススコアが高いと的中率も高いか？
   - 選手スコアが高いと的中率も高いか？

2. 現在の重み配分の妥当性
   - コース35%, 選手35%は適切か？

3. 相互作用の分析
   - コースと選手の組み合わせ効果
"""
```

**期待される発見:**
- 実際に的中に寄与している要素
- 過大/過小評価されている要素

---

## Phase 2: スコア算出ロジックの改善

### タスク2.1 コーススコアの正規化
**ファイル:** `src/analysis/race_predictor.py`
**関数:** `calculate_course_score()` (60-100行目)

**現状の問題:**
```python
# 1号艇の例
win_rate = 0.55  # 55%
score = win_rate * course_weight  # 0.55 × 35 = 19.25点

# 35点満点なのに19点しか取れない
```

**改善案1: 会場内での相対評価**
```python
# その会場での最大勝率を基準に正規化
max_win_rate = max(course_stats.values(), key=lambda x: x['win_rate'])['win_rate']
normalized_rate = win_rate / max_win_rate
score = normalized_rate * course_weight

# 1号艇(0.55) ÷ 1号艇最大(0.55) = 1.0 → 35点満点
```

**改善案2: 全国平均からの偏差**
```python
# 全国平均との差を評価
national_avg = {1: 0.55, 2: 0.14, 3: 0.12, 4: 0.10, 5: 0.06, 6: 0.03}
deviation = (win_rate - national_avg[course]) / national_avg[course]
score = (1.0 + deviation) * course_weight * base_multiplier
```

**改善案3: シグモイド関数で正規化**
```python
import math

def sigmoid_normalize(win_rate, midpoint=0.30, steepness=10):
    """
    勝率をシグモイド関数で0-1に正規化

    midpoint: 50%スコアとなる勝率（0.30 = 30%）
    steepness: 曲線の急峻さ
    """
    x = (win_rate - midpoint) * steepness
    return 1 / (1 + math.exp(-x))

normalized = sigmoid_normalize(win_rate)
score = normalized * course_weight
```

### タスク2.2 選手スコアの正規化
**ファイル:** `src/analysis/race_predictor.py`
**関数:** `calculate_racer_score()` (要確認)

**改善方針:**
- レース内の6選手を相対評価
- 最上位選手 = 35点満点
- 最下位選手 = 5点程度（0点は避ける）

**実装案:**
```python
def normalize_racer_scores_in_race(racers_data):
    """
    レース内の選手を相対評価

    Args:
        racers_data: [{racer_id, win_rate, ...}, ...]

    Returns:
        {racer_id: normalized_score}
    """
    win_rates = [r['win_rate'] for r in racers_data]
    max_rate = max(win_rates)
    min_rate = min(win_rates)

    # 正規化（min=0.1, max=1.0の範囲）
    normalized = {}
    for racer in racers_data:
        rate = racer['win_rate']
        if max_rate == min_rate:
            norm = 0.5  # 全員同じ場合
        else:
            norm = 0.1 + 0.9 * (rate - min_rate) / (max_rate - min_rate)

        normalized[racer['racer_id']] = norm * 35.0  # racer_weight=35

    return normalized
```

### タスク2.3 モータースコアの正規化
**ファイル:** `src/analysis/motor_analyzer.py` (要確認)

**改善方針:**
- 同一会場内での相対評価
- モーター勝率の分布を考慮

**実装案:**
```python
def normalize_motor_scores_at_venue(motors_data, venue_code):
    """
    会場内のモーターを相対評価

    同一会場の全モーターの勝率分布を取得し、
    偏差値的な評価を行う
    """
    # 会場内の全モーター勝率を取得
    venue_motors = get_all_motors_at_venue(venue_code)
    all_rates = [m['win_rate'] for m in venue_motors]

    mean = statistics.mean(all_rates)
    std = statistics.stdev(all_rates) if len(all_rates) > 1 else 0.1

    normalized = {}
    for motor in motors_data:
        rate = motor['win_rate']
        # 偏差値 = 50 + 10 * (値 - 平均) / 標準偏差
        deviation_score = 50 + 10 * (rate - mean) / std

        # 偏差値を0-1に変換（30-70を0-1にマッピング）
        norm = (deviation_score - 30) / 40
        norm = max(0.0, min(1.0, norm))  # クリップ

        normalized[motor['motor_number']] = norm * 20.0  # motor_weight=20

    return normalized
```

---

## Phase 3: 重み配分の最適化

### タスク3.1 グリッドサーチによる最適化
**ファイル:** `optimize_weights.py`

```python
"""
過去データで重み配分を最適化

現状:
- course_weight: 35
- racer_weight: 35
- motor_weight: 20
- kimarite_weight: 5
- grade_weight: 5

探索範囲:
- course_weight: 25-45
- racer_weight: 25-45
- motor_weight: 10-30
- kimarite_weight: 0-10
- grade_weight: 0-10
（合計100になる組み合わせのみ）

評価指標:
- 1着的中率
- 3連単的中率
- Brier Score
"""
```

### タスク3.2 機械学習による重み学習
**ファイル:** `ml_weight_optimizer.py`

```python
"""
scikit-learnのLogisticRegressionやXGBoostで
各要素の係数を学習

feature:
- course_score
- racer_score
- motor_score
- kimarite_score
- grade_score

target:
- 1着か否か（binary classification）
"""
```

---

## Phase 4: 信頼度判定の再調整

### タスク4.1 新しいスコア分布での基準見直し
**ファイル:** `src/analysis/race_predictor.py`
**関数:** `_calculate_confidence()` (486-582行目)

**改善後のスコア分布を想定:**
- 平均スコア: 50点 → 60点に上昇
- 最大スコア: 76点 → 90点に上昇

**新しい基準案:**
```python
if total_score >= 80:
    confidence = 'A'
elif total_score >= 70:
    confidence = 'B'
elif total_score >= 60:
    confidence = 'C'
elif total_score >= 50:
    confidence = 'D'
else:
    confidence = 'E'
```

### タスク4.2 データ充実度スコアの基準緩和
**現状:** data_quality >= 80でA判定許可

**改善案:** data_quality >= 70でA判定許可

ただし、**的中率を確認してから調整**

---

## 実装優先順位

### 🔥 最優先（今週中）
1. [ ] `analyze_score_components.py` 作成・実行
2. [ ] コーススコアの正規化実装
3. [ ] 1レース分でテスト実行
4. [ ] 効果確認（スコア分布の変化）

### ⚡ 高優先（来週前半）
5. [ ] 選手スコアの正規化実装
6. [ ] モータースコアの正規化実装
7. [ ] 全体再生成してバックテスト

### 📊 中優先（来週後半）
8. [ ] `analyze_accuracy_by_factor.py` 作成・実行
9. [ ] 重み配分の最適化実験
10. [ ] 信頼度基準の再調整

---

## 成功の指標

### スコア分布の改善目標
- 平均スコア: 33.8点 → **60点以上**
- A/B判定: 0.6% → **20%以上**
- E判定: 80% → **20%以下**

### 的中率の改善目標
- 1着的中率（全体）: 現状確認 → **+5%以上**
- 1着的中率（A判定）: N/A → **60%以上**
- 1着的中率（B判定）: N/A → **50%以上**

---

## 注意事項

### ⚠️ やってはいけないこと
1. **単純な係数掛け算でスコアを底上げ**
   - 相対的な順位が変わらないため、的中率は向上しない
   - 信頼度表示が良くなるだけで本質的な改善ではない

2. **信頼度基準だけを緩める**
   - スコアが低いままで基準を下げても意味がない
   - データが不足しているレースにA判定を出すのは危険

3. **重み配分だけを変更**
   - 各要素のスコア自体が低いまま重みを変えても効果は限定的
   - まず正規化してから重み調整

### ✅ やるべきこと
1. **各要素のスコア計算を正規化**
   - 各要素が理論上の最大値に到達できるようにする
   - 相対評価で差をつける

2. **データ駆動で最適化**
   - 過去データで的中率との相関を確認
   - バックテストで効果を検証

3. **段階的に実装・検証**
   - 一度に全部変えない
   - コース → 選手 → モーターの順に実装
   - 各段階で効果を確認

---

## 参考資料

### 関連コード
- `src/analysis/race_predictor.py` - メイン予測エンジン
- `src/analysis/statistics_calculator.py` - コース統計計算
- `src/analysis/racer_analyzer.py` - 選手分析
- `src/analysis/motor_analyzer.py` - モーター分析

### データベーステーブル
- `races` - レース基本情報
- `results` - レース結果
- `race_predictions` - 予測結果
- `racer_stats` - 選手統計（あれば）
- `motor_stats` - モーター統計（あれば）

### 分析スクリプト
- `analyze_confidence_distribution.py` - 信頼度分布分析（作成済み）
- `docs/20251125_作業ログ.md` - 本日の作業まとめ
