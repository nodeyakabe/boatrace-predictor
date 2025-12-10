================================================================================
データベースドキュメント検証レポート
================================================================================

## 検証サマリー

- 総テーブル数: 35
- ソースコードで使用中: 27
- 未使用テーブル数: 6

## 未使用テーブル（要確認）

- motor_features (0 件)
- race_tide_data_backup (12,334 件)
- recommendations (0 件)
- results_backup (24 件)
- venue_features (96 件)
- venue_strategies (24 件)

## 主要テーブル検証

### races (レース基本情報)

- 総カラム数: 14
- ソースコードで使用中: 8

**実際のカラム一覧:**
```
✓ 使用中  created_at
✓ 使用中  grade
✓ 使用中  id
  未使用  is_ladies
  未使用  is_nighter
  未使用  is_rookie
  未使用  is_shinnyuu_kotei
✓ 使用中  race_date
  未使用  race_distance
✓ 使用中  race_grade
✓ 使用中  race_number
  未使用  race_status
✓ 使用中  race_time
✓ 使用中  venue_code
```

**未使用カラム (6個):**

- is_ladies
- is_nighter
- is_rookie
- is_shinnyuu_kotei
- race_distance
- race_status

### trifecta_odds (3連単オッズ)

- 総カラム数: 5
- ソースコードで使用中: 5

**実際のカラム一覧:**
```
✓ 使用中  combination
✓ 使用中  fetched_at
✓ 使用中  id
✓ 使用中  odds
✓ 使用中  race_id
```

### race_predictions (予想データ)

- 総カラム数: 17
- ソースコードで使用中: 17

**実際のカラム一覧:**
```
✓ 使用中  applied_rules
✓ 使用中  confidence
✓ 使用中  course_score
✓ 使用中  created_at
✓ 使用中  generated_at
✓ 使用中  grade_score
✓ 使用中  id
✓ 使用中  kimarite_score
✓ 使用中  motor_score
✓ 使用中  pit_number
✓ 使用中  prediction_type
✓ 使用中  race_id
✓ 使用中  racer_name
✓ 使用中  racer_number
✓ 使用中  racer_score
✓ 使用中  rank_prediction
✓ 使用中  total_score
```

### results (レース結果)

- 総カラム数: 9
- ソースコードで使用中: 8

**実際のカラム一覧:**
```
  未使用  created_at
✓ 使用中  id
✓ 使用中  is_invalid
✓ 使用中  kimarite
✓ 使用中  pit_number
✓ 使用中  race_id
✓ 使用中  rank
✓ 使用中  trifecta_odds
✓ 使用中  winning_technique
```

**未使用カラム (1個):**

- created_at

### entries (出走表)

- 総カラム数: 25
- ソースコードで使用中: 24

**実際のカラム一覧:**
```
✓ 使用中  avg_st
✓ 使用中  boat_number
✓ 使用中  boat_second_rate
✓ 使用中  boat_third_rate
  未使用  created_at
✓ 使用中  f_count
✓ 使用中  id
✓ 使用中  l_count
✓ 使用中  local_second_rate
✓ 使用中  local_third_rate
✓ 使用中  local_win_rate
✓ 使用中  motor_number
✓ 使用中  motor_second_rate
✓ 使用中  motor_third_rate
✓ 使用中  pit_number
✓ 使用中  race_id
✓ 使用中  racer_age
✓ 使用中  racer_home
✓ 使用中  racer_name
✓ 使用中  racer_number
✓ 使用中  racer_rank
✓ 使用中  racer_weight
✓ 使用中  second_rate
✓ 使用中  third_rate
✓ 使用中  win_rate
```

**未使用カラム (1個):**

- created_at

## ドキュメント整合性チェック

### よくある検索パターンの検証

✅ **3連単オッズ**
   - テーブル: `trifecta_odds` ✓ 存在
   - カラム: `odds` ✓ 存在

❌ **2連単オッズ**
   - テーブル: `exacta_odds` ❌ 存在しません
   - カラム: `odds` 

✅ **単勝オッズ**
   - テーブル: `win_odds` ✓ 存在
   - カラム: `odds` ✓ 存在

❌ **レース結果（着順）**
   - テーブル: `results` ✓ 存在
   - カラム: `position` ❌ 存在しません

❌ **払戻金**
   - テーブル: `payouts` ✓ 存在
   - カラム: `payout_amount` ❌ 存在しません

❌ **予想データ**
   - テーブル: `race_predictions` ✓ 存在
   - カラム: `predicted_position` ❌ 存在しません

❌ **出走表**
   - テーブル: `entries` ✓ 存在
   - カラム: `racer_id` ❌ 存在しません

❌ **ST時間**
   - テーブル: `entries` ✓ 存在
   - カラム: `start_timing` ❌ 存在しません

❌ **展示タイム**
   - テーブル: `entries` ✓ 存在
   - カラム: `exhibition_time` ❌ 存在しません

================================================================================
検証完了
================================================================================