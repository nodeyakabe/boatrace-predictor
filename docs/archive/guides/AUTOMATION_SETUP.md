# ボートレース予想自動化システム セットアップガイド

## 概要

このシステムは以下の機能を自動化します：

1. **毎朝7:00** - 本日のレース予想を自動生成
2. **5分ごと** - 購入対象レースを監視
   - 締切20分前: 直前情報を自動取得
   - 締切10分前: Discordに通知（買い目・オッズ・推奨購入額付き）

## セットアップ（所要時間: 10分）

### 1. 必要なパッケージをインストール

```bash
pip install schedule requests python-dotenv
```

### 2. Discord Webhook URLを取得

1. [Discord Webhook設定ガイド](DISCORD_WEBHOOK_SETUP.md)の手順に従ってWebhook URLを取得
2. Webhook URL（`https://discord.com/api/webhooks/...`）をコピー

### 3. 環境変数を設定

`.env` ファイルに Discord Webhook URLを追加:

```bash
# .env ファイルを開く
notepad .env

# 以下の行を追加（your_webhook_url_here を実際のURLに置き換え）
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_url_here
```

保存して閉じます。

### 4. 通知テスト

```bash
python scripts/automation/test_notification.py
```

以下の4つの通知がDiscordに届けば成功です：
- ✓ 基本通知
- ✓ 朝の予想生成完了通知
- ✓ レース締切通知（サンプル）
- ✓ エラー通知（サンプル）

## 使い方

### 自動化システムを起動

```bash
python scripts/automation/daily_scheduler.py
```

起動すると：
- システム起動通知がDiscordに届く
- 毎朝7:00に予想生成が自動実行
- 5分ごとにレース監視が実行
- 購入対象レースの締切10分前に通知

### 停止方法

`Ctrl+C` でシステムを停止できます。
停止通知がDiscordに届きます。

## 通知内容の詳細

### 朝の予想生成完了通知（7:00頃）

```
☀️ 本日の予想生成完了

📅 日付: 2026-01-13
🏁 総レース数: 144レース
🎯 購入対象: 8レース

システムは自動監視を開始しました。
締切10分前に個別通知を送信します。
```

### レース締切10分前通知

```
🚤 レース締切10分前通知

📍 会場: 桐生 第12R
⏰ 締切: 15:30

【予想】
🎯 買い目: 1-2-3
📊 信頼度: 65.0%
🏷️ パターン: パターンH

【オッズ情報】
💰 3連単オッズ: 15.2倍
📈 期待収益率: 988.0%

【推奨購入額】
💵 2,000円
   (基本1000円 × 信頼度・期待値調整)
```

## 各モジュールの個別実行（デバッグ用）

### 朝の予想生成のみ実行

```bash
python scripts/automation/generate_daily_predictions.py
```

### レース監視のみ実行（1回）

```bash
python scripts/automation/monitor_race_timing.py
```

## トラブルシューティング

### 通知が届かない

**原因1: Webhook URLが設定されていない**
```bash
# .env ファイルを確認
notepad .env

# DISCORD_WEBHOOK_URL が設定されているか確認
```

**原因2: Webhook URLが間違っている**
- 余分なスペースがないか確認
- URLをもう一度コピー＆ペーストしてみる

**原因3: Webhookが削除された**
- Discord設定画面で「連携サービス」→「ウェブフック」を確認
- 存在しない場合は再作成

### スケジューラが起動しない

**パッケージ不足**
```bash
pip install schedule requests python-dotenv
```

**Pythonバージョン**
- Python 3.7以上が必要

### 予想生成が失敗する

**データベースが見つからない**
```bash
# データベースパスを確認
dir data\boatrace.db
```

**レースデータが存在しない**
- 先にデータ収集を実行:
```bash
python scripts/data_collection/fetch_today_data.py
```

## 常時稼働の設定

### Windows: タスクスケジューラで自動起動

1. タスクスケジューラを開く（`taskschd.msc`）
2. 「基本タスクの作成」をクリック
3. 設定：
   - 名前: `ボートレース自動化`
   - トリガー: `コンピューター起動時`
   - 操作: `プログラムの開始`
   - プログラム: `python`
   - 引数: `C:\path\to\scripts\automation\daily_scheduler.py`
   - 開始: `C:\path\to\project\`

4. 「条件」タブ:
   - 「コンピューターをAC電源で使用している場合のみタスクを開始する」をOFF

5. 「設定」タブ:
   - 「タスクが失敗した場合、次の間隔で再起動する」をON（間隔: 1分、再試行: 3回）

### PC起動時に自動起動（簡易版）

`startup_automation.bat` を作成:

```batch
@echo off
cd /d "C:\path\to\project"
python scripts\automation\daily_scheduler.py
```

スタートアップフォルダに配置:
- `Win + R` → `shell:startup` → バッチファイルをコピー

## クラウド移行（将来的に）

現在はローカルPC常駐ですが、以下のクラウドサービスに移行可能です：

### Google Cloud Run（推奨）
- コスト: 月額 $0～$5
- サーバーレスで管理不要
- Cloud Schedulerで定期実行

### AWS Lambda
- コスト: 月額 $0～$3
- Lambda + EventBridgeで定期実行

移行手順は別途ドキュメント作成予定。

## よくある質問

### Q1: PCをシャットダウンしても動きますか？

いいえ。現在の実装ではPCが起動している必要があります。
常時稼働させたい場合：
- タスクスケジューラで自動起動設定
- クラウドに移行（後日対応）
- Raspberry Pi等で24時間稼働

### Q2: 通知のタイミングを変更できますか？

はい。`scripts/automation/daily_scheduler.py` を編集:

```python
# 朝の予想生成時刻を変更（例: 6:30に変更）
schedule.every().day.at("06:30").do(morning_prediction_job)

# レース監視間隔を変更（例: 3分ごとに変更）
schedule.every(3).minutes.do(race_monitoring_job)
```

### Q3: 通知内容をカスタマイズできますか？

はい。`scripts/automation/notify.py` の `format_race_notification()` 関数を編集してください。

### Q4: 複数のDiscordチャンネルに通知できますか？

はい。チャンネルごとにWebhook URLを取得し、`notify.py` を修正して複数のURLに送信できます。

### Q5: エラー時の通知を無効化できますか？

はい。各スクリプトで `send_error_notification()` の呼び出しをコメントアウトしてください。

## サポート

問題が発生した場合：
1. [DISCORD_WEBHOOK_SETUP.md](DISCORD_WEBHOOK_SETUP.md) を確認
2. テストスクリプトを実行: `python scripts/automation/test_notification.py`
3. ログを確認: システムはコンソールにログを出力します
