# BoatRace プロジェクト - 別端末への移行ガイド

## 📦 バックアップ内容

- **ファイル名**: `BoatRace_backup_20251109_205946.zip`
- **サイズ**: 213.50 MB (圧縮後)
- **元サイズ**: 1275.81 MB
- **圧縮率**: 83.3%

### 含まれるもの

1. **ソースコード** (`src/`)
   - スクレイパー（V3改善版含む）
   - データベース管理
   - 機械学習モデル

2. **設定ファイル** (`config/`)
   - settings.py

3. **データベース**
   - `data/boatrace.db` (1.28 GB)
   - 2015-2021年のボートレースデータ

4. **重要スクリプト**
   - `fetch_improved_v3.py` - V3収集スクリプト（STタイムバグ修正版）
   - `test_improved_v3.py` - V3テストスクリプト
   - `verify_v3_data.py` - データ検証スクリプト
   - `count_missing.py` - 欠損データカウンター

5. **ドキュメント**
   - `SUMMARY_V3_FIX.md` - STタイムバグ修正の詳細
   - `README.md` - プロジェクト概要
   - `requirements.txt` - Python依存関係

## 🚀 別端末でのセットアップ手順

### 1. ZIPファイルの転送と展開

```bash
# ZIPファイルを新しいPCにコピー

# 展開
unzip BoatRace_backup_20251109_205946.zip -d BoatRace
cd BoatRace
```

Windowsの場合：
```cmd
# エクスプローラーでZIPを右クリック → すべて展開
cd BoatRace
```

### 2. Python環境のセットアップ

```bash
# 仮想環境作成（推奨）
python -m venv venv

# 仮想環境の有効化
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 依存関係のインストール
pip install -r requirements.txt
```

### 3. データベースの確認

```bash
# 欠損データ数を確認
python count_missing.py
```

期待される出力：
```
Missing data count (2015-2021): 59081 races
Estimated time (sequential): 246.2 hours
Estimated time (5 workers): 49.2 hours
```

### 4. V3収集の再開

```bash
# 5ワーカーで欠損データを収集
python fetch_improved_v3.py --fill-missing --workers 5
```

少量でテストする場合：
```bash
# 10件だけテスト
python fetch_improved_v3.py --fill-missing --workers 3 --limit 10
```

## 📊 V3改善版の特徴

### 修正された問題

**STタイムに決まり手が混入するバグ**
- 例: Pit 3のSTタイム `.14まくり差し` → 数値抽出失敗 → 欠損
- 影響: 約5,808レース（5/6 STタイムの10.5%）

### V3の改善点

1. **正規表現による数値抽出**
   - `.14まくり差し` → `.14` を正確に抽出
   
2. **F/L対応**
   - Flying: -0.01
   - Late: -0.02
   
3. **st_statusフィールド追加**
   - 'normal', 'flying', 'late' を記録

### テスト結果

- 単体テスト: 6/6 ST times ✅
- 小規模収集（10件）: 90%成功率、全て6/6 ST times ✅

## 📈 進捗確認

### 欠損データ数の確認

```bash
python count_missing.py
```

### データ品質の確認

```bash
# 最近収集したデータの検証
python verify_v3_data.py
```

### Pit 3欠損パターンの確認

```bash
python check_pit3_pattern.py
```

## ⚠️ 注意事項

1. **データベースロック**
   - 収集中はデータベースがロックされます
   - バックアップ前に必ず収集プロセスを停止してください

2. **収集時間**
   - 59,081レース: 約49時間（5ワーカー）
   - 定期的に進捗を確認してください

3. **ネットワーク負荷**
   - ワーカー数が多すぎるとタイムアウトが発生
   - 推奨: 3-5ワーカー

## 🔄 バックアップの作成（新しいPC上で）

```bash
python create_backup.py
```

## 📝 次のステップ

1. V3収集が完了したら `count_missing.py` で確認
2. データ品質分析（6/6 STタイム率の確認）
3. 機械学習モデルの再トレーニング
4. 予測精度の改善確認

## 📞 トラブルシューティング

### データベースが開けない

```bash
# WALモードをチェックポイント
sqlite3 data/boatrace.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

### 依存関係のエラー

```bash
# 個別にインストール
pip install requests beautifulsoup4 lxml pandas scikit-learn
```

### タイムアウトエラー

```bash
# ワーカー数を減らす
python fetch_improved_v3.py --fill-missing --workers 3
```

---

**作成日**: 2025-11-09 20:59
**元環境**: Windows, Python 3.12
