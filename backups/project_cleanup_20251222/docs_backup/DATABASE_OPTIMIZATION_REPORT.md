# データベース構造最適化レポート

**作成日**: 2025-12-12
**分析対象**: ボートレース予測システム データベース（35テーブル）
**データベース**: data/boatrace.db

---

## エグゼクティブサマリー

### 発見された問題点の総数
- **重複・冗長性の問題**: 8件（うち高優先度2件）
- **空テーブル（0件）**: 6テーブル
- **未使用/低使用カラム**: 12カラム
- **インデックス最適化の機会**: 5件

### 優先度の高い改善項目
1. **races.race_grade と races.grade の重複** - 即座に対応推奨
2. **results.winning_technique と results.kimarite の重複** - 即座に対応推奨
3. **空テーブルの削除検討** - 計画的に実施
4. **バックアップテーブルの整理** - 計画的に実施

### 期待される効果
- ストレージ使用量: 約5-10%削減見込み
- クエリパフォーマンス: JOINの簡素化により改善
- 保守性: コードの明確化、バグリスクの低減

---

## 1. 重複・冗長性の問題

### 問題1: races.race_grade と races.grade の重複 [高優先度]

- **影響範囲**: `races` テーブル（133,327件）
- **現状**:
  - `race_grade` カラム: 主に予測処理で使用（race_predictor.py line 695, 703）
  - `grade` カラム: データ保存時に使用（data_manager.py line 214）
  - コードでは `grade = race_data.get('grade', race_grade or '')` のようにフォールバック処理
- **問題点**:
  - 同じ情報が2つのカラムに格納されている
  - どちらが正式かが不明確
  - 使用箇所によって参照カラムが異なる
- **推奨対策**:
  1. `race_grade` に統一（既存の使用箇所が多い）
  2. `grade` カラムを削除
  3. 参照箇所を全て `race_grade` に更新
- **優先度**: 高
- **期待効果**: コードの明確化、保守性向上、潜在的バグの防止

```sql
-- 移行手順
-- 1. gradeのデータをrace_gradeにマージ（race_gradeがNULL/空の場合のみ）
UPDATE races SET race_grade = grade WHERE race_grade IS NULL OR race_grade = '';

-- 2. 検証後、gradeカラムを削除
ALTER TABLE races DROP COLUMN grade;
```

---

### 問題2: results.winning_technique と results.kimarite の重複 [高優先度]

- **影響範囲**: `results` テーブル（779,318件）
- **現状**:
  - `winning_technique`: INTEGER型、data_manager.pyでrank=1の時のみ保存
  - `kimarite`: TEXT型、「逃げ」「差し」「まくり」等のテキスト形式
  - 両方同時に保存される（data_manager.py line 568-575）
- **問題点**:
  - 同じ「決まり手」情報が2つの形式で保存
  - `winning_technique`はINTEGERだが数値コードの定義が不明確
  - `kimarite`の方が可読性が高く、実際の使用頻度も高い
- **推奨対策**:
  1. `kimarite` カラムに統一（TEXT形式の方が可読性・保守性が高い）
  2. `winning_technique` カラムを削除
  3. 必要に応じてコード変換用のマスタテーブルを作成
- **優先度**: 高
- **期待効果**: データの一貫性、保守性向上

```sql
-- 検証後、winning_techniqueカラムを削除
ALTER TABLE results DROP COLUMN winning_technique;
```

---

### 問題3: race_conditions と weather テーブルの重複

- **影響範囲**:
  - `race_conditions`: 130,792件（レース単位）
  - `weather`: 9,018件（日付・会場単位）
- **現状**:
  - 両テーブルに `wind_speed`, `wave_height`, `wind_direction`, `temperature`, `water_temperature` が存在
  - `race_conditions` は直前情報ページからのリアルタイム取得
  - `weather` は日単位の概要データ
- **問題点**:
  - 同じ属性が2つのテーブルに存在
  - クエリで両方参照する際の優先度が不明確
  - race_predictor.py では `race_conditions` を優先、フォールバックで `weather` を使用
- **推奨対策**:
  - 現状維持（用途が異なるため）
  - ただし、役割の文書化と命名の明確化を推奨
  - `race_conditions` -> `race_weather_realtime` のような名前変更を検討
- **優先度**: 低（現状は適切に使い分けられている）
- **期待効果**: 将来の混乱防止

---

### 問題4: venue_data と venue_strategies の類似性

- **影響範囲**:
  - `venue_data`: 24件
  - `venue_strategies`: 24件
- **現状**:
  - 両方とも24会場分のマスタデータ
  - `venue_data`: 水質、潮差、モーター型式、コース勝率、レコード情報
  - `venue_strategies`: 戦略的特徴（コース傾向、決まり手傾向、風の傾向）
- **問題点**:
  - `water_type` が両方に存在
  - 会場の静的情報が分散している
- **推奨対策**:
  - 統合を検討（ただし役割が異なるため慎重に）
  - `venue_data` に戦略情報を統合するか、外部キー参照で関連付け
- **優先度**: 低
- **期待効果**: マスタデータの一元管理

---

### 問題5: extracted_rules と venue_rules の関係性

- **影響範囲**:
  - `extracted_rules`: 308件
  - `venue_rules`: 308件
- **現状**:
  - 両テーブルが同じ件数
  - `extracted_rules`: ルール抽出処理の結果（rule_extractor.py）
  - `venue_rules`: 会場ルール（rule_validator.py, rule_based_engine.py）
- **問題点**:
  - データの重複の可能性
  - 同期処理の必要性が不明確
- **推奨対策**:
  1. 両テーブルの実データを比較
  2. 重複している場合は統合
  3. 用途が異なる場合は命名を明確化
- **優先度**: 中
- **期待効果**: ルール管理の一元化

---

### 問題6: race_predictions と prediction_history の関係

- **影響範囲**:
  - `race_predictions`: 196,692件
  - `prediction_history`: 18件
- **現状**:
  - `race_predictions`: 最新の予測結果
  - `prediction_history`: 予測履歴の保存（prediction_updater.py で管理）
- **問題点**:
  - `prediction_history` は18件のみで、履歴保存が機能していない可能性
  - 構造はほぼ同じで重複している
- **推奨対策**:
  1. `prediction_history` のデータ蓄積状況を確認
  2. 履歴機能が不要なら削除、必要なら蓄積処理を修正
- **優先度**: 中
- **期待効果**: 予測履歴の適切な管理

---

### 問題7: actual_courses と race_details.actual_course の重複

- **影響範囲**:
  - `actual_courses` テーブル: 6件
  - `race_details.actual_course` カラム: 790,680件中に存在
- **現状**:
  - `actual_courses` テーブルはほぼ未使用（6件のみ）
  - `race_details.actual_course` が実際のデータ保存先
- **問題点**:
  - テーブルとカラムで情報が分散
  - `actual_courses` テーブルは事実上未使用
- **推奨対策**:
  - `actual_courses` テーブルの削除を検討
  - `race_details.actual_course` に統一
- **優先度**: 中
- **期待効果**: 冗長なテーブルの削除

---

### 問題8: exhibition_data と race_details の重複

- **影響範囲**:
  - `exhibition_data`: 6件
  - `race_details.exhibition_time`: 790,680件中に存在
- **現状**:
  - `exhibition_data` はほぼ未使用（6件のみ）
  - `race_details` に `exhibition_time`, `tilt_angle`, `st_time` 等が存在
- **問題点**:
  - 展示データが2つの場所に分散
  - `exhibition_data` には追加情報（start_timing, turn_quality, weight_change）があるが、ほぼ未使用
- **推奨対策**:
  - 追加情報が必要なら `race_details` にカラム追加
  - `exhibition_data` テーブルの削除を検討
- **優先度**: 中
- **期待効果**: 展示データの一元管理

---

## 2. 空テーブル・未使用テーブル

### 空テーブル一覧（0件）

| テーブル名 | 用途 | 状態 | 推奨対策 |
|-----------|------|------|----------|
| venue_attack_patterns | 会場の攻撃パターン | 構造のみ存在、データ未投入 | 使用予定があれば残す、なければ削除 |
| venue_racer_patterns | 会場×選手パターン | 構造のみ存在 | 同上 |
| racer_attack_patterns | 選手の攻撃パターン | 構造のみ存在 | 同上 |
| motor_features | モーター特徴量 | 構造のみ存在 | 同上 |
| win_odds | 単勝オッズ | スクレイパーは存在するがデータ未取得 | データ取得処理を実行するか削除 |
| recommendations | 推奨情報 | 構造のみ存在 | 使用予定を確認 |

**推奨対策**:
- 開発予定がある場合: 残す
- 開発予定がない場合: 削除してスキーマを簡素化

---

### バックアップ・一時テーブル

| テーブル名 | 件数 | 状態 | 推奨対策 |
|-----------|------|------|----------|
| results_backup | 24件 | 古いバックアップ | 不要なら削除 |
| race_tide_data_backup | 12,334件 | 潮汐データバックアップ | 本テーブルへの統合後に削除 |

---

## 3. 未使用・低使用カラム

### races テーブル

| カラム名 | 使用状況 | 推奨対策 |
|---------|---------|----------|
| race_distance | 保存されるが読み取り箇所が少ない | 使用するか判断 |
| grade | race_gradeと重複 | 削除推奨 |

### results テーブル

| カラム名 | 使用状況 | 推奨対策 |
|---------|---------|----------|
| winning_technique | kimariteと重複、INTEGER型 | 削除推奨 |
| trifecta_odds | 結果テーブルにオッズ？ | 用途確認、不要なら削除 |

### racers テーブル

| カラム名 | 使用状況 | 推奨対策 |
|---------|---------|----------|
| second_rate | NULL多数 | entriesテーブルの方が充実 |
| third_rate | NULL多数 | 同上 |
| ability_index | 一部使用 | 計算方法の文書化推奨 |
| wins | 多数NULL | 同上 |

### weather テーブル

| カラム名 | 使用状況 | 推奨対策 |
|---------|---------|----------|
| weather_code | NULL多数 | 未使用なら削除 |
| wind_dir_code | NULL多数 | 同上 |

---

## 4. インデックス最適化

### 追加推奨インデックス

1. **race_conditions.race_id + collected_at** (複合インデックス)
   - 理由: 最新の気象条件を取得する際に有効
   - 頻度: 高

2. **race_predictions.race_id + prediction_type + created_at** (複合インデックス)
   - 理由: 特定タイプの最新予測取得
   - 頻度: 高

3. **payouts.race_id + bet_type** (複合インデックス)
   - 理由: 特定賭け式の払戻検索
   - 頻度: 中

### 削除検討インデックス

現状、明らかに不要なインデックスは見当たらない。ただし、以下は重複の可能性がある:

1. **idx_race_details_race_id** と **sqlite_autoindex_race_details_1**
   - 複合インデックスとの重複確認が必要

---

## 5. データ型最適化

### TEXT vs INTEGER

| テーブル.カラム | 現在の型 | 推奨型 | 理由 |
|---------------|---------|-------|------|
| races.venue_code | TEXT | TEXT | 01-24の文字列で問題なし |
| entries.racer_number | TEXT | TEXT | 先頭0を含む番号があるため |
| results.rank | TEXT | INTEGER | 数値比較に使用、ただし失格等もあり現状維持 |

### REAL vs INTEGER

| テーブル.カラム | 現在の型 | 推奨型 | 理由 |
|---------------|---------|-------|------|
| race_conditions.wave_height | INTEGER | INTEGER | 問題なし |
| entries.win_rate | REAL | REAL | 小数点が必要 |

---

## 6. 正規化レベルの調整

### 過度な正規化（JOINが多い）

現状、特に過度な正規化は見られない。むしろ非正規化されている部分が多い。

### 適切な非正規化の例

1. **entries テーブル**:
   - racer_name, racer_rank, racer_home がレースごとに保存
   - これは適切（選手情報は時点によって変化するため）

2. **race_predictions テーブル**:
   - racer_name, racer_number が予測結果と共に保存
   - これも適切（予測時点の情報を保持）

### 検討すべき非正規化

1. **venues vs venue_data vs venue_strategies**:
   - 3テーブルに分散している会場情報
   - 頻繁にJOINする場合は統合を検討

---

## 7. 実装優先順位

### Phase 1 (即座に実施推奨)

| 優先度 | 項目 | 作業内容 | 影響範囲 | 工数目安 |
|-------|------|---------|---------|---------|
| 1 | races.gradeの削除 | race_gradeに統一、コード修正 | data_manager.py, models.py | 2時間 |
| 2 | results.winning_techniqueの削除 | kimariteに統一 | data_manager.py | 1時間 |

### Phase 2 (計画的に実施)

| 優先度 | 項目 | 作業内容 | 影響範囲 | 工数目安 |
|-------|------|---------|---------|---------|
| 3 | 空テーブルの整理 | 使用予定確認、不要なら削除 | スキーマ全体 | 2時間 |
| 4 | actual_coursesテーブル削除 | race_detailsに統一 | 複数ファイル | 3時間 |
| 5 | exhibition_dataテーブル削除 | race_detailsに統一 | 複数ファイル | 3時間 |
| 6 | バックアップテーブル削除 | results_backup, race_tide_data_backup | データのみ | 1時間 |

### Phase 3 (将来の検討事項)

| 項目 | 検討内容 |
|------|---------|
| venue系テーブル統合 | venue_data, venue_strategies, venuesの統合 |
| ルールテーブル整理 | extracted_rules, venue_rules, racer_rulesの関係整理 |
| 予測履歴の運用方針 | prediction_historyの蓄積戦略決定 |

---

## 8. 移行計画案

### バックアップ手順

```bash
# 1. データベースのフルバックアップ
cp data/boatrace.db data/boatrace_backup_$(date +%Y%m%d_%H%M%S).db

# 2. スキーマのみのバックアップ
sqlite3 data/boatrace.db ".schema" > backup/schema_$(date +%Y%m%d).sql
```

### Phase 1 実行手順

#### races.grade カラムの削除

```sql
-- 1. バックアップ確認
SELECT COUNT(*) FROM races WHERE grade IS NOT NULL AND grade != '';
SELECT COUNT(*) FROM races WHERE race_grade IS NOT NULL AND race_grade != '';

-- 2. データマージ（gradeのデータをrace_gradeに統合）
UPDATE races
SET race_grade = grade
WHERE (race_grade IS NULL OR race_grade = '')
  AND grade IS NOT NULL AND grade != '';

-- 3. 検証
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN race_grade IS NOT NULL AND race_grade != '' THEN 1 ELSE 0 END) as with_grade
FROM races;

-- 4. カラム削除（SQLiteでは直接削除不可、テーブル再作成が必要）
-- 新テーブル作成 -> データ移行 -> 旧テーブル削除 -> リネーム
```

#### results.winning_technique カラムの削除

```sql
-- 1. 検証: kimariteにデータがあることを確認
SELECT COUNT(*) FROM results WHERE kimarite IS NOT NULL AND rank = '1';
SELECT COUNT(*) FROM results WHERE winning_technique IS NOT NULL AND rank = '1';

-- 2. 不整合がないか確認
SELECT winning_technique, kimarite, COUNT(*)
FROM results
WHERE rank = '1' AND winning_technique IS NOT NULL
GROUP BY winning_technique, kimarite;

-- 3. カラム削除（テーブル再作成）
```

### テーブル再作成テンプレート

```sql
-- SQLiteでカラムを削除する標準手順
BEGIN TRANSACTION;

-- 1. 新テーブル作成（削除するカラムを除外）
CREATE TABLE new_races AS
SELECT id, venue_code, race_date, race_number, race_time, created_at,
       race_grade, race_distance, race_status, is_nighter, is_ladies,
       is_rookie, is_shinnyuu_kotei
FROM races;

-- 2. 旧テーブル削除
DROP TABLE races;

-- 3. リネーム
ALTER TABLE new_races RENAME TO races;

-- 4. インデックス再作成
CREATE INDEX idx_races_venue_date_number ON races(venue_code, race_date, race_number);
CREATE INDEX idx_races_venue_date ON races(venue_code, race_date);
CREATE INDEX idx_races_date ON races(race_date);
CREATE UNIQUE INDEX sqlite_autoindex_races_1 ON races(venue_code, race_date, race_number);

COMMIT;
```

---

## 9. 注意事項

### 既存システムへの影響

1. **data_manager.py**: `grade` カラムの参照箇所を修正必要
2. **models.py**: スキーマ定義の更新
3. **batch_data_loader.py**: キャッシュ処理の確認

### ロールバック手順

```bash
# バックアップからの復元
cp data/boatrace_backup_YYYYMMDD_HHMMSS.db data/boatrace.db
```

### 検証項目

1. 単体テスト: 各モジュールの動作確認
2. 結合テスト: 予測処理のEnd-to-End確認
3. 性能テスト: クエリ実行時間の計測

---

## 10. 補足: 使用状況サマリー

### 高頻度使用テーブル（コアテーブル）

| テーブル | 件数 | 使用頻度 | 重要度 |
|---------|------|---------|-------|
| races | 133,327 | 非常に高い | 極めて高い |
| entries | 799,824 | 非常に高い | 極めて高い |
| race_details | 790,680 | 高い | 高い |
| results | 779,318 | 高い | 高い |
| race_predictions | 196,692 | 高い | 高い |
| trifecta_odds | 1,424,376 | 高い | 高い |
| payouts | 1,027,127 | 中 | 中 |

### 中頻度使用テーブル（サポートテーブル）

| テーブル | 件数 | 使用頻度 | 重要度 |
|---------|------|---------|-------|
| race_conditions | 130,792 | 中 | 中 |
| weather | 9,018 | 中 | 中 |
| venue_rules | 308 | 中 | 中 |
| racer_features | 8,939 | 低〜中 | 中 |
| racer_venue_features | 8,952 | 低〜中 | 中 |

### 低頻度・未使用テーブル

| テーブル | 件数 | 使用頻度 | 備考 |
|---------|------|---------|------|
| rdmdb_tide | 6,475,040 | 低 | 大量データだが使用箇所少 |
| tide | 27,353 | 低 | 潮汐データ |
| venue_attack_patterns | 0 | 未使用 | 構造のみ |
| win_odds | 0 | 未使用 | 構造のみ |

---

## 更新履歴

| 日付 | バージョン | 内容 |
|------|-----------|------|
| 2025-12-12 | 1.0 | 初版作成 |

