"""
適用されている法則を表示
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.analysis.race_predictor import RacePredictor

def show_rules():
    print("=" * 80)
    print("適用されている法則の確認")
    print("=" * 80)

    race_id = 15151  # 最初のレース

    predictor = RacePredictor()

    # 適用される法則を取得
    applied_rules = predictor.get_applied_rules(race_id)

    print(f"\nレースID: {race_id}")
    print(f"\n適用される法則数: {len(applied_rules)}")

    if applied_rules:
        print("\n法則リスト:")
        print("  " + "-" * 76)
        for i, rule in enumerate(applied_rules, 1):
            print(f"  {i}. {rule.get('rule_name', 'N/A')}")
            print(f"     条件: {rule.get('description', 'N/A')}")
            print(f"     補正: {rule.get('adjustment', 'N/A')}")
            print()
    else:
        print("\n適用される法則がありません")


if __name__ == "__main__":
    show_rules()
