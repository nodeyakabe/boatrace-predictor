# 競艇オッズスクレイピング技術ガイド

## 概要

競艇公式サイト（boatrace.jp）から3連単オッズを取得するための技術的知見をまとめる。

## 重要な発見

### 1. JavaScript動的レンダリング問題

**問題**: 3連単オッズはJavaScriptで動的にレンダリングされるため、通常のHTTPリクエストでは取得できない。

```python
# HTTPリクエストでは失敗
import requests
response = requests.get(url)  # HTMLにオッズデータが含まれない
```

**解決策**: ブラウザ自動化ツール（Playwright）を使用

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until='domcontentloaded')
    page.wait_for_timeout(5000)  # JS実行を待つ
    html = page.content()  # 完全なHTMLを取得
```

### 2. 競艇公式サイトのURL構造

```
3連単オッズ: https://www.boatrace.jp/owpc/pc/race/odds3t?rno={race}&jcd={venue}&hd={date}
2連単/複オッズ: https://www.boatrace.jp/owpc/pc/race/oddstf?rno={race}&jcd={venue}&hd={date}
単勝/複勝オッズ: https://www.boatrace.jp/owpc/pc/race/oddstf?rno={race}&jcd={venue}&hd={date}
```

パラメータ:
- `rno`: レース番号（1-12）
- `jcd`: 競艇場コード（2桁、例: '01'=桐生, '02'=戸田）
- `hd`: 日付（YYYYMMDD形式）

### 3. HTMLテーブル構造の解析

3連単オッズテーブルは特殊な構造を持つ:

```
テーブル構造:
- 1行目: ヘッダー
- 2行目以降: データ行

行の種類:
1. 18セル行（新しい2着の開始）
   [2着, 3着, オッズ] × 6列（1着1号艇〜6号艇）

2. 12セル行（同じ2着の継続）
   [3着, オッズ] × 6列

パターン:
- 行1,5,9,13,17: 18セル（新2着）
- 行2-4,6-8,10-12,14-16,18-20: 12セル（残り3着）
- 4行で1つの2着が完了
```

**実装例**:

```python
def _parse_trifecta_odds(self, html: str) -> dict:
    soup = BeautifulSoup(html, 'html.parser')
    odds_data = {}
    current_second = {}  # 各1着に対する現在の2着を管理

    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 20:
            continue

        for row in rows[1:]:  # ヘッダーをスキップ
            cells = row.find_all('td')
            cell_texts = [c.get_text(strip=True) for c in cells]

            if len(cell_texts) >= 18:
                # 新しい2着の開始
                for first in range(1, 7):
                    offset = (first - 1) * 3
                    second = int(cell_texts[offset])
                    third = int(cell_texts[offset + 1])
                    odds = float(cell_texts[offset + 2].replace(',', ''))
                    current_second[first] = second
                    odds_data[f"{first}-{second}-{third}"] = odds
            elif len(cell_texts) >= 12:
                # 同じ2着の残りの3着
                for first in range(1, 7):
                    offset = (first - 1) * 2
                    third = int(cell_texts[offset])
                    odds = float(cell_texts[offset + 1].replace(',', ''))
                    second = current_second[first]
                    odds_data[f"{first}-{second}-{third}"] = odds

    return odds_data  # 120通り
```

### 4. 単勝オッズ取得（HTTPで可能）

単勝・複勝オッズはJavaScriptレンダリング不要:

```python
def get_win_odds(self, venue_code: str, race_date: str, race_number: int):
    url = f"https://www.boatrace.jp/owpc/pc/race/oddstf?rno={race_number}&jcd={venue_code}&hd={race_date}"
    response = self.session.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # oddsPoint__labelクラスから艇番、oddsPoint__oddsからオッズを取得
    labels = soup.find_all('div', class_='oddsPoint__label')
    odds_values = soup.find_all('div', class_='oddsPoint__odds')

    odds_data = {}
    for i, (label, odds) in enumerate(zip(labels[:6], odds_values[:6]), 1):
        odds_data[i] = float(odds.get_text(strip=True))

    return odds_data  # {1: 1.2, 2: 4.2, ...}
```

### 5. Selenium vs Playwright

| 項目 | Selenium | Playwright |
|------|----------|------------|
| 安定性 | 低（headlessでクラッシュ多発） | 高（安定動作） |
| 速度 | 遅い | 速い |
| セットアップ | ChromeDriver必要 | `playwright install`で完了 |
| Windows対応 | 問題あり | 良好 |
| **推奨** | × | ✓ |

### 6. 期待値計算

```python
def calculate_expected_value(probability: float, odds: float) -> float:
    """
    期待値 = 予測確率 × 実際のオッズ

    期待値 > 1.0: プラス期待値（推奨）
    期待値 = 1.0: 期待値ゼロ
    期待値 < 1.0: マイナス期待値
    """
    return probability * odds

# ケリー基準（最適賭け金比率）
def kelly_criterion(probability: float, odds: float) -> float:
    """
    f* = (p × odds - (1-p)) / odds
    """
    return max(0, (probability * odds - (1 - probability)) / odds)
```

## 実装されたスクレイパー

### 1. PlaywrightOddsScraper（推奨）

場所: `src/scraper/playwright_odds_scraper.py`

```python
from src.scraper.playwright_odds_scraper import PlaywrightOddsScraper

scraper = PlaywrightOddsScraper(headless=True, timeout=30000)
odds = scraper.get_trifecta_odds('02', '20251117', 1)
# {'1-2-3': 10.1, '1-2-4': 18.1, ...} 120通り
```

### 2. OddsScraper（単勝用）

場所: `src/scraper/odds_scraper.py`

```python
from src.scraper.odds_scraper import OddsScraper

scraper = OddsScraper()
win_odds = scraper.get_win_odds('02', '20251117', 1)
# {1: 1.2, 2: 4.2, 3: 15.8, 4: 3.5, 5: 25.1, 6: 42.3}
```

### 3. RealtimeOddsPredictor（統合システム）

場所: `src/prediction/realtime_odds_predictor.py`

```python
from src.prediction.realtime_odds_predictor import RealtimeOddsPredictor

predictor = RealtimeOddsPredictor(use_playwright=True)
result = predictor.analyze_race('02', '20251117', 1, race_features)
# オッズ取得 + 確率計算 + 期待値計算を一括実行
```

## トラブルシューティング

### 問題1: オッズが30通りしか取得できない

**原因**: テーブル構造の誤解析。18セル行と12セル行を区別していない。

**解決**: `current_second`辞書で各1着の現在の2着を追跡する。

### 問題2: Seleniumがクラッシュする

**原因**: Windowsのheadlessモードでの互換性問題。

**解決**: Playwrightに移行する。

```bash
pip install playwright
playwright install chromium
```

### 問題3: ページ読み込みタイムアウト

**原因**: JavaScriptの実行時間が不足。

**解決**: `wait_for_timeout(5000)`で十分な待機時間を確保。

## 競艇場コード一覧

```
01: 桐生    07: 蒲郡    13: 尼崎    19: 下関
02: 戸田    08: 常滑    14: 鳴門    20: 若松
03: 江戸川  09: 津      15: 丸亀    21: 芦屋
04: 平和島  10: 三国    16: 児島    22: 福岡
05: 多摩川  11: びわこ  17: 宮島    23: 唐津
06: 浜名湖  12: 住之江  18: 徳山    24: 大村
```

## パフォーマンス考慮事項

1. **リクエスト間隔**: 最低1秒の遅延を設ける（サーバー負荷軽減）
2. **ブラウザ再利用**: 複数レースを連続取得する場合はブラウザを再起動しない
3. **タイムアウト設定**: 30秒程度が適切
4. **エラーハンドリング**: ネットワークエラー、タイムアウトに対応

## 今後の改善案

1. **キャッシュ機能**: 同じレースのオッズを再取得しない
2. **並列取得**: 複数会場のオッズを同時に取得
3. **オッズ変動監視**: 締め切り前のオッズ変動を追跡
4. **自動リトライ**: ネットワークエラー時の自動再試行
