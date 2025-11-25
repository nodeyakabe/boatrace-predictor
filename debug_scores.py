"""
スコアの詳細を確認するデバッグスクリプト
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.analysis.race_predictor import RacePredictor

def debug_scores():
    print("=" * 80)
    print("スコア詳細デバッグ")
    print("=" * 80)

    race_id = 15151  # 最初のレース

    predictor = RacePredictor()

    # 内部データを確認するため、予測処理を手動で実行
    import sqlite3
    from config.settings import DATABASE_PATH

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT venue_code, race_grade FROM races WHERE id = ?", (race_id,))
    race_info = cursor.fetchone()
    conn.close()

    venue_code = race_info['venue_code']
    race_grade = race_info['race_grade'] if race_info['race_grade'] else '一般'

    print(f"\nレース情報:")
    print(f"  race_id: {race_id}")
    print(f"  venue_code: {venue_code}")
    print(f"  race_grade: {race_grade}")

    print(f"\n重み設定:")
    for key, value in predictor.weights.items():
        print(f"  {key}: {value}")

    # 選手・モーター分析
    racer_analyses = predictor.racer_analyzer.analyze_race_entries(race_id)
    motor_analyses = predictor.motor_analyzer.analyze_race_motors(race_id)

    print(f"\n" + "=" * 80)
    print("各艇のスコア内訳")
    print("=" * 80)

    for racer_analysis, motor_analysis in zip(racer_analyses, motor_analyses):
        pit_number = racer_analysis['pit_number']
        racer_name = racer_analysis['racer_name']
        course = pit_number

        # コーススコア
        course_score = predictor.calculate_course_score(venue_code, course)

        # 選手スコア
        racer_score_raw = predictor.racer_analyzer.calculate_racer_score(racer_analysis)
        racer_score = racer_score_raw * (predictor.weights['racer_weight'] / 40.0)

        # モータースコア
        motor_score_raw = predictor.motor_analyzer.calculate_motor_score(motor_analysis)
        motor_score = motor_score_raw * (predictor.weights['motor_weight'] / 20.0)

        # 決まり手適性
        kimarite_result = predictor.kimarite_scorer.calculate_kimarite_affinity_score(
            racer_analysis['racer_number'],
            venue_code,
            course,
            days=180,
            max_score=predictor.weights['kimarite_weight']
        )
        kimarite_score = kimarite_result['score']

        # グレード適性
        grade_result = predictor.grade_scorer.calculate_grade_affinity_score(
            racer_analysis['racer_number'],
            race_grade,
            days=365,
            max_score=predictor.weights['grade_weight']
        )
        grade_score = grade_result['score']

        # 総合スコア
        raw_total = course_score + racer_score + motor_score + kimarite_score + grade_score
        max_possible = sum(predictor.weights.values())
        total_score = (raw_total / max_possible) * 100.0

        print(f"\n{pit_number}号艇 - {racer_name}")
        print(f"  コース(C={course}): {course_score:5.2f} (raw)")
        print(f"  選手        : {racer_score:5.2f} (raw={racer_score_raw:5.2f})")
        print(f"  モーター    : {motor_score:5.2f} (raw={motor_score_raw:5.2f})")
        print(f"  決まり手    : {kimarite_score:5.2f}")
        print(f"  グレード    : {grade_score:5.2f}")
        print(f"  合計(raw)   : {raw_total:5.2f}")
        print(f"  合計(0-100) : {total_score:5.2f}")


if __name__ == "__main__":
    debug_scores()
