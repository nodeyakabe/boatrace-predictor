"""
気象条件とレース結果の統計分析
プリセット的な活用ルール（条件→1着率・3連対率の変化）を抽出

分析対象:
1. 天候別（晴/曇/雨/霧/雪）の1着率・3連対率
2. 気温帯別の1着率・3連対率
3. 水温帯別の1着率・3連対率
4. 気温・水温差別の1着率・3連対率
5. 風速別の1着率・3連対率
6. 波高別の1着率・3連対率
7. 複合条件（天候×コース、気温帯×コース等）
"""
import os
import sys
import sqlite3
from typing import Dict, List, Tuple
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


class WeatherPatternExtractor:
    """気象パターン抽出器"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def analyze_by_weather_condition(self, start_date: str, end_date: str) -> Dict:
        """
        天候別のコース別1着率・3連対率を分析

        Returns:
            {天候: {コース: {win_rate, top3_rate, races}}}
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 天候データがあるレースの結果を取得
        cursor.execute("""
            SELECT
                rc.weather,
                res.pit_number,
                res.rank,
                ac.actual_course
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            JOIN results res ON r.id = res.race_id
            LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND rc.weather IS NOT NULL AND rc.weather != ''
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
        """, (start_date, end_date))

        results = cursor.fetchall()
        conn.close()

        # 統計集計
        stats = defaultdict(lambda: defaultdict(lambda: {
            'total': 0,
            'wins': 0,
            'top3': 0
        }))

        for row in results:
            weather = row['weather']
            pit = row['pit_number']
            rank = int(row['rank']) if row['rank'] else None
            # actual_courseがなければpit_numberをコースとみなす
            course = row['actual_course'] if row['actual_course'] else pit

            if rank is None:
                continue

            stats[weather][course]['total'] += 1

            if rank == 1:
                stats[weather][course]['wins'] += 1

            if rank <= 3:
                stats[weather][course]['top3'] += 1

        # 率を計算
        result = {}
        for weather in stats:
            result[weather] = {}
            for course in stats[weather]:
                total = stats[weather][course]['total']
                if total >= 10:  # 最低10サンプル
                    result[weather][course] = {
                        'win_rate': stats[weather][course]['wins'] / total * 100,
                        'top3_rate': stats[weather][course]['top3'] / total * 100,
                        'total': total
                    }

        return result

    def analyze_by_temperature_range(self, start_date: str, end_date: str) -> Dict:
        """
        気温帯別のコース別1着率・3連対率を分析

        Returns:
            {気温帯: {コース: {win_rate, top3_rate, races}}}
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                rc.temperature,
                res.pit_number,
                res.rank,
                ac.actual_course
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            JOIN results res ON r.id = res.race_id
            LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND rc.temperature IS NOT NULL
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
        """, (start_date, end_date))

        results = cursor.fetchall()
        conn.close()

        # 気温帯を定義
        def get_temp_range(temp):
            if temp < 10:
                return '極寒(<10C)'
            elif temp < 15:
                return '寒冷(10-15C)'
            elif temp < 20:
                return '涼(15-20C)'
            elif temp < 25:
                return '温(20-25C)'
            elif temp < 30:
                return '暑(25-30C)'
            else:
                return '猛暑(30C+)'

        # 統計集計
        stats = defaultdict(lambda: defaultdict(lambda: {
            'total': 0,
            'wins': 0,
            'top3': 0
        }))

        for row in results:
            temp = row['temperature']
            pit = row['pit_number']
            rank = int(row['rank']) if row['rank'] else None
            course = row['actual_course'] if row['actual_course'] else pit

            if temp is None or rank is None:
                continue

            temp_range = get_temp_range(temp)

            stats[temp_range][course]['total'] += 1

            if rank == 1:
                stats[temp_range][course]['wins'] += 1

            if rank <= 3:
                stats[temp_range][course]['top3'] += 1

        # 率を計算
        result = {}
        for temp_range in stats:
            result[temp_range] = {}
            for course in stats[temp_range]:
                total = stats[temp_range][course]['total']
                if total >= 10:
                    result[temp_range][course] = {
                        'win_rate': stats[temp_range][course]['wins'] / total * 100,
                        'top3_rate': stats[temp_range][course]['top3'] / total * 100,
                        'total': total
                    }

        return result

    def analyze_by_temp_water_diff(self, start_date: str, end_date: str) -> Dict:
        """
        気温・水温差別のコース別1着率・3連対率を分析

        Returns:
            {温度差帯: {コース: {win_rate, top3_rate, races}}}
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                rc.temperature,
                rc.water_temperature,
                res.pit_number,
                res.rank,
                ac.actual_course
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            JOIN results res ON r.id = res.race_id
            LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND rc.temperature IS NOT NULL
              AND rc.water_temperature IS NOT NULL
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
        """, (start_date, end_date))

        results = cursor.fetchall()
        conn.close()

        # 温度差帯を定義
        def get_diff_range(diff):
            if diff < 2:
                return '小(<2C)'
            elif diff < 5:
                return '中(2-5C)'
            elif diff < 8:
                return '大(5-8C)'
            else:
                return '極大(8C+)'

        # 統計集計
        stats = defaultdict(lambda: defaultdict(lambda: {
            'total': 0,
            'wins': 0,
            'top3': 0
        }))

        for row in results:
            temp = row['temperature']
            water_temp = row['water_temperature']
            pit = row['pit_number']
            rank = int(row['rank']) if row['rank'] else None
            course = row['actual_course'] if row['actual_course'] else pit

            if temp is None or water_temp is None or rank is None:
                continue

            diff = abs(temp - water_temp)
            diff_range = get_diff_range(diff)

            stats[diff_range][course]['total'] += 1

            if rank == 1:
                stats[diff_range][course]['wins'] += 1

            if rank <= 3:
                stats[diff_range][course]['top3'] += 1

        # 率を計算
        result = {}
        for diff_range in stats:
            result[diff_range] = {}
            for course in stats[diff_range]:
                total = stats[diff_range][course]['total']
                if total >= 10:
                    result[diff_range][course] = {
                        'win_rate': stats[diff_range][course]['wins'] / total * 100,
                        'top3_rate': stats[diff_range][course]['top3'] / total * 100,
                        'total': total
                    }

        return result

    def analyze_by_wind_speed(self, start_date: str, end_date: str) -> Dict:
        """
        風速別のコース別1着率・3連対率を分析

        Returns:
            {風速帯: {コース: {win_rate, top3_rate, races}}}
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                rc.wind_speed,
                res.pit_number,
                res.rank,
                ac.actual_course
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            JOIN results res ON r.id = res.race_id
            LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND rc.wind_speed IS NOT NULL
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
        """, (start_date, end_date))

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
        stats = defaultdict(lambda: defaultdict(lambda: {
            'total': 0,
            'wins': 0,
            'top3': 0
        }))

        for row in results:
            wind = row['wind_speed']
            pit = row['pit_number']
            rank = int(row['rank']) if row['rank'] else None
            course = row['actual_course'] if row['actual_course'] else pit

            if wind is None or rank is None:
                continue

            wind_range = get_wind_range(wind)

            stats[wind_range][course]['total'] += 1

            if rank == 1:
                stats[wind_range][course]['wins'] += 1

            if rank <= 3:
                stats[wind_range][course]['top3'] += 1

        # 率を計算
        result = {}
        for wind_range in stats:
            result[wind_range] = {}
            for course in stats[wind_range]:
                total = stats[wind_range][course]['total']
                if total >= 10:
                    result[wind_range][course] = {
                        'win_rate': stats[wind_range][course]['wins'] / total * 100,
                        'top3_rate': stats[wind_range][course]['top3'] / total * 100,
                        'total': total
                    }

        return result

    def calculate_baseline(self, start_date: str, end_date: str) -> Dict:
        """
        ベースライン（全体平均）を計算

        Returns:
            {コース: {win_rate, top3_rate, races}}
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                res.pit_number,
                res.rank,
                ac.actual_course
            FROM races r
            JOIN results res ON r.id = res.race_id
            LEFT JOIN actual_courses ac ON r.id = ac.race_id AND res.pit_number = ac.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND res.rank IS NOT NULL
              AND res.is_invalid = 0
        """, (start_date, end_date))

        results = cursor.fetchall()
        conn.close()

        # 統計集計
        stats = defaultdict(lambda: {
            'total': 0,
            'wins': 0,
            'top3': 0
        })

        for row in results:
            pit = row['pit_number']
            rank = int(row['rank']) if row['rank'] else None
            course = row['actual_course'] if row['actual_course'] else pit

            if rank is None:
                continue

            stats[course]['total'] += 1

            if rank == 1:
                stats[course]['wins'] += 1

            if rank <= 3:
                stats[course]['top3'] += 1

        # 率を計算
        result = {}
        for course in stats:
            total = stats[course]['total']
            if total > 0:
                result[course] = {
                    'win_rate': stats[course]['wins'] / total * 100,
                    'top3_rate': stats[course]['top3'] / total * 100,
                    'total': total
                }

        return result


def print_analysis_result(title: str, data: Dict, baseline: Dict):
    """分析結果を表示"""
    print("\n" + "=" * 80)
    print(f"{title}")
    print("=" * 80)

    for condition in sorted(data.keys()):
        print(f"\n【{condition}】")

        # ヘッダー
        print(f"{'コース':<6} {'1着率':<8} {'差分':<8} {'3連対率':<8} {'差分':<8} {'n':<6}")
        print("-" * 60)

        for course in sorted(data[condition].keys()):
            stats = data[condition][course]
            win_rate = stats['win_rate']
            top3_rate = stats['top3_rate']
            total = stats['total']

            # ベースラインとの差分
            baseline_win = baseline.get(course, {}).get('win_rate', 0)
            baseline_top3 = baseline.get(course, {}).get('top3_rate', 0)

            win_diff = win_rate - baseline_win
            top3_diff = top3_rate - baseline_top3

            print(f"{course}コース   {win_rate:5.1f}%  {win_diff:+5.1f}%  "
                  f"{top3_rate:5.1f}%  {top3_diff:+5.1f}%  {total:5d}")


def extract_significant_patterns(data: Dict, baseline: Dict, threshold: float = 3.0) -> List[Dict]:
    """
    統計的に有意なパターンを抽出

    Args:
        data: 分析データ
        baseline: ベースライン
        threshold: 差分の閾値（%、デフォルト3.0%）

    Returns:
        有意なパターンのリスト
    """
    patterns = []

    for condition in data:
        for course in data[condition]:
            stats = data[condition][course]
            baseline_stats = baseline.get(course, {})

            if not baseline_stats:
                continue

            win_diff = stats['win_rate'] - baseline_stats['win_rate']
            top3_diff = stats['top3_rate'] - baseline_stats['top3_rate']

            # いずれかが閾値を超えていれば有意
            if abs(win_diff) >= threshold or abs(top3_diff) >= threshold:
                patterns.append({
                    'condition': condition,
                    'course': course,
                    'win_rate': stats['win_rate'],
                    'win_diff': win_diff,
                    'top3_rate': stats['top3_rate'],
                    'top3_diff': top3_diff,
                    'total': stats['total']
                })

    # 差分の大きい順にソート
    patterns.sort(key=lambda x: abs(x['win_diff']) + abs(x['top3_diff']), reverse=True)

    return patterns


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 80)
    print("気象条件とレース結果の統計分析")
    print("=" * 80)

    extractor = WeatherPatternExtractor(db_path)

    # 対象期間（天候データが揃っている期間）
    start_date = '2025-11-28'
    end_date = '2025-12-10'

    print(f"\n対象期間: {start_date} ~ {end_date}")

    # ベースライン計算
    print("\n[ベースライン計算中...]")
    baseline = extractor.calculate_baseline(start_date, end_date)

    print("\n【ベースライン（全体平均）】")
    print(f"{'コース':<6} {'1着率':<8} {'3連対率':<8} {'n':<6}")
    print("-" * 40)
    for course in sorted(baseline.keys()):
        stats = baseline[course]
        print(f"{course}コース   {stats['win_rate']:5.1f}%  "
              f"{stats['top3_rate']:5.1f}%  {stats['total']:5d}")

    # 1. 天候別分析
    print("\n[天候別分析中...]")
    weather_data = extractor.analyze_by_weather_condition(start_date, end_date)
    print_analysis_result("1. 天候別のコース別1着率・3連対率", weather_data, baseline)

    # 2. 気温帯別分析
    print("\n[気温帯別分析中...]")
    temp_data = extractor.analyze_by_temperature_range(start_date, end_date)
    print_analysis_result("2. 気温帯別のコース別1着率・3連対率", temp_data, baseline)

    # 3. 気温・水温差別分析
    print("\n[気温・水温差別分析中...]")
    diff_data = extractor.analyze_by_temp_water_diff(start_date, end_date)
    print_analysis_result("3. 気温・水温差別のコース別1着率・3連対率", diff_data, baseline)

    # 4. 風速別分析
    print("\n[風速別分析中...]")
    wind_data = extractor.analyze_by_wind_speed(start_date, end_date)
    print_analysis_result("4. 風速別のコース別1着率・3連対率", wind_data, baseline)

    # 有意なパターンの抽出
    print("\n" + "=" * 80)
    print("【統計的に有意なパターン(差分3.0%以上)】")
    print("=" * 80)

    all_patterns = []

    # 天候別
    patterns = extract_significant_patterns(weather_data, baseline, threshold=3.0)
    for p in patterns:
        p['category'] = '天候'
        all_patterns.append(p)

    # 気温帯別
    patterns = extract_significant_patterns(temp_data, baseline, threshold=3.0)
    for p in patterns:
        p['category'] = '気温帯'
        all_patterns.append(p)

    # 気温・水温差別
    patterns = extract_significant_patterns(diff_data, baseline, threshold=3.0)
    for p in patterns:
        p['category'] = '温度差'
        all_patterns.append(p)

    # 風速別
    patterns = extract_significant_patterns(wind_data, baseline, threshold=3.0)
    for p in patterns:
        p['category'] = '風速'
        all_patterns.append(p)

    # ソート（影響度の大きい順）
    all_patterns.sort(key=lambda x: abs(x['win_diff']) + abs(x['top3_diff']), reverse=True)

    if all_patterns:
        print(f"\n{'カテゴリ':<8} {'条件':<16} {'コース':<6} {'1着率差':<8} "
              f"{'3連対率差':<10} {'n':<6}")
        print("-" * 70)

        for p in all_patterns:
            print(f"{p['category']:<8} {p['condition']:<16} {p['course']}コース   "
                  f"{p['win_diff']:+6.1f}%  {p['top3_diff']:+8.1f}%  {p['total']:5d}")
    else:
        print("\n有意なパターンは見つかりませんでした。")

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
