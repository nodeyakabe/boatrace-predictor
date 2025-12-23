# -*- coding: utf-8 -*-
"""
2025年全期間 正確なバックテスト

- 予測タイプ: before（直前情報あり）
- 的中判定: 3連単完全一致（予測1-2-3着 = 実際1-2-3着）
- 払戻金: payoutsテーブルのamount（100円あたりの払戻金額）
- 対象: bet_target_evaluator.pyの条件（信頼度C/D）
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def main():
    """メイン処理"""
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()

    print("=" * 100)
    print("2025年全期間 正確なバックテスト")
    print("=" * 100)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"予測タイプ: before（直前情報あり）")
    print(f"的中判定: 3連単完全一致（予測1-2-3着 = 実際1-2-3着）")
    print(f"払戻金: payoutsテーブルのamount（100円あたりの払戻金額）")
    print(f"対象: bet_target_evaluator.py の条件（信頼度C, D）")
    print()

    # 2025年全期間のレースを取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    stats = {
        'total_races': 0,
        'target': 0,
        'hit': 0,
        'bet': 0,
        'payout': 0,
        'by_confidence': {
            'C': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
            'D': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
        },
        'by_tier': {
            'Tier1': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
            'Tier2': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
            'Tier3': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
        },
        'by_month': {},
        'by_condition': defaultdict(lambda: {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0})
    }

    hit_details = []  # 的中レースの詳細

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0
        race_date = race['race_date']
        month = race_date[:7]  # YYYY-MM

        if month not in stats['by_month']:
            stats['by_month'][month] = {
                'target': 0, 'hit': 0, 'bet': 0, 'payout': 0
            }

        stats['total_races'] += 1

        # 1コース級別を取得
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # 予測情報を取得（直前情報 = before）★重要★
        cursor.execute('''
            SELECT pit_number, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']

        # 信頼度A, Bは除外
        if confidence in ['A', 'B']:
            continue

        # 予測トップ3
        top3 = [p['pit_number'] for p in preds[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

        # オッズ取得
        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                       (race_id, combo))
        odds_row = cursor.fetchone()

        if not odds_row:
            continue

        odds = odds_row['odds']

        # bet_target_evaluator.pyで購入判定
        result = evaluator.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=combo,
            new_combo=combo,
            old_odds=odds,
            new_odds=odds,
            has_beforeinfo=True,
            venue_code=venue_code
        )

        # 購入対象かチェック
        if result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            continue

        # 購入対象
        bet_amount = result.bet_amount
        stats['target'] += 1
        stats['bet'] += bet_amount
        stats['by_confidence'][confidence]['target'] += 1
        stats['by_confidence'][confidence]['bet'] += bet_amount
        stats['by_month'][month]['target'] += 1
        stats['by_month'][month]['bet'] += bet_amount

        # Tier判定（descriptionから）
        tier = 'Tier1'
        if 'Tier1' in result.reason or result.odds_range in ['60-100倍']:
            tier = 'Tier1'
        elif 'Tier2' in result.reason or result.odds_range in ['40-60倍', '80-120倍']:
            tier = 'Tier2'
        elif 'Tier3' in result.reason or result.odds_range in ['30-100倍']:
            tier = 'Tier3'

        stats['by_tier'][tier]['target'] += 1
        stats['by_tier'][tier]['bet'] += bet_amount

        # 条件別集計
        condition_key = f"{confidence} x {c1_rank} x {result.odds_range}"
        stats['by_condition'][condition_key]['target'] += 1
        stats['by_condition'][condition_key]['bet'] += bet_amount

        # 実際の結果を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

            # ★重要★ 3連単完全一致判定
            if combo == actual_combo:
                # 的中！払戻金を取得
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    # 払戻金は100円あたりなので、実際の賭け金に応じて計算
                    actual_payout = (bet_amount / 100) * payout_row['amount']
                    stats['hit'] += 1
                    stats['payout'] += actual_payout
                    stats['by_confidence'][confidence]['hit'] += 1
                    stats['by_confidence'][confidence]['payout'] += actual_payout
                    stats['by_month'][month]['hit'] += 1
                    stats['by_month'][month]['payout'] += actual_payout
                    stats['by_tier'][tier]['hit'] += 1
                    stats['by_tier'][tier]['payout'] += actual_payout
                    stats['by_condition'][condition_key]['hit'] += 1
                    stats['by_condition'][condition_key]['payout'] += actual_payout

                    # 的中詳細を保存
                    hit_details.append({
                        'race_id': race_id,
                        'race_date': race_date,
                        'combo': combo,
                        'odds': odds,
                        'payout': actual_payout,
                        'confidence': confidence,
                        'c1_rank': c1_rank,
                        'condition': condition_key
                    })

    conn.close()

    # 結果表示
    print(f"データ取得: {len(races):,}レース（2025年全期間）")
    print()
    print("=" * 100)
    print("全体サマリー")
    print("=" * 100)
    print(f"総レース数: {stats['total_races']:,}")
    print()

    # 全体結果
    purchase_count = stats['target']
    hit_count = stats['hit']
    hit_rate = (hit_count / purchase_count * 100) if purchase_count > 0 else 0
    total_investment = stats['bet']
    total_return = stats['payout']
    roi = (total_return / total_investment * 100) if total_investment > 0 else 0
    profit = total_return - total_investment

    print("[3連単 全体]")
    print(f"  購入: {purchase_count}レース")
    print(f"  的中: {hit_count}レース（的中率{hit_rate:.2f}%）")
    print(f"  投資額: {total_investment:,.0f}円")
    print(f"  払戻: {total_return:,.0f}円")
    print(f"  収支: {profit:+,.0f}円")
    print(f"  ROI: {roi:.1f}%")
    print()

    # 信頼度別
    print("=" * 100)
    print("信頼度別内訳")
    print("=" * 100)
    for conf in ['C', 'D']:
        cstats = stats['by_confidence'][conf]
        if cstats['target'] > 0:
            chit_rate = cstats['hit'] / cstats['target'] * 100
            croi = cstats['payout'] / cstats['bet'] * 100 if cstats['bet'] > 0 else 0
            cprofit = cstats['payout'] - cstats['bet']
            print(f"信頼度{conf}:")
            print(f"  購入{cstats['target']}件, 的中{cstats['hit']}件, 的中率{chit_rate:.2f}%")
            print(f"  投資額{cstats['bet']:,.0f}円, 払戻{cstats['payout']:,.0f}円")
            print(f"  収支{cprofit:+,.0f}円, ROI {croi:.1f}%")
            print()

    # Tier別
    print("=" * 100)
    print("Tier別内訳")
    print("=" * 100)
    for tier in ['Tier1', 'Tier2', 'Tier3']:
        tstats = stats['by_tier'][tier]
        if tstats['target'] > 0:
            thit_rate = tstats['hit'] / tstats['target'] * 100
            troi = tstats['payout'] / tstats['bet'] * 100 if tstats['bet'] > 0 else 0
            tprofit = tstats['payout'] - tstats['bet']
            print(f"{tier}:")
            print(f"  購入{tstats['target']}件, 的中{tstats['hit']}件, 的中率{thit_rate:.2f}%")
            print(f"  投資額{tstats['bet']:,.0f}円, 払戻{tstats['payout']:,.0f}円")
            print(f"  収支{tprofit:+,.0f}円, ROI {troi:.1f}%")
            print()

    # 条件別
    print("=" * 100)
    print("条件別詳細")
    print("=" * 100)
    sorted_conditions = sorted(stats['by_condition'].items(),
                               key=lambda x: x[1]['payout'] - x[1]['bet'],
                               reverse=True)

    print(f"{'条件':<30} {'購入':<8} {'的中':<8} {'的中率':<10} {'ROI':<10} {'収支':<15}")
    print('-' * 100)

    for condition, cond_stats in sorted_conditions:
        if cond_stats['target'] > 0:
            cond_hit_rate = cond_stats['hit'] / cond_stats['target'] * 100
            cond_roi = cond_stats['payout'] / cond_stats['bet'] * 100 if cond_stats['bet'] > 0 else 0
            cond_profit = cond_stats['payout'] - cond_stats['bet']
            print(f"{condition:<30} {cond_stats['target']:<8} {cond_stats['hit']:<8} "
                  f"{cond_hit_rate:>6.2f}% {cond_roi:>8.1f}% {cond_profit:>+13,.0f}円")

    # 月別ROI
    print()
    print("=" * 100)
    print("月別ROI")
    print("=" * 100)
    for month in sorted(stats['by_month'].keys()):
        mstats = stats['by_month'][month]
        if mstats['target'] > 0:
            mroi = mstats['payout'] / mstats['bet'] * 100
            mprofit = mstats['payout'] - mstats['bet']
            print(f"{month}: ROI {mroi:6.1f}% ({mstats['target']:3d}購入, {mstats['hit']:2d}的中, {mprofit:+10,.0f}円)")

    # 的中レースの詳細
    print()
    print("=" * 100)
    print("的中レース詳細")
    print("=" * 100)
    for h in hit_details:
        print(f"  {h['race_date']} race_id={h['race_id']} {h['combo']} オッズ{h['odds']:.1f}倍 "
              f"払戻{h['payout']:,.0f}円 [{h['condition']}]")

    print("=" * 100)

    # サマリーを返す
    return {
        'purchase_count': purchase_count,
        'hit_count': hit_count,
        'hit_rate': hit_rate,
        'total_investment': total_investment,
        'total_return': total_return,
        'profit': profit,
        'roi': roi,
        'by_confidence': stats['by_confidence'],
        'by_tier': stats['by_tier'],
        'by_month': stats['by_month'],
        'by_condition': dict(stats['by_condition']),
        'hit_details': hit_details
    }


if __name__ == '__main__':
    main()
