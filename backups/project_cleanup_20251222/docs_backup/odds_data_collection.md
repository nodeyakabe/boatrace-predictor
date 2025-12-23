# オッズデータ取得ガイド

## 概要

競艇公式サイト（boatrace.jp）から3連単オッズを取得するための各種スクリプトの使い方をまとめる。

---

## スクリプト一覧

| スクリプト | 用途 | 速度 | 推奨用途 |
|-----------|------|------|----------|
| `fetch_odds_fast.py` | 過去データ大量取得 | **高速**（2.2件/秒） | 大量バックフィル |
| `fetch_historical_odds.py` | 過去データ取得（直列） | 遅い（0.1件/秒） | 少量データ |
| `auto_odds_fetcher.py` | 当日レースのオッズ自動取得 | 標準 | 日常運用 |
| `bulk_missing_data_fetch_parallel.py` | 不足データ一括取得（オッズ含む） | 中速 | 日常メンテナンス |

---

## 1. 大量の過去データ取得（推奨）

### `scripts/fetch_odds_fast.py`

20並列処理で高速にオッズデータを取得する。

```bash
# 基本使用法（2025年1-10月のデータを取得）
python scripts/fetch_odds_fast.py

# オプション指定
python scripts/fetch_odds_fast.py \
  --start-date 2025-01-01 \
  --end-date 2025-10-31 \
  --workers 20 \
  --delay 0.1

# 並列数を変更（サーバー負荷を考慮）
python scripts/fetch_odds_fast.py --workers 10 --delay 0.3
```

**オプション:**
- `--start-date`: 開始日（YYYY-MM-DD）
- `--end-date`: 終了日（YYYY-MM-DD）
- `--workers`: 並列数（デフォルト: 20）
- `--delay`: リクエスト間隔（デフォルト: 0.1秒）
- `--batch-size`: DBバッチ書き込みサイズ（デフォルト: 50）

**処理速度の目安:**
- 20並列: 約2.2レース/秒（13,000レース ≈ 100分）
- 10並列: 約1.1レース/秒
- 4並列: 約0.4レース/秒

---

## 2. 当日レースのオッズ取得

### `src/scraper/auto_odds_fetcher.py`

```python
from src.scraper.auto_odds_fetcher import AutoOddsFetcher

fetcher = AutoOddsFetcher(delay=1.5)

# 単一レースのオッズ取得
result = fetcher.fetch_odds_for_race(
    race_id=12345,
    venue_code='01',
    race_date='2025-12-07',
    race_number=1
)

# 本日の全レースを一括取得
today_schedule = {'01': '20251207', '02': '20251207'}  # 会場コード: 日付
result = fetcher.fetch_odds_for_today(today_schedule)
```

---

## 3. 不足データ一括取得（オッズ含む）

### `scripts/bulk_missing_data_fetch_parallel.py`

結果データ、直前情報、オッズを一括取得する。

```bash
# 過去30日分の不足データを取得
python scripts/bulk_missing_data_fetch_parallel.py

# 期間指定
python scripts/bulk_missing_data_fetch_parallel.py \
  --start-date 2025-11-01 \
  --end-date 2025-11-30

# 並列数調整
python scripts/bulk_missing_data_fetch_parallel.py \
  --workers-results 16 \
  --workers-beforeinfo 8 \
  --workers-odds 4
```

**注意:** オッズ取得は4並列のため、大量データには `fetch_odds_fast.py` を推奨。

---

## 4. 基本のオッズスクレイパー

### `src/scraper/odds_scraper.py`

他のスクリプトから呼び出される基本クラス。

```python
from src.scraper.odds_scraper import OddsScraper

scraper = OddsScraper(delay=1.0)

# 3連単オッズ取得
odds = scraper.get_trifecta_odds(
    venue_code='01',    # 会場コード（2桁）
    race_date='20251115',  # 日付（YYYYMMDD）
    race_number=1       # レース番号
)
# 戻り値: {'1-2-3': 8.8, '1-2-4': 15.2, ...} （約99通り）

# 単勝オッズ取得
win_odds = scraper.get_win_odds('01', '20251115', 1)
# 戻り値: {1: 1.5, 2: 3.2, 3: 5.8, 4: 12.5, 5: 18.0, 6: 35.0}
```

---

## データベーステーブル

### `trifecta_odds`
3連単オッズを保存するテーブル。

| カラム | 型 | 説明 |
|--------|-----|------|
| race_id | INTEGER | レースID |
| combination | TEXT | 組み合わせ（'1-2-3'形式） |
| odds | REAL | オッズ値 |
| fetched_at | TEXT | 取得日時 |

### `win_odds`
単勝オッズを保存するテーブル。

| カラム | 型 | 説明 |
|--------|-----|------|
| race_id | INTEGER | レースID |
| pit_number | INTEGER | 艇番（1-6） |
| odds | REAL | オッズ値 |
| fetched_at | TEXT | 取得日時 |

---

## 会場コード一覧

```
01: 桐生    07: 蒲郡    13: 尼崎    19: 下関
02: 戸田    08: 常滑    14: 鳴門    20: 若松
03: 江戸川  09: 津      15: 丸亀    21: 芦屋
04: 平和島  10: 三国    16: 児島    22: 福岡
05: 多摩川  11: びわこ  17: 宮島    23: 唐津
06: 浜名湖  12: 住之江  18: 徳山    24: 大村
```

---

## トラブルシューティング

### 問題1: 取得速度が遅い

**原因:** boatrace.jpのレスポンスが1リクエスト約9秒と遅い（サーバー側の制限）。

**解決:** 並列数を増やす（`fetch_odds_fast.py --workers 20`）

### 問題2: オッズが99通りしか取得できない

**原因:** HTTPリクエストでは一部のオッズしか取得できない。

**解決:** 全120通りが必要な場合は `playwright_odds_scraper.py` を使用（JavaScript実行が必要）。

### 問題3: タイムアウトエラー

**原因:** ネットワーク遅延。

**解決:** タイムアウト値を増やす、並列数を減らす。

---

## 更新履歴

- 2025-12-07: `fetch_odds_fast.py` 作成（20並列高速版）
- 既存: `fetch_historical_odds.py`（直列処理）
