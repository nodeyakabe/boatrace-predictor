# HTMLダウンロード案の分析

**質問**: 各ページごとにブラウザソースをDLするのは不可能？

**回答**: 可能だが、速度向上効果はほぼゼロ

---

## 現在の処理フロー

```
1. HTTPリクエスト送信     → 1-2秒
2. HTMLダウンロード       → 1-2秒  ← 既にやっている
3. HTMLパース             → 5-8秒  ← ボトルネック
4. DB保存                 → 0.09秒
--------------------------------
合計: 9-12秒/ページ
```

**問題**: HTMLパース（BeautifulSoup）が遅い（5-8秒）

---

## HTMLを保存してから処理する案

### 方法1: HTML保存後に別処理

```python
# フェーズ1: HTML一括ダウンロード（高速）
for race in races:
    html = requests.get(url).text
    with open(f'html/{race}.html', 'w') as f:
        f.write(html)
    time.sleep(0.1)  # 待機時間短縮可能？

# フェーズ2: HTML読み込み→パース→DB保存
for file in html_files:
    with open(file) as f:
        html = f.read()
    soup = BeautifulSoup(html, 'lxml')  # ← 依然として遅い
    data = parse(soup)
    save_to_db(data)
```

**効果**:
- HTTPダウンロード: 変わらず
- HTMLパース: **変わらず**（依然として5-8秒）
- 合計時間: **ほぼ同じ**

**メリット**:
- HTML保存時の待機時間を短縮できる可能性（検知リスク増）
- データ再処理が容易

**デメリット**:
- ディスク容量消費（1ヶ月 = 数GB）
- 2段階処理で管理が複雑

---

## なぜ速くならないか

### 時間の内訳（実測）

| 処理 | 時間 | 削減可能？ |
|-----|------|----------|
| HTTPリクエスト | 1-2秒 | △（並列化で可能） |
| HTMLダウンロード | 1-2秒 | ❌ |
| **HTMLパース** | **5-8秒** | ✅ **selectolax** |
| DB保存 | 0.09秒 | ❌ |

**HTMLパースが全体の60-70%を占める**ため、HTML保存しても速くなりません。

---

## 真の高速化方法

### 解決策: selectolax使用

```python
# BeautifulSoup (遅い)
soup = BeautifulSoup(html, 'lxml')  # 5-8秒
data = soup.select_one('.racer-name').get_text()

# selectolax (速い)
tree = HTMLParser(html)  # 0.5-1秒（8-10倍高速！）
data = tree.css_first('.racer-name').text()
```

**効果**: 5-8秒 → 0.5-1秒（**8-10倍高速化**）

---

## 結論

### HTML保存案の評価

| 項目 | 評価 |
|-----|------|
| 実装可能性 | ✅ 可能 |
| 速度向上 | ❌ ほぼゼロ（5-10%程度） |
| 実装コスト | 中 |
| ディスク消費 | 大（数GB） |
| **推奨度** | ❌ **非推奨** |

### 推奨方法

**selectolax移行**:
- 速度向上: 50-70%
- 実装コスト: 中
- ディスク消費: ゼロ
- **推奨度**: ⭐⭐⭐⭐⭐

---

## ただし、HTML保存のメリット

### データ再処理が必要な場合

HTML保存は以下の場合に有効：

1. **パース処理を複数回実行する**
   - データ構造変更時
   - バグ修正後の再処理

2. **分析用に生データ保存**
   - 将来的に追加データ抽出

3. **バックアップ**
   - サイト仕様変更時の保険

### 実装例

```python
# オプション: HTML保存機能付きスクレイパー
class CachingScraper:
    def fetch_with_cache(self, url, cache_dir='html_cache'):
        cache_file = f"{cache_dir}/{hash(url)}.html"

        if os.path.exists(cache_file):
            # キャッシュから読み込み
            with open(cache_file) as f:
                html = f.read()
        else:
            # ダウンロード＆保存
            html = requests.get(url).text
            with open(cache_file, 'w') as f:
                f.write(html)

        return HTMLParser(html)  # selectolax使用
```

---

## 最終推奨

### 今すぐ実行: selectolax移行

HTMLダウンロードより**10倍以上効果的**

### オプション: HTML保存機能追加

selectolax移行後、余裕があれば追加
