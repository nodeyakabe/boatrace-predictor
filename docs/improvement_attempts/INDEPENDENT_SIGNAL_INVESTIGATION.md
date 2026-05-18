# 独立信号調査タスク 引継ぎ資料

**作成日**: 2026-05-18
**ベースライン**: v2.61.0（4,360件 / ROI 258.0% / +722,740円 / 6/6年黒字）
**ステータス**: 調査開始前（DBスキーマ・データカバレッジ確認済み）

---

## 1. タスクの目的と背景

### 1.1 凍結期間問題

現在の購入条件ポートフォリオ（全15条件）は、**凍結期間（前回ピーク収支を更新するまでの待機期間）が最長628日**に達する。これは年単位の機会損失であり、心理的にもシステム稼働継続のリスク要因。

### 1.2 構造的原因

| 観点 | 状況 |
|------|------|
| 表面上の月次的中相関 | 平均 0.03（独立に見える） |
| 実態 | 全15条件が同じ `total_score` / `confidence` を基軸 |
| 派生方法 | 同じスコアから「会場」「オッズ帯」「予測順位パターン」で切り分けただけ |
| 結果 | スコア計算の根幹（before予測 total_score）が共通 → 同時不発月が発生 |

**証拠**: Opus分析で「全15条件が同月にゼロ的中の月」が複数回観測。これは個別ROIが高くてもポートフォリオレベルで分散効果が出ていないことを意味する。

### 1.3 改善目標（定量）

| 指標 | 現状 | 目標 |
|------|:---:|:---:|
| 凍結期間（最長） | 628日（≈21ヶ月） | **6.5ヶ月以下** |
| 新規追加条件 | - | **月+30件 × ROI 150%以上** × **1〜2条件** |
| 月次的中相関（既存との） | 平均0.03（但し同源） | **< 0.3**（真の独立性） |

Opus試算: 独立な30件/月・ROI150%+の追加 → 凍結期間 11ヶ月 → 6.5ヶ月に短縮。

### 1.4 不採用方針（再検討禁止）

- **仮説A（低オッズ帯追加）**: 構造的にROI毀損 → 不採用
- **仮説B（既存条件の会場拡張）**: 月+0.36件の改善のみ → 効果不足

→ **本タスクのスコープは「現スコアと独立した新規信号の発見」のみ**。

---

## 2. 「独立した信号」の厳密な定義

| 条件 | 数値基準 |
|------|---------|
| **A. 現スコアとの月次的中相関** | < 0.3 |
| **B. 単独期待値** | ROI 150%以上（Tier1） |
| **C. 月次貢献** | 月+5件以上の追加的中（理想は+30件） |
| **D. データ起源の独立性** | `total_score_final` / `confidence` を直接参照しないこと |

**「独立」の核心定義**:
> 既存の race_predictions.total_score / .confidence と「数値的に独立」かつ「データ起源（特徴量）も大部分非重複」な信号。
> 例えば「current scoreが低いが新信号は高い」レースで的中が発生すれば真の独立性が確認できる。

---

## 3. 調査候補（DBデータカバレッジ確認済み）

DB実測（2026-05-18時点）に基づき、以下7カテゴリを実現可能性レベル別に評価。

### 3.1 ✅ 即時利用可（2020-2025全年カバレッジあり）

#### 候補1: 選手状態系（直近N走）

| テーブル | カラム | カバレッジ |
|---------|--------|-----------|
| `racer_features` | `recent_avg_rank_3/5/10`, `recent_win_rate_3/5/10`, `total_races` | **2024-2026のみ（431,897行）** ⚠️ |
| `racer_venue_features` | `venue_win_rate`, `venue_avg_rank`, `venue_races` | **2024-2026のみ（435,296行）** ⚠️ |

⚠️ **重大制約**: 2020-2023年は欠損。バックテストでは2024-2025の2年間しか使えない（Tier2合格基準「6年で4/6年黒字」を直接満たすには再構築が必要）。

**運用方針**:
- 候補1のTier1テストは2024-2025の2年で実施
- Tier2合格には `scripts/maintenance/run_racer_features_recompute.py` を使い2020-2023を遡及生成する必要あり
- 過去走データ自体は `results` に2020年分から完備（54,880行/年）→ 計算は可能

**独立性評価**: 直近成績は `total_score` の `racer_score`/`grade_score` 経由で既に部分的に反映済み。ただし `recent_avg_rank_3` のような短期変動は反映されていないため**部分的に独立**の可能性。

**有望仮説**:
- 「直近3走の平均着順 ≤ 1.5（急上昇選手）」× 1コース指定 → 通常スコアでは捉えられない短期好調を活用
- 「会場勝率 ≥ 50% × 会場経験10走以上」（venue specialist）

---

#### 候補3: 展示タイム絶対値（race_details）⭐ 最有望候補

| データ | 2020-2026カバレッジ |
|--------|---------------------|
| `race_details.exhibition_time` | 2020-2026全年（98%超） |
| `race_details.st_time` | 2020-2026全年（98%超） |
| `race_details.tilt_angle` | 2020-2026全年（99%超） |

**独立性**: 展示タイムは `total_score` に組み込まれているが、「会場内偏差」「ST分布の上下分位点」などは未活用 → 加工により独立信号化可能。

**有望仮説**:
- 「同一レース内の展示タイムが**最速** AND 既存スコアでは**Cランク以下**」→ 過小評価逆転シグナル
- 「会場固有の典型ST（中央値）からの偏差」→ 会場別の異常値検出
- 「2号艇ST ≤ 0.10 × 1号艇ST ≥ 0.18」→ 1号艇まくられ予兆

---

#### 候補4: 天候・波高系（ml_analysis_features）

| データ | カバレッジ |
|--------|-----------|
| `ml_analysis_features.wind_speed` | 2020-2025全年（57,756/年〜212,778/年） |
| `ml_analysis_features.wind_direction` | 同上 |
| `ml_analysis_features.wave_height` | 同上 |

⚠️ **注意**: `race_conditions` テーブルは2024年のみカバレッジ良好（その他年は数十件）。**必ず `ml_analysis_features` を使うこと**。

**独立性**: 風・波は現スコアに**まったく組み込まれていない**（特徴量から外されている）→ 真の独立信号候補。

**有望仮説**（CLAUDE.md誤推論パターン5に注意）:
- 「会場別」に「風速4m以上 × 風向×」の的中率を個別測定（**全会場一括禁止**）
- 「波高3cm以上」→ 荒れレース。下位コース来やすい
- 既知の傾向: 風速5m以上で1コース勝率が低下、波高が高いほど荒れる

---

#### 候補6: オッズ構造系（trifecta_odds）

| データ | カバレッジ |
|--------|-----------|
| `trifecta_odds`（全120点） | 2020-2026全年（98%超） |

**独立性**: 既存条件はオッズ「帯」（30-50倍など）でフィルタしているが、「オッズ構造そのもの」（人気合計・分布形状）は未活用 → **完全に独立**。

**有望仮説**:
- 「1〜3番人気の三連単オッズ合計 ≤ X倍」→ 上位3つで決まりやすい固いレース構造の検出
- 「1番人気と2番人気のオッズ比 ≥ N」→ 1強レース検出（既存スコアとは別軸）
- 「予測1着艇の人気順位（trifecta_odds 1着同居数）」→ 市場との乖離度

---

### 3.2 ⚠️ 部分利用可（2025+のみ・OOS検証は別途）

#### 候補2: モーター部品交換系

| データ | カバレッジ |
|--------|-----------|
| `race_details.parts_replacement` | **2025年: 16,614件 / 2026年: 6,204件のみ** |
| `exhibition_data.weight_change` ほか | 2025年: 10,870 / 2026年: 20,253のみ |

⚠️ **過去データなし**: 2020-2024は完全欠損。Tier2「6年で4/6年黒字」を満たせない。

**運用方針**: 2025-2026の2年間OOS検証のみ可能。本採用には2026-2027の追加実績が必要。**長期保留推奨**。

主要交換部品（実測）:
- プロペラ（ペラ）×2: 8,098件（圧倒的1位）
- プロペラ×1: 3,530件
- キャブ: 2,629件
- ピストン×2: 507件 ほか

---

#### 候補7: ボーターズ展示スコア（boaters_tenji_score）

**現状（MEMORY.md記載）**:
- `config/feature_flags.py` で `boaters_tenji_score: True`（**既に本採用済み**）
- 異常スケール会場（01,12,13,18,21）は除外
- max_score=1.0 で運用中
- DBには `prediction_features` 内に明示カラムなし（`ext_exhibition_score` 経由で統合済みと推定）

⚠️ **重要**: 既に総合スコアに統合済みのため**「独立信号」ではない**。除外。
ただし「**未統合の会場（01,12,13,18,21）でのスコア**」は独立性ある可能性 → サブタスクとして調査余地あり。

---

### 3.3 △ 既存スコアと部分的重複の可能性

#### 候補5: レース番号・時期系

| データ | カバレッジ |
|--------|-----------|
| `races.race_number` | 全期間 |
| `races.is_nighter / is_ladies / is_rookie` | 全期間（既に既存条件で活用） |

**独立性**: race_numberは未活用、is_xx系は既存条件で部分活用。

**注意**: MEMORY.md記載の通り「**セグメント絞り込みの統計的限界**」あり。R10-12等のレース番号絞り込みは「最低50的中=2,500-5,000件」のサンプルが必要。Bonferroni補正後に有意なセグメントは現行ポートフォリオでゼロ。

**有望仮説**: 「特定月（例: 12月）× 特定会場」のように複合条件にして十分なサンプルを確保。

---

## 4. 調査手順

### 4.1 ステップA: 候補信号のSQL定義

各候補について、以下のテンプレートで「信号Z」を定義する。

```sql
-- 例: 候補3 - 「予測1着艇の展示タイムが同レース内最速」
WITH race_min_et AS (
  SELECT rd.race_id, MIN(rd.exhibition_time) AS min_et
  FROM race_details rd
  WHERE rd.exhibition_time > 0
  GROUP BY rd.race_id
),
signal_z AS (
  SELECT rp1.race_id,
         CASE WHEN rd.exhibition_time = rmin.min_et THEN 1 ELSE 0 END AS signal_value
  FROM race_predictions rp1
  JOIN race_details rd ON rp1.race_id = rd.race_id AND rp1.pit_number = rd.pit_number
  JOIN race_min_et rmin ON rp1.race_id = rmin.race_id
  WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
)
SELECT * FROM signal_z;
```

### 4.2 ステップB: 独立性確認（月次的中相関 < 0.3）

```python
# scripts/analysis/check_signal_independence.py（要作成）
import sqlite3
import pandas as pd
from scipy.stats import pearsonr

conn = sqlite3.connect('data/boatrace.db')

# 既存スコア由来の月次的中（B_A1_30_50_8VENUES等の主力条件）
existing_hits = pd.read_sql_query("""
SELECT strftime('%Y-%m', r.race_date) AS yyyymm,
       COUNT(*) AS hits
FROM race_predictions rp
JOIN races r ON rp.race_id = r.id
JOIN results res1 ON rp.race_id = res1.race_id AND res1.rank = '1'
WHERE rp.prediction_type = 'before' AND rp.rank_prediction = 1
  AND rp.confidence IN ('A','B')
  AND rp.pit_number = res1.pit_number
  AND r.race_date BETWEEN '2020-01-01' AND '2025-12-31'
GROUP BY yyyymm
""", conn)

# 新規信号Zの月次的中（同じ集計粒度で）
new_hits = pd.read_sql_query("""SELECT ... -- 信号Zで絞った場合のhits""", conn)

merged = existing_hits.merge(new_hits, on='yyyymm', how='outer').fillna(0)
r, p = pearsonr(merged['hits_x'], merged['hits_y'])
print(f"月次相関 r={r:.3f}, p={p:.4f}")
# 合格基準: |r| < 0.3
```

### 4.3 ステップC: Tier1テスト（信号単独のROI測定）

`scripts/backtest/quick_condition_test.py` を活用。
**ただし候補1（racer_features系）は2024-2025年のみ実行可能。**

```bash
# 既存テンプレ流用例
python scripts/backtest/quick_condition_test.py --condition-json '{
  "id": "SIGNAL_Z_TEST",
  "name": "展示タイム最速・現スコアCランク以下",
  "confidence": "C",
  "c1_rank": ["A1","A2","B1"],
  "odds_min": 30,
  "odds_max": 100,
  "venue_filter": "ALL",
  "extra_filter_sql": "EXISTS (SELECT 1 FROM race_details rd JOIN ...)"
}'
```

⚠️ `quick_condition_test.py` が新シグナルをサポートしていない場合は、temp/ 配下に専用スキャンSQLを作成する。**MEMORY.md「スキャンSQL実装バグ」記載の2つの落とし穴に注意**:
1. `c1_rank` 結合は `e1.pit_number = 1`（pit_number=1固定）であって `rp1.pit_number` ではない
2. 月除外は `CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN (4)` で書く

### 4.4 ステップD: 独立性 × Tier1合格 → Tier2

合格した候補（相関<0.3 かつ ROI≥150%）のみ:
1. `config/bet_conditions.py` に追加
2. `python scripts/backtest/standard_backtest_unique.py --full --save-json data/tier2_signal_z.json`
3. 合格基準: ROI≥100%、4/6年黒字
4. Tier3一致率95%以上

### 4.5 ステップE: ポートフォリオ統合効果検証

Tier2合格しただけでは凍結期間は短縮しない可能性あり。**統合後の凍結期間を必ず再測定**:

```python
# 全条件で「最大ドローダウン期間」を計算
python scripts/backtest/standard_backtest_unique.py --full --save-json data/with_signal_z.json
# ドローダウン期間 < 既存ベースライン であることを確認
```

---

## 5. 採用基準（最終）

| 段階 | 基準 |
|------|------|
| **独立性** | 既存ポートフォリオ全体との月次的中相関 < 0.3 |
| **Tier1** | 単独でROI 150%以上、サンプル50件以上、1/2年黒字 |
| **Tier2** | 6年でROI 100%以上、4/6年黒字、累計黒字 |
| **Tier3** | Tier2との一致率 95%以上 |
| **ポートフォリオ貢献** | 統合後の最長凍結期間が縮む（例: 628日 → 400日以下） |
| **月次的中追加** | 月+5件以上（理想は+30件） |

---

## 6. 注意事項・過去の教訓（必読）

### 6.1 CLAUDE.md「データ分析前のチェックリスト」遵守

`docs/guides/DATA_ANALYSIS_CHECKLIST.md` を必ず先に読むこと。

### 6.2 誤推論パターン

#### パターン1（必読）: 表面の数値だけで判断しない
A率/的中率/相関いずれも、**「なぜその数値か」を2〜3段階掘り下げる**。
例: 月次相関が0.03でも「スコアの根幹は同じ」可能性を疑う。

#### パターン4: 影響範囲はコードで実証
「信号XをBスコアと統合 → ROI向上する」と主張する前に、実際にBスコアを使っているコード（`standard_backtest_unique.py` の prediction_type='before'部分）を確認すること。

#### パターン5: 会場共通統計の罠
24競艇場はコース配置が異なる。**全会場一括の「風向別の1コース勝率」は無意味**。必ず会場別に個別分析する。

特に風向の候補（候補4）は会場別必須。
- 北風が「追い風」になる会場：戸田・桐生など
- 北風が「向かい風」になる会場：丸亀・芦屋など
→ 全会場一括ではこれらが相殺・歪曲される。

### 6.3 セグメント絞り込みの統計的限界

MEMORY.md記載:
> 三連単条件のセグメント分析には**最低50的中（=2,500-5,000件）が必要**

レース番号絞り込み・特定月絞り込みは、サンプル不足で偽陽性を出しやすい。Bonferroni補正後に有意なセグメントは現行条件でゼロ。

候補5（レース番号・時期系）は特にこの罠に注意。**ROIが極端に高い小サンプルは「0的中セグメントを除外しただけ」の事後データスヌーピングの可能性**。

### 6.4 スキャンSQL実装テンプレート

MEMORY.md「スキャンSQL実装バグ（2026-04-15）」記載の落とし穴は必須対策:

```python
# ❌ 誤り
# c1_rank結合: e1.pit_number = rp1.pit_number
# 月除外: CAST(SUBSTR(race_date, 5, 2) AS INTEGER) != 4

# ✅ 正しい
# c1_rank結合: e1.pit_number = 1  (Course1は枠1固定)
# 月除外: CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN (4)

# trifecta_odds JOIN例（CLAUDE.md「分析スクリプトでの注意点」）
# 必ず予測順位ベースの買い目を使うこと:
JOIN trifecta_odds t ON rp.race_id = t.race_id
    AND t.combination = CAST(rp1.pit_number AS TEXT) || '-'
                     || CAST(rp2.pit_number AS TEXT) || '-'
                     || CAST(rp3.pit_number AS TEXT)
# ❌ NG: t.combination = '1-2-3'（枠番固定）
```

### 6.5 fast_backtest と standard_backtest_unique の乖離

MEMORY.md記載:
> 条件変更後に乖離する。`fast_backtest` は `prediction_features` テーブル使用 → race_predictions更新後に `import_features_from_predictions.py --full --force` 必要。
> **ベースラインJSONは必ず `standard_backtest_unique --save-json` で生成すること**。

### 6.6 KNOWN BUG（修正禁止領域）

MEMORY.md「extended_scorer scale bug」:
- `src/analysis/extended_scorer.py` L1651 `/ 30.0`（正: `/0.30`）
- `src/analysis/extended_scorer.py` L1638 `+10`（正: `+0.10`）

→ **修正禁止**。全15条件がこのバグ込みで最適化済み。新規独立信号でも `extended_scorer` の修正は触らないこと。

### 6.7 「分析ツールが自分の出力を信じる」罠

`ml_analysis_features` テーブルは事前計算済みの特徴量。古い予測結果が混在している可能性あり。
**信号の独立性検証は必ず生データ（race_details / racer_features / ml_analysis_features の wind系のみ）から再計算すること**。

---

## 7. 推奨優先順位

| 順位 | 候補 | 理由 |
|:---:|------|------|
| **1** | **候補3: 展示タイム絶対値の加工指標** | 2020-2026全年データあり / total_scoreに部分組み込みでも「相対化」「異常値検出」は未活用 |
| **2** | **候補6: オッズ構造（人気合計・分布）** | 完全独立、データ完備、未開拓領域 |
| **3** | **候補4: 風・波（会場別必須）** | 現スコアに未組み込み = 完全独立 / 但し会場別分析の手間あり |
| **4** | 候補1: 選手状態系（直近N走） | データは2024-2025年のみ → Tier2クリア困難。ただし racer_features 遡及計算で打開可 |
| 5 | 候補5: レース番号・時期系 | 統計的有意性確保困難 |
| **保留** | 候補2: 部品交換系 | 2025-2026のみ → 別タスクで2027年データ蓄積後に再開 |
| **対象外** | 候補7: ボーターズ展示 | 既に総合スコアに統合済み |

---

## 8. 開始時アクション

1. **CLAUDE.md / docs/HANDOVER.md / docs/残タスク一覧.md を確認**
2. **本資料を読み、優先順位1（候補3）から着手**
3. SQLサンプル定義 → 月次的中相関測定 → 相関<0.3確認 → Tier1 → Tier2 → Tier3
4. **すべてのテストで MEMORY.md 記載のスキャンSQLバグ対策を踏む**
5. 不採用案は `docs/improvement_attempts/REJECTED_IDEAS.md` に追記
6. 採用案は `config/bet_conditions.py` に追加 → ベースライン更新

---

## 9. 関連ファイル

| 種別 | パス |
|------|------|
| 既存条件定義 | `config/bet_conditions.py` |
| 機能フラグ | `config/feature_flags.py` |
| 拡張スコアラー | `src/analysis/extended_scorer.py`（KNOWN BUG有・修正禁止） |
| 標準バックテスト | `scripts/backtest/standard_backtest_unique.py` |
| Tier1テスト | `scripts/backtest/quick_condition_test.py` |
| 検証ワークフロー | `docs/guides/VALIDATION_WORKFLOW.md` |
| 不採用案ログ | `docs/improvement_attempts/REJECTED_IDEAS.md` |
| データ分析前チェックリスト | `docs/guides/DATA_ANALYSIS_CHECKLIST.md` |
| データ依存関係 | `docs/guides/DATA_DEPENDENCY_CHAIN.md` |

---

## 10. 補足: DB実測カバレッジ一覧（2026-05-18）

| テーブル/カラム | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 用途 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `race_details.exhibition_time` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 候補3 |
| `race_details.st_time` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 候補3 |
| `race_details.tilt_angle` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 候補3 |
| `race_details.parts_replacement` | ❌ | ❌ | ❌ | ❌ | ❌ | △ | 候補2 |
| `race_details.chikusen_time` | ❌ | ❌ | ❌ | ❌ | ❌ | △ | 候補3 |
| `exhibition_data.*` | ❌ | ❌ | ❌ | ❌ | ❌ | △ | 候補2/3（2025+ のみ） |
| `race_conditions.wind_speed` | ❌ | ❌ | ❌ | ❌ | △ | ❌ | 候補4（**使うな**） |
| `ml_analysis_features.wind_*` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 候補4（**こちらを使う**） |
| `ml_analysis_features.wave_height` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 候補4 |
| `racer_features.*` | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | 候補1（要遡及生成） |
| `racer_venue_features.*` | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | 候補1 |
| `trifecta_odds.*` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 候補6 |
| `results.rank` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 全候補・的中判定 |
| `player_escape_stats` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 候補1サブ |
| `stadium_attack_stats` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 候補4サブ |

✅ = 95%以上 / △ = 部分（2,000件未満等） / ❌ = ほぼ0件

---

**最終更新**: 2026-05-18
**次回更新タイミング**: 候補3（展示タイム加工）のTier1テスト完了時
