# データベーススキーマリファレンス

自動生成日時: 2025-12-10

## 主要テーブル一覧

### races (レース基本情報)
主キー: `id`

| カラム名 | 型 | 説明 |
|---------|-----|------|
| id | INTEGER | レースID（主キー） |
| venue_code | TEXT | 会場コード |
| race_date | DATE | レース日付 |
| race_number | INTEGER | レース番号 |
| race_time | TEXT | レース時刻 |
| race_grade | TEXT | レースグレード |
| grade | TEXT | グレード |
| is_nighter | INTEGER | ナイター開催フラグ |
| is_ladies | INTEGER | レディース戦フラグ |
| is_rookie | INTEGER | 新人戦フラグ |
| is_shinnyuu_kotei | INTEGER | 進入固定フラグ |
| race_distance | INTEGER | レース距離 |
| race_status | TEXT | レース状態 |
| created_at | TIMESTAMP | 作成日時 |

### results (レース結果)
主キー: `id`
外部キー: `race_id` → races.id

| カラム名 | 型 | 説明 |
|---------|-----|------|
| id | INTEGER | 結果ID（主キー） |
| race_id | INTEGER | レースID |
| pit_number | INTEGER | 艇番（1-6） |
| rank | TEXT | 着順（'1', '2', '3', '4', '5', '6', 'F', 'L', 'K', 'S'） |
| is_invalid | INTEGER | 失格・欠場フラグ |
| kimarite | TEXT | 決まり手 |
| winning_technique | INTEGER | 決まり手コード |
| trifecta_odds | REAL | 3連単オッズ |
| created_at | TIMESTAMP | 作成日時 |

**重要:** 着順は`rank`カラムで、文字列型（'1', '2', '3'など）

### entries (出走表)
主キー: `id`
外部キー: `race_id` → races.id

| カラム名 | 型 | 説明 |
|---------|-----|------|
| id | INTEGER | エントリID（主キー） |
| race_id | INTEGER | レースID |
| pit_number | INTEGER | 艇番 |
| racer_number | INTEGER | 登録番号 |
| racer_name | TEXT | 選手名 |
| racer_rank | TEXT | 級別（A1, A2, B1, B2） |
| racer_age | INTEGER | 年齢 |
| racer_weight | REAL | 体重 |
| racer_home | TEXT | 支部 |
| motor_number | INTEGER | モーター番号 |
| boat_number | INTEGER | ボート番号 |
| win_rate | REAL | 全国勝率 |
| second_rate | REAL | 全国2連対率 |
| third_rate | REAL | 全国3連対率 |
| local_win_rate | REAL | 当地勝率 |
| local_second_rate | REAL | 当地2連対率 |
| local_third_rate | REAL | 当地3連対率 |
| motor_second_rate | REAL | モーター2連対率 |
| motor_third_rate | REAL | モーター3連対率 |
| boat_second_rate | REAL | ボート2連対率 |
| boat_third_rate | REAL | ボート3連対率 |
| avg_st | REAL | 平均ST |
| f_count | INTEGER | フライング回数 |
| l_count | INTEGER | 出遅れ回数 |
| created_at | TIMESTAMP | 作成日時 |

### race_details (直前情報・展示データ)
主キー: `id`
外部キー: `race_id` → races.id

| カラム名 | 型 | 説明 |
|---------|-----|------|
| id | INTEGER | 詳細ID（主キー） |
| race_id | INTEGER | レースID |
| pit_number | INTEGER | 艇番 |
| exhibition_time | REAL | 展示タイム（秒） |
| st_time | REAL | スタートタイミング（秒、0に近いほど良い） |
| tilt_angle | REAL | チルト角度 |
| parts_replacement | TEXT | 部品交換情報 |
| actual_course | INTEGER | 実際の進入コース |
| exhibition_course | INTEGER | 展示航走での進入コース |
| chikusen_time | REAL | 直線タイム |
| isshu_time | REAL | 一周タイム |
| mawariashi_time | REAL | まわり足タイム |
| adjusted_weight | REAL | 調整体重 |
| prev_race_course | INTEGER | 前走コース |
| prev_race_st | REAL | 前走ST |
| prev_race_rank | INTEGER | 前走着順 |
| created_at | TIMESTAMP | 作成日時 |

**重要:**
- 展示タイムは`exhibition_time`カラム
- ST時間は`st_time`カラム
- 着順情報は`results`テーブルを参照

### race_predictions (予想データ)
主キー: `id`
外部キー: `race_id` → races.id

| カラム名 | 型 | 説明 |
|---------|-----|------|
| id | INTEGER | 予想ID（主キー） |
| race_id | INTEGER | レースID |
| pit_number | INTEGER | 艇番 |
| racer_number | INTEGER | 登録番号 |
| racer_name | TEXT | 選手名 |
| rank_prediction | INTEGER | 予想着順 |
| total_score | REAL | 総合スコア |
| racer_score | REAL | 選手スコア |
| motor_score | REAL | モータースコア |
| course_score | REAL | コーススコア |
| kimarite_score | REAL | 決まり手スコア |
| grade_score | REAL | グレードスコア |
| confidence | TEXT | 信頼度（A, B, C, D, E） |
| applied_rules | TEXT | 適用ルール |
| prediction_type | TEXT | 予測タイプ |
| generated_at | TIMESTAMP | 生成日時 |
| created_at | TIMESTAMP | 作成日時 |

## よくある誤り

### ❌ 間違い
```python
# 着順を取得
cursor.execute("SELECT * FROM race_details WHERE finish_position = 1")  # ❌ race_detailsに着順カラムはない

# 展示タイムを取得
cursor.execute("SELECT * FROM entries WHERE exhibition_time IS NOT NULL")  # ❌ entriesに展示タイムはない
```

### ✅ 正しい
```python
# 着順を取得
cursor.execute("SELECT * FROM results WHERE rank = '1'")  # ✅ resultsテーブルのrankカラム

# 展示タイムを取得
cursor.execute("SELECT * FROM race_details WHERE exhibition_time IS NOT NULL")  # ✅ race_detailsテーブル
```

## テーブル間の関係

```
races (id)
  ├─ entries (race_id) - 出走表
  ├─ race_details (race_id) - 直前情報
  ├─ results (race_id) - 結果
  ├─ race_predictions (race_id) - 予想
  └─ trifecta_odds (race_id) - オッズ
```

## 重要な注意事項

1. **主キーの命名**: ほとんどのテーブルで`id`が主キー、`race_id`が外部キー
2. **着順データ**: `results`テーブルの`rank`カラム（文字列型）
3. **展示データ**: `race_details`テーブルに格納
4. **艇番**: `pit_number`カラム（1-6の整数）
5. **選手番号**: `racer_number`カラム（登録番号）
