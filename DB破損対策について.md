# DB破損対策について

## 📌 問題の概要

並列オッズ収集中にプロセスを強制終了すると、データベースファイルが0バイトになり破損する問題が発生しました。

### 発生状況

- **1回目**: 12:33開始 → 13:40頃に `taskkill /F` で強制停止 → DB破損（0バイト）
- **2回目**: 14:26再開 → 14:28頃に `PowerShell Stop-Process -Force` で強制停止 → DB破損（0バイト）

## 🔍 原因分析

### 根本原因

**プロセス強制終了時にDBファイルが書き込み中だった**

### 詳細

1. **SQLiteの書き込み動作**
   - SQLiteは書き込み時にファイルを一時的にロック
   - `conn.commit()` 実行中に強制終了されると、ファイルが不完全な状態になる
   - Windows環境では特に顕著（ファイルロックの仕様）

2. **並列処理の問題**
   - 10個のスレッドが同時にDB書き込みを試みる
   - バッチ保存（50件ごと）で書き込みが頻繁に発生
   - 強制終了すると、書き込み中のトランザクションが中断

3. **問題のあるコード**
   ```python
   def save_batch_to_db(self, batch_data):
       conn = sqlite3.connect(self.db_path)  # ← 毎回新規接続
       cursor = conn.cursor()
       try:
           for race_id, odds_data in batch_data:
               for combination, odds_value in odds_data.items():
                   cursor.execute(...)  # ← 大量のINSERT
           conn.commit()  # ← この瞬間に停止すると破損
       finally:
           conn.close()
   ```

## ✅ 実装した対策

### 1. WALモード有効化

**効果**: DB破損のリスクを大幅に削減

```python
self.db_conn.execute("PRAGMA journal_mode=WAL")
self.db_conn.execute("PRAGMA synchronous=NORMAL")
self.db_conn.execute("PRAGMA busy_timeout=30000")
```

**WALモードの利点**:
- 書き込みと読み取りがブロックし合わない
- クラッシュ時のリカバリ性能が高い
- トランザクションの途中で停止してもDB本体は保護される

### 2. シグナルハンドラ実装

**効果**: Ctrl+Cで優雅に終了できる

```python
def signal_handler(signum, frame):
    self.logger.warning("終了シグナル受信。優雅にシャットダウンしています...")
    self.is_shutting_down = True
    self.shutdown_event.set()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
```

**動作**:
1. Ctrl+C押下
2. 現在実行中のタスクを完了
3. バッファデータをDBに保存
4. バックアップ作成
5. DB接続をクローズ
6. 安全に終了

### 3. DB接続プーリング

**効果**: 頻繁なopen/closeを回避、パフォーマンス向上

```python
# 初期化時に接続を確立
self.db_conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)

# 保存時は既存の接続を使用
def save_batch_to_db(self, batch_data):
    cursor = self.db_conn.cursor()  # ← 既存接続を使用
    try:
        cursor.execute("BEGIN IMMEDIATE")
        # ... データ挿入 ...
        self.db_conn.commit()
    except Exception as e:
        self.db_conn.rollback()
```

### 4. 定期的な自動バックアップ

**効果**: データ損失を最小限に

```python
# 1時間ごとに自動バックアップ
if time.time() - self.last_backup_time > self.backup_interval:
    self.create_backup()
```

**バックアップ処理**:
1. 現在のバッファをDBに保存
2. WALチェックポイント実行（WALファイルの内容をメインDBに反映）
3. DBファイルをコピー
4. `data/backups/boatrace_auto_backup_YYYYMMDD_HHMMSS.db` として保存

### 5. トランザクション管理の強化

**効果**: データ整合性の向上

```python
cursor.execute("BEGIN IMMEDIATE")  # 即座にロック取得
# ... データ挿入 ...
self.db_conn.commit()  # 一括コミット
```

## 📝 使用方法

### 改善版の実行

```bash
# バッチファイルから実行（推奨）
run_odds_safe.bat

# または直接実行
python fetch_odds_parallel_safe.py --db data/boatrace.db --start-date 2020-01-01 --end-date 2024-12-31 --workers 10 --delay 0.3 --batch-size 50 --log-file logs/odds_fetch_safe.log --progress-interval 100
```

### 安全な停止方法

**✅ 正しい方法**:
```
Ctrl+C を押す
```

出力例:
```
================================================================================
終了シグナル受信。優雅にシャットダウンしています...
データを保存中です。強制終了しないでください。
================================================================================
新規タスクの投入を停止します
シャットダウン処理を開始します
残りのバッファデータを保存中...
最終バックアップを作成中...
自動バックアップ作成: data/backups/boatrace_auto_backup_20251218_143055.db
データベース接続をクローズしました

================================================================================
中断完了（データは安全に保存されました）
  成功: 5,234レース
  エラー: 12レース
  処理時間: 23.5分 (0.4時間)
  平均速度: 3.71件/秒
================================================================================
```

**❌ 避けるべき方法**:
- `taskkill /F` （強制終了）
- `PowerShell Stop-Process -Force` （強制終了）
- タスクマネージャーから「タスクの終了」

## 📊 パフォーマンス比較

| 項目 | 従来版 | 改善版 |
|------|--------|--------|
| DB破損リスク | 高い | 極めて低い |
| 停止方法 | 強制終了のみ | Ctrl+Cで優雅に終了 |
| DB接続 | 毎回open/close | プーリング |
| バックアップ | 手動のみ | 1時間ごと自動 + 終了時 |
| 処理速度 | 6,000レース/時間 | 同等 or 若干向上 |
| データ安全性 | 低い | 高い |

## 🔧 トラブルシューティング

### Q: それでもDB破損した場合

**A**: 以下の手順でバックアップから復元

```bash
# 最新の自動バックアップを確認
ls -lh data/backups/boatrace_auto_backup_*.db | tail -1

# 復元
cp data/backups/boatrace_auto_backup_YYYYMMDD_HHMMSS.db data/boatrace.db
```

### Q: WALファイル(-wal, -shm)が残っている

**A**: 正常な動作です

- `-wal`: Write-Ahead Logファイル（トランザクション記録）
- `-shm`: 共有メモリファイル（WAL制御用）

これらのファイルは：
- 処理中は必須
- 安全に終了すれば自動削除される
- 強制終了後は残る可能性がある（次回起動時に自動回復）

### Q: バックアップファイルが増えすぎた場合

**A**: 古いバックアップを定期的に削除

```bash
# 7日以上前のバックアップを削除
find data/backups -name "boatrace_auto_backup_*.db" -mtime +7 -delete
```

## 📅 今後の推奨事項

1. **定期的なバックアップ確認**
   - `data/backups/` の容量監視
   - 古いバックアップの定期削除

2. **ログファイルの確認**
   - エラー率が10%を超えたら調査
   - 処理速度の低下をモニタリング

3. **システム環境**
   - ディスク空き容量の確保（最低5GB推奨）
   - PCのスリープ設定を無効化

## 📌 まとめ

### 改善前の問題
- 強制終了でDB破損
- データ損失リスク
- 復旧に時間がかかる

### 改善後
- **WALモード**: DB破損リスク大幅削減
- **優雅な終了**: Ctrl+Cで安全に停止
- **自動バックアップ**: データ損失を最小限に
- **接続プーリング**: パフォーマンス向上

**今後は `fetch_odds_parallel_safe.py` を使用してください。**

---

**最終更新**: 2025-12-18
**作成者**: Claude Code
