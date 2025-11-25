# Git設定手順ガイド

このドキュメントは、別PCでこのプロジェクトのGit環境を設定するための手順書です。

## 前提条件

- Gitがインストールされていること
- GitHubアカウントを持っていること
- インターネット接続があること

## 設定情報

```
ユーザー名: nodeyakabe
メールアドレス: yakabe@nodecast.jp
リモートリポジトリURL: https://github.com/nodeyakabe/boatrace-predictor.git
ブランチ: main
```

## 手順1: Gitユーザー設定

以下のコマンドでGitのユーザー情報を設定してください。

```bash
git config --global user.name "nodeyakabe"
git config --global user.email "yakabe@nodecast.jp"
```

## 手順2: リポジトリのクローン

GitHubからプロジェクトをクローンします。

```bash
cd 作業ディレクトリのパス
git clone https://github.com/nodeyakabe/boatrace-predictor.git
cd boatrace-predictor
```

## 手順3: 動作確認

正しくクローンできたか確認します。

```bash
git status
git log --oneline -5
```

## 手順4: 認証設定（初回プッシュ時に必要）

GitHubへプッシュする際、認証が求められます。以下の方法で対応してください。

### 方法A: Personal Access Token（推奨）

1. GitHubにログイン
2. Settings → Developer settings → Personal access tokens → Tokens (classic)
3. "Generate new token (classic)" をクリック
4. Noteに「BoatRace Predictor」などと入力
5. `repo` にチェックを入れる
6. "Generate token" をクリック
7. 表示されたトークンをコピー（二度と表示されないので保存してください）
8. プッシュ時、パスワードの代わりにこのトークンを使用

### 方法B: SSH鍵認証

```bash
# SSH鍵を生成（既に持っている場合はスキップ）
ssh-keygen -t ed25519 -C "yakabe@nodecast.jp"

# 公開鍵を表示
cat ~/.ssh/id_ed25519.pub

# GitHubに公開鍵を登録
# Settings → SSH and GPG keys → New SSH key
# 表示された公開鍵をコピーして貼り付け

# リモートURLをSSHに変更
git remote set-url origin git@github.com:nodeyakabe/boatrace-predictor.git
```

## よく使うGitコマンド

### 変更をコミットしてプッシュ

```bash
# 変更されたファイルを確認
git status

# すべての変更をステージング
git add .

# コミット
git commit -m "変更内容の説明"

# GitHubにプッシュ
git push
```

### 最新版を取得

```bash
# GitHubから最新版を取得
git pull
```

### ブランチ操作

```bash
# 新しいブランチを作成して切り替え
git checkout -b 新しいブランチ名

# ブランチ一覧を表示
git branch

# ブランチを切り替え
git checkout ブランチ名

# ブランチをmainにマージ
git checkout main
git merge ブランチ名
```

### 変更の確認

```bash
# 変更内容を確認
git diff

# コミット履歴を確認
git log

# グラフ形式で履歴を確認
git log --graph --oneline --all
```

## プロジェクト固有の注意事項

### .gitignoreの設定

以下のファイル・ディレクトリはGit管理から除外されています：

- `.env` - 環境変数（機密情報）
- `*.db`, `*.sqlite` - データベースファイル
- `*.csv` - データファイル
- `__pycache__/` - Pythonキャッシュ
- `logs/`, `*.log`, `*.txt` - ログファイル
- `models/`, `*.pkl`, `*.joblib` - 機械学習モデル
- `*.zip`, `*.tar.gz` - アーカイブファイル
- `*.html` - デバッグ用HTMLファイル
- `*.png`, `*.jpg` - 画像ファイル

### 環境変数の設定

`.env`ファイルはGit管理されていません。`.env.example`を参考に、各PCで個別に作成してください。

```bash
# .env.exampleをコピー
cp .env.example .env

# .envファイルを編集
# エディタで必要な環境変数を設定
```

## トラブルシューティング

### プッシュ時に認証エラーが出る

```bash
# Personal Access Tokenを使用しているか確認
# または、SSH鍵が正しく設定されているか確認
ssh -T git@github.com
```

### コンフリクト（競合）が発生した場合

```bash
# 最新版を取得してマージ
git pull

# コンフリクトしたファイルを手動で編集
# コンフリクトマーカー（<<<<<<<, =======, >>>>>>>）を削除して修正

# 修正後、コミット
git add .
git commit -m "Resolve conflict"
git push
```

### 間違えてコミットした場合

```bash
# 直前のコミットを取り消し（変更は残る）
git reset --soft HEAD~1

# 直前のコミットを完全に取り消し（変更も削除）
git reset --hard HEAD~1
```

## 参考リンク

- Git公式ドキュメント: https://git-scm.com/doc
- GitHub Docs: https://docs.github.com/ja
- GitHubリポジトリ: https://github.com/nodeyakabe/boatrace-predictor

## サポート

設定で問題が発生した場合は、このドキュメントをClaude Codeに読ませて質問してください。
