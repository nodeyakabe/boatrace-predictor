# 機能比較レポート: 復元版 vs 破損版

**作成日**: 2025年11月13日

---

## タブ構成の比較

### 復元版 (10月31日版) - 11タブ
1. 🏠 ホーム
2. 🔮 リアルタイム予想
3. 📥 **過去データ取得**
4. 🏟️ 場攻略
5. 👤 選手
6. ⚙️ **システム設定**
7. 📝 **レース結果**
8. 📋 **データ充足率**
9. 🧮 **特徴量**
10. 📤 **MLデータ出力**
11. 🤖 モデル学習

### 破損版 (11月13日版) - 8タブ
1. 🏠 ホーム
2. 🔮 リアルタイム予想
3. 💰 **購入履歴**
4. 🏟️ 場攻略
5. 👤 選手
6. 🤖 モデル学習
7. 🧪 **バックテスト**
8. ⚙️ **設定・データ管理**

---

## 主要な違い

### ✅ 復元版にあって破損版にない機能

1. **📥 過去データ取得タブ**
   - 過去のレースデータを取得する機能
   - 日付範囲指定
   - 会場指定
   - データ種別選択(基本情報/展示タイム/潮汐データ)

2. **📝 レース結果タブ**
   - レース結果の確認・表示

3. **📋 データ充足率タブ**
   - データの充足状況を確認

4. **🧮 特徴量タブ**
   - 特徴量エンジニアリングの設定・確認

5. **📤 MLデータ出力タブ**
   - 機械学習用データの出力

6. **⚙️ システム設定タブ (独立)**
   - システム全体の設定

### ✅ 破損版にあって復元版にない機能

1. **💰 購入履歴タブ**
   - 賭け履歴の管理
   - コンポーネント: `ui/components/bet_history.py`
   - 関数: `render_bet_history_page()`

2. **🧪 バックテストタブ**
   - モデルのバックテスト機能
   - コンポーネント: `ui/components/backtest.py`

3. **選手タブの表示モード切り替え**
   - 「選手分析(新)」と「選手情報」の切り替え
   - コンポーネント: `ui/components/racer_analysis.py`
   - 関数: `render_racer_analysis_page()`

4. **場攻略タブの表示モード切り替え**
   - 「データ分析(新)」「シンプル分析」「詳細分析」の切り替え
   - コンポーネント:
     - `ui/components/venue_analysis.py`
     - `ui/components/venue_strategy.py`

5. **天候別成績セクション (選手タブ内)**
   - SQLクエリで天候データを結合して表示

6. **賭け推奨機能**
   - コンポーネント: `ui/components/betting_recommendation.py`
   - 関数: `render_betting_recommendations()`

---

## 追加インポート (破損版のみ)

破損版で追加されていた主なインポート:

```python
from ui.components.bet_history import render_bet_history_page
from ui.components.betting_recommendation import render_betting_recommendations
from ui.components.racer_analysis import render_racer_analysis_page
from ui.components.backtest import render_backtest_page
from src.prediction.stage2_predictor import Stage2Predictor
from src.scraper.odds_fetcher import OddsFetcher
from src.ml.race_selector import RaceSelector
```

---

## 機能の優先度評価

### 🔴 優先度: 高 (復元推奨)

1. **💰 購入履歴タブ**
   - ユーザーの賭け履歴管理は重要
   - ファイル存在確認が必要: `ui/components/bet_history.py`

2. **🧪 バックテストタブ**
   - モデル検証に必須
   - ファイル存在確認が必要: `ui/components/backtest.py`

### 🟡 優先度: 中 (検討推奨)

3. **選手タブの表示モード**
   - ただし、ユーザー要望で「表示モード削除」を希望
   - 新しい分析機能のみを統合すれば良い

4. **場攻略タブの表示モード**
   - ユーザー要望で「表示モード削除」を希望
   - 不要の可能性が高い

5. **賭け推奨機能**
   - 便利だが必須ではない

### 🟢 優先度: 低 (復元不要)

6. **天候別成績セクション**
   - 新機能だがエラーが出ていた
   - 後で正しく実装すれば良い

---

## 推奨アクション

### ステップ1: 必須コンポーネントの確認

以下のファイルが存在するか確認:
- `ui/components/bet_history.py`
- `ui/components/backtest.py`
- `ui/components/betting_recommendation.py`
- `ui/components/racer_analysis.py`

### ステップ2: 優先度の高い機能から復元

1. **購入履歴タブ** を復元
2. **バックテストタブ** を復元

### ステップ3: ユーザー確認

- 表示モード機能は復元するか?
  - ユーザーは「削除して全て表示」を希望していた
  - 新機能の内容のみを現在のタブに統合する方が良いかもしれない

---

## まとめ

**復元版の長所:**
- ✅ データ管理機能が充実(過去データ取得、データ充足率など)
- ✅ 特徴量エンジニアリング機能あり
- ✅ 構文エラーなし、安定動作

**破損版の長所:**
- ✅ 購入履歴管理
- ✅ バックテスト機能
- ✅ より洗練されたUI(表示モード切り替え)
- ❌ ただし構文エラーで動作不可

**結論:**
- 現在の復元版をベースに、購入履歴とバックテスト機能を追加するのが最適
- 表示モード機能はユーザー要望に反するため、復元不要
