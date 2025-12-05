"""
スコア要素の詳細分析スクリプト

各スコア要素（コース、選手、モーター、決まり手、グレード）の
実測値と分布を分析し、正規化の改善点を特定する
"""

import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent))

from src.analysis.race_predictor import RacePredictor
from src.analysis.statistics_calculator import StatisticsCalculator
from src.analysis.racer_analyzer import RacerAnalyzer
from src.analysis.motor_analyzer import MotorAnalyzer


def analyze_score_components():
    """各スコア要素の分布を分析"""

    db_path = "data/boatrace.db"
    predictor = RacePredictor(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 最近の予測データを取得
    cursor.execute("""
        SELECT
            rp.race_id,
            rp.pit_number,
            rp.course_score,
            rp.racer_score,
            rp.motor_score,
            rp.kimarite_score,
            rp.grade_score,
            rp.total_score,
            rp.confidence,
            r.venue_code,
            r.race_date
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date >= date('now', '-30 days')
        ORDER BY r.race_date DESC
    """)

    predictions = cursor.fetchall()

    if not predictions:
        print("予測データがありません。先に予測を生成してください。")
        return

    print("=" * 80)
    print("スコア要素の詳細分析")
    print("=" * 80)
    print(f"分析対象: {len(predictions)}件の予測データ")

    # 各スコア要素の統計
    score_types = ['course_score', 'racer_score', 'motor_score', 'kimarite_score', 'grade_score', 'total_score']

    # 重み設定（理論上の最大値）
    max_scores = {
        'course_score': 35.0,
        'racer_score': 35.0,
        'motor_score': 20.0,
        'kimarite_score': 5.0,
        'grade_score': 5.0,
        'total_score': 100.0
    }

    print("\n" + "=" * 80)
    print("【各スコア要素の分布】")
    print("=" * 80)

    for score_type in score_types:
        scores = [p[score_type] for p in predictions if p[score_type] is not None]

        if not scores:
            print(f"\n{score_type}: データなし")
            continue

        avg = statistics.mean(scores)
        med = statistics.median(scores)
        std = statistics.stdev(scores) if len(scores) > 1 else 0
        min_val = min(scores)
        max_val = max(scores)
        max_possible = max_scores[score_type]
        utilization = (avg / max_possible) * 100  # 平均スコアが理論最大値の何%か

        print(f"\n【{score_type}】(理論最大: {max_possible}点)")
        print(f"  平均: {avg:6.2f}点  (利用率: {utilization:5.1f}%)")
        print(f"  中央: {med:6.2f}点")
        print(f"  標準: {std:6.2f}")
        print(f"  範囲: {min_val:6.2f} ~ {max_val:6.2f}")

        # ヒストグラム（簡易版）
        bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        if max_possible <= 35:
            bins = [0, 5, 10, 15, 20, 25, 30, 35]
        elif max_possible <= 20:
            bins = [0, 3, 6, 9, 12, 15, 18, 20]
        elif max_possible <= 5:
            bins = [0, 1, 2, 3, 4, 5]

        hist = defaultdict(int)
        for s in scores:
            for i in range(len(bins) - 1):
                if bins[i] <= s < bins[i+1]:
                    hist[f"{bins[i]}-{bins[i+1]}"] = hist.get(f"{bins[i]}-{bins[i+1]}", 0) + 1
                    break
            else:
                hist[f"{bins[-2]}-{bins[-1]}"] = hist.get(f"{bins[-2]}-{bins[-1]}", 0) + 1

        print("  分布:")
        for i in range(len(bins) - 1):
            key = f"{bins[i]}-{bins[i+1]}"
            count = hist.get(key, 0)
            pct = count / len(scores) * 100
            bar = "#" * int(pct / 2)
            print(f"    {key:>8s}: {count:5d} ({pct:5.1f}%) {bar}")

    # コース別分析
    print("\n" + "=" * 80)
    print("【コース別スコア分析】")
    print("=" * 80)

    course_scores = defaultdict(list)
    for p in predictions:
        if p['course_score'] is not None:
            course_scores[p['pit_number']].append(p['course_score'])

    print("\nコース | 件数  | 平均    | 最大    | 最小    | 利用率")
    print("-" * 60)
    for course in sorted(course_scores.keys()):
        scores = course_scores[course]
        avg = statistics.mean(scores)
        max_val = max(scores)
        min_val = min(scores)
        utilization = (avg / 35.0) * 100
        print(f"  {course}   | {len(scores):5d} | {avg:6.2f} | {max_val:6.2f} | {min_val:6.2f} | {utilization:5.1f}%")

    # 会場別分析
    print("\n" + "=" * 80)
    print("【会場別total_score平均】")
    print("=" * 80)

    venue_scores = defaultdict(list)
    for p in predictions:
        if p['total_score'] is not None:
            venue_scores[p['venue_code']].append(p['total_score'])

    print("\n会場 | 件数  | 平均    | 最大    | 最小")
    print("-" * 50)
    for venue in sorted(venue_scores.keys()):
        scores = venue_scores[venue]
        avg = statistics.mean(scores)
        max_val = max(scores)
        min_val = min(scores)
        print(f" {venue}  | {len(scores):5d} | {avg:6.2f} | {max_val:6.2f} | {min_val:6.2f}")

    # 信頼度別スコア分析
    print("\n" + "=" * 80)
    print("【信頼度別の詳細スコア】")
    print("=" * 80)

    conf_details = defaultdict(lambda: defaultdict(list))
    for p in predictions:
        conf = p['confidence']
        for score_type in score_types:
            if p[score_type] is not None:
                conf_details[conf][score_type].append(p[score_type])

    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf not in conf_details:
            continue
        print(f"\n【信頼度 {conf}】")
        print(f"  件数: {len(conf_details[conf]['total_score'])}")
        for score_type in ['course_score', 'racer_score', 'motor_score', 'kimarite_score', 'grade_score']:
            scores = conf_details[conf][score_type]
            if scores:
                avg = statistics.mean(scores)
                max_possible = max_scores[score_type]
                utilization = (avg / max_possible) * 100
                print(f"  {score_type:15s}: 平均 {avg:5.2f} / {max_possible} ({utilization:5.1f}%)")

    # 問題点のサマリー
    print("\n" + "=" * 80)
    print("【問題点のサマリー】")
    print("=" * 80)

    all_course = [p['course_score'] for p in predictions if p['course_score'] is not None]
    all_racer = [p['racer_score'] for p in predictions if p['racer_score'] is not None]
    all_motor = [p['motor_score'] for p in predictions if p['motor_score'] is not None]
    all_total = [p['total_score'] for p in predictions if p['total_score'] is not None]

    print(f"""
1. コーススコア (重み: 35点)
   - 平均: {statistics.mean(all_course):.2f}点 (利用率: {statistics.mean(all_course)/35*100:.1f}%)
   - 問題: 勝率をそのまま使用しているため、1コース(55%)でも19点程度
   - 改善案: 会場内での相対評価、または全国平均からの偏差で正規化

2. 選手スコア (重み: 35点)
   - 平均: {statistics.mean(all_racer):.2f}点 (利用率: {statistics.mean(all_racer)/35*100:.1f}%)
   - 問題: 選手の勝率がそのままスコアに反映
   - 改善案: レース内の6選手を相対評価（最上位=満点、最下位=基礎点）

3. モータースコア (重み: 20点)
   - 平均: {statistics.mean(all_motor):.2f}点 (利用率: {statistics.mean(all_motor)/20*100:.1f}%)
   - 問題: モーター勝率がそのままスコアに反映
   - 改善案: 同一会場内のモーターで相対評価（偏差値的計算）

4. 総合スコア (最大: 100点)
   - 平均: {statistics.mean(all_total):.2f}点
   - 45点未満（E判定）: {sum(1 for s in all_total if s < 45) / len(all_total) * 100:.1f}%
   - 目標: 平均60点以上、E判定を20%以下に
""")

    conn.close()


def analyze_course_score_detail():
    """コーススコア計算の詳細分析"""

    db_path = "data/boatrace.db"
    stats_calc = StatisticsCalculator(db_path)

    print("\n" + "=" * 80)
    print("【コーススコア計算の詳細分析】")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 各会場のコース別勝率を取得
    cursor.execute("SELECT DISTINCT venue_code FROM races ORDER BY venue_code")
    venues = [row[0] for row in cursor.fetchall()]

    print("\n会場別コース1勝率:")
    print("-" * 40)

    venue_course1_rates = {}
    for venue in venues[:10]:  # 最初の10会場
        course_stats = stats_calc.calculate_course_stats(venue)
        if 1 in course_stats:
            win_rate = course_stats[1]['win_rate']
            venue_course1_rates[venue] = win_rate
            current_score = win_rate * 35  # 現在の計算方法
            print(f"会場{venue}: 1コース勝率 {win_rate:.1%} → 現在スコア: {current_score:.1f}点")

    # 正規化案の比較
    if venue_course1_rates:
        avg_rate = statistics.mean(venue_course1_rates.values())
        max_rate = max(venue_course1_rates.values())
        min_rate = min(venue_course1_rates.values())

        print(f"\n全会場の1コース勝率: 平均{avg_rate:.1%}, 最大{max_rate:.1%}, 最小{min_rate:.1%}")
        print("\n【正規化案の比較】")

        for venue, rate in list(venue_course1_rates.items())[:5]:
            current = rate * 35
            # 案1: 最大勝率を基準に正規化
            normalized1 = (rate / max_rate) * 35
            # 案2: 平均からの偏差
            normalized2 = 35 * (0.5 + (rate - avg_rate) / (max_rate - min_rate))

            print(f"会場{venue}: 現在{current:.1f}点 → 案1: {normalized1:.1f}点, 案2: {normalized2:.1f}点")

    conn.close()


if __name__ == "__main__":
    analyze_score_components()
    print("\n")
    analyze_course_score_detail()
