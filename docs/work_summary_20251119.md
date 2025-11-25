# 作業まとめ 2025-11-19

## 本日の作業内容

### 1. スクレイピング失敗の調査と修正

**問題**: 会場19（下関）10Rと会場22（福岡）6Rの2レースが取得できなかった

**原因**: 並列処理時のタイムアウト

**修正内容**:
- `src/scraper/bulk_scraper_parallel.py`: リトライロジック追加（失敗したレースを再取得）
- `src/scraper/base_scraper_v2.py`: タイムアウトを10秒→15秒に延長
- `fix_missing_races.py`: 欠損レース復旧スクリプト作成

**結果**: 144/144レース取得成功

---

### 2. 法則解析エラーの修正

**問題**: 「一部の法則解析に失敗しました」エラー

**修正内容**:
- `reanalyze_all.py`: 新規作成（ルール抽出とvenue_rulesへの移行）
- SQLスキーマの修正（rule_name, condition_json, adjustmentを使用）

**結果**: 64件のルール抽出、66件のvenue_rules移行完了

---

### 3. レース一覧の複数買い目表示

**修正内容**:
- `ui/components/unified_race_list.py`: 2段階戦略表示を追加
  - 3連単5点 + 3連複1点の表示
  - カードビューとテーブルビューの両方に対応

---

### 4. 予測精度の問題修正（メイン作業）

**問題**: Top-1正解率10%、6号艇が47.2%予測されるが実際は2.9%

**根本原因**:
1. コーススコア計算の正規化スケーリングに欠陥
2. 総合スコアが0-100に正規化されていない
3. race_scorer係数が武断的（500, 150, 110）

**修正ファイル**:

| ファイル | 修正内容 |
|---------|---------|
| `src/analysis/race_predictor.py` | コーススコア計算修正、スコア正規化(0-100)、重み検証追加 |
| `src/betting/race_scorer.py` | 係数を理論的な値に修正（max_variance=0.139） |
| `src/utils/scoring_config.py` | 5つの重み定義追加（kimarite_weight, grade_weight） |
| `config/scoring_weights.json` | 新しい重み設定（35/35/20/5/5） |

**結果**:
| 号艇 | 修正前 | 修正後 | 実際の勝率 |
|------|--------|--------|-----------|
| 1号艇 | 1.4% | **61.1%** | ~55% |
| 6号艇 | 47.2% | **4.9%** | ~3% |

---

### 5. 予測ロジック包括的レビュー

発見した問題12件をリストアップ：

**高優先度（修正済み）**:
1. コース/枠番混同 → 修正済
2. 総合スコア未正規化 → 修正済
3. race_scorer係数問題 → 修正済

**中優先度（未対応）**:
- データ不足時の処理不統一（racer_analyzer.py）
- モータースコア係数根拠不明（motor_analyzer.py）
- 信頼度制限ロジック不完全（race_predictor.py）
- 確信度計算のエントロピー式（race_scorer.py）

---

## 作成したファイル

| ファイル | 目的 |
|---------|-----|
| `debug_missing_races.py` | 欠損レース調査 |
| `fix_missing_races.py` | 欠損レース復旧 |
| `reanalyze_all.py` | 法則再解析 |
| `diagnose_prediction.py` | 予測精度診断 |
| `regenerate_predictions.py` | 予測再生成 |

---

## 現在の重み設定

```json
{
  "course_weight": 35,
  "racer_weight": 35,
  "motor_weight": 20,
  "kimarite_weight": 5,
  "grade_weight": 5,
  "total": 100
}
```

---

## 明日以降の作業項目

### 優先度: 高

1. **データ不足時の処理改善**
   - 場所: `src/analysis/racer_analyzer.py:447-484`
   - 内容: データ平滑化（スムージング）とデータ信頼度ウェイト追加
   - 理由: 新人選手や少数出場選手が過度に低評価される

2. **モータースコア係数の見直し**
   - 場所: `src/analysis/motor_analyzer.py:306-326`
   - 内容: 2連対率40%で10点満点は過度に厳しい
   - 例: `score += min(place_rate_2 * 25, 10.0)` の25は根拠不明

3. **信頼度判定の改善**
   - 場所: `src/analysis/race_predictor.py:486-488`
   - 内容: データ量に応じた信頼度上限を動的に設定

### 優先度: 中

4. **race_scorerエントロピー計算修正**
   - 場所: `src/betting/race_scorer.py:257-291`
   - 内容: max_entropy計算式の修正

5. **ScoringConfig.save_weights()の拡張**
   - 場所: `src/utils/scoring_config.py:48`
   - 内容: 5つの重みを保存できるように拡張

### 優先度: 低

6. **型の統一**
   - コース番号をintで統一（現在は文字列混在の可能性）

7. **エッジケース処理**
   - 確率合計が1でない場合の処理追加

---

## テスト推奨事項

修正後に以下をテスト：

1. **スコア範囲テスト**: 全レースのスコアが0-100範囲内
2. **予測分布テスト**: 1号艇が50-60%程度で1着予測
3. **データ不足テスト**: 新人選手のスコアが極端に低くない
4. **信頼度テスト**: A-E判定が的中率と相関

---

## 診断スクリプトの使い方

```bash
# 予測精度診断
python diagnose_prediction.py

# 予測再生成
python regenerate_predictions.py

# 法則再解析
python reanalyze_all.py
```

---

## 注意事項

- Streamlit UIは複数のバックグラウンドプロセスで実行中
- バックグラウンドタスクを確認: `/tasks` コマンド
- 既存の設定ファイル（scoring_weights.json）は新しい5つの重み形式に更新済み
