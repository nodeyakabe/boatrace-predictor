# 冗長カラムの削除提案

**作成日**: 2026-02-09
**問題**: 充足率が低い・使われていないカラムがDB構造を複雑化している

---

## 🎯 削除を検討すべきカラム

### 1. race_conditions.weather（充足率: 0.79%）

**現状**:
- 130,792件中わずか1,033件のみデータあり
- 99.2%が空（NULL）

**問題点**:
- Claude Codeが毎回このカラムを見つけて混乱
- 「天気データがない」という誤った判断をする
- 実際は`weather`テーブル（27.8%カバレッジ）を使うべき

**削除のメリット**:
- ✅ データ構造がシンプルになる
- ✅ 混乱の原因が1つ減る
- ✅ ドキュメントの「よくある間違い」セクションが不要になる

**削除のデメリット**:
- ⚠️ 将来、レース単位で天気を収集する機能を追加する場合、再度カラム追加が必要
- ⚠️ 既存の1,033件のデータが失われる（ただし0.79%なので影響は軽微）

**推奨**: ✅ **削除を推奨**

---

### 2. 他の候補カラム

#### weather.weather_condition（多くがNone）

**現状**:
- 11,528件のレコード中、多くがNone
- 実際にデータがあるのは一部のみ

**問題点**:
- データが入っているように見えるが、実際は空
- 分析時に「天気データがある」と誤認する

**推奨**: ⚠️ **保留（まず収集方法を改善すべき）**
- 削除より先に、`BeforeInfoScraper._extract_weather_data()`の修正を試みる
- 修正後もNoneが多い場合は削除を検討

---

## 📋 削除の実施方法

### Option 1: 段階的削除（推奨）

**Phase 1: 調査**
```sql
-- race_conditions.weatherの実データ確認
SELECT COUNT(*) as total,
       COUNT(weather) as has_weather,
       COUNT(weather) * 100.0 / COUNT(*) as coverage_pct
FROM race_conditions;

-- 実データのサンプル確認
SELECT * FROM race_conditions
WHERE weather IS NOT NULL AND weather != ''
LIMIT 100;
```

**Phase 2: バックアップ**
```sql
-- 削除前にバックアップテーブル作成
CREATE TABLE race_conditions_backup AS
SELECT * FROM race_conditions;
```

**Phase 3: カラム削除**
```sql
-- SQLiteではALTER TABLE DROP COLUMNが使えない（SQLite 3.35.0+では可能）
-- テーブル再作成が必要

-- 1. 新しいテーブル作成（weatherカラムなし）
CREATE TABLE race_conditions_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    wind_direction TEXT,
    wind_speed REAL,
    wave_height INTEGER,
    temperature REAL,
    water_temperature REAL,
    collected_at TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (race_id) REFERENCES races(id)
);

-- 2. データコピー
INSERT INTO race_conditions_new
    (id, race_id, wind_direction, wind_speed, wave_height,
     temperature, water_temperature, collected_at, created_at)
SELECT
    id, race_id, wind_direction, wind_speed, wave_height,
    temperature, water_temperature, collected_at, created_at
FROM race_conditions;

-- 3. インデックス再作成
CREATE INDEX idx_race_conditions_race_id
ON race_conditions_new(race_id);

-- 4. 旧テーブル削除・新テーブルをリネーム
DROP TABLE race_conditions;
ALTER TABLE race_conditions_new RENAME TO race_conditions;
```

**Phase 4: 検証**
```sql
-- レコード数確認
SELECT COUNT(*) FROM race_conditions;

-- 外部キー確認
PRAGMA foreign_key_check(race_conditions);

-- 既存クエリの動作確認
-- （standard_backtest.pyなど主要スクリプトを実行）
```

---

### Option 2: 即座に削除（非推奨）

直接削除すると、バックアップなしでデータが失われるため推奨しません。

---

## ⚖️ 判断基準

### 削除すべきカラム

以下のすべてを満たす場合、削除を検討：

1. ✅ **充足率が5%未満**
2. ✅ **代替データが存在する**（別のテーブル/カラム）
3. ✅ **既存スクリプトで使われていない**
4. ✅ **混乱の原因になっている**

### 削除すべきでないカラム

以下のいずれかに該当する場合、保持：

1. ❌ **充足率が20%以上**
2. ❌ **代替データがない**
3. ❌ **既存スクリプトで参照されている**
4. ❌ **将来的に収集する予定がある**

---

## 🎯 race_conditions.weatherの評価

| 基準 | 評価 | 詳細 |
|------|------|------|
| 充足率 | ✅ 削除候補 | 0.79%（ほぼ空） |
| 代替データ | ✅ 削除候補 | `weather`テーブルあり（27.8%） |
| 使用状況 | ✅ 削除候補 | 既存スクリプトで未使用 |
| 混乱度 | ✅ 削除候補 | Claude Codeが毎回混乱 |

**結論**: **削除を強く推奨** ✅

---

## 📝 削除後の対応

### 1. ドキュメント更新

- ✅ `DATABASE_SCHEMA.md`から`race_conditions.weather`の記載を削除
- ✅ 「よくある間違い」セクションの該当箇所を削除または更新

### 2. スクリプト確認

- ✅ 全スクリプトで`race_conditions.weather`を参照していないか確認
  ```bash
  grep -r "race_conditions.weather" scripts/
  grep -r "rc.weather" scripts/
  ```

### 3. 収集スクリプト修正

- ✅ `補完_2021_2023_完全版.py`の`race_conditions`セクション
  - weatherカラムへの書き込みを削除
  - `if race_data.get('weather'):`条件を削除（これがrace_conditions全体をスキップする原因）

---

## 🚀 実施タイミング

### 推奨タイミング

**2021-2023データ収集完了後**

理由：
- 現在の収集が完了してからDBメンテナンスを実施
- 収集中にスキーマ変更するとトラブルのリスク
- バックテスト・予測生成後に余裕を持って実施

### 実施手順

1. ✅ **2021-2023データ収集完了を待つ**（優先度: 最高）
2. ✅ **DB投入完了後、バックアップ作成**
3. ✅ **カラム削除実施**（30分程度）
4. ✅ **全スクリプトの動作確認**（1-2時間）
5. ✅ **ドキュメント更新**（30分程度）

---

## 💡 まとめ

### 削除を推奨するカラム

| カラム | 充足率 | 代替 | 優先度 |
|--------|--------|------|--------|
| `race_conditions.weather` | 0.79% | `weather`テーブル | **高** ✅ |

### 今後の方針

1. **データ収集完了後に削除**
2. **削除前に必ずバックアップ**
3. **段階的に実施（調査→バックアップ→削除→検証）**
4. **削除後は収集スクリプトも修正**

---

**最終更新**: 2026-02-09
