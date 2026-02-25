"""
拡張スコアリングモジュール

追加の予測要素を実装:
1. 選手級別スコア（A1/A2/B1/B2）
2. F/L持ちペナルティ
3. 節間成績分析
4. 前走レベル評価
5. 進入コース予測
6. 選手間相性分析
7. モーター特性分析
"""
import sqlite3
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH, EXTENDED_SCORE_WEIGHTS
from config.feature_flags import is_feature_enabled
from src.utils.db_connection_pool import get_connection


class ExtendedScorer:
    """拡張スコアリング"""

    # 級別基準スコア（max_score=10として）
    CLASS_SCORES = {
        'A1': 10.0,  # トップ選手
        'A2': 7.0,   # 上位選手
        'B1': 4.0,   # 中堅選手
        'B2': 1.0,   # 新人・下位選手
    }

    # F/Lペナルティ（1回あたり）
    FL_PENALTIES = {
        'F': -3.0,  # フライング1回で-3点
        'L': -1.5,  # 出遅れ1回で-1.5点
    }

    # 平均STスコア基準（勝率との相関に基づく）
    # ST 0.10-0.15が最も勝率高い（24.38%）、0.20以上は低い（9.64%）
    ST_SCORE_RANGES = [
        (0.00, 0.10, 0.7),   # 早すぎ（Fリスク）
        (0.10, 0.15, 1.0),   # 最適（最高勝率）
        (0.15, 0.18, 0.8),   # 良好
        (0.18, 0.20, 0.6),   # やや遅い
        (0.20, 1.00, 0.4),   # 遅い
    ]

    # 進入コース予測用：枠番別の進入傾向（デフォルト）
    DEFAULT_COURSE_TENDENCY = {
        1: {1: 0.98, 2: 0.02},  # 1号艇は98%で1コース
        2: {1: 0.01, 2: 0.95, 3: 0.04},
        3: {2: 0.02, 3: 0.93, 4: 0.05},
        4: {3: 0.03, 4: 0.90, 5: 0.07},
        5: {4: 0.05, 5: 0.85, 6: 0.10},
        6: {5: 0.08, 6: 0.92},
    }

    # 逃げ率スコア基準（1コース艇のみ適用）
    # 全国平均逃げ率は約55%
    ESCAPE_RATE_THRESHOLDS = {
        'excellent': 0.70,  # 70%以上: 優秀 (+3pt)
        'good': 0.60,       # 60-70%: 良好 (+1.5pt)
        'average': 0.50,    # 50-60%: 平均 (±0pt)
        'poor': 0.45,       # 45-50%: やや低い (-1pt)
        # 45%未満: 低い (-2pt)
    }

    # 会場攻撃率スコア基準（コース3-5に適用）
    # 全国平均: まくり率約21.5%, 差し率約18.8%
    VENUE_ATTACK_THRESHOLDS = {
        'makuri': {
            'high': 0.25,       # 25%以上: まくり有利場 (+2pt for 3-4C)
            'average': 0.20,    # 20-25%: 平均 (±0pt)
            # 20%未満: まくり不利場 (-1pt for 3-4C)
        },
        'sashi': {
            'high': 0.22,       # 22%以上: 差し有利場 (+2pt for 2,5C)
            'average': 0.17,    # 17-22%: 平均 (±0pt)
            # 17%未満: 差し不利場 (-1pt for 2,5C)
        }
    }

    def __init__(self, db_path: str = None, batch_loader=None):
        self.db_path = db_path or DATABASE_PATH
        self.batch_loader = batch_loader
        # 逃げ率キャッシュ（レース毎にリセット不要、選手IDでキャッシュ）
        self._escape_rate_cache = {}
        # 会場攻撃率キャッシュ（会場コードでキャッシュ）
        self._venue_attack_cache = {}
        # モーター転覆ペナルティキャッシュ（(motor_number, venue_code) -> result）
        self._capsizing_cache = {}
        # 会場相性スコアキャッシュ（(racer_number, venue_code) -> result）
        self._venue_affinity_cache = {}

    def calculate_escape_rate_score(
        self,
        racer_number: str,
        pit_number: int,
        venue_code: str = None,
        max_score: float = 5.0
    ) -> Dict:
        """
        逃げ率スコアを計算（1コース艇のみ）

        Args:
            racer_number: 選手番号
            pit_number: 枠番（1のみ適用）
            venue_code: 会場コード（当地逃げ率を優先する場合）
            max_score: 最大スコア（デフォルト5.0点）

        Returns:
            {
                'score': float,           # スコア（-2.0 〜 +3.0）
                'escape_rate': float,     # 逃げ率（0.0-1.0）
                'is_local': bool,         # 当地逃げ率を使用したか
                'races_count': int,       # 母数
                'level': str,             # excellent/good/average/poor/low
                'description': str
            }
        """
        # 1コース以外は適用しない
        if pit_number != 1:
            return {
                'score': 0.0,
                'escape_rate': None,
                'is_local': False,
                'races_count': 0,
                'level': 'not_applicable',
                'description': '1コース以外は逃げ率スコア適用外'
            }

        # キャッシュチェック
        cache_key = f"{racer_number}_{venue_code or 'national'}"
        if cache_key in self._escape_rate_cache:
            return self._escape_rate_cache[cache_key]

        # DBから逃げ率を取得
        escape_rate = None
        is_local = False
        races_count = 0

        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            # 当地逃げ率を優先（venue_codeが指定されている場合）
            if venue_code:
                cursor.execute("""
                    SELECT escape_rate, races_1course
                    FROM player_escape_stats
                    WHERE player_id = ? AND stadium_id = ?
                    ORDER BY updated_at DESC LIMIT 1
                """, (str(racer_number), venue_code))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    escape_rate = row[0]
                    races_count = row[1]
                    is_local = True

            # 当地がない場合は全国逃げ率
            if escape_rate is None:
                cursor.execute("""
                    SELECT escape_rate, races_1course
                    FROM player_escape_stats
                    WHERE player_id = ? AND stadium_id IS NULL
                    ORDER BY updated_at DESC LIMIT 1
                """, (str(racer_number),))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    escape_rate = row[0]
                    races_count = row[1]
                    is_local = False

            cursor.close()
        except Exception as e:
            # エラー時はデフォルト値
            pass

        # 逃げ率が取得できない場合
        if escape_rate is None:
            result = {
                'score': 0.0,
                'escape_rate': None,
                'is_local': False,
                'races_count': 0,
                'level': 'unknown',
                'description': '逃げ率データなし（中立）'
            }
            self._escape_rate_cache[cache_key] = result
            return result

        # スコア計算
        thresholds = self.ESCAPE_RATE_THRESHOLDS
        if escape_rate >= thresholds['excellent']:
            score = 3.0
            level = 'excellent'
            desc = f'逃げ率{escape_rate:.1%}（優秀）'
        elif escape_rate >= thresholds['good']:
            score = 1.5
            level = 'good'
            desc = f'逃げ率{escape_rate:.1%}（良好）'
        elif escape_rate >= thresholds['average']:
            score = 0.0
            level = 'average'
            desc = f'逃げ率{escape_rate:.1%}（平均）'
        elif escape_rate >= thresholds['poor']:
            score = -1.0
            level = 'poor'
            desc = f'逃げ率{escape_rate:.1%}（やや低い）'
        else:
            score = -2.0
            level = 'low'
            desc = f'逃げ率{escape_rate:.1%}（低い）'

        # 当地データの場合は補足
        if is_local:
            desc += f'【当地/{races_count}走】'
        else:
            desc += f'【全国/{races_count}走】'

        result = {
            'score': score,
            'escape_rate': escape_rate,
            'is_local': is_local,
            'races_count': races_count,
            'level': level,
            'description': desc
        }
        self._escape_rate_cache[cache_key] = result
        return result

    def calculate_venue_attack_score(
        self,
        pit_number: int,
        venue_code: str
    ) -> Dict:
        """
        会場攻撃率スコアを計算（コース2-5に適用）

        - 3-4コース: まくり率の高い会場で+2pt、低い会場で-1pt
        - 2,5コース: 差し率の高い会場で+2pt、低い会場で-1pt
        - 1,6コース: 適用なし（0pt）

        Args:
            pit_number: 枠番（2-5のみ適用）
            venue_code: 会場コード

        Returns:
            {
                'score': float,           # スコア（-1.0 〜 +2.0）
                'makuri_rate': float,     # 会場まくり率
                'sashi_rate': float,      # 会場差し率
                'attack_type': str,       # 適用した攻撃タイプ（'makuri'/'sashi'/None）
                'venue_level': str,       # 会場レベル（'high'/'average'/'low'）
                'description': str
            }
        """
        # デフォルト結果（1コース/6コースまたはデータなし）
        default_result = {
            'score': 0.0,
            'makuri_rate': None,
            'sashi_rate': None,
            'attack_type': None,
            'venue_level': 'not_applicable',
            'description': '会場攻撃率スコア対象外'
        }

        # 1コースと6コースは対象外
        if pit_number == 1 or pit_number == 6:
            return default_result

        if not venue_code:
            return default_result

        # キャッシュチェック
        cache_key = venue_code
        if cache_key in self._venue_attack_cache:
            cached = self._venue_attack_cache[cache_key]
            return self._apply_venue_attack_to_course(cached, pit_number)

        # DBから会場攻撃率を取得
        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT makuri_rate, sashi_rate, total_races
                FROM stadium_attack_stats
                WHERE stadium_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
            ''', (venue_code,))
            row = cursor.fetchone()

            if not row:
                self._venue_attack_cache[cache_key] = None
                return default_result

            makuri_rate, sashi_rate, total_races = row

            # キャッシュに保存
            cached_data = {
                'makuri_rate': makuri_rate,
                'sashi_rate': sashi_rate,
                'total_races': total_races
            }
            self._venue_attack_cache[cache_key] = cached_data

            return self._apply_venue_attack_to_course(cached_data, pit_number)

        except Exception as e:
            return default_result

    def _apply_venue_attack_to_course(self, venue_data: Dict, pit_number: int) -> Dict:
        """
        会場攻撃率をコースに適用してスコアを計算

        Args:
            venue_data: {'makuri_rate', 'sashi_rate', 'total_races'}
            pit_number: 枠番

        Returns:
            スコア結果
        """
        if venue_data is None:
            return {
                'score': 0.0,
                'makuri_rate': None,
                'sashi_rate': None,
                'attack_type': None,
                'venue_level': 'not_applicable',
                'description': '会場データなし'
            }

        makuri_rate = venue_data['makuri_rate']
        sashi_rate = venue_data['sashi_rate']
        thresholds = self.VENUE_ATTACK_THRESHOLDS

        score = 0.0
        attack_type = None
        venue_level = 'average'
        desc = ''

        # 3-4コース: まくり率を適用
        if pit_number in [3, 4]:
            attack_type = 'makuri'
            if makuri_rate >= thresholds['makuri']['high']:
                score = 2.0
                venue_level = 'high'
                desc = f'まくり有利場{makuri_rate:.1%}（{pit_number}C+2pt）'
            elif makuri_rate >= thresholds['makuri']['average']:
                score = 0.0
                venue_level = 'average'
                desc = f'まくり平均場{makuri_rate:.1%}（{pit_number}C±0pt）'
            else:
                score = -1.0
                venue_level = 'low'
                desc = f'まくり不利場{makuri_rate:.1%}（{pit_number}C-1pt）'

        # 2,5コース: 差し率を適用
        elif pit_number in [2, 5]:
            attack_type = 'sashi'
            if sashi_rate >= thresholds['sashi']['high']:
                score = 2.0
                venue_level = 'high'
                desc = f'差し有利場{sashi_rate:.1%}（{pit_number}C+2pt）'
            elif sashi_rate >= thresholds['sashi']['average']:
                score = 0.0
                venue_level = 'average'
                desc = f'差し平均場{sashi_rate:.1%}（{pit_number}C±0pt）'
            else:
                score = -1.0
                venue_level = 'low'
                desc = f'差し不利場{sashi_rate:.1%}（{pit_number}C-1pt）'

        return {
            'score': score,
            'makuri_rate': makuri_rate,
            'sashi_rate': sashi_rate,
            'attack_type': attack_type,
            'venue_level': venue_level,
            'description': desc
        }

    def calculate_class_score(self, racer_rank: str, max_score: float = 10.0) -> Dict:
        """
        選手級別スコアを計算

        Args:
            racer_rank: 級別（A1, A2, B1, B2）
            max_score: 最大スコア

        Returns:
            {'score': float, 'rank': str, 'description': str}
        """
        if not racer_rank:
            return {
                'score': max_score * 0.4,  # 不明時は中間値
                'rank': 'unknown',
                'description': '級別不明'
            }

        base_score = self.CLASS_SCORES.get(racer_rank.upper(), 4.0)
        # 10点満点を max_score に正規化
        score = base_score * (max_score / 10.0)

        descriptions = {
            'A1': 'トップ選手',
            'A2': '上位選手',
            'B1': '中堅選手',
            'B2': '新人・下位選手'
        }

        return {
            'score': score,
            'rank': racer_rank,
            'description': descriptions.get(racer_rank.upper(), '不明')
        }

    def calculate_condition_factor(
        self,
        racer_number: str,
        target_date: str,
        recent_races: int = 20
    ) -> Dict:
        """
        選手の調子係数を計算（P-2タスク: 2025-12-20追加）

        直近N走の着順平均から調子を判定し、級別スコアに適用する係数を算出。
        平均着順3.5を基準とし、好調なら係数>1.0、不調なら係数<1.0。

        Args:
            racer_number: 選手登録番号
            target_date: 対象日付（YYYY-MM-DD）- この日より前のレースを集計
            recent_races: 直近レース数（デフォルト20走）

        Returns:
            {
                'factor': float,          # 調子係数（0.8〜1.2）
                'avg_rank': float,        # 平均着順
                'race_count': int,        # 集計レース数
                'trend': str,             # 'hot'/'normal'/'cold'
                'description': str
            }
        """
        if not racer_number:
            return {
                'factor': 1.0,
                'avg_rank': None,
                'race_count': 0,
                'trend': 'unknown',
                'description': '選手番号不明'
            }

        try:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            # 直近N走の着順を取得
            cursor.execute('''
                SELECT CAST(r.rank AS INTEGER) as rank_int
                FROM results r
                JOIN races ra ON r.race_id = ra.id
                JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
                WHERE e.racer_number = ?
                  AND ra.race_date < ?
                  AND r.rank IS NOT NULL
                  AND r.rank BETWEEN 1 AND 6
                ORDER BY ra.race_date DESC, ra.race_number DESC
                LIMIT ?
            ''', (str(racer_number), target_date, recent_races))

            ranks = [row[0] for row in cursor.fetchall()]
            cursor.close()

            if len(ranks) < 5:
                # データ不足時は中立
                return {
                    'factor': 1.0,
                    'avg_rank': None,
                    'race_count': len(ranks),
                    'trend': 'unknown',
                    'description': f'データ不足（{len(ranks)}走）'
                }

            avg_rank = sum(ranks) / len(ranks)

            # 調子係数の計算
            # 基準: 平均3.5着 → 係数1.0
            # 平均2.0着 → 係数1.15（好調）
            # 平均5.0着 → 係数0.85（不調）
            # 係数 = 1.0 + (3.5 - avg_rank) × 0.1
            factor = 1.0 + (3.5 - avg_rank) * 0.1

            # 係数の範囲制限（0.8〜1.2）
            factor = max(0.8, min(1.2, factor))

            # トレンド判定
            if avg_rank <= 2.5:
                trend = 'hot'
                desc = f'絶好調（平均{avg_rank:.1f}着/{len(ranks)}走）'
            elif avg_rank <= 3.0:
                trend = 'good'
                desc = f'好調（平均{avg_rank:.1f}着/{len(ranks)}走）'
            elif avg_rank <= 4.0:
                trend = 'normal'
                desc = f'普通（平均{avg_rank:.1f}着/{len(ranks)}走）'
            elif avg_rank <= 4.5:
                trend = 'cold'
                desc = f'不調（平均{avg_rank:.1f}着/{len(ranks)}走）'
            else:
                trend = 'slump'
                desc = f'低迷（平均{avg_rank:.1f}着/{len(ranks)}走）'

            return {
                'factor': round(factor, 3),
                'avg_rank': round(avg_rank, 2),
                'race_count': len(ranks),
                'trend': trend,
                'description': desc
            }

        except Exception as e:
            return {
                'factor': 1.0,
                'avg_rank': None,
                'race_count': 0,
                'trend': 'error',
                'description': f'計算エラー: {str(e)}'
            }

    def calculate_start_timing_score(
        self,
        avg_st: float,
        pit_number: int,
        max_score: float = 8.0
    ) -> Dict:
        """
        平均STスコアを計算

        スタートタイミングは勝率に強く影響する。
        0.10-0.15秒が最も勝率が高く（24.38%）、
        0.20秒以上は低い（9.64%）。

        Args:
            avg_st: 平均スタートタイミング（秒）
            pit_number: 枠番（1コースはST影響大）
            max_score: 最大スコア

        Returns:
            {'score': float, 'avg_st': float, 'category': str, 'description': str}
        """
        if avg_st is None or avg_st <= 0:
            return {
                'score': max_score * 0.5,  # データなしは中間
                'avg_st': None,
                'category': 'unknown',
                'description': 'STデータなし'
            }

        # ST範囲に基づくスコア係数を取得
        score_factor = 0.5  # デフォルト
        category = 'average'
        for st_min, st_max, factor in self.ST_SCORE_RANGES:
            if st_min <= avg_st < st_max:
                score_factor = factor
                if factor >= 1.0:
                    category = 'excellent'
                elif factor >= 0.8:
                    category = 'good'
                elif factor >= 0.6:
                    category = 'average'
                else:
                    category = 'slow'
                break

        # 1コースはSTが特に重要（係数1.2倍）
        if pit_number == 1:
            score_factor = min(1.0, score_factor * 1.2)

        score = max_score * score_factor

        # 説明文生成
        if avg_st < 0.10:
            desc = f'ST{avg_st:.2f}秒（Fリスク）'
        elif avg_st < 0.15:
            desc = f'ST{avg_st:.2f}秒（絶好）'
        elif avg_st < 0.18:
            desc = f'ST{avg_st:.2f}秒（良好）'
        elif avg_st < 0.20:
            desc = f'ST{avg_st:.2f}秒（やや遅）'
        else:
            desc = f'ST{avg_st:.2f}秒（遅い）'

        return {
            'score': score,
            'avg_st': avg_st,
            'category': category,
            'description': desc
        }

    # 転覆ペナルティ定数（データ分析に基づく調整 2025-12-19）
    # 実績: 転覆後30日以内は勝率-0.5pt、2連対率-1.3pt低下、31日以降は影響なし
    CAPSIZING_PENALTIES = {
        'motor_recent_30d': -1.0,    # 直近30日以内にモーターで転覆（実測-1.3pt相当）
        'motor_recent_90d': 0.0,     # 31日以降は影響なし（データで確認済み）
        'motor_multiple': -0.5,      # 同モーターで複数回転覆（追加ペナルティ/回）
    }

    def calculate_fl_penalty(self, f_count: int, l_count: int, max_penalty: float = -10.0) -> Dict:
        """
        F/L持ちペナルティを計算

        F持ち選手は慎重なスタートになり、特に1コースで不利

        Args:
            f_count: フライング回数
            l_count: 出遅れ回数
            max_penalty: 最大ペナルティ（負の値）

        Returns:
            {'penalty': float, 'f_count': int, 'l_count': int, 'risk_level': str}
        """
        f_count = f_count or 0
        l_count = l_count or 0

        # ペナルティ計算
        f_penalty = f_count * self.FL_PENALTIES['F']
        l_penalty = l_count * self.FL_PENALTIES['L']
        total_penalty = max(f_penalty + l_penalty, max_penalty)  # max_penaltyで下限

        # リスクレベル判定
        if f_count >= 2:
            risk_level = 'critical'  # 即帰郷の危険
        elif f_count == 1:
            risk_level = 'high'  # 慎重スタート必須
        elif l_count >= 2:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        return {
            'penalty': total_penalty,
            'f_count': f_count,
            'l_count': l_count,
            'risk_level': risk_level,
            'description': f'F{f_count}L{l_count}' if (f_count + l_count) > 0 else 'クリーン'
        }

    def calculate_motor_capsizing_penalty(
        self,
        motor_number: int,
        venue_code: str,
        target_date: str,
        max_penalty: float = -5.0
    ) -> Dict:
        """
        モーター転覆履歴ペナルティを計算

        転覆後のモーターは性能が低下している可能性があるため、
        直近の転覆履歴に基づいてペナルティを適用。

        Args:
            motor_number: モーター番号
            venue_code: 会場コード
            target_date: 対象日付（YYYY-MM-DD）
            max_penalty: 最大ペナルティ（負の値）

        Returns:
            {
                'penalty': float,
                'capsizing_count': int,
                'days_since_last': int or None,
                'risk_level': str,
                'description': str
            }
        """
        if not motor_number:
            return {
                'penalty': 0.0,
                'capsizing_count': 0,
                'days_since_last': None,
                'risk_level': 'unknown',
                'description': 'モーター番号なし'
            }

        # キャッシュチェック（同じ日の同じモーター×会場は同じ結果）
        cache_key = (motor_number, venue_code)
        if cache_key in self._capsizing_cache:
            return self._capsizing_cache[cache_key]

        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        try:
            # 同じモーター番号で結果が欠損している（転覆/失格の可能性）レースを検索
            # 転覆は results に6件未満しか登録されないパターンで検出
            cursor.execute('''
                WITH race_result_counts AS (
                    SELECT
                        r.id as race_id,
                        r.race_date,
                        r.venue_code,
                        e.motor_number,
                        e.pit_number,
                        COUNT(res.id) as result_count,
                        MAX(CASE WHEN res.pit_number = e.pit_number THEN res.rank ELSE NULL END) as my_rank
                    FROM races r
                    JOIN entries e ON r.id = e.race_id
                    LEFT JOIN results res ON r.id = res.race_id
                    WHERE e.motor_number = ?
                      AND r.venue_code = ?
                      AND r.race_date < ?
                      AND r.race_date >= date(?, '-180 days')
                    GROUP BY r.id, e.pit_number
                )
                SELECT
                    race_date,
                    result_count,
                    my_rank,
                    julianday(?) - julianday(race_date) as days_ago
                FROM race_result_counts
                WHERE result_count < 6 AND (my_rank IS NULL OR my_rank NOT IN ('1','2','3','4','5','6'))
                ORDER BY race_date DESC
            ''', (motor_number, venue_code, target_date, target_date, target_date))

            capsizing_events = cursor.fetchall()
            capsizing_count = len(capsizing_events)

            if capsizing_count == 0:
                result = {
                    'penalty': 0.0,
                    'capsizing_count': 0,
                    'days_since_last': None,
                    'risk_level': 'none',
                    'description': '転覆履歴なし'
                }
                self._capsizing_cache[cache_key] = result
                return result

            # 最新の転覆からの日数
            days_since_last = int(capsizing_events[0][3]) if capsizing_events else None

            # ペナルティ計算（データ分析に基づく: 30日以内のみ影響あり）
            total_penalty = 0.0

            # 直近30日以内に転覆 → 成績低下あり
            if days_since_last and days_since_last <= 30:
                total_penalty += self.CAPSIZING_PENALTIES['motor_recent_30d']
                risk_level = 'high'

                # 複数回転覆の追加ペナルティ（30日以内の場合のみ、最大2回分）
                if capsizing_count >= 2:
                    additional = min(capsizing_count - 1, 2) * self.CAPSIZING_PENALTIES['motor_multiple']
                    total_penalty += additional
            else:
                # 31日以降は影響なし（データで確認済み）
                risk_level = 'none'
                total_penalty = 0.0

            # 最大ペナルティ制限
            total_penalty = max(total_penalty, max_penalty)

            # 説明文
            if days_since_last and days_since_last <= 30:
                desc = f'転覆注意（{days_since_last}日前, 計{capsizing_count}回）'
            else:
                desc = f'転覆履歴あり（{days_since_last}日前）※31日以上経過で影響なし'

            result = {
                'penalty': round(total_penalty, 2),
                'capsizing_count': capsizing_count,
                'days_since_last': days_since_last,
                'risk_level': risk_level,
                'description': desc
            }
            self._capsizing_cache[cache_key] = result
            return result

        except Exception as e:
            # エラー時は安全側に倒す（ペナルティなし）
            return {
                'penalty': 0.0,
                'capsizing_count': 0,
                'days_since_last': None,
                'risk_level': 'error',
                'description': f'エラー: {str(e)}'
            }
        finally:
            cursor.close()

    def calculate_session_performance(
        self,
        racer_number: str,
        venue_code: str,
        target_date: str,
        max_score: float = 5.0
    ) -> Dict:
        """
        節間成績スコアを計算

        同一会場での直近成績（同じ開催期間内）を評価

        Args:
            racer_number: 選手番号
            venue_code: 会場コード
            target_date: 対象日付（YYYY-MM-DD）
            max_score: 最大スコア

        Returns:
            {'score': float, 'races': int, 'avg_rank': float, 'trend': str}
        """
        # キャッシュ優先
        if self.batch_loader and self.batch_loader._cache_loaded:
            cached = self.batch_loader.get_session_performance(racer_number, venue_code)
            results = [(d['rank'], d['race_date'], d['race_number']) for d in cached]
        else:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    SELECT res.rank, r.race_date, r.race_number
                    FROM entries e
                    JOIN races r ON e.race_id = r.id
                    LEFT JOIN results res ON res.race_id = r.id AND res.pit_number = e.pit_number
                    WHERE e.racer_number = ?
                      AND r.venue_code = ?
                      AND r.race_date < ?
                      AND r.race_date >= date(?, '-7 days')
                      AND res.rank IS NOT NULL
                      AND res.rank NOT IN ('F', 'L', '欠', '失')
                    ORDER BY r.race_date DESC, r.race_number DESC
                    LIMIT 12
                ''', (racer_number, venue_code, target_date, target_date))
                results = cursor.fetchall()
            finally:
                cursor.close()

        if not results:
            return {
                'score': max_score * 0.5,
                'races': 0,
                'avg_rank': None,
                'trend': 'unknown',
                'description': '節間データなし'
            }

        # 着順を数値化
        ranks = []
        for row in results:
            try:
                rank = int(row[0])
                if 1 <= rank <= 6:
                    ranks.append(rank)
            except (ValueError, TypeError):
                pass

        if not ranks:
            return {
                'score': max_score * 0.5,
                'races': len(results),
                'avg_rank': None,
                'trend': 'unknown',
                'description': '有効データなし'
            }

        avg_rank = sum(ranks) / len(ranks)

        score = max(0, (6 - avg_rank) / 5 * max_score)

        if len(ranks) >= 4:
            first_half = sum(ranks[:len(ranks)//2]) / (len(ranks)//2)
            second_half = sum(ranks[len(ranks)//2:]) / (len(ranks) - len(ranks)//2)
            if second_half < first_half - 0.5:
                trend = 'improving'
            elif second_half > first_half + 0.5:
                trend = 'declining'
            else:
                trend = 'stable'
        else:
            trend = 'insufficient'

        return {
            'score': score,
            'races': len(ranks),
            'avg_rank': round(avg_rank, 2),
            'trend': trend,
            'description': f'節間{len(ranks)}走 平均{avg_rank:.1f}着'
        }

    def calculate_previous_race_level(
        self,
        racer_number: str,
        target_date: str,
        max_score: float = 5.0
    ) -> Dict:
        """
        前走レベル評価

        直前のレースがSG/G1だったか、一般戦だったかで調子を推定

        Args:
            racer_number: 選手番号
            target_date: 対象日付
            max_score: 最大スコア

        Returns:
            {'score': float, 'prev_grade': str, 'prev_result': int, 'description': str}
        """
        # キャッシュ優先
        prev_grade, prev_rank = None, None
        if self.batch_loader and self.batch_loader._cache_loaded:
            prev = self.batch_loader.get_previous_race(racer_number)
            if prev is not None:
                prev_grade = prev.get('prev_grade')
                prev_rank = prev.get('prev_rank')
        else:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    SELECT r.race_grade, res.rank, r.race_date
                    FROM entries e
                    JOIN races r ON e.race_id = r.id
                    LEFT JOIN results res ON res.race_id = r.id AND res.pit_number = e.pit_number
                    WHERE e.racer_number = ?
                      AND r.race_date < ?
                    ORDER BY r.race_date DESC, r.race_number DESC
                    LIMIT 1
                ''', (racer_number, target_date))
                row = cursor.fetchone()
            finally:
                cursor.close()
            if row:
                prev_grade, prev_rank, _ = row

        if prev_grade is None and prev_rank is None:
            return {
                'score': max_score * 0.5,
                'prev_grade': None,
                'prev_result': None,
                'description': '前走データなし'
            }

        # グレード評価
        grade_scores = {
            'SG': 1.0,
            'G1': 0.9,
            'G2': 0.8,
            'G3': 0.7,
            '一般': 0.5,
            'ルーキーシリーズ': 0.4,
        }
        grade_factor = grade_scores.get(prev_grade, 0.5)

        # 前走結果評価
        try:
            rank = int(prev_rank)
            if rank == 1:
                result_factor = 1.0
            elif rank == 2:
                result_factor = 0.8
            elif rank <= 3:
                result_factor = 0.6
            else:
                result_factor = 0.4
        except (ValueError, TypeError):
            result_factor = 0.3  # F/L等

        score = max_score * (grade_factor * 0.4 + result_factor * 0.6)

        return {
            'score': score,
            'prev_grade': prev_grade,
            'prev_result': prev_rank,
            'description': f'前走{prev_grade or "不明"} {prev_rank or "-"}着'
        }

    def predict_course_entry(
        self,
        pit_number: int,
        racer_number: str,
        venue_code: str
    ) -> Dict:
        """
        進入コース予測

        過去の進入傾向から実際のコースを予測

        Args:
            pit_number: 枠番（1-6）
            racer_number: 選手番号
            venue_code: 会場コード

        Returns:
            {'predicted_course': int, 'confidence': float, 'probabilities': dict}
        """
        # デフォルトの傾向を使用（DB不要）
        probabilities = self.DEFAULT_COURSE_TENDENCY.get(pit_number, {pit_number: 1.0})
        predicted_course = max(probabilities, key=probabilities.get)
        confidence = probabilities[predicted_course]
        return {
            'predicted_course': predicted_course,
            'confidence': confidence,
            'probabilities': probabilities,
            'description': f'{pit_number}号艇→{predicted_course}コース予測（{confidence*100:.0f}%）'
        }

    def analyze_racer_matchup(
        self,
        race_entries: List[Dict],
        max_score: float = 5.0
    ) -> Dict[int, Dict]:
        """
        選手間相性・力関係分析

        同じレースに出走する選手同士の相対的な力関係を評価

        Args:
            race_entries: [{'pit_number': int, 'racer_number': str, 'racer_rank': str, 'win_rate': float}, ...]
            max_score: 最大スコア

        Returns:
            {pit_number: {'relative_score': float, 'rank_in_race': int, ...}}
        """
        if not race_entries:
            return {}

        # 勝率でランキング
        sorted_entries = sorted(
            race_entries,
            key=lambda x: (
                self.CLASS_SCORES.get(x.get('racer_rank', 'B1'), 4),
                x.get('win_rate', 0) or 0
            ),
            reverse=True
        )

        results = {}
        for rank, entry in enumerate(sorted_entries, 1):
            pit = entry.get('pit_number')

            # 相対スコア：1位に対する相対評価
            top_win_rate = sorted_entries[0].get('win_rate', 0) or 1
            current_win_rate = entry.get('win_rate', 0) or 0
            relative_factor = current_win_rate / top_win_rate if top_win_rate > 0 else 0.5

            score = max_score * relative_factor

            # 級別差
            top_class = sorted_entries[0].get('racer_rank', 'B1')
            current_class = entry.get('racer_rank', 'B1')
            class_diff = self.CLASS_SCORES.get(current_class, 4) - self.CLASS_SCORES.get(top_class, 4)

            results[pit] = {
                'relative_score': score,
                'rank_in_race': rank,
                'class_diff': class_diff,
                'description': f'レース内{rank}位' + (f'（{current_class}）' if current_class else '')
            }

        return results

    def calculate_course_entry_tendency(
        self,
        racer_number: str,
        pit_number: int,
        max_score: float = 5.0
    ) -> Dict:
        """
        選手の進入コース傾向（前付け傾向）を分析

        外枠から内コースへ進入する傾向がある選手を特定し、
        進入予測の信頼度と補正スコアを計算する。

        Args:
            racer_number: 選手番号
            pit_number: 枠番（1-6）
            max_score: 最大スコア

        Returns:
            {
                'front_entry_rate': float,  # 前付け率（0-100%）
                'predicted_course': int,    # 予測コース
                'confidence': float,        # 進入予測の信頼度（0-1）
                'score': float,             # スコア（有利不利の補正）
                'description': str
            }
        """
        # キャッシュ優先（全枠番データを取得）
        if self.batch_loader and self.batch_loader._cache_loaded:
            course_counts = self.batch_loader._cache.get('course_entry_tendency', {}).get(racer_number)
            if course_counts is None:
                return {
                    'front_entry_rate': 0.0,
                    'predicted_course': pit_number,
                    'confidence': 0.8,
                    'score': max_score * 0.5,
                    'is_front_entry_prone': False,
                    'description': '進入データなし（枠番進入を予測）'
                }
        else:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    SELECT
                        e.pit_number,
                        rd.actual_course,
                        COUNT(*) as cnt
                    FROM entries e
                    JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                    WHERE e.racer_number = ?
                      AND rd.actual_course IS NOT NULL
                    GROUP BY e.pit_number, rd.actual_course
                ''', (racer_number,))
                rows = cursor.fetchall()
            finally:
                cursor.close()

            if not rows:
                return {
                    'front_entry_rate': 0.0,
                    'predicted_course': pit_number,
                    'confidence': 0.8,
                    'score': max_score * 0.5,
                    'is_front_entry_prone': False,
                    'description': '進入データなし（枠番進入を予測）'
                }

            course_counts = {}
            for pit, course, cnt in rows:
                if pit not in course_counts:
                    course_counts[pit] = {}
                course_counts[pit][course] = cnt

        # 該当枠番での傾向を分析
        if pit_number in course_counts:
            pit_distribution = course_counts[pit_number]
            total = sum(pit_distribution.values())
            predicted_course = max(pit_distribution, key=pit_distribution.get)
            predicted_prob = pit_distribution[predicted_course] / total
            front_entry_count = sum(
                cnt for c, cnt in pit_distribution.items() if c < pit_number
            )
            front_entry_rate = (front_entry_count / total) * 100
        else:
            total_front = sum(
                cnt for pit, dist in course_counts.items()
                for c, cnt in dist.items() if c < pit
            )
            total_all = sum(cnt for dist in course_counts.values() for cnt in dist.values())
            front_entry_rate = (total_front / total_all * 100) if total_all > 0 else 0
            predicted_course = pit_number
            predicted_prob = 0.7

        confidence = predicted_prob
        if front_entry_rate > 50:
            confidence *= 0.7
        elif front_entry_rate > 30:
            confidence *= 0.85

        score = max_score * 0.5
        if predicted_course < pit_number:
            score += max_score * (pit_number - predicted_course) * 0.1
        elif predicted_course > pit_number:
            score -= max_score * (predicted_course - pit_number) * 0.1
        if confidence < 0.6:
            score *= 0.8
        score = max(0, min(max_score, score))

        is_front_entry_prone = front_entry_rate > 40
        if front_entry_rate > 50:
            desc = f'前付け常習（{front_entry_rate:.0f}%）→{predicted_course}コース予測'
        elif front_entry_rate > 20:
            desc = f'前付け傾向あり（{front_entry_rate:.0f}%）'
        else:
            desc = f'{pit_number}号艇→{predicted_course}コース予測（{confidence*100:.0f}%）'

        return {
            'front_entry_rate': round(front_entry_rate, 1),
            'predicted_course': predicted_course,
            'confidence': round(confidence, 2),
            'score': round(score, 2),
            'is_front_entry_prone': is_front_entry_prone,
            'description': desc
        }

    def calculate_exhibition_time_score(
        self,
        race_id: int,
        pit_number: int,
        max_score: float = 8.0
    ) -> Dict:
        """
        展示タイムに基づくスコアを計算

        展示タイムはレース当日のモーター調子を反映する重要な指標。
        他艇との相対比較でスコアを算出。

        Args:
            race_id: レースID
            pit_number: 枠番
            max_score: 最大スコア

        Returns:
            {'score': float, 'exhibition_time': float, 'rank': int, 'description': str}
        """
        # キャッシュ優先（レース全艇のrace_detailsを取得）
        if self.batch_loader and self.batch_loader._cache_loaded:
            race_details_all = self.batch_loader._cache.get('race_details', {}).get(race_id, {})
            rows = sorted(
                [(pit, d['exhibition_time']) for pit, d in race_details_all.items()
                 if d.get('exhibition_time') is not None],
                key=lambda x: x[1]
            )
        else:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    SELECT pit_number, exhibition_time
                    FROM race_details
                    WHERE race_id = ? AND exhibition_time IS NOT NULL
                    ORDER BY exhibition_time ASC
                ''', (race_id,))
                rows = cursor.fetchall()
            finally:
                cursor.close()

        if not rows:
            return {
                'score': max_score * 0.5,
                'exhibition_time': None,
                'rank': None,
                'description': '展示タイムデータなし'
            }

        times = [(pit, time) for pit, time in rows]
        target_time = None
        target_rank = None
        for rank, (pit, time) in enumerate(times, 1):
            if pit == pit_number:
                target_time = time
                target_rank = rank
                break

        if target_time is None:
            return {
                'score': max_score * 0.5,
                'exhibition_time': None,
                'rank': None,
                'description': '展示タイムデータなし'
            }

        total_boats = len(times)
        if total_boats > 1:
            score = max_score * (total_boats - target_rank) / (total_boats - 1)
        else:
            score = max_score * 0.5

        if target_rank == 1:
            desc = f'展示タイム{target_time:.2f}秒（1位/トップ）'
        elif target_rank <= 2:
            desc = f'展示タイム{target_time:.2f}秒（{target_rank}位/好調）'
        elif target_rank <= 4:
            desc = f'展示タイム{target_time:.2f}秒（{target_rank}位/普通）'
        else:
            desc = f'展示タイム{target_time:.2f}秒（{target_rank}位/不調）'

        return {
            'score': round(score, 2),
            'exhibition_time': target_time,
            'rank': target_rank,
            'description': desc
        }

    def calculate_tilt_angle_score(
        self,
        race_id: int,
        pit_number: int,
        racer_number: str,
        max_score: float = 3.0
    ) -> Dict:
        """
        チルト角度に基づくスコアを計算

        チルト角度は選手のセッティング傾向を示す。
        - マイナス（跳ね）: 出足重視、まくり向き
        - プラス（伏せ）: 伸び重視、逃げ・差し向き
        コース特性との相性を評価。

        Args:
            race_id: レースID
            pit_number: 枠番
            racer_number: 選手番号
            max_score: 最大スコア

        Returns:
            {'score': float, 'tilt_angle': float, 'setting_type': str, 'description': str}
        """
        # キャッシュ優先
        tilt = None
        if self.batch_loader and self.batch_loader._cache_loaded:
            detail = self.batch_loader.get_race_details(race_id, pit_number)
            if detail is not None:
                tilt = detail.get('tilt_angle')
        if tilt is None and not (self.batch_loader and self.batch_loader._cache_loaded):
            conn = get_connection(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    SELECT tilt_angle
                    FROM race_details
                    WHERE race_id = ? AND pit_number = ?
                ''', (race_id, pit_number))
                row = cursor.fetchone()
                if row:
                    tilt = row[0]
            finally:
                cursor.close()

        if tilt is None:
            return {
                'score': max_score * 0.5,
                'tilt_angle': None,
                'setting_type': 'unknown',
                'description': 'チルトデータなし'
            }

        if tilt <= -0.5:
            setting_type = 'dash'
            type_desc = '出足重視'
        elif tilt >= 0.5:
            setting_type = 'stretch'
            type_desc = '伸び重視'
        else:
            setting_type = 'balanced'
            type_desc = 'バランス'

        score = max_score * 0.5
        if pit_number == 1:
            if setting_type == 'stretch':
                score = max_score * 0.8
            elif setting_type == 'balanced':
                score = max_score * 0.6
            else:
                score = max_score * 0.4
        elif pit_number in [2, 3]:
            if setting_type in ['balanced', 'stretch']:
                score = max_score * 0.7
            else:
                score = max_score * 0.5
        elif pit_number in [4, 5, 6]:
            if setting_type == 'dash':
                score = max_score * 0.8
            elif setting_type == 'balanced':
                score = max_score * 0.6
            else:
                score = max_score * 0.4

        return {
            'score': round(score, 2),
            'tilt_angle': tilt,
            'setting_type': setting_type,
            'description': f'チルト{tilt:+.1f}°（{type_desc}）'
        }

    def calculate_chikusen_time_score(
        self,
        race_id: int,
        pit_number: int,
        max_score: float = 4.0
    ) -> Dict:
        """
        直線タイム（chikusen_time）に基づくスコアを計算

        直線タイムは選手とモーターの伸び脚を示す重要な指標。
        レース内での相対順位によってスコアを付与します。

        Args:
            race_id: レースID
            pit_number: 枠番
            max_score: 最大スコア（デフォルト: 4.0点）

        Returns:
            {'score': float, 'chikusen_time': float, 'rank': int,
             'level': str, 'description': str}

        スコアリング基準:
            1位（最速）: max_score点
            2-3位: max_score * 0.6点
            4-5位: max_score * 0.3点
            6位（最遅）: 0点
            データなし: max_score * 0.5点（中立）
        """
        # batch_loaderからキャッシュを取得（高速化）
        if self.batch_loader and hasattr(self.batch_loader, '_cache'):
            race_details = self.batch_loader._cache.get('race_details', {}).get(race_id, {})
            times_data = []
            for pit, details in race_details.items():
                chikusen_time = details.get('chikusen_time')
                if chikusen_time is not None:
                    times_data.append((pit, chikusen_time))

            # 直線タイムでソート（昇順=速い順）
            times_data.sort(key=lambda x: x[1])
        else:
            # フォールバック: 従来のDBクエリ
            conn = get_connection(self.db_path)
            cursor = conn.cursor()

            try:
                # 該当レースの全艇の直線タイムを取得
                # exhibition_dataとrace_detailsの両方から取得を試みる
                cursor.execute('''
                    SELECT pit_number, chikusen_time
                    FROM (
                        -- exhibition_dataから取得（優先）
                        SELECT pit_number, chikusen_time
                        FROM exhibition_data
                        WHERE race_id = ? AND chikusen_time IS NOT NULL

                        UNION

                        -- race_detailsから取得（フォールバック）
                        SELECT pit_number, chikusen_time
                        FROM race_details
                        WHERE race_id = ? AND chikusen_time IS NOT NULL
                    )
                    ORDER BY chikusen_time ASC
                ''', (race_id, race_id))

                times_data = cursor.fetchall()
            finally:
                cursor.close()

        # データなしチェック
        if not times_data or len(times_data) == 0:
            # データなしの場合は中立点
            return {
                'score': max_score * 0.5,
                'chikusen_time': None,
                'rank': None,
                'level': 'unknown',
                'description': '直線タイムデータなし'
            }

        # 対象艇のデータを探す
        target_time = None
        target_rank = None

        for rank, (pit, time) in enumerate(times_data, start=1):
            if pit == pit_number:
                target_time = time
                target_rank = rank
                break

        if target_time is None:
            # 対象艇のデータなし
            return {
                'score': max_score * 0.5,
                'chikusen_time': None,
                'rank': None,
                'level': 'unknown',
                'description': '直線タイムデータなし'
            }

        # 順位に基づくスコアリング
        if target_rank == 1:
            score = max_score  # 1位（最速）: 満点
            level = 'excellent'
            desc = f'直線タイム{target_time:.2f}秒（1位/最速）'
        elif target_rank in [2, 3]:
            score = max_score * 0.6  # 2-3位: 60%
            level = 'good'
            desc = f'直線タイム{target_time:.2f}秒（{target_rank}位/良好）'
        elif target_rank in [4, 5]:
            score = max_score * 0.3  # 4-5位: 30%
            level = 'average'
            desc = f'直線タイム{target_time:.2f}秒（{target_rank}位/普通）'
        else:  # 6位
            score = 0.0  # 6位（最遅）: 0点
            level = 'poor'
            desc = f'直線タイム{target_time:.2f}秒（6位/不調）'

        return {
            'score': round(score, 2),
            'chikusen_time': round(target_time, 2),
            'rank': target_rank,
            'level': level,
            'description': desc
        }

    def calculate_recent_form_score(
        self,
        racer_number: str,
        race_date: str,
        max_score: float = 8.0
    ) -> Dict:
        """
        直近成績（短期の調子）に基づくスコアを計算

        racer_features テーブルから直近3/5/10走の成績を取得し、
        短期的な調子を評価する。

        Args:
            racer_number: 選手番号
            race_date: 対象日付
            max_score: 最大スコア

        Returns:
            {'score': float, 'recent_win_rate': float, 'recent_avg_rank': float,
             'trend': str, 'description': str}
        """
        # キャッシュ優先
        row = None
        if self.batch_loader and self.batch_loader._cache_loaded:
            features = self.batch_loader.get_racer_features(racer_number)
            if features is not None:
                row = (
                    features.get('recent_avg_rank_3'),
                    features.get('recent_avg_rank_5'),
                    features.get('recent_avg_rank_10'),
                    features.get('recent_win_rate_3'),
                    features.get('recent_win_rate_5'),
                    features.get('recent_win_rate_10'),
                    features.get('total_races'),
                    features.get('feature_date'),
                )
        if row is None:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    SELECT
                        recent_avg_rank_3, recent_avg_rank_5, recent_avg_rank_10,
                        recent_win_rate_3, recent_win_rate_5, recent_win_rate_10,
                        total_races, race_date
                    FROM racer_features
                    WHERE racer_number = ? AND race_date <= ?
                    ORDER BY race_date DESC
                    LIMIT 1
                ''', (racer_number, race_date))
                row = cursor.fetchone()
            finally:
                cursor.close()

        if not row:
            return {
                'score': max_score * 0.5,
                'recent_win_rate': None,
                'recent_avg_rank': None,
                'trend': 'unknown',
                'description': '直近成績データなし'
            }

        (avg_rank_3, avg_rank_5, avg_rank_10,
         win_rate_3, win_rate_5, win_rate_10,
         total_races, feature_date) = row

        recent_win_rate = win_rate_5 if win_rate_5 is not None else (win_rate_3 or win_rate_10 or 0)
        recent_avg_rank = avg_rank_5 if avg_rank_5 is not None else (avg_rank_3 or avg_rank_10 or 3.5)

        if win_rate_3 is not None and win_rate_10 is not None:
            if win_rate_3 > win_rate_10 + 10:
                trend = 'improving'
                trend_desc = '上昇中'
            elif win_rate_3 < win_rate_10 - 10:
                trend = 'declining'
                trend_desc = '下降中'
            else:
                trend = 'stable'
                trend_desc = '安定'
        else:
            trend = 'unknown'
            trend_desc = '不明'

        win_rate_score = min(recent_win_rate / 30.0, 1.0) * max_score * 0.6
        rank_score = max(0, (4.5 - recent_avg_rank) / 3.5) * max_score * 0.4
        score = win_rate_score + rank_score
        if trend == 'improving':
            score *= 1.1
        elif trend == 'declining':
            score *= 0.9
        score = max(0, min(max_score, score))

        return {
            'score': round(score, 2),
            'recent_win_rate': recent_win_rate,
            'recent_avg_rank': recent_avg_rank,
            'trend': trend,
            'description': f'直近5走: 勝率{recent_win_rate:.0f}%, 平均{recent_avg_rank:.1f}着（{trend_desc}）'
        }

    def calculate_venue_affinity_score(
        self,
        racer_number: str,
        venue_code: str,
        race_date: str,
        max_score: float = 6.0,
        local_win_rate: float = None,
        national_win_rate: float = None
    ) -> Dict:
        """
        会場相性スコアを計算（当地勝率 - 全国勝率）

        選手の全国勝率と当地勝率の差分から会場相性を評価します。
        entriesテーブルのlocal_win_rate/win_rateを直接使用することで、
        より正確な相性評価が可能です。

        Args:
            racer_number: 選手番号
            venue_code: 会場コード
            race_date: 対象日付
            max_score: 最大スコア（デフォルト: 6.0点）
            local_win_rate: 当地勝率（%、entries.local_win_rateから渡される場合）
            national_win_rate: 全国勝率（%、entries.win_rateから渡される場合）

        Returns:
            {'score': float, 'affinity_diff': float, 'local_win_rate': float,
             'national_win_rate': float, 'affinity_level': str, 'description': str}

        スコアリング基準:
            +5.0pt以上: 得意会場 → +3点
            +2.0-5.0pt: やや得意 → +1点
            -2.0-+2.0pt: 標準 → 中立点（max_score * 0.5）
            -5.0--2.0pt: やや苦手 → -1点
            -5.0pt以下: 苦手会場 → -3点
        """
        # キャッシュチェック（同一選手×会場×日付は同じ結果）
        cache_key = (racer_number, venue_code, race_date, max_score)
        if cache_key in self._venue_affinity_cache:
            return self._venue_affinity_cache[cache_key]

        # パラメータで渡されていない場合はDBから取得
        if local_win_rate is None or national_win_rate is None:
            conn = get_connection(self.db_path)
            cursor = conn.cursor()
            try:
                # 最新のentries情報から取得
                cursor.execute('''
                    SELECT e.local_win_rate, e.win_rate
                    FROM entries e
                    JOIN races r ON e.race_id = r.id
                    WHERE e.racer_number = ?
                      AND r.venue_code = ?
                      AND r.race_date <= ?
                      AND e.local_win_rate IS NOT NULL
                      AND e.win_rate IS NOT NULL
                    ORDER BY r.race_date DESC
                    LIMIT 1
                ''', (racer_number, venue_code, race_date))

                row = cursor.fetchone()

                if not row:
                    # データなしの場合は中立点
                    result = {
                        'score': max_score * 0.5,
                        'affinity_diff': 0.0,
                        'local_win_rate': None,
                        'national_win_rate': None,
                        'affinity_level': 'unknown',
                        'description': '会場相性データなし'
                    }
                    self._venue_affinity_cache[cache_key] = result
                    return result

                local_win_rate, national_win_rate = row
            finally:
                cursor.close()

        # 会場相性差を計算（pt単位）
        affinity_diff = local_win_rate - national_win_rate

        # スコアリング（5段階評価）
        if affinity_diff >= 5.0:
            # 得意会場: +3点
            score = max_score * 0.5 + 3.0
            affinity_level = 'excellent'
            desc = f'得意水面（+{affinity_diff:.1f}pt）'
        elif affinity_diff >= 2.0:
            # やや得意: +1点
            score = max_score * 0.5 + 1.0
            affinity_level = 'good'
            desc = f'やや得意（+{affinity_diff:.1f}pt）'
        elif affinity_diff >= -2.0:
            # 標準: 中立点
            score = max_score * 0.5
            affinity_level = 'average'
            sign = '+' if affinity_diff >= 0 else ''
            desc = f'標準相性（{sign}{affinity_diff:.1f}pt）'
        elif affinity_diff >= -5.0:
            # やや苦手: -1点
            score = max_score * 0.5 - 1.0
            affinity_level = 'poor'
            desc = f'やや苦手（{affinity_diff:.1f}pt）'
        else:
            # 苦手会場: -3点
            score = max_score * 0.5 - 3.0
            affinity_level = 'very_poor'
            desc = f'苦手水面（{affinity_diff:.1f}pt）'

        result = {
            'score': round(max(0, min(max_score * 1.5, score)), 2),  # 範囲: 0 ~ max_score*1.5
            'affinity_diff': round(affinity_diff, 2),
            'local_win_rate': round(local_win_rate, 1),
            'national_win_rate': round(national_win_rate, 1),
            'affinity_level': affinity_level,
            'description': desc
        }
        self._venue_affinity_cache[cache_key] = result
        return result

    def calculate_place_rate_score(
        self,
        racer_number: str,
        race_date: str,
        max_score: float = 5.0
    ) -> Dict:
        """
        2着率・3着率（連対率）に基づくスコアを計算

        勝率だけでなく、2着・3着に入る確率も重要。
        連に絡む確率が高い選手を評価する。

        Args:
            racer_number: 選手番号
            race_date: 対象日付
            max_score: 最大スコア

        Returns:
            {'score': float, 'second_rate': float, 'third_rate': float,
             'rentai_rate': float, 'description': str}
        """
        # キャッシュ優先（racer_overall に place_rate_2/3 あり）
        if self.batch_loader and self.batch_loader._cache_loaded:
            stats = self.batch_loader.get_racer_overall_stats(racer_number)
            if stats is not None and stats.get('total_races', 0) >= 10:
                total = stats['total_races']
                win_rate = stats['win_rate']
                second_rate = stats['place_rate_2']
                third_rate = stats['place_rate_3']
                avg_second_rate = 0.333
                avg_third_rate = 0.500
                second_score = (second_rate / avg_second_rate) * (max_score * 0.6)
                third_score = (third_rate / avg_third_rate) * (max_score * 0.4)
                score = max(0, min(max_score, second_score + third_score))
                is_strong_rentai = second_rate > 0.45
                if is_strong_rentai:
                    desc = f'連対力◎（2連対{second_rate*100:.0f}%, 3連対{third_rate*100:.0f}%）'
                elif second_rate > avg_second_rate:
                    desc = f'連対○（2連対{second_rate*100:.0f}%）'
                else:
                    desc = f'連対△（2連対{second_rate*100:.0f}%）'
                return {
                    'score': round(score, 2),
                    'win_rate': round(win_rate * 100, 1),
                    'second_rate': round(second_rate * 100, 1),
                    'third_rate': round(third_rate * 100, 1),
                    'rentai_rate': round(second_rate * 100, 1),
                    'is_strong_rentai': is_strong_rentai,
                    'description': desc
                }
            return {
                'score': max_score * 0.5,
                'win_rate': None, 'second_rate': None, 'third_rate': None,
                'rentai_rate': None, 'description': '連対率データ不足'
            }

        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        try:
            # 直近の成績から2着率・3着率を計算
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN res.rank IN ('1', '2') THEN 1 ELSE 0 END) as second_count,
                    SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) as third_count
                FROM entries e
                JOIN races r ON e.race_id = r.id
                JOIN results res ON res.race_id = r.id AND res.pit_number = e.pit_number
                WHERE e.racer_number = ?
                  AND r.race_date < ?
                  AND r.race_date >= date(?, '-180 days')
                  AND res.rank IN ('1', '2', '3', '4', '5', '6')
            ''', (racer_number, race_date, race_date))

            row = cursor.fetchone()

            if not row or row[0] < 10:  # 10レース未満はデータ不足
                return {
                    'score': max_score * 0.5,
                    'win_rate': None,
                    'second_rate': None,
                    'third_rate': None,
                    'rentai_rate': None,
                    'description': '連対率データ不足'
                }

            total, win_count, second_count, third_count = row

            win_rate = win_count / total
            second_rate = second_count / total  # 2連対率
            third_rate = third_count / total  # 3連対率

            # 連対率ベースのスコア
            # 平均的な2連対率: 33.3% (1/3)
            # 平均的な3連対率: 50.0% (1/2)
            # 2連対率を重視（連勝式で重要）

            # 2連対率スコア（60%の重み）
            avg_second_rate = 0.333
            second_score = (second_rate / avg_second_rate) * (max_score * 0.6)

            # 3連対率スコア（40%の重み）
            avg_third_rate = 0.500
            third_score = (third_rate / avg_third_rate) * (max_score * 0.4)

            score = second_score + third_score
            score = max(0, min(max_score, score))

            # 連対強さ判定
            is_strong_rentai = second_rate > 0.45  # 2連対率45%以上

            # 説明文
            if is_strong_rentai:
                desc = f'連対力◎（2連対{second_rate*100:.0f}%, 3連対{third_rate*100:.0f}%）'
            elif second_rate > avg_second_rate:
                desc = f'連対○（2連対{second_rate*100:.0f}%）'
            else:
                desc = f'連対△（2連対{second_rate*100:.0f}%）'

            return {
                'score': round(score, 2),
                'win_rate': round(win_rate * 100, 1),
                'second_rate': round(second_rate * 100, 1),
                'third_rate': round(third_rate * 100, 1),
                'rentai_rate': round(second_rate * 100, 1),  # 2連対率
                'is_strong_rentai': is_strong_rentai,
                'description': desc
            }

        finally:
            cursor.close()

    def analyze_motor_characteristics(
        self,
        motor_number: int,
        venue_code: str,
        max_score: float = 5.0
    ) -> Dict:
        """
        モーター特性分析

        モーターの詳細特性（加速/最高速/安定性）を分析
        BatchDataLoaderのキャッシュがあればDBクエリなしで高速に計算。

        Args:
            motor_number: モーター番号
            venue_code: 会場コード
            max_score: 最大スコア

        Returns:
            {'score': float, 'characteristics': dict, 'description': str}
        """
        # BatchDataLoaderキャッシュから取得を試みる（DBクエリ回避）
        if self.batch_loader and self.batch_loader._cache_loaded:
            cached = self.batch_loader.get_motor_stats(venue_code, motor_number)
            if cached:
                races = cached.get('total_races', 0)
                if races < 5:
                    return {
                        'score': max_score * 0.5,
                        'characteristics': {},
                        'races': races,
                        'description': 'モーターデータ不足'
                    }
                win_rate = cached.get('win_rate', 0)
                second_rate = cached.get('place_rate_2', 0)
                score = min(max_score, max_score * (win_rate / 0.20))
                characteristics = {
                    'power': 'high' if win_rate > 0.15 else 'medium' if win_rate > 0.08 else 'low',
                    'stability': 'high' if second_rate > 0.30 else 'medium' if second_rate > 0.20 else 'low'
                }
                return {
                    'score': score,
                    'characteristics': characteristics,
                    'win_rate': round(win_rate * 100, 1),
                    'second_rate': round(second_rate * 100, 1),
                    'races': races,
                    'description': f'勝率{win_rate*100:.1f}% ({races}走)'
                }
            else:
                # キャッシュにないモーター → データ不足
                return {
                    'score': max_score * 0.5,
                    'characteristics': {},
                    'races': 0,
                    'description': 'モーターデータ不足'
                }

        # フォールバック: DB直接クエリ
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT
                    e.motor_number,
                    AVG(CASE WHEN res.rank = '1' THEN 1.0 ELSE 0.0 END) as win_rate,
                    AVG(CASE WHEN res.rank IN ('1', '2') THEN 1.0 ELSE 0.0 END) as second_rate,
                    COUNT(*) as races
                FROM entries e
                JOIN races r ON e.race_id = r.id
                LEFT JOIN results res ON res.race_id = r.id AND res.pit_number = e.pit_number
                WHERE e.motor_number = ?
                  AND r.venue_code = ?
                  AND res.rank IS NOT NULL
                GROUP BY e.motor_number
            ''', (motor_number, venue_code))

            row = cursor.fetchone()

            if not row or row[3] < 5:
                return {
                    'score': max_score * 0.5,
                    'characteristics': {},
                    'races': row[3] if row else 0,
                    'description': 'モーターデータ不足'
                }

            win_rate = row[1] or 0
            second_rate = row[2] or 0
            races = row[3]

            score = min(max_score, max_score * (win_rate / 0.20))

            characteristics = {
                'power': 'high' if win_rate > 0.15 else 'medium' if win_rate > 0.08 else 'low',
                'stability': 'high' if second_rate > 0.30 else 'medium' if second_rate > 0.20 else 'low'
            }

            return {
                'score': score,
                'characteristics': characteristics,
                'win_rate': round(win_rate * 100, 1),
                'second_rate': round(second_rate * 100, 1),
                'races': races,
                'description': f'勝率{win_rate*100:.1f}% ({races}走)'
            }

        finally:
            cursor.close()

    def get_comprehensive_score(
        self,
        entry: Dict,
        venue_code: str,
        target_date: str,
        race_entries: List[Dict] = None,
        race_id: int = None
    ) -> Dict:
        """
        総合拡張スコアを計算

        2024年11月27日更新: EXTENDED_SCORE_WEIGHTSの設定を使用

        Args:
            entry: {'pit_number', 'racer_number', 'racer_rank', 'f_count', 'l_count', 'motor_number', ...}
            venue_code: 会場コード
            target_date: 対象日付
            race_entries: 同レースの全出走者リスト
            race_id: レースID（展示データ取得用）

        Returns:
            総合スコアと各要素の詳細
        """
        pit_number = entry.get('pit_number')
        racer_number = entry.get('racer_number')

        # 設定ファイルから重みを取得
        weights = EXTENDED_SCORE_WEIGHTS

        # 1. 級別スコア (設定: class)
        class_result = self.calculate_class_score(
            entry.get('racer_rank'),
            max_score=float(weights.get('class', 10))
        )

        # 2. F/Lペナルティ (max: 0, min: -10)
        fl_result = self.calculate_fl_penalty(
            entry.get('f_count', 0),
            entry.get('l_count', 0)
        )

        # 3. 節間成績 (設定: session)
        session_result = self.calculate_session_performance(
            racer_number,
            venue_code,
            target_date,
            max_score=float(weights.get('session', 5))
        )

        # 4. 前走レベル (設定: prev_race)
        prev_race_result = self.calculate_previous_race_level(
            racer_number,
            target_date,
            max_score=float(weights.get('prev_race', 5))
        )

        # 5. 進入コース傾向分析 (設定: course_entry)
        course_entry_result = self.calculate_course_entry_tendency(
            racer_number,
            pit_number,
            max_score=float(weights.get('course_entry', 5))
        )

        # 6. 選手間相性（race_entriesがあれば）(設定: matchup)
        matchup_result = {}
        matchup_max = float(weights.get('matchup', 5))
        if race_entries:
            all_matchups = self.analyze_racer_matchup(race_entries, max_score=matchup_max)
            matchup_result = all_matchups.get(pit_number, {})

        # 7. モーター特性 (設定: motor)
        motor_result = self.analyze_motor_characteristics(
            entry.get('motor_number'),
            venue_code,
            max_score=float(weights.get('motor', 5))
        )

        # 8. 平均STスコア (設定: start_timing) - 重要指標のため強化
        st_result = self.calculate_start_timing_score(
            entry.get('avg_st'),
            pit_number,
            max_score=float(weights.get('start_timing', 10))  # 8→10に強化
        )

        # 9. 展示タイムスコア (設定: exhibition) - 重要指標のため強化
        exhibition_max = float(weights.get('exhibition', 10))  # 8→10に強化
        exhibition_result = {'score': exhibition_max * 0.5, 'description': '展示データなし'}
        if race_id:
            exhibition_result = self.calculate_exhibition_time_score(
                race_id,
                pit_number,
                max_score=exhibition_max
            )

        # 10. チルト角度スコア (設定: tilt) - 影響小のため低下
        tilt_max = float(weights.get('tilt', 2))  # 3→2に低下
        tilt_result = {'score': tilt_max * 0.5, 'description': 'チルトデータなし'}
        if race_id:
            tilt_result = self.calculate_tilt_angle_score(
                race_id,
                pit_number,
                racer_number,
                max_score=tilt_max
            )

        # 11. 直近成績スコア (設定: recent_form)
        recent_form_result = self.calculate_recent_form_score(
            racer_number,
            target_date,
            max_score=float(weights.get('recent_form', 8))
        )

        # 12. 会場相性スコア (設定: venue_affinity) - local_win_rate活用に改善
        venue_affinity_result = self.calculate_venue_affinity_score(
            racer_number,
            venue_code,
            target_date,
            max_score=float(weights.get('venue_affinity', 0.0)),  # 6→8に強化
            local_win_rate=entry.get('local_win_rate'),  # entriesから直接取得
            national_win_rate=entry.get('win_rate')  # entriesから直接取得
        )

        # 13. 連対率スコア (設定: place_rate)
        place_rate_result = self.calculate_place_rate_score(
            racer_number,
            target_date,
            max_score=float(weights.get('place_rate', 5))
        )

        # 14. 直線タイムスコア (設定: chikusen_time)
        chikusen_time_result = self.calculate_chikusen_time_score(
            race_id,
            pit_number,
            max_score=float(weights.get('chikusen_time', 4))
        )

        # 15. 転覆ペナルティ（フラグが有効な場合のみ）
        capsizing_result = {'penalty': 0.0, 'capsizing_count': 0, 'days_since_last': None, 'risk_level': 'none', 'description': '転覆履歴なし'}
        if is_feature_enabled('motor_capsizing_penalty') and entry.get('motor_number'):
            capsizing_result = self.calculate_motor_capsizing_penalty(
                entry.get('motor_number'),
                venue_code,
                target_date
            )

        # 16. モーター2連対率スコア
        motor_second_rate = entry.get('motor_second_rate')
        motor_second_rate_result = self.calculate_motor_second_rate_score(
            motor_second_rate,
            max_score=0.0
        )

        # 総合スコア計算
        # 各スコアを合算
        total_score = (
            class_result['score'] +
            fl_result['penalty'] +
            capsizing_result['penalty'] +  # 転覆ペナルティを追加
            session_result['score'] +
            prev_race_result['score'] +
            course_entry_result['score'] +
            matchup_result.get('relative_score', matchup_max * 0.5) +
            motor_result['score'] +
            st_result['score'] +
            exhibition_result['score'] +
            tilt_result['score'] +
            chikusen_time_result['score'] +  # 直線タイムスコアを追加
            recent_form_result['score'] +
            venue_affinity_result['score'] +
            place_rate_result['score'] +
            motor_second_rate_result['score']  # モーター2連対率スコアを追加
        )

        # 最大可能スコアを計算（正規化用）
        max_possible = sum(
            v for k, v in weights.items() if k != 'fl_penalty'
        )

        # 進入予測の信頼度を考慮した補正
        # 前付け常習者がいる場合、他艇の予測信頼度も下がる
        entry_confidence = course_entry_result.get('confidence', 0.8)
        if entry_confidence < 0.6:
            # 進入不安定な選手は全体スコアにペナルティ
            total_score *= 0.95

        return {
            'total_extended_score': total_score,
            'max_possible_score': max_possible,  # 動的計算（78点）
            'weights_used': weights,  # 使用した重み設定
            'class': class_result,
            'fl_penalty': fl_result,
            'capsizing_penalty': capsizing_result,  # 転覆ペナルティを追加
            'session': session_result,
            'prev_race': prev_race_result,
            'course_entry': course_entry_result,
            'course_prediction': {  # 後方互換性
                'predicted_course': course_entry_result.get('predicted_course', pit_number),
                'confidence': course_entry_result.get('confidence', 0.8),
                'description': course_entry_result.get('description', '')
            },
            'matchup': matchup_result,
            'motor': motor_result,
            'motor_second_rate': motor_second_rate_result,
            'start_timing': st_result,
            'exhibition': exhibition_result,
            'tilt': tilt_result,
            'chikusen_time': chikusen_time_result,  # 直線タイムスコアを追加
            'recent_form': recent_form_result,
            'venue_affinity': venue_affinity_result,
            'place_rate': place_rate_result
        }

    def calculate_motor_second_rate_score(
        self,
        motor_second_rate: float,
        max_score: float = 5.0
    ) -> Dict:
        """
        モーター2連対率スコアを計算

        Args:
            motor_second_rate: モーター2連対率（0.0-100.0）
            max_score: 最大スコア（デフォルト5.0点）

        Returns:
            {
                'score': float,              # スコア（-2.0 〜 +5.0）
                'motor_second_rate': float,  # モーター2連対率
                'level': str,                # excellent/good/average/poor/very_poor
                'description': str
            }
        """
        if motor_second_rate is None:
            return {
                'score': 0.0,
                'motor_second_rate': None,
                'level': 'unknown',
                'description': 'モーター2連対率データなし'
            }

        # モーター2連対率の基準
        # 全国平均: 約40-45%
        # 優秀: 50%以上
        # 良好: 45-50%
        # 平均: 35-45%
        # 低い: 30-35%
        # 非常に低い: 30%未満

        if motor_second_rate >= 50.0:
            # 優秀なモーター（50%以上）
            score = max_score  # +5.0点
            level = 'excellent'
            description = f'優秀モーター({motor_second_rate:.1f}%)'
        elif motor_second_rate >= 45.0:
            # 良好なモーター（45-50%）
            score = max_score * 0.6  # +3.0点
            level = 'good'
            description = f'良好モーター({motor_second_rate:.1f}%)'
        elif motor_second_rate >= 35.0:
            # 平均的なモーター（35-45%）
            score = 0.0
            level = 'average'
            description = f'平均モーター({motor_second_rate:.1f}%)'
        elif motor_second_rate >= 30.0:
            # 低成績モーター（30-35%）
            score = -1.0
            level = 'poor'
            description = f'低成績モーター({motor_second_rate:.1f}%)'
        else:
            # 非常に低成績モーター（30%未満）
            score = -2.0
            level = 'very_poor'
            description = f'非常に低成績モーター({motor_second_rate:.1f}%)'

        return {
            'score': score,
            'motor_second_rate': motor_second_rate,
            'level': level,
            'description': description
        }
