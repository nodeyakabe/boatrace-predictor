# 継続作業計画 - 2025-12-08

## 現在の状況

### 完了済み
- ✅ 直前情報活用状況調査
- ✅ BEFORE_SCORE逆相関問題の原因特定（実際は強い正相関）
- ✅ 正規化統合の実装（src/analysis/race_predictor.py）
- ✅ Feature Flags設定（normalized_before_integration: True）
- ✅ 検証スクリプト作成（validate_normalized_integration.py）

### 実行中
- ⏳ 検証スクリプト実行（残り時間: 約1時間）
  - BEFORE無効 vs 正規化統合の的中率比較
  - 200レース × 2パターン = 400レース分の予測

---

## 継続作業の流れ

### Step 1: 検証完了待機（自動）
- scripts/validate_normalized_integration.py の完了を待つ
- 完了予定: 約1時間後

### Step 2: 検証結果の確認
- results/normalized_integration_validation_20251208.txt を読み込み
- 的中率向上を確認
  - 期待: +3-8%の向上
  - 判定基準: +1%以上なら成功

### Step 3: 効果確認テストの実施

#### テスト内容
1. **戦略Aバックテストの再実行（正規化統合ON）**
   - scripts/validate_strategy_a.py を修正
   - RacePredictorを直接呼び出すように変更
   - 正規化統合有効で2025年データを検証

2. **月別パフォーマンス分析**
   - 各月の的中率・ROI・収支を算出
   - BEFORE無効時との比較

3. **統合前後の比較レポート作成**
   - 年間収支の改善額
   - ROI向上率
   - 的中回数の増加

---

## 実施するスクリプト

### 1. 戦略Aバックテスト（正規化統合版）

**新規作成**: `scripts/validate_strategy_a_with_normalized.py`

**内容**:
- RacePredictorを直接呼び出し
- normalized_before_integration = True で実行
- 戦略A 8条件で購入対象を絞り込み
- 2025年全期間での成績を算出

**期待結果**:
- 年間的中: 52回 → 55-58回
- ROI: 298.9% → 320-380%
- 収支: +380,070円 → +420,000-470,000円

### 2. 月別比較レポート

**新規作成**: `scripts/monthly_comparison_normalized.py`

**内容**:
- BEFORE無効 vs 正規化統合の月別比較
- 各月の的中率・ROI・収支を算出
- 黒字月率の比較

### 3. 最終統合レポート

**新規作成**: `results/normalized_integration_final_report_20251208.md`

**内容**:
- 実装背景
- 検証結果
- 効果測定結果
- 本番運用推奨度
- ロールバック手順

---

## 判定基準

### 成功条件（本番運用推奨）
- 1着的中率向上: +1%以上
- 年間収支改善: +20,000円以上
- ROI改善: +10%以上

### 条件付き成功（様子見）
- 1着的中率向上: +0.5%以上
- 年間収支改善: +10,000円以上
- 月別で改悪月が3ヶ月以下

### 失敗条件（ロールバック）
- 1着的中率低下: -0.5%以下
- 年間収支悪化: -10,000円以下
- 月別で改悪月が6ヶ月以上

---

## ロールバック手順（失敗時）

1. config/feature_flags.py を編集
   ```python
   'normalized_before_integration': False
   ```

2. システム再起動（または次回予測時に自動適用）

3. before_safe_integration を再有効化するか判断
   - 進入コース + 部品交換のみの限定版
   - または完全にBEFORE無効を継続

---

## 作業完了後の報告内容

### レポート構成

1. **検証結果サマリー**
   - BEFORE無効 vs 正規化統合の比較
   - 的中率・ROI・収支の差分

2. **効果測定結果**
   - 戦略A成績の変化
   - 月別パフォーマンス
   - 黒字月率の改善

3. **推奨事項**
   - 本番運用可否
   - パラメータ調整の必要性
   - 追加検証の要否

4. **次のアクション**
   - 即時実施推奨
   - 中期検討事項
   - 長期改善案

---

## 作業スケジュール

| 時刻 | 作業内容 | 所要時間 |
|------|---------|---------|
| 現在+1h | 検証完了 | - |
| 現在+1h | 検証結果確認 | 5分 |
| 現在+1h5m | 戦略Aバックテスト実行 | 30分 |
| 現在+1h35m | 月別比較分析 | 20分 |
| 現在+1h55m | 最終レポート作成 | 15分 |
| 現在+2h10m | **作業完了・報告** | - |

**完了予定**: 約2時間10分後

---

## 成果物リスト

### スクリプト
1. scripts/validate_strategy_a_with_normalized.py
2. scripts/monthly_comparison_normalized.py

### レポート
1. results/normalized_integration_validation_20251208.txt（検証結果）
2. results/strategy_a_normalized_20251208.txt（戦略A成績）
3. results/monthly_comparison_20251208.txt（月別比較）
4. results/normalized_integration_final_report_20251208.md（最終報告）

---

## 備考

- すべての作業は自動で実施
- 各ステップの結果をファイルに保存
- 最終的に総合レポートを作成
- 失敗時は自動でロールバック推奨を報告

**開始**: 検証スクリプト完了次第
**完了目標**: 現在時刻 + 2時間10分
