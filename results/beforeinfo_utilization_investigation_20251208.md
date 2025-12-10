# 直前情報活用状況の詳細調査レポート

**調査日**: 2025-12-08
**調査理由**: ユーザーから「直前情報の活用って既にしていると思ってたんだけど本当にない？」との指摘

---

## 調査結果サマリー

### 結論

**直前情報機能は実装済みだが、現在は実質的に無効化されている**

- [OK] BeforeInfoScorer実装済み（611行）
- [OK] RacePredictor統合済み
- [NG] **デフォルトでBEFOREスコアの重み = 0.0** (完全停止)
- [OK] race_detailsテーブルにデータ存在（790,680件）
- [NG] **戦略Aバックテストでは直前情報を一切使用していない**

---

## 詳細調査結果

### 1. データベース状態

#### race_detailsテーブル
```
レコード数: 790,680件

直前情報カラム:
- exhibition_time (展示タイム)
- st_time (スタートタイミング)
- tilt_angle (チルト角度)
- parts_replacement (部品交換)
- adjusted_weight (調整重量)
- exhibition_course (進入隊形)
- actual_course (実際の進入コース)
- prev_race_course, prev_race_st, prev_race_rank
```

**状態**: [OK] 全データ保持済み

---

### 2. スコアリングエンジン実装状態

#### BeforeInfoScorer (src/analysis/beforeinfo_scorer.py)
```
行数: 611行
実装日: 2025-12-02
状態: 完全実装済み

スコア項目（100点満点）:
- 展示タイム: 25点
- ST: 25点
- 進入隊形: 20点
- 前走成績: 15点
- チルト・風: 10点
- 部品・重量: 5点
```

**状態**: [OK] 完全実装

---

### 3. RacePredictor統合状態

#### 統合処理 (src/analysis/race_predictor.py)

**統合メソッド**: `_apply_beforeinfo_integration()` (行1450-1572)

**統合フロー**:
```python
# 行831: predict_race()内で呼び出し
predictions = self._apply_beforeinfo_integration(
    predictions,
    race_id,
    venue_code
)

# 行1493-1496: BeforeInfoScorerでスコア計算
beforeinfo_result = self.beforeinfo_scorer.calculate_beforeinfo_score(
    race_id=race_id,
    pit_number=pit_number
)
```

**状態**: [OK] 統合実装済み

---

### 4. 機能フラグ設定状態

#### config/feature_flags.py

```python
FEATURE_FLAGS = {
    'dynamic_integration': False,      # 動的合成比（停止中）
    'before_safe_integration': True,   # 安全版直前情報統合（有効）
    'before_safe_st_exhibition': False # ST/展示タイム統合（無効）
}
```

**重要**: `dynamic_integration = False`のため、レガシーモードで動作

---

### 5. 実際のスコア統合式

#### レガシーモード実装 (race_predictor.py 行1547-1553)

```python
# before_safe_integration = True の場合
if use_before_safe:
    # BEFORE_SAFEスコア（進入コース + 部品交換のみ）
    before_safe_result = self.before_safe_scorer.calculate_before_safe_score(...)
    before_safe_score = before_safe_result['total_score']

    # 統合式
    weights = self.safe_integrator.get_weights()
    final_score = pre_score * weights['pre_weight'] + before_safe_score * weights['before_safe_weight']

else:
    # BEFORE完全停止モード
    # BEFORE_SCOREは逆相関（的中率4.1%）のため完全停止
    # PRE_SCORE単体で運用（43.3%的中率）
    final_score = pre_score * 1.0 + before_score * 0.0  # ← BEFOREの重みが0.0
    pred['integration_mode'] = 'before_disabled'
```

**現在の動作**:
- `before_safe_integration = True`により、BEFORE_SAFEスコアのみ使用
- BEFORE_SAFEスコアは**進入コース + 部品交換のみ**（展示タイム、STは含まれない）
- フルのBeforeInfoScorer（展示タイム25点 + ST 25点）は計算されるが、**重みが0.0で実質無効**

---

### 6. バックテストスクリプトの状態

#### scripts/validate_strategy_a.py

**直前情報参照**: なし

**使用データ**:
```python
# 行53-66: race_predictionsテーブルから予測結果を取得
cursor.execute('''
    SELECT pit_number, confidence
    FROM race_predictions
    WHERE race_id = ? AND prediction_type = 'advance'
    ORDER BY rank_prediction
''', (race_id,))
```

**問題点**:
- race_detailsテーブルを一切参照していない
- BeforeInfoScorerを一切呼び出していない
- 直前情報によるフィルタリングなし

**つまり**:
戦略Aの検証（ROI 298.9%, 収支 +380,070円）は、**直前情報を全く使わずに達成した成績**

---

### 7. BetTargetEvaluatorでの直前情報活用

#### src/betting/bet_target_evaluator.py

**has_beforeinfoパラメータの用途**:
```python
# 行318-331: オッズ不明時の処理
if not has_beforeinfo:
    return BetTarget(
        status=BetStatus.CANDIDATE,
        reason='オッズ未取得。直前情報待ち'
    )

# 行338: 購入ステータスの判定
status = BetStatus.TARGET_CONFIRMED if has_beforeinfo else BetStatus.TARGET_ADVANCE
```

**用途**:
- オッズ取得タイミングの管理のみ
- 直前情報による**フィルタリングや条件追加は一切なし**

---

## 実装履歴の確認

### docs/beforeinfo_integration_summary.md

**実装日**: 2025-12-02
**ステータス**: 実装完了・動作確認済み

**統合式の記載**:
```
FINAL_SCORE = PRE_SCORE × 0.6 + BEFORE_SCORE × 0.4  (データ充実度 ≥ 0.5)
FINAL_SCORE = PRE_SCORE × 0.8 + BEFORE_SCORE × 0.2  (データ充実度 < 0.5)
```

**動作検証結果** (11/28 津会場):
```
race_id: 132538 (津 1R)
- 2号艇: PRE 66.2, BEFORE +15.7, FINAL 46.0
- 統合式検証: 66.2 × 0.6 + 15.7 × 0.4 = 46.0 ✓ (完全一致)
```

**検証時の問題点**:
- 検証は「スコア計算が正しいか」のみ
- 「的中率が改善するか」の検証は**未実施**（レース結果確定待ち）

---

## なぜ無効化されたのか

### docs/beforeinfo_integration_summary.md より

**7.1 精度検証（優先度: 高）**:
```
内容: test_prediction_accuracy.py による実測値比較
実施タイミング: 12/2以降のレース結果が確定次第
現状: レース結果未確定のため精度比較未実施
```

**つまり**:
1. 2025-12-02に実装完了
2. スコア計算は正常動作を確認
3. 精度検証（的中率比較）は**結果待ちで未実施**
4. その後、何らかの理由で`before_disabled`モードに変更された可能性
5. または、最初から`before_safe_integration`のみ有効で、フルのBEFOREスコアは使わない設計だった

---

## 実装されている機能（使われていない）

### BeforeInfoScorerの機能（100点満点）

| 項目 | 配点 | 評価内容 | 実装状況 | 使用状況 |
|------|------|---------|---------|---------|
| 展示タイム | 25点 | 相対順位ベース | [OK] 実装済み | [NG] 未使用 |
| ST | 25点 | レンジベース | [OK] 実装済み | [NG] 未使用 |
| 進入隊形 | 20点 | 枠なり逸脱検出 | [OK] 実装済み | [OK] BEFORE_SAFEで使用 |
| 前走成績 | 15点 | 前走ST・着順 | [OK] 実装済み | [NG] 未使用 |
| チルト・風 | 10点 | コース依存評価 | [OK] 実装済み | [NG] 未使用 |
| 部品・重量 | 5点 | 交換ペナルティ | [OK] 実装済み | [OK] BEFORE_SAFEで使用 |

**結論**:
- BEFORE_SAFEは進入隊形 + 部品・重量のみ（30点満点中）
- 展示タイム（25点）とST（25点）という最重要項目が**未使用**

---

## 戦略Aの成績は直前情報なしで達成

### scripts/validate_strategy_a.py の結果

**年間成績**:
- 購入: 637レース
- 的中: 52回
- ROI: 298.9%
- 収支: +380,070円

**この成績に直前情報は一切関与していない**:
- race_detailsテーブル: 参照なし
- BeforeInfoScorer: 呼び出しなし
- 直前情報フィルター: なし

**つまり**:
- 事前予測（PRE_SCORE）のみで達成
- 信頼度（A/B/C/D）+ オッズ範囲 + 1コース級別のみ
- 直前情報を追加すれば、さらなる改善の余地あり

---

## 改善の可能性

### 1. 展示タイム・STフィルターの追加

**期待効果**:
- 展示タイム下位（4-6位）の艇を除外
- ST不良（0.18秒以上）の艇を除外
- → 的中率向上、無駄買い減少

**実装難易度**: 低（データ・スコアリングエンジンは既存）

---

### 2. BeforeInfoScorerのフル活用

**現在のレガシーモード**:
```python
final_score = pre_score * 1.0 + before_score * 0.0  # BEFOREの重みが0
```

**ドキュメント記載の統合式**:
```python
final_score = pre_score * 0.6 + before_score * 0.4  # データ充実度 ≥ 0.5
```

**検証が必要な理由**:
- コメントに「BEFORE_SCOREは逆相関（的中率4.1%）のため完全停止」とある
- しかし、展示タイム・STは有用なはず（ボートレース予想の基本）
- 逆相関になった原因の調査が必要

---

### 3. バックテストスクリプトの修正

**現状**: validate_strategy_a.py は race_predictions から結果を取得

**問題点**:
- race_predictions は過去に保存された予測結果
- 直前情報のON/OFF比較ができない

**解決策**:
- RacePredictorを直接呼び出してリアルタイム予測
- feature_flagsを切り替えて比較
  - before_disabled (現状)
  - before_safe_integration
  - dynamic_integration（要：before_scoreの逆相関問題解決）

---

## 推奨アクション

### 即時実施可能

1. **展示タイム・STフィルターの追加**
   - 戦略A条件に追加条件を設定
   - 例: 「展示タイム4位以下は除外」「ST 0.18秒以上は除外」
   - バックテストで効果検証

2. **BEFORE_SCORE逆相関問題の原因調査**
   - test_prediction_accuracy.py を実行（2025年データで検証可能）
   - BeforeInfoScorerのスコアリングロジック見直し
   - 展示タイム・STの評価式の妥当性確認

---

### 中期実施（原因解明後）

3. **BeforeInfoScorerのフル活用**
   - 逆相関問題が解決したら、統合式を有効化
   - feature_flags: `dynamic_integration = True` または適切な重み設定

4. **バックテストフレームワークの強化**
   - RacePredictorを直接呼び出す新スクリプト作成
   - 直前情報ON/OFF比較
   - 月別・会場別の効果分析

---

## まとめ

### 現状

| 項目 | 状態 | 備考 |
|------|------|------|
| データ保持 | [OK] 完備 | race_details: 790,680件 |
| BeforeInfoScorer | [OK] 実装済み | 611行、100点満点 |
| RacePredictor統合 | [OK] 実装済み | _apply_beforeinfo_integration() |
| 実際の使用 | [NG] 実質停止 | BEFOREの重み = 0.0 |
| バックテスト | [NG] 未使用 | race_detailsを参照していない |
| 戦略A成績 | [OK] 優秀 | ROI 298.9%、ただし直前情報なし |

---

### ユーザーの質問への回答

**「直前情報の活用って既にしていると思ってたんだけど本当にない？」**

→ **回答**: 実装は完了しているが、**現在は実質的に使われていない**

**理由**:
1. BeforeInfoScorer（フル版）は重みが0.0で無効化
2. BEFORE_SAFEは進入コース + 部品交換のみ（展示タイム・ST未使用）
3. バックテストスクリプトは直前情報を一切参照していない
4. 戦略Aの成績（ROI 298.9%）は直前情報なしで達成

**改善の余地**:
- 展示タイム・STフィルターを追加すれば、さらなる精度向上が期待できる
- ただし、BEFORE_SCORE逆相関問題（的中率4.1%）の原因調査が必要

---

**関連ファイル**:
- src/analysis/beforeinfo_scorer.py (実装)
- src/analysis/race_predictor.py (統合処理)
- config/feature_flags.py (フラグ設定)
- docs/beforeinfo_integration_summary.md (実装記録)
- scripts/validate_strategy_a.py (バックテスト)
