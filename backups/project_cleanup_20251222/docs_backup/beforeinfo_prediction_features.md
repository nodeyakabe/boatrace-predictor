# 直前情報データの予想活用ガイド

作成日: 2025-12-02

## 概要

BeforeInfoScraperで取得できる全13種類のデータについて、予想への活用方法を詳細に解説します。

---

## 取得可能データ一覧

### 選手別データ（6艇分）

| No | データ名 | 型 | 説明 | DB格納先 |
|----|---------|-----|------|---------|
| 1 | exhibition_times | dict[int, float] | 展示タイム（秒） | race_details.exhibition_time |
| 2 | start_timings | dict[int, float] | スタート展示ST（秒、負=フライング） | race_details.st_time |
| 3 | tilt_angles | dict[int, float] | チルト角度（度） | race_details.tilt_angle |
| 4 | parts_replacements | dict[int, str] | 部品交換（R/P/E/L/K等） | race_details.parts_replacement |
| 5 | adjusted_weights | dict[int, float] | 調整重量（kg） | race_details.adjusted_weight |
| 6 | exhibition_courses | dict[int, int] | 展示進入コース | race_details.exhibition_course |
| 7 | previous_race | dict[int, dict] | 前走成績（course/st/rank） | race_details.prev_race_* |

### 気象データ（レース共通）

| No | データ名 | 型 | 説明 | DB格納先 |
|----|---------|-----|------|---------|
| 8 | temperature | float | 気温（℃） | weather.temperature |
| 9 | water_temp | float | 水温（℃） | weather.water_temperature |
| 10 | wind_speed | int | 風速（m） | weather.wind_speed |
| 11 | wave_height | int | 波高（cm） | weather.wave_height |
| 12 | weather_code | int | 天候コード（1=晴, 2=曇, 3=雨...） | weather.weather_code |
| 13 | wind_dir_code | int | 風向コード | weather.wind_dir_code |

---

## 予想への活用方法

### 🏆 優先度：最高

#### 1. 展示タイム（exhibition_times）

**予想への影響度**: ⭐⭐⭐⭐⭐

**活用方法:**
- **相対評価で使う**: 6艇の中での順位が重要
  - 1位: +15点
  - 2位: +10点
  - 3位: +5点
  - 4-6位: 0点
- **絶対値での評価**:
  - 6.70秒以下: モーター・選手の調子が極めて良好 → +5点
  - 6.90秒以上: 調子が悪い可能性 → -5点

**実装例:**
```python
# 展示タイム順位計算
sorted_times = sorted(exhibition_times.items(), key=lambda x: x[1])
for rank, (pit, time) in enumerate(sorted_times, 1):
    if rank == 1:
        score[pit] += 15
    elif rank == 2:
        score[pit] += 10
    elif rank == 3:
        score[pit] += 5
```

**注意点:**
- 会場によって平均タイムが異なる（戸田は遅め、大村は速め）
- 風・波の影響を受けやすい

---

#### 2. スタートタイミング（start_timings）

**予想への影響度**: ⭐⭐⭐⭐⭐

**活用方法:**

**（A）ST値の評価:**
- **0.10秒以下**: 超優秀 → +20点
- **0.11〜0.14秒**: 優秀 → +10点
- **0.15〜0.17秒**: 平均的 → +5点
- **0.18秒以上**: 遅い → 0点
- **負の値（フライング）**: 大幅減点 → -30点

**（B）STの相対評価:**
```python
# 全艇の平均STを計算
avg_st = sum(start_timings.values()) / len(start_timings)

for pit, st in start_timings.items():
    if st < 0:  # フライング
        score[pit] -= 30
        continue

    # 平均より早い
    if st < avg_st - 0.03:
        score[pit] += 15
    elif st < avg_st:
        score[pit] += 8
    # 平均より遅い
    elif st > avg_st + 0.03:
        score[pit] -= 10
```

**（C）フライング検出:**
- フライングした選手は本番で慎重になる傾向 → 大幅減点
- 展示でフライング = 本番では出遅れリスク

---

#### 3. 展示進入コース（exhibition_courses）

**予想への影響度**: ⭐⭐⭐⭐⭐

**活用方法:**

**（A）進入変更の検出:**
```python
# 枠番とコースが異なる = 進入変更
is_wakamari = all(pit == course for pit, course in exhibition_courses.items())

if not is_wakamari:
    # 進入変更あり
    for pit, course in exhibition_courses.items():
        if pit != course:
            # インに入った選手を評価アップ
            if course == 1:
                score[pit] += 25  # 1コース取り
            elif course == 2:
                score[pit] += 15  # 2コース取り

            # 外に回された選手を評価ダウン
            if pit <= 2 and course >= 4:
                score[pit] -= 20  # インから外に
```

**（B）進入隊形の分析:**
- **1-2-3-4-5-6（枠なり）**: 標準的な展開
- **2-1-3-4-5-6（イン戦）**: 1-2号艇のイン争い → 両者減点
- **1-3-2-4-5-6**: 3号艇が2コース取り → 3号艇を評価アップ

**（C）スタート順序の予測:**
- 展示進入コース ≒ 本番進入コース（かなり高い確率で一致）
- 本番の進入コース予測に活用

---

### 🔥 優先度：高

#### 4. 前走成績（previous_race）

**予想への影響度**: ⭐⭐⭐⭐

**活用方法:**

**（A）前走ST評価:**
```python
if pit in previous_race:
    prev = previous_race[pit]
    prev_st = prev.get('st')

    if prev_st:
        # 前走STが良い → 調子良好
        if prev_st < 0.12:
            score[pit] += 10
        elif prev_st < 0.15:
            score[pit] += 5
        # 前走STが悪い → 調子不良
        elif prev_st > 0.18:
            score[pit] -= 5
```

**（B）前走着順評価:**
```python
prev_rank = prev.get('rank')
if prev_rank:
    # 前走好走 → 調子継続の可能性
    if prev_rank == 1:
        score[pit] += 8
    elif prev_rank <= 3:
        score[pit] += 3
    # 前走大敗 → 調子悪化の可能性
    elif prev_rank >= 5:
        score[pit] -= 5
```

**（C）前走進入コースとの一貫性:**
```python
prev_course = prev.get('course')
current_course = exhibition_courses.get(pit)

# 同じコースから出る = スタート慣れ
if prev_course == current_course:
    score[pit] += 3  # 微加点
```

**注意点:**
- 前走が別会場の場合、コース特性が異なる
- 前走が数日前の場合、調子が変わっている可能性

---

#### 5. チルト角度（tilt_angles）

**予想への影響度**: ⭐⭐⭐

**活用方法:**

**（A）チルト角度の解釈:**
- **-0.5度**: 標準（ターン重視、安定志向）
- **0.0度**: やや攻め（出足・伸び重視）
- **+0.5〜+3.0度**: 攻めのセッティング（まくり・まくり差し狙い）

**（B）コースとの相性:**
```python
tilt = tilt_angles.get(pit)
course = exhibition_courses.get(pit)

# 1-2コース（イン）でマイナスチルト → 逃げ重視
if course in [1, 2] and tilt <= -0.5:
    score[pit] += 3  # 逃げに適したセッティング

# 4-6コース（外）でプラスチルト → まくり狙い
if course in [4, 5, 6] and tilt >= 0.5:
    score[pit] += 5  # まくり戦法
```

**（C）相対評価:**
- チルトを大きく立てた選手（+2.0度以上）→ 勝負気配
- 全員が-0.5度 → 標準的な展開

---

#### 6. 調整重量（adjusted_weights）

**予想への影響度**: ⭐⭐⭐

**活用方法:**

**（A）重量ハンデの影響:**
- 調整重量が多い = 選手の体重が軽い
- 重い選手 vs 軽い選手 → スタート・ターンで差が出る

**（B）評価基準:**
```python
weight = adjusted_weights.get(pit, 0.0)

# 2.0kg以上の重量差がある場合
if weight >= 2.0:
    # 体重が軽い選手は不利（特にアウト戦）
    if course >= 4:
        score[pit] -= 5  # 外回り+軽量は厳しい
    else:
        score[pit] -= 2  # インコースでも若干不利

# 全員0.0kgの場合は影響なし
```

**（C）他艇との比較:**
```python
# 最も軽い選手と最も重い選手の差
max_weight = max(adjusted_weights.values())
min_weight = min(adjusted_weights.values())

if max_weight - min_weight >= 3.0:
    # 大きな体重差がある → 重い選手を評価アップ
    for pit, weight in adjusted_weights.items():
        if weight <= min_weight + 0.5:
            score[pit] += 5  # 相対的に重い
```

---

### 📊 優先度：中

#### 7. 部品交換（parts_replacements）

**予想への影響度**: ⭐⭐⭐

**活用方法:**

**（A）交換部品の種類:**
- **R（リング）**: プロペラのエッジ交換 → モーター整備良好
- **P（ピストン）**: エンジン整備 → パワー改善期待
- **E（エレクトロニクス）**: 電装系交換
- **L（ローター）**: 回転部分
- **K（キャブレター）**: 燃料系統

**（B）評価基準:**
```python
parts = parts_replacements.get(pit, '')

if parts:
    # 部品交換あり = モーター整備に気を使っている
    if 'R' in parts:
        score[pit] += 3  # リング交換は好材料
    if 'P' in parts:
        score[pit] += 2  # パワーアップ期待
```

**（C）未交換の意味:**
- 交換なし = 調整不要なほど好調 or 諦めモード
- モーター2連対率と組み合わせて判断

---

#### 8. 気温・水温（temperature / water_temp）

**予想への影響度**: ⭐⭐

**活用方法:**

**（A）気温の影響:**
- **低温（10℃以下）**: モーター性能が安定しにくい
- **高温（30℃以上）**: モーターオーバーヒートリスク

**（B）水温の影響:**
```python
water_temp = weather.get('water_temp')

if water_temp:
    # 低水温（15℃以下）→ パワーが出やすい
    if water_temp <= 15:
        # 高出力モーターの選手を評価アップ
        pass

    # 高水温（25℃以上）→ オーバーヒート注意
    if water_temp >= 25:
        # 長時間走行で不利になる可能性
        pass
```

**（C）気温・水温差:**
- 気温と水温の差が大きい → モーター調整難易度が高い

---

#### 9. 風速・風向（wind_speed / wind_dir_code）

**予想への影響度**: ⭐⭐⭐⭐

**活用方法:**

**（A）風速の影響:**
```python
wind_speed = weather.get('wind_speed', 0)

if wind_speed >= 5:
    # 強風時の評価
    # インコース有利度が下がる
    venue_correction *= 0.95  # 会場補正を調整
```

**（B）風向の影響:**
- **追い風**: インコース有利、スピード出やすい
- **向かい風**: アウトコース有利、ターンが難しい
- **横風**: コース取りが難しい

**（C）会場別風特性:**
```python
# 風向コードと会場特性の組み合わせ
wind_dir = weather.get('wind_dir_code')

# 例: 浜名湖、琵琶湖は風の影響大
if venue_code in ['09', '11'] and wind_speed >= 3:
    # 外コースを若干評価アップ
    for pit, course in exhibition_courses.items():
        if course >= 4:
            score[pit] += 3
```

---

#### 10. 波高（wave_height）

**予想への影響度**: ⭐⭐

**活用方法:**

**（A）波高の影響:**
```python
wave_height = weather.get('wave_height', 0)

if wave_height >= 5:
    # 高波時 → 体重が重い選手有利
    for pit, weight in adjusted_weights.items():
        if weight <= 1.0:  # 体重が重い（調整重量少ない）
            score[pit] += 5
```

**（B）会場特性:**
- 海水: 波が立ちやすい（唐津、徳山、下関、丸亀など）
- 淡水: 波は少ない（戸田、多摩川など）

---

#### 11. 天候コード（weather_code）

**予想への影響度**: ⭐⭐

**活用方法:**

**（A）天候による影響:**
```python
weather_code = weather.get('weather_code')

# 1=晴, 2=曇, 3=雨
if weather_code == 3:  # 雨
    # 視界不良 → 経験豊富な選手有利
    # モーターパワーより操縦技術が重要
    pass
```

**（B）視界の影響:**
- 雨天 → スタートタイミングが取りにくい
- 曇天 → 標準的
- 晴天 → 視界良好、スタート精度高い

---

## 複合評価の実装例

### 総合スコアリング

```python
def calculate_beforeinfo_score(pit, exhibition_data, weather_data):
    """直前情報に基づく総合スコア計算"""
    score = 0

    # 1. 展示タイム評価（最大15点）
    rank = get_exhibition_time_rank(pit, exhibition_data['exhibition_times'])
    score += [15, 10, 5, 0, 0, 0][rank - 1]

    # 2. ST評価（最大20点、最低-30点）
    st = exhibition_data['start_timings'].get(pit)
    if st is not None:
        if st < 0:
            score -= 30  # フライング
        elif st <= 0.10:
            score += 20
        elif st <= 0.14:
            score += 10
        elif st <= 0.17:
            score += 5

    # 3. 進入コース評価（最大25点）
    course = exhibition_data['exhibition_courses'].get(pit)
    pit_num = pit
    if course != pit_num:
        if course == 1:
            score += 25  # 1コース奪取
        elif course == 2:
            score += 15
        elif pit_num <= 2 and course >= 4:
            score -= 20  # インから外へ

    # 4. 前走成績評価（最大18点）
    prev = exhibition_data['previous_race'].get(pit, {})
    if prev.get('st') and prev['st'] < 0.12:
        score += 10
    if prev.get('rank') == 1:
        score += 8
    elif prev.get('rank', 99) >= 5:
        score -= 5

    # 5. チルト評価（最大5点）
    tilt = exhibition_data['tilt_angles'].get(pit)
    if tilt is not None and course:
        if course in [1, 2] and tilt <= -0.5:
            score += 3
        elif course in [4, 5, 6] and tilt >= 0.5:
            score += 5

    # 6. 調整重量評価
    weight = exhibition_data['adjusted_weights'].get(pit, 0.0)
    if weight >= 2.0 and course >= 4:
        score -= 5

    # 7. 部品交換評価（最大5点）
    parts = exhibition_data['parts_replacements'].get(pit, '')
    if 'R' in parts:
        score += 3
    if 'P' in parts:
        score += 2

    # 8. 気象条件評価
    wind_speed = weather_data.get('wind_speed', 0)
    if wind_speed >= 5 and course >= 4:
        score += 3  # 強風時は外有利

    return score
```

---

## データ品質チェック

### データ取得状況の確認

```python
def check_beforeinfo_quality(beforeinfo_data):
    """直前情報の充実度をチェック"""
    quality_score = 0
    max_score = 7

    if beforeinfo_data.get('exhibition_times') and len(beforeinfo_data['exhibition_times']) == 6:
        quality_score += 1

    if beforeinfo_data.get('start_timings') and len(beforeinfo_data['start_timings']) == 6:
        quality_score += 1

    if beforeinfo_data.get('exhibition_courses') and len(beforeinfo_data['exhibition_courses']) == 6:
        quality_score += 1

    if beforeinfo_data.get('tilt_angles') and len(beforeinfo_data['tilt_angles']) >= 5:
        quality_score += 1

    if beforeinfo_data.get('adjusted_weights') and len(beforeinfo_data['adjusted_weights']) >= 5:
        quality_score += 1

    if beforeinfo_data.get('previous_race') and len(beforeinfo_data['previous_race']) >= 1:
        quality_score += 1

    if beforeinfo_data.get('weather'):
        weather = beforeinfo_data['weather']
        if all([weather.get('temperature'), weather.get('wind_speed'), weather.get('weather_code')]):
            quality_score += 1

    # 充実度: 7段階
    return quality_score, max_score
```

---

## 実装優先順位まとめ

### Phase 1（即実装推奨）
1. ✅ 展示タイム評価（相対順位）
2. ✅ ST評価（絶対値+フライング検出）
3. ✅ 展示進入コース評価（進入変更検出）

### Phase 2（重要）
4. ⭐ 前走成績評価（ST+着順）
5. ⭐ チルト角度評価（コース別）
6. ⭐ 風速・風向評価（会場別）

### Phase 3（補助的）
7. 調整重量評価
8. 部品交換評価
9. 気温・水温評価
10. 波高評価
11. 天候コード評価

---

## 参考資料

- [setup_beforeinfo_enhancement.md](setup_beforeinfo_enhancement.md) - 環境構築手順
- [残タスク一覧.md](残タスク一覧.md) - タスク状況
- `src/scraper/beforeinfo_scraper.py` - データ取得実装
- `src/analysis/race_predictor.py` - 予測エンジン（実装先）

---

## 更新履歴

| 日付 | 変更内容 |
|------|---------|
| 2025-12-02 | 初版作成（全13種類のデータ活用方法を記載） |
