# オッズAPI実装状況

## 現在の状態

### ✅ 実装済み
1. **OddsFetcherクラス** (`src/scraper/odds_fetcher.py`)
   - BOAT RACE公式サイトからオッズをスクレイピングする基本構造
   - 三連単オッズ取得機能
   - 特定組み合わせのオッズ取得機能
   - モックオッズ生成機能（フォールバック）

2. **UI統合** (`ui/app.py` - リアルタイム予想タブ)
   - オッズAPI呼び出し
   - エラー時の自動フォールバック
   - ユーザーへの状態表示（成功/警告/情報）

### ⚠️ 制限事項

1. **実際のスクレイピングは動作未確認**
   - BOAT RACE公式サイトのHTML構造は推測で実装
   - タイムアウトが発生する可能性あり
   - アンチスクレイピング対策により接続拒否の可能性あり

2. **現在はモックオッズを使用**
   - 予測確率から逆算してオッズを生成
   - 市場効率80%と仮定
   - `odds = 1.0 / (prob * 0.8)`

### 📊 モックオッズの精度

モックオッズは以下のロジックで生成されます：

```python
def generate_mock_odds(predictions: list) -> Dict[str, float]:
    """
    モックオッズを生成

    Args:
        predictions: [{'combination': '1-2-3', 'prob': 0.15}, ...]

    Returns:
        {'1-2-3': 8.3, '1-2-4': 10.4, ...}
    """
    odds_data = {}

    for pred in predictions:
        combination = pred['combination']
        prob = pred['prob']

        # 市場効率80%と仮定
        implied_prob = prob * 0.8
        if implied_prob > 0:
            odds_data[combination] = 1.0 / implied_prob
        else:
            odds_data[combination] = 100.0

    return odds_data
```

**利点:**
- 予測確率と整合性が取れている
- Kelly基準の計算には十分な精度
- 常に利用可能（ネットワークエラーなし）

**欠点:**
- 実際の市場オッズとは異なる
- 市場の歪み（バリューベット）を検出できない
- 実際の投資には不向き

---

## 実際のオッズAPIを使用する方法

### オプション1: BOAT RACE公式APIを使用（推奨）

BOAT RACE公式が提供するAPIがあれば、それを使用するのが最も安全です。

**必要な調整:**
1. API keyの取得
2. `src/scraper/odds_fetcher.py`のURL変更
3. 認証ヘッダーの追加

```python
class OddsFetcher:
    def __init__(self, api_key: str = None):
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({
                'Authorization': f'Bearer {api_key}',
                'User-Agent': 'Mozilla/5.0...'
            })
```

### オプション2: スクレイピングの改善

現在のスクレイピングコードを実際のHTML構造に合わせて調整：

**手順:**
1. ブラウザでBOAT RACE公式サイトのオッズページを開く
2. 開発者ツールでHTML構造を確認
3. `fetch_sanrentan_odds()`のセレクターを調整

```python
# 例：実際のHTML構造に合わせる
odds_tables = soup.find_all('div', class_='odds-table-3tan')
for table in odds_tables:
    odds_rows = table.find_all('tr', class_='odds-row')
    for row in odds_rows:
        combination = row.find('td', class_='combination').get_text()
        odds = row.find('td', class_='odds-value').get_text()
        # ...
```

**注意:**
- アンチスクレイピング対策に注意
- 利用規約を確認
- レート制限を設ける
- ユーザーエージェントを設定

### オプション3: サードパーティAPIを使用

競艇データを提供するサードパーティサービスがあれば使用：

- 安定性が高い
- サポートあり
- 有料の場合が多い

---

## テスト方法

### 現在のモックオッズのテスト

```bash
cd c:\Users\seizo\Desktop\BoatRace
python test_odds_fetcher.py
```

**期待される出力:**
```
============================================================
オッズ取得APIテスト
============================================================
...
[OK] モックオッズ生成は正常に動作しています

組み合わせ | オッズ | 市場確率
----------------------------------------
      1-2-3 |    8.3倍 |   12.0%
      1-2-4 |   10.4倍 |    9.6%
      ...
```

### 実際のAPIが実装された後のテスト

1. `test_odds_fetcher.py`を実行
2. `[OK] オッズ取得成功: XX件`が表示されればOK
3. リアルタイム予想タブで実際のレースを選択
4. `[OK] リアルタイムオッズを取得: XX件`が表示されればOK

---

## 今後の改善案

### 短期（1-2週間）
- [ ] BOAT RACE公式サイトのHTML構造を調査
- [ ] スクレイピングコードを実際の構造に合わせて修正
- [ ] タイムアウト処理の改善
- [ ] リトライ機能の追加

### 中期（3-4週間）
- [ ] オッズ取得結果をキャッシュ（5分間）
- [ ] 複数会場を並列取得
- [ ] エラーログの詳細化

### 長期（5-6週間）
- [ ] 公式APIの調査・申請
- [ ] データベースにオッズ履歴を保存
- [ ] オッズ変動の分析機能

---

**作成日:** 2025-11-03
**ステータス:** モックオッズで動作中（実API未実装）
**次のアクション:** HTML構造の調査とスクレイピングコードの調整
