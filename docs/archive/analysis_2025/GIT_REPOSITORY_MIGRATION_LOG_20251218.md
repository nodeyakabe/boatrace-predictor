# Git リポジトリ移行作業ログ

**作業日**: 2025年12月18日
**作業内容**: GitLab容量問題の解決とOneDrive DB同期への移行

---

## 背景・問題点

### 発生した問題

1. **GitLabへのプッシュが失敗**
   - エラー: 容量超過（allocated storage exceeded）
   - 原因: DBファイル（1.9GB）をGit LFSで管理していたが、複数回の更新で容量超過

2. **プッシュに時間がかかる**
   - DBを含むプッシュに数分～10分以上かかっていた
   - Git LFSでも1.9GBのアップロードは重い

3. **リポジトリが2つ存在**
   - GitHub: https://github.com/nodeyakabe/boatrace-predictor.git
   - GitLab: https://gitlab.com/nodeyakabe-group/boatrace-db.git
   - 両方にプッシュする運用は非効率

---

## 実施した解決策

### 案2.5: GitHub（コードのみ）+ OneDrive（DB同期）

**方針**:
- GitHub: コード管理（高速プッシュ）
- OneDrive: DB管理（自動同期）
- GitLab: 使用停止（ローカル設定削除）

---

## 作業手順

### 1. OneDriveフォルダ作成

```bash
mkdir -p /c/Users/User/OneDrive/BoatRace/data
```

作成場所:
```
C:\Users\User\OneDrive\BoatRace\data\
```

### 2. DBをOneDriveにコピー

```bash
cp data/boatrace.db /c/Users/User/OneDrive/BoatRace/data/boatrace.db
```

- ファイルサイズ: 1.9GB
- コピー時間: 約1分

### 3. バックアップ作成

```bash
cp data/boatrace.db ~/Desktop/boatrace_backup_20251218.db
```

バックアップ場所:
- デスクトップ: `C:\Users\User\Desktop\boatrace_backup_20251218.db`
- OneDrive: `C:\Users\User\OneDrive\BoatRace\data\boatrace.db`
- 元の場所: `data\boatrace.db`（これをシンボリックリンクに変更）

### 4. シンボリックリンク作成

**管理者権限のコマンドプロンプトで実行**:

```cmd
cd C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032
del /F data\boatrace.db
cd data
mklink boatrace.db C:\Users\User\OneDrive\BoatRace\data\boatrace.db
```

結果:
```
data\boatrace.db → C:\Users\User\OneDrive\BoatRace\data\boatrace.db
```

### 5. Git設定変更

#### .gitattributes編集

変更前:
```
data/*.db filter=lfs diff=lfs merge=lfs -text
```

変更後:
```
# DBファイルはOneDriveで管理（Git LFS使用停止）
# data/*.db filter=lfs diff=lfs merge=lfs -text
```

#### GitHubからDB削除

```bash
git rm --cached data/boatrace.db
git add .gitattributes
git commit -m "OneDrive DB同期に移行・GitHub軽量化"
git push origin main  # 数秒で完了！
```

### 6. Git LFS無効化

```bash
git lfs uninstall
```

### 7. GitLabリモート削除

```bash
git remote remove gitlab
```

確認:
```bash
git remote -v
# origin  https://github.com/nodeyakabe/boatrace-predictor.git (fetch)
# origin  https://github.com/nodeyakabe/boatrace-predictor.git (push)
```

---

## 変更後の構成

```
メインPC (PC-A)
├─ プロジェクトフォルダ/
│  ├─ src/
│  ├─ data/
│  │  └─ boatrace.db ← シンボリックリンク
│  └─ ...
├─ OneDrive/
│  └─ BoatRace/
│     └─ data/
│        └─ boatrace.db ← 実体（クラウド同期）
└─ Desktop/
   └─ boatrace_backup_20251218.db ← バックアップ
```

---

## 効果

### Before（変更前）

| 項目 | 状態 |
|------|------|
| GitHubプッシュ | 数分～10分以上 |
| GitLabプッシュ | 容量超過で失敗 |
| リポジトリサイズ | 1.9GB（DB含む） |
| DB同期方法 | Git LFS |
| 別PC同期 | Gitクローン（重い） |

### After（変更後）

| 項目 | 状態 |
|------|------|
| GitHubプッシュ | **数秒で完了** ✅ |
| GitLabプッシュ | 使用停止 |
| リポジトリサイズ | **数十MB（コードのみ）** ✅ |
| DB同期方法 | **OneDrive自動同期** ✅ |
| 別PC同期 | **OneDrive自動同期** ✅ |

---

## トラブルシューティング履歴

### 問題1: DBファイルが削除できない

**エラー**:
```
rm: cannot remove 'data/boatrace.db': Device or resource busy
```

**原因**: OneDrive同期プロセスがファイルをロック

**解決**: 管理者権限のコマンドプロンプトで `del /F` を使用

### 問題2: Gitプッシュで LFS エラー

**エラー**:
```
remote: error: GH008: Your push referenced at least 1 unknown Git LFS object
```

**原因**: 過去のコミット履歴にLFS参照が残っていた

**解決**:
1. `git reset --soft d19c0d9` でDB更新前に戻る
2. 新しいコミットを作成
3. プッシュ成功

---

## 今後の運用

### 日常作業

**コード変更時**:
```bash
git add .
git commit -m "変更内容"
git push  # 数秒で完了
```

**データ収集時**:
```bash
python scripts/daily_collection.py
# 何もしなくてOK - OneDriveが自動同期
```

### 別PCでの作業

詳細は [docs/DUAL_PC_SETUP_GUIDE.md](DUAL_PC_SETUP_GUIDE.md) を参照

**セットアップ手順概要**:
1. OneDrive同期完了を確認
2. GitHubからクローン
3. シンボリックリンク作成
4. Python環境セットアップ

---

## GitLab リポジトリについて

### 現状

- **リポジトリ**: まだ存在（削除していない）
- **ローカル設定**: 削除済み
- **アクセス**: https://gitlab.com/nodeyakabe-group/boatrace-db.git

### 将来の選択肢

**A. このまま放置**
- メリット: バックアップとして残る
- デメリット: 容量超過の警告が来る可能性

**B. リポジトリを削除**
- GitLab Web UI → Settings → General → Advanced → Remove project

**C. 復帰する場合**
```bash
git remote add gitlab https://gitlab.com/nodeyakabe-group/boatrace-db.git
```

---

## 参考ドキュメント

作成したドキュメント:
- [DB_ONEDRIVE_SETUP_GUIDE.md](../DB_ONEDRIVE_SETUP_GUIDE.md) - メインPC用セットアップガイド
- [docs/DUAL_PC_SETUP_GUIDE.md](DUAL_PC_SETUP_GUIDE.md) - 別PC用セットアップガイド

---

## 学んだこと

1. **大容量ファイルはGit LFSでも限界がある**
   - 1.9GBのファイルを頻繁に更新すると容量超過
   - クラウドストレージ（OneDrive）の方が適している

2. **シンボリックリンクは便利**
   - プロジェクト構造を変えずにファイルの実体を移動できる
   - OneDriveと組み合わせることで自動同期可能

3. **Git リポジトリは軽量に保つべき**
   - コードのみならプッシュが高速
   - データは別の方法で管理する方が効率的

4. **複数リポジトリ運用は複雑**
   - GitHub 1つに集約してシンプルに
   - 用途が明確でない限り複数リポジトリは避けるべき

---

## まとめ

✅ GitLab容量問題を解決
✅ GitHubプッシュを高速化（数秒）
✅ OneDriveでDB自動同期を実現
✅ 別PC間での作業をスムーズに
✅ Git管理をシンプルに（GitHubのみ）

**作業完了**: 2025年12月18日
