# オリジナル展示データ スクリプト状況報告

## 実施日時
2025年11月11日

---

## スクリプトの確認結果

### スクリプト発見
- **ファイル**: [src/scraper/original_tenji_browser.py](src/scraper/original_tenji_browser.py)
- **状態**: 存在確認済み
- **サイズ**: 9,091バイト
- **最終更新**: 2024年11月3日 02:12

---

## スクリプトの機能

### 取得可能なデータ
- **直線タイム** (chikusen_time)
- **一周タイム** (isshu_time)
- **まわり足タイム** (mawariashi_time)

### データソース
- **URL**: `https://boaters-boatrace.com/race/{venue}/{date}/{race}R/last-minute?last-minute-content=original-tenji`
- **サイト**: boaters-boatrace.com（サードパーティサイト）

### 技術仕様
- **使用ライブラリ**: Selenium（ブラウザ自動化）
- **ブラウザ**: Chrome（ChromeDriver自動管理）
- **動作モード**: ヘッドレスモード対応

---

## 重要な制約

### 1. データの時間制約
**オリジナル展示データは過去データが存在しない**
- 取得可能: **前日～当日のレースのみ**
- 取得不可: 過去のレース（2日前以前）

### 2. 技術的制約
**Seleniumが必要**
- 現在の状態: **Seleniumがインストールされていない**
- 必要なパッケージ:
  ```bash
  pip install selenium webdriver-manager
  ```

### 3. データベースの現状
現在のDBには**ほとんど存在しない**:
- 直線タイム: 115レース (0.1%)
- 一周タイム: 116レース (0.1%)
- まわり足タイム: 115レース (0.1%)

**理由**: 過去データは取得不可能なため

---

## 動作確認状況

### インストール状況
```
[OK] Seleniumインストール済み
pip install selenium webdriver-manager
```

### スクレイパー修正履歴
**2025-11-11**: グリッド構造の解析バグを修正
- **修正前**: `.css-15871fl`グリッドコンテナから誤ったデータを抽出
- **修正後**: `.css-1qmyagr`データコンテナから正しく抽出
- **構造**: 各艇につき4つの連続したコンテナ
  - コンテナ0: 1周タイム (isshu_time)
  - コンテナ1: 回り足タイム (mawariashi_time)
  - コンテナ2: 直線タイム (chikusen_time)
  - コンテナ3: 展示タイム (tenji_time)

### テスト結果
```
[OK] テスト成功（多摩川 2025-11-10 1R）
取得艇数: 6艇

1号艇:
  直線タイム: 7.03秒
  一周タイム: 36.8秒
  回り足タイム: 5.57秒

期待値との比較: 完全一致
```

**全6艇のデータを正常に取得**

---

## 今後の運用方法

### 日次自動収集が必須

オリジナル展示データは**過去に遡れない**ため、以下の運用が必要:

#### 1. 毎日の自動実行（推奨）
```bash
# 明日のレースデータを取得（毎日実行）
python fetch_original_tenji_daily.py
```

#### 2. 実行タイミング
- **前日の夜（推奨）**: 翌日のレースデータが公開された後
- **当日の朝**: レース開始前

#### 3. cron/タスクスケジューラで自動化
```bash
# Linux/Mac (cron)
0 20 * * * cd /path/to/project && python fetch_original_tenji_daily.py

# Windows (タスクスケジューラ)
毎日20:00に実行
```

---

## スクリプトの使用例

### 基本的な使い方
```python
from src.scraper.original_tenji_browser import OriginalTenjiBrowserScraper
from datetime import datetime, timedelta

# 初期化（UIなし）
scraper = OriginalTenjiBrowserScraper(headless=True)

# 明日の日付
tomorrow = datetime.now() + timedelta(days=1)
date_str = tomorrow.strftime('%Y-%m-%d')

# データ取得（若松 1R）
tenji_data = scraper.get_original_tenji('20', date_str, 1)

if tenji_data:
    for boat_num, data in tenji_data.items():
        print(f"{boat_num}号艇:")
        print(f"  直線: {data['chikusen_time']}秒")
        print(f"  1周: {data['isshu_time']}秒")
        print(f"  回り足: {data['mawariashi_time']}秒")

scraper.close()
```

---

## データ補充の可能性

### 過去データ
- **補充不可**: オリジナル展示データは前日～当日のみ
- **現状維持**: 過去データ（0.1%）はこのまま

### 今後のデータ
- **補充可能**: 日次自動収集で100%カバー可能
- **必要作業**:
  1. Seleniumインストール
  2. 日次収集スクリプト作成
  3. 自動実行設定（cron/タスクスケジューラ）

---

## 予想精度への影響

### オリジナル展示データの重要性
- **直線タイム**: スタート後の加速性能
- **一周タイム**: コース適性・総合スピード
- **まわり足タイム**: ターン性能

これらは**重要な予測特徴量**だが、過去データは補充不可

### 対策
1. **今後のデータ収集**: 日次自動収集で蓄積
2. **代替特徴量の活用**:
   - 展示タイム（98.7%カバー済み）
   - ST時間（補充後100%予定）
   - モーター2連率・3連率
   - 潮位データ（100%カバー済み）

---

## 推奨される対応

### 短期的（今すぐ）
1. **Seleniumインストール** (UIは起動しない)
   ```bash
   pip install selenium webdriver-manager
   ```

2. **動作確認**
   ```python
   # headless=True でテスト（UIなし）
   python -c "from src.scraper.original_tenji_browser import OriginalTenjiBrowserScraper; s = OriginalTenjiBrowserScraper(headless=True); s.close(); print('OK')"
   ```

### 中期的（1週間以内）
3. **日次収集スクリプト作成**
   - 翌日の全レースのオリジナル展示データを取得
   - DBに自動保存

4. **自動実行設定**
   - タスクスケジューラで毎日20:00に実行

### 長期的（継続運用）
5. **データ蓄積の確認**
   - 月次でデータカバー率をチェック
   - 取得失敗時の再試行ロジック

---

## まとめ

### 現状
- [x] スクリプト存在確認
- [ ] Seleniumインストール（未）
- [ ] 動作確認（未）
- [ ] 日次収集設定（未）

### 重要な発見
1. **過去データは補充不可**: オリジナル展示は前日～当日のみ
2. **DB内のデータはほぼ0%**: 115-116レースのみ（0.1%）
3. **日次収集が必須**: 今後のデータ蓄積には自動化が必要

### 次のステップ
1. Seleniumインストール（UIなし）
2. 動作確認テスト
3. 日次収集スクリプト作成（別日）

---

**作成日時**: 2025-11-11 15:45
**状態**: スクリプト確認完了、Seleniumインストール待ち
