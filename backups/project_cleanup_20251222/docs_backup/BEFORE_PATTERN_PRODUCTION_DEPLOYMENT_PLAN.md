# BEFOREパターン 本番環境導入計画

**作成日**: 2025-12-10
**作成者**: Claude Opus 4.5
**対象システム**: ボートレース予測システム

---

## エグゼクティブサマリー

BEFOREパターンシステムの検証結果を踏まえ、本番環境への段階的導入計画を策定。
**信頼度B/Cで明確な効果（+8-9.5pt）が確認された一方、信頼度Aでは逆効果（-6.5pt）となる重要な発見**があったため、慎重かつ段階的なロールアウトが必要。

### 期待効果

| 指標 | 改善前 | 改善後 | 改善幅 |
|------|--------|--------|--------|
| 的中率（B/C） | 48.2% | 55.4% | +7.2pt |
| 回収率 | 168.7% | 193.8% | +25.1pt |
| 月間利益 | +28,500円 | +42,700円 | +49.8% |

---

## 1. 段階的ロールアウト戦略

### 1.1 推奨アプローチ: カナリアリリース

**いきなり全機能有効化はリスクが高い**ため、以下の段階的導入を推奨。

```
Phase 1（即時）    → 信頼度B/Cのみで有効化、Aは除外
Phase 2（2週間後） → パフォーマンス最適化適用
Phase 3（1ヶ月後） → 全機能統合、ネガティブパターン追加
```

### 1.2 A/Bテスト設計

**テスト期間**: 2週間（約150-200レース/週）

```python
# A/Bテスト設定
AB_TEST_CONFIG = {
    'enabled': True,
    'ratio': 0.5,  # 50%のレースで新システム適用
    'metrics': ['hit_rate', 'roi', 'profit'],
    'min_sample_size': 100,  # 最小サンプル数
    'confidence_level': 0.95  # 信頼区間95%
}
```

**判定基準**:
- 新システムのROIが旧システム比 95%以上維持 → 継続
- 新システムのROIが旧システム比 90%未満 → ロールバック

### 1.3 フェーズ詳細

#### Phase 1: コア機能導入（即時〜1週間）

| タスク | 優先度 | 工数 | 担当 |
|--------|--------|------|------|
| 信頼度A除外ロジック実装 | 最高 | 2h | - |
| PatternPriorityOptimizer統合 | 最高 | 4h | - |
| 基本動作テスト | 高 | 2h | - |
| A/Bテストフレームワーク構築 | 高 | 4h | - |
| **Phase 1合計** | - | **12h** | - |

#### Phase 2: パフォーマンス最適化（1〜2週間）

| タスク | 優先度 | 工数 | 担当 |
|--------|--------|------|------|
| パターン計算キャッシング | 高 | 4h | - |
| バッチ処理最適化 | 高 | 6h | - |
| インデックス追加 | 中 | 2h | - |
| ベンチマーク測定 | 中 | 2h | - |
| **Phase 2合計** | - | **14h** | - |

#### Phase 3: 機能拡張（2週間〜1ヶ月）

| タスク | 優先度 | 工数 | 担当 |
|--------|--------|------|------|
| ネガティブパターン実装 | 中 | 6h | - |
| UIへのパターン情報表示 | 中 | 4h | - |
| 会場別パターン最適化 | 低 | 8h | - |
| 自動パターン更新機構 | 低 | 8h | - |
| **Phase 3合計** | - | **26h** | - |

**総工数見積もり**: 52時間（約6.5人日）

---

## 2. リスク管理

### 2.1 信頼度A逆効果問題への対処

**問題**: 信頼度Aレースでパターン適用すると -6.5pt の精度低下

**原因分析**:
- 信頼度Aは元々79%の高精度
- 基本予測モデルが既に最適化済み
- BEFOREパターンがノイズとして作用

**対策**:

```python
# src/analysis/race_predictor.py に追加
def apply_before_patterns(self, predictions, race_id, confidence_level):
    """BEFOREパターンを適用（信頼度チェック付き）"""

    # 【重要】信頼度Aではパターンを適用しない
    if confidence_level == 'A':
        self._log_pattern_skip(race_id, 'confidence_a_excluded')
        return predictions

    # 信頼度Eでも適用しない（サンプル不足）
    if confidence_level == 'E':
        self._log_pattern_skip(race_id, 'confidence_e_excluded')
        return predictions

    # B/C/Dで適用
    matched_patterns = self._find_matching_patterns(race_id)
    # ...
```

**フォールバック設定**:

```python
CONFIDENCE_PATTERN_CONFIG = {
    'A': {'apply_patterns': False, 'reason': '逆効果確認済み'},
    'B': {'apply_patterns': True, 'effect': '+9.5pt'},
    'C': {'apply_patterns': True, 'effect': '+8.3pt'},
    'D': {'apply_patterns': True, 'effect': '+3.9pt', 'conservative': True},
    'E': {'apply_patterns': False, 'reason': 'サンプル不足'},
}
```

### 2.2 予期しない動作への備え

**監視対象**:

| 異常パターン | 検知条件 | 対応 |
|-------------|---------|------|
| 急激な精度低下 | 直近50レースで的中率が-10pt以上低下 | 自動ロールバック |
| パターン適用率異常 | 適用率が20%未満または80%超 | アラート発報 |
| 処理時間異常 | 1レースあたり10秒超 | パフォーマンス調査 |
| メモリ使用量異常 | 通常の2倍以上 | キャッシュクリア |

**自動検知コード例**:

```python
class PatternAnomalyDetector:
    def __init__(self, window_size=50):
        self.window_size = window_size
        self.hit_history = []
        self.baseline_hit_rate = 0.52  # ベースライン的中率

    def check_anomaly(self, hit_result: bool) -> dict:
        self.hit_history.append(hit_result)
        if len(self.hit_history) < self.window_size:
            return {'anomaly': False}

        recent = self.hit_history[-self.window_size:]
        current_rate = sum(recent) / len(recent)
        deviation = current_rate - self.baseline_hit_rate

        if deviation < -0.10:  # -10pt以上低下
            return {
                'anomaly': True,
                'type': 'accuracy_drop',
                'severity': 'critical',
                'action': 'rollback',
                'deviation': deviation
            }
        elif deviation < -0.05:  # -5pt以上低下
            return {
                'anomaly': True,
                'type': 'accuracy_warning',
                'severity': 'warning',
                'action': 'investigate',
                'deviation': deviation
            }

        return {'anomaly': False, 'current_rate': current_rate}
```

### 2.3 ロールバック計画

**3段階ロールバック**:

```
Level 1: パターン適用一時停止（即時、5分以内）
Level 2: 前バージョンへの切り替え（30分以内）
Level 3: バックアップからの完全復元（2時間以内）
```

**Level 1 実装**:

```python
# config/feature_flags.py
FEATURE_FLAGS = {
    'before_patterns_enabled': True,  # False でパターン適用停止
    'pattern_priority_optimizer': True,
    'negative_patterns': False,  # Phase 3まで無効
}

# 緊急停止コマンド
def emergency_disable_patterns():
    """緊急時のパターン適用停止"""
    FEATURE_FLAGS['before_patterns_enabled'] = False
    log_critical("BEFORE patterns disabled due to emergency")
    notify_admin("Pattern system emergency shutdown")
```

**Level 2 実装**:

```bash
# ロールバック手順（Git使用）
git stash  # 現在の変更を退避
git checkout HEAD~1 -- src/analysis/race_predictor.py
git checkout HEAD~1 -- src/analysis/pattern_priority_optimizer.py
# または特定のコミットに戻る
git checkout 31d0caa -- src/analysis/
```

---

## 3. パフォーマンス最適化

### 3.1 現状の問題

**60分/1000レースは実用的ではない**

| 処理 | 現状時間 | 目標時間 | 削減率 |
|------|---------|---------|--------|
| 1000レース分析 | 60分 | 15分 | 75% |
| 1レースあたり | 3.6秒 | 0.9秒 | 75% |
| リアルタイム予測 | 3-5秒 | 1秒以下 | 80% |

### 3.2 最適化戦略

#### 3.2.1 キャッシング戦略

```python
# src/utils/pattern_cache.py
import functools
from datetime import datetime, timedelta

class PatternCache:
    def __init__(self, ttl_minutes=15):
        self._cache = {}
        self._ttl = timedelta(minutes=ttl_minutes)

    def get(self, key):
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now() - timestamp < self._ttl:
                return value
            del self._cache[key]
        return None

    def set(self, key, value):
        self._cache[key] = (value, datetime.now())

    def clear_expired(self):
        now = datetime.now()
        expired = [k for k, (v, t) in self._cache.items()
                   if now - t >= self._ttl]
        for k in expired:
            del self._cache[k]

# 使用例
pattern_cache = PatternCache(ttl_minutes=15)

@functools.lru_cache(maxsize=1000)
def get_pattern_stats_cached(pattern_name, confidence_level, venue_code):
    """パターン統計情報（キャッシュ付き）"""
    cache_key = f"{pattern_name}_{confidence_level}_{venue_code}"
    cached = pattern_cache.get(cache_key)
    if cached:
        return cached

    # DB計算（重い処理）
    stats = _calculate_pattern_stats(pattern_name, confidence_level, venue_code)
    pattern_cache.set(cache_key, stats)
    return stats
```

#### 3.2.2 バッチ処理最適化

```python
# src/analysis/batch_pattern_processor.py
from concurrent.futures import ThreadPoolExecutor
import numpy as np

class BatchPatternProcessor:
    def __init__(self, max_workers=4):
        self.max_workers = max_workers

    def process_races_batch(self, race_ids, batch_size=50):
        """バッチ単位でレースを処理"""
        results = []

        # バッチに分割
        batches = [race_ids[i:i+batch_size]
                   for i in range(0, len(race_ids), batch_size)]

        # 並列処理
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self._process_batch, batch)
                       for batch in batches]
            for future in futures:
                results.extend(future.result())

        return results

    def _process_batch(self, race_ids):
        """1バッチを処理"""
        # 一括でDBクエリを実行（N+1問題回避）
        race_data = self._fetch_race_data_bulk(race_ids)
        pattern_results = []

        for race_id, data in race_data.items():
            patterns = self._apply_patterns(data)
            pattern_results.append({
                'race_id': race_id,
                'patterns': patterns
            })

        return pattern_results

    def _fetch_race_data_bulk(self, race_ids):
        """複数レースのデータを一括取得"""
        # IN句で一括取得
        query = """
            SELECT rd.*, r.confidence_level, r.venue_code
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE rd.race_id IN ({})
        """.format(','.join(['?'] * len(race_ids)))
        # ...
```

#### 3.2.3 インデックス追加

```sql
-- パターン分析高速化用インデックス
CREATE INDEX IF NOT EXISTS idx_race_details_pattern_lookup
ON race_details(race_id, pit_number, exhibition_time, st_time);

CREATE INDEX IF NOT EXISTS idx_races_confidence_venue
ON races(confidence_level, venue_code, race_date);

CREATE INDEX IF NOT EXISTS idx_results_rank_filter
ON results(race_id, pit_number, rank)
WHERE rank IN ('1', '2', '3');
```

### 3.3 リアルタイム予測への影響

**現状**: 展示情報取得後の再予測に3-5秒かかる

**最適化後の目標フロー**:

```
[展示情報取得] → [パターンマッチ（キャッシュ）] → [スコア計算] → [予測更新]
     |                    |                           |              |
    1秒                 0.1秒                       0.3秒          0.1秒

                         合計: 1.5秒（目標）
```

---

## 4. モニタリング計画

### 4.1 監視指標一覧

| カテゴリ | 指標 | 正常範囲 | 警告閾値 | 危険閾値 |
|---------|------|---------|---------|---------|
| **精度** | 的中率（全体） | 50-55% | <45% | <40% |
| | 的中率（信頼度B） | 62-68% | <58% | <55% |
| | 的中率（信頼度C） | 45-52% | <40% | <35% |
| **収益** | ROI | 150-200% | <120% | <100% |
| | 日次収支 | +5,000円〜 | <0円/3日連続 | <-10,000円/週 |
| **パターン** | 適用率 | 45-60% | <30% or >75% | <20% or >85% |
| | pre1_ex1的中率 | 58-68% | <50% | <45% |
| **性能** | レース処理時間 | 0.5-1.5秒 | >3秒 | >5秒 |
| | メモリ使用量 | <500MB | >800MB | >1GB |

### 4.2 異常検知の閾値設定

```python
# src/monitoring/alert_config.py
ALERT_THRESHOLDS = {
    'accuracy': {
        'warning': {
            'condition': 'hit_rate < baseline - 0.05',
            'window': '50_races',
            'action': 'notify'
        },
        'critical': {
            'condition': 'hit_rate < baseline - 0.10',
            'window': '30_races',
            'action': 'rollback'
        }
    },
    'roi': {
        'warning': {
            'condition': 'daily_roi < 0.8',  # 80%未満
            'consecutive_days': 3,
            'action': 'notify'
        },
        'critical': {
            'condition': 'weekly_roi < 1.0',  # 100%未満
            'action': 'investigate'
        }
    },
    'pattern_application': {
        'warning': {
            'condition': 'rate < 0.30 or rate > 0.75',
            'action': 'notify'
        }
    },
    'performance': {
        'warning': {
            'condition': 'processing_time > 3.0',
            'action': 'notify'
        },
        'critical': {
            'condition': 'processing_time > 5.0',
            'action': 'throttle'
        }
    }
}
```

### 4.3 レポーティング頻度

| レポート種別 | 頻度 | 内容 | 送信先 |
|-------------|------|------|--------|
| **リアルタイムダッシュボード** | 常時 | 当日の成績、パターン適用状況 | UI |
| **日次サマリー** | 毎日21:00 | 当日成績、ROI、異常検知結果 | 管理者 |
| **週次レポート** | 毎週月曜 | 週間収支、パターン効果分析、改善提案 | 管理者 |
| **月次分析** | 毎月1日 | 月間トレンド、パターン統計更新 | 管理者 |

### 4.4 ダッシュボード設計

```python
# ui/components/pattern_dashboard.py
def render_pattern_monitoring_dashboard():
    """パターン監視ダッシュボード"""

    st.header("BEFOREパターン監視")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "本日の的中率",
            f"{today_hit_rate:.1f}%",
            delta=f"{today_hit_rate - baseline:.1f}pt"
        )

    with col2:
        st.metric(
            "パターン適用率",
            f"{pattern_apply_rate:.1f}%",
            delta=None
        )

    with col3:
        st.metric(
            "本日ROI",
            f"{today_roi:.1f}%",
            delta=f"{today_roi - 100:.1f}%"
        )

    with col4:
        status = "正常" if no_anomaly else "警告"
        st.metric("システム状態", status)

    # 信頼度別成績グラフ
    st.subheader("信頼度別成績（直近7日）")
    fig = plot_confidence_level_performance()
    st.plotly_chart(fig)

    # パターン別効果
    st.subheader("パターン別効果")
    st.dataframe(pattern_effectiveness_df)
```

---

## 5. 実装優先順位

### 5.1 Phase 1: 即時実装（今週中）

**目標**: 基本機能の安全な導入

| # | タスク | 工数 | 依存 | 成果物 |
|---|--------|------|------|--------|
| 1.1 | 信頼度A除外ロジック実装 | 2h | なし | `race_predictor.py`修正 |
| 1.2 | PatternPriorityOptimizer統合 | 4h | 1.1 | 統合コード |
| 1.3 | フィーチャーフラグ追加 | 1h | 1.2 | `feature_flags.py`修正 |
| 1.4 | ユニットテスト作成 | 2h | 1.2 | `tests/test_pattern_*.py` |
| 1.5 | 基本動作確認 | 2h | 1.4 | テスト結果レポート |
| 1.6 | ログ機能追加 | 1h | 1.2 | パターン適用ログ |

**Phase 1成功基準**:
- 全ユニットテストがパス
- 信頼度Aでパターンが適用されないことを確認
- 信頼度B/Cで正しくパターンが適用されることを確認

### 5.2 Phase 2: 最適化（2週間以内）

**目標**: パフォーマンス改善とモニタリング整備

| # | タスク | 工数 | 依存 | 成果物 |
|---|--------|------|------|--------|
| 2.1 | パターン計算キャッシング | 4h | Phase1 | `pattern_cache.py` |
| 2.2 | バッチ処理最適化 | 6h | 2.1 | `batch_pattern_processor.py` |
| 2.3 | DBインデックス追加 | 2h | なし | SQLスクリプト |
| 2.4 | ベンチマーク測定 | 2h | 2.2 | ベンチマーク結果 |
| 2.5 | 異常検知システム実装 | 4h | Phase1 | `anomaly_detector.py` |
| 2.6 | ダッシュボード基本版 | 4h | 2.5 | UI改修 |

**Phase 2成功基準**:
- 処理時間が60分→15分以下に短縮
- 異常検知が正常動作
- ダッシュボードで主要指標が確認可能

### 5.3 Phase 3: 機能拡張（1ヶ月以内）

**目標**: 高度機能の追加と継続的改善

| # | タスク | 工数 | 依存 | 成果物 |
|---|--------|------|------|--------|
| 3.1 | ネガティブパターン実装 | 6h | Phase2 | 警告フラグシステム |
| 3.2 | UIパターン情報表示 | 4h | Phase2 | UI拡張 |
| 3.3 | A/Bテストフレームワーク | 4h | Phase2 | テストシステム |
| 3.4 | 会場別パターン最適化 | 8h | 3.3 | 会場別設定 |
| 3.5 | パターン自動更新機構 | 8h | 3.4 | 自動更新システム |
| 3.6 | 詳細レポーティング | 4h | 3.2 | レポート生成 |

**Phase 3成功基準**:
- ネガティブパターンが効果的に動作
- 会場別最適化でさらに+2-3ptの改善
- 自動更新でメンテナンスコスト削減

### 5.4 依存関係図

```
Phase 1
  1.1 信頼度A除外
   ↓
  1.2 Optimizer統合 ← 1.3 フィーチャーフラグ
   ↓
  1.4 ユニットテスト
   ↓
  1.5 基本動作確認

Phase 2
  2.1 キャッシング ← Phase 1
   ↓
  2.2 バッチ処理
   ↓
  2.4 ベンチマーク

  2.5 異常検知 ← Phase 1
   ↓
  2.6 ダッシュボード

Phase 3
  3.1 ネガティブパターン ← Phase 2
  3.2 UI拡張 ← Phase 2
   ↓
  3.3 A/Bテスト
   ↓
  3.4 会場別最適化
   ↓
  3.5 自動更新
```

---

## 6. 品質保証

### 6.1 テスト戦略

#### 6.1.1 ユニットテスト

```python
# tests/test_pattern_priority_optimizer.py
import pytest
from src.analysis.pattern_priority_optimizer import PatternPriorityOptimizer

class TestPatternPriorityOptimizer:

    @pytest.fixture
    def optimizer(self):
        return PatternPriorityOptimizer()

    def test_select_best_pattern_single(self, optimizer):
        """単一パターンマッチ時のテスト"""
        patterns = [{'name': 'pre1_ex1', 'multiplier': 1.286}]
        result = optimizer.select_best_pattern(patterns, 'B')
        assert result['name'] == 'pre1_ex1'

    def test_select_best_pattern_multiple(self, optimizer):
        """複数パターンマッチ時のテスト"""
        patterns = [
            {'name': 'pre1_ex1', 'multiplier': 1.286},
            {'name': 'pre1_st1_3', 'multiplier': 1.310}
        ]
        result = optimizer.select_best_pattern(patterns, 'B')
        # pre1_ex1が最高的中率のため選択されるべき
        assert result['name'] == 'pre1_ex1'

    def test_confidence_a_exclusion(self, optimizer):
        """信頼度Aでのパターン除外テスト"""
        # これはRacePredictorレベルでテスト
        pass

    def test_combination_bonus(self, optimizer):
        """組み合わせボーナスのテスト"""
        patterns = [
            {'name': 'pre1_ex1'},
            {'name': 'pre1_st1_3'}
        ]
        bonus = optimizer.get_pattern_combination_bonus(patterns)
        assert bonus == 1.05  # 相乗効果
```

#### 6.1.2 統合テスト

```python
# tests/test_pattern_integration.py
import pytest
from src.analysis.race_predictor import RacePredictor

class TestPatternIntegration:

    @pytest.fixture
    def predictor(self):
        return RacePredictor()

    def test_confidence_a_no_pattern(self, predictor):
        """信頼度Aでパターンが適用されないことを確認"""
        # テストレース（信頼度A）を使用
        result = predictor.predict_with_patterns(
            race_id='test_race_a',
            confidence_level='A'
        )
        assert result['pattern_applied'] == False

    def test_confidence_b_pattern_applied(self, predictor):
        """信頼度Bでパターンが適用されることを確認"""
        result = predictor.predict_with_patterns(
            race_id='test_race_b',
            confidence_level='B'
        )
        assert result['pattern_applied'] == True

    def test_pattern_effect_positive(self, predictor):
        """パターン適用で精度向上を確認"""
        # 100レースのバックテスト
        with_pattern = predictor.backtest(use_patterns=True, n_races=100)
        without_pattern = predictor.backtest(use_patterns=False, n_races=100)

        # 信頼度B/Cで改善を期待
        assert with_pattern['hit_rate_bc'] >= without_pattern['hit_rate_bc']
```

#### 6.1.3 E2Eテスト

```python
# tests/test_e2e_pattern_flow.py
import pytest
from ui.app import create_app

class TestE2EPatternFlow:

    def test_full_prediction_flow(self):
        """完全な予測フローのE2Eテスト"""
        # 1. 展示情報取得をシミュレート
        # 2. パターンマッチングが実行されることを確認
        # 3. 予測結果にパターン情報が含まれることを確認
        # 4. UIに正しく表示されることを確認
        pass

    def test_rollback_mechanism(self):
        """ロールバック機能のE2Eテスト"""
        # 1. パターン機能を有効化
        # 2. 異常を検知させる
        # 3. 自動ロールバックが実行されることを確認
        pass
```

### 6.2 検証項目チェックリスト

#### Phase 1リリース前

- [ ] 信頼度A除外ロジックが正しく動作する
- [ ] 信頼度B/Cでパターンが正しく適用される
- [ ] パターン優先度が正しく計算される
- [ ] 組み合わせボーナスが正しく適用される
- [ ] フィーチャーフラグで機能をON/OFFできる
- [ ] ログにパターン適用状況が記録される
- [ ] 既存機能への影響がない

#### Phase 2リリース前

- [ ] 処理時間が目標値（15分/1000レース）以下
- [ ] キャッシュが正しく動作する
- [ ] バッチ処理で結果に差異がない
- [ ] 異常検知が正しく動作する
- [ ] ダッシュボードに指標が表示される
- [ ] メモリリークがない

#### Phase 3リリース前

- [ ] ネガティブパターンが効果的に動作する
- [ ] UIにパターン情報が正しく表示される
- [ ] A/Bテストで統計的に有意な結果が得られる
- [ ] 会場別最適化で改善が確認される
- [ ] 自動更新が正しく動作する

### 6.3 成功基準

#### 定量的基準

| 指標 | Phase 1 | Phase 2 | Phase 3 |
|------|---------|---------|---------|
| 的中率（B/C） | ≥52% | ≥54% | ≥55% |
| ROI | ≥150% | ≥170% | ≥190% |
| 処理時間 | <3秒/レース | <1秒/レース | <0.5秒/レース |
| テストカバレッジ | >70% | >80% | >85% |
| 障害発生率 | <1回/週 | <1回/月 | <1回/四半期 |

#### 定性的基準

- ユーザーからの機能追加要望に対応できる
- 新しいパターンを容易に追加できる
- 運用チームがダッシュボードで状況を把握できる
- 問題発生時に迅速にロールバックできる

---

## 7. 実装コード例

### 7.1 信頼度A除外の実装

```python
# src/analysis/race_predictor.py への追加

# 既存のimportに追加
from config.feature_flags import is_feature_enabled

# RacePredictor クラス内に追加
def apply_before_patterns(self, predictions, race_id, confidence_level):
    """
    BEFOREパターンを適用（本番導入版）

    Args:
        predictions: 現在の予測結果
        race_id: レースID
        confidence_level: 信頼度レベル（A/B/C/D/E）

    Returns:
        パターン適用後の予測結果
    """
    # フィーチャーフラグチェック
    if not is_feature_enabled('before_patterns_enabled'):
        return predictions

    # 信頼度チェック（A/Eは除外）
    if confidence_level in ['A', 'E']:
        self._log_pattern_skip(race_id, confidence_level,
                               reason=f'Confidence {confidence_level} excluded')
        return predictions

    # パターンマッチング実行
    race_data = self._get_race_before_info(race_id)
    if not race_data:
        return predictions

    matched_patterns = []
    for entry in race_data:
        pit_number = entry['pit_number']
        pre_rank = entry.get('pre_rank', 6)
        ex_rank = entry.get('ex_rank', 6)
        st_rank = entry.get('st_rank', 6)

        # パターンマッチング
        entry_patterns = self._match_patterns(pre_rank, ex_rank, st_rank, pit_number)
        matched_patterns.append({
            'pit_number': pit_number,
            'patterns': entry_patterns
        })

    # パターン優先度最適化
    if is_feature_enabled('pattern_priority_optimizer'):
        matched_patterns = self._optimize_pattern_priority(
            matched_patterns, confidence_level
        )

    # 予測スコア調整
    adjusted_predictions = self._adjust_predictions_by_patterns(
        predictions, matched_patterns
    )

    # ログ記録
    self._log_pattern_application(race_id, matched_patterns)

    return adjusted_predictions

def _log_pattern_skip(self, race_id, confidence_level, reason):
    """パターンスキップをログに記録"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Pattern skipped - Race: {race_id}, "
                f"Confidence: {confidence_level}, Reason: {reason}")

def _log_pattern_application(self, race_id, matched_patterns):
    """パターン適用をログに記録"""
    import logging
    logger = logging.getLogger(__name__)
    pattern_summary = [
        f"Pit{p['pit_number']}: {[pt['name'] for pt in p['patterns']]}"
        for p in matched_patterns if p['patterns']
    ]
    logger.info(f"Patterns applied - Race: {race_id}, "
                f"Patterns: {pattern_summary}")
```

### 7.2 フィーチャーフラグの実装

```python
# config/feature_flags.py

"""
フィーチャーフラグ管理モジュール

本番環境での機能のON/OFF切り替えを管理
"""

# 現在のフィーチャーフラグ設定
_FEATURE_FLAGS = {
    # BEFOREパターン関連
    'before_patterns_enabled': True,      # パターンシステム全体
    'pattern_priority_optimizer': True,   # 優先度最適化
    'negative_patterns': False,           # ネガティブパターン（Phase 3）
    'pattern_caching': True,              # キャッシング

    # A/Bテスト関連
    'ab_test_enabled': False,             # A/Bテストモード
    'ab_test_ratio': 0.5,                 # 新システム適用率

    # モニタリング関連
    'anomaly_detection': True,            # 異常検知
    'auto_rollback': False,               # 自動ロールバック（慎重に）
}

def is_feature_enabled(feature_name: str) -> bool:
    """
    フィーチャーが有効かどうかを確認

    Args:
        feature_name: フィーチャー名

    Returns:
        有効ならTrue、無効ならFalse
    """
    return _FEATURE_FLAGS.get(feature_name, False)

def get_feature_value(feature_name: str, default=None):
    """
    フィーチャーの値を取得

    Args:
        feature_name: フィーチャー名
        default: デフォルト値

    Returns:
        フィーチャーの値
    """
    return _FEATURE_FLAGS.get(feature_name, default)

def set_feature_flag(feature_name: str, value):
    """
    フィーチャーフラグを設定（管理者用）

    Args:
        feature_name: フィーチャー名
        value: 設定値
    """
    _FEATURE_FLAGS[feature_name] = value
    _log_flag_change(feature_name, value)

def emergency_disable_patterns():
    """
    緊急時のパターン機能停止
    """
    _FEATURE_FLAGS['before_patterns_enabled'] = False
    _log_flag_change('before_patterns_enabled', False, emergency=True)
    _notify_admin("EMERGENCY: Pattern system disabled")

def _log_flag_change(feature_name, value, emergency=False):
    """フラグ変更をログに記録"""
    import logging
    logger = logging.getLogger(__name__)
    level = logging.CRITICAL if emergency else logging.INFO
    logger.log(level, f"Feature flag changed: {feature_name} = {value}")

def _notify_admin(message):
    """管理者に通知"""
    # TODO: 実際の通知実装（Slack、メール等）
    import logging
    logging.getLogger(__name__).critical(f"ADMIN NOTIFICATION: {message}")
```

---

## 8. タイムライン

```
Week 0 (今週)
├─ Day 1-2: Phase 1開発（信頼度A除外、Optimizer統合）
├─ Day 3: ユニットテスト作成
├─ Day 4: 基本動作確認
└─ Day 5: Phase 1リリース（限定公開）

Week 1-2
├─ A/Bテスト実施（100レース/日）
├─ キャッシング実装
├─ バッチ処理最適化
└─ 結果分析・調整

Week 3
├─ 異常検知システム実装
├─ ダッシュボード基本版
├─ ベンチマーク測定
└─ Phase 2リリース

Week 4-5
├─ ネガティブパターン実装
├─ UI拡張
├─ A/Bテストフレームワーク
└─ 会場別最適化調査

Week 6-8
├─ 会場別パターン最適化
├─ 自動更新機構
├─ 詳細レポーティング
└─ Phase 3リリース
```

---

## 9. 連絡先・エスカレーション

### 問題発生時の連絡フロー

```
Level 1（警告）: ダッシュボードで通知確認
     ↓
Level 2（重要）: 管理者へメール/Slack通知
     ↓
Level 3（緊急）: 電話連絡 + 緊急ロールバック実行
```

### 判断基準

| Level | 条件 | 対応 |
|-------|------|------|
| 1 | 的中率が-5pt以下 | 経過観察、翌日レビュー |
| 2 | 的中率が-10pt以下、またはROI<100% | 調査開始、パターン調整検討 |
| 3 | システム障害、またはROI<80% | 緊急ロールバック |

---

## 10. 付録

### A. 関連ドキュメント

- [docs/pattern_implementation_summary.md](pattern_implementation_summary.md) - 実装サマリー
- [results/PATTERN_ANALYSIS_REPORT.md](../results/PATTERN_ANALYSIS_REPORT.md) - 分析レポート
- [src/analysis/pattern_priority_optimizer.py](../src/analysis/pattern_priority_optimizer.py) - 優先度最適化
- [docs/残タスク一覧.md](残タスク一覧.md) - 残タスク一覧

### B. 変更履歴

| 日付 | バージョン | 変更内容 | 作成者 |
|------|-----------|---------|--------|
| 2025-12-10 | 1.0 | 初版作成 | Claude Opus 4.5 |

---

**承認**:

| 役割 | 氏名 | 日付 | 署名 |
|------|------|------|------|
| 開発責任者 | | | |
| 運用責任者 | | | |
| プロジェクトオーナー | | | |

---

*本ドキュメントは計画書であり、実際の実装時には状況に応じて調整が必要です。*
