"""
パターン分析モジュール

競艇場ごと、選手ごとのデータを分析し、傾向と法則を言語化する
"""

import sqlite3
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
import statistics
from src.utils.db_connection_pool import get_connection


class PatternAnalyzer:
    """パターン分析クラス - 傾向と法則を言語化"""

    def __init__(self, db_path: str = "data/boatrace.db"):
        self.db_path = db_path

    def _connect(self):
        """データベース接続（接続プールから取得）"""
        return get_connection(self.db_path)

    def _fetch_all(self, query, params=None):
        """クエリ実行（複数行取得）"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params or [])
        results = cursor.fetchall()
        cursor.close()
        return results

    def _fetch_one(self, query, params=None):
        """クエリ実行（1行取得）"""
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params or [])
        result = cursor.fetchone()
        cursor.close()
        return result

    # ========================================
    # 競艇場別パターン分析
    # ========================================

    def _get_venue_name(self, venue_code: str) -> str:
        """競艇場コードから競艇場名を取得"""
        from config.settings import VENUES

        for key, info in VENUES.items():
            if info['code'] == venue_code:
                return info['name']
        return f"競艇場{venue_code}"  # フォールバック

    def analyze_venue_pattern(self, venue_code: str, days: int = 90) -> Dict:
        """
        競艇場の傾向を分析して言語化

        Args:
            venue_code: 競艇場コード
            days: 集計期間（日数）

        Returns:
            {
                'venue_code': '01',
                'venue_name': '桐生',
                'patterns': ['1号艇の逃げ率が65%と高く、固い場である', ...],
                'course_tendencies': {...},
                'winning_combinations': [...],
                'risk_level': 'low' | 'medium' | 'high'
            }
        """
        venue_name = self._get_venue_name(venue_code)
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        patterns = []

        # 1. コース別勝率分析
        course_stats = self._analyze_venue_course_stats(venue_code, start_date)
        course_patterns = self._describe_course_patterns(course_stats)
        patterns.extend(course_patterns)

        # 2. 逃げ率分析
        escape_rate = self._get_escape_rate(venue_code, start_date)
        if escape_rate > 0.6:
            patterns.append(f"1号艇の逃げ率が{escape_rate*100:.1f}%と高く、固い場である")
        elif escape_rate < 0.45:
            patterns.append(f"1号艇の逃げ率が{escape_rate*100:.1f}%と低く、荒れやすい場である")
        else:
            patterns.append(f"1号艇の逃げ率は{escape_rate*100:.1f}%で標準的")

        # 3. 決まり手分析
        kimarite_pattern = self._analyze_kimarite_pattern(venue_code, start_date)
        if kimarite_pattern:
            patterns.append(kimarite_pattern)

        # 4. 配当分析
        payout_pattern = self._analyze_payout_pattern(venue_code, start_date)
        if payout_pattern:
            patterns.append(payout_pattern)

        # 5. イン有利度
        inside_win_rate = self._get_inside_win_rate(venue_code, start_date)
        if inside_win_rate > 0.75:
            patterns.append(f"インコース（1-3コース）の勝率が{inside_win_rate*100:.1f}%と高く、イン有利の場")
        elif inside_win_rate < 0.60:
            patterns.append(f"インコース（1-3コース）の勝率が{inside_win_rate*100:.1f}%と低く、アウトにもチャンスがある")

        # 6. よく出る出目組み合わせ
        top_combinations = self._get_top_combinations(venue_code, start_date, limit=5)

        # リスクレベル判定
        risk_level = self._determine_risk_level(escape_rate, payout_pattern)

        return {
            'venue_code': venue_code,
            'venue_name': venue_name,
            'patterns': patterns,
            'course_stats': course_stats,
            'top_combinations': top_combinations,
            'risk_level': risk_level,
            'escape_rate': escape_rate,
            'inside_win_rate': inside_win_rate
        }

    def _analyze_venue_course_stats(self, venue_code: str, start_date: str) -> Dict:
        """コース別統計を取得"""
        query = """
            SELECT
                rd.actual_course as course,
                COUNT(*) as total_races,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as first_place,
                SUM(CASE WHEN r.rank = 2 THEN 1 ELSE 0 END) as second_place,
                SUM(CASE WHEN r.rank = 3 THEN 1 ELSE 0 END) as third_place
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            WHERE ra.venue_code = ?
              AND ra.race_date >= ?
            GROUP BY rd.actual_course
            ORDER BY rd.actual_course
        """
        rows = self._fetch_all(query, [venue_code, start_date])

        stats = {}
        for row in rows:
            course = row['course']
            total = row['total_races']
            if total > 0:
                stats[course] = {
                    'total_races': total,
                    'win_rate': row['first_place'] / total,
                    'place_rate_2': row['second_place'] / total,
                    'place_rate_3': row['third_place'] / total
                }
        return stats

    def _describe_course_patterns(self, course_stats: Dict) -> List[str]:
        """コース統計から傾向を言語化"""
        patterns = []

        for course, stats in course_stats.items():
            win_rate = stats['win_rate']

            if course == 1:
                if win_rate > 0.6:
                    patterns.append(f"1コースの勝率が{win_rate*100:.1f}%と非常に高く、1号艇が圧倒的に有利")
                elif win_rate < 0.45:
                    patterns.append(f"1コースの勝率が{win_rate*100:.1f}%と低く、インが弱い特殊な場")
            elif course == 2:
                if win_rate > 0.15:
                    patterns.append(f"2コースの勝率が{win_rate*100:.1f}%とやや高く、差しが決まりやすい")
            elif course in [5, 6]:
                if win_rate > 0.02:
                    patterns.append(f"{course}コースの勝率が{win_rate*100:.1f}%で、アウトからの逆転も狙える")

        return patterns

    def _get_escape_rate(self, venue_code: str, start_date: str) -> float:
        """1号艇逃げ率"""
        query = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as wins
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            WHERE ra.venue_code = ?
              AND ra.race_date >= ?
              AND rd.actual_course = 1
        """
        row = self._fetch_one(query, [venue_code, start_date])
        if row and row['total'] > 0:
            return row['wins'] / row['total']
        return 0.0

    def _get_inside_win_rate(self, venue_code: str, start_date: str) -> float:
        """イン勝率（1-3コース）"""
        query = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as wins
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            WHERE ra.venue_code = ?
              AND ra.race_date >= ?
              AND rd.actual_course IN (1, 2, 3)
        """
        row = self._fetch_one(query, [venue_code, start_date])
        if row and row['total'] > 0:
            return row['wins'] / row['total']
        return 0.0

    def _analyze_kimarite_pattern(self, venue_code: str, start_date: str) -> str:
        """決まり手の傾向を分析"""
        query = """
            SELECT
                res.kimarite,
                COUNT(*) as count
            FROM results res
            JOIN races ra ON res.race_id = ra.id
            WHERE ra.venue_code = ?
              AND ra.race_date >= ?
              AND res.kimarite IS NOT NULL
              AND res.kimarite != ''
              AND res.rank = '1'
            GROUP BY res.kimarite
            ORDER BY count DESC
            LIMIT 1
        """
        row = self._fetch_one(query, [venue_code, start_date])
        if row and row['count'] > 10:
            kimarite = row['kimarite']
            return f"最も多い決まり手は「{kimarite}」で、この戦法が有効"
        return None

    def _analyze_payout_pattern(self, venue_code: str, start_date: str) -> str:
        """配当傾向を分析"""
        query = """
            SELECT
                AVG(trifecta_odds) as avg_odds,
                SUM(CASE WHEN trifecta_odds >= 10000 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as upset_rate
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            WHERE ra.venue_code = ?
              AND ra.race_date >= ?
              AND r.rank = 1
              AND r.trifecta_odds IS NOT NULL
        """
        row = self._fetch_one(query, [venue_code, start_date])
        if row:
            avg_odds = row['avg_odds'] or 0
            upset_rate = row['upset_rate'] or 0

            if upset_rate > 0.03:
                return f"万舟率が{upset_rate*100:.2f}%と高く、高配当が期待できる荒れる場"
            elif avg_odds > 3000:
                return f"平均配当が{avg_odds:.0f}円とやや高め"
            elif avg_odds < 1500:
                return "平均配当が低く、堅い決着が多い"
        return None

    def _get_top_combinations(self, venue_code: str, start_date: str, limit: int = 5) -> List[Dict]:
        """よく出る出目の組み合わせ"""
        query = """
            SELECT
                r1.pit_number as first,
                r2.pit_number as second,
                r3.pit_number as third,
                COUNT(*) as count
            FROM races ra
            JOIN results r1 ON ra.id = r1.race_id AND r1.rank = 1
            JOIN results r2 ON ra.id = r2.race_id AND r2.rank = 2
            JOIN results r3 ON ra.id = r3.race_id AND r3.rank = 3
            WHERE ra.venue_code = ?
              AND ra.race_date >= ?
            GROUP BY r1.pit_number, r2.pit_number, r3.pit_number
            ORDER BY count DESC
            LIMIT ?
        """
        rows = self._fetch_all(query, [venue_code, start_date, limit])

        combinations = []
        for row in rows:
            combinations.append({
                'combination': f"{row['first']}-{row['second']}-{row['third']}",
                'count': row['count']
            })
        return combinations

    def _determine_risk_level(self, escape_rate: float, payout_pattern: str) -> str:
        """リスクレベルを判定"""
        if escape_rate > 0.6 and "堅い決着" in (payout_pattern or ""):
            return "low"
        elif escape_rate < 0.45 or "荒れる場" in (payout_pattern or ""):
            return "high"
        else:
            return "medium"

    # ========================================
    # 選手別パターン分析
    # ========================================

    def analyze_racer_pattern(self, racer_number: int, days: int = 180) -> Dict:
        """
        選手の傾向を分析して言語化

        Args:
            racer_number: 選手登録番号
            days: 集計期間（日数）

        Returns:
            {
                'racer_number': 4320,
                'racer_name': '峰竜太',
                'patterns': ['スタートが得意で平均ST0.12と早い', ...],
                'strong_courses': [1, 2],
                'weak_courses': [6],
                'strong_venues': ['01', '04'],
                'performance_level': 'A' | 'B' | 'C'
            }
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # 選手名取得
        racer_name = self._get_racer_name(racer_number)
        if not racer_name:
            return None

        patterns = []

        # 1. 基本成績
        basic_stats = self._get_racer_basic_stats(racer_number, start_date)
        if basic_stats:
            win_rate = basic_stats['win_rate']
            if win_rate > 0.30:
                patterns.append(f"勝率{win_rate*100:.1f}%と高く、実力上位の選手")
            elif win_rate > 0.20:
                patterns.append(f"勝率{win_rate*100:.1f}%で安定した実力者")
            elif win_rate < 0.10:
                patterns.append(f"勝率{win_rate*100:.1f}%とやや低調")

        # 2. スタートタイミング分析
        st_pattern = self._analyze_st_pattern(racer_number, start_date)
        if st_pattern:
            patterns.append(st_pattern)

        # 3. コース別得意・不得意
        course_analysis = self._analyze_racer_course_strength(racer_number, start_date)
        strong_courses = course_analysis['strong']
        weak_courses = course_analysis['weak']

        if strong_courses:
            patterns.append(f"{','.join(map(str, strong_courses))}コースが得意")
        if weak_courses:
            patterns.append(f"{','.join(map(str, weak_courses))}コースが苦手")

        # 4. 会場別成績
        venue_analysis = self._analyze_racer_venue_strength(racer_number, start_date)
        strong_venues = venue_analysis['strong']

        if strong_venues:
            from config.settings import VENUES
            venue_names = [VENUES[vc]['name'] for vc in strong_venues[:3]]
            patterns.append(f"{','.join(venue_names)}で好成績")

        # 5. 決まり手
        favorite_kimarite = self._get_racer_favorite_kimarite(racer_number, start_date)
        if favorite_kimarite:
            patterns.append(f"得意な決まり手は「{favorite_kimarite}」")

        # パフォーマンスレベル判定
        performance_level = self._determine_performance_level(basic_stats['win_rate'] if basic_stats else 0)

        return {
            'racer_number': racer_number,
            'racer_name': racer_name,
            'patterns': patterns,
            'strong_courses': strong_courses,
            'weak_courses': weak_courses,
            'strong_venues': strong_venues,
            'performance_level': performance_level,
            'basic_stats': basic_stats
        }

    def _get_racer_name(self, racer_number: int) -> str:
        """選手名を取得"""
        query = """
            SELECT DISTINCT racer_name
            FROM entries
            WHERE racer_number = ?
            LIMIT 1
        """
        row = self._fetch_one(query, [racer_number])
        return row['racer_name'] if row else None

    def _get_racer_basic_stats(self, racer_number: int, start_date: str) -> Dict:
        """選手の基本成績"""
        query = """
            SELECT
                COUNT(*) as total_races,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN r.rank <= 2 THEN 1 ELSE 0 END) as top2,
                SUM(CASE WHEN r.rank <= 3 THEN 1 ELSE 0 END) as top3
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND ra.race_date >= ?
        """
        row = self._fetch_one(query, [racer_number, start_date])

        if row and row['total_races'] > 0:
            total = row['total_races']
            return {
                'total_races': total,
                'win_rate': row['wins'] / total,
                'place_rate_2': row['top2'] / total,
                'place_rate_3': row['top3'] / total
            }
        return None

    def _analyze_st_pattern(self, racer_number: int, start_date: str) -> str:
        """スタートタイミング分析"""
        query = """
            SELECT AVG(rd.st_time) as avg_st
            FROM race_details rd
            JOIN races ra ON rd.race_id = ra.id
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND ra.race_date >= ?
              AND rd.st_time IS NOT NULL
        """
        row = self._fetch_one(query, [racer_number, start_date])

        if row and row['avg_st'] is not None:
            avg_st = row['avg_st']
            if avg_st < 0.15:
                return f"スタートが得意で平均ST{avg_st:.2f}と早い"
            elif avg_st > 0.20:
                return f"スタートがやや遅く平均ST{avg_st:.2f}"
        return None

    def _analyze_racer_course_strength(self, racer_number: int, start_date: str) -> Dict:
        """コース別得意・不得意分析"""
        query = """
            SELECT
                rd.actual_course as course,
                COUNT(*) as total,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as wins
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
            WHERE e.racer_number = ?
              AND ra.race_date >= ?
            GROUP BY rd.actual_course
            HAVING COUNT(*) >= 5
        """
        rows = self._fetch_all(query, [racer_number, start_date])

        course_rates = {}
        for row in rows:
            course = row['course']
            win_rate = row['wins'] / row['total'] if row['total'] > 0 else 0
            course_rates[course] = win_rate

        if not course_rates:
            return {'strong': [], 'weak': []}

        avg_rate = statistics.mean(course_rates.values())

        strong_courses = [c for c, r in course_rates.items() if r > avg_rate + 0.05]
        weak_courses = [c for c, r in course_rates.items() if r < avg_rate - 0.05]

        return {
            'strong': sorted(strong_courses),
            'weak': sorted(weak_courses)
        }

    def _analyze_racer_venue_strength(self, racer_number: int, start_date: str) -> Dict:
        """会場別得意分析"""
        query = """
            SELECT
                ra.venue_code,
                COUNT(*) as total,
                SUM(CASE WHEN r.rank = 1 THEN 1 ELSE 0 END) as wins
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND ra.race_date >= ?
            GROUP BY ra.venue_code
            HAVING COUNT(*) >= 3
            ORDER BY wins * 1.0 / total DESC
            LIMIT 5
        """
        rows = self._fetch_all(query, [racer_number, start_date])

        strong_venues = [row['venue_code'] for row in rows if row['total'] >= 3]

        return {'strong': strong_venues}

    def _get_racer_favorite_kimarite(self, racer_number: int, start_date: str) -> str:
        """得意な決まり手"""
        query = """
            SELECT
                r.kimarite,
                COUNT(*) as count
            FROM results r
            JOIN races ra ON r.race_id = ra.id
            JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
            WHERE e.racer_number = ?
              AND ra.race_date >= ?
              AND r.rank = '1'
              AND r.kimarite IS NOT NULL
              AND r.kimarite != ''
            GROUP BY r.kimarite
            ORDER BY count DESC
            LIMIT 1
        """
        row = self._fetch_one(query, [racer_number, start_date])
        if row and row['count'] >= 3:
            return row['kimarite']
        return None

    def _determine_performance_level(self, win_rate: float) -> str:
        """パフォーマンスレベル判定"""
        if win_rate > 0.25:
            return "A"
        elif win_rate > 0.15:
            return "B"
        else:
            return "C"

    # ========================================
    # 一括分析
    # ========================================

    def analyze_all_venues(self, days: int = 90) -> Dict[str, Dict]:
        """全競艇場の傾向を一括分析"""
        from config.settings import VENUES

        results = {}
        for venue_code in VENUES.keys():
            analysis = self.analyze_venue_pattern(venue_code, days)
            if analysis:
                results[venue_code] = analysis

        return results

    def get_venue_summary_text(self, venue_code: str, days: int = 90) -> str:
        """競艇場の傾向を自然言語で要約"""
        analysis = self.analyze_venue_pattern(venue_code, days)
        if not analysis:
            return "データが不足しています"

        summary_parts = [
            f"【{analysis['venue_name']}の傾向】",
            ""
        ]

        for i, pattern in enumerate(analysis['patterns'], 1):
            summary_parts.append(f"{i}. {pattern}")

        summary_parts.append("")
        summary_parts.append(f"リスクレベル: {analysis['risk_level'].upper()}")

        if analysis['top_combinations']:
            summary_parts.append("")
            summary_parts.append("よく出る出目:")
            for combo in analysis['top_combinations'][:3]:
                summary_parts.append(f"  - {combo['combination']} ({combo['count']}回)")

        return "\n".join(summary_parts)

    def get_racer_summary_text(self, racer_number: int, days: int = 180) -> str:
        """選手の傾向を自然言語で要約"""
        analysis = self.analyze_racer_pattern(racer_number, days)
        if not analysis:
            return "データが不足しています"

        summary_parts = [
            f"【{analysis['racer_name']}選手の傾向】",
            f"パフォーマンスレベル: {analysis['performance_level']}",
            ""
        ]

        for i, pattern in enumerate(analysis['patterns'], 1):
            summary_parts.append(f"{i}. {pattern}")

        if analysis['basic_stats']:
            stats = analysis['basic_stats']
            summary_parts.append("")
            summary_parts.append(f"直近{days}日間の成績:")
            summary_parts.append(f"  - 出走数: {stats['total_races']}回")
            summary_parts.append(f"  - 勝率: {stats['win_rate']*100:.1f}%")
            summary_parts.append(f"  - 連対率: {stats['place_rate_2']*100:.1f}%")
            summary_parts.append(f"  - 3着内率: {stats['place_rate_3']*100:.1f}%")

        return "\n".join(summary_parts)


if __name__ == "__main__":
    # テスト実行
    analyzer = PatternAnalyzer()

    print("=" * 80)
    print("パターン分析テスト")
    print("=" * 80)

    # 競艇場分析（桐生）
    print("\n【競艇場分析: 桐生】")
    venue_summary = analyzer.get_venue_summary_text('01', days=90)
    print(venue_summary)

    print("\n" + "=" * 80)
