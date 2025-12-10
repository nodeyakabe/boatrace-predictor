# 更なるデータ取得効率化・高速化の検討

## 現在の処理フロー分析

### 1レースあたりの処理

```
1. 出走表取得（racecard）           1 HTTPリクエスト
2. DB保存・race_id取得              DB操作
3. 待機（1秒）                      1秒
4. 事前情報取得（beforeinfo）       1 HTTPリクエスト
5. DB保存                           DB操作
6. 待機（1秒）                      1秒
7. 完全結果取得（raceresult）       1 HTTPリクエスト
8. DB保存（結果×5回）               DB操作
9. 待機（1.5秒）                    1.5秒
----------------------------------------
合計: 3 HTTPリクエスト + 3.5秒待機
```

**1レースあたりの実測時間**: 約5-6秒
- HTTPリクエスト: 3回 × 0.5秒 = 1.5秒
- 待機時間: 3.5秒
- DB操作: 0.5-1秒

---

## 効率化案一覧

### 案1: 並列リクエスト（最大効果）⚡⚡⚡

**概要**: 出走表・事前情報・結果を並列取得

**実装**:
```python
import concurrent.futures
import asyncio

# 3つのリクエストを並列実行
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    future_race = executor.submit(scraper.get_race_card, ...)
    future_before = executor.submit(scraper.get_beforeinfo, ...)
    future_result = executor.submit(scraper.get_race_result_complete, ...)

    race_data = future_race.result()
    beforeinfo = future_before.result()
    result_data = future_result.result()
```

**効果**:
- HTTPリクエスト時間: 3回 × 0.5秒 = 1.5秒 → **0.5秒**（並列化）
- 1レースあたり: 5-6秒 → **4-4.5秒**
- 1ヶ月: 5-6時間 → **3.5-4時間**（30-40%削減）

**リスク**: ⚠️ 中
- 同時3リクエストは検知されやすい可能性
- ただし異なるエンドポイントなので自然

**実装難易度**: 中（2-3時間）

---

### 案2: 日付単位の並列処理 ⚡⚡

**概要**: 同一競艇場の複数日を並列取得

**実装**:
```python
# 3日分を並列処理
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = []
    for date in [date1, date2, date3]:
        future = executor.submit(fetch_one_day, venue_code, date)
        futures.append(future)

    for future in concurrent.futures.as_completed(futures):
        result = future.result()
```

**効果**:
- 競艇場あたり: 10日 × 12R = 120レース
- 並列度3なら: **30%削減**
- 1ヶ月: 5-6時間 → **3.5-4時間**

**リスク**: ⚠️ 中～高
- 同一IPから複数セッション
- より検知されやすい

**実装難易度**: 中（2-3時間）

---

### 案3: 競艇場単位の並列処理 ⚡⚡⚡

**概要**: 複数競艇場を同時処理

**実装**:
```python
# 3競艇場を並列処理
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = []
    for venue in [venue1, venue2, venue3]:
        future = executor.submit(fetch_venue_data, venue, dates)
        futures.append(future)

    for future in concurrent.futures.as_completed(futures):
        result = future.result()
```

**効果**:
- 24競艇場 ÷ 3並列 = 8回のイテレーション
- 1ヶ月: 5-6時間 → **2-2.5時間**（60%削減）

**リスク**: ⚠️⚠️ 高
- 同一IPから大量の並列リクエスト
- 検知リスク大

**実装難易度**: 中（2-3時間）

---

### 案4: DB操作の一括化 ⚡

**概要**: 1レースごとではなく、1日分まとめてDB保存

**実装**:
```python
# 12レース分のデータを蓄積
race_data_list = []
for race_num in range(1, 13):
    data = fetch_race_data(...)
    race_data_list.append(data)

# 一括保存
data_manager.bulk_insert(race_data_list)
```

**効果**:
- DB接続オーバーヘッド削減
- 1レースあたり: 5-6秒 → **5-5.5秒**（10%削減）
- 1ヶ月: 5-6時間 → **4.5-5.5時間**

**リスク**: ✅ 低（HTTPアクセスパターン変わらず）

**実装難易度**: 低（1時間）

---

### 案5: 待機時間の最適化 ⚡

**概要**: 固定待機ではなく、レスポンス時間ベースの動的待機

**実装**:
```python
import time

last_request_time = 0

def smart_delay():
    elapsed = time.time() - last_request_time
    if elapsed < 2.0:
        time.sleep(2.0 - elapsed)  # 最低2秒間隔を保証
    else:
        time.sleep(0.5)  # すでに時間が経過している場合は短く
```

**効果**:
- 無駄な待機削減
- 1レースあたり: 5-6秒 → **4.5-5.5秒**（10%削減）
- 1ヶ月: 5-6時間 → **4.5-5.5時間**

**リスク**: ⚠️ 中（待機時間が短くなるケースがある）

**実装難易度**: 低（1時間）

---

### 案6: HTTP/2 接続の再利用 ⚡

**概要**: Keep-Alive接続を活用し、接続確立オーバーヘッドを削減

**実装**:
```python
import requests

# セッション再利用
session = requests.Session()
session.mount('https://', requests.adapters.HTTPAdapter(
    pool_connections=1,
    pool_maxsize=1,
    max_retries=3
))
```

**効果**:
- 接続確立時間削減: 0.1-0.2秒/リクエスト
- 1レースあたり: 5-6秒 → **4.7-5.8秒**（5%削減）
- 1ヶ月: 5-6時間 → **4.7-5.8時間**

**リスク**: ✅ 低（既に実装済み？要確認）

**実装難易度**: 低（30分）

---

### 案7: resultlistエンドポイントの活用 ⚡⚡

**概要**: 1日分の12レース結果を1リクエストで取得

**エンドポイント**: `/resultlist?jcd=XX&hd=YYYYMMDD`

**実装**:
```python
# 1リクエストで12レース分の1-2-3着取得
results = result_scraper.get_all_race_results_by_date(venue_code, date_str)

# 詳細が必要なレースのみ個別取得
for race in results:
    if need_details(race):
        details = get_race_result_complete(...)
```

**効果**:
- 12レース × 1リクエスト = 12リクエスト → **1リクエスト**
- 1日あたり: 60-72秒 → **30-40秒**（50%削減）
- 1ヶ月: 5-6時間 → **2.5-3時間**

**リスク**: ✅ 低（公式が提供しているエンドポイント）

**実装難易度**: 中（2時間）

**注意**: `get_all_race_results_by_date()`は既に実装済み！（result_scraper.py:439行目）

---

### 案8: キャッシュ機構の導入 ⚡

**概要**: 既にDBに存在するレースはスキップ

**実装**:
```python
# DBチェック
existing = data_manager.check_race_exists(venue_code, date, race_num)
if existing and existing['has_complete_data']:
    print(f"  R{race_num}: キャッシュ使用")
    continue
```

**効果**:
- 再実行時に劇的に高速化
- 初回実行: 変化なし
- 2回目以降: **ほぼ即座に完了**

**リスク**: ✅ 低

**実装難易度**: 低（1時間）

---

## 効率化案の比較

| 案 | 削減率 | リスク | 実装時間 | 1ヶ月推定時間 | 推奨度 |
|----|--------|--------|----------|-------------|--------|
| 現行 | - | 中 | - | 5-6時間 | - |
| 案1: 並列リクエスト | 30% | 中 | 2-3h | 3.5-4時間 | ⭐⭐⭐ |
| 案2: 日付並列 | 30% | 中～高 | 2-3h | 3.5-4時間 | ⭐⭐ |
| 案3: 競艇場並列 | 60% | 高 | 2-3h | 2-2.5時間 | ⭐ |
| 案4: DB一括化 | 10% | 低 | 1h | 4.5-5.5時間 | ⭐⭐⭐ |
| 案5: 動的待機 | 10% | 中 | 1h | 4.5-5.5時間 | ⭐⭐ |
| 案6: HTTP/2 | 5% | 低 | 0.5h | 4.7-5.8時間 | ⭐⭐⭐ |
| 案7: resultlist活用 | 50% | 低 | 2h | 2.5-3時間 | ⭐⭐⭐⭐⭐ |
| 案8: キャッシュ | 0%→100% | 低 | 1h | 2回目:即座 | ⭐⭐⭐⭐ |

---

## 推奨実装プラン

### プランA: 安全重視（推奨）⭐⭐⭐⭐⭐

**実装順序**:
1. **案7: resultlist活用**（2時間） → 50%削減
2. **案8: キャッシュ**（1時間） → 再実行時100%削減
3. **案6: HTTP/2最適化**（0.5時間） → さらに5%削減
4. **案4: DB一括化**（1時間） → さらに5%削減

**合計実装時間**: 4.5時間
**最終的な1ヶ月取得時間**: **2-2.5時間**（60%削減）
**リスク**: ✅ 低
**ROI**: ⭐⭐⭐⭐⭐

---

### プランB: バランス型

**実装順序**:
1. **案7: resultlist活用**（2時間） → 50%削減
2. **案1: 並列リクエスト**（2-3時間） → さらに15%削減

**合計実装時間**: 4-5時間
**最終的な1ヶ月取得時間**: **1.5-2時間**（70%削減）
**リスク**: ⚠️ 中
**ROI**: ⭐⭐⭐⭐

---

### プランC: 最速（非推奨）

**実装順序**:
1. **案7: resultlist活用**（2時間）
2. **案1: 並列リクエスト**（2-3時間）
3. **案3: 競艇場並列**（2-3時間）

**合計実装時間**: 6-8時間
**最終的な1ヶ月取得時間**: **30-45分**（90%削減）
**リスク**: ⚠️⚠️⚠️ 非常に高
**ROI**: ⭐⭐

---

## 詳細: 案7（resultlist活用）の実装

### 既存実装の確認

`result_scraper.py`の439行目に既に実装済み：

```python
def get_all_race_results_by_date(self, venue_code, race_date):
    """
    指定日の全レース結果を一括取得（resultlistエンドポイント使用）

    効率重視: 1リクエストで12レース分取得
    """
```

### 活用方法

**現在の処理**:
```python
# 各レースごとに3リクエスト
for race_num in range(1, 13):
    race_data = get_race_card(...)          # 1
    beforeinfo = get_beforeinfo(...)        # 2
    result = get_race_result_complete(...)  # 3
```

**最適化後**:
```python
# 1. 1日分の結果を一括取得（1リクエスト）
results_summary = result_scraper.get_all_race_results_by_date(venue_code, date_str)

# 2. 各レースの詳細を取得（12レース × 2リクエスト = 24リクエスト）
for race_num in range(1, 13):
    race_data = get_race_card(...)     # 出走表
    beforeinfo = get_beforeinfo(...)   # 事前情報
    # 結果は results_summary[race_num-1] から取得（リクエスト不要）
```

**削減効果**:
- 1日あたり: 36リクエスト → **25リクエスト**（30%削減）
- ただし、resultlistは1-2-3着のみ（詳細データなし）

### より高度な活用

**戦略**: resultlistで開催レースを事前確認

```python
# ステップ1: 開催レース確認（1リクエスト）
results_summary = get_all_race_results_by_date(venue_code, date_str)
if not results_summary:
    # 開催なし → スキップ
    continue

# ステップ2: 開催が確認されたレースのみ詳細取得
for result in results_summary:
    race_num = result['race_number']
    if result['is_invalid']:
        # 返還レース → スキップ
        continue

    # 詳細取得
    race_data = get_race_card(...)
    beforeinfo = get_beforeinfo(...)
    complete_result = get_race_result_complete(...)
```

**メリット**:
- 未開催日の判定が1リクエストで完結
- 返還レースをスキップ可能

---

## 実装の注意点

### 並列処理時の注意

1. **セッション管理**
   ```python
   # NG: セッション共有（スレッドセーフでない）
   scraper = RaceScraper()  # 共有インスタンス

   # OK: スレッドごとに独立したインスタンス
   def worker(venue):
       scraper = RaceScraper()  # 各スレッドで生成
   ```

2. **User-Agentの分散**
   ```python
   # 各スレッドで異なるUser-Agentを使用
   user_agents = [UA1, UA2, UA3]
   for i, venue in enumerate(venues):
       thread_scraper = RaceScraper()
       thread_scraper.set_user_agent(user_agents[i % 3])
   ```

3. **エラーハンドリング**
   ```python
   # 1スレッドのエラーで全体が止まらないように
   with concurrent.futures.ThreadPoolExecutor() as executor:
       futures = [executor.submit(fetch, v) for v in venues]
       for future in concurrent.futures.as_completed(futures):
           try:
               result = future.result()
           except Exception as e:
               print(f"エラー: {e}")
               continue  # 他のスレッドは継続
   ```

---

## 検知リスクの再評価

### 案7（resultlist活用）のリスク

**評価**: ✅ 低

**理由**:
1. 公式が提供しているエンドポイント
2. 一般ユーザーも使用可能
3. リクエスト数削減 → より自然
4. 待機時間は変わらず

**推奨**: 即座に実装すべき

### 並列処理のリスク

**案1（レース並列）**: ⚠️ 中
- 異なるエンドポイント（racecard, beforeinfo, raceresult）
- 同時3リクエストは許容範囲内

**案2（日付並列）**: ⚠️ 中～高
- 同じ競艇場への複数セッション
- やや不自然

**案3（競艇場並列）**: ⚠️⚠️ 高
- 異なる競艇場でも同一ドメイン（boatrace.jp）
- 大量の並列接続は検知されやすい

---

## まとめ

### 即座に実装すべき

1. ✅ **案7: resultlist活用**（既存メソッド活用）
   - 実装時間: 2時間
   - 削減率: 30-50%
   - リスク: 低

2. ✅ **案8: キャッシュ機構**
   - 実装時間: 1時間
   - 削減率: 再実行時100%
   - リスク: 低

3. ✅ **案6: HTTP/2最適化**
   - 実装時間: 30分
   - 削減率: 5%
   - リスク: 低

### 慎重に検討すべき

4. ⚠️ **案1: 並列リクエスト**
   - リスク中、効果高
   - テスト実行後に判断

5. ⚠️ **案4: DB一括化**
   - リスク低、効果中

### 非推奨

6. ❌ **案2: 日付並列**（リスク高）
7. ❌ **案3: 競艇場並列**（リスク非常に高）
8. ❌ **案5: 動的待機**（リスク中、効果低）

---

## 次のアクション

### 提案1: resultlist活用版を今すぐ実装

**所要時間**: 2時間
**効果**: 1ヶ月5-6時間 → **2.5-3時間**

### 提案2: 現行を継続、次回からresultlist活用

**理由**: 現在既に実行中（桐生の処理中）
**次回実装**: 次の期間（11月、12月等）

どちらを希望しますか？
