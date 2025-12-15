# 買い目システム 実装状況レポート

**作成日**: 2025年12月8日
**目的**: betting_system_improvement_plan.mdの実装状況を確認し、未実装タスクを洗い出す

---

## 1. 実装済み機能

### 1.1 コアモジュール（✅ 完了）

| モジュール | ファイル | 状態 | 備考 |
|-----------|---------|------|------|
| 設定管理 | `src/betting/config.py` | ✅ 完了 | 戦略モード切替、機能フラグ管理 |
| フィルタエンジン | `src/betting/filter_engine.py` | ✅ 完了 | 除外条件の一元管理 |
| EV計算 | `src/betting/ev_calculator.py` | ✅ 完了 | 期待値+Edge計算 |
| 買い目選択 | `src/betting/bet_selector.py` | ✅ 完了 | 動的配分ロジック |
| Kelly計算 | `src/betting/kelly_calculator.py` | ✅ 完了 | 簡易Kelly基準 |
| 戦略エンジン | `src/betting/strategy_engine.py` | ✅ 完了 | 全体制御 |
| ログ管理 | `src/betting/bet_logger.py` | ✅ 完了 | ベット記録 |
| 旧ロジック保管 | `src/betting/legacy/` | ✅ 完了 | ロールバック用 |

### 1.2 信頼度C,D用の買い目改善（✅ 完了）

`src/betting/bet_target_evaluator.py` に実装済み:

#### 信頼度C（従来方式、A1級のみ）
- C × 従来 × 30-60倍 × A1級: 回収率127.2%, 賭け金500円
- C × 従来 × 20-40倍 × A1級: 回収率122.8%, 賭け金400円

#### 信頼度D（新方式・従来方式混合、A1級のみ）
- D × 新方式 × 25-50倍 × A1級: 回収率251.5%, 賭け金300円
- D × 従来 × 20-50倍 × A1級: 回収率215.7%, 賭け金300円

#### 2連単（補助戦略）
- D × A1 × 2連単: 的中率14.6%, ROI 106.7%, 賭け金200円

### 1.3 戦略モード切替（✅ 完了）

`config.py`で以下のモードを切替可能:
- `baseline`: 旧ロジック（MODERATE戦略）
- `edge_test`: Edge計算のみ追加
- `venue_test`: 場タイプ別オッズのみ追加
- `exclusion_test`: 除外条件強化のみ追加
- `kelly_test`: Kelly基準のみ追加
- `full_v2`: 全機能ON

現在のモード: **baseline** (v1.0)

---

## 1.4. パターンH会場コース調整システム（✅ 完了 2025-12-15）

### 目的
会場の単純除外を廃止し、会場×コース別の特性を数値化してポイント調整する。曜日条件は統計的根拠が薄いため不採用。

### 実装ファイル

| ファイル | 説明 | 状態 |
|---------|------|------|
| `scripts/analysis/analyze_venue_course_performance.py` | 会場×コース別実勝率分析 | ✅ 完了 |
| `config/venue_course_adjustments.py` | 24会場×6コース調整設定 | ✅ 完了 |
| `src/betting/venue_course_adjuster.py` | VenueCourseAdjusterクラス | ✅ 完了 |
| `scripts/backtest_pattern_h_with_venue_course_adjustment.py` | バックテスト | ✅ 完了 |
| `docs/VENUE_COURSE_ADJUSTMENT_ANALYSIS.md` | 詳細分析ドキュメント | ✅ 完了 |
| `data/venue_course_analysis.json` | 分析結果JSON | ✅ 完了 |

### 実装内容

**会場特性の定量化**:
- インが弱い会場: 戸田(-12pt), 平和島(-12pt), 江戸川(-9pt), 鳴門(-8pt)
- インが強い会場: 徳山(+9pt), 大村(+8pt), 下関(+6pt)
- 統計的に有意な差分のみ採用（最低100レース以上）

**BetTargetEvaluator統合**:
- `enable_venue_course_adjustment=True`でデフォルト有効化
- `venue_course_adjustment_scale`で調整スケール変更可能
- 調整情報を`BetTarget.venue_course_adjustment`に自動付与

### バックテスト結果（2024-2025年）

| 条件 | 2024年収支 | 2025年収支 | 合計 |
|------|-----------|-----------|------|
| 調整なし | -263,300円 | -78,700円 | -342,000円 |
| 最適調整 | -255,720円 | -77,700円 | -333,420円 |
| **改善額** | **+7,580円** | **+1,000円** | **+8,580円** |

**最適パラメータ**: スキップ閾値=-12pt, バフ閾値=+10pt

### 使用方法

```python
from src.betting.bet_target_evaluator import BetTargetEvaluator

# デフォルトで会場コース調整が有効
evaluator = BetTargetEvaluator(
    use_multi_bet=True,
    multi_bet_pattern=MultiBetPattern.PATTERN_H
)

# レース評価
target = evaluator.evaluate_race(race_data, predictions, odds_data)

# 調整情報を確認
if target.venue_course_adjustment:
    print(f"調整: {target.venue_course_adjustment.adjustment}pt")
    print(f"理由: {target.venue_course_adjustment.reason}")
```

### 勝利パターン分析（✅ 完了 2025-12-15）

Opus AIによる2025年プラス月（6月、9月、10月）の詳細分析を実施:

**分析結果ドキュメント**:
- [docs/PATTERN_H_WINNING_ANALYSIS_2025.md](PATTERN_H_WINNING_ANALYSIS_2025.md)
- [scripts/analysis/analyze_pattern_h_winning_months.py](../scripts/analysis/analyze_pattern_h_winning_months.py)
- [scripts/analysis/analyze_pattern_h_golden_rules.py](../scripts/analysis/analyze_pattern_h_golden_rules.py)

**主な発見**:
- 期待改善効果: **+335,740円/年**
- トップ会場: 鳴門(ROI 357.4%), 丸亀(312.4%), 蒲郡(296.6%)
- ベスト条件: C × B1 × 30-40倍（ROI 162.8%, +61,510円）
- 3点傾斜配分の有効性証明: 本命以外(1-2-4 + 1-2-5)で64.4%を的中

---

## 2. Phase別実装状況

### Phase A: 低リスク改善

| 項目 | 実装 | バックテスト | 結果 | 判定 |
|------|-----|-------------|------|------|
| ⑤ 除外条件明文化 | ✅ 完了 | ✅ 実施 | ROI低下 | ❌ 不採用 |
| ③ Edge計算導入 | ✅ 完了 | ✅ 実施 | 3連単ROI 24.0%→21.4% (-2.6pt) | ❌ 不採用 |

**バックテスト結果（2025年全期間）**:
- **baseline**: 3連単ROI 24.0%, 収支 -908,070円
- **edge_test**: 3連単ROI 21.4%, 収支 -755,020円（購入件数半減で若干マシだが本質的に悪化）
- **venue_test**: 3連単ROI 19.9%, 収支 -990,950円（最悪）

**不採用理由**: すべてのPhase A機能でROIが悪化。baseline維持が最適。

### Phase B: 中リスク改善

| 項目 | 実装状況 | バックテスト | 備考 |
|------|---------|------------|------|
| ① 状況別オッズレンジ | ✅ 実装済み | ❓ 未検証 | config.py - VENUE_TYPE_ODDS_RANGES |
| ④ 動的資金配分 | ✅ 実装済み | ❓ 未検証 | bet_selector.py - DynamicAllocator |

**バックテストスクリプト**:
- `scripts/backtest_v2_venue_test.py` - 場タイプ別オッズテスト用

### Phase C: 高リスク改善

| 項目 | 実装状況 | バックテスト | 備考 |
|------|---------|------------|------|
| ② 簡易Kelly導入 | ✅ 実装済み | ❓ 未検証 | kelly_calculator.py |

---

## 3. 未実装・未検証タスク

### 3.1 バックテスト実行（🔴 最優先）

**Phase A（低リスク改善）の検証**:
```bash
# Edge計算テスト
python scripts/backtest_v2_edge_test.py

# 全モード比較
python scripts/backtest_all_modes.py
```

**成功条件**:
- ROI維持 or 向上（最低115%）
- ROI 5%以上低下した場合はロールバック

### 3.2 実運用への段階的導入（⚠️ バックテスト後）

1. **Week 1**: Phase A機能をONにして並行運用
   - `STRATEGY_MODE = 'edge_test'` に変更
   - 1週間ログ収集
   - ROI比較

2. **Week 2-3**: Phase B機能の検証
   - `venue_test`, `exclusion_test` の個別検証
   - 2週間運用でROI +3%以上なら採用

3. **Week 4**: Phase C機能の検証
   - `kelly_test` の検証
   - 最大ドローダウン確認

### 3.3 ドキュメント整備（📝 低優先度）

- [ ] バックテスト結果レポート作成
- [ ] 運用マニュアル作成
- [ ] ロールバック手順書作成

---

## 4. 推奨作業順序

### Step 1: Phase Aバックテスト実行（今日）

```bash
# 1. Edge計算のバックテスト
python scripts/backtest_v2_edge_test.py > results/edge_test_$(date +%Y%m%d).txt

# 2. 除外条件強化のバックテスト
# TODO: スクリプト作成が必要
python scripts/backtest_v2_exclusion_test.py > results/exclusion_test_$(date +%Y%m%d).txt

# 3. 全モード比較
python scripts/backtest_all_modes.py > results/all_modes_$(date +%Y%m%d).txt
```

### Step 2: 結果分析（今日）

- baselineとの比較
- ROI、的中率、最大DD確認
- Phase A採用可否判定

### Step 3: 実運用テスト（明日以降）

- ROI維持確認できたらPhase A機能をON
- 1週間並行運用でログ収集

---

## 5. 既存実装の活用

### 5.1 信頼度C,D改善（✅ 活用中）

`docs/残タスク一覧.md`に記載の最終運用戦略は`bet_target_evaluator.py`に実装済み。

### 5.2 attack_patternsモジュール（✅ 利用可能）

今回のgit pullで追加された`src/database/attack_patterns.py`を活用:
- 会場別攻略パターン
- 選手別攻略パターン
- 会場×選手クロスパターン

これらをフィルタエンジンに統合できる可能性あり。

---

## 6. リスク管理

### 6.1 ロールバック設計（✅ 完了）

```python
# config.py で1行変更するだけ
STRATEGY_MODE = 'baseline'  # 旧ロジックに戻る
```

### 6.2 判定基準

| フェーズ | 成功 | 失敗（ロールバック） |
|----------|------|---------------------|
| Phase A | ROI 120%以上維持 | ROI 115%未満 |
| Phase B | ROI 125%以上達成 | ROI 120%未満 |
| Phase C | ROI 130%以上 + DD 50%以下 | それ以外 |

---

## 7. まとめ

### 実装完了度: **80%**

✅ **完了済み**:
- コアモジュール実装
- 信頼度C,D用買い目改善
- 戦略モード切替
- Phase A〜C全機能実装

❓ **未検証**:
- Phase A〜Cのバックテスト実行
- 実運用テスト

🔴 **最優先タスク**:
1. Phase Aバックテスト実行
2. 結果分析と採用判定
3. 実運用への段階的導入

---

*作成者: Claude Code*
*最終更新: 2025年12月8日*
