# 重要な実装知見・ノウハウ集

このドキュメントは、**過去に実装された重要な技術的知見**を記録し、今後の開発で同じ間違いを繰り返さないためのものです。

---

## 1. データ収集の効率化 - スケジュールベース取得

### ❌ 間違った実装（非効率）

```python
# fetch_historical_data.py の初期実装
# 全288タスク(24会場 × 12レース)を毎日試行
for date_str in dates:
    for venue_code in ALL_VENUES:  # 24会場全て
        for race_number in range(1, 13):  # 12レース全て
            tasks.append((venue_code, date_str, race_number))
```

**問題点:**
- 実際には1日5-10会場のみ開催なのに、24会場全てを試行
- **70-80%が無駄なHTTPリクエスト**
- 87,552タスクのうち約60,000タスクが「開催なし」でスキップ
- 完了時間: 48時間

### ✅ 正しい実装（効率的）

```python
# fetch_parallel_v6.py の実装
# ScheduleScraperで開催日・会場を事前取得
schedule_scraper = ScheduleScraper()
schedule = schedule_scraper.get_schedule_for_period(start_date, end_date)

# 開催日のみタスク生成
for venue_code, dates in schedule.items():
    for date_str in dates:
        for race_number in range(1, 13):
            tasks.append((venue_code, date_str, race_number))
```

**効果:**
- リクエスト数: 87,552 → **約15,000-20,000に削減**（70-80%削減）
- 完了時間: 48時間 → **10-12時間に短縮**
- スキップ率: 70% → **5%以下**

### 実装場所

- **ScheduleScraper**: `src/scraper/schedule_scraper.py`
- **正しい使用例**: `fetch_parallel_v6.py` (443-464行目)
- **間違った例**: `fetch_historical_data.py` (89-113行目)

---

## 2. データベース書き込みの競合回避

### ✅ 正しい実装

```python
# fetch_parallel_v6.py: シングルスレッドでDB書き込み
db_thread = Thread(target=db_writer_worker, args=(data_queue, stats, stop_event))
```

**重要ポイント:**
- **DB書き込みは必ず1スレッドで実行**
- HTTPリクエストは並列化OK（ProcessPoolExecutor）
- キューを使ってHTTPワーカー → DBライターへデータ受け渡し

---

## 3. エラーハンドリングの最適化

### ❌ 非効率な実装

```python
# デバッグ出力が大量発生
print(f"\n[DEBUG] Race data fetch error for {venue_code}-{date_str}-R{race_number}: {e}")
traceback.print_exc()
```

**問題点:**
- 1レースあたり複数のエラー出力
- I/Oオーバーヘッドで処理速度低下
- ログが膨大で見づらい

### ✅ 効率的な実装

```python
# 必要なログのみ出力
if result['success']:
    print(f"[OK] {venue_code} {date_str} {race_number:2d}R 保存完了")
else:
    error_msg = result.get('error', 'Unknown')
    if '出走表が空' not in error_msg:  # 開催なしは表示しない
        print(f"[SKIP] {venue_code} {date_str} {race_number:2d}R - {error_msg}")
```

---

## 4. HTTPリクエストの並列化

### ✅ 最適な実装（V6改善）

```python
# 3つのHTTPリクエストを並列実行（3.3秒 → 1.1秒）
with ThreadPoolExecutor(max_workers=3) as executor:
    future_race = executor.submit(fetch_race_data)
    future_before = executor.submit(fetch_beforeinfo)
    future_result = executor.submit(fetch_result)

    race_data = future_race.result()
    beforeinfo = future_before.result()
    complete_result = future_result.result()
```

**効果:**
- 1レースあたりの取得時間: 3.3秒 → **1.1秒**（3倍高速化）

---

## 5. 推奨されるデータ収集スクリプト

### 新規データ収集（過去データ含む）

```bash
# fetch_parallel_v6.py を使用（スケジュールベース）
python fetch_parallel_v6.py --start 2022-01-01 --end 2022-10-31 --workers 10
```

### 欠損データ補完

```bash
# 欠損データのみ取得
python fetch_parallel_v6.py --fill-missing --workers 10
```

### 本日のレース取得

```bash
# 今日から3日先まで
python fetch_upcoming_races.py --days 3
```

---

## 6. よくある間違いとその対処

### 間違い1: 全会場・全レースをブルートフォース試行
**対処**: `ScheduleScraper.get_schedule_for_period()` で開催日を事前取得

### 間違い2: DB書き込みを並列化してロック競合
**対処**: DB書き込みは必ず1スレッドで実行

### 間違い3: 大量のデバッグログで処理速度低下
**対処**: 必要最小限のログのみ出力（成功/重要なエラーのみ）

### 間違い4: HTTPリクエストを直列実行
**対処**: ThreadPoolExecutorで並列実行（出走表・結果・直前情報を同時取得）

---

## 7. パフォーマンス指標

### 目標値

- **取得速度**: 2-3レース/秒以上
- **スキップ率**: 5%以下（開催日ベース）
- **DB書き込み成功率**: 95%以上
- **HTTPエラー率**: 5%以下

### 計測方法

```python
elapsed = time.time() - start_time
rate = completed / elapsed
success_rate = stats['saved'] / len(tasks) * 100
```

---

## 8. 今後の実装時の注意点

### 新しいデータ収集スクリプトを作成する場合

1. **必ず `ScheduleScraper` を使用する**
2. **DB書き込みは1スレッド**
3. **HTTPリクエストは並列化**
4. **ログは最小限**
5. **既存の `fetch_parallel_v6.py` を参考にする**

### レビューチェックリスト

- [ ] スケジュールベースでタスク生成しているか？
- [ ] DB書き込みは1スレッドか？
- [ ] HTTPリクエストは並列化されているか？
- [ ] 不要なデバッグログは削除されているか？
- [ ] エラーハンドリングは適切か？

---

## 9. 参考実装ファイル

| ファイル | 用途 | 備考 |
|---------|------|------|
| `fetch_parallel_v6.py` | **推奨：メインデータ収集** | スケジュールベース・並列化・最適化済み |
| `src/scraper/schedule_scraper.py` | 開催スケジュール取得 | 必ず使用すること |
| `fetch_upcoming_races.py` | 未来のレース取得 | リアルタイム予想用 |
| `fetch_historical_data.py` | ❌ 非推奨 | ブルートフォース方式・非効率 |

---

## 10. 最後に

**このドキュメントを必ず読んでから新しいデータ収集機能を実装してください。**

過去の知見を活かすことで、開発時間とリソースを大幅に節約できます。
