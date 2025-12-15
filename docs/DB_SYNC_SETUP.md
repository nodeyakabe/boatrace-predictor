# DB同期セットアップガイド

2台のPC間でデータベース（boatrace.db）を共有するための設定手順。

## 概要

- **方式**: Git LFS + GitLab
- **DB保存先**: GitLab（LFS 10GB無料枠）
- **ソースコード**: GitHub（従来通り）

## 前提条件

- Git がインストール済み
- Git LFS がインストール済み（`git lfs version` で確認）

Git LFSが未インストールの場合:
```bash
# Windows (winget)
winget install GitHub.GitLFS

# または https://git-lfs.github.com/ からダウンロード
```

---

## 新規PCでのセットアップ手順

### 1. リポジトリをクローン（GitHubから）

```bash
cd C:\Users\<ユーザー名>\Desktop
git clone https://github.com/nodeyakabe/boatrace-predictor.git BoatRace
cd BoatRace
```

### 2. Git LFSを初期化

```bash
git lfs install
```

### 3. GitLabリモートを追加

```bash
git remote add gitlab https://gitlab.com/nodeyakabe-group/boatrace-db.git
```

### 4. GitLabからDBを取得

```bash
git fetch gitlab main
git checkout gitlab/main -- data/boatrace.db
```

初回は1.7GB程度のダウンロードがあるため、数十分かかります。

### 5. .envファイルを作成

```bash
# .env.example をコピーして編集
cp .env.example .env
# WEATHER_API_KEY などを設定
```

---

## 日常の運用

### 作業開始時（DBを最新化）

```bash
git pull origin main              # ソースコード更新
git fetch gitlab main             # GitLabから最新取得
git checkout gitlab/main -- data/boatrace.db  # DB上書き
```

### 作業終了時（DBをアップロード）

```bash
# DBをコミット
git add -f data/boatrace.db
git commit -m "Update database"

# GitLabにプッシュ（DBのみ）
git push gitlab main

# GitHubにプッシュ（ソースコードのみ、DBは.gitignoreで除外済み）
git push origin main
```

---

## リモート構成

| リモート名 | URL | 用途 |
|-----------|-----|------|
| origin | https://github.com/nodeyakabe/boatrace-predictor.git | ソースコード |
| gitlab | https://gitlab.com/nodeyakabe-group/boatrace-db.git | データベース（LFS） |

確認コマンド:
```bash
git remote -v
```

---

## トラブルシューティング

### 認証エラーが出る場合

GitLabの認証ウィンドウが表示されたらログインしてください。
ブラウザでGitLabにログイン済みなら自動認証されます。

### DBが取得できない場合

```bash
# LFSファイルを明示的に取得
git lfs pull --include="data/boatrace.db"
```

### プッシュがタイムアウトする場合

回線が不安定な場合、再度実行してください:
```bash
git push gitlab main
```

### .gitignoreでdataが除外されている場合

強制的に追加:
```bash
git add -f data/boatrace.db
```

---

## 注意事項

- **同時編集禁止**: 2台のPCで同時にDBを編集しないこと（SQLite破損の恐れ）
- **作業前に必ずpull**: 作業開始時は必ず最新DBを取得
- **作業後に必ずpush**: 作業終了時は必ずDBをアップロード

---

## 簡易コマンド集

```bash
# === 作業開始 ===
git pull origin main
git fetch gitlab main && git checkout gitlab/main -- data/boatrace.db

# === 作業終了 ===
git add -f data/boatrace.db && git commit -m "Update DB" && git push gitlab main
git add . && git commit -m "Update code" && git push origin main
```
