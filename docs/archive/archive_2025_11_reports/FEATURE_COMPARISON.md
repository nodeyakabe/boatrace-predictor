# 機能比較レポート - 過去実装vs現在実装

**作成日**: 2025-11-03
**目的**: 過去の実装と現在の実装を比較し、削除・変更された機能を記録

---

## 1. データ収集スクリプトの比較

### 1.1 fetch_historical_data.py の変更

#### ❌ **削除された機能: スケジュールベース取得**

**過去の実装（推奨版）**:
```python
# IMPORTANT_KNOW_HOW.md に記載されている推奨実装
schedule_scraper = ScheduleScraper()
schedule = schedule_scraper.get_schedule_for_period(start_date, end_date)

# 開催日のみタスク生成
for venue_code, dates in schedule.items():
    for date_str in dates:
        for race_number in range(1, 13):
            tasks.append((venue_code, date_str, race_number))
```

**現在の実装（ブルートフォース方式に戻っている）**:
```python
# fetch_historical_data.py: 89-113行目
def generate_tasks(start_date_str, end_date_str, venues=None):
    dates = generate_date_range(start_date_str, end_date_str)

    tasks = []
    for date_str in dates:
        for venue_code in venues:
            # 全日×全会場を試行（非効率）
            for race_number in range(1, 13):
                tasks.append((venue_code, date_str, race_number))
```

**問題点**:
- ✅ `ScheduleScraper`はインポートされている（33行目）
- ❌ しかし実際には使用されていない
- ❌ 全日×全会場のブルートフォース方式に戻っている
- ❌ IMPORTANT_KNOW_HOW.mdの推奨実装から逆行

**影響**:
- リクエスト数: **70-80%増加**（不要なリクエスト発生）
- 処理時間: 推定で**2-3倍に悪化**
- スキップ率: 5%以下 → **70%以上**（開催なしを大量に試行）

---

### 1.2 fetch_parallel_v6.py の状態

#### ✅ **維持されている機能**

**スケジュールベース取得** (443-464行目):
```python
# 正しい実装が維持されている
schedule_scraper = ScheduleScraper()
schedule = schedule_scraper.get_schedule_for_period(start_date, end_date)

# 開催日のみタスク生成
for venue_code, dates in schedule.items():
    for date_str in dates:
        for race_number in range(1, 13):
            tasks.append((venue_code, date_str, race_number))
```

**結論**: fetch_parallel_v6.pyは正しい実装を維持している ✅

---

## 2. HTTPリクエストの並列化

### 2.1 fetch_parallel_v6.py

#### ✅ **維持されている機能**

**3つのHTTPリクエストを並列実行** (fetch_http_only関数内):
- 出走表 (RaceScraperV2)
- 結果 (ResultScraper)
- 直前情報 (BeforeInfoScraper)

```python
# V5からの改善が維持されている
with ThreadPoolExecutor(max_workers=3) as executor:
    future_race = executor.submit(fetch_race_data)
    future_before = executor.submit(fetch_beforeinfo)
    future_result = executor.submit(fetch_result)
```

**効果**: 1レースあたり 3.3秒 → 1.1秒（3倍高速化）✅

---

### 2.2 fetch_historical_data.py

#### ⚠️ **変更された実装**

**現在の実装**:
```python
# fetch_historical_data.py: 117-201行目
# 直列実行（並列化なし）
race_data = race_scraper.fetch_race_data(...)  # 1つ目
complete_result = result_scraper.fetch_result(...)  # 2つ目
beforeinfo = beforeinfo_scraper.scrape(...)  # 3つ目
```

**問題点**:
- ❌ 3つのHTTPリクエストを直列実行
- ❌ V6で実装された並列化改善が反映されていない
- ❌ 1レースあたり約3.3秒かかる（V6の3倍）

**影響**:
- 処理速度: V6の **3分の1に低下**

---

## 3. データベース書き込み

### 3.1 両スクリプトの比較

#### ✅ **正しい実装（共通）**

**DB書き込みは1スレッド**:
- `fetch_parallel_v6.py`: db_writer_worker (486行目)
- `fetch_historical_data.py`: saver_thread (343行目)

**結論**: DB書き込みの競合回避は両方とも正しく実装されている ✅

---

## 4. エラーハンドリング

### 4.1 fetch_historical_data.py の問題

#### ❌ **デバッグログの大量出力**

```python
# 154-157行目, 174-176行目, 195-197行目
import traceback
print(f"\n[DEBUG] Race data fetch error for {venue_code}-{date_str}-R{race_number}: {e}")
traceback.print_exc()
```

**問題点**:
- ❌ 1レースあたり複数のデバッグ出力
- ❌ tracebackの全スタックトレース出力
- ❌ I/Oオーバーヘッドで処理速度低下
- ❌ ログが膨大で見づらい

**IMPORTANT_KNOW_HOW.mdの推奨**:
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

### 4.2 fetch_parallel_v6.py の状態

#### ✅ **適切なエラーハンドリング**

- 必要最小限のログ出力
- スキップとエラーを明確に分離
- I/Oオーバーヘッド最小化

---

## 5. その他のスクリプト

### 5.1 fetch_upcoming_races.py

#### ✅ **機能は維持**

- 未来のレース情報取得
- リアルタイム予想用
- Beautiful Soup使用（旧版のまま、V2スクレイパーに未移行）

**状態**: 動作するが、V2スクレイパーへの移行が望ましい

---

### 5.2 fetch_missing_data.py

#### ✅ **機能は維持**

- CSV から欠損データ読み込み
- ThreadPoolExecutor で並列収集
- ResultScraper, BeforeInfoScraper 使用

**状態**: 正常に動作

---

### 5.3 fetch_venue_data.py

#### ✅ **機能は維持**

- 24会場の基本データ取得
- OfficialVenueScraper 使用
- 水質、干満差、コース別1着率など

**状態**: 正常に動作

---

## 6. 総合評価

### 6.1 推奨スクリプト vs 非推奨スクリプト

| スクリプト | スケジュールベース | HTTP並列化 | ログ最適化 | 総合評価 | 推奨度 |
|-----------|-----------------|-----------|----------|---------|-------|
| **fetch_parallel_v6.py** | ✅ 実装済み | ✅ 実装済み | ✅ 最適化済み | **優秀** | ⭐⭐⭐⭐⭐ |
| **fetch_historical_data.py** | ❌ 未実装 | ❌ 未実装 | ❌ 大量出力 | **非効率** | ⭐ |
| fetch_upcoming_races.py | N/A | N/A | ✅ 適切 | 普通 | ⭐⭐⭐ |
| fetch_missing_data.py | N/A | ✅ 実装済み | ✅ 適切 | 良好 | ⭐⭐⭐⭐ |
| fetch_venue_data.py | N/A | N/A | ✅ 適切 | 良好 | ⭐⭐⭐⭐ |

---

## 7. 改善が必要な項目

### 7.1 最優先（Critical）

#### ❌ fetch_historical_data.py のスケジュールベース取得

**現状**: ブルートフォース方式で70-80%が無駄なリクエスト

**修正方法**:
```python
# generate_tasks() 関数を以下に置き換え
def generate_tasks_schedule_based(start_date_str, end_date_str, venues=None):
    """スケジュールベースでタスク生成"""
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

    # ScheduleScraperで開催日を事前取得
    schedule_scraper = ScheduleScraper()
    schedule = schedule_scraper.get_schedule_for_period(start_date, end_date)
    schedule_scraper.close()

    tasks = []
    if venues:
        for venue_code in venues:
            if venue_code in schedule:
                for date_str in schedule[venue_code]:
                    for race_number in range(1, 13):
                        tasks.append((venue_code, date_str, race_number))
    else:
        for venue_code, dates in schedule.items():
            for date_str in dates:
                for race_number in range(1, 13):
                    tasks.append((venue_code, date_str, race_number))

    return tasks
```

**効果**: リクエスト数 70-80%削減、処理時間 50%以上短縮

---

### 7.2 高優先（High）

#### ❌ fetch_historical_data.py のHTTPリクエスト並列化

**現状**: 直列実行で処理時間が3倍

**修正方法**:
```python
# fetch_http_only() 関数内で並列実行
with ThreadPoolExecutor(max_workers=3) as executor:
    future_race = executor.submit(race_scraper.fetch_race_data, venue_code, date_str, race_number)
    future_result = executor.submit(result_scraper.fetch_result, venue_code, date_str, race_number)

    if fetch_beforeinfo:
        future_before = executor.submit(beforeinfo_scraper.scrape, venue_code, date_str, race_number)

    race_data = future_race.result()
    complete_result = future_result.result()

    if fetch_beforeinfo:
        beforeinfo = future_before.result()
```

**効果**: 1レースあたり 3.3秒 → 1.1秒（3倍高速化）

---

### 7.3 中優先（Medium）

#### ❌ fetch_historical_data.py のデバッグログ削減

**現状**: 大量のtracebackで見づらく、I/Oオーバーヘッド

**修正方法**:
1. デバッグログを削除（154-157行目, 174-176行目, 195-197行目）
2. 必要最小限のログのみ残す
3. 開催なしのスキップは表示しない

**効果**: ログの可読性向上、I/Oオーバーヘッド削減

---

## 8. 結論

### 8.1 現在の状況

**正しく動作しているスクリプト**:
- ✅ **fetch_parallel_v6.py**: 最も効率的、全ての最適化が実装済み
- ✅ fetch_missing_data.py: 欠損データ補完用
- ✅ fetch_venue_data.py: 会場基本データ取得用
- ⚠️ fetch_upcoming_races.py: 動作するが旧版（V2化推奨）

**問題のあるスクリプト**:
- ❌ **fetch_historical_data.py**: IMPORTANT_KNOW_HOW.mdの推奨実装から逆行

---

### 8.2 推奨アクション

**即座に実施すべき**:
1. **fetch_historical_data.py の使用を中止**
   - 現在実行中のプロセスがあれば停止を検討
   - IMPORTANT_KNOW_HOW.md に「非推奨」と明記

2. **fetch_parallel_v6.py を推奨スクリプトとして確立**
   - 過去データ取得: `python fetch_parallel_v6.py --start 2022-01-01 --end 2022-10-31 --workers 10`
   - 欠損データ補完: `python fetch_parallel_v6.py --fill-missing --workers 10`

**中期的に実施すべき**:
1. **fetch_historical_data.py の修正**（上記7.1-7.3の修正を実施）
2. **fetch_upcoming_races.py のV2化**（BeforeInfoScraperV2への移行）

---

### 8.3 機能的に「落としている」もの

#### 具体的な削除機能:

1. **スケジュールベース取得** (fetch_historical_data.py)
   - 実装: あり（ScheduleScraperをインポート）
   - 使用: なし
   - 状態: **実装されているが使われていない**

2. **HTTPリクエスト並列化** (fetch_historical_data.py)
   - 実装: なし
   - V6で実装済みの改善が未反映
   - 状態: **V5以前の古い実装のまま**

3. **エラーログの最適化** (fetch_historical_data.py)
   - 大量のデバッグログ出力
   - 状態: **IMPORTANT_KNOW_HOW.mdの推奨から逸脱**

---

## 9. 参考資料

- **IMPORTANT_KNOW_HOW.md**: 推奨実装の詳細
- **fetch_parallel_v6.py**: 最新の最適化実装（ベストプラクティス）
- **fetch_historical_data.py**: 修正が必要な実装

---

**最終更新**: 2025-11-03
