# 技術的知見まとめ 2025-11-19

## 1. スコア計算の落とし穴

### 問題: 正規化スケーリングの罠

**発見した問題**:
```python
# 悪い例（修正前）
max_rate = max(win_rates)
min_rate = min(win_rates)
normalized = (rate - min_rate) / (max_rate - min_rate)  # 相対的な位置のみ
score = normalized * max_score
```

この方式の問題点:
- **差が消える**: 1コース55%と6コース3%の差が、単なる0-1の範囲に圧縮される
- **データ依存**: その日のデータによって同じ勝率でもスコアが変わる
- **直感に反する**: 6コースが「その中では低い」だけで絶対的に低くならない

**正しい方式**:
```python
# 良い例（修正後）
score = win_rate * max_score  # 勝率を直接スコアに変換
# 55%勝率 → 55% * 35 = 19.25点
# 3%勝率 → 3% * 35 = 1.05点
```

### 教訓
- 正規化は「相対位置」を表し、「絶対値」を失う
- ボートレースのように明確な統計がある場合は、生データを直接使用すべき

---

## 2. 重みの二重適用問題

### 問題: 複数箇所での重み適用

**発見した問題**:
```python
# race_predictor.py
course_score = self.calculate_course_score(venue_code, course)  # ここで重み適用
# さらに
total_score = course_score * weight  # 二重適用！
```

**修正方法**:
- 各スコア計算関数で重みを適用するか、最後にまとめて適用するか統一
- 現在は各関数で適用し、最後は正規化のみ

### 教訓
- 重みの適用箇所を明確にドキュメント化する
- コード全体を通して一貫したパターンを維持

---

## 3. データベーススキーマの確認不足

### 問題: 存在しないカラムへのアクセス

**エラー例**:
```sql
-- エラー: no such column: first_place
SELECT first_place FROM results
-- 正しくは
SELECT pit_number FROM results WHERE rank = '1'
```

**エラー例2**:
```sql
-- エラー: no such column: venue_code (extracted_rulesテーブル)
-- 実際のスキーマ: rule_name, condition_json, adjustment
```

### 教訓
- 新しいテーブルを使う前に必ずスキーマを確認
- `SELECT * FROM sqlite_master WHERE type='table'` でテーブル一覧
- `PRAGMA table_info(table_name)` でカラム確認

---

## 4. 並列処理のタイムアウト問題

### 問題: 並列スクレイピングでの失敗

**原因**:
- ThreadPoolExecutorで複数会場を同時処理
- サーバー負荷によりタイムアウト（10秒）
- 失敗したレースがリトライされない

**解決策**:
```python
def fetch_venue_races(venue_code):
    races = []
    failed_races = []

    # 第1パス: 全レース取得
    for race_number in range(1, race_count + 1):
        try:
            race_data = scraper.get_race_card(...)
            if race_data:
                races.append(race_data)
            else:
                failed_races.append(race_number)
        except:
            failed_races.append(race_number)

    # 第2パス: 失敗分をリトライ
    if failed_races:
        time.sleep(2)  # サーバー回復待ち
        for race_number in failed_races:
            # リトライ処理
```

### 教訓
- 並列処理では失敗を前提としたリトライ設計が必須
- タイムアウトは余裕を持って設定（10秒→15秒）
- 失敗ログを残して後から調査可能に

---

## 5. 予測分布の異常検知

### 問題: 6号艇47%予測 vs 実際3%

**診断方法**:
```python
# 1. 予測分布を確認
SELECT pit_number, COUNT(*)
FROM race_predictions
WHERE rank_prediction = 1
GROUP BY pit_number

# 2. 実際の勝率を確認
SELECT pit_number, COUNT(*)
FROM results
WHERE rank = '1'
GROUP BY pit_number

# 3. 比較して大きな乖離があれば問題
```

**異常の定義**:
- 1コースが50%未満で予測される → 異常
- 6コースが10%以上で予測される → 異常

### 教訓
- 予測分布は必ず実データと比較する
- 診断スクリプトを用意しておく（diagnose_prediction.py）
- 大きな変更後は必ず分布を確認

---

## 6. 重み設定の管理

### 問題: 設定ファイルと コードの不整合

**発見した問題**:
- `scoring_weights.json`: 3つの重み（course, racer, motor）
- `race_predictor.py`: 5つの重み（+ kimarite, grade）
- デフォルト値の不一致

**解決策**:
```python
# 1. 設定ファイルを正とする
def load_weights(self):
    if not self.config_path.exists():
        return {
            'course_weight': 35.0,
            'racer_weight': 35.0,
            'motor_weight': 20.0,
            'kimarite_weight': 5.0,
            'grade_weight': 5.0
        }

# 2. 古い設定ファイルとの互換性
if 'kimarite_weight' not in self.weights:
    self.weights['kimarite_weight'] = 5.0

# 3. 合計チェック
total = sum(self.weights.values())
if abs(total - 100.0) > 0.1:
    logging.warning(f"重みの合計が100ではありません: {total}")
```

### 教訓
- 設定の「信頼できる情報源」を1つに決める
- 後方互換性のためのフォールバック処理
- バリデーションで不整合を早期発見

---

## 7. ボートレース特有の知見

### コース別勝率（全国平均）

| コース | 勝率 | 2連対率 | 3連対率 |
|--------|------|---------|---------|
| 1コース | 55% | 74% | 82% |
| 2コース | 14% | 40% | 57% |
| 3コース | 12% | 36% | 54% |
| 4コース | 10% | 32% | 50% |
| 5コース | 6% | 22% | 40% |
| 6コース | 3% | 16% | 32% |

### 枠番とコースの関係

- **枠番**: 艇番号（固定）
- **コース**: 進入位置（レースごとに変わる可能性）
- 実際は80-90%が枠番通りに進入（1号艇→1コース）
- 予測時は枠番=コースとして計算可能

### 会場別の特徴

- 会場によってコース別勝率が大きく異なる
- インコース有利な会場（55%以上）とそうでない会場がある
- venue_rulesテーブルで会場別の補正を管理

---

## 8. コードレビューで発見した問題パターン

### パターン1: 無意味な条件分岐

```python
# 悪い例
if condition:
    course = pit_number
else:
    course = pit_number  # 同じ結果
```

### パターン2: マジックナンバー

```python
# 悪い例
concentration_score = min(prob_variance * 500, 100)  # 500の根拠は？

# 良い例
max_variance = 0.139  # 理論的最大値
concentration_score = min((prob_variance / max_variance) * 100, 100)
```

### パターン3: 不完全なデフォルト処理

```python
# 悪い例
if total_races >= 20:
    score += win_rate * 50  # 20未満は0加算

# 良い例
data_weight = min(total_races / 20.0, 1.0)
score += win_rate * 50 * data_weight  # 段階的に加算
```

---

## 9. デバッグ手法

### SQLiteデータ確認

```python
# テーブル一覧
SELECT name FROM sqlite_master WHERE type='table'

# カラム確認
PRAGMA table_info(table_name)

# データ件数確認
SELECT COUNT(*) FROM table_name
```

### 予測診断

```bash
# 診断スクリプト実行
python diagnose_prediction.py

# 確認ポイント
# - 重み設定
# - 過去データの1コース勝率
# - 予測データの1着予測分布
# - サンプルレースのスコア内訳
# - 予測 vs 実結果
```

### バックグラウンドプロセス確認

```bash
# Claude Code内で
/tasks
```

---

## 10. パフォーマンス最適化

### スクレイピング

- 並列処理: 3会場同時（サーバー負荷考慮）
- 待機時間: 0.3秒（通常）、0.5秒（リトライ）
- タイムアウト: 15秒

### 予測生成

- 144レース: 約60秒
- 1レースあたり: 約0.4秒
- ボトルネック: DB読み込み

---

## 11. 今後の改善指針

### 自動テスト追加

```python
def test_score_range():
    """スコアが0-100範囲内であることを確認"""
    predictor = RacePredictor()
    predictions = predictor.predict_race(race_id)
    for pred in predictions:
        assert 0 <= pred['total_score'] <= 100

def test_prediction_distribution():
    """予測分布が実勝率に近いことを確認"""
    # 1号艇が50-65%程度で1着予測されること
    pass
```

### モニタリング

- 毎日の予測分布を記録
- 的中率のトラッキング
- 異常検知アラート

### ドキュメント

- 各関数の重み適用ルールを明記
- スコア計算の数式をコメントで説明
- 設定ファイルの各項目の意味を記載
