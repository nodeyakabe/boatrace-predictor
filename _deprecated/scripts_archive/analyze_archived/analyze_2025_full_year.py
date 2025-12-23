"""
2025年全データでの予想精度分析（信頼度B/C/D）

2025年1月1日～12月9日までの全レースで分析
信頼度A・Eは除外
"""

import sys
import warnings
from pathlib import Path
import sqlite3
from collections import defaultdict
from datetime import datetime

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.race_predictor import RacePredictor


def main():
    print("=" * 80)
    print("2025年全データ予想精度分析（信頼度B/C/D）")
    print("=" * 80)
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    predictor = RacePredictor(str(db_path))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 2025年の全レースを取得（信頼度判定のため予測が必要なレースのみ）
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01'
          AND r.race_date < '2026-01-01'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    all_races = cursor.fetchall()

    print(f"2025年総レース数: {len(all_races):,}レース")
    print()

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

    # 月別統計
    monthly_stats = defaultdict(lambda: {
        'total': 0,
        'hit': 0,
        'total_invested': 0,
        'total_return': 0
    })

    print("分析開始...")
    print()

    processed = 0
    for idx, (race_id, race_date, venue_code, race_number) in enumerate(all_races):
        if (idx + 1) % 100 == 0:
            print(f"処理中: {idx+1:,}/{len(all_races):,}レース... ({processed:,}レース分析完了)", flush=True)

        try:
            # 予測実行
            predictions = predictor.predict_race(race_id)

            if not predictions or len(predictions) < 6:
                continue

            # 信頼度を取得
            confidence = predictions[0].get('confidence', 'E')

            # 信頼度A・Eは除外
            if confidence in ['A', 'E']:
                continue

            # 予想上位3艇
            predicted_top3 = [p['pit_number'] for p in predictions[:3]]

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

            # 月を取得
            month = race_date[:7]  # "2025-01" 形式

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

            # 月別統計更新
            monthly_stats[month]['total'] += 1
            if is_hit:
                monthly_stats[month]['hit'] += 1
            monthly_stats[month]['total_invested'] += investment
            monthly_stats[month]['total_return'] += return_amount

            processed += 1

        except Exception:
            continue

    conn.close()

    print(f"\n処理完了: {processed:,}レース分析完了")
    print()

    # 結果表示
    print("=" * 80)
    print("全体評価結果（信頼度B/C/D）")
    print("=" * 80)
    print()

    if overall_stats['total'] > 0:
        print(f"分析レース数: {overall_stats['total']:,}レース")
        print()

        # 三連単的中率
        hit_rate = overall_stats['hit'] / overall_stats['total'] * 100
        print("【三連単的中率】")
        print(f"  的中: {overall_stats['hit']:,}/{overall_stats['total']:,} = {hit_rate:.2f}%")
        print(f"  ランダム期待値: 0.83%")
        print(f"  改善倍率: {hit_rate / 0.83:.1f}倍")
        print()

        # 各順位の的中率
        print("【各順位の的中率】")
        rank1_rate = overall_stats['rank1_correct'] / overall_stats['total'] * 100
        rank2_rate = overall_stats['rank2_correct'] / overall_stats['total'] * 100
        rank3_rate = overall_stats['rank3_correct'] / overall_stats['total'] * 100

        print(f"  1位的中率: {overall_stats['rank1_correct']:,}/{overall_stats['total']:,} = {rank1_rate:.2f}% (ランダム: 16.67%)")
        print(f"  2位的中率: {overall_stats['rank2_correct']:,}/{overall_stats['total']:,} = {rank2_rate:.2f}% (ランダム: 20.00%)")
        print(f"  3位的中率: {overall_stats['rank3_correct']:,}/{overall_stats['total']:,} = {rank3_rate:.2f}% (ランダム: 25.00%)")
        print()

        # ROI
        roi = (overall_stats['total_return'] / overall_stats['total_invested']) * 100 if overall_stats['total_invested'] > 0 else 0
        print("【ROI（回収率）】")
        print(f"  投資額: {overall_stats['total_invested']:,}円")
        print(f"  払戻額: {overall_stats['total_return']:,.0f}円")
        print(f"  ROI: {roi:.2f}%")
        profit = overall_stats['total_return'] - overall_stats['total_invested']
        print(f"  収支: {profit:+,.0f}円")
        print()

    # 信頼度別結果
    print("=" * 80)
    print("信頼度別評価結果")
    print("=" * 80)
    print()

    for confidence in sorted(confidence_stats.keys()):
        stats = confidence_stats[confidence]
        if stats['total'] == 0:
            continue

        print(f"【信頼度{confidence}】")
        print(f"  レース数: {stats['total']:,}レース")

        hit_rate = stats['hit'] / stats['total'] * 100
        print(f"  三連単的中率: {stats['hit']:,}/{stats['total']:,} = {hit_rate:.2f}%")

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
        print()

    # 月別結果
    print("=" * 80)
    print("月別評価結果")
    print("=" * 80)
    print()

    for month in sorted(monthly_stats.keys()):
        stats = monthly_stats[month]
        if stats['total'] == 0:
            continue

        hit_rate = stats['hit'] / stats['total'] * 100 if stats['total'] > 0 else 0
        roi = (stats['total_return'] / stats['total_invested']) * 100 if stats['total_invested'] > 0 else 0
        profit = stats['total_return'] - stats['total_invested']

        print(f"{month}: {stats['total']:,}R | 的中率 {hit_rate:.2f}% | ROI {roi:.2f}% | 収支 {profit:+,.0f}円")

    print()
    print("=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
