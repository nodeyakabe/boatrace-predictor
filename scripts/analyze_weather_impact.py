"""
気象情報活用の効果検証スクリプト

Phase 1-3で実装した気象情報活用機能の効果を検証:
- ベースライン（気象スコアなし）vs 拡張版（気象スコアあり）
- 天候条件別の的中率・ROI比較
- インコース vs 外コースへの影響分析
"""
import os
import sys
import sqlite3
from typing import Dict, List, Tuple
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.analysis.beforeinfo_scorer import BeforeInfoScorer
from src.analysis.race_predictor import RacePredictor


class WeatherImpactAnalyzer:
    """気象情報の影響度分析"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.scorer = BeforeInfoScorer()
        self.predictor = RacePredictor()

    def analyze_weather_score_impact(self, start_date: str, end_date: str) -> Dict:
        """
        気象スコアの影響度を分析

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)

        Returns:
            分析結果の辞書
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 天候データが揃っているレースを取得
        cursor.execute("""
            SELECT r.id, r.venue_code, r.race_date, r.race_number,
                   rc.temperature, rc.water_temperature, rc.weather,
                   rc.wind_speed, rc.wave_height
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND rc.weather IS NOT NULL AND rc.weather != ''
              AND rc.temperature IS NOT NULL
            ORDER BY r.race_date, r.venue_code, r.race_number
        """, (start_date, end_date))

        races = cursor.fetchall()

        print(f"\n分析対象レース: {len(races)}件 ({start_date} ~ {end_date})")

        # 統計情報
        stats = {
            'total_races': len(races),
            'weather_score_distribution': defaultdict(int),
            'score_by_course': defaultdict(list),
            'score_by_weather': defaultdict(list),
            'extreme_weather_cases': []
        }

        for race in races:
            race_id = race['id']
            venue_code = race['venue_code']
            temperature = race['temperature']
            water_temp = race['water_temperature']
            weather_condition = race['weather']

            # 各艇の気象スコアを計算
            for pit in range(1, 7):
                result = self.scorer.calculate_beforeinfo_score(race_id, pit)
                weather_score = result['weather_score']

                # スコア分布
                score_bucket = int(weather_score / 2) * 2  # 2点刻みでバケット化
                stats['weather_score_distribution'][score_bucket] += 1

                # コース別スコア
                stats['score_by_course'][pit].append(weather_score)

                # 天候別スコア
                stats['score_by_weather'][weather_condition].append(weather_score)

                # 極端な気象条件のケース（|score| >= 5.0）
                if abs(weather_score) >= 5.0:
                    stats['extreme_weather_cases'].append({
                        'race_id': race_id,
                        'venue_code': venue_code,
                        'race_date': race['race_date'],
                        'race_number': race['race_number'],
                        'pit': pit,
                        'weather_score': weather_score,
                        'temperature': temperature,
                        'water_temp': water_temp,
                        'weather_condition': weather_condition,
                        'total_score': result['total_score']
                    })

        conn.close()
        return stats

    def analyze_prediction_accuracy(self, start_date: str, end_date: str) -> Dict:
        """
        予測精度への影響を分析（ベースライン vs 拡張版）

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)

        Returns:
            精度比較結果
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 結果が確定しているレースを取得（resultsテーブルを使用）
        cursor.execute("""
            SELECT DISTINCT r.id, r.venue_code, r.race_date, r.race_number,
                   rc.weather
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            JOIN results res ON r.id = res.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND rc.weather IS NOT NULL AND rc.weather != ''
              AND res.rank IS NOT NULL
            ORDER BY r.race_date, r.venue_code, r.race_number
        """, (start_date, end_date))

        races = cursor.fetchall()

        print(f"\n精度分析対象レース: {len(races)}件")

        # 天候条件別の統計
        stats_by_weather = defaultdict(lambda: {
            'total': 0,
            'baseline_top3_correct': 0,
            'enhanced_top3_correct': 0,
            'baseline_winner_correct': 0,
            'enhanced_winner_correct': 0,
            'score_diff_avg': 0.0
        })

        # 全体統計
        overall_stats = {
            'total': 0,
            'baseline_top3_correct': 0,
            'enhanced_top3_correct': 0,
            'baseline_winner_correct': 0,
            'enhanced_winner_correct': 0
        }

        for race in races:
            race_id = race['id']
            weather_condition = race['weather']

            # 実際の結果を取得
            cursor.execute("""
                SELECT pit_number, rank
                FROM results
                WHERE race_id = ? AND rank IS NOT NULL AND is_invalid = 0
                ORDER BY CAST(rank AS INTEGER)
            """, (race_id,))
            results = cursor.fetchall()

            if len(results) < 3:
                continue

            actual_winner = results[0]['pit_number']
            actual_top3 = {r['pit_number'] for r in results[:3]}

            # ベースライン予測（気象スコアを0として計算）
            baseline_scores = {}
            enhanced_scores = {}

            for pit in range(1, 7):
                result = self.scorer.calculate_beforeinfo_score(race_id, pit)

                # 拡張版（実際のスコア）
                enhanced_scores[pit] = result['total_score']

                # ベースライン（気象スコアを除外）
                baseline_scores[pit] = result['total_score'] - result['weather_score']

            # ソート（スコアの高い順）
            baseline_ranking = sorted(baseline_scores.items(), key=lambda x: x[1], reverse=True)
            enhanced_ranking = sorted(enhanced_scores.items(), key=lambda x: x[1], reverse=True)

            baseline_pred_winner = baseline_ranking[0][0]
            baseline_pred_top3 = {pit for pit, _ in baseline_ranking[:3]}

            enhanced_pred_winner = enhanced_ranking[0][0]
            enhanced_pred_top3 = {pit for pit, _ in enhanced_ranking[:3]}

            # 的中判定
            baseline_top3_hit = len(baseline_pred_top3 & actual_top3)
            enhanced_top3_hit = len(enhanced_pred_top3 & actual_top3)

            baseline_winner_hit = 1 if baseline_pred_winner == actual_winner else 0
            enhanced_winner_hit = 1 if enhanced_pred_winner == actual_winner else 0

            # 統計更新
            stats_by_weather[weather_condition]['total'] += 1
            stats_by_weather[weather_condition]['baseline_top3_correct'] += baseline_top3_hit
            stats_by_weather[weather_condition]['enhanced_top3_correct'] += enhanced_top3_hit
            stats_by_weather[weather_condition]['baseline_winner_correct'] += baseline_winner_hit
            stats_by_weather[weather_condition]['enhanced_winner_correct'] += enhanced_winner_hit

            overall_stats['total'] += 1
            overall_stats['baseline_top3_correct'] += baseline_top3_hit
            overall_stats['enhanced_top3_correct'] += enhanced_top3_hit
            overall_stats['baseline_winner_correct'] += baseline_winner_hit
            overall_stats['enhanced_winner_correct'] += enhanced_winner_hit

        conn.close()

        return {
            'overall': overall_stats,
            'by_weather': dict(stats_by_weather)
        }

    def analyze_pit_impact(self, start_date: str, end_date: str) -> Dict:
        """
        ピット番号別の気象スコア影響度を分析

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)

        Returns:
            ピット番号別分析結果
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 天候条件別・ピット番号別の統計
        stats = defaultdict(lambda: defaultdict(lambda: {
            'count': 0,
            'avg_weather_score': 0.0,
            'total_weather_score': 0.0
        }))

        # 各レースの気象スコアを取得
        cursor.execute("""
            SELECT r.id, rc.weather
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND rc.weather IS NOT NULL AND rc.weather != ''
        """, (start_date, end_date))

        races = cursor.fetchall()

        for race in races:
            race_id = race['id']
            weather = race['weather']

            for pit in range(1, 7):
                result = self.scorer.calculate_beforeinfo_score(race_id, pit)
                weather_score = result['weather_score']

                stats[weather][pit]['count'] += 1
                stats[weather][pit]['total_weather_score'] += weather_score

        # 平均を計算
        for weather in stats:
            for pit in stats[weather]:
                if stats[weather][pit]['count'] > 0:
                    stats[weather][pit]['avg_weather_score'] = (
                        stats[weather][pit]['total_weather_score'] /
                        stats[weather][pit]['count']
                    )

        conn.close()
        return dict(stats)


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')

    print("=" * 80)
    print("気象情報活用の効果検証")
    print("=" * 80)

    analyzer = WeatherImpactAnalyzer(db_path)

    # 対象期間（天候データが100%揃っている期間）
    start_date = '2025-11-28'
    end_date = '2025-12-10'

    print(f"\n対象期間: {start_date} ~ {end_date}")
    print("（天候データが完全に揃っている期間）")

    # === 1. 気象スコアの影響度分析 ===
    print("\n" + "=" * 80)
    print("1. 気象スコアの影響度分析")
    print("=" * 80)

    stats = analyzer.analyze_weather_score_impact(start_date, end_date)

    print(f"\n総レース数: {stats['total_races']}件")
    print(f"総艇数: {stats['total_races'] * 6}艇")

    print("\n【気象スコア分布】")
    for score_bucket in sorted(stats['weather_score_distribution'].keys()):
        count = stats['weather_score_distribution'][score_bucket]
        pct = count / (stats['total_races'] * 6) * 100
        print(f"  {score_bucket:+3d}点台: {count:4d}艇 ({pct:5.1f}%)")

    print("\n【コース別平均気象スコア】")
    for course in sorted(stats['score_by_course'].keys()):
        scores = stats['score_by_course'][course]
        avg = sum(scores) / len(scores) if scores else 0.0
        print(f"  {course}コース: {avg:+6.2f}点 (n={len(scores)})")

    print("\n【天候条件別平均気象スコア】")
    for weather in sorted(stats['score_by_weather'].keys()):
        scores = stats['score_by_weather'][weather]
        avg = sum(scores) / len(scores) if scores else 0.0
        print(f"  {weather}: {avg:+6.2f}点 (n={len(scores)})")

    print(f"\n【極端な気象条件のケース（|スコア| >= 5.0点）】")
    print(f"  該当件数: {len(stats['extreme_weather_cases'])}件")

    if stats['extreme_weather_cases']:
        print("\n  上位10件:")
        sorted_cases = sorted(stats['extreme_weather_cases'],
                            key=lambda x: abs(x['weather_score']), reverse=True)[:10]

        for case in sorted_cases:
            print(f"    {case['race_date']} {case['venue_code']}R{case['race_number']:02d} "
                  f"{case['pit']}号艇: 気象スコア={case['weather_score']:+6.2f}点, "
                  f"総合スコア={case['total_score']:6.2f}点")
            print(f"      気温={case['temperature']}℃, 水温={case['water_temp']}℃, "
                  f"天候={case['weather_condition']}")

    # === 2. 予測精度への影響分析 ===
    print("\n" + "=" * 80)
    print("2. 予測精度への影響分析（ベースライン vs 拡張版）")
    print("=" * 80)

    accuracy_stats = analyzer.analyze_prediction_accuracy(start_date, end_date)

    overall = accuracy_stats['overall']

    print("\n【全体統計】")
    print(f"  対象レース: {overall['total']}件")

    if overall['total'] > 0:
        baseline_top3_rate = overall['baseline_top3_correct'] / (overall['total'] * 3) * 100
        enhanced_top3_rate = overall['enhanced_top3_correct'] / (overall['total'] * 3) * 100
        baseline_winner_rate = overall['baseline_winner_correct'] / overall['total'] * 100
        enhanced_winner_rate = overall['enhanced_winner_correct'] / overall['total'] * 100

        print(f"\n  3連対的中数:")
        print(f"    ベースライン: {overall['baseline_top3_correct']} / {overall['total'] * 3} ({baseline_top3_rate:.1f}%)")
        print(f"    拡張版:       {overall['enhanced_top3_correct']} / {overall['total'] * 3} ({enhanced_top3_rate:.1f}%)")
        print(f"    改善:         {enhanced_top3_rate - baseline_top3_rate:+.1f}ポイント")

        print(f"\n  1着的中数:")
        print(f"    ベースライン: {overall['baseline_winner_correct']} / {overall['total']} ({baseline_winner_rate:.1f}%)")
        print(f"    拡張版:       {overall['enhanced_winner_correct']} / {overall['total']} ({enhanced_winner_rate:.1f}%)")
        print(f"    改善:         {enhanced_winner_rate - baseline_winner_rate:+.1f}ポイント")

    print("\n【天候条件別統計】")
    for weather, stats in sorted(accuracy_stats['by_weather'].items()):
        if stats['total'] == 0:
            continue

        baseline_top3_rate = stats['baseline_top3_correct'] / (stats['total'] * 3) * 100
        enhanced_top3_rate = stats['enhanced_top3_correct'] / (stats['total'] * 3) * 100
        baseline_winner_rate = stats['baseline_winner_correct'] / stats['total'] * 100
        enhanced_winner_rate = stats['enhanced_winner_correct'] / stats['total'] * 100

        print(f"\n  [{weather}] (n={stats['total']})")
        print(f"    3連対的中率: {baseline_top3_rate:.1f}% → {enhanced_top3_rate:.1f}% ({enhanced_top3_rate - baseline_top3_rate:+.1f}pt)")
        print(f"    1着的中率:   {baseline_winner_rate:.1f}% → {enhanced_winner_rate:.1f}% ({enhanced_winner_rate - baseline_winner_rate:+.1f}pt)")

    # === 3. ピット番号別影響度分析 ===
    print("\n" + "=" * 80)
    print("3. ピット番号別気象スコア影響度")
    print("=" * 80)

    pit_stats = analyzer.analyze_pit_impact(start_date, end_date)

    for weather in sorted(pit_stats.keys()):
        print(f"\n【{weather}】")
        for pit in sorted(pit_stats[weather].keys()):
            info = pit_stats[weather][pit]
            print(f"  {pit}号艇: 平均スコア={info['avg_weather_score']:+6.2f}点 (n={info['count']})")

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
