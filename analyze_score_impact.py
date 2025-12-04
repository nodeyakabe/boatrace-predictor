"""
スコアの影響範囲を分析

PRE_SCOREとBEFORE_SCOREの実際の値と影響を確認
"""

import sqlite3
from src.analysis.race_predictor import RacePredictor

def main():
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 最新30レース取得
    cursor.execute("""
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        JOIN results res ON r.id = res.race_id
        WHERE rd.exhibition_course IS NOT NULL
        AND res.rank IS NOT NULL
        AND res.is_invalid = 0
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT 30
    """)

    test_races = cursor.fetchall()
    predictor = RacePredictor(db_path='data/boatrace.db')

    print("=" * 80)
    print("スコア影響分析")
    print("=" * 80)
    print()

    total_pre_diff = 0
    total_before_range = 0
    count = 0

    for race_id, date, venue, race_no in test_races[:10]:  # 最初の10レースのみ詳細表示
        predictions = predictor.predict_race(race_id)
        if not predictions or len(predictions) < 2:
            continue

        # PRE_SCOREの順位
        pre_sorted = sorted(predictions, key=lambda x: x.get('pre_score', 0), reverse=True)

        # 1位と2位のPRE_SCORE差
        pre_1st = pre_sorted[0].get('pre_score', 0)
        pre_2nd = pre_sorted[1].get('pre_score', 0)
        pre_diff = pre_1st - pre_2nd

        # BEFORE_SCOREの範囲
        before_scores = [p.get('beforeinfo_score', 0) for p in predictions]
        before_max = max(before_scores)
        before_min = min(before_scores)
        before_range = before_max - before_min

        # 重み取得
        pre_w = predictions[0].get('pre_weight', 0.6)
        before_w = predictions[0].get('before_weight', 0.4)

        # 実際の影響
        before_impact = before_range * before_w

        print(f"【{date} {venue} {race_no}R (ID: {race_id})】")
        print(f"  使用重み: PRE {pre_w:.0%} / BEFORE {before_w:.0%}")
        print(f"  PRE 1位-2位差: {pre_diff:.2f}点")
        print(f"  BEFORE範囲: {before_min:.2f} 〜 {before_max:.2f} (差{before_range:.2f}点)")
        print(f"  BEFORE最大影響: {before_impact:.2f}点 (重み適用後)")

        if before_impact < pre_diff:
            print(f"  → BEFOREでは覆せない (影響{before_impact:.2f} < 差{pre_diff:.2f})")
        else:
            print(f"  → BEFOREで逆転可能！ (影響{before_impact:.2f} >= 差{pre_diff:.2f})")

        print()

        total_pre_diff += pre_diff
        total_before_range += before_range
        count += 1

    print("=" * 80)
    print("統計サマリー")
    print("=" * 80)

    if count > 0:
        avg_pre_diff = total_pre_diff / count
        avg_before_range = total_before_range / count

        print(f"PRE 1位-2位差の平均: {avg_pre_diff:.2f}点")
        print(f"BEFORE範囲の平均: {avg_before_range:.2f}点")
        print()

        # 現在の重みでの影響
        print("【重み別の影響力】")
        for pre_w in [0.75, 0.70, 0.65, 0.60, 0.55, 0.50]:
            before_w = 1.0 - pre_w
            impact = avg_before_range * before_w
            print(f"  PRE {pre_w:.0%} / BEFORE {before_w:.0%}: BEFORE影響{impact:.2f}点", end="")
            if impact >= avg_pre_diff:
                print(" → 逆転可能！")
            else:
                print(f" (不足{avg_pre_diff - impact:.2f}点)")

    print()
    print("=" * 80)

    conn.close()

if __name__ == "__main__":
    main()
