# 再予測機能セットアップガイド

## 概要

再予測機能により、レース直前データ（展示タイム、天候、実際の進入コースなど）を使って初期予測を更新できます。

## セットアップ手順

### 1. データベース拡張

```bash
# 再予測用テーブルを追加
python migrations/add_reprediction_tables.py

# race_predictionsテーブルにスコア内訳カラムを追加
python migrations/add_score_breakdown_columns.py
```

### 2. 既存予測のスコア内訳を埋める（オプション）

既にrace_predictionsに保存済みの予測がある場合、スコア内訳を埋めることができます。

```bash
# 既存予測のスコア内訳を再計算（時間がかかります）
python migrations/backfill_score_breakdowns.py
```

**注意**: これは既存データ用です。今後生成する予測は自動的にスコア内訳が保存されます。

## 使い方

### 基本的な流れ

```bash
# 1. 初期予測を生成
python generate_one_date.py 2025-11-25

# 2. レース直前データを収集
# race_idを取得（例: SQLiteブラウザやPythonで確認）

# 展示データを入力
python collect_exhibition_data.py <race_id>

# レース条件を入力
python collect_race_conditions.py <race_id>

# 実際の進入コースを入力
python collect_actual_courses.py <race_id>

# 3. 予測を更新
python repredict_race.py <race_id>
```

### race_idの取得方法

```python
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 2025-11-25の最初のレース
cursor.execute("""
    SELECT id, venue_code, race_number
    FROM races
    WHERE race_date = '2025-11-25'
    ORDER BY venue_code, race_number
    LIMIT 1
""")
print(cursor.fetchone())
conn.close()
```

## データ収集の詳細

### 展示データ

- 展示タイム: 6.0～8.0秒程度
- スタート評価: 1～5（5が最良）
- ターン評価: 1～5（5が最良）
- 体重変化: ±5kg程度

### レース条件

- 天候: 晴 / 曇 / 雨 / 雪
- 風向: 無風 / 向い風 / 追い風 / 横風
- 風速: m/s
- 波高: cm
- 気温: ℃
- 水温: ℃

### 実際の進入コース

通常は艇番=コース番号ですが、「進入変化」があった場合のみ変更します。

## 補正ロジック

### 展示タイムによる補正

- 平均より0.3秒以上速い: モーター+8点、信頼度+0.08
- 平均より0.15秒速い: モーター+4点、信頼度+0.04
- 平均より0.3秒以上遅い: モーター-8点、信頼度-0.05
- 平均より0.15秒遅い: モーター-4点、信頼度-0.03

### 進入変化による補正

実際の進入コースが予定と異なる場合、会場の歴史データに基づいて補正。

### 天候・風向による補正

- 向い風（3.0m/s以上）: インコース+2点
- 追い風（3.0m/s以上）: インコース-2点
- 荒天: 信頼度-0.03

## テスト

サンプルデータでテストできます:

```bash
python test_reprediction_sample.py 15022
```

## トラブルシューティング

### エラー: "初期予測が見つかりません"

先に初期予測を生成してください:
```bash
python generate_one_date.py <日付>
```

### エラー: "レース直前データがありません"

少なくとも1つのデータ（展示/条件/進入）を収集してください。

### スコアがマイナスになる

補正が大きすぎる場合、スコアがマイナスになることがあります。これは正常な動作です。

## 出力例

```
【1号艇】
  スコア: 45.9 → 53.9 (+8.0)
  信頼度: D → C ⚠ 変更
  内訳:
    モーター: 15.0 → 23.0 (+8.0)
  理由:
    • 展示タイム優秀（平均より0.32秒速い）
    • スタート評価良好（4/5）
    • 向い風4.2m/s（イン有利）
```

## データベース構造

再予測機能で追加されたテーブル:

- `exhibition_data`: 展示航走データ
- `race_conditions`: レース条件（天候・風向など）
- `actual_courses`: 実際の進入コース
- `prediction_history`: 予測履歴（初期/更新の比較用）

race_predictionsに追加されたカラム:

- `course_score`: コース点
- `racer_score`: 選手点
- `motor_score`: モーター点
- `kimarite_score`: 決まり手点
- `grade_score`: グレード点

## 今後の拡張

現在は手動データ入力ですが、将来的にはWebスクレイピングで自動化できます。

データソース例:
- 展示データ: 公式サイトの展示航走結果
- レース条件: 公式サイトのレース情報
- 実際の進入: スタート展示の進入隊形
