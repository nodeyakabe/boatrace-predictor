# ボートレース予測システム 改善実装計画書

**作成日**: 2024年12月2日
**対象システム**: BoatRace_package_20251115_172032
**作成者**: Claude Code

---

## 目次

1. [現状分析サマリー](#1-現状分析サマリー)
2. [Phase 1: 高優先度改善（今すぐ実装）](#2-phase-1-高優先度改善今すぐ実装)
   - 2.1 動的合成比導入
   - 2.2 進入予測モデル追加
   - 2.3 直前情報信頼度スコアの明確化
3. [Phase 2: 中優先度改善（数週間以内）](#3-phase-2-中優先度改善数週間以内)
   - 3.1 複合バフの自動学習化
   - 3.2 信頼度の細分化
   - 3.3 キャリブレーション導入
4. [Phase 3: 低優先度改善（中長期）](#4-phase-3-低優先度改善中長期)
   - 4.1 会場別ベイズ階層モデル
   - 4.2 強化学習的買い目最適化
5. [検証・評価計画](#5-検証評価計画)
6. [リスク管理](#6-リスク管理)
7. [成果物リスト](#7-成果物リスト)

---

## 1. 現状分析サマリー

### 1.1 現在のシステム構造

| コンポーネント | ファイル | 概要 |
|--------------|---------|------|
| メインエンジン | `src/analysis/race_predictor.py` (1584行) | 総合予測スコア計算 |
| 直前情報スコアリング | `src/analysis/beforeinfo_scorer.py` (602行) | 直前情報の100点満点評価 |
| 複合バフシステム | `src/analysis/compound_buff_system.py` (716行) | 条件組み合わせバフ/デバフ |
| 拡張スコアラー | `src/analysis/extended_scorer.py` (1408行) | 追加予測要素 |
| 設定ファイル | `config/settings.py` (336行) | 重み設定・会場特性 |

### 1.2 現在の統合式

```python
# race_predictor.py line 1457
FINAL_SCORE = PRE_SCORE * 0.6 + BEFORE_SCORE * 0.4
```

**問題点**: 固定比率であり、日によって直前情報の重要度が変わる「偏差日」に対応できていない。

### 1.3 改善項目一覧

| 優先度 | 項目 | 現状 | 目標 |
|-------|------|------|------|
| **高** | 動的合成比 | 固定(0.6/0.4) | 条件別動的調整 |
| **高** | 進入予測モデル | ルールベースのみ | 確率モデル追加 |
| **高** | 信頼度スコア | 5段階(A-E) | 連続スコア化 |
| **中** | 複合バフ | 手動ルール | 自動学習化 |
| **中** | 信頼度細分化 | A-E | A1/A2/B/C/D/E |
| **中** | キャリブレーション | なし | 日次/週次 |
| **低** | 階層モデル | なし | 会場別ベイズ |
| **低** | 買い目最適化 | 固定ロジック | 強化学習 |

---

## 2. Phase 1: 高優先度改善（今すぐ実装）

### 2.1 動的合成比導入

**目的**: PRE_SCORE と BEFORE_SCORE の重みを条件に応じて動的に変える

#### 2.1.1 新規ファイル作成

**ファイル**: `src/analysis/dynamic_integration.py`

```python
"""
動的スコア統合モジュール

条件に応じてPRE_SCOREとBEFORE_SCOREの合成比を動的に調整する。
偏差日（直前情報の重要度が特に高い/低い日）に対応。
"""

from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import math


class IntegrationCondition(Enum):
    """統合条件タイプ"""
    NORMAL = "normal"           # 通常
    BEFOREINFO_CRITICAL = "before_critical"  # 直前情報重視
    PREINFO_RELIABLE = "pre_reliable"        # 事前情報重視
    UNCERTAIN = "uncertain"     # 不確実性高


@dataclass
class IntegrationWeights:
    """統合重み"""
    pre_weight: float      # PRE_SCOREの重み (0.0-1.0)
    before_weight: float   # BEFORE_SCOREの重み (0.0-1.0)
    condition: IntegrationCondition
    reason: str
    confidence: float      # この重み判断の信頼度


class DynamicIntegrator:
    """動的スコア統合クラス"""

    # デフォルト重み
    DEFAULT_PRE_WEIGHT = 0.6
    DEFAULT_BEFORE_WEIGHT = 0.4

    # 条件別重み設定
    CONDITION_WEIGHTS = {
        IntegrationCondition.NORMAL: (0.6, 0.4),
        IntegrationCondition.BEFOREINFO_CRITICAL: (0.4, 0.6),
        IntegrationCondition.PREINFO_RELIABLE: (0.75, 0.25),
        IntegrationCondition.UNCERTAIN: (0.5, 0.5),
    }

    # 直前情報重視の閾値
    EXHIBITION_VARIANCE_THRESHOLD = 0.15  # 展示タイム分散が高い
    ST_VARIANCE_THRESHOLD = 0.08          # ST分散が高い
    ENTRY_CHANGE_THRESHOLD = 2            # 進入変更艇数

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def determine_weights(
        self,
        race_id: int,
        beforeinfo_data: Dict,
        pre_predictions: list,
        venue_code: str,
        weather_data: Optional[Dict] = None
    ) -> IntegrationWeights:
        """
        レース状況に応じた動的重みを決定

        Args:
            race_id: レースID
            beforeinfo_data: 直前情報データ
            pre_predictions: 事前予測結果
            venue_code: 会場コード
            weather_data: 天候データ

        Returns:
            IntegrationWeights: 決定された重み
        """
        reasons = []
        condition = IntegrationCondition.NORMAL

        # 1. 展示タイムの分散をチェック
        exhibition_variance = self._calculate_exhibition_variance(beforeinfo_data)
        if exhibition_variance > self.EXHIBITION_VARIANCE_THRESHOLD:
            condition = IntegrationCondition.BEFOREINFO_CRITICAL
            reasons.append(f"展示タイム分散高({exhibition_variance:.3f})")

        # 2. STの分散をチェック
        st_variance = self._calculate_st_variance(beforeinfo_data)
        if st_variance > self.ST_VARIANCE_THRESHOLD:
            condition = IntegrationCondition.BEFOREINFO_CRITICAL
            reasons.append(f"ST分散高({st_variance:.3f})")

        # 3. 進入変更をチェック
        entry_changes = self._count_entry_changes(beforeinfo_data)
        if entry_changes >= self.ENTRY_CHANGE_THRESHOLD:
            condition = IntegrationCondition.BEFOREINFO_CRITICAL
            reasons.append(f"進入変更{entry_changes}艇")

        # 4. 事前予測の信頼度をチェック
        pre_confidence = self._evaluate_pre_confidence(pre_predictions)
        if pre_confidence > 0.85:
            # 事前予測が高信頼の場合は事前重視
            if condition == IntegrationCondition.NORMAL:
                condition = IntegrationCondition.PREINFO_RELIABLE
                reasons.append(f"事前予測高信頼({pre_confidence:.2f})")
        elif pre_confidence < 0.5:
            # 事前予測が低信頼の場合は直前情報重視
            condition = IntegrationCondition.BEFOREINFO_CRITICAL
            reasons.append(f"事前予測低信頼({pre_confidence:.2f})")

        # 5. 天候変化をチェック
        if weather_data:
            weather_impact = self._evaluate_weather_impact(weather_data)
            if weather_impact > 0.3:
                condition = IntegrationCondition.BEFOREINFO_CRITICAL
                reasons.append(f"天候変動大({weather_impact:.2f})")

        # 6. 直前情報のデータ充実度をチェック
        before_completeness = self._calculate_before_completeness(beforeinfo_data)
        if before_completeness < 0.5:
            # 直前情報不足の場合は事前重視
            condition = IntegrationCondition.PREINFO_RELIABLE
            reasons.append(f"直前情報不足({before_completeness:.2f})")

        # 重みを取得
        pre_w, before_w = self.CONDITION_WEIGHTS[condition]

        # データ充実度で微調整
        if before_completeness < 0.8:
            # 直前情報が不完全な場合、その分事前重みを上げる
            adjustment = (1.0 - before_completeness) * 0.2
            pre_w = min(0.85, pre_w + adjustment)
            before_w = max(0.15, before_w - adjustment)

        # 正規化
        total = pre_w + before_w
        pre_w /= total
        before_w /= total

        return IntegrationWeights(
            pre_weight=pre_w,
            before_weight=before_w,
            condition=condition,
            reason="; ".join(reasons) if reasons else "通常条件",
            confidence=min(pre_confidence, before_completeness)
        )

    def _calculate_exhibition_variance(self, beforeinfo_data: Dict) -> float:
        """展示タイムの分散を計算"""
        times = beforeinfo_data.get('exhibition_times', {})
        if len(times) < 4:
            return 0.0

        values = list(times.values())
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    def _calculate_st_variance(self, beforeinfo_data: Dict) -> float:
        """STの分散を計算"""
        timings = beforeinfo_data.get('start_timings', {})
        if len(timings) < 4:
            return 0.0

        values = [v for v in timings.values() if v >= 0]  # フライング除外
        if len(values) < 3:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    def _count_entry_changes(self, beforeinfo_data: Dict) -> int:
        """進入変更艇数をカウント"""
        courses = beforeinfo_data.get('exhibition_courses', {})
        changes = 0
        for pit, course in courses.items():
            if pit != course:
                changes += 1
        return changes

    def _evaluate_pre_confidence(self, predictions: list) -> float:
        """事前予測の信頼度を評価"""
        if not predictions:
            return 0.5

        # トップと2位のスコア差
        if len(predictions) >= 2:
            gap = predictions[0].get('total_score', 0) - predictions[1].get('total_score', 0)
            # ギャップが大きいほど信頼度高
            gap_factor = min(gap / 15.0, 1.0)  # 15点差で最大
        else:
            gap_factor = 0.5

        # 信頼度の分布
        confidence_map = {'A': 1.0, 'B': 0.8, 'C': 0.6, 'D': 0.4, 'E': 0.2}
        top_conf = confidence_map.get(predictions[0].get('confidence', 'C'), 0.6)

        return (gap_factor + top_conf) / 2

    def _evaluate_weather_impact(self, weather_data: Dict) -> float:
        """天候変化の影響度を評価"""
        impact = 0.0

        wind_speed = weather_data.get('wind_speed', 0)
        wave_height = weather_data.get('wave_height', 0)

        if wind_speed >= 6:
            impact += 0.3
        elif wind_speed >= 4:
            impact += 0.15

        if wave_height >= 10:
            impact += 0.2
        elif wave_height >= 5:
            impact += 0.1

        return min(impact, 1.0)

    def _calculate_before_completeness(self, beforeinfo_data: Dict) -> float:
        """直前情報のデータ充実度を計算"""
        if not beforeinfo_data.get('is_published', False):
            return 0.0

        score = 0
        max_score = 6

        if len(beforeinfo_data.get('exhibition_times', {})) >= 5:
            score += 1
        if len(beforeinfo_data.get('start_timings', {})) >= 5:
            score += 1
        if len(beforeinfo_data.get('exhibition_courses', {})) >= 5:
            score += 1
        if len(beforeinfo_data.get('tilt_angles', {})) >= 5:
            score += 1
        if beforeinfo_data.get('weather', {}):
            score += 1
        if len(beforeinfo_data.get('previous_race', {})) >= 3:
            score += 1

        return score / max_score

    def integrate_scores(
        self,
        pre_score: float,
        before_score: float,
        weights: IntegrationWeights
    ) -> float:
        """
        スコアを統合

        Args:
            pre_score: 事前スコア (0-100)
            before_score: 直前情報スコア (0-100)
            weights: 統合重み

        Returns:
            統合後スコア
        """
        return pre_score * weights.pre_weight + before_score * weights.before_weight
```

#### 2.1.2 race_predictor.py への統合

**変更箇所**: `src/analysis/race_predictor.py` line 1422-1481

```python
# 変更前
def _apply_beforeinfo_integration(
    self,
    predictions: List[Dict],
    race_id: int,
    venue_code: str
) -> List[Dict]:
    """
    直前情報スコアリングと統合を適用

    統合式: FINAL_SCORE = PRE_SCORE * 0.6 + BEFORE_SCORE * 0.4
    """
    # ... 固定比率での統合

# 変更後
from .dynamic_integration import DynamicIntegrator, IntegrationWeights

def _apply_beforeinfo_integration(
    self,
    predictions: List[Dict],
    race_id: int,
    venue_code: str,
    weather_data: Optional[Dict] = None
) -> List[Dict]:
    """
    直前情報スコアリングと統合を適用（動的重み版）

    統合式: FINAL_SCORE = PRE_SCORE * w1 + BEFORE_SCORE * w2
    w1, w2 は条件により動的に決定
    """
    # DynamicIntegratorで重みを決定
    integrator = DynamicIntegrator(self.db_path)

    # 直前情報データを取得
    beforeinfo_data = self.beforeinfo_scorer._load_beforeinfo_from_db(race_id)

    # 動的重みを決定
    weights = integrator.determine_weights(
        race_id=race_id,
        beforeinfo_data=beforeinfo_data,
        pre_predictions=predictions,
        venue_code=venue_code,
        weather_data=weather_data
    )

    # 各艇のスコアを統合
    for pred in predictions:
        pit_number = pred['pit_number']
        pre_score = pred['total_score']

        # 直前情報スコアを計算
        beforeinfo_result = self.beforeinfo_scorer.calculate_beforeinfo_score(
            race_id=race_id,
            pit_number=pit_number,
            beforeinfo_data=beforeinfo_data
        )

        before_score = beforeinfo_result['total_score']

        # 動的統合
        final_score = integrator.integrate_scores(
            pre_score=pre_score,
            before_score=before_score,
            weights=weights
        )

        # スコアを更新
        pred['pre_score'] = round(pre_score, 1)
        pred['total_score'] = round(final_score, 1)
        pred['beforeinfo_score'] = round(before_score, 1)

        # 動的重み情報を追加
        pred['integration_weights'] = {
            'pre_weight': round(weights.pre_weight, 3),
            'before_weight': round(weights.before_weight, 3),
            'condition': weights.condition.value,
            'reason': weights.reason
        }

        # 既存の詳細情報も維持
        pred['beforeinfo_detail'] = {
            'exhibition_time': round(beforeinfo_result['exhibition_time_score'], 1),
            'st': round(beforeinfo_result['st_score'], 1),
            'entry': round(beforeinfo_result['entry_score'], 1),
            'prev_race': round(beforeinfo_result['prev_race_score'], 1),
            'tilt_wind': round(beforeinfo_result['tilt_wind_score'], 1),
            'parts_weight': round(beforeinfo_result['parts_weight_score'], 1)
        }

    return predictions
```

#### 2.1.3 テストコード

**ファイル**: `tests/test_dynamic_integration.py`

```python
"""
動的スコア統合のユニットテスト
"""

import pytest
from src.analysis.dynamic_integration import (
    DynamicIntegrator, IntegrationCondition, IntegrationWeights
)


class TestDynamicIntegrator:
    """動的統合テスト"""

    def setup_method(self):
        self.integrator = DynamicIntegrator()

    def test_normal_condition(self):
        """通常条件での重み決定"""
        beforeinfo_data = {
            'is_published': True,
            'exhibition_times': {1: 6.77, 2: 6.78, 3: 6.79, 4: 6.80, 5: 6.81, 6: 6.82},
            'start_timings': {1: 0.12, 2: 0.13, 3: 0.14, 4: 0.15, 5: 0.16, 6: 0.17},
            'exhibition_courses': {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
            'tilt_angles': {1: -0.5, 2: -0.5, 3: 0.0, 4: 0.0, 5: 0.5, 6: 0.5},
            'weather': {'wind_speed': 2, 'wave_height': 3}
        }

        predictions = [
            {'total_score': 75.0, 'confidence': 'A'},
            {'total_score': 65.0, 'confidence': 'B'},
        ]

        weights = self.integrator.determine_weights(
            race_id=1,
            beforeinfo_data=beforeinfo_data,
            pre_predictions=predictions,
            venue_code='01'
        )

        assert 0.5 <= weights.pre_weight <= 0.7
        assert 0.3 <= weights.before_weight <= 0.5

    def test_exhibition_variance_high(self):
        """展示タイム分散が高い場合"""
        beforeinfo_data = {
            'is_published': True,
            'exhibition_times': {1: 6.50, 2: 6.90, 3: 6.55, 4: 6.95, 5: 6.60, 6: 6.85},
            'start_timings': {1: 0.12, 2: 0.13, 3: 0.14, 4: 0.15, 5: 0.16, 6: 0.17},
            'exhibition_courses': {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6},
            'tilt_angles': {},
            'weather': {}
        }

        predictions = [
            {'total_score': 70.0, 'confidence': 'B'},
            {'total_score': 68.0, 'confidence': 'B'},
        ]

        weights = self.integrator.determine_weights(
            race_id=1,
            beforeinfo_data=beforeinfo_data,
            pre_predictions=predictions,
            venue_code='01'
        )

        # 直前情報重視になるべき
        assert weights.condition == IntegrationCondition.BEFOREINFO_CRITICAL
        assert weights.before_weight > 0.5

    def test_entry_changes(self):
        """進入変更が多い場合"""
        beforeinfo_data = {
            'is_published': True,
            'exhibition_times': {1: 6.77, 2: 6.78, 3: 6.79, 4: 6.80, 5: 6.81, 6: 6.82},
            'start_timings': {1: 0.12, 2: 0.13, 3: 0.14, 4: 0.15, 5: 0.16, 6: 0.17},
            'exhibition_courses': {1: 1, 2: 3, 3: 2, 4: 5, 5: 4, 6: 6},  # 3艇変更
            'tilt_angles': {},
            'weather': {}
        }

        predictions = [
            {'total_score': 70.0, 'confidence': 'B'},
            {'total_score': 68.0, 'confidence': 'B'},
        ]

        weights = self.integrator.determine_weights(
            race_id=1,
            beforeinfo_data=beforeinfo_data,
            pre_predictions=predictions,
            venue_code='01'
        )

        assert weights.condition == IntegrationCondition.BEFOREINFO_CRITICAL

    def test_score_integration(self):
        """スコア統合のテスト"""
        weights = IntegrationWeights(
            pre_weight=0.6,
            before_weight=0.4,
            condition=IntegrationCondition.NORMAL,
            reason="テスト",
            confidence=0.8
        )

        final_score = self.integrator.integrate_scores(
            pre_score=70.0,
            before_score=80.0,
            weights=weights
        )

        expected = 70.0 * 0.6 + 80.0 * 0.4  # 74.0
        assert final_score == pytest.approx(expected, rel=0.01)
```

#### 2.1.4 実装手順

| ステップ | 作業内容 | 予想工数 |
|---------|---------|---------|
| 1 | `dynamic_integration.py` 新規作成 | 2時間 |
| 2 | `race_predictor.py` の `_apply_beforeinfo_integration` 修正 | 1時間 |
| 3 | `test_dynamic_integration.py` 作成・テスト実行 | 1時間 |
| 4 | バックテストで効果検証 | 2時間 |
| **合計** | | **6時間** |

---

### 2.2 進入予測モデル追加

**目的**: 枠なり崩れを履歴ベースの確率モデルで予測

#### 2.2.1 新規ファイル作成

**ファイル**: `src/analysis/entry_prediction_model.py`

```python
"""
進入予測モデル

選手の過去進入パターンから、実際の進入コースを確率的に予測する。
前付け傾向のある選手を特定し、進入崩れの影響を正確に反映する。
"""

import sqlite3
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import math


@dataclass
class EntryPrediction:
    """進入予測結果"""
    pit_number: int
    predicted_course: int
    probabilities: Dict[int, float]  # {コース: 確率}
    confidence: float
    is_front_entry_prone: bool  # 前付け傾向
    front_entry_rate: float
    description: str


class EntryPredictionModel:
    """進入予測モデル"""

    # ベイズ更新用の事前分布（枠番=コースの確率）
    PRIOR_SAME_COURSE_PROB = 0.90  # 枠なりの事前確率

    # 選手タイプ別の前付け傾向
    FRONT_ENTRY_TYPES = {
        'aggressive': 0.7,   # 積極的前付け型
        'occasional': 0.3,   # 時々前付け型
        'passive': 0.05,     # 枠なり型
    }

    # 最低サンプル数（これ未満はベイズ更新の重みを下げる）
    MIN_SAMPLES = 10

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path
        self._entry_cache: Dict[str, Dict] = {}

    def predict_race_entries(
        self,
        race_id: int,
        entries: List[Dict]
    ) -> Dict[int, EntryPrediction]:
        """
        レースの進入隊形を予測

        Args:
            race_id: レースID
            entries: 出走選手リスト [{'pit_number', 'racer_number', ...}]

        Returns:
            {pit_number: EntryPrediction}
        """
        predictions = {}
        racer_patterns = {}

        # 各選手の進入パターンを取得
        for entry in entries:
            pit = entry['pit_number']
            racer_number = entry['racer_number']

            pattern = self._get_racer_entry_pattern(racer_number)
            racer_patterns[pit] = pattern

            # 個別予測を計算
            prediction = self._predict_single_entry(pit, pattern)
            predictions[pit] = prediction

        # 進入競合を解決（複数艇が同じコースを予測した場合）
        predictions = self._resolve_entry_conflicts(predictions, racer_patterns)

        return predictions

    def _get_racer_entry_pattern(self, racer_number: str) -> Dict:
        """
        選手の進入パターンを取得

        Returns:
            {
                'pit_course_matrix': {pit: {course: count}},
                'total_races': int,
                'front_entry_rate': float,
                'entry_type': str
            }
        """
        # キャッシュチェック
        if racer_number in self._entry_cache:
            return self._entry_cache[racer_number]

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 過去180日の進入パターンを集計
            cursor.execute('''
                SELECT
                    e.pit_number,
                    rd.actual_course,
                    COUNT(*) as cnt
                FROM entries e
                JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                JOIN races r ON e.race_id = r.id
                WHERE e.racer_number = ?
                  AND rd.actual_course IS NOT NULL
                  AND r.race_date >= date('now', '-180 days')
                GROUP BY e.pit_number, rd.actual_course
            ''', (racer_number,))

            rows = cursor.fetchall()

            if not rows:
                # データがない場合はデフォルトパターン
                return {
                    'pit_course_matrix': {},
                    'total_races': 0,
                    'front_entry_rate': 0.0,
                    'entry_type': 'passive'
                }

            # マトリクスを構築
            matrix = defaultdict(lambda: defaultdict(int))
            total = 0
            front_entry_count = 0

            for pit, course, cnt in rows:
                matrix[pit][course] = cnt
                total += cnt
                if course < pit:
                    front_entry_count += cnt

            # 前付け率
            front_entry_rate = front_entry_count / total if total > 0 else 0

            # 選手タイプ判定
            if front_entry_rate > 0.5:
                entry_type = 'aggressive'
            elif front_entry_rate > 0.2:
                entry_type = 'occasional'
            else:
                entry_type = 'passive'

            pattern = {
                'pit_course_matrix': dict(matrix),
                'total_races': total,
                'front_entry_rate': front_entry_rate,
                'entry_type': entry_type
            }

            # キャッシュに保存
            self._entry_cache[racer_number] = pattern

            return pattern

        finally:
            conn.close()

    def _predict_single_entry(
        self,
        pit_number: int,
        pattern: Dict
    ) -> EntryPrediction:
        """
        単一選手の進入を予測
        """
        matrix = pattern.get('pit_course_matrix', {})
        total_races = pattern.get('total_races', 0)

        # 事前分布
        prior = {c: 0.01 for c in range(1, 7)}
        prior[pit_number] = self.PRIOR_SAME_COURSE_PROB

        # 総和を1に正規化
        prior_sum = sum(prior.values())
        prior = {c: p / prior_sum for c, p in prior.items()}

        if pit_number in matrix and total_races >= self.MIN_SAMPLES:
            # ベイズ更新
            pit_data = matrix[pit_number]
            pit_total = sum(pit_data.values())

            # 尤度を計算
            likelihood = {}
            for course in range(1, 7):
                count = pit_data.get(course, 0)
                likelihood[course] = (count + 1) / (pit_total + 6)  # ラプラス平滑化

            # 事後分布
            posterior = {}
            for course in range(1, 7):
                posterior[course] = prior[course] * likelihood[course]

            # 正規化
            post_sum = sum(posterior.values())
            probabilities = {c: p / post_sum for c, p in posterior.items()}
        else:
            # データ不足の場合は事前分布を使用
            probabilities = prior

        # 最も確率の高いコースを予測
        predicted_course = max(probabilities, key=probabilities.get)
        confidence = probabilities[predicted_course]

        # 前付け傾向フラグ
        is_front_entry_prone = pattern.get('front_entry_rate', 0) > 0.3

        # 説明文生成
        if is_front_entry_prone:
            desc = f"{pit_number}号艇: 前付け傾向({pattern['front_entry_rate']*100:.0f}%)→{predicted_course}コース予測"
        elif predicted_course != pit_number:
            desc = f"{pit_number}号艇: {predicted_course}コース予測({confidence*100:.0f}%)"
        else:
            desc = f"{pit_number}号艇: 枠なり({confidence*100:.0f}%)"

        return EntryPrediction(
            pit_number=pit_number,
            predicted_course=predicted_course,
            probabilities=probabilities,
            confidence=confidence,
            is_front_entry_prone=is_front_entry_prone,
            front_entry_rate=pattern.get('front_entry_rate', 0),
            description=desc
        )

    def _resolve_entry_conflicts(
        self,
        predictions: Dict[int, EntryPrediction],
        racer_patterns: Dict[int, Dict]
    ) -> Dict[int, EntryPrediction]:
        """
        進入競合を解決

        複数の艇が同じコースを予測した場合、前付け傾向や確率から調整
        """
        # コースごとの予測をグループ化
        course_predictions = defaultdict(list)
        for pit, pred in predictions.items():
            course_predictions[pred.predicted_course].append((pit, pred))

        # 競合があるコースを処理
        final_predictions = dict(predictions)

        for course, preds in course_predictions.items():
            if len(preds) <= 1:
                continue

            # 競合がある場合、前付け傾向と確率でソート
            sorted_preds = sorted(
                preds,
                key=lambda x: (
                    x[1].is_front_entry_prone,
                    x[1].front_entry_rate,
                    x[1].confidence
                ),
                reverse=True
            )

            # 最も前付け傾向の強い艇がそのコースを取得
            winner_pit = sorted_preds[0][0]

            # 他の艇は次のコースに移動
            for i, (pit, pred) in enumerate(sorted_preds[1:], 1):
                # 次に確率の高いコースを割り当て
                available_courses = [c for c in range(1, 7)
                                   if c != course and
                                   not any(p.predicted_course == c
                                          for p in final_predictions.values()
                                          if p.pit_number != pit)]

                if available_courses:
                    # 確率が最も高い利用可能コース
                    new_course = max(available_courses,
                                    key=lambda c: pred.probabilities.get(c, 0))

                    # 予測を更新
                    final_predictions[pit] = EntryPrediction(
                        pit_number=pit,
                        predicted_course=new_course,
                        probabilities=pred.probabilities,
                        confidence=pred.probabilities.get(new_course, 0.1),
                        is_front_entry_prone=pred.is_front_entry_prone,
                        front_entry_rate=pred.front_entry_rate,
                        description=f"{pit}号艇: 競合により{new_course}コースに調整"
                    )

        return final_predictions

    def calculate_entry_impact_score(
        self,
        pit_number: int,
        prediction: EntryPrediction,
        max_score: float = 10.0
    ) -> Dict:
        """
        進入予測による影響スコアを計算

        Args:
            pit_number: 枠番
            prediction: 進入予測
            max_score: 最大スコア

        Returns:
            {
                'score': float,
                'impact_type': str,  # 'positive' / 'negative' / 'neutral'
                'description': str
            }
        """
        predicted_course = prediction.predicted_course
        confidence = prediction.confidence

        # コース変化による影響
        if predicted_course < pit_number:
            # 内コースを取得 → 有利
            course_gain = pit_number - predicted_course
            base_score = max_score * 0.5 + (course_gain * 0.15 * max_score)
            impact_type = 'positive'
            desc = f"内コース取得({pit_number}→{predicted_course})"
        elif predicted_course > pit_number:
            # 外コースに追いやられる → 不利
            course_loss = predicted_course - pit_number
            base_score = max_score * 0.5 - (course_loss * 0.15 * max_score)
            impact_type = 'negative'
            desc = f"外コースに流出({pit_number}→{predicted_course})"
        else:
            # 枠なり → 中立
            base_score = max_score * 0.5
            impact_type = 'neutral'
            desc = f"枠なり({pit_number}コース)"

        # 信頼度で調整
        score = base_score * (0.5 + 0.5 * confidence)

        # 前付け傾向による不安定性ペナルティ
        if prediction.is_front_entry_prone and confidence < 0.7:
            score *= 0.9  # 10%ペナルティ
            desc += "（進入不安定）"

        return {
            'score': max(0, min(max_score, score)),
            'impact_type': impact_type,
            'description': desc,
            'predicted_course': predicted_course,
            'confidence': confidence
        }
```

#### 2.2.2 extended_scorer.py への統合

**変更箇所**: `src/analysis/extended_scorer.py` の `calculate_course_entry_tendency` メソッドを拡張

```python
# 追加インポート
from .entry_prediction_model import EntryPredictionModel, EntryPrediction

class ExtendedScorer:
    def __init__(self, db_path: str = None, batch_loader=None):
        self.db_path = db_path or DATABASE_PATH
        self.batch_loader = batch_loader
        self.entry_model = EntryPredictionModel(self.db_path)  # 追加

    def calculate_course_entry_with_model(
        self,
        racer_number: str,
        pit_number: int,
        race_entries: List[Dict],
        max_score: float = 5.0
    ) -> Dict:
        """
        確率モデルベースの進入予測スコアを計算

        Args:
            racer_number: 選手番号
            pit_number: 枠番
            race_entries: 同レースの全エントリー
            max_score: 最大スコア

        Returns:
            進入予測とスコア
        """
        # レース全体の進入予測
        predictions = self.entry_model.predict_race_entries(
            race_id=0,  # race_idは使用しない
            entries=race_entries
        )

        if pit_number not in predictions:
            return {
                'score': max_score * 0.5,
                'predicted_course': pit_number,
                'confidence': 0.5,
                'description': '進入予測データなし'
            }

        prediction = predictions[pit_number]
        impact = self.entry_model.calculate_entry_impact_score(
            pit_number=pit_number,
            prediction=prediction,
            max_score=max_score
        )

        return {
            'score': impact['score'],
            'predicted_course': impact['predicted_course'],
            'confidence': impact['confidence'],
            'impact_type': impact['impact_type'],
            'front_entry_rate': prediction.front_entry_rate,
            'is_front_entry_prone': prediction.is_front_entry_prone,
            'all_predictions': {
                p: {
                    'course': pred.predicted_course,
                    'confidence': pred.confidence
                }
                for p, pred in predictions.items()
            },
            'description': impact['description']
        }
```

#### 2.2.3 実装手順

| ステップ | 作業内容 | 予想工数 |
|---------|---------|---------|
| 1 | `entry_prediction_model.py` 新規作成 | 3時間 |
| 2 | `extended_scorer.py` への統合 | 1時間 |
| 3 | `race_predictor.py` でモデル使用 | 1時間 |
| 4 | テストコード作成・実行 | 1.5時間 |
| 5 | バックテストで効果検証 | 2時間 |
| **合計** | | **8.5時間** |

---

### 2.3 直前情報信頼度スコアの明確化

**目的**: 直前情報の信頼度を連続値（0.0-1.0）で表現し、統合時に活用

#### 2.3.1 beforeinfo_scorer.py の改良

**変更箇所**: `src/analysis/beforeinfo_scorer.py`

```python
# 変更前
def _calc_confidence(self, total_score: float, data_completeness: float) -> float:
    """
    信頼度を計算（0.0-1.0）
    シグモイド関数を使用
    """
    import math
    def sigmoid(x):
        return 1 / (1 + math.exp(-x))
    score_confidence = sigmoid((total_score - 30) / 15)
    return score_confidence * data_completeness

# 変更後（複合的な信頼度計算）
def _calc_confidence(
    self,
    total_score: float,
    data_completeness: float,
    exhibition_times: Dict[int, float],
    start_timings: Dict[int, float],
    pit_number: int
) -> Dict:
    """
    複合的な信頼度を計算

    Returns:
        {
            'overall': float,          # 総合信頼度 (0.0-1.0)
            'score_based': float,      # スコアベース信頼度
            'data_based': float,       # データ充実度ベース信頼度
            'consistency': float,      # 一貫性信頼度
            'relative_strength': float # 相対的強さ信頼度
        }
    """
    import math

    def sigmoid(x):
        return 1 / (1 + math.exp(-x))

    # 1. スコアベース信頼度
    score_confidence = sigmoid((total_score - 30) / 15)

    # 2. データ充実度ベース信頼度
    data_confidence = data_completeness

    # 3. 一貫性信頼度（展示タイムとSTの順位相関）
    consistency = self._calc_consistency_confidence(
        exhibition_times, start_timings, pit_number
    )

    # 4. 相対的強さ信頼度（他艇との差）
    relative_strength = self._calc_relative_strength_confidence(
        exhibition_times, start_timings, pit_number
    )

    # 総合信頼度（加重平均）
    overall = (
        score_confidence * 0.3 +
        data_confidence * 0.3 +
        consistency * 0.2 +
        relative_strength * 0.2
    )

    return {
        'overall': overall,
        'score_based': score_confidence,
        'data_based': data_confidence,
        'consistency': consistency,
        'relative_strength': relative_strength
    }

def _calc_consistency_confidence(
    self,
    exhibition_times: Dict[int, float],
    start_timings: Dict[int, float],
    pit_number: int
) -> float:
    """
    展示タイムとSTの順位が一致しているか（一貫性）を評価
    """
    if len(exhibition_times) < 4 or len(start_timings) < 4:
        return 0.5  # データ不足

    # 展示タイム順位
    sorted_ex = sorted(exhibition_times.items(), key=lambda x: x[1])
    ex_rank = next((i+1 for i, (p, _) in enumerate(sorted_ex) if p == pit_number), 3)

    # ST順位（小さいほど良い、負は除外）
    valid_st = {p: t for p, t in start_timings.items() if t >= 0}
    if pit_number not in valid_st:
        return 0.5

    sorted_st = sorted(valid_st.items(), key=lambda x: x[1])
    st_rank = next((i+1 for i, (p, _) in enumerate(sorted_st) if p == pit_number), 3)

    # 順位差
    rank_diff = abs(ex_rank - st_rank)

    # 差が小さいほど一貫性が高い
    if rank_diff <= 1:
        return 1.0
    elif rank_diff <= 2:
        return 0.7
    elif rank_diff <= 3:
        return 0.5
    else:
        return 0.3

def _calc_relative_strength_confidence(
    self,
    exhibition_times: Dict[int, float],
    start_timings: Dict[int, float],
    pit_number: int
) -> float:
    """
    他艇との差が明確かどうかを評価
    """
    if len(exhibition_times) < 4:
        return 0.5

    # 展示タイムでの相対位置
    if pit_number not in exhibition_times:
        return 0.5

    my_time = exhibition_times[pit_number]
    all_times = list(exhibition_times.values())

    min_time = min(all_times)
    max_time = max(all_times)
    time_range = max_time - min_time

    if time_range < 0.01:
        return 0.5  # 全員同じ

    # 正規化した位置（0=トップ、1=最下位）
    position = (my_time - min_time) / time_range

    # トップに近いほど信頼度高
    if position <= 0.2:
        return 0.9
    elif position <= 0.4:
        return 0.7
    elif position <= 0.6:
        return 0.5
    else:
        return 0.3
```

#### 2.3.2 実装手順

| ステップ | 作業内容 | 予想工数 |
|---------|---------|---------|
| 1 | `beforeinfo_scorer.py` の `_calc_confidence` 改良 | 2時間 |
| 2 | 戻り値を辞書形式に変更、呼び出し元修正 | 1時間 |
| 3 | テストコード追加 | 1時間 |
| **合計** | | **4時間** |

---

## 3. Phase 2: 中優先度改善（数週間以内）

### 3.1 複合バフの自動学習化

**目的**: 手動ルールを頻度ベース/機械学習で検証・更新

#### 3.1.1 新規ファイル作成

**ファイル**: `src/analysis/buff_auto_learner.py`

```python
"""
複合バフ自動学習モジュール

過去データから複合条件と結果の相関を分析し、
バフルールを自動的に検証・更新する。
"""

import sqlite3
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import math
from .compound_buff_system import CompoundBuffRule, BuffCondition, ConditionType


@dataclass
class BuffValidationResult:
    """バフ検証結果"""
    rule_id: str
    sample_count: int
    hit_rate: float          # 実際の1着率
    expected_rate: float     # 期待1着率（ベースライン）
    lift: float              # リフト（実際/期待）
    statistical_significance: float  # 統計的有意性
    recommended_buff: float  # 推奨バフ値
    is_valid: bool           # 有効なルールか


class BuffAutoLearner:
    """バフ自動学習クラス"""

    # 最低サンプル数
    MIN_SAMPLES = 50

    # 統計的有意性の閾値（95%信頼区間）
    SIGNIFICANCE_THRESHOLD = 1.96

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def validate_rule(
        self,
        rule: CompoundBuffRule,
        start_date: str,
        end_date: str
    ) -> BuffValidationResult:
        """
        ルールを過去データで検証

        Args:
            rule: 検証するルール
            start_date: 検証期間開始日
            end_date: 検証期間終了日

        Returns:
            検証結果
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # ルール条件に合致するレースを抽出
            matching_races = self._find_matching_races(cursor, rule, start_date, end_date)

            if len(matching_races) < self.MIN_SAMPLES:
                return BuffValidationResult(
                    rule_id=rule.rule_id,
                    sample_count=len(matching_races),
                    hit_rate=0.0,
                    expected_rate=0.167,  # 1/6
                    lift=1.0,
                    statistical_significance=0.0,
                    recommended_buff=0.0,
                    is_valid=False
                )

            # 1着率を計算
            hit_count = sum(1 for r in matching_races if r['is_win'])
            hit_rate = hit_count / len(matching_races)

            # ベースライン（コース別平均勝率）
            expected_rate = self._get_baseline_win_rate(cursor, rule)

            # リフト計算
            lift = hit_rate / expected_rate if expected_rate > 0 else 1.0

            # 統計的有意性（z検定）
            n = len(matching_races)
            se = math.sqrt(expected_rate * (1 - expected_rate) / n)
            z_score = (hit_rate - expected_rate) / se if se > 0 else 0

            # 推奨バフ値の計算
            # リフトに基づく: 1.5倍以上で+5点、2倍で+10点
            if lift > 1.0:
                recommended_buff = min(15.0, (lift - 1.0) * 10.0)
            else:
                recommended_buff = max(-10.0, (lift - 1.0) * 10.0)

            return BuffValidationResult(
                rule_id=rule.rule_id,
                sample_count=len(matching_races),
                hit_rate=hit_rate,
                expected_rate=expected_rate,
                lift=lift,
                statistical_significance=z_score,
                recommended_buff=recommended_buff,
                is_valid=abs(z_score) >= self.SIGNIFICANCE_THRESHOLD
            )

        finally:
            conn.close()

    def _find_matching_races(
        self,
        cursor,
        rule: CompoundBuffRule,
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        """
        ルール条件に合致するレースを抽出
        """
        # 基本クエリ
        query = '''
            SELECT
                r.id as race_id,
                r.venue_code,
                e.pit_number,
                rd.actual_course,
                res.rank,
                e.racer_number,
                e.racer_rank,
                m.motor_number
            FROM races r
            JOIN entries e ON r.id = e.race_id
            LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
            LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            LEFT JOIN motors m ON e.motor_number = m.motor_number AND r.venue_code = m.venue_code
            WHERE r.race_date BETWEEN ? AND ?
            AND res.rank IS NOT NULL
        '''

        params = [start_date, end_date]

        # 条件を追加
        for cond in rule.conditions:
            if cond.condition_type == ConditionType.VENUE:
                if isinstance(cond.value, list):
                    placeholders = ','.join('?' * len(cond.value))
                    query += f' AND r.venue_code IN ({placeholders})'
                    params.extend(cond.value)
                else:
                    query += ' AND r.venue_code = ?'
                    params.append(cond.value)

            elif cond.condition_type == ConditionType.COURSE:
                if isinstance(cond.value, list):
                    placeholders = ','.join('?' * len(cond.value))
                    query += f' AND COALESCE(rd.actual_course, e.pit_number) IN ({placeholders})'
                    params.extend(cond.value)
                else:
                    query += ' AND COALESCE(rd.actual_course, e.pit_number) = ?'
                    params.append(cond.value)

            elif cond.condition_type == ConditionType.RACER_RANK:
                if isinstance(cond.value, list):
                    placeholders = ','.join('?' * len(cond.value))
                    query += f' AND e.racer_rank IN ({placeholders})'
                    params.extend(cond.value)
                else:
                    query += ' AND e.racer_rank = ?'
                    params.append(cond.value)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            try:
                rank = int(row[4])
                is_win = (rank == 1)
            except (ValueError, TypeError):
                is_win = False

            results.append({
                'race_id': row[0],
                'venue_code': row[1],
                'pit_number': row[2],
                'actual_course': row[3] or row[2],
                'rank': row[4],
                'is_win': is_win,
                'racer_number': row[5],
                'racer_rank': row[6]
            })

        return results

    def _get_baseline_win_rate(self, cursor, rule: CompoundBuffRule) -> float:
        """
        ベースライン勝率を取得（条件なしの場合の平均勝率）
        """
        # コース条件がある場合はそのコースの平均勝率を使用
        for cond in rule.conditions:
            if cond.condition_type == ConditionType.COURSE:
                course = cond.value if not isinstance(cond.value, list) else cond.value[0]
                course_win_rates = {
                    1: 0.55, 2: 0.14, 3: 0.12,
                    4: 0.10, 5: 0.06, 6: 0.03
                }
                return course_win_rates.get(course, 0.167)

        return 0.167  # 1/6

    def discover_new_rules(
        self,
        start_date: str,
        end_date: str,
        min_lift: float = 1.3
    ) -> List[CompoundBuffRule]:
        """
        過去データから新しいルールを発見

        Args:
            start_date: 分析期間開始日
            end_date: 分析期間終了日
            min_lift: 最低リフト値

        Returns:
            発見されたルールのリスト
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        discovered_rules = []

        try:
            # 会場×コースの組み合わせを分析
            cursor.execute('''
                SELECT
                    r.venue_code,
                    COALESCE(rd.actual_course, e.pit_number) as course,
                    COUNT(*) as total,
                    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins
                FROM races r
                JOIN entries e ON r.id = e.race_id
                LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
                LEFT JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
                WHERE r.race_date BETWEEN ? AND ?
                AND res.rank IS NOT NULL
                GROUP BY r.venue_code, course
                HAVING COUNT(*) >= ?
            ''', (start_date, end_date, self.MIN_SAMPLES))

            for venue, course, total, wins in cursor.fetchall():
                win_rate = wins / total
                expected = {1: 0.55, 2: 0.14, 3: 0.12, 4: 0.10, 5: 0.06, 6: 0.03}.get(course, 0.167)
                lift = win_rate / expected if expected > 0 else 1.0

                if lift >= min_lift:
                    # 有意なパターンを発見
                    buff_value = min(10.0, (lift - 1.0) * 8.0)

                    rule = CompoundBuffRule(
                        rule_id=f"auto_{venue}_{course}",
                        name=f"会場{venue}の{course}コース強化",
                        description=f"自動発見: 会場{venue}で{course}コースの勝率が{win_rate*100:.1f}%",
                        conditions=[
                            BuffCondition(ConditionType.VENUE, venue),
                            BuffCondition(ConditionType.COURSE, course),
                        ],
                        buff_value=buff_value,
                        confidence=0.7,  # 自動発見は初期信頼度を低めに
                        sample_count=total,
                        hit_rate=win_rate
                    )
                    discovered_rules.append(rule)

            return discovered_rules

        finally:
            conn.close()

    def update_rule_confidence(
        self,
        rule: CompoundBuffRule,
        validation_result: BuffValidationResult
    ) -> CompoundBuffRule:
        """
        検証結果に基づいてルールの信頼度とバフ値を更新
        """
        # 信頼度の更新（ベイズ更新的アプローチ）
        prior_confidence = rule.confidence
        evidence_weight = min(1.0, validation_result.sample_count / 100)

        if validation_result.is_valid:
            new_confidence = prior_confidence * 0.7 + 0.3 * evidence_weight
        else:
            new_confidence = prior_confidence * 0.8  # 無効な場合は徐々に低下

        # バフ値の更新
        new_buff = (rule.buff_value * 0.6 + validation_result.recommended_buff * 0.4)

        return CompoundBuffRule(
            rule_id=rule.rule_id,
            name=rule.name,
            description=rule.description,
            conditions=rule.conditions,
            buff_value=new_buff,
            confidence=new_confidence,
            sample_count=validation_result.sample_count,
            hit_rate=validation_result.hit_rate,
            is_active=new_confidence >= 0.3  # 信頼度0.3未満は無効化
        )
```

#### 3.1.2 実装手順

| ステップ | 作業内容 | 予想工数 |
|---------|---------|---------|
| 1 | `buff_auto_learner.py` 新規作成 | 4時間 |
| 2 | `compound_buff_system.py` との連携 | 2時間 |
| 3 | 定期実行スクリプト作成 | 1時間 |
| 4 | テスト・検証 | 2時間 |
| **合計** | | **9時間** |

---

### 3.2 信頼度の細分化

**目的**: A-Eの5段階を A1/A2/B/C/D/E の6段階または連続スコアに拡張

#### 3.2.1 race_predictor.py の修正

```python
# 変更前
def _calculate_confidence(self, total_score: float, racer_analysis: Dict, motor_analysis: Dict) -> str:
    """信頼度を判定（A-E）"""
    # ... 5段階判定
    return confidence  # 'A', 'B', 'C', 'D', 'E'

# 変更後
def _calculate_confidence(
    self,
    total_score: float,
    racer_analysis: Dict,
    motor_analysis: Dict
) -> Dict:
    """
    信頼度を判定（細分化版）

    Returns:
        {
            'grade': str,           # 'A1', 'A2', 'B', 'C', 'D', 'E'
            'score': float,         # 連続スコア (0-100)
            'data_quality': float,  # データ充実度 (0-100)
            'components': {
                'score_based': float,
                'data_based': float,
                'consistency': float
            }
        }
    """
    # データ充実度を計算
    racer_overall = racer_analysis['overall_stats']['total_races']
    racer_course = racer_analysis['course_stats']['total_races']
    racer_venue = racer_analysis['venue_stats']['total_races']
    motor_total = motor_analysis['motor_stats']['total_races']

    # データ充実度スコア（0-100点）
    data_quality = 0.0

    if racer_overall >= 100:
        data_quality += 40.0
    elif racer_overall >= 50:
        data_quality += 30.0
    elif racer_overall >= 20:
        data_quality += 20.0
    else:
        data_quality += min(racer_overall, 10)

    if racer_course >= 15:
        data_quality += 25.0
    elif racer_course >= 10:
        data_quality += 20.0
    elif racer_course >= 5:
        data_quality += 15.0
    else:
        data_quality += racer_course * 2

    if racer_venue >= 10:
        data_quality += 15.0
    elif racer_venue >= 5:
        data_quality += 10.0
    else:
        data_quality += racer_venue * 2

    if motor_total >= 30:
        data_quality += 20.0
    elif motor_total >= 20:
        data_quality += 15.0
    elif motor_total >= 10:
        data_quality += 10.0
    else:
        data_quality += motor_total * 0.5

    # 連続スコア計算
    # スコアベース（50%）+ データ充実度（50%）
    score_component = min(100, total_score)
    data_component = data_quality

    continuous_score = score_component * 0.5 + data_component * 0.5

    # 細分化グレード判定
    if continuous_score >= 85 and data_quality >= 80:
        grade = 'A1'
    elif continuous_score >= 75 and data_quality >= 60:
        grade = 'A2'
    elif continuous_score >= 65 and data_quality >= 50:
        grade = 'B'
    elif continuous_score >= 55:
        grade = 'C'
    elif continuous_score >= 45:
        grade = 'D'
    else:
        grade = 'E'

    return {
        'grade': grade,
        'score': round(continuous_score, 1),
        'data_quality': round(data_quality, 1),
        'components': {
            'score_based': round(score_component, 1),
            'data_based': round(data_component, 1)
        }
    }
```

#### 3.2.2 実装手順

| ステップ | 作業内容 | 予想工数 |
|---------|---------|---------|
| 1 | `_calculate_confidence` メソッド改修 | 2時間 |
| 2 | 呼び出し元の修正（辞書形式対応） | 1.5時間 |
| 3 | UI表示の修正 | 1時間 |
| 4 | テスト | 1時間 |
| **合計** | | **5.5時間** |

---

### 3.3 キャリブレーション導入

**目的**: 予測確率を実際の勝率に合わせて調整

#### 3.3.1 新規ファイル作成

**ファイル**: `src/analysis/probability_calibrator.py`

```python
"""
確率キャリブレーションモジュール

予測スコアを実際の勝率に合わせてキャリブレーションする。
日次・週次で更新し、過補正を防ぐ。
"""

import sqlite3
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import math
import json
from pathlib import Path
from datetime import datetime, timedelta


@dataclass
class CalibrationBin:
    """キャリブレーションビン"""
    score_min: float
    score_max: float
    predicted_count: int
    actual_wins: int
    predicted_prob: float  # 予測確率（スコア中央値）
    actual_prob: float     # 実際の勝率


class ProbabilityCalibrator:
    """確率キャリブレータ"""

    # ビン数
    NUM_BINS = 10

    # キャリブレーションデータの保存先
    CALIBRATION_FILE = "data/calibration_data.json"

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path
        self.calibration_table: Dict[str, List[CalibrationBin]] = {}
        self._load_calibration_data()

    def _load_calibration_data(self):
        """保存されたキャリブレーションデータを読み込み"""
        path = Path(self.CALIBRATION_FILE)
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, bins in data.items():
                        self.calibration_table[key] = [
                            CalibrationBin(**b) for b in bins
                        ]
            except Exception:
                pass

    def _save_calibration_data(self):
        """キャリブレーションデータを保存"""
        path = Path(self.CALIBRATION_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {}
        for key, bins in self.calibration_table.items():
            data[key] = [
                {
                    'score_min': b.score_min,
                    'score_max': b.score_max,
                    'predicted_count': b.predicted_count,
                    'actual_wins': b.actual_wins,
                    'predicted_prob': b.predicted_prob,
                    'actual_prob': b.actual_prob
                }
                for b in bins
            ]

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def update_calibration(
        self,
        venue_code: Optional[str] = None,
        days: int = 30
    ) -> Dict:
        """
        キャリブレーションテーブルを更新

        Args:
            venue_code: 会場コード（Noneで全会場）
            days: 集計期間（日数）

        Returns:
            更新結果
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            # 予測スコアと実際の結果を取得
            # 注: 予測スコアは predictions テーブルに保存されている前提
            query = '''
                SELECT
                    p.pit_number,
                    p.total_score,
                    res.rank,
                    r.venue_code
                FROM predictions p
                JOIN races r ON p.race_id = r.id
                JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number
                WHERE r.race_date BETWEEN ? AND ?
            '''
            params = [start_date, end_date]

            if venue_code:
                query += ' AND r.venue_code = ?'
                params.append(venue_code)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            if not rows:
                return {'status': 'no_data', 'rows': 0}

            # ビンに分類
            bins = self._create_bins(rows)

            # キャリブレーションテーブルを更新
            key = venue_code or 'all'
            self.calibration_table[key] = bins

            # 保存
            self._save_calibration_data()

            return {
                'status': 'updated',
                'rows': len(rows),
                'bins': len(bins),
                'key': key
            }

        finally:
            conn.close()

    def _create_bins(self, rows: List[Tuple]) -> List[CalibrationBin]:
        """
        データをビンに分類
        """
        bins = []
        bin_size = 100.0 / self.NUM_BINS

        for i in range(self.NUM_BINS):
            score_min = i * bin_size
            score_max = (i + 1) * bin_size

            # このビンに該当するデータ
            bin_data = [r for r in rows if score_min <= r[1] < score_max]

            if bin_data:
                predicted_count = len(bin_data)
                actual_wins = sum(1 for r in bin_data if r[2] == '1' or r[2] == 1)
                predicted_prob = (score_min + score_max) / 200.0  # スコアを確率に変換
                actual_prob = actual_wins / predicted_count if predicted_count > 0 else 0
            else:
                predicted_count = 0
                actual_wins = 0
                predicted_prob = (score_min + score_max) / 200.0
                actual_prob = predicted_prob  # データなしは予測と同じ

            bins.append(CalibrationBin(
                score_min=score_min,
                score_max=score_max,
                predicted_count=predicted_count,
                actual_wins=actual_wins,
                predicted_prob=predicted_prob,
                actual_prob=actual_prob
            ))

        return bins

    def calibrate_score(
        self,
        score: float,
        venue_code: Optional[str] = None
    ) -> float:
        """
        スコアをキャリブレーション

        Args:
            score: 元のスコア (0-100)
            venue_code: 会場コード

        Returns:
            キャリブレーション後のスコア
        """
        # キャリブレーションテーブルを取得
        key = venue_code or 'all'
        if key not in self.calibration_table:
            key = 'all'

        if key not in self.calibration_table:
            return score  # テーブルがなければ元のスコア

        bins = self.calibration_table[key]

        # 該当するビンを探す
        for b in bins:
            if b.score_min <= score < b.score_max:
                if b.predicted_prob > 0:
                    # キャリブレーション係数
                    calibration_factor = b.actual_prob / b.predicted_prob
                    # 元のスコアに係数を適用（緩やかに）
                    calibrated = score * (0.7 + 0.3 * calibration_factor)
                    return max(0, min(100, calibrated))
                return score

        return score

    def get_calibration_report(self, venue_code: Optional[str] = None) -> Dict:
        """
        キャリブレーションレポートを生成
        """
        key = venue_code or 'all'
        if key not in self.calibration_table:
            return {'status': 'no_data'}

        bins = self.calibration_table[key]

        # Brierスコアを計算
        brier_score = 0.0
        total_samples = 0

        report_bins = []
        for b in bins:
            if b.predicted_count > 0:
                # Brierスコア = (予測確率 - 実際の結果)^2 の平均
                brier_score += b.predicted_count * (b.predicted_prob - b.actual_prob) ** 2
                total_samples += b.predicted_count

            report_bins.append({
                'range': f"{b.score_min:.0f}-{b.score_max:.0f}",
                'count': b.predicted_count,
                'wins': b.actual_wins,
                'predicted_prob': round(b.predicted_prob * 100, 1),
                'actual_prob': round(b.actual_prob * 100, 1),
                'diff': round((b.actual_prob - b.predicted_prob) * 100, 1)
            })

        if total_samples > 0:
            brier_score /= total_samples

        return {
            'status': 'ok',
            'key': key,
            'total_samples': total_samples,
            'brier_score': round(brier_score, 4),
            'bins': report_bins
        }
```

#### 3.3.2 実装手順

| ステップ | 作業内容 | 予想工数 |
|---------|---------|---------|
| 1 | `probability_calibrator.py` 新規作成 | 3時間 |
| 2 | 予測結果の保存機能追加 | 2時間 |
| 3 | 日次バッチ更新スクリプト | 1時間 |
| 4 | race_predictor.py への統合 | 1時間 |
| 5 | テスト・検証 | 2時間 |
| **合計** | | **9時間** |

---

## 4. Phase 3: 低優先度改善（中長期）

### 4.1 会場別ベイズ階層モデル

**概要**: 会場ごとにパラメータを持つ階層的ベイズモデルで、会場特性を自動学習

**実装ファイル**: `src/prediction/bayesian_hierarchical_model.py`

**主要機能**:
- 全会場共通のパラメータ（グローバル）
- 会場別のパラメータ（ローカル）
- 両者を統合した予測

**予想工数**: 20時間（2-3日）

**依存ライブラリ**: PyMC3 または NumPyro

---

### 4.2 強化学習的買い目最適化

**概要**: 期待値と分散を考慮した買い目選択を強化学習で最適化

**実装ファイル**: `src/betting/rl_optimizer.py`

**主要機能**:
- 状態: レース特性、予測スコア、オッズ
- 行動: 買い目の選択（組み合わせと金額）
- 報酬: 収益（回収率）

**予想工数**: 40時間（1週間）

**依存ライブラリ**: Stable-Baselines3 または RLlib

---

## 5. 検証・評価計画

### 5.1 A/Bテスト方法

```python
"""
A/Bテスト実行フレームワーク
"""

class ABTestFramework:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.model_a = RacePredictor(db_path)  # 現行モデル
        self.model_b = RacePredictor(db_path, use_new_features=True)  # 新モデル

    def run_test(
        self,
        start_date: str,
        end_date: str,
        split_ratio: float = 0.5
    ) -> Dict:
        """
        A/Bテストを実行

        - レースをランダムに2群に分割
        - 各群で異なるモデルを使用
        - 結果を比較
        """
        # 実装...
        pass
```

### 5.2 Walk-forward Backtest

```python
"""
Walk-forward バックテスト

時系列を考慮した検証方法:
1. 過去N日でモデルを学習/キャリブレーション
2. 翌日の予測を実行
3. 実際の結果と比較
4. ウィンドウをスライドして繰り返し
"""

class WalkForwardBacktest:
    def __init__(self, db_path: str, window_days: int = 30):
        self.db_path = db_path
        self.window_days = window_days

    def run(
        self,
        start_date: str,
        end_date: str
    ) -> Dict:
        """
        Walk-forward テストを実行
        """
        results = []
        current_date = start_date

        while current_date <= end_date:
            # 学習期間
            train_end = current_date - timedelta(days=1)
            train_start = train_end - timedelta(days=self.window_days)

            # モデル更新
            self._update_model(train_start, train_end)

            # 予測実行
            predictions = self._predict_day(current_date)

            # 結果記録
            results.append(predictions)

            current_date += timedelta(days=1)

        return self._aggregate_results(results)
```

### 5.3 評価指標

| 指標 | 説明 | 目標値 |
|-----|------|-------|
| **1着的中率** | 予測1位が実際に1着 | 30%以上 |
| **3連対的中率** | 予測Top3に1着が含まれる | 70%以上 |
| **Brier Score** | 確率予測の正確性 | 0.15以下 |
| **ROI** | 投資収益率 | 85%以上 |
| **シャープレシオ** | リスク調整後リターン | 0.5以上 |

### 5.4 モニタリングダッシュボード

```python
# ui/components/monitoring_dashboard.py

import streamlit as st
import plotly.express as px

def render_monitoring_dashboard():
    st.title("予測モニタリングダッシュボード")

    # 日次精度推移
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("日次1着的中率")
        # グラフ表示

    with col2:
        st.subheader("日次ROI")
        # グラフ表示

    # キャリブレーション状況
    st.subheader("確率キャリブレーション")
    # ビン別の予測vs実際

    # アラート
    st.subheader("アラート")
    # 精度低下時の警告
```

---

## 6. リスク管理

### 6.1 各改善項目のリスク評価

| 項目 | リスクレベル | 主なリスク | 対策 |
|------|------------|-----------|------|
| 動的合成比 | **中** | 過補正による精度低下 | 段階的導入、モニタリング |
| 進入予測モデル | **低** | データ不足時の不安定性 | ベイズ更新で安定化 |
| 信頼度細分化 | **低** | UI変更の影響 | 後方互換性維持 |
| 複合バフ自動学習 | **中** | 過学習 | 正則化、検証セット分離 |
| キャリブレーション | **中** | 過去データへの過剰適合 | 時系列考慮、ウィンドウ制限 |
| ベイズ階層モデル | **高** | 実装複雑、計算コスト | 段階的導入、キャッシュ活用 |
| 強化学習最適化 | **高** | 学習不安定、実環境との乖離 | シミュレーション環境構築 |

### 6.2 ロールバック手順

```python
# config/feature_flags.py

FEATURE_FLAGS = {
    'dynamic_integration': True,      # 動的合成比
    'entry_prediction_model': True,   # 進入予測モデル
    'confidence_refinement': True,    # 信頼度細分化
    'auto_buff_learning': False,      # 複合バフ自動学習
    'probability_calibration': False, # キャリブレーション
}

def is_feature_enabled(feature_name: str) -> bool:
    return FEATURE_FLAGS.get(feature_name, False)
```

```python
# race_predictor.py での使用例

from config.feature_flags import is_feature_enabled

if is_feature_enabled('dynamic_integration'):
    predictions = self._apply_beforeinfo_integration_v2(predictions, ...)
else:
    predictions = self._apply_beforeinfo_integration(predictions, ...)  # 旧版
```

### 6.3 段階的導入ステップ

1. **ステージ1**: 開発環境でテスト（1週間）
2. **ステージ2**: バックテストで検証（1週間）
3. **ステージ3**: 本番環境の10%で試験運用（1週間）
4. **ステージ4**: 問題なければ50%に拡大（1週間）
5. **ステージ5**: 全体展開

---

## 7. 成果物リスト

### 7.1 新規作成ファイル

| Phase | ファイルパス | 概要 |
|-------|------------|------|
| 1 | `src/analysis/dynamic_integration.py` | 動的スコア統合 |
| 1 | `src/analysis/entry_prediction_model.py` | 進入予測モデル |
| 1 | `tests/test_dynamic_integration.py` | 動的統合テスト |
| 1 | `tests/test_entry_prediction.py` | 進入予測テスト |
| 2 | `src/analysis/buff_auto_learner.py` | バフ自動学習 |
| 2 | `src/analysis/probability_calibrator.py` | 確率キャリブレーション |
| 2 | `data/calibration_data.json` | キャリブレーションデータ |
| 3 | `src/prediction/bayesian_hierarchical_model.py` | ベイズ階層モデル |
| 3 | `src/betting/rl_optimizer.py` | 強化学習最適化 |
| - | `config/feature_flags.py` | 機能フラグ管理 |
| - | `ui/components/monitoring_dashboard.py` | モニタリングUI |

### 7.2 変更が必要な既存ファイル

| ファイルパス | 変更内容 |
|------------|---------|
| `src/analysis/race_predictor.py` | 動的統合、信頼度細分化、キャリブレーション統合 |
| `src/analysis/beforeinfo_scorer.py` | 信頼度計算の改良 |
| `src/analysis/extended_scorer.py` | 進入予測モデル統合 |
| `src/analysis/compound_buff_system.py` | 自動学習との連携 |
| `config/settings.py` | 新設定項目の追加 |
| `tests/test_core_logic.py` | 新機能のテスト追加 |

### 7.3 ドキュメント更新箇所

| ドキュメント | 更新内容 |
|------------|---------|
| `README.md` | 新機能の説明追加 |
| `docs/architecture.md` | システム構成図更新 |
| `docs/configuration.md` | 新設定項目の説明 |
| `docs/api_reference.md` | 新APIの仕様 |

---

## 付録: 実装優先度サマリー

### 即時実装（Phase 1）- 合計18.5時間

1. **動的合成比導入** (6時間)
   - 投資対効果: 高（固定比率の問題を解消）

2. **進入予測モデル** (8.5時間)
   - 投資対効果: 高（進入崩れの影響を正確に反映）

3. **信頼度スコア明確化** (4時間)
   - 投資対効果: 中（統合時の判断材料改善）

### 数週間以内（Phase 2）- 合計23.5時間

4. **複合バフ自動学習** (9時間)
5. **信頼度細分化** (5.5時間)
6. **キャリブレーション** (9時間)

### 中長期（Phase 3）- 合計60時間

7. **ベイズ階層モデル** (20時間)
8. **強化学習最適化** (40時間)

---

**作成完了**: 2024年12月2日
