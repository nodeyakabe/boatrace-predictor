# スクリプトガイド

最新バージョンのスクリプトと使い方を説明します。

## 📁 ディレクトリ構成

```
BoatRace/
├── scripts/              # 実行用スクリプト
├── src/                  # ソースコード
│   ├── workflow/        # ワークフロー（並列化版）
│   ├── scraper/         # データ取得
│   ├── prediction/      # 予測エンジン
│   └── ...
├── ui/                   # Streamlit UI
├── _archive/            # 旧バージョン・実験コード
└── ルート              # 現在使用中の補完スクリプト
```

## 🚀 主要スクリプト

### データ収集

#### 1. **不足データ一括取得（並列化版）** ⭐ 推奨
```bash
python scripts/bulk_missing_data_fetch_parallel.py --start-date 2025-12-01 --end-date 2025-12-04
```
- **並列処理**: 16スレッド（結果取得）、8スレッド（直前情報）
- **速度**: 従来版の10-20倍高速
- **推定時間**: 1000レース → 約10-20分
- **オプション**:
  - `--workers-results N`: 結果取得の並列数（デフォルト: 16）
  - `--workers-beforeinfo N`: 直前情報取得の並列数（デフォルト: 8）
  - `--workers-odds N`: オッズ取得の並列数（デフォルト: 4）

#### 2. **今日の予測生成**
```bash
python scripts/background_today_prediction.py
```
- 本日のレースデータ取得
- 直前情報・オッズ取得（並列処理）
- 予測生成

#### 3. **オリジナル展示データ収集**
```bash
python fetch_original_tenji_daily.py
```
- 直線タイム、1周タイム、回り足タイム
- ⚠️ 公開期間が限られているため、毎日実行推奨

### データ補完（単独実行）

これらは通常、並列化版スクリプトから自動実行されます。

```bash
# レース詳細（ST時間、実際コース）
python 補完_レース詳細データ_改善版v4.py --start-date 2025-12-01 --end-date 2025-12-04

# 決まり手
python 補完_決まり手データ_改善版.py --start-date 2025-12-01 --end-date 2025-12-04

# 払戻金
python 補完_払戻金データ.py --start-date 2025-12-01 --end-date 2025-12-04

# 潮位データ
python 収集_潮位データ_最新.py --start-date 2025-12-01 --end-date 2025-12-04
```

### データベース

```bash
# 初期化
python init_database.py

# テーブル更新（マイグレーション）
python update_database.py
```

## 🎯 推奨ワークフロー

### 1. 初回セットアップ
```bash
# 仮想環境作成
python -m venv venv
venv\Scripts\activate

# パッケージインストール
pip install -r requirements.txt

# データベース初期化
python init_database.py
```

### 2. 日次運用（UIから実行推奨）
```bash
# UIを起動
streamlit run ui/app.py
```

UI で以下を実行:
1. **データ準備** → **ワークフロー自動化** → 「🎯 今日の予測を生成」
2. **レース予想** → 予測結果を確認

### 3. 過去データ補完（コマンドライン）
```bash
# 過去1ヶ月の不足データを高速取得
python scripts/bulk_missing_data_fetch_parallel.py \
  --start-date 2025-11-01 \
  --end-date 2025-12-04 \
  --workers-results 16
```

## ⚠️ 非推奨スクリプト

以下は `_archive/` に移動済み。参考資料として残していますが、使用は推奨しません:

### 旧バージョン
- `bulk_missing_data_fetch.py` → **`bulk_missing_data_fetch_parallel.py` を使用**
- 各種 `collect_*.py` → UIから実行
- 各種 `test_*.py`, `verify_*.py` → 開発用のみ

### アーカイブの場所
```
_archive/
├── legacy_scripts/    # 旧バージョンスクリプト
├── experiments/       # 実験的コード
├── tests/            # テストコード
└── docs_old/         # 過去のドキュメント
```

## 📊 パフォーマンス比較

| スクリプト | 処理速度 | 1000レース | 用途 |
|-----------|---------|-----------|------|
| **並列化版** | 1.5件/秒 | **10-20分** | ✅ 推奨 |
| 従来版 | 0.2件/秒 | 約80分 | ❌ 非推奨 |

## 🔧 トラブルシューティング

### データベースロック
```bash
# 接続を閉じる
python -c "import sqlite3; conn=sqlite3.connect('data/boatrace.db'); conn.close()"
```

### 並列数の調整
サーバー負荷が高い場合は並列数を減らす:
```bash
python scripts/bulk_missing_data_fetch_parallel.py \
  --start-date 2025-12-01 \
  --end-date 2025-12-04 \
  --workers-results 8 \
  --workers-beforeinfo 4
```

## 📅 更新履歴

- **2025-12-05**: 並列化版スクリプト追加、プロジェクト大規模整理
- **2025-11-13**: UI統合、ワークフロー自動化
- **2025-11-02**: README作成、バックテスト機能追加
