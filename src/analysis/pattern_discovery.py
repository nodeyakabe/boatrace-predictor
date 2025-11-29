"""
複合条件パターン自動発見システム

目的:
- 会場×環境×コース×選手特性の組み合わせで有意なパターンを発見
- 統計的信頼性を検証（サンプル数、信頼区間、有意性検定）
- 反証条件（バフが発生しない条件）も特定

分析対象:
1. 会場別の決まり手傾向
2. 会場×潮位×コースの勝率
3. 会場×風向×風速×決まり手
4. 選手の決まり手得意パターン
5. モーターの会場別パフォーマンス
"""

import sqlite3
import math
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
import json
from datetime import datetime, timedelta


@dataclass
class PatternResult:
    """パターン分析結果"""
    pattern_id: str
    description: str
    conditions: Dict[str, Any]
    sample_count: int
    win_rate: float  # 1着率
    place_rate: float  # 3着内率
    baseline_win_rate: float  # ベースライン勝率（比較対象）
    lift: float  # リフト値（win_rate / baseline）
    confidence_interval: Tuple[float, float]  # 95%信頼区間
    is_significant: bool  # 統計的に有意か
    p_value: float  # p値
    effect_size: float  # 効果量（バフ値の推奨）
    counter_conditions: List[Dict]  # 反証条件
    reliability_score: float  # 信頼性スコア（0-100）


class PatternDiscovery:
    """複合条件パターン発見システム"""

    # 分析に必要な最小サンプル数
    MIN_SAMPLE_SIZE = 30

    # 有意水準
    SIGNIFICANCE_LEVEL = 0.05

    # 会場コードと名前のマッピング
    VENUE_NAMES = {
        '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
        '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
        '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
        '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
        '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
        '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
    }

    # 海水会場
    SEAWATER_VENUES = ['03', '06', '10', '14', '15', '16', '17', '18',
                       '19', '20', '21', '22', '23', '24']

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def _get_connection(self):
        """DB接続を取得"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _calculate_confidence_interval(self, p: float, n: int, z: float = 1.96) -> Tuple[float, float]:
        """
        二項分布の信頼区間を計算（Wilson法）

        Args:
            p: 勝率
            n: サンプル数
            z: z値（95%信頼区間なら1.96）

        Returns:
            (下限, 上限)
        """
        if n == 0:
            return (0.0, 1.0)

        denominator = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denominator
        margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denominator

        return (max(0, center - margin), min(1, center + margin))

    def _calculate_p_value(self, observed: int, total: int, expected_rate: float) -> float:
        """
        二項検定のp値を計算（近似）

        Args:
            observed: 観測された成功数
            total: 試行数
            expected_rate: 期待される成功率

        Returns:
            p値
        """
        if total == 0 or expected_rate <= 0 or expected_rate >= 1:
            return 1.0

        expected = total * expected_rate
        variance = total * expected_rate * (1 - expected_rate)

        if variance <= 0:
            return 1.0

        z = (observed - expected) / math.sqrt(variance)

        # 正規分布近似でp値を計算（両側検定）
        # 簡易的なp値計算
        p_value = 2 * (1 - self._normal_cdf(abs(z)))

        return p_value

    def _normal_cdf(self, x: float) -> float:
        """標準正規分布のCDF（近似）"""
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def _calculate_reliability_score(
        self,
        sample_count: int,
        p_value: float,
        lift: float,
        ci_width: float
    ) -> float:
        """
        信頼性スコアを計算

        Args:
            sample_count: サンプル数
            p_value: p値
            lift: リフト値
            ci_width: 信頼区間の幅

        Returns:
            0-100のスコア
        """
        score = 0.0

        # サンプル数（最大40点）
        if sample_count >= 500:
            score += 40
        elif sample_count >= 200:
            score += 30
        elif sample_count >= 100:
            score += 20
        elif sample_count >= 50:
            score += 10
        else:
            score += sample_count / 5

        # p値（最大30点）
        if p_value < 0.001:
            score += 30
        elif p_value < 0.01:
            score += 25
        elif p_value < 0.05:
            score += 15
        elif p_value < 0.10:
            score += 5

        # リフト値（最大20点）
        if lift >= 2.0:
            score += 20
        elif lift >= 1.5:
            score += 15
        elif lift >= 1.2:
            score += 10
        elif lift >= 1.1:
            score += 5

        # 信頼区間の狭さ（最大10点）
        if ci_width < 0.05:
            score += 10
        elif ci_width < 0.10:
            score += 7
        elif ci_width < 0.15:
            score += 4
        elif ci_width < 0.20:
            score += 2

        return min(100, score)

    # ========================================
    # 会場別分析
    # ========================================

    def analyze_venue_course_kimarite(self, venue_code: str, days: int = 365) -> List[PatternResult]:
        """
        会場×コース×決まり手のパターンを分析

        決まり手は1着の艇にのみ記録されるため、
        「あるコースで特定の決まり手による1着が多いか」を分析する。

        Args:
            venue_code: 会場コード
            days: 分析期間（日数）

        Returns:
            発見されたパターンのリスト
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        venue_name = self.VENUE_NAMES.get(venue_code, f'会場{venue_code}')

        patterns = []

        # 全体のコース別勝率（ベースライン）
        cursor.execute("""
            SELECT rd.actual_course, COUNT(*) as total,
                   SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins
            FROM race_details rd
            JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            JOIN races r ON rd.race_id = r.id
            WHERE r.venue_code = ? AND r.race_date >= ?
              AND rd.actual_course IS NOT NULL
            GROUP BY rd.actual_course
        """, (venue_code, cutoff_date))

        baseline_rates = {}
        total_races_per_course = {}
        for row in cursor.fetchall():
            course = row['actual_course']
            if course and row['total'] > 0:
                baseline_rates[course] = row['wins'] / row['total']
                total_races_per_course[course] = row['total']

        # 決まり手別の分析（1着の決まり手がどのコースから発生したか）
        # 決まり手は1着にのみ付くので、決まり手の発生回数＝そのコースの1着回数（その決まり手で）
        cursor.execute("""
            SELECT rd.actual_course, res.kimarite, COUNT(*) as kimarite_wins
            FROM race_details rd
            JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            JOIN races r ON rd.race_id = r.id
            WHERE r.venue_code = ? AND r.race_date >= ?
              AND res.rank = '1'
              AND res.kimarite IS NOT NULL AND res.kimarite != ''
              AND rd.actual_course IS NOT NULL
            GROUP BY rd.actual_course, res.kimarite
            HAVING kimarite_wins >= ?
        """, (venue_code, cutoff_date, self.MIN_SAMPLE_SIZE))

        for row in cursor.fetchall():
            course = row['actual_course']
            kimarite = row['kimarite']
            kimarite_wins = row['kimarite_wins']

            if not course or course not in total_races_per_course:
                continue

            total_races = total_races_per_course[course]
            baseline = baseline_rates.get(course, 0.1)

            # この決まり手での勝率 = (その決まり手での1着回数) / (そのコースの出走回数)
            win_rate = kimarite_wins / total_races if total_races > 0 else 0

            # リフト値の計算方法を変更
            # 全会場での同コース同決まり手の平均勝率と比較したい
            # 簡易的に、そのコースの全勝率に対する比率で表現
            # 例: 1コース逃げ率50%、全体の1コース勝率55% → 逃げ率は高いのでリフト高
            if baseline > 0:
                lift = win_rate / baseline * (1 / 0.5)  # 決まり手が勝利の50%を占めるのを基準
            else:
                lift = 1.0

            # 信頼区間
            ci = self._calculate_confidence_interval(win_rate, total_races)
            ci_width = ci[1] - ci[0]

            # p値（二項検定）
            # 期待値 = 全体勝率の半分（その決まり手が使われる確率として）
            expected_kimarite_rate = baseline * 0.5  # 簡易的な期待値
            p_value = self._calculate_p_value(kimarite_wins, total_races, expected_kimarite_rate)

            # 有意性判定：この会場・コースでこの決まり手が特に多いか
            is_significant = p_value < self.SIGNIFICANCE_LEVEL and win_rate > baseline * 0.4

            # 信頼性スコア
            reliability = self._calculate_reliability_score(kimarite_wins, p_value, lift, ci_width)

            # 効果量（推奨バフ値）- 決まり手率がコース全体勝率の何%を占めるか
            kimarite_contribution = (win_rate / baseline) if baseline > 0 else 0
            effect_size = kimarite_contribution * 10  # 0-10点の範囲

            # パターン名に決まり手率を含める
            kimarite_pct = win_rate * 100

            if reliability >= 20 and kimarite_wins >= self.MIN_SAMPLE_SIZE:
                patterns.append(PatternResult(
                    pattern_id=f"venue_{venue_code}_course_{course}_kimarite_{kimarite}",
                    description=f"{venue_name}{course}コースの{kimarite}({kimarite_pct:.1f}%)",
                    conditions={
                        'venue': venue_code,
                        'course': course,
                        'kimarite': kimarite
                    },
                    sample_count=kimarite_wins,
                    win_rate=win_rate,
                    place_rate=0,  # 決まり手は1着のみなので3着内率は意味がない
                    baseline_win_rate=baseline,
                    lift=kimarite_contribution,
                    confidence_interval=ci,
                    is_significant=is_significant,
                    p_value=p_value,
                    effect_size=effect_size,
                    counter_conditions=[],
                    reliability_score=reliability
                ))

        conn.close()

        # 信頼性スコア順にソート
        patterns.sort(key=lambda x: -x.reliability_score)

        return patterns

    def analyze_venue_tide_patterns(self, venue_code: str, days: int = 365) -> List[PatternResult]:
        """
        会場×潮位のパターンを分析

        Args:
            venue_code: 会場コード
            days: 分析期間

        Returns:
            発見されたパターン
        """
        if venue_code not in self.SEAWATER_VENUES:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        venue_name = self.VENUE_NAMES.get(venue_code, f'会場{venue_code}')

        patterns = []

        # 潮位カテゴリ別の分析
        # 潮位データと結果を結合
        cursor.execute("""
            SELECT
                CASE
                    WHEN rtd.sea_level_cm >= 150 THEN '満潮'
                    WHEN rtd.sea_level_cm >= 100 THEN '中潮'
                    ELSE '干潮'
                END as tide_category,
                rd.actual_course,
                COUNT(*) as total,
                SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins
            FROM race_tide_data rtd
            JOIN race_details rd ON rtd.race_id = rd.race_id
            JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            JOIN races r ON rtd.race_id = r.id
            WHERE r.venue_code = ? AND r.race_date >= ?
            GROUP BY tide_category, rd.actual_course
            HAVING total >= ?
        """, (venue_code, cutoff_date, self.MIN_SAMPLE_SIZE))

        # 全体のコース別勝率（ベースライン）
        cursor.execute("""
            SELECT rd.actual_course,
                   COUNT(*) as total,
                   SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins
            FROM race_details rd
            JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            JOIN races r ON rd.race_id = r.id
            WHERE r.venue_code = ? AND r.race_date >= ?
            GROUP BY rd.actual_course
        """, (venue_code, cutoff_date))

        baseline_rates = {}
        for row in cursor.fetchall():
            if row['total'] > 0:
                baseline_rates[row['actual_course']] = row['wins'] / row['total']

        # 潮位×コースの分析結果を取得
        cursor.execute("""
            SELECT
                CASE
                    WHEN rtd.sea_level_cm >= 150 THEN '満潮'
                    WHEN rtd.sea_level_cm >= 100 THEN '中潮'
                    ELSE '干潮'
                END as tide_category,
                rd.actual_course,
                COUNT(*) as total,
                SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as places
            FROM race_tide_data rtd
            JOIN race_details rd ON rtd.race_id = rd.race_id
            JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            JOIN races r ON rtd.race_id = r.id
            WHERE r.venue_code = ? AND r.race_date >= ?
            GROUP BY tide_category, rd.actual_course
            HAVING total >= ?
        """, (venue_code, cutoff_date, self.MIN_SAMPLE_SIZE))

        for row in cursor.fetchall():
            tide = row['tide_category']
            course = row['actual_course']
            total = row['total']
            wins = row['wins']
            places = row['places']

            win_rate = wins / total if total > 0 else 0
            place_rate = places / total if total > 0 else 0
            baseline = baseline_rates.get(course, 0.1)

            if baseline > 0:
                lift = win_rate / baseline
            else:
                lift = 1.0

            ci = self._calculate_confidence_interval(win_rate, total)
            ci_width = ci[1] - ci[0]
            p_value = self._calculate_p_value(wins, total, baseline)
            is_significant = p_value < self.SIGNIFICANCE_LEVEL and abs(lift - 1.0) > 0.1
            reliability = self._calculate_reliability_score(total, p_value, lift, ci_width)
            effect_size = (win_rate - baseline) * 100

            if is_significant and reliability >= 30:
                patterns.append(PatternResult(
                    pattern_id=f"venue_{venue_code}_tide_{tide}_course_{course}",
                    description=f"{venue_name}の{tide}時{course}コース",
                    conditions={
                        'venue': venue_code,
                        'tide': tide,
                        'course': course
                    },
                    sample_count=total,
                    win_rate=win_rate,
                    place_rate=place_rate,
                    baseline_win_rate=baseline,
                    lift=lift,
                    confidence_interval=ci,
                    is_significant=is_significant,
                    p_value=p_value,
                    effect_size=effect_size,
                    counter_conditions=[],
                    reliability_score=reliability
                ))

        conn.close()
        patterns.sort(key=lambda x: -x.reliability_score)

        return patterns

    # ========================================
    # 選手別分析
    # ========================================

    def analyze_racer_kimarite_patterns(self, racer_number: str, days: int = 365) -> List[PatternResult]:
        """
        選手の決まり手パターンを分析

        Args:
            racer_number: 選手登録番号
            days: 分析期間

        Returns:
            発見されたパターン
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        patterns = []

        # 選手名を取得
        cursor.execute("""
            SELECT DISTINCT racer_name FROM entries WHERE racer_number = ? LIMIT 1
        """, (racer_number,))
        row = cursor.fetchone()
        racer_name = row['racer_name'] if row else f'選手{racer_number}'

        # コース別決まり手の分析
        cursor.execute("""
            SELECT rd.actual_course, res.kimarite,
                   COUNT(*) as total,
                   SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as places
            FROM race_details rd
            JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            JOIN races r ON rd.race_id = r.id
            WHERE e.racer_number = ? AND r.race_date >= ?
              AND res.kimarite IS NOT NULL AND res.kimarite != ''
            GROUP BY rd.actual_course, res.kimarite
            HAVING total >= 10
        """, (racer_number, cutoff_date))

        # 全体の決まり手別勝率（ベースライン）
        cursor.execute("""
            SELECT res.kimarite, rd.actual_course,
                   COUNT(*) as total,
                   SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins
            FROM race_details rd
            JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            JOIN races r ON rd.race_id = r.id
            WHERE r.race_date >= ? AND res.kimarite IS NOT NULL
            GROUP BY res.kimarite, rd.actual_course
        """, (cutoff_date,))

        baseline_rates = {}
        for row in cursor.fetchall():
            key = (row['actual_course'], row['kimarite'])
            if row['total'] > 0:
                baseline_rates[key] = row['wins'] / row['total']

        # 選手の分析を再取得
        cursor.execute("""
            SELECT rd.actual_course, res.kimarite,
                   COUNT(*) as total,
                   SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as places
            FROM race_details rd
            JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            JOIN races r ON rd.race_id = r.id
            WHERE e.racer_number = ? AND r.race_date >= ?
              AND res.kimarite IS NOT NULL AND res.kimarite != ''
            GROUP BY rd.actual_course, res.kimarite
            HAVING total >= 10
        """, (racer_number, cutoff_date))

        for row in cursor.fetchall():
            course = row['actual_course']
            kimarite = row['kimarite']
            total = row['total']
            wins = row['wins']
            places = row['places']

            win_rate = wins / total if total > 0 else 0
            place_rate = places / total if total > 0 else 0
            baseline = baseline_rates.get((course, kimarite), 0.1)

            if baseline > 0:
                lift = win_rate / baseline
            else:
                lift = 1.0

            ci = self._calculate_confidence_interval(win_rate, total)
            ci_width = ci[1] - ci[0]
            p_value = self._calculate_p_value(wins, total, baseline)
            is_significant = p_value < self.SIGNIFICANCE_LEVEL and lift > 1.2
            reliability = self._calculate_reliability_score(total, p_value, lift, ci_width)
            effect_size = (win_rate - baseline) * 100

            if reliability >= 20:  # 選手分析は緩めの基準
                patterns.append(PatternResult(
                    pattern_id=f"racer_{racer_number}_course_{course}_kimarite_{kimarite}",
                    description=f"{racer_name}の{course}コース{kimarite}",
                    conditions={
                        'racer_number': racer_number,
                        'course': course,
                        'kimarite': kimarite
                    },
                    sample_count=total,
                    win_rate=win_rate,
                    place_rate=place_rate,
                    baseline_win_rate=baseline,
                    lift=lift,
                    confidence_interval=ci,
                    is_significant=is_significant,
                    p_value=p_value,
                    effect_size=effect_size,
                    counter_conditions=[],
                    reliability_score=reliability
                ))

        conn.close()
        patterns.sort(key=lambda x: -x.reliability_score)

        return patterns

    def analyze_venue_tide_kimarite_patterns(self, venue_code: str, days: int = 365) -> List[PatternResult]:
        """
        会場×潮位×コース×決まり手の複合パターンを分析

        例: 福岡で満潮時に3コースからまくりが決まりやすい

        Args:
            venue_code: 会場コード
            days: 分析期間

        Returns:
            発見されたパターン
        """
        if venue_code not in self.SEAWATER_VENUES:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        venue_name = self.VENUE_NAMES.get(venue_code, f'会場{venue_code}')

        patterns = []

        # ベースライン（コース別勝率）
        cursor.execute("""
            SELECT rd.actual_course,
                   COUNT(*) as total,
                   SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins
            FROM race_details rd
            JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            JOIN races r ON rd.race_id = r.id
            WHERE r.venue_code = ? AND r.race_date >= ?
              AND rd.actual_course IS NOT NULL
            GROUP BY rd.actual_course
        """, (venue_code, cutoff_date))

        baseline_rates = {}
        total_races = {}
        for row in cursor.fetchall():
            course = row['actual_course']
            if course:
                baseline_rates[course] = row['wins'] / row['total'] if row['total'] > 0 else 0
                total_races[course] = row['total']

        # 潮位×コース×決まり手の分析
        cursor.execute("""
            SELECT
                CASE
                    WHEN rtd.sea_level_cm >= 150 THEN '満潮'
                    WHEN rtd.sea_level_cm >= 100 THEN '中潮'
                    ELSE '干潮'
                END as tide_category,
                rd.actual_course,
                res.kimarite,
                COUNT(*) as kimarite_wins
            FROM race_tide_data rtd
            JOIN race_details rd ON rtd.race_id = rd.race_id
            JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            JOIN races r ON rtd.race_id = r.id
            WHERE r.venue_code = ? AND r.race_date >= ?
              AND res.rank = '1'
              AND res.kimarite IS NOT NULL AND res.kimarite != ''
              AND rd.actual_course IS NOT NULL
            GROUP BY tide_category, rd.actual_course, res.kimarite
            HAVING kimarite_wins >= 15
        """, (venue_code, cutoff_date))

        for row in cursor.fetchall():
            tide = row['tide_category']
            course = row['actual_course']
            kimarite = row['kimarite']
            wins = row['kimarite_wins']

            if not course or course not in total_races:
                continue

            total = total_races.get(course, 1)
            baseline = baseline_rates.get(course, 0.1)

            win_rate = wins / total if total > 0 else 0
            ci = self._calculate_confidence_interval(win_rate, total)
            ci_width = ci[1] - ci[0]
            kimarite_contribution = (win_rate / baseline) if baseline > 0 else 0
            effect_size = kimarite_contribution * 10
            expected = baseline * 0.3
            p_value = self._calculate_p_value(wins, total, expected)
            reliability = self._calculate_reliability_score(wins, p_value, kimarite_contribution, ci_width)

            if reliability >= 25 and wins >= 15:
                patterns.append(PatternResult(
                    pattern_id=f"venue_{venue_code}_tide_{tide}_course_{course}_kimarite_{kimarite}",
                    description=f"{venue_name}{tide}時{course}コースの{kimarite}({win_rate*100:.1f}%)",
                    conditions={
                        'venue': venue_code,
                        'tide': tide,
                        'course': course,
                        'kimarite': kimarite
                    },
                    sample_count=wins,
                    win_rate=win_rate,
                    place_rate=0,
                    baseline_win_rate=baseline,
                    lift=kimarite_contribution,
                    confidence_interval=ci,
                    is_significant=p_value < self.SIGNIFICANCE_LEVEL,
                    p_value=p_value,
                    effect_size=effect_size,
                    counter_conditions=[],
                    reliability_score=reliability
                ))

        conn.close()
        patterns.sort(key=lambda x: -x.reliability_score)
        return patterns

    def analyze_racer_venue_patterns(self, racer_number: str, days: int = 730) -> List[PatternResult]:
        """
        選手の得意会場・得意コースパターンを分析

        Args:
            racer_number: 選手登録番号
            days: 分析期間（2年程度推奨）

        Returns:
            発見されたパターン
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        patterns = []

        cursor.execute("SELECT DISTINCT racer_name FROM entries WHERE racer_number = ? LIMIT 1", (racer_number,))
        row = cursor.fetchone()
        racer_name = row['racer_name'] if row else f'選手{racer_number}'

        cursor.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins
            FROM entries e
            JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            JOIN races r ON e.race_id = r.id
            WHERE e.racer_number = ? AND r.race_date >= ?
        """, (racer_number, cutoff_date))

        row = cursor.fetchone()
        if not row or row['total'] < 30:
            conn.close()
            return patterns

        overall_win_rate = row['wins'] / row['total'] if row['total'] > 0 else 0

        cursor.execute("""
            SELECT r.venue_code, rd.actual_course,
                   COUNT(*) as total,
                   SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN CAST(res.rank AS INTEGER) <= 3 THEN 1 ELSE 0 END) as places
            FROM entries e
            JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
            JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
            JOIN races r ON e.race_id = r.id
            WHERE e.racer_number = ? AND r.race_date >= ?
              AND rd.actual_course IS NOT NULL
            GROUP BY r.venue_code, rd.actual_course
            HAVING total >= 10
        """, (racer_number, cutoff_date))

        for row in cursor.fetchall():
            venue_code = row['venue_code']
            course = row['actual_course']
            total = row['total']
            wins = row['wins']
            places = row['places']

            venue_name = self.VENUE_NAMES.get(venue_code, f'会場{venue_code}')
            win_rate = wins / total if total > 0 else 0
            place_rate = places / total if total > 0 else 0
            lift = win_rate / overall_win_rate if overall_win_rate > 0 else 1.0

            ci = self._calculate_confidence_interval(win_rate, total)
            ci_width = ci[1] - ci[0]
            p_value = self._calculate_p_value(wins, total, overall_win_rate)
            reliability = self._calculate_reliability_score(total, p_value, lift, ci_width)
            effect_size = (win_rate - overall_win_rate) * 50

            if reliability >= 20 and lift > 1.2:
                patterns.append(PatternResult(
                    pattern_id=f"racer_{racer_number}_venue_{venue_code}_course_{course}",
                    description=f"{racer_name}の{venue_name}{course}コース({win_rate*100:.1f}%)",
                    conditions={
                        'racer_number': racer_number,
                        'venue': venue_code,
                        'course': course
                    },
                    sample_count=total,
                    win_rate=win_rate,
                    place_rate=place_rate,
                    baseline_win_rate=overall_win_rate,
                    lift=lift,
                    confidence_interval=ci,
                    is_significant=p_value < self.SIGNIFICANCE_LEVEL,
                    p_value=p_value,
                    effect_size=effect_size,
                    counter_conditions=[],
                    reliability_score=reliability
                ))

        conn.close()
        patterns.sort(key=lambda x: -x.reliability_score)
        return patterns

    # ========================================
    # 総合分析
    # ========================================

    def discover_all_venue_patterns(self, days: int = 365) -> Dict[str, List[PatternResult]]:
        """
        全会場のパターンを発見

        Args:
            days: 分析期間

        Returns:
            {会場コード: [パターンリスト]}
        """
        all_patterns = {}

        for venue_code in self.VENUE_NAMES.keys():
            venue_patterns = []

            # 決まり手パターン
            kimarite_patterns = self.analyze_venue_course_kimarite(venue_code, days)
            venue_patterns.extend(kimarite_patterns)

            # 潮位パターン（海水会場のみ）
            tide_patterns = self.analyze_venue_tide_patterns(venue_code, days)
            venue_patterns.extend(tide_patterns)

            # 潮位×決まり手複合パターン
            tide_kimarite_patterns = self.analyze_venue_tide_kimarite_patterns(venue_code, days)
            venue_patterns.extend(tide_kimarite_patterns)

            if venue_patterns:
                all_patterns[venue_code] = venue_patterns

        return all_patterns

    def find_counter_conditions(self, pattern: PatternResult, days: int = 365) -> List[Dict]:
        """
        パターンの反証条件を探す
        （条件を満たしていてもバフが発生しないケース）

        Args:
            pattern: 検証するパターン
            days: 分析期間

        Returns:
            反証条件のリスト
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        counter_conditions = []
        conditions = pattern.conditions

        # 会場×コース×決まり手パターンの反証条件を探す
        if 'venue' in conditions and 'course' in conditions:
            venue_code = conditions['venue']
            course = conditions['course']

            # 選手ランク別の成績を確認
            cursor.execute("""
                SELECT e.racer_rank,
                       COUNT(*) as total,
                       SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as wins
                FROM race_details rd
                JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
                JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
                JOIN races r ON rd.race_id = r.id
                WHERE r.venue_code = ? AND rd.actual_course = ? AND r.race_date >= ?
                GROUP BY e.racer_rank
                HAVING total >= ?
            """, (venue_code, course, cutoff_date, self.MIN_SAMPLE_SIZE))

            for row in cursor.fetchall():
                rank = row['racer_rank']
                total = row['total']
                wins = row['wins']
                win_rate = wins / total if total > 0 else 0

                # パターンの勝率より大幅に低い場合は反証条件
                if win_rate < pattern.win_rate * 0.7:
                    counter_conditions.append({
                        'type': 'racer_rank',
                        'value': rank,
                        'description': f'{rank}級選手では効果薄い',
                        'win_rate': win_rate,
                        'sample_count': total
                    })

        conn.close()

        return counter_conditions

    def generate_report(self, venue_code: str, days: int = 365) -> str:
        """
        会場の分析レポートを生成

        Args:
            venue_code: 会場コード
            days: 分析期間

        Returns:
            レポート文字列
        """
        venue_name = self.VENUE_NAMES.get(venue_code, f'会場{venue_code}')

        lines = []
        lines.append(f"{'=' * 70}")
        lines.append(f"【{venue_name}】複合条件パターン分析レポート")
        lines.append(f"分析期間: 過去{days}日間")
        lines.append(f"{'=' * 70}")
        lines.append("")

        # 決まり手パターン
        lines.append("■ コース別決まり手分布")
        lines.append("-" * 50)

        kimarite_patterns = self.analyze_venue_course_kimarite(venue_code, days)
        if kimarite_patterns:
            for p in kimarite_patterns[:15]:
                lines.append(f"  {p.description}")
                lines.append(f"    決まり手率: {p.win_rate*100:.1f}% (コース勝率: {p.baseline_win_rate*100:.1f}%)")
                lines.append(f"    貢献度: {p.lift:.1%}, サンプル数: {p.sample_count}回")
                lines.append(f"    信頼性: {p.reliability_score:.0f}/100")
                if p.effect_size > 5:
                    lines.append(f"    ★ 推奨バフ: +{p.effect_size:.1f}点（この決まり手が得意な選手に有効）")
                lines.append("")
        else:
            lines.append("  有意なパターンなし")
            lines.append("")

        # 潮位パターン
        if venue_code in self.SEAWATER_VENUES:
            lines.append("■ 潮位×コースパターン")
            lines.append("-" * 50)

            tide_patterns = self.analyze_venue_tide_patterns(venue_code, days)
            if tide_patterns:
                for p in tide_patterns[:10]:
                    lines.append(f"  {p.description}")
                    lines.append(f"    勝率: {p.win_rate*100:.1f}% (全体: {p.baseline_win_rate*100:.1f}%)")
                    lines.append(f"    リフト: {p.lift:.2f}倍, サンプル数: {p.sample_count}")
                    lines.append(f"    信頼性: {p.reliability_score:.0f}/100")
                    lines.append(f"    推奨バフ: {p.effect_size:+.1f}点")
                    lines.append("")
            else:
                lines.append("  有意なパターンなし")
                lines.append("")

        lines.append("=" * 70)

        return "\n".join(lines)


if __name__ == "__main__":
    discovery = PatternDiscovery()

    # 福岡のパターンを分析
    print(discovery.generate_report('22', days=365))

    print("\n" + "=" * 70)

    # 大村のパターンを分析
    print(discovery.generate_report('24', days=365))
