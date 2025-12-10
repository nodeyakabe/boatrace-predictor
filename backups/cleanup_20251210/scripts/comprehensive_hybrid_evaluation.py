"""
ハイブリッドスコアリングの包括的評価

信頼度B/C/D/E全体で以下を評価：
1. 三連単的中率
2. 各順位の的中率
3. ROI（回収率）
4. 信頼度別の性能
"""

import sys
from pathlib import Path
import sqlite3
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.race_predictor import RacePredictor


def main():
    print("=" * 80)
    print("ハイブリッドスコアリングの包括的評価")
    print("=" * 80)

    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    predictor = RacePredictor(str(db_path))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 2024-2025年の全レース（最大200レース）を取得
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        WHERE r.race_date >= '2024-01-01'
          AND r.race_date < '2025-01-01'
        ORDER BY r.race_date
        LIMIT 200
    ''')
    races = cursor.fetchall()

    print(f"\n評価レース数: {len(races)}レース\n")

    # 全体統計
    overall_stats = {
        'total': 0,
        'hit': 0,
        'rank1_correct': 0,
        'rank2_correct': 0,
        'rank3_correct': 0,
        'total_invested': 0,
        'total_return': 0
    }

    # 信頼度別統計
    confidence_stats = defaultdict(lambda: {
        'total': 0,
        'hit': 0,
        'rank1_correct': 0,
        'rank2_correct': 0,
        'rank3_correct': 0,
        'total_invested': 0,
        'total_return': 0
    })

    for idx, (race_id, race_date, venue_code, race_number) in enumerate(races):
        if (idx + 1) % 50 == 0:
            print(f"処理中: {idx+1}/{len(races)}レース...")

        try:
            # 予測実行
            predictions = predictor.predict_race(race_id)

            if not predictions or len(predictions) < 6:
                continue

            # 予想上位3艇
            predicted_top3 = [p['pit_number'] for p in predictions[:3]]

            # 信頼度を取得（トップ予想の信頼度）
            confidence = predictions[0].get('confidence', 'E')

            # 実際の結果取得
            cursor.execute('''
                SELECT pit_number, CAST(rank AS INTEGER) as rank_int
                FROM results
                WHERE race_id = ? AND is_invalid = 0 AND CAST(rank AS INTEGER) <= 3
                ORDER BY rank_int
            ''', (race_id,))
            actual_results = cursor.fetchall()

            if len(actual_results) < 3:
                continue

            actual_top3 = [row[0] for row in actual_results]
            actual_combo = f"{actual_top3[0]}-{actual_top3[1]}-{actual_top3[2]}"
            predicted_combo = f"{predicted_top3[0]}-{predicted_top3[1]}-{predicted_top3[2]}"

            # オッズ取得
            cursor.execute('''
                SELECT odds FROM trifecta_odds
                WHERE race_id = ? AND combination = ?
            ''', (race_id, actual_combo))
            odds_row = cursor.fetchone()
            actual_odds = odds_row[0] if odds_row else 0

            # 的中判定
            is_hit = (predicted_combo == actual_combo)
            rank1_correct = (predicted_top3[0] == actual_top3[0])
            rank2_correct = (predicted_top3[1] == actual_top3[1])
            rank3_correct = (predicted_top3[2] == actual_top3[2])

            # 投資額（1レースあたり100円）
            investment = 100

            # 払戻額
            return_amount = actual_odds * investment if is_hit else 0

            # 全体統計更新
            overall_stats['total'] += 1
            if is_hit:
                overall_stats['hit'] += 1
            if rank1_correct:
                overall_stats['rank1_correct'] += 1
            if rank2_correct:
                overall_stats['rank2_correct'] += 1
            if rank3_correct:
                overall_stats['rank3_correct'] += 1
            overall_stats['total_invested'] += investment
            overall_stats['total_return'] += return_amount

            # 信頼度別統計更新
            confidence_stats[confidence]['total'] += 1
            if is_hit:
                confidence_stats[confidence]['hit'] += 1
            if rank1_correct:
                confidence_stats[confidence]['rank1_correct'] += 1
            if rank2_correct:
                confidence_stats[confidence]['rank2_correct'] += 1
            if rank3_correct:
                confidence_stats[confidence]['rank3_correct'] += 1
            confidence_stats[confidence]['total_invested'] += investment
            confidence_stats[confidence]['total_return'] += return_amount

        except Exception as e:
            continue

    conn.close()

    # 結果表示
    print("\n" + "=" * 80)
    print("全体評価結果")
    print("=" * 80)

    if overall_stats['total'] > 0:
        print(f"\n評価レース数: {overall_stats['total']}レース")

        # 三連単的中率
        hit_rate = overall_stats['hit'] / overall_stats['total'] * 100
        print(f"\n【三連単的中率】")
        print(f"  的中: {overall_stats['hit']}/{overall_stats['total']} = {hit_rate:.2f}%")
        print(f"  ランダム期待値: 0.83%")
        print(f"  改善倍率: {hit_rate / 0.83:.1f}倍")

        # 各順位の的中率
        print(f"\n【各順位の的中率】")
        rank1_rate = overall_stats['rank1_correct'] / overall_stats['total'] * 100
        rank2_rate = overall_stats['rank2_correct'] / overall_stats['total'] * 100
        rank3_rate = overall_stats['rank3_correct'] / overall_stats['total'] * 100

        print(f"  1位的中率: {overall_stats['rank1_correct']}/{overall_stats['total']} = {rank1_rate:.2f}% (ランダム: 16.67%)")
        print(f"  2位的中率: {overall_stats['rank2_correct']}/{overall_stats['total']} = {rank2_rate:.2f}% (ランダム: 20.00%)")
        print(f"  3位的中率: {overall_stats['rank3_correct']}/{overall_stats['total']} = {rank3_rate:.2f}% (ランダム: 25.00%)")

        # ROI
        roi = (overall_stats['total_return'] / overall_stats['total_invested']) * 100 if overall_stats['total_invested'] > 0 else 0
        print(f"\n【ROI（回収率）】")
        print(f"  投資額: {overall_stats['total_invested']:,}円")
        print(f"  払戻額: {overall_stats['total_return']:,.0f}円")
        print(f"  ROI: {roi:.2f}%")
        profit = overall_stats['total_return'] - overall_stats['total_invested']
        print(f"  収支: {profit:+,.0f}円")

    # 信頼度別結果
    print("\n" + "=" * 80)
    print("信頼度別評価結果")
    print("=" * 80)

    for confidence in sorted(confidence_stats.keys()):
        stats = confidence_stats[confidence]
        if stats['total'] == 0:
            continue

        print(f"\n【信頼度{confidence}】")
        print(f"  レース数: {stats['total']}レース")

        hit_rate = stats['hit'] / stats['total'] * 100
        print(f"  三連単的中率: {stats['hit']}/{stats['total']} = {hit_rate:.2f}%")

        rank1_rate = stats['rank1_correct'] / stats['total'] * 100
        rank2_rate = stats['rank2_correct'] / stats['total'] * 100
        rank3_rate = stats['rank3_correct'] / stats['total'] * 100

        print(f"  1位的中率: {rank1_rate:.2f}%")
        print(f"  2位的中率: {rank2_rate:.2f}%")
        print(f"  3位的中率: {rank3_rate:.2f}%")

        roi = (stats['total_return'] / stats['total_invested']) * 100 if stats['total_invested'] > 0 else 0
        print(f"  ROI: {roi:.2f}%")
        profit = stats['total_return'] - stats['total_invested']
        print(f"  収支: {profit:+,.0f}円")

    print("\n" + "=" * 80)
    print("評価完了")
    print("=" * 80)

    # まとめ
    if overall_stats['total'] > 0:
        print("\n【総評】")
        hit_rate = overall_stats['hit'] / overall_stats['total'] * 100
        roi = (overall_stats['total_return'] / overall_stats['total_invested']) * 100

        print(f"ハイブリッドスコアリングにより：")
        print(f"  - 三連単的中率: {hit_rate:.2f}%（ランダムの{hit_rate/0.83:.1f}倍）")
        print(f"  - ROI: {roi:.2f}%")

        if roi > 100:
            print(f"  - プラス収支達成！ (+{roi-100:.2f}%)")
        else:
            print(f"  - マイナス収支 ({roi-100:.2f}%)")

        print(f"\n参考：統合前のスコアリング")
        print(f"  - 信頼度B三連単的中率: 4.12% → {hit_rate:.2f}%")
        print(f"  - 改善: +{hit_rate - 4.12:.2f}pt")


if __name__ == "__main__":
    main()
