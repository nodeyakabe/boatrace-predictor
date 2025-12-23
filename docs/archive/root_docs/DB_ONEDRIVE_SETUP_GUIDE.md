# OneDrive DB同期セットアップガイド（メインPC）

## ✅ セットアップ完了

このガイドは**メインPC（PC-A）での初回セットアップ**用です。
**別PC（サブPC）でのセットアップ**は [docs/DUAL_PC_SETUP_GUIDE.md](docs/DUAL_PC_SETUP_GUIDE.md) を参照してください。

---

## 完了した作業

### 1. ✅ OneDriveフォルダ作成
```
C:\Users\User\OneDrive\BoatRace\data\
```

### 2. ✅ DBをOneDriveにコピー
```
元の場所: data\boatrace.db (1.9GB)
コピー先: C:\Users\User\OneDrive\BoatRace\data\boatrace.db
```

### 3. ✅ シンボリックリンク作成
```
data\boatrace.db → C:\Users\User\OneDrive\BoatRace\data\boatrace.db
```

### 4. ✅ Git設定変更
- `.gitattributes` でGit LFS無効化
- GitHubリポジトリからDB削除（1.9GB削減）
- プッシュが高速化（数秒で完了）

### 5. ✅ バックアップ作成
```
デスクトップ: C:\Users\User\Desktop\boatrace_backup_20251218.db
```

---

## 構成

```
メインPC (PC-A)
├─ プロジェクトフォルダ/
│  ├─ data/
│  │  └─ boatrace.db ← シンボリックリンク
│  └─ ...
├─ OneDrive/
│  └─ BoatRace/
│     └─ data/
│        └─ boatrace.db ← 実体（クラウド同期中）
└─ Desktop/
   └─ boatrace_backup_20251218.db ← バックアップ
```

---

## 今後の運用

### 通常の作業フロー

1. **コード変更**
2. **Git操作**
   ```bash
   git add .
   git commit -m "変更内容"
   git push origin main  # 数秒で完了！
   ```
3. **DB更新時**
   - 何もしなくてOK
   - OneDriveが自動的にクラウドにアップロード
   - 別PCに自動同期される

### DB確認

```bash
# DBファイルの確認
ls -lh data/boatrace.db

# DB接続テスト
python -c "import sqlite3; conn = sqlite3.connect('data/boatrace.db'); print('接続成功'); conn.close()"
```

---

## 別PCでの作業

別PCでも同じ環境を構築する場合は、以下のガイドを参照してください：

📖 **[docs/DUAL_PC_SETUP_GUIDE.md](docs/DUAL_PC_SETUP_GUIDE.md)**

---

## トラブルシューティング

### OneDrive同期の確認

**タスクバーのOneDriveアイコン**をクリックして同期状態を確認：
- ✓ マーク: 同期完了
- 矢印マーク: 同期中
- ⚠ マーク: エラー

### シンボリックリンクが切れた場合

再作成してください：

```cmd
cd C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\data
del boatrace.db
mklink boatrace.db C:\Users\User\OneDrive\BoatRace\data\boatrace.db
```

### OneDrive容量不足

現在の使用量:
- DB: 1.9GB / 5GB（無料プラン）

容量が不足する場合：
- Microsoft 365プラン（1TB）へアップグレード
- 古いバックアップファイルを削除

---

## バックアップ戦略

### 自動バックアップ
1. **OneDrive クラウド**: 自動同期
2. **OneDrive ローカル**: PC内にコピー
3. **OneDrive バージョン履歴**: 30日間保持

### 手動バックアップ
- デスクトップ: `boatrace_backup_20251218.db`
- 必要に応じて外付けHDD/SSDにコピー

---

## GitLab について

GitLabリポジトリは容量不足のため使用停止しました。

- ❌ GitLab: 使用停止（削除可能）
- ✅ GitHub: コード管理（高速プッシュ）
- ✅ OneDrive: DB管理（自動同期）

---

## 参考ドキュメント

- [docs/DUAL_PC_SETUP_GUIDE.md](docs/DUAL_PC_SETUP_GUIDE.md) - 別PCセットアップ手順
- [README.md](README.md) - プロジェクト概要
- [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) - DB仕様書

---

**セットアップ完了日**: 2025年12月18日
