# 運用手順書

**バージョン**: 1.0
**最終更新**: 2025-12-11

---

## 目次

1. [日常運用](#日常運用)
2. [定期タスク](#定期タスク)
3. [モニタリング](#モニタリング)
4. [トラブルシューティング](#トラブルシューティング)
5. [緊急対応](#緊急対応)

---

## 日常運用

### 1. 予測実行

#### UIから予測

```bash
cd ui && python -m streamlit run app.py
```

ブラウザで `http://localhost:8501` にアクセス

#### コマンドラインから予測

```python
from src.analysis.race_predictor import RacePredictor

predictor = RacePredictor()
predictions = predictor.predict_race(race_id)
```

### 2. 結果確認

予測結果には以下の情報が含まれます:

| フィールド | 説明 |
|------------|------|
| `pit_number` | 艇番 |
| `total_score` | 最終スコア |
| `confidence` | 信頼度（A-E） |
| `pattern_multiplier` | パターン倍率 |
| `negative_pattern_applied` | ネガティブパターン適用有無 |
| `negative_patterns` | 検出されたネガティブパターン |

---

## 定期タスク

### 日次タスク

| 時刻 | タスク | コマンド |
|------|--------|----------|
| 23:30 | 自動モニタリング | `python scripts/automated_monitoring.py` |
| 夜間 | データ収集バッチ | `scripts/night_batch.bat` |

### 週次タスク（推奨: 毎週月曜日）

| タスク | コマンド | 目的 |
|--------|----------|------|
| パターン分析 | `python scripts/auto_pattern_update.py --days 7` | パフォーマンス確認 |
| パフォーマンスレポート | `python scripts/monitor_pattern_performance.py` | 精度傾向分析 |

### 月次タスク

| タスク | コマンド | 目的 |
|--------|----------|------|
| 詳細パターン分析 | `python scripts/auto_pattern_update.py --days 30` | 長期トレンド確認 |
| ログクリーンアップ | 30日以上のログ削除 | ディスク容量管理 |

---

## モニタリング

### キャッシュ状態確認

```python
from src.utils.pattern_cache import PatternCache

cache = PatternCache()
stats = cache.get_stats()
print(f"ヒット率: {stats['hit_rate']:.1%}")
print(f"サイズ: {stats['size']}エントリ")
```

### ネガティブパターン動作確認

```python
from src.analysis.negative_pattern_checker import NegativePatternChecker

checker = NegativePatternChecker()
result = checker.check_prediction(
    pit_number=1,
    ex_rank=6,
    st_rank=6,
    st_time=0.22,
    pre_rank=1
)
print(f"検出: {result['matched_patterns']}")
print(f"重要度: {result['severity']}")
```

### フィーチャーフラグ状態確認

```python
from config.feature_flags import get_enabled_features

enabled = get_enabled_features()
print(f"有効な機能: {enabled}")
```

### パフォーマンスモニター確認

```python
from src.monitoring.performance_monitor import PerformanceMonitor

monitor = PerformanceMonitor()
trend = monitor.get_performance_trend(days=7)
for day in trend:
    print(f"{day['date']}: 1着的中率 {day['hit_rate_1st']:.1%}")
```

---

## トラブルシューティング

### 問題: 予測結果が返ってこない

**確認手順**:

1. データベース接続確認
```python
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM races")
print(cursor.fetchone())
```

2. モデルファイル確認
```bash
ls models/
```

3. フィーチャーフラグ確認
```python
from config.feature_flags import get_all_features
print(get_all_features())
```

### 問題: 的中率が低下している

**確認手順**:

1. 最近のパフォーマンス確認
```bash
python scripts/auto_pattern_update.py --days 7
```

2. ネガティブパターンの影響確認
```python
from config.feature_flags import set_feature_flag
# 一時的に無効化して比較
set_feature_flag('negative_patterns', False)
```

3. パターン適用率確認
```bash
python scripts/monitor_pattern_performance.py
```

### 問題: キャッシュが効いていない

**確認手順**:

```python
from src.utils.pattern_cache import PatternCache

cache = PatternCache()
stats = cache.get_stats()

if stats['hit_rate'] < 0.3:
    print("キャッシュヒット率が低い")
    print("原因: TTL設定、キャッシュキー不一致")
```

### 問題: モニタリングタスクが実行されない

**確認手順**:

```powershell
# タスク状態確認
.\scripts\setup_monitoring_task.ps1 -Action status

# 必要に応じて再作成
.\scripts\setup_monitoring_task.ps1 -Action create
```

---

## 緊急対応

### 精度が急激に低下した場合

1. **即座にフィーチャーフラグ確認**
```python
from config.feature_flags import get_all_features
print(get_all_features())
```

2. **最近の変更をロールバック**
```bash
# ネガティブパターン無効化
python -c "from config.feature_flags import set_feature_flag; set_feature_flag('negative_patterns', False)"
```

3. **データ品質確認**
```python
# 最新データの整合性確認
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()
cursor.execute("""
    SELECT race_date, COUNT(*)
    FROM races
    WHERE race_date >= date('now', '-7 days')
    GROUP BY race_date
""")
for row in cursor.fetchall():
    print(row)
```

### システムエラーが発生した場合

1. **ログ確認**
```bash
type logs\monitoring\*.log | tail -100
```

2. **エラー詳細調査**
```bash
type logs\alerts\*.log
```

3. **復旧手順**
```bash
# バックアップから復元
copy backups\pre_deployment_*\feature_flags.py.bak config\feature_flags.py
```

---

## 連絡先・エスカレーション

| レベル | 状況 | 対応 |
|--------|------|------|
| L1 | 軽微な警告 | 次回運用時に確認 |
| L2 | 的中率10%低下 | 1日以内に原因調査 |
| L3 | システムダウン | 即座にロールバック |

---

## 付録: コマンドクイックリファレンス

```bash
# 予測実行
python -c "from src.analysis.race_predictor import RacePredictor; p=RacePredictor(); print(p.predict_race(RACE_ID))"

# モニタリング実行
python scripts/automated_monitoring.py

# パターン分析
python scripts/auto_pattern_update.py --days 7

# フラグ有効化
python -c "from config.feature_flags import set_feature_flag; set_feature_flag('FLAG_NAME', True)"

# フラグ無効化
python -c "from config.feature_flags import set_feature_flag; set_feature_flag('FLAG_NAME', False)"

# UI起動
cd ui && python -m streamlit run app.py
```

---

*この運用手順書は定期的に更新されます。最新版は `docs/OPERATIONS_GUIDE.md` を参照してください。*
