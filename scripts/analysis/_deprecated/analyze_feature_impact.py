# -*- coding: utf-8 -*-
"""
特徴量効果の検証スクリプト

実装済みの特徴量の効果を測定:
1. 会場×コース勝率テーブル（24会場×6コース=144エントリー）
2. 天候強化特徴量（風向×風速の複合補正）
3. チルト×風向シナジー

検証項目:
- 各特徴量の的中率への寄与度
- ROI改善効果
- 会場別の効果差
"""

import sys
import sqlite3
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple
from collections import defaultdict

# パス設定
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


class FeatureImpactAnalyzer:
    """特徴量効果分析クラス"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def analyze_venue_course_win_rate_impact(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """会場×コース勝率テーブルの効果分析"""
        print("\n" + "=" * 70)
        print("1. 会場×コース勝率テーブルの効果分析")
        print("=" * 70)

        cursor = self.conn.cursor()

        # 会場×コース別の実勝率と予測精度を確認
        cursor.execute('''
            SELECT
                r.venue_code,
                e.pit_number as course,
                COUNT(*) as total_races,
                SUM(CASE WHEN res.rank = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN p.rank_prediction = 1 AND res.rank = 1 THEN 1 ELSE 0 END) as correct_predictions
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            LEFT JOIN race_predictions p ON r.id = p.race_id AND e.pit_number = p.pit_number
                AND p.prediction_type = 'advance'
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND e.racer_rank IN ('A1', 'A2', 'B1')  -- 主要級別のみ
            GROUP BY r.venue_code, e.pit_number
            HAVING total_races >= 50  -- 最低50レース以上
            ORDER BY r.venue_code, e.pit_number
        ''', (start_date, end_date))

        venue_course_stats = []
        total_correct = 0
        total_predictions = 0

        print("\n会場×コース別 実勝率 vs 予測精度:")
        print(f"{'会場':4} {'コース':6} {'レース数':8} {'実勝率':8} {'予測精度':10} {'差分':6}")
        print("-" * 60)

        for row in cursor.fetchall():
            venue = row['venue_code']
            course = row['course']
            total = row['total_races']
            wins = row['wins']
            correct = row['correct_predictions'] or 0

            win_rate = (wins / total * 100) if total > 0 else 0
            prediction_accuracy = (correct / total * 100) if total > 0 else 0
            diff = prediction_accuracy - win_rate

            venue_course_stats.append({
                'venue_code': venue,
                'course': course,
                'total_races': total,
                'win_rate': win_rate,
                'prediction_accuracy': prediction_accuracy,
                'diff': diff
            })

            total_correct += correct
            total_predictions += total

            print(f"{venue:4} {course:6} {total:8} {win_rate:7.1f}% {prediction_accuracy:9.1f}% {diff:+6.1f}%")

        overall_accuracy = (total_correct / total_predictions * 100) if total_predictions > 0 else 0
        print("-" * 60)
        print(f"全体平均予測精度: {overall_accuracy:.1f}%")

        # 会場×コース勝率テーブルの効果（インが強い/弱い会場での精度差）
        print("\n会場特性別の予測精度:")

        # インが強い会場（徳山、大村、下関）
        strong_in_venues = ['18', '24', '19']
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN p.rank_prediction = 1 AND res.rank = 1 THEN 1 ELSE 0 END) as hits
            FROM races r
            JOIN race_predictions p ON r.id = p.race_id
            JOIN results res ON r.id = res.race_id AND p.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND p.prediction_type = 'advance'
              AND p.rank_prediction = 1
              AND r.venue_code IN ({})
        '''.format(','.join(['?' for _ in strong_in_venues])), (start_date, end_date, *strong_in_venues))

        strong_in = cursor.fetchone()
        strong_in_accuracy = (strong_in['hits'] / strong_in['total'] * 100) if strong_in['total'] > 0 else 0

        # インが弱い会場（戸田、平和島、江戸川）
        weak_in_venues = ['02', '04', '03']
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN p.rank_prediction = 1 AND res.rank = 1 THEN 1 ELSE 0 END) as hits
            FROM races r
            JOIN race_predictions p ON r.id = p.race_id
            JOIN results res ON r.id = res.race_id AND p.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
              AND p.prediction_type = 'advance'
              AND p.rank_prediction = 1
              AND r.venue_code IN ({})
        '''.format(','.join(['?' for _ in weak_in_venues])), (start_date, end_date, *weak_in_venues))

        weak_in = cursor.fetchone()
        weak_in_accuracy = (weak_in['hits'] / weak_in['total'] * 100) if weak_in['total'] > 0 else 0

        print(f"  インが強い会場（徳山、大村、下関）: {strong_in_accuracy:.1f}% ({strong_in['hits']}/{strong_in['total']})")
        print(f"  インが弱い会場（戸田、平和島、江戸川）: {weak_in_accuracy:.1f}% ({weak_in['hits']}/{weak_in['total']})")
        print(f"  精度差: {strong_in_accuracy - weak_in_accuracy:+.1f}pt")

        return {
            'venue_course_stats': venue_course_stats,
            'overall_accuracy': overall_accuracy,
            'strong_in_accuracy': strong_in_accuracy,
            'weak_in_accuracy': weak_in_accuracy,
            'accuracy_diff': strong_in_accuracy - weak_in_accuracy
        }

    def analyze_weather_feature_impact(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """天候強化特徴量の効果分析"""
        print("\n" + "=" * 70)
        print("2. 天候強化特徴量の効果分析")
        print("=" * 70)

        cursor = self.conn.cursor()

        # 風速別の予測精度
        print("\n風速別の予測精度:")
        print(f"{'風速':10} {'レース数':8} {'1着的中':8} {'的中率':8}")
        print("-" * 40)

        wind_speed_bins = [
            (0, 2, '微風 (0-2m)'),
            (2, 4, '弱風 (2-4m)'),
            (4, 6, '中風 (4-6m)'),
            (6, 100, '強風 (6m+)')
        ]

        wind_results = []
        for min_speed, max_speed, label in wind_speed_bins:
            cursor.execute('''
                SELECT
                    COUNT(DISTINCT r.id) as total,
                    SUM(CASE WHEN p.rank_prediction = 1 AND res.rank = 1 THEN 1 ELSE 0 END) as hits
                FROM races r
                JOIN race_conditions rc ON r.id = rc.race_id
                JOIN race_predictions p ON r.id = p.race_id
                JOIN results res ON r.id = res.race_id AND p.pit_number = res.pit_number
                WHERE r.race_date >= ? AND r.race_date <= ?
                  AND p.prediction_type = 'advance'
                  AND p.rank_prediction = 1
                  AND rc.wind_speed >= ? AND rc.wind_speed < ?
            ''', (start_date, end_date, min_speed, max_speed))

            row = cursor.fetchone()
            total = row['total']
            hits = row['hits'] or 0
            accuracy = (hits / total * 100) if total > 0 else 0

            wind_results.append({
                'label': label,
                'total': total,
                'hits': hits,
                'accuracy': accuracy
            })

            print(f"{label:10} {total:8} {hits:8} {accuracy:7.1f}%")

        # 風向別の予測精度
        print("\n風向別の予測精度:")
        print(f"{'風向':15} {'レース数':8} {'1着的中':8} {'的中率':8}")
        print("-" * 45)

        # 追い風系（南）vs 向かい風系（北）
        wind_directions = [
            (['南', '南南東', '南東', '東南東', '南南西', '南西', '西南西'], '追い風系'),
            (['北', '北北東', '北東', '東北東', '北北西', '北西', '西北西'], '向かい風系'),
            (['東', '西'], '横風'),
        ]

        wind_dir_results = []
        for directions, label in wind_directions:
            placeholders = ','.join(['?' for _ in directions])
            cursor.execute(f'''
                SELECT
                    COUNT(DISTINCT r.id) as total,
                    SUM(CASE WHEN p.rank_prediction = 1 AND res.rank = 1 THEN 1 ELSE 0 END) as hits
                FROM races r
                JOIN race_conditions rc ON r.id = rc.race_id
                JOIN race_predictions p ON r.id = p.race_id
                JOIN results res ON r.id = res.race_id AND p.pit_number = res.pit_number
                WHERE r.race_date >= ? AND r.race_date <= ?
                  AND p.prediction_type = 'advance'
                  AND p.rank_prediction = 1
                  AND rc.wind_direction IN ({placeholders})
                  AND rc.wind_speed >= 3  -- 風速3m以上のみ
            ''', (start_date, end_date, *directions))

            row = cursor.fetchone()
            total = row['total']
            hits = row['hits'] or 0
            accuracy = (hits / total * 100) if total > 0 else 0

            wind_dir_results.append({
                'label': label,
                'total': total,
                'hits': hits,
                'accuracy': accuracy
            })

            print(f"{label:15} {total:8} {hits:8} {accuracy:7.1f}%")

        return {
            'wind_speed_results': wind_results,
            'wind_direction_results': wind_dir_results
        }

    def analyze_tilt_wind_synergy(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """チルト×風向シナジーの効果分析"""
        print("\n" + "=" * 70)
        print("3. チルト×風向シナジーの効果分析")
        print("=" * 70)

        cursor = self.conn.cursor()

        # チルト角度×風向の組み合わせ効果
        print("\nチルト角度×風向の1着的中率:")
        print(f"{'チルト':8} {'風向':10} {'レース数':8} {'1着的中':8} {'的中率':8}")
        print("-" * 50)

        tilt_bins = [
            (-0.5, -0.5, '-0.5'),
            (0.0, 0.0, '0.0'),
            (0.5, 0.5, '+0.5'),
            (1.0, 1.0, '+1.0'),
            (1.5, 100, '+1.5以上')
        ]

        wind_types = [
            (['南', '南南東', '南東', '東南東', '南南西', '南西', '西南西'], '追い風'),
            (['北', '北北東', '北東', '東北東', '北北西', '北西', '西北西'], '向かい風'),
        ]

        synergy_results = []
        for tilt_min, tilt_max, tilt_label in tilt_bins:
            for directions, wind_label in wind_types:
                placeholders = ','.join(['?' for _ in directions])
                cursor.execute(f'''
                    SELECT
                        COUNT(DISTINCT r.id) as total,
                        SUM(CASE WHEN p.rank_prediction = 1 AND res.rank = 1 THEN 1 ELSE 0 END) as hits
                    FROM races r
                    JOIN race_details rd ON r.id = rd.race_id
                    JOIN race_conditions rc ON r.id = rc.race_id
                    JOIN race_predictions p ON r.id = p.race_id AND rd.pit_number = p.pit_number
                    JOIN results res ON r.id = res.race_id AND p.pit_number = res.pit_number
                    WHERE r.race_date >= ? AND r.race_date <= ?
                      AND p.prediction_type = 'advance'
                      AND p.rank_prediction = 1
                      AND rd.tilt_angle >= ? AND rd.tilt_angle <= ?
                      AND rc.wind_direction IN ({placeholders})
                      AND rc.wind_speed >= 3  -- 風速3m以上
                ''', (start_date, end_date, tilt_min, tilt_max, *directions))

                row = cursor.fetchone()
                total = row['total']
                hits = row['hits'] or 0
                accuracy = (hits / total * 100) if total > 0 else 0

                if total >= 10:  # 最低10レース以上
                    synergy_results.append({
                        'tilt': tilt_label,
                        'wind': wind_label,
                        'total': total,
                        'hits': hits,
                        'accuracy': accuracy
                    })

                    print(f"{tilt_label:8} {wind_label:10} {total:8} {hits:8} {accuracy:7.1f}%")

        return {
            'synergy_results': synergy_results
        }

    def calculate_overall_impact(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """総合的な効果の計算"""
        print("\n" + "=" * 70)
        print("総合評価")
        print("=" * 70)

        # 会場×コース勝率テーブルの効果
        venue_impact = results['venue_course']['accuracy_diff']
        print(f"\n1. 会場×コース勝率テーブル:")
        print(f"   インが強い会場 vs 弱い会場の精度差: {venue_impact:+.1f}pt")
        if abs(venue_impact) >= 1.5:
            print(f"   評価: [OK] 効果が認められる（{venue_impact:+.1f}pt）")
        else:
            print(f"   評価: [警告] 効果が小さい（{venue_impact:+.1f}pt）")

        # 天候強化特徴量の効果
        wind_speed_results = results['weather']['wind_speed_results']
        calm_accuracy = next((r['accuracy'] for r in wind_speed_results if '微風' in r['label']), 0)
        strong_accuracy = next((r['accuracy'] for r in wind_speed_results if '強風' in r['label']), 0)
        wind_impact = abs(calm_accuracy - strong_accuracy)

        print(f"\n2. 天候強化特徴量（風速）:")
        print(f"   微風 vs 強風の精度差: {wind_impact:.1f}pt")
        if wind_impact >= 0.7:
            print(f"   評価: [OK] 効果が認められる（{wind_impact:.1f}pt）")
        else:
            print(f"   評価: [警告] 効果が小さい（{wind_impact:.1f}pt）")

        # チルト×風向シナジーの効果
        synergy_results = results['synergy']['synergy_results']
        if synergy_results:
            max_accuracy = max(r['accuracy'] for r in synergy_results)
            min_accuracy = min(r['accuracy'] for r in synergy_results)
            synergy_impact = max_accuracy - min_accuracy

            print(f"\n3. チルト×風向シナジー:")
            print(f"   最大精度差: {synergy_impact:.1f}pt")
            if synergy_impact >= 1.0:
                print(f"   評価: [OK] シナジー効果が認められる（{synergy_impact:.1f}pt）")
            else:
                print(f"   評価: [警告] シナジー効果が小さい（{synergy_impact:.1f}pt）")
        else:
            synergy_impact = 0
            print(f"\n3. チルト×風向シナジー:")
            print(f"   評価: [警告] データ不足で評価不能")

        # 総合評価
        print("\n" + "=" * 70)
        print("推奨アクション")
        print("=" * 70)

        recommendations = []

        if abs(venue_impact) >= 1.5:
            recommendations.append("[採用] 会場×コース勝率テーブルは有効 -> 維持")
        else:
            recommendations.append("[検討] 会場×コース勝率テーブルの見直し")

        if wind_impact >= 0.7:
            recommendations.append("[採用] 天候強化特徴量は有効 -> 維持")
        else:
            recommendations.append("[検討] 天候強化特徴量の見直し")

        if synergy_impact >= 1.0:
            recommendations.append("[採用] チルト×風向シナジーは有効 -> 維持")
        else:
            recommendations.append("[検討] チルト×風向シナジーの見直し")

        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec}")

        return {
            'venue_impact': venue_impact,
            'wind_impact': wind_impact,
            'synergy_impact': synergy_impact,
            'recommendations': recommendations
        }

    def run_full_analysis(self, start_date: str, end_date: str):
        """完全な分析を実行"""
        print("\n" + "=" * 70)
        print("特徴量効果の検証")
        print("=" * 70)
        print(f"期間: {start_date} ～ {end_date}")

        results = {}

        # 1. 会場×コース勝率テーブル
        results['venue_course'] = self.analyze_venue_course_win_rate_impact(start_date, end_date)

        # 2. 天候強化特徴量
        results['weather'] = self.analyze_weather_feature_impact(start_date, end_date)

        # 3. チルト×風向シナジー
        results['synergy'] = self.analyze_tilt_wind_synergy(start_date, end_date)

        # 4. 総合評価
        overall = self.calculate_overall_impact(results)

        return {
            **results,
            'overall': overall
        }

    def close(self):
        """接続を閉じる"""
        self.conn.close()


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='特徴量効果の検証')
    parser.add_argument('--year', type=str, default='2025', help='検証年（デフォルト: 2025）')
    args = parser.parse_args()

    db_path = str(ROOT_DIR / 'data' / 'boatrace.db')

    analyzer = FeatureImpactAnalyzer(db_path)

    try:
        # 指定年の全期間で分析
        start_date = f'{args.year}-01-01'
        end_date = f'{args.year}-12-31'

        results = analyzer.run_full_analysis(start_date, end_date)

        print("\n検証完了")

    finally:
        analyzer.close()


if __name__ == '__main__':
    main()
