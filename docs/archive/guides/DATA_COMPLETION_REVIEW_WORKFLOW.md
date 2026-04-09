# データ補完後の再検証ワークフロー

**作成日**: 2026-01-30
**目的**: 2021年・2023年データ補完後の「全ロジック包括的再検証」（70時間）を効率的に進めるためのワークフロー

**期待効果**: ROI 160.7% -> 185-200%、年間収支+45-55万円

---

## 全体の流れ

```
Phase 1.5 (データ補完)
      |
      v
+---> Phase 1 (1-3日目、8時間)
|     超高優先度案件の再検証
|           |
|           v
|     Phase 2 (4-7日目、11.5時間)
|     サンプル数不足案件 + 現行条件精緻化
|           |
|           v
|     Phase 3 (8-14日目、16時間)
|     新規分析 + モデル再学習
|           |
|           v
|     Phase 4 (15-30日目、8時間)
+---- 統合テスト・本番反映
```

---

## ワークフロー1: 不採用案の再検証

### 対象

REJECTED_IDEAS.mdに記載された9件の不採用案（RJ-1 ~ RJ-9）

| ID | 不採用案 | 優先度 | 不採用理由 |
|:--:|----------|:------:|-----------|
| RJ-1 | A x 50倍+等 信頼度条件 | 超高 | 計算ミス疑惑（1-2-3固定オッズ） |
| RJ-2 | motor_second_rate + venue_affinity | 高 | 2025年で-4.58pt悪化 |
| RJ-3 | 連帯率フィルター（Motor40%+） | 高 | サンプル27件、黒字3/6年 |
| RJ-4 | D x A1/A2 x モーター40%+ | 高 | サンプル不足（32件） |
| RJ-5 | A x A2 x モーター40%+ | 中高 | 分析1644% vs 実テスト70.3% |
| RJ-6 | Bias Index（順位誤差方向性） | 中 | 年度間で傾向逆転 |
| RJ-7 | Error Variance（着順差分散） | 中 | 一貫した傾向なし |
| RJ-8 | 逃げ率スコアリング | 中 | 既存特徴量と重複 |
| RJ-9 | メタ指数フィルター | 低中 | 仕様と実態の乖離 |

### Step 1: 不採用案の詳細確認

**参照ファイル**: `docs/improvement_attempts/REJECTED_IDEAS.md`

```bash
# REJECTED_IDEAS.mdを開いて対象案件の詳細を確認
# 確認項目:
# - 不採用時の検証日
# - 不採用理由の詳細
# - 当時のサンプル数
# - 当時の年度別ROI・黒字年数
```

**チェック項目**:
- [ ] 不採用理由が「サンプル不足」または「計算ミス」か確認
- [ ] 当時の検証で使用したクエリ・ロジックの問題点を特定
- [ ] データ補完によって解決される見込みがあるか判断

### Step 2: テンプレートで再分析

**使用スクリプト**: `scripts/templates/rejected_idea_review_template.py`

このスクリプトは**正しいオッズ取得ロジック**を組み込み済み:
- オッズは「予測組み合わせ」に対して取得（1-2-3固定ではない）
- 的中判定は「予測組み合わせ == 実際の結果組み合わせ」で判定

**実行例**:

```bash
# RJ-1: A x 50倍+
python scripts/templates/rejected_idea_review_template.py \
    --confidence A \
    --odds-min 50 \
    --odds-max 1000

# RJ-3: 連帯率フィルター（B x 10-30 + モーター40%+）
python scripts/templates/rejected_idea_review_template.py \
    --confidence B \
    --odds-min 10 \
    --odds-max 30 \
    --motor-second-rate-min 40

# RJ-4: D x A1 x モーター40%+
python scripts/templates/rejected_idea_review_template.py \
    --confidence D \
    --odds-min 10 \
    --odds-max 100 \
    --c1-rank A1 \
    --motor-second-rate-min 40

# RJ-5: A x A2 x モーター40%+
python scripts/templates/rejected_idea_review_template.py \
    --confidence A \
    --odds-min 10 \
    --odds-max 100 \
    --c1-rank A2 \
    --motor-second-rate-min 40
```

**出力内容**:
- 6年間の年度別ROI、収支、的中率、サンプル数
- 黒字年数判定
- 採用基準の自動判定
- standard_backtest.pyでの検証コマンド

### Step 3: 採用基準チェック

**採用基準**（全て満たす必要あり）:

| 基準 | 条件 | 根拠 |
|------|------|------|
| 黒字年数 | 4/6年以上 | 年度安定性の担保 |
| ROI | 100%以上 | 黒字条件 |
| 累計収支 | プラス | 実益の確保 |
| サンプル数 | 100件以上 | 統計的信頼性 |

**判定ロジック**:
```python
採用可否 = (
    黒字年数 >= 4 and
    ROI >= 100.0 and
    累計収支 > 0 and
    サンプル数 >= 100
)
```

### Step 4: 採用 or 不採用の決定

#### 採用する場合

1. **standard_backtest.pyに条件を追加**

   `scripts/backtest/standard_backtest.py`の`BET_CONDITIONS`リストに追加:

   ```python
   {
       'name': '新規条件名',
       'confidence': 'A',
       'odds_min': 50,
       'odds_max': 100,
       'c1_rank': ['A1', 'A2', 'B1'],
       'venue_filter': None,
       'use_pattern_h': True,
       'description': '再検証で採用: RJ-X',
   },
   ```

2. **最終検証を実行**

   ```bash
   python scripts/backtest/standard_backtest.py --full
   ```

3. **BET_CONDITIONS.mdに追加**

   `docs/presets/BET_CONDITIONS.md`に条件詳細を記載

4. **知見DBに登録**

   ```bash
   python scripts/register_experiment.py \
       --id "RJ-X" \
       --name "条件名" \
       --category "購入条件" \
       --result "accepted" \
       --effect "+XX.X pt" \
       --keywords "キーワード1,キーワード2"
   ```

#### 不採用を継続する場合

1. **REJECTED_IDEAS.mdに再検証結果を追記**

   ```markdown
   ### 再検証結果（2026-XX-XX）

   **再検証理由**: データ補完後のサンプル数増加

   **結果**:
   - サンプル数: 27件 -> 150件
   - 黒字年数: 3/6年 -> 3/6年（変化なし）
   - ROI: 214.1% -> 185.3%

   **結論**: 不採用を継続
   - 黒字年数が採用基準（4/6年）未達
   - データ補完後も年度安定性に改善なし
   ```

2. **知見DBに登録**

   ```bash
   python scripts/register_experiment.py \
       --id "RJ-X-RETEST" \
       --name "条件名（再検証）" \
       --category "購入条件" \
       --result "rejected" \
       --effect "不採用継続" \
       --keywords "再検証,データ補完"
   ```

---

## ワークフロー2: 新規条件の追加

### Step 1: 仮説立案

**探索観点**:
- 会場別パターン（24会場 x 4信頼度 x 5オッズ帯 = 480セグメント）
- 級別 x モーター条件（A1/A2/B1 x モーター30-45% x 信頼度）
- 季節 x 会場 x 信頼度の交互作用
- 未活用カラム（local_win_rate, f_count, exhibition_course等）の活用

**仮説例**:
- 「会場Xでは信頼度Bの20-30倍帯が異常に高ROI」
- 「冬季の海水面会場では信頼度Cが有効」
- 「モーター2連率40%+かつ1コースA2級は高配当狙いに有効」

### Step 2: 探索分析

**使用スクリプト**: `scripts/templates/rejected_idea_review_template.py`

```bash
# 会場別探索例（鳴門会場でC信頼度を探索）
python scripts/templates/rejected_idea_review_template.py \
    --confidence C \
    --odds-min 30 \
    --odds-max 80 \
    --c1-rank A2 \
    --venue-filter 14

# 季節除外を試す
python scripts/templates/rejected_idea_review_template.py \
    --confidence B \
    --odds-min 50 \
    --odds-max 100 \
    --month-exclude 12 1 2 4
```

**網羅的分析のヒント**:

```bash
# 複数条件を自動化する場合はシェルスクリプトを作成
for conf in A B C D; do
  for odds_min in 10 20 30 50; do
    odds_max=$((odds_min + 20))
    python scripts/templates/rejected_idea_review_template.py \
        --confidence $conf \
        --odds-min $odds_min \
        --odds-max $odds_max \
        2>/dev/null | grep -E "(採用推奨|ROI:)"
  done
done
```

### Step 3: standard_backtest.pyで検証

採用候補が見つかったら必ず最終検証:

```bash
# 条件追加後
python scripts/backtest/standard_backtest.py --full
```

**確認項目**:
- [ ] 6年間ROI
- [ ] 黒字年数（4/6年以上）
- [ ] 月別の安定性（極端な偏りがないか）
- [ ] 他条件との重複がないか

### Step 4: ドキュメント更新と知見登録

**採用時**:
1. `docs/presets/BET_CONDITIONS.md`に追加
2. `scripts/register_experiment.py`で知見DB登録

---

## ワークフロー3: 現行条件の精緻化

### 対象

BET_CONDITIONS.mdに記載された現行10条件

| 条件 | 現状ROI | 精緻化ポイント |
|------|---------|---------------|
| A x A1 x 10-12 | 115.1% | 会場フィルター追加検討 |
| A x A1 x 14-16 | 137.0% | 月除外の検討 |
| A x B1 x モーター40%+ | 196.6% | 閾値微調整 |
| B x 50-100 | 201.1% | 月除外の最適化 |
| B x 30-50 x B1 + 4会場 | 333.6% | 会場追加検討 |
| B x 10-30 x 穴源 x 会場 | 168.8% | bias閾値最適化 |
| C x 20-30 x B1 + 会場 | 144.8% | 会場リスト再選定 |
| 鳴門 x C x A2 x 30-80 | 215.6% | 他会場展開 |
| D x B1 x 40-50 | 173.0% | 2連率閾値最適化 |
| D x 5コース予測 | 103.2% | 他コース条件探索 |

### Step 1: 現行条件のベースライン再取得

```bash
python scripts/backtest/standard_backtest.py --full --save-baseline
```

これにより、データ補完後のベースライン（ROI、収支、年度別成績）を保存

### Step 2: 会場フィルター・閾値の最適化

**グリッドサーチのアプローチ**:

```bash
# 会場フィルターの最適化例（B x 30-50 x B1条件）
# 現行: 津,三国,芦屋,浜名湖

# 全24会場で個別ROIを確認
for venue in $(seq 1 24); do
    python scripts/templates/rejected_idea_review_template.py \
        --confidence B \
        --odds-min 30 \
        --odds-max 50 \
        --c1-rank B1 \
        --venue-filter $venue \
        2>/dev/null | grep -E "ROI:"
done
```

**閾値最適化例**:

```bash
# モーター2連率閾値の最適化
for motor_rate in 35 37 40 42 45; do
    echo "Motor rate >= $motor_rate%"
    python scripts/templates/rejected_idea_review_template.py \
        --confidence A \
        --odds-min 10 \
        --odds-max 100 \
        --c1-rank B1 \
        --motor-second-rate-min $motor_rate \
        2>/dev/null | grep -E "(ROI:|黒字年数)"
done
```

### Step 3: standard_backtest.pyで検証

```bash
# 条件変更後
python scripts/backtest/standard_backtest.py --full

# ベースラインと比較
python scripts/backtest/standard_backtest.py --full --compare
```

### Step 4: 改善が確認できれば条件を更新

**更新箇所**:
1. `scripts/backtest/standard_backtest.py`のBET_CONDITIONS
2. `src/betting/bet_target_evaluator.py`の購入条件
3. `docs/presets/BET_CONDITIONS.md`のドキュメント

---

## Phase 1-4の詳細チェックリスト

### Phase 1（1-3日目、8時間）: 超高優先度案件

#### RJ-1: A x 50倍+等 信頼度条件

**背景**: 分析時ROI 396%が実テストでROI 58.4%に。1-2-3固定オッズでの計算ミス疑惑。

- [ ] REJECTED_IDEAS.mdから詳細確認（セクション0-1参照）
- [ ] 正しいオッズで再計算
  ```bash
  python scripts/templates/rejected_idea_review_template.py \
      --confidence A --odds-min 50 --odds-max 100
  python scripts/templates/rejected_idea_review_template.py \
      --confidence A --odds-min 50 --odds-max 200
  python scripts/templates/rejected_idea_review_template.py \
      --confidence A --odds-min 100 --odds-max 500
  ```
- [ ] 年度別成績を確認（4/6年黒字か）
- [ ] サンプル数を確認（100件以上か）
- [ ] 採用基準を満たす場合: standard_backtest.pyに追加
  ```bash
  python scripts/backtest/standard_backtest.py --full
  ```
- [ ] 採用 or 不採用を決定
- [ ] ドキュメント更新（BET_CONDITIONS.mdまたはREJECTED_IDEAS.md）
- [ ] 知見DB登録

**期待効果**: ROI +20-50pt（最大の改善ポテンシャル）
**工数**: 2-3時間

---

#### RJ-2: motor_second_rate + venue_affinity

**背景**: 2023-2025年3年間では+1.72ptだが、2025年単独では-4.58pt。年度依存性の問題。

- [ ] REJECTED_IDEAS.mdから詳細確認（セクション0-1参照）
- [ ] 6年間完全データで再検証
  - ExtendedScorerのmotor_second_rate, venue_affinityウェイトを変更してテスト
  ```bash
  # feature_flags.pyでウェイト設定を変更後
  python scripts/backtest/standard_backtest.py --full
  ```
- [ ] 年度別の効果を確認（全年でプラスか、逆転がないか）
- [ ] 採用 or 無効化を決定
- [ ] ドキュメント更新
- [ ] 知見DB登録

**期待効果**: ROI +2-5pt
**工数**: 3-4時間

---

#### 潮位補正の効果検証

**背景**: TideAdjuster実装済みだが効果未検証。

- [ ] 潮位補正ON/OFFの比較テスト
  ```bash
  # config/feature_flags.pyのtide_adjustmentをTrue/Falseで切り替え
  python scripts/backtest/standard_backtest.py --full
  ```
- [ ] 海水面9会場での効果測定
- [ ] 潮位レベル別の予測精度分析
- [ ] 採用 or 機能無効化を決定
- [ ] ドキュメント更新

**期待効果**: ROI +2-5pt or 機能無効化
**工数**: 2時間

---

### Phase 2（4-7日目、11.5時間）: サンプル数不足案件 + 現行条件精緻化

#### RJ-3: 連帯率フィルター（Motor40%+）

**背景**: サンプル27件でROI 214.1%、黒字3/6年。サンプル過少で判断困難だった。

- [ ] REJECTED_IDEAS.mdから詳細確認
- [ ] データ補完後のサンプル数を確認
  ```bash
  python scripts/templates/rejected_idea_review_template.py \
      --confidence B \
      --odds-min 10 \
      --odds-max 30 \
      --motor-second-rate-min 40
  ```
- [ ] 100件以上に増加したか確認
- [ ] 黒字年数が改善したか確認
- [ ] 採用 or 不採用を決定
- [ ] ドキュメント更新
- [ ] 知見DB登録

**期待効果**: ROI +10-30pt or 確実な棄却
**工数**: 2時間

---

#### RJ-4: D x A1/A2 x モーター40%+

**背景**: 保留中条件。D x A1（ROI 125.6%、32件）、D x A2（ROI 150.9%、32件）

- [ ] 再検証
  ```bash
  python scripts/templates/rejected_idea_review_template.py \
      --confidence D --odds-min 10 --odds-max 100 \
      --c1-rank A1 --motor-second-rate-min 40

  python scripts/templates/rejected_idea_review_template.py \
      --confidence D --odds-min 10 --odds-max 100 \
      --c1-rank A2 --motor-second-rate-min 40
  ```
- [ ] 100件以上に増加したか確認
- [ ] 採用 or 不採用を決定
- [ ] ドキュメント更新

**期待効果**: 収支+10,000-20,000円/年
**工数**: 1.5時間

---

#### RJ-5: A x A2 x モーター40%+

**背景**: 分析ROI 1644% vs 実テストROI 70.3%の乖離。計算方法の問題か、データ偏りか不明。

- [ ] 再検証
  ```bash
  python scripts/templates/rejected_idea_review_template.py \
      --confidence A --odds-min 10 --odds-max 100 \
      --c1-rank A2 --motor-second-rate-min 40
  ```
- [ ] 乖離の原因を特定
- [ ] 採用 or 確実な棄却
- [ ] ドキュメント更新

**工数**: 2時間

---

#### 現行10条件の精緻化

- [ ] 全条件のベースライン再取得
  ```bash
  python scripts/backtest/standard_backtest.py --full --save-baseline
  ```

**B x 30-50 x B1 + 4会場（年22件 -> サンプル増）**:
- [ ] 会場追加候補の探索
- [ ] 最適会場リストの決定
- [ ] 条件更新

**B x 10-30 x 穴源 x 会場（年19件 -> bias閾値最適化）**:
- [ ] bias閾値の最適化（-0.2, -0.3, -0.4比較）
- [ ] 会場フィルター再選定
- [ ] 条件更新

**その他条件の閾値最適化**:
- [ ] 月除外の見直し
- [ ] オッズ帯の細分化検討

**工数**: 4時間

---

### Phase 3（8-14日目、16時間）: 新規分析 + モデル再学習

#### 会場別 x 信頼度 x オッズ帯の網羅的分析

**目的**: 480セグメント（24会場 x 4信頼度 x 5オッズ帯）を網羅探索

- [ ] 分析スクリプトの準備
- [ ] 480セグメントの一括分析
- [ ] ROI 120%以上 & 黒字4/6年以上のセグメント抽出
- [ ] 有望候補のstandard_backtest.py検証
- [ ] 新規条件2-5件の採用

**期待効果**: 新規条件発見、収支+30,000-80,000円
**工数**: 4時間

---

#### 級別 x モーター条件の再探索

- [ ] モーター閾値30-45%のグリッドサーチ
- [ ] 級別 x 信頼度の組み合わせ探索
- [ ] 最適組み合わせの特定

**工数**: 3時間

---

#### 季節 x 会場 x 信頼度の交互作用分析

- [ ] 月別 x 会場 x 信頼度のROIマトリクス作成
- [ ] 季節除外フィルターの会場別最適化
- [ ] 特定月に強い会場の発見

**工数**: 2.5時間

---

#### RJ-6, RJ-7, RJ-8, RJ-9の再検証

- [ ] Bias Index再検証（RJ-6）
- [ ] Error Variance再検証（RJ-7）
- [ ] 逃げ率スコアリング再検証（RJ-8）
- [ ] メタ指数フィルター再検証（RJ-9）

**工数**: 各1-2時間、合計6.5時間

---

#### LightGBMモデルの再学習

**前提**: Stage1/2/3モデルは2020-2024年データで学習済み。2021年・2023年データ欠損の影響あり。

- [ ] 特徴量生成
  ```bash
  python scripts/training/generate_features.py --start 2020 --end 2025
  ```
- [ ] モデル学習
  ```bash
  python scripts/training/train_conditional_model.py
  ```
- [ ] 効果検証
  ```bash
  python scripts/backtest/standard_backtest.py --full --compare
  ```
- [ ] 改善確認後、モデルを本番採用

**期待効果**: 予測精度+2-3%、ROI +5-10pt
**工数**: 6時間（学習時間含む）

---

### Phase 4（15-30日目、8時間）: 統合テスト・本番反映

#### 全条件の統合バックテスト

- [ ] Phase 1-3で採用した全条件を統合
- [ ] 6年間バックテスト実行
  ```bash
  python scripts/backtest/standard_backtest.py --full
  ```
- [ ] 総合ROI・収支・的中率を確認
- [ ] 条件間の重複・干渉がないか確認

**工数**: 3時間

---

#### 本番コードへの反映

- [ ] `src/betting/bet_target_evaluator.py`の更新
- [ ] `config/feature_flags.py`の更新
- [ ] コードレビュー・テスト

**工数**: 2時間

---

#### ドキュメント更新

- [ ] BET_CONDITIONS.mdの更新
- [ ] REJECTED_IDEAS.mdの更新
- [ ] YEARLY_PERFORMANCE.mdの更新
- [ ] HANDOVER.mdの更新

**工数**: 2時間

---

#### モニタリング準備

- [ ] 1ヶ月間のモニタリング計画策定
- [ ] アラート閾値の設定
- [ ] ロールバック手順の確認

**工数**: 1時間

---

## ツール・スクリプト一覧

| ツール | 用途 | コマンド例 |
|--------|------|----------|
| rejected_idea_review_template.py | 不採用案の再検証 | `python scripts/templates/rejected_idea_review_template.py --confidence A --odds-min 50 --odds-max 100` |
| standard_backtest.py | 最終検証 | `python scripts/backtest/standard_backtest.py --full` |
| standard_backtest.py --compare | ベースライン比較 | `python scripts/backtest/standard_backtest.py --full --compare` |
| register_experiment.py | 知見DB登録 | `python scripts/register_experiment.py --id RJ-1 --result accepted --effect "+20pt"` |
| search_knowledge.py | 知見検索 | `python scripts/search_knowledge.py "モーター"` |

---

## 進捗管理

### 完了基準

| Phase | 完了基準 |
|-------|---------|
| Phase 1 | RJ-1, RJ-2の再検証完了、潮位補正の効果確定 |
| Phase 2 | RJ-3~RJ-5の再検証完了、現行10条件の精緻化完了 |
| Phase 3 | 新規分析4項目完了、RJ-6~RJ-9再検証完了、モデル再学習完了 |
| Phase 4 | 統合テスト完了、本番反映完了、ドキュメント更新完了 |

### KPI目標

| 指標 | 現状 | Phase 1完了後 | Phase 2完了後 | 最終目標 |
|------|------|--------------|--------------|---------|
| ROI | 160.7% | 170-175% | 175-185% | **185-200%** |
| 年間収支 | +332,380円 | +380,000円 | +420,000円 | **+450,000-550,000円** |
| 1着的中率 | 4.56% | 5.0% | 5.5% | **5.5-6.5%** |
| 黒字年数 | 6/6年 | 6/6年維持 | 6/6年維持 | **6/6年維持** |

### 進捗チェックポイント

- [ ] **Day 3**: Phase 1完了、RJ-1/RJ-2の結論確定
- [ ] **Day 7**: Phase 2完了、現行条件の最適化完了
- [ ] **Day 14**: Phase 3完了、モデル再学習完了
- [ ] **Day 30**: Phase 4完了、本番反映完了

---

## リスクと対策

| リスク | 確率 | 対策 |
|-------|:----:|------|
| データ補完後も効果が出ない | 20% | Phase 1で効果測定し、効果薄ならPhase 2以降を縮小 |
| 過学習リスク | 30% | 黒字年数4/6年以上、サンプル100件以上を厳守 |
| 実行工数の超過 | 40% | 優先度順に実行、低優先度は見送り |
| 既存条件のパフォーマンス悪化 | 15% | ベースライン保存、ロールバック手順準備 |

---

## 関連ドキュメント

### 必読
- [DATA_COMPLETION_REVIEW_ITEMS.md](../DATA_COMPLETION_REVIEW_ITEMS.md) - 不採用案・条件再評価の詳細（43.5時間分）
- [COMPREHENSIVE_LOGIC_REVIEW_ITEMS.md](../COMPREHENSIVE_LOGIC_REVIEW_ITEMS.md) - システム全体再点検（27時間分）
- [REJECTED_IDEAS.md](../improvement_attempts/REJECTED_IDEAS.md) - 不採用案の詳細
- [BET_CONDITIONS.md](../presets/BET_CONDITIONS.md) - 現行購入条件

### 参考
- [残タスク一覧.md](../残タスク一覧.md) - 全体タスク管理
- [PREDICTION_LOGIC.md](../architecture/PREDICTION_LOGIC.md) - 予測ロジック
- [DATABASE_SCHEMA.md](../architecture/DATABASE_SCHEMA.md) - DB構造

---

**作成日**: 2026-01-30
**作成者**: Claude Opus 4.5
**次回更新予定**: Phase 1完了後
