# BoatRace データベース エクスポート資料

**作成日:** 2025年11月26日
**エクスポートファイル:** `BoatRace_full_export_20251126_180620.zip`
**ZIPサイズ:** 227.51 MB（展開後: 1,324.91 MB）

---

## 概要

前回のエクスポート（2025年11月9日）から、データの追加・新規テーブルの作成が行われています。
本エクスポートには全データが含まれています。

---

## 前回エクスポートとの差分

### ファイルサイズ比較
| 項目 | 前回 (11/9) | 今回 (11/26) | 差分 |
|------|-------------|--------------|------|
| DBサイズ | 1,277.51 MB | 1,324.91 MB | +47.4 MB |

### テーブル別データ件数比較

#### 新規追加テーブル（6テーブル）
| テーブル名 | 件数 | 説明 |
|-----------|------|------|
| `racer_features` | 8,939 | 選手の直近成績特徴量 |
| `racer_venue_features` | 8,952 | 選手×会場別の成績特徴量 |
| `race_predictions` | 432 | レース予測結果 |
| `motor_features` | 0 | モーター特徴量（スキーマのみ） |
| `trifecta_odds` | 0 | 3連単オッズ（スキーマのみ） |
| `win_odds` | 0 | 単勝オッズ（スキーマのみ） |

#### データ増加テーブル
| テーブル名 | 前回 | 今回 | 差分 |
|-----------|------|------|------|
| `payouts` | 666,419 | 1,016,956 | **+350,537** |
| `race_details` | 629,697 | 782,242 | **+152,545** |
| `results` | 722,281 | 770,436 | **+48,155** |
| `entries` | 787,063 | 787,500 | +437 |
| `races` | 131,746 | 131,833 | +87 |
| `venue_data` | 0 | 24 | +24 |

#### データ減少テーブル
| テーブル名 | 前回 | 今回 | 差分 | 備考 |
|-----------|------|------|------|------|
| `race_tide_data` | 38,099 | 7,844 | -30,255 | データ整理により削減 |

#### 変更なしテーブル
| テーブル名 | 件数 |
|-----------|------|
| `rdmdb_tide` | 6,475,040 |
| `tide` | 27,353 |
| `weather` | 8,989 |
| `racer_rules` | 215 |
| `venue_features` | 96 |
| `venues` | 24 |
| `venue_strategies` | 24 |
| `venue_rules` | 18 |
| `bet_history` | 3 |
| `results_backup` | 24 |
| `recommendations` | 0 |

---

## データ期間

| データ種別 | 期間 |
|-----------|------|
| races（レース情報） | 2015-11-01 ～ 2025-11-14 |
| results（レース結果） | 2015-11-01 ～ 2025-11-04 |
| racer_features（選手特徴量） | 2024-04-01 ～ 2024-06-30 |
| race_predictions | 72レース分 |

---

## 新規テーブルのスキーマ

### racer_features（選手特徴量）
選手の直近N戦の成績を集計した特徴量テーブル。

```sql
CREATE TABLE racer_features (
    racer_number TEXT,
    race_date TEXT,
    recent_avg_rank_3 REAL,      -- 直近3戦平均着順
    recent_avg_rank_5 REAL,      -- 直近5戦平均着順
    recent_avg_rank_10 REAL,     -- 直近10戦平均着順
    recent_win_rate_3 REAL,      -- 直近3戦勝率
    recent_win_rate_5 REAL,      -- 直近5戦勝率
    recent_win_rate_10 REAL,     -- 直近10戦勝率
    total_races INTEGER,         -- 総レース数
    computed_at TEXT,
    PRIMARY KEY (racer_number, race_date)
)
```

### racer_venue_features（選手×会場特徴量）
選手の会場別成績を集計した特徴量テーブル。

```sql
CREATE TABLE racer_venue_features (
    racer_number TEXT,
    venue_code TEXT,
    race_date TEXT,
    venue_win_rate REAL,    -- 当該会場での勝率
    venue_avg_rank REAL,    -- 当該会場での平均着順
    venue_races INTEGER,    -- 当該会場でのレース数
    computed_at TEXT,
    PRIMARY KEY (racer_number, venue_code, race_date)
)
```

### race_predictions（レース予測）
AIによるレース予測結果を格納するテーブル。

```sql
CREATE TABLE race_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    pit_number INTEGER NOT NULL,
    rank_prediction INTEGER NOT NULL,
    total_score REAL NOT NULL,
    confidence TEXT,
    racer_name TEXT,
    racer_number TEXT,
    applied_rules TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(race_id, pit_number),
    FOREIGN KEY (race_id) REFERENCES races(id)
)
```

### motor_features（モーター特徴量）
モーターの成績特徴量テーブル（現在はスキーマのみ）。

```sql
CREATE TABLE motor_features (
    race_id INTEGER,
    pit_number INTEGER,
    motor_recent_2rate_diff REAL,
    motor_trend REAL,
    computed_at TEXT,
    PRIMARY KEY (race_id, pit_number)
)
```

### win_odds / trifecta_odds（オッズ）
オッズ情報を格納するテーブル（現在はスキーマのみ）。

```sql
CREATE TABLE win_odds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    pit_number INTEGER NOT NULL,
    odds REAL NOT NULL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(race_id, pit_number),
    FOREIGN KEY (race_id) REFERENCES races(id)
)

CREATE TABLE trifecta_odds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    combination TEXT NOT NULL,
    odds REAL NOT NULL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(race_id, combination),
    FOREIGN KEY (race_id) REFERENCES races(id)
)
```

---

## 使用方法

1. `BoatRace_full_export_20251126_180620.zip` を展開
2. `data/boatrace.db` を別PCの `BoatRace/data/` ディレクトリに配置
3. 既存の `boatrace.db` がある場合はバックアップ後に置き換え

---

## 注意事項

- 本エクスポートは**完全なデータベースのコピー**です
- 前回エクスポートとの差分ではなく、全データが含まれています
- 別PCで使用する際は、このDBファイルで既存のものを置き換えてください
