# デプロイメントシステム実装サマリー

## 概要

段階的導入と品質管理のための3つのシステムを実装しました。

---

## 1. Walk-forward Backtest

### 目的
時系列を考慮した段階的バックテスト。過去データで学習し、未来データで検証を繰り返すことで、モデルの実運用での性能を正確に評価します。

### ファイル
- [src/evaluation/walkforward_backtest.py](../src/evaluation/walkforward_backtest.py)
- [test_walkforward.py](../test_walkforward.py) (テストスクリプト)

### 主な機能

#### 1. Walk-forward Backtestの実行
```python
from src.evaluation.walkforward_backtest import WalkForwardBacktest

backtest = WalkForwardBacktest()

result = backtest.run_walkforward(
    start_date='2025-11-01',
    end_date='2025-11-17',
    train_days=14,      # 訓練期間
    test_days=3,        # テスト期間
    step_days=3,        # ステップ間隔
    output_dir='temp/walkforward/test'
)
```

#### 2. 評価指標
- **1着的中率**: 予測1位が実際1位になる確率
- **3連単的中率**: 予測上位3艇が実際の上位3艇と完全一致する確率
- **スコア精度**: 予測順位と実際順位の相関 (0-1)

#### 3. 出力ファイル
- `walkforward_results.json`: 詳細な評価結果（JSON形式）
- `walkforward_report.txt`: 人間が読みやすいレポート

### 使用例

```bash
python test_walkforward.py
```

**期待される出力:**
```
総ステップ数: 6
総評価レース数: XXX

【全体統計】
  1着的中率: XX.XX%
  3連単的中率: X.XX%
  平均スコア精度: 0.XXXX

【ステップ平均】
  平均1着的中率: XX.XX%
  平均3連単的中率: X.XX%
  平均スコア精度: 0.XXXX
```

---

## 2. Performance Monitor

### 目的
日次精度推移を記録・可視化するモニタリングシステム。予測精度の異常を検知し、アラートを発報します。

### ファイル
- [src/monitoring/performance_monitor.py](../src/monitoring/performance_monitor.py)

### 主な機能

#### 1. 予測結果の記録
```python
from src.monitoring.performance_monitor import PerformanceMonitor

monitor = PerformanceMonitor()

# 予測結果をログに記録
monitor.log_prediction(
    race_id=12345,
    race_date='2025-11-17',
    venue_code='01',
    race_number=1,
    predictions=[...],
    actual_results=[...],
    integration_mode='DYNAMIC',
    feature_flags={'dynamic_integration': True}
)
```

#### 2. 日次統計の計算
```python
# 指定日の統計を計算
stats = monitor.calculate_daily_stats('2025-11-17')
print(f"1着的中率: {stats['hit_rate_1st']:.2%}")
print(f"3連単的中率: {stats['hit_rate_top3']:.2%}")
```

#### 3. パフォーマンス推移の取得
```python
# 過去30日間の推移を取得
trend = monitor.get_performance_trend(days=30)
for day in trend:
    print(f"{day['date']}: 1着的中率 {day['hit_rate_1st']:.2%}")
```

#### 4. アラート検知
```python
# アラート条件をチェック
alerts = monitor.check_alerts(date='2025-11-17', stats=stats)
for alert in alerts:
    print(f"[{alert['alert_type']}] {alert['message']}")
```

**アラート閾値:**
- 1着的中率 < 15%
- 3連単的中率 < 5%
- スコア精度 < 0.6
- 評価レース数 < 10

#### 5. レポート生成
```python
# 過去7日間のレポートを生成
monitor.generate_report(days=7, output_path='temp/monitor/report.txt')
```

### データベース構造

モニタリング用のSQLiteデータベース (`data/monitor.db`) に3つのテーブルを作成:

1. **daily_performance**: 日次パフォーマンス統計
2. **race_predictions**: レース単位の予測ログ
3. **alerts**: アラート履歴

---

## 3. Gradual Rollout System

### 目的
新機能を段階的に導入 (10% → 50% → 100%) するA/Bテストシステム。リスクを最小化しながら、安全に機能をロールアウトします。

### ファイル
- [src/deployment/gradual_rollout.py](../src/deployment/gradual_rollout.py)
- [test_gradual_rollout.py](../test_gradual_rollout.py) (テストスクリプト)

### 主な機能

#### 1. 機能の有効化判定
```python
from src.deployment.gradual_rollout import GradualRollout

rollout = GradualRollout()

# レースIDに基づいて機能を有効化すべきか判定
if rollout.should_enable_feature('probability_calibration', race_id):
    # 新機能を使用
    pass
else:
    # レガシー処理
    pass
```

**特徴:**
- **ハッシュベース**: race_idのMD5ハッシュを使用
- **決定的**: 同じrace_idは常に同じ判定結果
- **均等分散**: 0-99のバケットに均等に割り当て

#### 2. ステージの更新
```python
# ステージを更新
rollout.update_rollout_stage('probability_calibration', '10%')  # 10%で試験運用
rollout.update_rollout_stage('probability_calibration', '50%')  # 50%に拡大
rollout.update_rollout_stage('probability_calibration', '100%') # 全展開
```

**利用可能なステージ:**
- `disabled`: 無効
- `10%`: 10%のレースで有効
- `50%`: 50%のレースで有効
- `100%`: 全レースで有効

#### 3. 健全性チェック
```python
# パフォーマンスメトリクスで健全性をチェック
metrics = {
    'hit_rate_1st': 0.25,
    'hit_rate_top3': 0.10,
    'avg_score_accuracy': 0.70,
    'error_rate': 0.02,
}

result = rollout.check_rollout_health('probability_calibration', metrics)
print(f"ステータス: {result['status']}")  # HEALTHY, WARNING, CRITICAL
print(f"アクション: {result['action']}")
```

**健全性判定基準:**

| 指標 | 正常 | 警告 | クリティカル |
|------|------|------|--------------|
| 1着的中率 | ≥20% | 15-20% | <15% |
| 3連単的中率 | ≥5% | - | <5% |
| スコア精度 | ≥0.65 | 0.60-0.65 | <0.60 |
| エラー率 | <10% | - | ≥10% |

**ステータス:**
- `HEALTHY`: 次のステージへ進行可能
- `WARNING`: 継続モニタリング
- `CRITICAL`: ロールバック推奨

#### 4. ロールアウト計画の取得
```python
# ロールアウト計画を表示
plan = rollout.rollout_plan('probability_calibration')
for stage in plan['stages']:
    print(f"{stage['stage']}: {stage['description']}")
```

#### 5. ロールアウト状況の確認
```python
# 全機能の状況を確認
status = rollout.get_rollout_status()
for feature, info in status['feature_rollouts'].items():
    print(f"{feature}: {info['stage']}")
```

### 設定ファイル

設定は `config/rollout_config.json` に保存されます:

```json
{
  "feature_rollouts": {
    "dynamic_integration": {
      "stage": "100%",
      "enabled_at": "2025-11-01"
    },
    "entry_prediction_model": {
      "stage": "100%",
      "enabled_at": "2025-11-15"
    },
    "probability_calibration": {
      "stage": "disabled",
      "enabled_at": null
    }
  },
  "updated_at": "2025-12-02 16:12:02"
}
```

### 使用例

```bash
python test_gradual_rollout.py
```

**出力例:**
```
【ステージ別有効化率テスト】

ステージ: disabled
  有効化レース数: 0/100
  実際の有効化率: 0.0%

ステージ: 10%
  有効化レース数: 13/100
  実際の有効化率: 13.0%

ステージ: 50%
  有効化レース数: 52/100
  実際の有効化率: 52.0%

ステージ: 100%
  有効化レース数: 100/100
  実際の有効化率: 100.0%
```

---

## 統合ワークフロー

### ステップ1: Walk-forward Backtestで検証

```bash
# 新機能の効果を時系列考慮で検証
python test_walkforward.py
```

### ステップ2: 段階的導入開始

```python
# 10%で試験運用
rollout = GradualRollout()
rollout.update_rollout_stage('probability_calibration', '10%')
```

### ステップ3: モニタリング開始

```python
# 日次でパフォーマンスを記録
monitor = PerformanceMonitor()

# 各レース後に記録
monitor.log_prediction(race_id, race_date, ...)

# 日次統計を計算
stats = monitor.calculate_daily_stats('2025-12-02')

# 健全性チェック
result = rollout.check_rollout_health('probability_calibration', {
    'hit_rate_1st': stats['hit_rate_1st'],
    'hit_rate_top3': stats['hit_rate_top3'],
    'avg_score_accuracy': stats['avg_score_accuracy'],
    'error_rate': 0.0,
})
```

### ステップ4: 段階的拡大

```python
# 1週間問題なければ50%に拡大
if result['status'] == 'HEALTHY':
    rollout.update_rollout_stage('probability_calibration', '50%')

# さらに1週間問題なければ100%に
if result['status'] == 'HEALTHY':
    rollout.update_rollout_stage('probability_calibration', '100%')
```

### ステップ5: 問題発生時はロールバック

```python
# 問題が検出された場合
if result['status'] == 'CRITICAL':
    rollout.update_rollout_stage('probability_calibration', 'disabled')
    print("ロールバックしました")
```

---

## テスト結果

### 段階的導入システムのテスト

```bash
python test_gradual_rollout.py
```

**結果:**
- ✅ ステージ別有効化率テスト: 成功
- ✅ ハッシュ一貫性テスト: 成功
- ✅ 健全性チェックテスト: 成功
- ✅ ロールアウト状況確認: 成功

---

## 実装完了状況

| システム | ファイル | テスト | 状態 |
|---------|----------|--------|------|
| Walk-forward Backtest | `src/evaluation/walkforward_backtest.py` | `test_walkforward.py` | ✅ 完了 |
| Performance Monitor | `src/monitoring/performance_monitor.py` | - | ✅ 完了 |
| Gradual Rollout | `src/deployment/gradual_rollout.py` | `test_gradual_rollout.py` | ✅ 完了 |

---

## 今後の拡張

### 1. UIダッシュボード
- Streamlitでモニタリングダッシュボードを作成
- リアルタイムで精度推移を可視化
- アラートをWeb UIで確認

### 2. 自動ロールバック
- 健全性チェックが`CRITICAL`の場合、自動的にロールバック
- Slack/Email通知の統合

### 3. マルチバリアントテスト
- 2つ以上のバージョンを同時にテスト
- 統計的有意性検定を実装

---

## まとめ

3つのシステムを実装することで、以下が実現されました:

1. **時系列考慮の正確な評価** (Walk-forward Backtest)
2. **リアルタイムモニタリング** (Performance Monitor)
3. **安全な段階的導入** (Gradual Rollout)

これにより、新機能を**低リスク**で導入し、**継続的に品質を監視**できる体制が整いました。
