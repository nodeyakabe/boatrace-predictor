"""
2024年の予想精度詳細分析（信頼度B/C/Dのみ）

以下を調査：
1. 全体の的中率・払戻金・ROI
2. 信頼度別の詳細分析（B/C/Dのみ）
3. 月別推移
4. 会場別パフォーマンス
5. ハイブリッドスコアリングの効果

注：信頼度A・Eは対象外
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
    print("2024年 予想精度詳細分析")
    print("=" * 80)
    print()

    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    predictor = RacePredictor(str(db_path))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 2024年のデータ有無を確認
    cursor.execute('''
        SELECT COUNT(*), MIN(race_date), MAX(race_date)
        FROM races
        WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'
    ''')
    count, min_date, max_date = cursor.fetchone()

    if count == 0:
        print("警告: 2024年のデータがありません")
        print("利用可能なデータ範囲を確認します...")
        cursor.execute('SELECT MIN(race_date), MAX(race_date) FROM races')
        min_available, max_available = cursor.fetchone()
        print(f"データ範囲: {min_available} ～ {max_available}")
        print()

        # 最新1年のデータを使用
        cursor.execute('''
            SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
            FROM races r
            WHERE r.race_date >= date((SELECT MAX(race_date) FROM races), '-1 year')
            ORDER BY r.race_date
        ''')
        all_races = cursor.fetchall()
        print(f"最新1年間のレース数: {len(all_races)}レース")
    else:
        print(f"2024年データ: {count}レース ({min_date} ～ {max_date})")
        # 2024年の全レースを取得
        cursor.execute('''
            SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
            FROM races r
            WHERE r.race_date >= '2024-01-01'
              AND r.race_date < '2025-01-01'
            ORDER BY r.race_date
        ''')
        all_races = cursor.fetchall()

    print(f"分析対象レース数: {len(all_races)}レース")
    print()

    # 統計データ構造
    overall_stats = {
        'total': 0,
        'hit_trifecta': 0,
        'hit_rank1': 0,
        'hit_rank2': 0,
        'hit_rank3': 0,
        'total_invested': 0,
        'total_return': 0,
        'coverage_3': 0,
        'coverage_2': 0,
        'coverage_1': 0,
        'coverage_0': 0
    }

    confidence_stats = defaultdict(lambda: {
        'total': 0,
        'hit_trifecta': 0,
        'hit_rank1': 0,
        'hit_rank2': 0,
        'hit_rank3': 0,
        'total_invested': 0,
        'total_return': 0,
        'coverage_3': 0,
        'coverage_2': 0,
        'coverage_1': 0,
        'coverage_0': 0
    })

    monthly_stats = defaultdict(lambda: {
        'total': 0,
        'hit_trifecta': 0,
        'total_invested': 0,
        'total_return': 0
    })

    venue_stats = defaultdict(lambda: {
        'total': 0,
        'hit_trifecta': 0,
        'total_invested': 0,
        'total_return': 0
    })

    # 各レースを処理
    for idx, (race_id, race_date, venue_code, race_number) in enumerate(all_races):
        if (idx + 1) % 200 == 0:
            print(f"処理中: {idx+1}/{len(all_races)}レース...")

        try:
            # 予測実行
            predictions = predictor.predict_race(race_id)

            if not predictions or len(predictions) < 6:
                continue

            # 予想上位3艇
            predicted_top3 = [p['pit_number'] for p in predictions[:3]]
            confidence = predictions[0].get('confidence', 'E')

            # 信頼度A・Eは除外
            if confidence in ['A', 'E']:
                continue

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
            is_hit_trifecta = (predicted_combo == actual_combo)
            is_hit_rank1 = (predicted_top3[0] == actual_top3[0])
            is_hit_rank2 = (predicted_top3[1] == actual_top3[1])
            is_hit_rank3 = (predicted_top3[2] == actual_top3[2])

            # カバレッジ
            coverage = sum(1 for pit in predicted_top3 if pit in actual_top3)

            # 投資・払戻
            investment = 100
            return_amount = actual_odds * investment if is_hit_trifecta else 0

            # 月の取得
            month = race_date[:7]  # YYYY-MM

            # 全体統計更新
            overall_stats['total'] += 1
            if is_hit_trifecta:
                overall_stats['hit_trifecta'] += 1
            if is_hit_rank1:
                overall_stats['hit_rank1'] += 1
            if is_hit_rank2:
                overall_stats['hit_rank2'] += 1
            if is_hit_rank3:
                overall_stats['hit_rank3'] += 1
            overall_stats['total_invested'] += investment
            overall_stats['total_return'] += return_amount

            if coverage == 3:
                overall_stats['coverage_3'] += 1
            elif coverage == 2:
                overall_stats['coverage_2'] += 1
            elif coverage == 1:
                overall_stats['coverage_1'] += 1
            else:
                overall_stats['coverage_0'] += 1

            # 信頼度別統計更新
            confidence_stats[confidence]['total'] += 1
            if is_hit_trifecta:
                confidence_stats[confidence]['hit_trifecta'] += 1
            if is_hit_rank1:
                confidence_stats[confidence]['hit_rank1'] += 1
            if is_hit_rank2:
                confidence_stats[confidence]['hit_rank2'] += 1
            if is_hit_rank3:
                confidence_stats[confidence]['hit_rank3'] += 1
            confidence_stats[confidence]['total_invested'] += investment
            confidence_stats[confidence]['total_return'] += return_amount

            if coverage == 3:
                confidence_stats[confidence]['coverage_3'] += 1
            elif coverage == 2:
                confidence_stats[confidence]['coverage_2'] += 1
            elif coverage == 1:
                confidence_stats[confidence]['coverage_1'] += 1
            else:
                confidence_stats[confidence]['coverage_0'] += 1

            # 月別統計更新
            monthly_stats[month]['total'] += 1
            if is_hit_trifecta:
                monthly_stats[month]['hit_trifecta'] += 1
            monthly_stats[month]['total_invested'] += investment
            monthly_stats[month]['total_return'] += return_amount

            # 会場別統計更新
            venue_stats[venue_code]['total'] += 1
            if is_hit_trifecta:
                venue_stats[venue_code]['hit_trifecta'] += 1
            venue_stats[venue_code]['total_invested'] += investment
            venue_stats[venue_code]['total_return'] += return_amount

        except Exception as e:
            continue

    conn.close()

    # ===============================
    # 結果表示
    # ===============================

    print("\n" + "=" * 80)
    print("【1. 全体サマリー】")
    print("=" * 80)
    print()

    if overall_stats['total'] > 0:
        print(f"評価レース数: {overall_stats['total']}レース")
        print()

        # 三連単的中率
        trifecta_rate = overall_stats['hit_trifecta'] / overall_stats['total'] * 100
        print(f"三連単的中率: {overall_stats['hit_trifecta']}/{overall_stats['total']} = {trifecta_rate:.2f}%")
        print(f"  ランダム期待値: 0.83%")
        print(f"  改善倍率: {trifecta_rate / 0.83:.1f}倍")
        print()

        # 各順位の的中率
        rank1_rate = overall_stats['hit_rank1'] / overall_stats['total'] * 100
        rank2_rate = overall_stats['hit_rank2'] / overall_stats['total'] * 100
        rank3_rate = overall_stats['hit_rank3'] / overall_stats['total'] * 100

        print("各順位の的中率:")
        print(f"  1位的中率: {overall_stats['hit_rank1']}/{overall_stats['total']} = {rank1_rate:.2f}% (ランダム: 16.67%)")
        print(f"  2位的中率: {overall_stats['hit_rank2']}/{overall_stats['total']} = {rank2_rate:.2f}% (ランダム: 20.00%)")
        print(f"  3位的中率: {overall_stats['hit_rank3']}/{overall_stats['total']} = {rank3_rate:.2f}% (ランダム: 25.00%)")
        print()

        # ROI
        roi = (overall_stats['total_return'] / overall_stats['total_invested']) * 100 if overall_stats['total_invested'] > 0 else 0
        profit = overall_stats['total_return'] - overall_stats['total_invested']

        print("ROI（回収率）:")
        print(f"  投資額: {overall_stats['total_invested']:,}円")
        print(f"  払戻額: {overall_stats['total_return']:,.0f}円")
        print(f"  ROI: {roi:.2f}%")
        print(f"  収支: {profit:+,.0f}円")
        print()

        # カバレッジ
        avg_coverage = (
            overall_stats['coverage_3'] * 3 +
            overall_stats['coverage_2'] * 2 +
            overall_stats['coverage_1'] * 1
        ) / overall_stats['total']

        print("カバレッジ（予想3艇のうち実際TOP3に含まれる数）:")
        print(f"  3艇的中: {overall_stats['coverage_3']}レース ({overall_stats['coverage_3']/overall_stats['total']*100:.1f}%)")
        print(f"  2艇的中: {overall_stats['coverage_2']}レース ({overall_stats['coverage_2']/overall_stats['total']*100:.1f}%)")
        print(f"  1艇的中: {overall_stats['coverage_1']}レース ({overall_stats['coverage_1']/overall_stats['total']*100:.1f}%)")
        print(f"  0艇的中: {overall_stats['coverage_0']}レース ({overall_stats['coverage_0']/overall_stats['total']*100:.1f}%)")
        print(f"  平均カバレッジ: {avg_coverage:.2f}艇/3艇")

    # ===============================
    # 信頼度別分析
    # ===============================

    print("\n" + "=" * 80)
    print("【2. 信頼度別詳細分析】")
    print("=" * 80)
    print()

    for confidence in sorted(confidence_stats.keys()):
        stats = confidence_stats[confidence]
        if stats['total'] == 0:
            continue

        print(f"信頼度{confidence}")
        print("-" * 80)
        print(f"レース数: {stats['total']}レース ({stats['total']/overall_stats['total']*100:.1f}%)")
        print()

        trifecta_rate = stats['hit_trifecta'] / stats['total'] * 100
        print(f"三連単的中率: {stats['hit_trifecta']}/{stats['total']} = {trifecta_rate:.2f}%")

        rank1_rate = stats['hit_rank1'] / stats['total'] * 100
        rank2_rate = stats['hit_rank2'] / stats['total'] * 100
        rank3_rate = stats['hit_rank3'] / stats['total'] * 100

        print(f"  1位的中率: {rank1_rate:.2f}%")
        print(f"  2位的中率: {rank2_rate:.2f}%")
        print(f"  3位的中率: {rank3_rate:.2f}%")

        roi = (stats['total_return'] / stats['total_invested']) * 100 if stats['total_invested'] > 0 else 0
        profit = stats['total_return'] - stats['total_invested']

        print(f"ROI: {roi:.2f}%")
        print(f"収支: {profit:+,.0f}円")

        avg_coverage = (
            stats['coverage_3'] * 3 +
            stats['coverage_2'] * 2 +
            stats['coverage_1'] * 1
        ) / stats['total']
        print(f"平均カバレッジ: {avg_coverage:.2f}艇/3艇")
        print()

    # ===============================
    # 月別推移
    # ===============================

    print("=" * 80)
    print("【3. 月別推移】")
    print("=" * 80)
    print()

    print(f"{'月':<12} {'レース数':>8} {'的中率':>8} {'ROI':>8} {'収支':>12}")
    print("-" * 80)

    for month in sorted(monthly_stats.keys()):
        stats = monthly_stats[month]
        if stats['total'] == 0:
            continue

        trifecta_rate = stats['hit_trifecta'] / stats['total'] * 100
        roi = (stats['total_return'] / stats['total_invested']) * 100 if stats['total_invested'] > 0 else 0
        profit = stats['total_return'] - stats['total_invested']

        print(f"{month:<12} {stats['total']:>8} {trifecta_rate:>7.2f}% {roi:>7.2f}% {profit:>+11,.0f}円")

    # ===============================
    # 会場別TOP10
    # ===============================

    print("\n" + "=" * 80)
    print("【4. 会場別パフォーマンス（ROI上位10会場）】")
    print("=" * 80)
    print()

    # ROIでソート
    venue_list = []
    for venue_code, stats in venue_stats.items():
        if stats['total'] >= 10:  # 最低10レース以上
            roi = (stats['total_return'] / stats['total_invested']) * 100 if stats['total_invested'] > 0 else 0
            trifecta_rate = stats['hit_trifecta'] / stats['total'] * 100
            venue_list.append((venue_code, stats, roi, trifecta_rate))

    venue_list.sort(key=lambda x: x[2], reverse=True)

    print(f"{'会場':>4} {'レース数':>8} {'的中率':>8} {'ROI':>8} {'収支':>12}")
    print("-" * 80)

    for venue_code, stats, roi, trifecta_rate in venue_list[:10]:
        profit = stats['total_return'] - stats['total_invested']
        print(f"{venue_code:>4} {stats['total']:>8} {trifecta_rate:>7.2f}% {roi:>7.2f}% {profit:>+11,.0f}円")

    # ===============================
    # まとめ
    # ===============================

    print("\n" + "=" * 80)
    print("【5. 改善状況まとめ】")
    print("=" * 80)
    print()

    if overall_stats['total'] > 0:
        trifecta_rate = overall_stats['hit_trifecta'] / overall_stats['total'] * 100
        roi = (overall_stats['total_return'] / overall_stats['total_invested']) * 100

        print("2024年の予想性能:")
        print(f"  - 三連単的中率: {trifecta_rate:.2f}% (ランダムの{trifecta_rate/0.83:.1f}倍)")
        print(f"  - 1位的中率: {rank1_rate:.2f}% (ランダムの{rank1_rate/16.67:.1f}倍)")
        print(f"  - ROI: {roi:.2f}%")
        print()

        # 信頼度Bの特記
        if 'B' in confidence_stats:
            b_stats = confidence_stats['B']
            b_trifecta_rate = b_stats['hit_trifecta'] / b_stats['total'] * 100
            b_roi = (b_stats['total_return'] / b_stats['total_invested']) * 100
            print("信頼度Bの性能（ハイブリッドスコアリング適用）:")
            print(f"  - レース数: {b_stats['total']}レース ({b_stats['total']/overall_stats['total']*100:.1f}%)")
            print(f"  - 三連単的中率: {b_trifecta_rate:.2f}%")
            print(f"  - ROI: {b_roi:.2f}%")
            if b_roi > 100:
                print(f"  - プラス収支達成！")

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == "__main__":
    main()
