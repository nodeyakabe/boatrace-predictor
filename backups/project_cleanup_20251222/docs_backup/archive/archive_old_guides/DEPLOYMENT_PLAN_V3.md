# fetch_parallel_v3.py 導入計画

## 問題の特定

### 現状の問題点
1. **天気データが全く収集されていない** (weather テーブル: 0件)
2. **進入コース (actual_course) データが不完全** (5,358件のみ)
3. **STタイム (st_time) データが不完全** (2,767件のみ)
4. **事前情報が未収集** (exhibition_time, tilt_angle, parts_replacement)

### 根本原因
**fetch_parallel_v2.py** が以下の問題を抱えている:

```python
# 問題のコード (fetch_parallel_v2.py 70-92行目)
result_data = result_scraper.get_race_result(venue_code, date_str, race_number)
# ↑ 基本メソッドを使用 (天気・進入・STタイムを返さない)

if result_data.get('actual_courses'):
    # ... actual_coursesを保存しようとするが
    # get_race_result()はactual_coursesを返さない！
```

### 解決方法
**result_scraper.py** には完全版メソッドが既に実装済み:

```python
def get_race_result_complete(self, venue_code, race_date, race_number):
    """
    レース結果ページを1回だけ取得し、全データを抽出

    Returns:
        - results: 着順データ
        - trifecta_odds: 三連単オッズ
        - weather_data: 天気情報 ← これが必要！
        - actual_courses: 進入コース ← これが必要！
        - st_times: STタイム ← これが必要！
        - payouts: 払戻金
        - kimarite: 決まり手
    """
```

## fetch_parallel_v3.py の改善点

### 1. 完全版メソッドの使用
```python
# v2 (不完全)
result_data = result_scraper.get_race_result(...)

# v3 (完全版)
complete_result = result_scraper.get_race_result_complete(...)
```

### 2. 事前情報の統合
```python
# BeforeInfoScraperを追加
beforeinfo_scraper = BeforeInfoScraper(delay=0.5)
beforeinfo = beforeinfo_scraper.get_race_beforeinfo(venue_code, date_str, race_number)

# 展示タイム・チルト角度・部品交換を保存
if beforeinfo:
    for pit in range(1, 7):
        pit_detail = {
            'pit_number': pit,
            'exhibition_time': beforeinfo['exhibition_times'].get(pit),
            'tilt_angle': beforeinfo['tilt_angles'].get(pit),
            'parts_replacement': beforeinfo['parts_replacements'].get(pit)
        }
        detail_updates.append(pit_detail)
    db.save_race_details(race_id, detail_updates)
```

### 3. 進入コース・STタイムの保存
```python
# v3で追加
actual_courses = complete_result.get('actual_courses', {})
st_times = complete_result.get('st_times', {})

for pit in range(1, 7):
    pit_detail = {
        'pit_number': pit,
        'actual_course': actual_courses.get(pit),
        'st_time': st_times.get(pit)
    }
    detail_updates.append(pit_detail)
db.save_race_details(race_id, detail_updates)
```

### 4. 天気データの保存
```python
# v3で追加
weather_data = complete_result.get('weather_data')
if weather_data:
    weather_record = {
        'venue_code': venue_code,
        'weather_date': race_date_formatted,
        'temperature': weather_data.get('temperature'),
        'weather_condition': weather_data.get('weather_condition'),
        'wind_speed': weather_data.get('wind_speed'),
        'wind_direction': weather_data.get('wind_direction'),
        'water_temperature': weather_data.get('water_temperature'),
        'wave_height': weather_data.get('wave_height')
    }
    db.save_weather_data(weather_record)
```

## デプロイ手順

### 前提条件
- 現在実行中のデータ収集が完了していること
- データベースロックが解除されていること

### ステップ1: テスト実行

```bash
# 単一レースでのテスト
venv\Scripts\python.exe test_fetch_v3.py
```

**期待される出力:**
```
================================================================================
fetch_parallel_v3 テスト
================================================================================
対象: 21 20251023 1R

1. 出走表取得...
   [OK] 出走表取得成功: 6艇
   [OK] 出走表保存成功
   [OK] レースID: XXXX

2. 事前情報取得...
   [OK] 展示タイム: 6艇
   [OK] チルト角度: 6艇
   [OK] 部品交換: X艇
   [OK] 事前情報保存成功

3. レース結果取得（完全版）...
   [OK] 結果取得成功: 6艇
   [OK] 結果保存成功
   [OK] 進入コース: 6艇
   [OK] STタイム: 6艇
   [OK] 進入コース・STタイム保存成功
   [OK] 天気データ取得成功
      - 気温: XX度
      - 天候: 晴
      - 風速: Xm
      - 風向: XX
   [OK] 天気データ保存成功

[SUCCESS] テスト成功！全データが保存されました
```

### ステップ2: 本番デプロイ

**オプションA: 次回データ収集から適用**

auto_collect_next_month.py を修正:

```python
# 変更前
result = subprocess.run([python_path, 'fetch_parallel_v2.py', ...])

# 変更後
result = subprocess.run([python_path, 'fetch_parallel_v3.py', ...])
```

**オプションB: 手動実行 (推奨: 最初の数日)**

```bash
# 例: 2025年9月データを完全版で収集
venv\Scripts\python.exe fetch_parallel_v3.py --start 2025-09-01 --end 2025-09-30 --workers 4
```

**注意:** 並列数は4-6に設定推奨 (処理時間は4.5秒/レース程度)

### ステップ3: 検証

```python
import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 天気データ件数確認
cursor.execute("SELECT COUNT(*) FROM weather")
print(f"Weather records: {cursor.fetchone()[0]:,}")

# 進入コース充足率確認
cursor.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN actual_course IS NOT NULL THEN 1 ELSE 0 END) as filled
    FROM race_details
""")
total, filled = cursor.fetchone()
print(f"Actual course: {filled}/{total} ({filled/total*100:.1f}%)")

# STタイム充足率確認
cursor.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN st_time IS NOT NULL THEN 1 ELSE 0 END) as filled
    FROM race_details
""")
total, filled = cursor.fetchone()
print(f"ST time: {filled}/{total} ({filled/total*100:.1f}%)")

conn.close()
```

**期待される結果:**
- Weather records: > 0 (収集日数相当)
- Actual course: 100%
- ST time: 100%

## 過去データの再収集

### 必要性
既存の9,499レースには以下のデータが欠けている:
- 天気データ: 0%
- 進入コース: 約56%
- STタイム: 約29%

### 再収集スクリプト

```bash
# 2025年10月を再収集 (完全版)
venv\Scripts\python.exe fetch_parallel_v3.py --start 2025-10-01 --end 2025-10-30 --workers 4

# 2025年9月以降も同様に実行
# ※既存データは上書きされる
```

### 優先順位
1. **最優先:** 2025年データ (予測精度に直結)
2. **次優先:** 2024年後半 (直近の傾向分析)
3. **その後:** 2024年前半以前 (履歴データ)

## トラブルシューティング

### データベースロックエラー
```
sqlite3.OperationalError: database is locked
```

**原因:** 複数プロセスが同時にDB書き込み

**対処:**
1. 既存のデータ収集プロセスを確認:
   ```bash
   tasklist | findstr python
   ```
2. 必要なら待つか、プロセスを停止してから実行

### 天気データが保存されない
- result_scraper.get_race_result_complete() が None を返す
- レース結果ページがまだ存在しない (未開催)

### 進入コースが NULL
- actual_coursesがページから取得できない
- HTML構造が変更された可能性 → result_scraper.py を確認

## パフォーマンス

### 処理速度
- **v2:** 約3.5秒/レース
- **v3:** 約4.5秒/レース (+28%遅い)

追加データ取得のため若干遅くなるが、1ヶ月(8,640レース)で約10時間で完了。

### 推定時間
```
総レース数: 24会場 × 30日 × 12レース = 8,640レース
処理時間: 8,640 × 4.5秒 / 6並列 / 3600秒 = 1.8時間
```

## まとめ

### 解決される問題
✅ 天気データが完全収集される
✅ 進入コースが100%収集される
✅ STタイムが100%収集される
✅ 事前情報 (展示タイム・チルト・部品交換) が収集される

### 次のステップ
1. 現在のデータ収集完了を待つ
2. test_fetch_v3.py でテスト実行
3. fetch_parallel_v3.py を本番デプロイ
4. 過去データを段階的に再収集

---
**作成日時:** 2025-10-30
**ステータス:** テスト待ち (データベースロック解除後)
**関連ファイル:**
- [fetch_parallel_v3.py](fetch_parallel_v3.py)
- [test_fetch_v3.py](test_fetch_v3.py)
- [src/scraper/result_scraper.py](src/scraper/result_scraper.py)
- [src/scraper/beforeinfo_scraper.py](src/scraper/beforeinfo_scraper.py)
