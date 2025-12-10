# 決まり手データ調査結果

## 🎉 重要な発見: 決まり手データは実は99.9%取得できている！

### 問題の原因
`data_coverage_checker.py`の集計方法が不適切だった。

**現在の集計方法（誤り）:**
```python
# 全艇（184,572件）のうち、決まり手が入っているレコード数をカウント
SELECT COUNT(*) FROM results WHERE kimarite IS NOT NULL
→ 結果: 30,668 / 181,996 = 16.9%
```

**正しい集計方法:**
```python
# 1着艇のみで決まり手をカウント（決まり手は1着艇にのみ記録される）
SELECT COUNT(*) FROM results WHERE rank = '1' AND kimarite IS NOT NULL
→ 結果: 31,174 / 31,204 = 99.9% ✅
```

---

## データの実態

### resultsテーブルの構造
```
- id (INTEGER)
- race_id (INTEGER)
- pit_number (INTEGER)
- rank (TEXT)
- is_invalid (INTEGER)
- trifecta_odds (REAL)
- created_at (TIMESTAMP)
- kimarite (TEXT)           ← テキスト形式（例: "逃げ", "差し", "まくり"）
- winning_technique (INTEGER) ← 数値形式（1=逃げ, 2=差し, 3=まくり, 4=まくり差し, 5=抜き, 6=恵まれ）
```

### 実際のデータサンプル（1着艇）
```
会場 | 日付       | R  | 決まり手(text) | 決まり手(int)
-----|-----------|----|--------------|--------------
  21 | 2025-09-04|  7 | 逃げ          | 1
  18 | 2025-08-06|  4 | 逃げ          | 1
  11 | 2025-10-07|  2 | 逃げ          | 1
  06 | 2023-12-11|  6 | 差し          | 2
  09 | 2024-06-07|  8 | まくり         | 3
  01 | 2024-10-16| 11 | 差し          | なし (rare case)
  06 | 2024-10-17| 11 | 逃げ          | 1
  02 | 2025-10-16|  2 | まくり差し      | 4
  07 | 2024-03-15|  7 | 逃げ          | 1
  23 | 2025-07-20| 11 | 逃げ          | 1
```

**99.9%のレースで正しく取得できている！**

---

## 決まり手データの取得ロジック

### ResultScraperの実装（src/scraper/result_scraper.py）

#### 1. `get_race_result()` メソッド（170-191行目）
HTMLページから「決まり手○○」というテキストパターンを正規表現で検索：

```python
technique_map = {
    '逃げ': 1,
    '差し': 2,
    'まくり差し': 4,  # 先にチェック（「まくり」より優先）
    'まくり': 3,
    '抜き': 5,
    '恵まれ': 6
}

for technique_name, technique_code in technique_map.items():
    if f'決まり手{technique_name}' in normalized_text or f'決まり手：{technique_name}' in normalized_text:
        result_data["winning_technique"] = technique_code
        break
```

#### 2. `get_winning_technique()` メソッド（451-510行目）
より詳細な決まり手抽出メソッドも存在（単独でも使用可能）

#### 3. `get_payouts_and_kimarite()` メソッド（984-1135行目）
払戻金と決まり手を同時に取得するメソッド

---

## 修正が必要な箇所

### data_coverage_checker.py の修正

**現在のコード（540-549行目）:**
```python
# 決まり手（kimarite列確認）
cursor.execute("PRAGMA table_info(results)")
columns = [col[1] for col in cursor.fetchall()]
has_kimarite = 'kimarite' in columns

if has_kimarite:
    cursor.execute("SELECT COUNT(*) FROM results res JOIN races r ON res.race_id = r.id WHERE r.race_status = 'completed' AND res. kimarite IS NOT NULL")
    count = cursor.fetchone()[0]
else:
    count = 0
```

**修正後のコード:**
```python
# 決まり手（1着艇のみカウント）
cursor.execute("PRAGMA table_info(results)")
columns = [col[1] for col in cursor.fetchall()]
has_kimarite = 'kimarite' in columns

if has_kimarite:
    # 1着艇のみでカウント
    cursor.execute("""
        SELECT COUNT(*)
        FROM results res
        JOIN races r ON res.race_id = r.id
        WHERE r.race_status = 'completed'
        AND res.rank = '1'
        AND (res.kimarite IS NOT NULL OR res.winning_technique IS NOT NULL)
    """)
    count = cursor.fetchone()[0]

    # 総レース数（1着艇の数）
    cursor.execute("""
        SELECT COUNT(*)
        FROM results res
        JOIN races r ON res.race_id = r.id
        WHERE r.race_status = 'completed'
        AND res.rank = '1'
    """)
    total_first_place = cursor.fetchone()[0]
else:
    count = 0
    total_first_place = total_races

items.append({
    "name": "決まり手",
    "importance": 4,
    "status": "未取得" if count == 0 else "取得済み",
    "coverage": count / total_first_place if total_first_place > 0 else 0,
    "count": count,
    "total": total_first_place  # 全艇数ではなく1着艇数
})
```

---

## まとめ

### ✅ 良いニュース
- **決まり手データは既に99.9%収集済み**
- スクレイピングロジックは正常に動作している
- 追加のデータ収集は**不要**

### 🔧 必要な対応
- `data_coverage_checker.py`の集計ロジックを修正（1着艇のみカウント）
- UIに表示される充足率が16.3% → 99.9%に修正される

### 📊 更新後のデータ充足率
```
進入コース:   76.8% → 100% (収集中)
STタイム:     64.3% → 100% (収集中)
展示タイム:   82.4% → 100% (収集中)
チルト角度:   82.4% → 100% (収集中)
決まり手:     16.3% → 99.9% (既に完了！) ✅
```

---

## 次のステップ

1. **優先度1:** 現在の事前情報収集を完了させる（6,894件、残り約1時間）
2. **優先度2:** `data_coverage_checker.py`を修正して正しい充足率を表示
3. **優先度3:** 潮汐データの検討（長期的課題）
