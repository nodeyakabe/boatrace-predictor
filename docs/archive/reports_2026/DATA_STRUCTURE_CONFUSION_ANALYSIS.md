# データ構造の混乱分析と対策

**作成日**: 2026-02-06
**問題**: Claude Codeが毎回、天気・潮位データで混乱する

---

## 🚨 混乱の原因

### 1. 同じデータが複数の場所に存在

#### 天気データの例

| 保存場所 | 粒度 | 結合キー | 充足率 | 実態 |
|---------|------|---------|--------|------|
| `race_conditions.weather` | **レース単位** | race_id | 0.79% | **ほぼ空** |
| `weather.weather_condition` | **日付単位** | venue_code + weather_date | 27.8% | **多くがNone** |

#### 潮位データの例

| 保存場所 | 粒度 | データ範囲 | 件数 |
|---------|------|-----------|------|
| `race_tide_data` | **レース単位** | 2022年以降 | 7,844件 |
| `tide` | **満潮/干潮時刻** | 2022年以降 | 27,353件 |
| `rdmdb_tide` | **10分間隔観測** | 2022年以降 | 6,475,040件 |

### 2. なぜこうなったのか

**推測される理由:**

1. **収集時期の違い**
   - 初期: race_conditionsに全データを入れる設計
   - 後期: weatherテーブルを追加（日付単位で収集が容易）

2. **データソースの違い**
   - race_conditions: レースページから取得（レース単位）
   - weather: 天気ページから取得（日付単位）
   - rdmdb_tide: 気象庁観測データ（10分間隔）

3. **収集難易度の違い**
   - レース単位の天気: スクレイピングが困難/不安定
   - 日付単位の天気: 比較的容易だが粒度が粗い
   - 潮位データ: 外部API（気象庁）から一括取得

---

## 🤔 複数カラム/テーブルは意味がある？

### ✅ 意味がある場合

1. **粒度が異なる**
   - レース単位（12回/日）vs 日付単位（1回/日）
   - 満潮/干潮（2-4回/日）vs 10分間隔観測（144回/日）

2. **用途が異なる**
   - race_conditions.wind_speed: そのレースの風速
   - weather.wind_speed: その日の代表的な風速

3. **データソースが異なる**
   - 公式サイト vs 気象庁API
   - リアルタイム vs 確定値

### ❌ 意味がない（冗長な）場合

1. **同じデータの重複保存**
   - weather_conditionが2箇所にあるが、両方とも充足率が低い
   - どちらか一方に統一すべき

2. **歴史的な理由で残っている**
   - 古いカラムが削除されずに残っている
   - 新しいテーブルを追加したが、古いカラムも残した

---

## 🎯 Claude Codeが混乱しないための対策

### 対策1: ドキュメントの明確化

**DATABASE_SCHEMA.mdに追加すべき内容:**

```markdown
## データ取得時の優先順位

### 天気データ
1. 最優先: `weather`テーブル（venue_code + weather_date で結合）
2. 非推奨: `race_conditions.weather`（充足率0.79%、ほぼ空）

### 潮位データ
1. レース単位で必要: `race_tide_data`（race_idで結合）
2. 詳細分析用: `rdmdb_tide`（10分間隔、observation_datetime で検索）
3. 満潮/干潮時刻: `tide`（venue_code + tide_date で結合）

### 気象数値データ（風速・気温・水温）
1. 最優先: `race_conditions`（race_idで結合、レース単位）
2. サブ: `weather`（venue_code + weather_date で結合、日付単位）
```

### 対策2: クエリテンプレートの作成

**よく使うパターンをドキュメント化:**

```sql
-- 天気データを含むレース分析（正しい方法）
SELECT
    r.race_date,
    r.race_number,
    w.weather_condition,  -- weatherテーブルから取得
    rc.wind_speed,        -- race_conditionsから取得（レース単位）
    rc.temperature
FROM races r
LEFT JOIN race_conditions rc ON r.id = rc.race_id
LEFT JOIN weather w ON r.venue_code = w.venue_code
    AND r.race_date = w.weather_date
```

### 対策3: 混乱しやすいポイントをチェックリストに追加

**DATA_ANALYSIS_CHECKLIST.mdに追記:**

- [ ] 天気データは`weather`テーブルを使用（race_conditions.weatherは使わない）
- [ ] 気象数値（風速・気温・水温）は`race_conditions`を優先
- [ ] 潮位データは目的に応じて使い分け（レース単位 or 詳細分析）
- [ ] 2021年の潮位データは存在しない（2022年以降のみ）

---

## 📊 現状の正しいデータ取得方法（2021年1-8月）

| データ種別 | 推奨テーブル | 充足率 | 備考 |
|-----------|------------|--------|------|
| **天気（文字列）** | `weather.weather_condition` | 27.8%（日付単位） | **多くがNone** |
| **風速** | `race_conditions.wind_speed` | **100%** | ✅ レース単位で完全 |
| **気温** | `race_conditions.temperature` | **100%** | ✅ レース単位で完全 |
| **水温** | `race_conditions.water_temperature` | **100%** | ✅ レース単位で完全 |
| **潮位** | - | **0%** | ❌ 2021年データ不在 |

---

## 🔧 推奨アクション

### 短期（今すぐ）

1. ✅ **DATA_ANALYSIS_CHECKLIST.mdを必ず参照**
2. ✅ **DATABASE_SCHEMA.mdの「よくある間違い」セクションを確認**
3. ✅ **クエリ作成前に全テーブル一覧を確認**

### 中期（次回データ収集時）

1. 🔄 **天気文字列の収集方法を改善**
   - 現在: race_conditions.weatherもweather.weather_conditionも多くがNone
   - 対策: BeforeInfoScraperの`_extract_weather_data`が正しく動作するか検証

2. 🔄 **2021年の潮位データ収集可否を確認**
   - 公式サイトに残っているか？
   - 気象庁APIで遡及取得可能か？

### 長期（データ構造改善）

1. 🔧 **テーブル/カラムの統廃合を検討**
   - race_conditions.weatherを削除（常に空なら不要）
   - weatherテーブルとの統合を検討

2. 🔧 **データ収集スクリプトの統一**
   - 現在: 複数のスクリプトが異なるテーブルに保存
   - 理想: 1つのスクリプトが正しいテーブルに保存
