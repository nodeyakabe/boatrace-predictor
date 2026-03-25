# 展示タイム活用マップ

**作成**: 2026-03-25
**背景**: 展示タイムの活用方法を徹底調査した結果をまとめた資料。
新規施策を検討する前に必ず参照し、「すでに実装済み」の重複実装を避けること。

---

## 結論サマリー

展示タイムは以下の **5層構造** で活用済み。ユーザーが着目した3点（タイム差・会場重み・コース補正）はすべて実装されている。

| ユーザーの着目点 | 実装状況 | 実装箇所 |
|:------|:-------:|:-----|
| タイム差の大きさを活用 | ✅ 完全実装 | feature_transforms.py（4種の連続値特徴量） |
| 会場ごとの重み最適化 | ✅ 完全実装 | extended_scorer.py + venue_exhibition_reliability.json |
| コースごとの補正 | ⚠️ 部分実装 | feature_transforms.py（全会場共通の固定係数） |

---

## 5層の詳細実装

### 層1: beforeinfo_scorer — 順位ベーススコア（展示タイムスコア25点満点）

**ファイル**: `src/analysis/beforeinfo_scorer.py` L169-197
**用途**: `total_score` の構成要素（信頼度 A/B/C/D 判定に使用）
**ロジック**:
```python
rank_scores = {1: 25.0, 2: 18.0, 3: 12.0, 4: 6.0, 5: 3.0, 6: 0.0}
```
- タイム差の大きさは**無視**（順位のみ）
- 6位=0点（マイナスなし）
- 数値の由来: 経験則（コード内に実測根拠なし）

**評価**: 粗い設計だが、LightGBM層（層3）がタイム差をカバーするため問題なし。棲み分けが機能している。

---

### 層2: pattern_scorer — 複合パターン乗算

**ファイル**: `src/analysis/scorers/pattern_scorer.py`
**用途**: 展示順位 × PRE順位 × ST順位 の組み合わせパターンボーナス
**ロジック**:
```python
# 例: 展示1位 × PRE1位 × ST1位 → 1.5倍ボーナス
ex_rank <= 3  # のような順位判定のみ
```
- タイム差の大きさは**無視**
- LightGBM層でカバー済み

---

### 層3: feature_transforms — LightGBM特徴量（タイム差magnitude対応）⭐

**ファイル**: `src/features/feature_transforms.py`
**用途**: conditional_rank_model（LightGBM）の入力特徴量
**ロジック**: コース別補正後の展示タイムから4種の相対値を生成

```python
# コース別補正係数（インコース有利を補正）
course_exh_adjustment = {
    1: -0.02,   # 1コースは0.02秒遅くても同等評価
    2: -0.01,
    3:  0.0,
    4:  0.0,
    5: +0.01,
    6: +0.02,   # 6コースは0.02秒速くないと同等評価にならない
}

# 補正後タイムから4特徴量を生成
exh_adjusted    = exhibition_time + course_exh_adjustment[course]
exh_rank        = レース内順位（1=最速）
exh_diff        = exh_adjusted - レース平均                ← タイム差magnitude反映
exh_zscore      = (exh_adjusted - 平均) / 標準偏差         ← タイム差magnitude反映
exh_gap_to_best = exh_adjusted - レース最速タイム          ← タイム差magnitude反映（最重要）
exh_relative_position = (自艇-最速)/(最遅-最速) → 0〜1   ← タイム差magnitude反映
```

**重要**: `exh_gap_to_best` は「0.01秒差の1位と0.10秒差の1位」を明確に区別する。

**コース別補正係数について**:
- 根拠: 経験則（実測検証なし）
- 範囲は-0.02〜+0.02秒（展示タイムの典型レンジ0.10〜0.30秒の7〜20%）
- 全24会場で共通（会場×コース最適化なし）
- 評価: LightGBMが非線形学習で吸収するため現状で十分。変更コスト（再学習）に見合わない

---

### 層4: extended_scorer — 会場別信頼性重み（TJ-9成果）⭐

**ファイル**: `src/analysis/extended_scorer.py` L95-145
**データ**: `data/venue_exhibition_reliability.json`（全24会場、実測データ）
**用途**: 展示タイムの会場別信頼性に基づき、スコアの最大値（max_score）を調整
**呼び出し元**: `src/analysis/race_predictor.py` → 本番稼働中

**データ内容（主要会場）**:
```
会場          スコア  Spearman相関  展示1位1着率   重み
徳山・丸亀    91     0.24         31.2%・29.6%  0.937倍
住之江・尼崎  87-78  0.22         29.5%・28.6%  0.910-0.847倍
江戸川        1.0    0.129        23.6%         0.307倍（大幅減）
児島          3.1    0.170        25.3%         0.322倍（大幅減）
```

**重み変換式**:
```python
multiplier = 0.30 + 0.70 * (score / 100.0)
# score=91 → 0.937倍（ほぼフル）
# score=1  → 0.307倍（69%減）
```

**評価**: 実測データに基づく合理的な設計。最小値0.307（下限0.30）は「完全ゼロにはしない」フロアとして適切。変換式の線形性は会場間の信頼性差を適切に反映している。

**注意: デッドコード**:
`config/exhibition_reliability.py` に別の信頼性係数（1.50/0.50）が定義されているが、どこからもimportされていない（= 完全デッドコード）。混乱の元なので削除候補。

---

### 層5: boaters_inspired_features — モーター累積成績

**ファイル**: `src/features/boaters_inspired_features.py` L98-162
**用途**: モーターの過去展示タイム平均（motor_tenji_avg）をLightGBM特徴量として使用
**ロジック**: 過去60日間の同モーターの展示タイム平均 + 会場平均との差分

```python
AVG(rd.exhibition_time) as avg_tenji
avg_tenji - venue_avg_tenji as diff_from_avg  # 会場平均との差分
```

- 「当日の速さ（瞬間値）」ではなく「モーターの継続的な速さ（累積値）」
- 会場×モーター番号の組み合わせで評価

---

## 未使用だが存在するファイル

| ファイル | 内容 | 状態 |
|:--------|:-----|:----:|
| `src/scoring/exhibition_scorer_v3.py` | タイム差ボーナス（0.1-0.2秒→+10点等）実装済み | **未使用**（アーカイブ版のみ使用） |
| `src/scoring/exhibition_scorer_v2.py` | 会場別平均との z-score ベーススコア | **未使用** |
| `config/exhibition_reliability.py` | 1.50/0.50係数の信頼性設定 | **デッドコード**（削除候補） |
| `data/venue_exhibition_stats.json` | 24会場の展示タイム平均・標準偏差 | exhibition_scorer_v2/v3専用（本番未使用） |

---

## 検証済み「追加活用は不要」の施策

以下は実際に試みたが効果なしと確認済み（REJECTED_IDEAS.md に記録）:

### 不採用1: compound_buff加算（展示タイム差ルール）
- **内容**: exhibition_gap_large(+5pt)/medium(+2pt)/small(-2pt)をtotal_scoreに加算
- **結果**: ROI -24.7pt / 収支 -79,670円の大幅悪化
- **原因**: compound_buffが6艇全員に適用 → rank2/3が変動 → 3連単買い目30%変化で的中率低下

### 不採用2: 購入条件フィルタ（案A）
- **内容**: bet_conditionsに exh_time_diff >= X秒 フィルタを追加
- **結果**: 全体収支 -83%（件数1/9になりROI改善は副産物）
- **原因**: 展示タイム差は「1着の確度向上シグナル」だが3連単2〜3着予測には無関係

### 核心的な限界
> 展示タイム差は「1位の機力優位」を示すシグナルだが、
> **3連単の2着・3着の組み合わせ特定には寄与しない**。
> 3連単予測には「誰が1着か」だけでなく「誰が2着・3着か」も必要。

---

## 今後の新規施策を検討する際のチェックリスト

展示タイム関連の施策を検討する前に確認:

- [ ] 「タイム差の大きさ」→ `exh_gap_to_best` で既にLightGBMに入力済みか？
- [ ] 「会場別重み」→ TJ-9（venue_exhibition_reliability.json）で適用済みか？
- [ ] 「コース別補正」→ feature_transforms.py の course_exh_adjustment で補正済みか？
- [ ] 「モーター累積成績」→ motor_tenji_avg で既に活用済みか？
- [ ] 「3連単2着・3着への影響」→ 1着シグナルだけを強化しても3連単的中率は改善しないことを確認したか？

---

## 設定値の最適性評価（2026-03-25 Opus確認）

| 設定 | 判定 | 備考 |
|:-----|:----:|:-----|
| コース別補正（-0.02〜+0.02） | **現状で十分** | LightGBMが非線形学習で吸収。再学習コスト不要 |
| 会場別信頼性スコア変換式 | **現状で十分** | 実測データに基づく合理的設計 |
| beforeinfo_scorer 順位スコア | **現状で十分** | LightGBMの連続値特徴量と棲み分け済み |
| config/exhibition_reliability.py | **デッドコード** | 削除候補（本番未使用） |
| prediction_engine_v2.py L421-423 | **未使用ファイル** | 本番未import（STANDARD_TIME=6.70も未検証だが影響なし） |
