# オリジナル展示スクレイパー修正報告

## 実施日時
2025年11月11日

---

## 問題の発見

### 症状
[src/scraper/original_tenji_browser.py](src/scraper/original_tenji_browser.py:116-175) が以下の問題を抱えていた:
- **直線タイム (chikusen_time)**: 常にNone
- **一周タイム (isshu_time)**: 正常に取得
- **回り足タイム (mawariashi_time)**: 常にNone

### テストURL
```
https://boaters-boatrace.com/race/tamagawa/2025-11-10/1R/last-minute?last-minute-content=original-tenji
```

### 期待値（1号艇）
- 直線タイム: **7.03**秒
- 一周タイム: **36.80**秒
- 回り足タイム: **5.57**秒

### 修正前の取得結果
- 直線タイム: **None**
- 一周タイム: **36.80**秒 ✓
- 回り足タイム: **None**

---

## 原因分析

### 誤ったHTML構造の想定

**修正前のコード**:
```python
# グリッドコンテナから抽出
grid_container = self.driver.find_element(By.CSS_SELECTOR, ".css-15871fl")
cells = grid_container.find_elements(By.CSS_SELECTOR, "div")

# 各艇のデータは9セルずつ
CELLS_PER_ROW = 9
base_index = data_start + ((boat_num - 1) * CELLS_PER_ROW)

# 1周タイムのみ取得
isshu_cell = cells[base_index + 5]
isshu = float(isshu_cell.text.strip())

# 回り足・直線はNone
mawariashi = None
chikusen = None
```

### 実際のHTML構造

HTMLの詳細分析により、以下が判明:

1. **`.css-15871fl` グリッドコンテナは表示用のレイアウトコンテナ**
   - セル数: 60個
   - 内容: 枠番、レーサー名、合算値、平均との差など
   - **直線タイムと回り足タイムは含まれていない**

2. **実際のデータは `.css-1qmyagr` コンテナに格納**
   - 総コンテナ数: 24個 (6艇 × 4データ)
   - 構造:
     ```
     各艇につき4つの連続したコンテナ:
       コンテナ0: 一周タイム (isshu_time)     例: 36.80
       コンテナ1: 回り足タイム (mawariashi_time) 例: 5.57
       コンテナ2: 直線タイム (chikusen_time)   例: 7.03
       コンテナ3: 展示タイム (tenji_time)      例: 6.75
     ```

### 検証結果

`.css-1qmyagr` コンテナの内容:
```
Container 0: 36.80  # 1号艇 一周
Container 1: 5.57   # 1号艇 回り足
Container 2: 7.03   # 1号艇 直線
Container 3: 6.75   # 1号艇 展示
Container 4: 37.61  # 2号艇 一周
Container 5: 5.93   # 2号艇 回り足
...
```

---

## 修正内容

### 修正したファイル
[src/scraper/original_tenji_browser.py](src/scraper/original_tenji_browser.py:116-175)

### 変更点

**修正前** (lines 119-188):
```python
# 誤ったグリッドコンテナから抽出
grid_container = self.driver.find_element(By.CSS_SELECTOR, ".css-15871fl")
cells = grid_container.find_elements(By.CSS_SELECTOR, "div")

# 複雑なインデックス計算
CELLS_PER_ROW = 9
data_start = 0
for i, cell in enumerate(cells):
    if cell.text.strip() == '1':
        data_start = i
        break

base_index = data_start + ((boat_num - 1) * CELLS_PER_ROW)
isshu = float(cells[base_index + 5].text.strip())

# 回り足・直線は取得できず
mawariashi = None
chikusen = None
```

**修正後** (lines 119-175):
```python
# 正しいデータコンテナから抽出
data_containers = self.driver.find_elements(By.CSS_SELECTOR, ".css-1qmyagr")

# 各艇のデータは4つの連続したコンテナに格納
for boat_num in range(1, 7):
    base_index = (boat_num - 1) * 4

    # インデックスが範囲内か確認
    if base_index + 3 >= len(data_containers):
        continue

    # 各タイムを個別に取得
    isshu = float(data_containers[base_index].text.strip())
    mawariashi = float(data_containers[base_index + 1].text.strip())
    chikusen = float(data_containers[base_index + 2].text.strip())

    result[boat_num] = {
        'chikusen_time': chikusen,
        'isshu_time': isshu,
        'mawariashi_time': mawariashi
    }
```

---

## テスト結果

### テストケース: 多摩川 2025-11-10 1R

**実行コマンド**:
```python
scraper = OriginalTenjiBrowserScraper(headless=True)
data = scraper.get_original_tenji('05', '2025-11-10', 1)
```

**結果**:
```
[OK] データ取得成功
取得艇数: 6艇

1号艇:
  直線タイム (chikusen): 7.03秒
  一周タイム (isshu): 36.8秒
  回り足タイム (mawariashi): 5.57秒

期待値との比較（1号艇）:
期待: 直線=7.03, 一周=36.80, 回り足=5.57
取得: 直線=7.03, 一周=36.8, 回り足=5.57
[OK] 完全一致！
```

**全艇のデータ** (多摩川 2025-11-10 1R):
```
1号艇: 直線=7.03, 一周=36.8, 回り足=5.57
2号艇: 直線=7.2, 一周=37.61, 回り足=5.93
3号艇: 直線=7.02, 一周=37.3, 回り足=5.73
4号艇: 直線=6.98, 一周=36.9, 回り足=5.53
5号艇: 直線=7.33, 一周=37.87, 回り足=5.43
6号艇: 直線=7.03, 一周=38.27, 回り足=6.2
```

**結論**: **全6艇のデータを正常に取得**

---

## 修正の影響範囲

### 影響を受ける機能
1. **オリジナル展示データの取得** (src/scraper/original_tenji_browser.py)
   - 修正前: 一周タイムのみ取得可能
   - 修正後: 直線・一周・回り足の3タイム全て取得可能

2. **日次データ収集**
   - 修正により、今後のデータ収集で完全なデータを取得できる
   - 過去データは依然として取得不可（ボータースサイトの制約）

### 影響を受けないもの
- ST時間データ補充 (fix_st_times.py)
- レース詳細データ補充 (fetch_improved_v3.py)
- データベースの既存データ

---

## 今後の運用

### オリジナル展示データの特性

**重要な制約**:
- **データソース**: boaters-boatrace.com のみ（公式サイトにはなし）
- **取得可能期間**: 前日～当日のみ
- **過去データ**: 取得不可能

### 推奨される運用方法

#### 1. 日次自動収集の実施
```bash
# 毎日実行するスクリプト
python fetch_original_tenji_daily.py
```

実行タイミング:
- **前日の夜 (20:00頃)**: 翌日のレースデータが公開された後
- **当日の朝 (8:00頃)**: レース開始前

#### 2. タスクスケジューラによる自動化

**Windows (タスクスケジューラ)**:
```
トリガー: 毎日 20:00
操作: python fetch_original_tenji_daily.py
```

**Linux/Mac (cron)**:
```bash
0 20 * * * cd /path/to/project && python fetch_original_tenji_daily.py
```

---

## データベースへの影響

### 現状のオリジナル展示データ

| 項目 | レース数 | カバー率 |
|------|---------|----------|
| 直線タイム | 115 | 0.1% |
| 一周タイム | 116 | 0.1% |
| 回り足タイム | 115 | 0.1% |

**理由**: 過去データは取得不可能

### 今後の見通し

**日次収集を開始した場合**:
- **1ヶ月後**: 約360レース分のデータ蓄積
- **1年後**: 約4,380レース分のデータ蓄積
- **カバー率**: 新規データの100%

---

## まとめ

### 作業成果

- [x] HTML構造の詳細分析
- [x] グリッド構造のバグ修正
- [x] `.css-15871fl` → `.css-1qmyagr` への変更
- [x] 3タイム（直線・一周・回り足）の完全取得
- [x] テスト実行・検証完了
- [x] ドキュメント更新

### 技術的知見

1. **HTML構造の複雑性**
   - 表示用レイアウト (.css-15871fl) と実データ (.css-1qmyagr) が分離
   - CSSセレクタの選択が重要

2. **データコンテナの構造**
   - 各艇につき4つの連続したコンテナ
   - 単純な4倍インデックス計算で取得可能

3. **エラーハンドリング**
   - コンテナ数の範囲チェックが重要
   - データなしの場合は None を返す

### 次のステップ

1. **日次収集スクリプトの作成** (fetch_original_tenji_daily.py)
2. **自動実行の設定** (タスクスケジューラ)
3. **データ蓄積の開始**

---

**作成日時**: 2025-11-11 16:00
**状態**: 修正完了、テスト済み、運用準備完了
**修正ファイル**: [src/scraper/original_tenji_browser.py](src/scraper/original_tenji_browser.py)
