# トラブルシューティングガイド

**バージョン**: 1.0
**最終更新**: 2025-12-11

---

## 目次

1. [予測システム関連](#予測システム関連)
2. [キャッシュ関連](#キャッシュ関連)
3. [ネガティブパターン関連](#ネガティブパターン関連)
4. [モニタリング関連](#モニタリング関連)
5. [データベース関連](#データベース関連)
6. [パフォーマンス関連](#パフォーマンス関連)

---

## 予測システム関連

### 問題: 予測が返ってこない

**症状**: `predict_race()` がNoneまたは空リストを返す

**確認手順**:

```python
import sqlite3

# 1. レースデータの存在確認
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

cursor.execute("""
    SELECT COUNT(*) FROM race_details
    WHERE race_id = ? AND exhibition_time IS NOT NULL
""", (race_id,))
print(f"レース詳細データ: {cursor.fetchone()[0]}件")

# 2. 結果データの確認
cursor.execute("""
    SELECT COUNT(*) FROM results WHERE race_id = ?
""", (race_id,))
print(f"結果データ: {cursor.fetchone()[0]}件")
```

**解決策**:

| 原因 | 対策 |
|------|------|
| レースデータがない | データ収集バッチを実行 |
| BEFORE情報がない | 展示タイム/ST情報の収集確認 |
| モデルファイルがない | `models/` ディレクトリ確認 |

### 問題: 予測スコアが異常（0や極端な値）

**症状**: `total_score` が0、負の値、または1000以上

**確認手順**:

```python
from src.analysis.race_predictor import RacePredictor

predictor = RacePredictor()
predictions = predictor.predict_race(race_id)

for p in predictions:
    print(f"艇{p['pit_number']}: PRE={p.get('pre_score', 'N/A')}, "
          f"PATTERN={p.get('pattern_multiplier', 1.0)}, "
          f"TOTAL={p.get('total_score', 0)}")
```

**解決策**:

1. パターン倍率の確認（通常1.0-1.5の範囲）
2. フィーチャーフラグの状態確認
3. モデルの再訓練を検討

---

## キャッシュ関連

### 問題: キャッシュヒット率が低い

**症状**: ヒット率が30%未満

**確認手順**:

```python
from src.utils.pattern_cache import PatternCache

cache = PatternCache(ttl_minutes=15)
stats = cache.get_stats()
print(f"ヒット: {stats['hits']}")
print(f"ミス: {stats['misses']}")
print(f"ヒット率: {stats['hit_rate']:.1%}")
```

**解決策**:

| 原因 | 対策 |
|------|------|
| TTLが短すぎる | `ttl_minutes` を増やす（30-60分） |
| キャッシュキーの不一致 | キー生成ロジック確認 |
| 頻繁なクリア | `clear()` 呼び出し箇所を確認 |

### 問題: キャッシュが肥大化

**症状**: メモリ使用量増加、サイズが10000以上

**確認手順**:

```python
cache = PatternCache()
stats = cache.get_stats()
print(f"キャッシュサイズ: {stats['size']}エントリ")
```

**解決策**:

```python
# 期限切れエントリの削除
cache.cleanup_expired()

# 完全クリア（最終手段）
cache.clear()
```

---

## ネガティブパターン関連

### 問題: ネガティブパターンが検出されない

**症状**: `has_negative` が常にFalse

**確認手順**:

```python
from config.feature_flags import is_feature_enabled

# フラグ確認
print(f"negative_patterns: {is_feature_enabled('negative_patterns')}")
```

```python
from src.analysis.negative_pattern_checker import NegativePatternChecker

checker = NegativePatternChecker()

# 直接テスト（これはnegativeになるべき条件）
result = checker.check_prediction(
    pit_number=1,
    ex_rank=6,  # ワースト
    st_rank=6,  # ワースト
    st_time=0.25,
    pre_rank=1
)
print(result)
```

**解決策**:

1. フィーチャーフラグを有効化
2. BEFORE情報（ex_rank, st_rank）がNoneでないことを確認

### 問題: ネガティブパターンが効きすぎる

**症状**: 的中率の低下、多くの予測が変更される

**確認手順**:

```python
# ネガティブパターン適用率の確認
predictions = predictor.predict_race(race_id)
negative_count = sum(1 for p in predictions if p.get('negative_pattern_applied'))
print(f"ネガティブ適用: {negative_count}/{len(predictions)}")
```

**解決策**:

1. `score_multiplier` の値を調整（現在0.85、0.90、0.95）
2. フィーチャーフラグを一時的に無効化

```python
# src/analysis/negative_pattern_checker.py の調整
'both_bad': {
    'score_multiplier': 0.90,  # 0.85から緩和
}
```

---

## モニタリング関連

### 問題: 自動モニタリングが実行されない

**症状**: レポートファイルが生成されない

**確認手順**:

```powershell
# タスクスケジューラ確認
.\scripts\setup_monitoring_task.ps1 -Action status
```

**解決策**:

```powershell
# タスク再作成
.\scripts\setup_monitoring_task.ps1 -Action create
```

### 問題: アラートが送信されない

**症状**: 設定したのに通知が来ない

**確認手順**:

```python
import json
with open('config/monitoring_config.json', 'r') as f:
    config = json.load(f)
print(config['notifications'])
```

**解決策**:

1. `enabled` がTrueか確認
2. SMTP/Webhookの設定値確認
3. ファイアウォール確認

```bash
# 通知テスト
python src/utils/alert_notifier.py
```

---

## データベース関連

### 問題: データベースがロックされている

**症状**: `database is locked` エラー

**確認手順**:

```bash
# 接続中のプロセス確認（Windows）
tasklist | findstr python
```

**解決策**:

1. 同時実行中のスクリプトを終了
2. UIを停止してから再実行
3. タイムアウト設定の追加

```python
conn = sqlite3.connect('data/boatrace.db', timeout=30)
```

### 問題: データ整合性エラー

**症状**: 予測時にKeyErrorやデータ不足

**確認手順**:

```python
# データ完全性チェック
cursor.execute("""
    SELECT
        r.race_date,
        COUNT(DISTINCT r.id) as races,
        COUNT(DISTINCT rd.race_id) as details,
        COUNT(DISTINCT res.race_id) as results
    FROM races r
    LEFT JOIN race_details rd ON r.id = rd.race_id
    LEFT JOIN results res ON r.id = res.race_id
    WHERE r.race_date >= date('now', '-7 days')
    GROUP BY r.race_date
""")
for row in cursor.fetchall():
    print(row)
```

**解決策**:

1. 欠損データの再収集
2. データ補完スクリプトの実行

---

## パフォーマンス関連

### 問題: 予測が遅い（5秒以上）

**症状**: 1レースの予測に時間がかかる

**確認手順**:

```python
import time

start = time.time()
predictions = predictor.predict_race(race_id)
elapsed = time.time() - start
print(f"処理時間: {elapsed:.2f}秒")
```

**解決策**:

| 原因 | 対策 |
|------|------|
| キャッシュ無効 | キャッシュ有効化 |
| DBクエリが遅い | インデックス確認 |
| モデル読み込み | モデルのメモリ常駐化 |

### 問題: メモリ使用量が多い

**症状**: 8GB以上のメモリ使用

**確認手順**:

```python
import psutil
process = psutil.Process()
print(f"メモリ使用: {process.memory_info().rss / 1024 / 1024:.0f} MB")
```

**解決策**:

1. キャッシュの定期クリア
2. 不要なモデルのアンロード
3. バッチサイズの調整

---

## よくある質問（FAQ）

### Q: フィーチャーフラグをコード以外から変更できますか？

A: 現在はコード変更が必要です。設定ファイル化は今後の課題です。

### Q: キャッシュはどこに保存されていますか？

A: メモリ上に保存されます。永続化が必要な場合はRedis等の導入を検討してください。

### Q: 会場別の倍率を変更するには？

A: `src/analysis/venue_pattern_optimizer.py` の `venue_characteristics` を編集してください。

### Q: ログはどこに保存されますか？

A: `logs/monitoring/` および `logs/alerts/` に保存されます。

---

## 緊急連絡先

問題が解決しない場合:

1. `docs/残タスク一覧.md` に問題を記録
2. エラーログを保存
3. 再現手順を文書化

---

*このトラブルシューティングガイドは継続的に更新されます。*
