"""
2025年通年データを使った風向×風速×会場×級別の包括的分析

分析対象:
1. 会場別の風速分布
2. 会場別×風向×風速の詳細分析
3. 級別×風速の影響分析
4. 複合的な洞察
"""
import os
import sys
import sqlite3
from typing import Dict, List, Tuple
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


class WeatherComprehensiveAnalyzer:
    """風向×風速×会場×級別の包括的分析器"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def analyze_venue_wind_distribution(self, start_date: str, end_date: str) -> Dict:
        """
        会場別の風速分布を分析

        Returns:
            {会場コード: {total_races, avg_wind, max_wind, strong_wind_count, ...}}
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                r.venue_code,
                COUNT(DISTINCT r.id) as total_races,
                AVG(rc.wind_speed) as avg_wind,
                MAX(rc.wind_speed) as max_wind,
                SUM(CASE WHEN rc.wind_speed >= 8.0 THEN 1 ELSE 0 END) as violent_wind,
                SUM(CASE WHEN rc.wind_speed >= 6.0 AND rc.wind_speed < 8.0 THEN 1 ELSE 0 END) as strong_wind
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND rc.wind_speed IS NOT NULL
            GROUP BY r.venue_code
            ORDER BY violent_wind DESC, avg_wind DESC
        """, (start_date, end_date))

        results = cursor.fetchall()
        conn.close()

        data = {}
        for row in results:
            data[row['venue_code']] = {
                'total_races': row['total_races'],
                'avg_wind': row['avg_wind'],
                'max_wind': row['max_wind'],
                'violent_wind': row['violent_wind'],
                'strong_wind': row['strong_wind']
            }

        return data

    def analyze_venue_wind_direction_detail(self, start_date: str, end_date: str,
                                            venue_codes: List[int] = None) -> Dict:
        """
        会場別×風向×風速の詳細分析

        Args:
            venue_codes: 分析対象の会場コード（Noneなら全会場）

        Returns:
            {会場コード: {風速帯: {風向: {1コース勝率, サンプル数, ...}}}}
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 風速帯・風向別の1コース勝率を取得
        query = """
            SELECT
                r.venue_code,
                rc.wind_speed,
                rc.wind_direction,
                COALESCE(ac.actual_course, res.pit_number) as course,
                res.rank
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            JOIN results res ON r.id = res.race_id
            LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND rc.wind_speed IS NOT NULL
              AND rc.wind_direction IS NOT NULL
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
        """

        params = [start_date, end_date]

        if venue_codes:
            placeholders = ','.join('?' * len(venue_codes))
            query += f" AND r.venue_code IN ({placeholders})"
            params.extend(venue_codes)

        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()

        # 風速帯を定義
        def get_wind_range(wind):
            if wind < 2:
                return '無風(<2m)'
            elif wind < 4:
                return '微風(2-4m)'
            elif wind < 6:
                return '中風(4-6m)'
            elif wind < 8:
                return '強風(6-8m)'
            else:
                return '暴風(8m+)'

        # 統計集計
        stats = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {
            'total': 0,
            'wins': 0
        }))))

        for row in results:
            venue = row['venue_code']
            wind = row['wind_speed']
            direction = row['wind_direction']
            course = row['course']
            rank = int(row['rank']) if row['rank'] else None

            if wind is None or direction is None or rank is None:
                continue

            wind_range = get_wind_range(wind)

            stats[venue][wind_range][direction][course]['total'] += 1

            if rank == 1:
                stats[venue][wind_range][direction][course]['wins'] += 1

        # 勝率を計算
        result = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

        for venue in stats:
            for wind_range in stats[venue]:
                for direction in stats[venue][wind_range]:
                    for course in stats[venue][wind_range][direction]:
                        total = stats[venue][wind_range][direction][course]['total']
                        wins = stats[venue][wind_range][direction][course]['wins']

                        if total >= 3:  # 最低3サンプル
                            result[venue][wind_range][direction][course] = {
                                'win_rate': wins / total * 100,
                                'total': total,
                                'wins': wins
                            }

        return result

    def analyze_racer_rank_by_wind(self, start_date: str, end_date: str) -> Dict:
        """
        級別×風速の影響分析

        Returns:
            {風速帯: {級別: {コース: {勝率, サンプル数}}}}
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                rc.wind_speed,
                e.racer_rank,
                COALESCE(ac.actual_course, res.pit_number) as course,
                res.rank
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            JOIN results res ON r.id = res.race_id
            JOIN entries e ON r.id = e.race_id AND res.pit_number = e.pit_number
            LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND rc.wind_speed IS NOT NULL
              AND e.racer_rank IS NOT NULL
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
        """, (start_date, end_date))

        results = cursor.fetchall()
        conn.close()

        # 風速帯を定義
        def get_wind_range(wind):
            if wind < 6:
                return '通常(<6m)'
            elif wind < 8:
                return '強風(6-8m)'
            else:
                return '暴風(8m+)'

        # 統計集計
        stats = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {
            'total': 0,
            'wins': 0
        })))

        for row in results:
            wind = row['wind_speed']
            racer_rank = row['racer_rank']
            course = row['course']
            rank = int(row['rank']) if row['rank'] else None

            if wind is None or racer_rank is None or rank is None:
                continue

            wind_range = get_wind_range(wind)

            stats[wind_range][racer_rank][course]['total'] += 1

            if rank == 1:
                stats[wind_range][racer_rank][course]['wins'] += 1

        # 勝率を計算
        result = defaultdict(lambda: defaultdict(dict))

        for wind_range in stats:
            for racer_rank in stats[wind_range]:
                for course in stats[wind_range][racer_rank]:
                    total = stats[wind_range][racer_rank][course]['total']
                    wins = stats[wind_range][racer_rank][course]['wins']

                    if total >= 5:  # 最低5サンプル
                        result[wind_range][racer_rank][course] = {
                            'win_rate': wins / total * 100,
                            'total': total,
                            'wins': wins
                        }

        return result

    def get_violent_wind_races_detail(self, start_date: str, end_date: str,
                                     min_wind: float = 8.0) -> List[Dict]:
        """
        暴風レースの詳細情報を取得

        Returns:
            [{race_date, venue_code, race_number, wind_speed, wind_direction, weather}, ...]
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT
                r.race_date,
                r.venue_code,
                r.race_number,
                rc.wind_speed,
                rc.wind_direction,
                rc.weather
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND rc.wind_speed >= ?
            ORDER BY r.race_date, r.venue_code, r.race_number
        """, (start_date, end_date, min_wind))

        results = cursor.fetchall()
        conn.close()

        races = []
        for row in results:
            races.append({
                'race_date': row['race_date'],
                'venue_code': row['venue_code'],
                'race_number': row['race_number'],
                'wind_speed': row['wind_speed'],
                'wind_direction': row['wind_direction'],
                'weather': row['weather']
            })

        return races


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 100)
    print("風向×風速×会場×級別の包括的分析（2025年通年データ）")
    print("=" * 100)

    analyzer = WeatherComprehensiveAnalyzer(db_path)

    # 対象期間（2025年通年）
    start_date = '2025-01-01'
    end_date = '2025-12-31'

    print(f"\n対象期間: {start_date} ~ {end_date}")

    # === 1. 会場別の風速分布 ===
    print("\n" + "=" * 100)
    print("1. 会場別の風速分布")
    print("=" * 100)

    venue_dist = analyzer.analyze_venue_wind_distribution(start_date, end_date)

    print(f"\n{'会場':<6} {'レース数':<10} {'平均風速':<10} {'最大風速':<10} {'暴風(8m+)':<12} {'強風(6-8m)':<12}")
    print("-" * 100)

    total_violent = 0
    total_strong = 0

    for venue_code, data in sorted(venue_dist.items(), key=lambda x: x[1]['violent_wind'], reverse=True):
        venue_num = int(venue_code) if isinstance(venue_code, str) else venue_code
        print(f"{venue_num:02d}     {data['total_races']:6d}件   "
              f"{data['avg_wind']:5.1f}m     {data['max_wind']:5.1f}m     "
              f"{data['violent_wind']:6d}件     {data['strong_wind']:6d}件")

        total_violent += data['violent_wind']
        total_strong += data['strong_wind']

    print("-" * 100)
    print(f"合計: 暴風={total_violent}件, 強風={total_strong}件")

    # === 2. 暴風レースの詳細リスト（サンプル表示） ===
    print("\n" + "=" * 100)
    print("2. 暴風レース(8m+)の詳細（上位30件）")
    print("=" * 100)

    violent_races = analyzer.get_violent_wind_races_detail(start_date, end_date, min_wind=8.0)

    print(f"\n全暴風レース数: {len(violent_races)}件")
    print(f"\n{'日付':<12} {'会場':<6} {'R':<4} {'風速':<8} {'風向':<10} {'天候':<8}")
    print("-" * 100)

    for race in violent_races[:30]:  # 上位30件のみ表示
        venue_num = int(race['venue_code']) if isinstance(race['venue_code'], str) else race['venue_code']
        direction = race['wind_direction'] if race['wind_direction'] else '-'
        weather = race['weather'] if race['weather'] else '-'
        print(f"{race['race_date']}  {venue_num:02d}    "
              f"{race['race_number']:2d}R  {race['wind_speed']:5.1f}m  "
              f"{direction:<10} {weather:<8}")

    # === 3. 会場別×風向×風速の詳細分析（暴風が多い会場のみ） ===
    print("\n" + "=" * 100)
    print("3. 会場別×風向×風速の詳細分析（暴風10件以上の会場）")
    print("=" * 100)

    # 暴風が10件以上の会場を抽出
    target_venues = [venue for venue, data in venue_dist.items() if data['violent_wind'] >= 10]

    print(f"\n分析対象会場: {target_venues} (暴風10件以上)")

    venue_detail = analyzer.analyze_venue_wind_direction_detail(start_date, end_date, target_venues)

    for venue_code in sorted(target_venues):
        if venue_code not in venue_detail:
            continue

        venue_num = int(venue_code) if isinstance(venue_code, str) else venue_code
        print(f"\n### 会場{venue_num:02d} ###")

        # 暴風時のみ表示
        if '暴風(8m+)' in venue_detail[venue_code]:
            print("\n【暴風(8m+)】")

            for direction in venue_detail[venue_code]['暴風(8m+)']:
                print(f"\n風向: {direction}")
                print(f"{'コース':<8} {'勝率':<10} {'サンプル':<10}")
                print("-" * 40)

                # 1コースを優先表示
                for course in sorted(venue_detail[venue_code]['暴風(8m+)'][direction].keys()):
                    data = venue_detail[venue_code]['暴風(8m+)'][direction][course]
                    print(f"{course}コース   {data['win_rate']:5.1f}%    "
                          f"{data['wins']}/{data['total']}艇")

    # === 4. 級別×風速の影響分析 ===
    print("\n" + "=" * 100)
    print("4. 級別×風速の影響分析")
    print("=" * 100)

    racer_rank_data = analyzer.analyze_racer_rank_by_wind(start_date, end_date)

    for wind_range in ['通常(<6m)', '強風(6-8m)', '暴風(8m+)']:
        if wind_range not in racer_rank_data:
            continue

        print(f"\n### {wind_range} ###")

        # 級別ごとに1コース勝率を表示
        print(f"\n{'級別':<8} {'1コース勝率':<12} {'サンプル':<10}")
        print("-" * 40)

        for racer_rank in ['A1', 'A2', 'B1', 'B2']:
            if racer_rank in racer_rank_data[wind_range] and 1 in racer_rank_data[wind_range][racer_rank]:
                data = racer_rank_data[wind_range][racer_rank][1]
                print(f"{racer_rank}級     {data['win_rate']:5.1f}%       "
                      f"{data['wins']}/{data['total']}艇")

        # 全コース別の勝率（暴風時のみ詳細表示）
        if wind_range == '暴風(8m+)':
            print(f"\n【暴風時の級別×コース別勝率】")

            for racer_rank in ['A1', 'B1']:  # A1とB1のみ比較
                if racer_rank not in racer_rank_data[wind_range]:
                    continue

                print(f"\n{racer_rank}級:")
                print(f"{'コース':<8} {'勝率':<10} {'サンプル':<10}")
                print("-" * 40)

                for course in sorted(racer_rank_data[wind_range][racer_rank].keys()):
                    data = racer_rank_data[wind_range][racer_rank][course]
                    print(f"{course}コース   {data['win_rate']:5.1f}%    "
                          f"{data['wins']}/{data['total']}艇")

    print("\n" + "=" * 100)
    print("分析完了")
    print("=" * 100)


if __name__ == "__main__":
    main()
