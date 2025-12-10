# クイックスタートガイド - 決まり手ベース予測システム

## 5分で始める

### 1. システムの動作確認

```bash
# テストスクリプトを実行
python test_kimarite_prediction.py
```

**期待される出力**:
```
=== 推奨買い目 ===
1. 1-2-3 - 26.3% (Very High)
2. 1-2-4 - 19.7% (High)
3. 1-3-2 - 16.4% (High)
...

本命: 1号艇
的中率カバー: 96.5%
```

✅ この出力が表示されれば正常動作

---

### 2. UIで使用する

```bash
# Streamlitアプリを起動
streamlit run test_unified_ui.py
```

**操作手順**:
1. ブラウザで `http://localhost:8501` を開く
2. 「🔮 レース予想一覧」タブを選択
3. 「🎯 的中率重視」タブ内で日付を選択
4. 自動的におすすめレースが表示される

**表示内容**:
- 本命買い目（例: 1-2-3）
- 他の買い目（例: 他5点）
- 的中率カバー（例: 96.5%）

---

### 3. プログラムから使用

```python
from src.prediction.integrated_kimarite_predictor import IntegratedKimaritePredictor

# 予測器を初期化
predictor = IntegratedKimaritePredictor()

# レースを予測（race_idで指定）
result = predictor.predict_race(race_id=445, min_bets=3, max_bets=6)

# 買い目を取得
for bet in result['bets']:
    print(f"{bet.rank}. {bet.combination[0]}-{bet.combination[1]}-{bet.combination[2]} "
          f"({bet.probability*100:.1f}%) - {bet.confidence}")

# または、レースキーで指定
result = predictor.predict_race_by_key(
    race_date='2024-10-01',
    venue_code='20',
    race_number=1
)
```

---

## よくある質問

### Q1: 買い目が3つしか出ない
**A**: 確率が低いため、上位3つのみ選定されています。
- `max_bets=10` に増やす
- または `min_confidence` を下げる

### Q2: "Race not found" エラー
**A**: 指定したレースがDBに存在しません。
- race_date, venue_code, race_number を確認
- データ準備タブでデータを取得

### Q3: 予測が遅い
**A**: 初回は決まり手履歴の取得に時間がかかります。
- 2回目以降はキャッシュにより高速化
- 10-15秒程度かかる場合あり

### Q4: 的中率が低い
**A**: レース展開が複雑な場合は的中率が下がります。
- `min_confidence` を上げて、高信頼度レースのみ選択
- 買い目数を増やす（`max_bets=10`）

---

## パラメータ早見表

### 買い目数の設定

| 設定 | min_bets | max_bets | 期待的中率 | 用途 |
|------|----------|----------|-----------|------|
| 保守的 | 3 | 3 | 30-40% | 本命1点+ヘッジ2点 |
| 標準 | 3 | 6 | 50-70% | バランス型 |
| 広範囲 | 3 | 10 | 70-90% | 的中率重視 |

### 信頼度フィルタ

| min_confidence | レース数 | 的中率 | 説明 |
|----------------|----------|--------|------|
| 70% | 少ない | 高い | 超本命レースのみ |
| 60% | 普通 | 高い | 信頼度高いレース |
| 50% | 多い | 中 | バランス型（推奨） |
| 40% | 非常に多い | 低 | 幅広く網羅 |

---

## トラブル時の対処

### エラーが出た場合

1. **ログを確認**
   ```bash
   # ログレベルをINFOに設定してテスト
   python test_kimarite_prediction.py
   ```

2. **データベースを確認**
   ```python
   import sqlite3
   conn = sqlite3.connect('data/boatrace.db')
   cursor = conn.cursor()

   # レース数を確認
   cursor.execute("SELECT COUNT(*) FROM races")
   print(cursor.fetchone())
   ```

3. **モジュールのインポート確認**
   ```python
   # Pythonインタプリタで確認
   from src.prediction.integrated_kimarite_predictor import IntegratedKimaritePredictor
   # エラーが出なければOK
   ```

---

## 次のステップ

### さらに詳しく知りたい
→ [kimarite_prediction_system.md](kimarite_prediction_system.md) を参照

### カスタマイズしたい
→ [kimarite_constants.py](../src/prediction/kimarite_constants.py) のパラメータを調整

### バックテストしたい
→ 過去データで的中率・回収率を検証（今後実装予定）

---

**困ったときは**: [kimarite_prediction_system.md](kimarite_prediction_system.md) の「トラブルシューティング」セクションを参照
