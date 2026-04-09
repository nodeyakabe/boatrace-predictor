# 別PC セットアップガイド

## 概要

このプロジェクトはOneDriveでDBを同期し、GitHubでコードを管理しています。
別PCでも同じ環境を構築するための手順を説明します。

---

## 前提条件

- ✅ Windows PC
- ✅ 同じMicrosoftアカウントでOneDriveにサインイン済み
- ✅ Git がインストール済み
- ✅ Python 3.9以上がインストール済み

---

## セットアップ手順

### ステップ1: OneDriveの同期を確認

1. **タスクバーのOneDriveアイコン**をクリック
2. `BoatRace/data/boatrace.db` が同期されていることを確認
3. 同期が完了するまで待つ（タスクバーに「✓」マークが表示される）

**確認方法**:
```cmd
dir C:\Users\[ユーザー名]\OneDrive\BoatRace\data
```

`boatrace.db` (約1.9GB) が存在すればOK

---

### ステップ2: GitHubからプロジェクトをクローン

```cmd
cd C:\Users\[ユーザー名]\Desktop\BR
git clone https://github.com/nodeyakabe/boatrace-predictor.git
cd boatrace-predictor
```

---

### ステップ3: シンボリックリンクを作成

**管理者権限でコマンドプロンプトを開き**、以下を実行：

```cmd
cd C:\Users\[ユーザー名]\Desktop\BR\boatrace-predictor\data
mklink boatrace.db C:\Users\[ユーザー名]\OneDrive\BoatRace\data\boatrace.db
```

**成功メッセージ**:
```
boatrace.db <<===>> C:\Users\[ユーザー名]\OneDrive\BoatRace\data\boatrace.db のシンボリック リンクが作成されました
```

**確認**:
```bash
ls -lh data/boatrace.db
```

シンボリックリンクが表示されればOK

---

### ステップ4: Python環境のセットアップ

```cmd
cd C:\Users\[ユーザー名]\Desktop\BR\boatrace-predictor
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

### ステップ5: 動作確認

```bash
# DBにアクセスできるか確認
python -c "import sqlite3; conn = sqlite3.connect('data/boatrace.db'); print('DB接続成功:', conn.execute('SELECT COUNT(*) FROM races').fetchone()[0], '件のレースデータ'); conn.close()"
```

---

## 日常の作業フロー

### PC-A（メインPC）での作業

1. コード変更
2. コミット & プッシュ
   ```bash
   git add .
   git commit -m "変更内容"
   git push origin main
   ```
3. DBは自動的にOneDriveで同期される

### PC-B（サブPC）での作業

1. 最新コードを取得
   ```bash
   git pull origin main
   ```
2. DBは自動的にOneDriveから同期される（何もしなくてOK）

---

## トラブルシューティング

### Q1: シンボリックリンク作成で「アクセスが拒否されました」

**解決策**: コマンドプロンプトを**管理者権限**で起動してください

1. スタートメニューで「cmd」を検索
2. 右クリック → 「管理者として実行」

---

### Q2: OneDriveの同期が遅い

**解決策**:

1. タスクバーのOneDriveアイコン → 設定
2. 「ネットワーク」タブ
3. 「アップロード速度」を「制限しない」に変更

---

### Q3: DBファイルが見つからない

**確認ポイント**:

1. OneDriveの同期状態を確認
   ```cmd
   dir C:\Users\[ユーザー名]\OneDrive\BoatRace\data
   ```

2. シンボリックリンクが正しいか確認
   ```bash
   ls -lh data/boatrace.db
   ```

3. リンク先のパスが正しいか確認
   - ユーザー名が正しいか
   - OneDriveフォルダのパスが正しいか

---

### Q4: Git LFSのエラーが出る

**解決策**: Git LFSは使用していないので無効化してください

```bash
git lfs uninstall
```

---

## ファイル構成の理解

```
PC-A (メインPC)
├─ プロジェクトフォルダ/
│  ├─ src/
│  ├─ data/
│  │  └─ boatrace.db ← シンボリックリンク
│  └─ ...
└─ OneDrive/
   └─ BoatRace/
      └─ data/
         └─ boatrace.db ← 実体（クラウド同期）

PC-B (サブPC)
├─ プロジェクトフォルダ/
│  ├─ src/
│  ├─ data/
│  │  └─ boatrace.db ← シンボリックリンク
│  └─ ...
└─ OneDrive/
   └─ BoatRace/
      └─ data/
         └─ boatrace.db ← 実体（クラウド同期）
```

**重要**:
- プロジェクトフォルダの `data/boatrace.db` はシンボリックリンク
- 実際のDBファイルは `OneDrive/BoatRace/data/boatrace.db`
- 両PCのOneDriveが同じファイルを参照するため、自動同期される

---

## バックアップについて

DBは以下の3箇所に存在します：

1. **OneDrive クラウド**: 自動バックアップ
2. **PC-A のOneDriveフォルダ**: ローカルコピー
3. **PC-B のOneDriveフォルダ**: ローカルコピー

さらに安全性を高めたい場合：
- 定期的に外付けHDD/SSDにコピー
- OneDriveのバージョン履歴機能を活用（30日間保持）

---

## 注意事項

### 同時編集の防止

両PCで同時にDBを更新すると、OneDriveが競合を検出します。

**推奨運用**:
- メインPC (PC-A) でDB更新作業を実施
- サブPC (PC-B) は読み取り専用として使用
- DB更新作業は一度に1台のPCのみで実行

### OneDrive容量

- 無料プラン: 5GB
- 現在のDB: 1.9GB
- 残り容量: 約3GB

容量が不足する場合：
- Microsoft 365プラン (1TB) へアップグレード
- または、古いバックアップファイルを削除

---

## よくある質問

### Q: GitLabはどうなった？

**A**: 容量不足のため使用停止しました。削除しても問題ありません。

### Q: DBのバージョン管理は？

**A**: OneDriveのバージョン履歴で30日分保持されます。それ以上の履歴が必要な場合は、手動でバックアップを作成してください。

### Q: 3台目のPCでも使える？

**A**: 可能です。同じ手順でセットアップしてください。ただし、同時編集には注意が必要です。

---

## サポート

問題が発生した場合は、以下のファイルも参照してください：

- [DB_ONEDRIVE_SETUP_GUIDE.md](../DB_ONEDRIVE_SETUP_GUIDE.md) - 初回セットアップの詳細
- [README.md](../README.md) - プロジェクト概要
- [docs/DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) - データベース仕様

---

**最終更新**: 2025年12月18日
