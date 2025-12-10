# 作業サマリー 2025-11-17

## 本日の成果

### 1. バックテストロジック修正 ✅

**問題**: 期待値が常に約0.75になり、賭けが0件
**原因**: 推定オッズ = (1/確率) × 0.75 のため、期待値 = 確率 × 推定オッズ ≈ 0.75

**修正内容** (`run_backtest.py`):
- 期待値閾値による賭け判定を確率閾値に変更
- 実際のオッズデータ（payoutsテーブル）を使用

**結果**:
- 戦略1: 92レース賭け、6勝、ROI 194.6%、利益 +8,699円
- 戦略2: 53レース賭け、4勝、ROI 155.9%、利益 +2,960円

### 2. 3連単オッズスクレイピング ✅

**課題**: JavaScript動的レンダリングのため、HTTPリクエストでは取得不可

**試行錯誤**:
1. HTTPスクレイパー → 失敗（3連単オッズなし）
2. Selenium → クラッシュ多発（Windowsヘッドレス問題）
3. **Playwright → 成功！**

**最終実装** (`src/scraper/playwright_odds_scraper.py`):
- 全120通りの3連単オッズを正確に取得
- HTMLテーブル構造を完全解析（18セル行 + 12セル行パターン）

### 3. リアルタイム予測システム統合 ✅

**新規作成ファイル**:

1. `src/prediction/realtime_odds_predictor.py`
   - Playwrightスクレイパー統合
   - 条件付き確率モデルによる120通り確率計算
   - 期待値・ケリー基準計算
   - 推奨ベット自動選定

2. `predict_today.py`
   - 本日のレース予測スクリプト
   - DBから出走表を読み込み
   - リアルタイムオッズと統合

**テスト結果**（戸田競艇場 1R）:
```
期待値Top3:
  6-4-1: 確率1.00% × 1443倍 = 期待値14.40
  6-4-3: 確率1.17% × 1211倍 = 期待値14.12
  6-1-4: 確率0.95% × 1090倍 = 期待値10.32
```

### 4. 依存関係更新 ✅

`requirements.txt`に追加:
```
playwright==1.49.0
```

## ファイル変更一覧

### 新規作成
- `src/scraper/playwright_odds_scraper.py` - Playwright 3連単スクレイパー
- `src/scraper/selenium_odds_scraper.py` - Selenium版（参考用）
- `src/prediction/realtime_odds_predictor.py` - リアルタイム統合予測
- `predict_today.py` - 本日予測スクリプト
- `docs/odds_scraping_guide.md` - オッズ取得技術ガイド

### 修正
- `run_backtest.py` - バックテストロジック修正
- `src/scraper/odds_scraper.py` - 単勝オッズ取得改善
- `src/ml/conditional_rank_model.py` - ベクトル化予測（高速化）
- `requirements.txt` - playwright追加

## 技術的知見

### HTMLテーブル構造
```
3連単オッズテーブル:
- 20行以上のテーブルを検索
- 18セル行: 新しい2着開始 [2着, 3着, オッズ] × 6
- 12セル行: 同じ2着の継続 [3着, オッズ] × 6
- 4行で1つの2着が完了
```

### 期待値計算
```python
期待値 = 予測確率 × 実際のオッズ
ケリー基準 = (確率×オッズ - (1-確率)) / オッズ
```

## 残課題・改善案

1. **モデル精度向上**
   - 6号艇を過大評価している可能性
   - より多くの特徴量（展示タイム、コース別成績など）

2. **オッズ取得の安定化**
   - ネットワークエラー時の自動リトライ
   - キャッシュ機能

3. **UI/UX**
   - Streamlitダッシュボードへの統合
   - リアルタイムオッズ表示

4. **バックテスト拡張**
   - 実際の過去オッズデータ（第三者提供がない）
   - より長期間の検証

---

## 明日の作業開始手順

### 1. 環境確認

```bash
cd C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032
python --version  # Python 3.x確認

# Playwrightインストール確認
pip show playwright
playwright install chromium  # 必要に応じて
```

### 2. 予測システム動作確認

```bash
# リアルタイム予測テスト
python src/prediction/realtime_odds_predictor.py

# 期待される出力:
# - オッズ取得: 120通り
# - 確率計算: 120通り
# - 推奨ベット: 数通り
```

### 3. 本日のレース予測

```bash
python predict_today.py
```

### 4. 主要ファイル確認

| ファイル | 用途 |
|---------|------|
| `src/scraper/playwright_odds_scraper.py` | 3連単オッズ取得 |
| `src/prediction/realtime_odds_predictor.py` | 統合予測システム |
| `predict_today.py` | 本日予測実行 |
| `run_backtest.py` | バックテスト実行 |
| `models/conditional_rank_v1_*.pkl` | 学習済みモデル |

### 5. 次の開発候補

1. **モデル精度検証**
   - 実際のレースで予測精度を検証
   - 期待値が高い組み合わせの的中率を追跡

2. **Streamlit UI統合**
   - `ui/`ディレクトリのダッシュボードにリアルタイムオッズ機能を追加

3. **自動予測システム**
   - 締め切り前に自動的にオッズを取得して予測
   - 通知機能

4. **収支管理**
   - 実際の賭け結果を記録
   - 長期的なROI追跡

### 6. 重要な注意点

- **Playwright待機時間**: 5秒必要（JS実行待ち）
- **リクエスト間隔**: 最低1秒空ける
- **モデルの制限**: 現在のモデルは6号艇を過大評価している可能性あり
- **期待値14倍**: 高すぎる可能性があるので、実際の結果で検証が必要

---

## クイックリファレンス

### オッズ取得

```python
from src.scraper.playwright_odds_scraper import PlaywrightOddsScraper

scraper = PlaywrightOddsScraper(headless=True)
odds = scraper.get_trifecta_odds('02', '20251117', 1)
# {'1-2-3': 10.1, '1-2-4': 18.1, ...} 120通り
```

### 期待値計算

```python
from src.prediction.realtime_odds_predictor import RealtimeOddsPredictor

predictor = RealtimeOddsPredictor()
result = predictor.analyze_race('02', '20251117', 1, race_features)

# result['recommended_bets'] に期待値1.0以上の組み合わせ
```

### 競艇場コード

```
01: 桐生    02: 戸田    03: 江戸川  04: 平和島
05: 多摩川  06: 浜名湖  07: 蒲郡    08: 常滑
...
```

---

**作成日**: 2025-11-17
**次回更新予定**: 明日の作業終了後
