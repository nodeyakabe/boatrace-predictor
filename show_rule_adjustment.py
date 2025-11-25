"""
法則補正の詳細を表示
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.analysis.race_predictor import RacePredictor

def show_adjustment():
    print("=" * 80)
    print("法則補正の詳細")
    print("=" * 80)

    race_id = 15151

    predictor = RacePredictor()
    predictions = predictor.predict_race(race_id)

    if not predictions:
        print("予測失敗")
        return

    print(f"\nレースID: {race_id}")
    print("\n補正の影響:")
    print("  枠 | 選手名 | 最終スコア | 補正値 | (補正前)")
    print("  " + "-" * 60)

    for pred in sorted(predictions, key=lambda x: x['rank_prediction']):
        pit = pred['pit_number']
        name = pred['racer_name']
        final_score = pred['total_score']
        adjustment = pred.get('rule_adjustment', 0)
        original = final_score - adjustment

        print(f"  {pit}号艇 | {name:8s} | {final_score:5.1f} | {adjustment:+5.1f} | ({original:5.1f})")


if __name__ == "__main__":
    show_adjustment()
