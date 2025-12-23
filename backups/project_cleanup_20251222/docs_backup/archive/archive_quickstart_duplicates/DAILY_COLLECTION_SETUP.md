# オリジナル展示データ日次収集セットアップガイド

## 作成日
2025年11月13日

---

## 📋 概要

オリジナル展示データは**過去に遡れない**（2日前以前のデータは削除される）ため、日次自動収集が必須です。

このガイドでは、毎日20:00に自動実行されるタスクスケジューラの設定方法を説明します。

---

## 🎯 作成したファイル

### 1. [fetch_original_tenji_daily.py](fetch_original_tenji_daily.py)
**用途**: オリジナル展示データ収集スクリプト（本体）

**機能**:
- 指定日（デフォルトは翌日）のオリジナル展示データを取得
- データベース（race_details テーブル）に自動保存
- 進捗表示とログ出力
- テストモード対応

**使用例**:
```bash
# 翌日のデータを取得（本番実行）
python fetch_original_tenji_daily.py

# テストモード（DB保存なし）
python fetch_original_tenji_daily.py --test --limit 10

# 当日のデータを取得
python fetch_original_tenji_daily.py --today

# 特定日のデータを取得
python fetch_original_tenji_daily.py --date 2025-11-14
```

### 2. [run_daily_tenji_collection.bat](run_daily_tenji_collection.bat)
**用途**: タスクスケジューラから実行されるバッチファイル

**機能**:
- 仮想環境の自動アクティベート
- Pythonスクリプトの実行
- ログファイルへの出力

### 3. [setup_task_scheduler.ps1](setup_task_scheduler.ps1)
**用途**: タスクスケジューラの自動設定スクリプト（PowerShell）

**機能**:
- タスクの自動登録
- 毎日20:00実行に設定
- 既存タスクの上書き

---

## ⚙️ セットアップ手順

### 方法1: PowerShellスクリプトで自動設定（推奨）

#### ステップ1: PowerShellを管理者権限で起動
```powershell
# スタートメニュー → Windows PowerShell → 右クリック → 管理者として実行
```

#### ステップ2: 実行ポリシーを一時的に変更（必要に応じて）
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

#### ステップ3: プロジェクトディレクトリに移動
```powershell
cd C:\Users\seizo\Desktop\BoatRace
```

#### ステップ4: セットアップスクリプトを実行
```powershell
.\setup_task_scheduler.ps1
```

**期待される出力**:
```
タスク 'BoatRace_Daily_Tenji_Collection' を登録します...

タスクスケジューラの設定が完了しました！

設定内容:
  タスク名: BoatRace_Daily_Tenji_Collection
  実行時刻: 毎日 20:00
  スクリプト: C:\Users\seizo\Desktop\BoatRace\run_daily_tenji_collection.bat
```

---

### 方法2: 手動でタスクスケジューラに登録

#### ステップ1: タスクスケジューラを開く
```
スタートメニュー → タスクスケジューラ
または
Win + R → taskschd.msc → Enter
```

#### ステップ2: 新しいタスクを作成
1. 右側の「操作」パネルから「基本タスクの作成」をクリック
2. 名前: `BoatRace_Daily_Tenji_Collection`
3. 説明: `ボートレースオリジナル展示データの日次自動収集`
4. 「次へ」をクリック

#### ステップ3: トリガーを設定
1. 「毎日」を選択
2. 開始時刻: `20:00`
3. 「次へ」をクリック

#### ステップ4: 操作を設定
1. 「プログラムの開始」を選択
2. プログラム/スクリプト: `C:\Users\seizo\Desktop\BoatRace\run_daily_tenji_collection.bat`
3. 開始場所: `C:\Users\seizo\Desktop\BoatRace`
4. 「次へ」をクリック

#### ステップ5: 完了
1. 設定内容を確認
2. 「完了」をクリック

---

## ✅ 動作確認

### 1. 手動実行テスト

#### PowerShellから実行:
```powershell
Start-ScheduledTask -TaskName "BoatRace_Daily_Tenji_Collection"
```

#### タスクスケジューラから実行:
1. タスクスケジューラを開く
2. `BoatRace_Daily_Tenji_Collection` を右クリック
3. 「実行する」をクリック

### 2. ログファイルを確認
```powershell
# ログファイルの表示
Get-Content C:\Users\seizo\Desktop\BoatRace\logs\daily_tenji_collection.log -Tail 50
```

**期待される出力例**:
```
=== オリジナル展示データ収集 ===
対象日: 2025-11-14
モード: 本番（DB保存あり）

  [成功] 多摩川 1R: 6艇
  [成功] 多摩川 2R: 6艇
  ...

=== 収集完了 ===
試行回数: 288
成功レース数: 100
取得艇数: 600
DB保存レース数: 100

[2025/11/13 20:05:32] 収集完了
```

### 3. データベースを確認
```bash
# Pythonで確認
python -c "import sqlite3; conn = sqlite3.connect('data/boatrace.db'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM race_details WHERE chikusen_time IS NOT NULL AND isshu_time IS NOT NULL AND mawariashi_time IS NOT NULL'); print(f'オリジナル展示データ: {cursor.fetchone()[0]}件'); conn.close()"
```

---

## 📊 運用方法

### 日次実行スケジュール

| 時刻 | 処理内容 |
|------|---------|
| 20:00 | タスクスケジューラが自動実行 |
| 20:00-20:10 | 翌日のオリジナル展示データを取得 |
| 20:10 | ログファイルに結果を記録 |

### 取得可能なデータ

- **対象**: 翌日のレースデータ
- **データソース**: boaters-boatrace.com
- **取得内容**: 直線タイム、一周タイム、回り足タイム
- **取得率**: 約34.7%（全24会場中、約9会場が公開）

### 月次確認タスク

毎月1日に以下を確認:
1. ログファイルでエラーがないか確認
2. データベースのオリジナル展示データ件数を確認
3. タスクスケジューラでタスクが正常に実行されているか確認

---

## 🔧 トラブルシューティング

### 問題1: タスクが実行されない

**原因と対処**:
1. **PCが起動していない**: 20:00にPCが起動している必要があります
2. **タスク設定の確認**: タスクスケジューラで設定を確認
3. **実行権限**: バッチファイルの実行権限を確認

### 問題2: データが取得できない

**原因と対処**:
1. **レースが開催されていない**: 翌日にレースがない場合は取得できません
2. **データが公開されていない**: 全会場が公開しているわけではない（約9/24会場）
3. **ネットワークエラー**: インターネット接続を確認

### 問題3: ChromeDriver エラー

**症状**: `OSError: [WinError 193]` または ChromeDriver関連のエラー

**対処**:
```bash
# webdriver-managerの再インストール
pip uninstall webdriver-manager
pip install webdriver-manager

# Chromeブラウザの更新
# Google Chromeを最新版に更新してください
```

### 問題4: ログファイルが作成されない

**対処**:
```bash
# logsフォルダを手動作成
mkdir logs
```

---

## 📁 ファイル構成

```
BoatRace/
├── fetch_original_tenji_daily.py           # 収集スクリプト本体
├── run_daily_tenji_collection.bat          # バッチファイル
├── setup_task_scheduler.ps1                # タスクスケジューラ設定スクリプト
├── DAILY_COLLECTION_SETUP.md               # 本ドキュメント
├── logs/
│   └── daily_tenji_collection.log          # 実行ログ
├── data/
│   └── boatrace.db                         # データベース
└── src/
    └── scraper/
        └── original_tenji_browser.py       # オリジナル展示スクレイパー
```

---

## 📈 期待される効果

### データ蓄積シミュレーション

| 期間 | 蓄積レース数（予測） | カバー率 |
|------|-------------------|----------|
| 1週間後 | 約70レース | 新規データの100% |
| 1ヶ月後 | 約300レース | 新規データの100% |
| 1年後 | 約3,650レース | 新規データの100% |

**前提**: 全24会場中9会場が公開、1日平均10レース

### 機械学習への貢献

**オリジナル展示データの重要性**:
- **直線タイム**: スタート後の加速性能
- **一周タイム**: コース適性・総合スピード
- **回り足タイム**: ターン性能

これらは重要な予測特徴量です。日次収集により、今後のデータは100%カバー可能になります。

---

## 🚨 重要な注意事項

### データの特性
1. **過去データは取得不可**: 2日前以前のデータは削除される
2. **日次収集が必須**: データが毎日削除されるため、自動化が必要
3. **全会場が公開しているわけではない**: 約9/24会場のみ公開

### 運用上の注意
1. **PCを20:00に起動**: タスク実行時にPCが起動している必要があります
2. **定期的なログ確認**: 月1回はログを確認してください
3. **ChromeDriverの更新**: Chrome更新時にエラーが出る場合があります

---

## 📞 サポート情報

### 関連ドキュメント
- [HANDOVER_REPORT_20251111.md](HANDOVER_REPORT_20251111.md) - 引継ぎ資料
- [ORIGINAL_TENJI_SCRAPER_FIX_20251111.md](ORIGINAL_TENJI_SCRAPER_FIX_20251111.md) - スクレイパー修正詳細
- [ORIGINAL_TENJI_STATUS.md](ORIGINAL_TENJI_STATUS.md) - 運用ステータス

### テストURL
`https://boaters-boatrace.com/race/tamagawa/2025-11-10/1R/last-minute?last-minute-content=original-tenji`

---

**作成日**: 2025年11月13日
**状態**: セットアップ準備完了
**次のアクション**: PowerShellスクリプトを実行してタスクスケジューラを設定
