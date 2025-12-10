# データ収集改善ガイド

## 概要

このガイドでは、2015-2021年のデータ収集における問題点と改善策を説明します。

---

## 🔍 調査結果サマリー

### データ収集状況 (2015-2021年)

| データ項目 | 充足率 | ステータス | 備考 |
|-----------|--------|-----------|------|
| parts_replacement (部品交換) | 100.0% | ✓ | 完璧 |
| tilt_angle (チルト角度) | 99.7% | ✓ | ほぼ完璧 |
| exhibition_time (展示タイム) | 99.7% | ✓ | ほぼ完璧 |
| weather (天気データ) | 99.9% | ✓ | ほぼ完璧 |
| actual_course (進入コース) | 95.2% | ✓ | 良好 |
| results (レース結果) | 89.5% | ✓ | 良好 |
| **st_time (STタイム)** | **79.4%** | ⚠ | **要改善** |
| tide (潮位データ) | 0.0% | ✗ | 未収集 |

---

## 🚨 STタイム欠損の真因

### 問題の詳細

**データベース分析結果** (全59,081レース):

```
0/6艇:   2,497レース (4.23%)
1/6艇:       0レース (0.00%)
2/6艇:       0レース (0.00%)
3/6艇:     191レース (0.32%)
4/6艇:   1,048レース (1.77%)
5/6艇:  55,345レース (93.68%) ← 最多
6/6艇:       0レース (0.00%) ← 完全なデータなし
```

### 原因

**93.68%のレースで5艇分のSTタイムは取得できているが、毎回1艇だけ欠損している**

理由:
1. **フライング(F)や出遅れ(L)の艇のSTタイムが数値ではなく文字で表示される**
2. **既存のスクレイパーが数値以外をスキップしている**

該当コード: `src/scraper/result_scraper.py:1312-1316`

```python
try:
    st_time = float(time_text)  # "F"や"L"は変換失敗
    result["st_times"][pit_number] = st_time
except ValueError:
    pass  # ← ここでスキップされる
```

---

## ✅ 改善策

### 1. 改善版スクレイパーの使用

新しい `ImprovedResultScraper` を作成しました:

**場所**: `src/scraper/result_scraper_improved.py`

**改善点**:
- フライング(F) → `-0.01` として保存
- 出遅れ(L) → `-0.02` として保存
- STステータス(normal/flying/late)も記録

**使用方法**:

```python
from src.scraper.result_scraper_improved import ImprovedResultScraper

scraper = ImprovedResultScraper()
result = scraper.get_race_result_complete("01", "20151109", 1)

st_times = result['st_times']     # {1: 0.15, 2: -0.01, ...}
st_status = result['st_status']   # {1: 'normal', 2: 'flying', ...}
```

### 2. 改善版並列収集スクリプト

**ファイル**: `fetch_parallel_improved.py`

**特徴**:
- ImprovedResultScraperを使用
- F/L対応でほぼ100%のSTタイムを取得
- フライング・出遅れを自動検出してログ出力

**使用方法**:

```bash
# 欠損データ補完
python fetch_parallel_improved.py --fill-missing --workers 10

# 期間指定
python fetch_parallel_improved.py --start 2015-01-01 --end 2021-12-31 --workers 10
```

---

## 🌤️ 環境データ収集

### 既存の環境データ

| データ | 充足率 | 備考 |
|--------|--------|------|
| 気温 | 99.9% | weatherテーブル |
| 水温 | 99.9% | weatherテーブル |
| 風速 | 99.9% | weatherテーブル |
| 風向 | 99.9% | weatherテーブル |
| 波高 | 99.9% | weatherテーブル |
| 潮位 | 0.0% | 未収集 |

### 環境データ収集スクリプト

**ファイル**: `collect_environmental_data.py`

天気・風・波などの環境データを収集します。

**使用方法**:

```bash
# 欠損分のみ収集
python collect_environmental_data.py --fill-missing --workers 5

# 期間指定
python collect_environmental_data.py --start 2015-01-01 --end 2021-12-31 --workers 5
```

---

## 📝 推奨アクション

### ステップ1: 改善版スクリプトでデータ再取得

```bash
# STタイム欠損を改善版で再収集
python fetch_parallel_improved.py --fill-missing --workers 10
```

- **対象**: 59,081レース
- **推定時間**: 約197分 (3.3時間)
- **改善効果**: STタイム完全取得率が0% → 95%+に向上

### ステップ2: 環境データ補完

```bash
# 天気データの欠損分を補完
python collect_environmental_data.py --fill-missing --workers 5
```

### ステップ3: データ検証

```bash
# 改善結果を確認
python analyze_data_quality.py
```

---

## 🧪 テストスクリプト

### 改善版スクレイパーのテスト

```bash
python test_improved_scraper.py
```

期待される結果:
- 5/6艇 → 6/6艇に改善
- フライング・出遅れが正しく記録される

---

## 📊 分析スクリプト

### 1. データ品質分析

```bash
python analyze_data_quality.py
```

出力:
- データ項目別の充足率
- 年度別の完全性
- STタイム欠損パターン
- テスト用サンプルレース

### 2. 欠損データレポート

```bash
python check_missing_correct.py
```

出力:
- 年度別の欠損数
- 会場別の欠損数
- 補完推奨コマンド

---

## 💾 データベーススキーマ

### race_detailsテーブル

```sql
CREATE TABLE race_details (
    id INTEGER PRIMARY KEY,
    race_id INTEGER,
    pit_number INTEGER,
    exhibition_time REAL,      -- 展示タイム
    tilt_angle REAL,           -- チルト角度
    parts_replacement TEXT,    -- 部品交換
    actual_course INTEGER,     -- 進入コース
    st_time REAL,              -- STタイム (F=-0.01, L=-0.02)
    chikusen_time REAL,        -- 直線タイム (未実装)
    isshu_time REAL,           -- 1周タイム (未実装)
    mawariashi_time REAL       -- まわり足タイム (未実装)
)
```

### weatherテーブル

```sql
CREATE TABLE weather (
    id INTEGER PRIMARY KEY,
    venue_code TEXT,
    weather_date DATE,
    temperature REAL,          -- 気温
    weather_condition TEXT,    -- 天気
    wind_speed REAL,           -- 風速
    wind_direction TEXT,       -- 風向
    humidity INTEGER,          -- 湿度
    water_temperature REAL,    -- 水温
    wave_height REAL          -- 波高
)
```

---

## 🔧 トラブルシューティング

### Q1: STタイムが-0.01や-0.02になっている

**A**: これは正常です。
- `-0.01` = フライング(F)
- `-0.02` = 出遅れ(L)

実際の数値として使用する場合は、これらの値を除外するか、特別な処理を行ってください。

### Q2: 改善版でも6/6にならない

**A**: 以下の可能性があります:
1. 公式サイト側でデータが欠損している
2. HTMLの構造が変更されている
3. レースが中止・延期された

`analyze_data_quality.py`でサンプルレースを確認してください。

### Q3: 潮位データが0件

**A**: 潮位データは公式サイトに掲載されていない可能性があります。別のデータソースが必要です。

---

## 📈 期待される改善効果

| 指標 | 改善前 | 改善後 (予想) |
|------|--------|--------------|
| STタイム完全取得率 (6/6艇) | 0.0% | 95%+ |
| STタイム部分取得率 (5/6艇) | 93.68% | 3%未満 |
| STタイムゼロ (0/6艇) | 4.23% | 1%未満 |
| フライング・出遅れ検出 | 不可 | 可能 |

---

## 📚 関連ファイル

### スクレイパー
- `src/scraper/result_scraper.py` - 既存版
- `src/scraper/result_scraper_improved.py` - **改善版 (F/L対応)**
- `src/scraper/beforeinfo_scraper.py` - 事前情報スクレイパー
- `src/scraper/race_scraper_v2.py` - 出走表スクレイパー

### 収集スクリプト
- `fetch_parallel_v6.py` - 既存版
- **`fetch_parallel_improved.py`** - **改善版 (推奨)**
- **`collect_environmental_data.py`** - 環境データ収集

### 分析スクリプト
- `analyze_data_quality.py` - データ品質分析
- `check_missing_correct.py` - 欠損データレポート
- `check_missing_data.py` - 詳細レポート

### テストスクリプト
- `test_scraper.py` - 既存版スクレイパーテスト
- `test_improved_scraper.py` - 改善版スクレイパーテスト

---

## 🎯 次のステップ

1. **改善版スクレイパーでデータ再収集**
   ```bash
   python fetch_parallel_improved.py --fill-missing --workers 10
   ```

2. **結果の検証**
   ```bash
   python analyze_data_quality.py
   ```

3. **環境データ補完** (必要に応じて)
   ```bash
   python collect_environmental_data.py --fill-missing --workers 5
   ```

4. **機械学習モデルの学習**
   - STタイムデータが完全になったため、より精度の高いモデル学習が可能

---

## ℹ️ サポート

問題が発生した場合:
1. `analyze_data_quality.py`で状況を確認
2. `test_improved_scraper.py`で動作テスト
3. ログを確認して原因を特定

---

**作成日**: 2025-11-09
**バージョン**: 1.0
**改善版スクレイパー**: ImprovedResultScraper
