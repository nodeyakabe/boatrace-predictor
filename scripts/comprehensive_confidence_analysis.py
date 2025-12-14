# -*- coding: utf-8 -*-
"""
信頼度A・B・C・D 全条件マトリクス 網羅的バックテスト

目的:
1. 信頼度A・Bの可能性を徹底検証（除外判断が正しかったか検証）
2. 全信頼度 x 全級別 x 全オッズ範囲のROI・的中率を算出
3. 有望な条件を抽出し、新戦略を提案

テスト条件:
- 予測タイプ: before（直前情報あり）
- 的中判定: 3連単完全一致（予測1-2-3着 = 実際1-2-3着）
- 払戻金: payoutsテーブルのamount（100円あたりの払戻金額）
- 賭け金: 300円/件
- 対象期間: 2025年全期間
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import json

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def get_odds_range(odds):
    """オッズを範囲カテゴリに分類（10倍刻み）"""
    if odds < 5:
        return '0-5倍'
    elif odds < 10:
        return '5-10倍'
    elif odds < 20:
        return '10-20倍'
    elif odds < 30:
        return '20-30倍'
    elif odds < 40:
        return '30-40倍'
    elif odds < 50:
        return '40-50倍'
    elif odds < 60:
        return '50-60倍'
    elif odds < 70:
        return '60-70倍'
    elif odds < 80:
        return '70-80倍'
    elif odds < 100:
        return '80-100倍'
    elif odds < 120:
        return '100-120倍'
    elif odds < 150:
        return '120-150倍'
    elif odds < 200:
        return '150-200倍'
    elif odds < 300:
        return '200-300倍'
    else:
        return '300倍+'


def main():
    """メイン処理"""
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    bet_amount = 300  # 固定賭け金

    print("=" * 120)
    print("信頼度A・B・C・D 全条件マトリクス 網羅的バックテスト")
    print("=" * 120)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"予測タイプ: before（直前情報あり）")
    print(f"的中判定: 3連単完全一致（予測1-2-3着 = 実際1-2-3着）")
    print(f"払戻金: payoutsテーブルのamount（100円あたりの払戻金額）")
    print(f"賭け金: {bet_amount}円/件")
    print()

    # 2025年全期間のレースを取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    # 統計用データ構造
    # Key: (confidence, c1_rank, odds_range)
    all_conditions = defaultdict(lambda: {
        'total': 0, 'hit': 0, 'bet': 0, 'payout': 0, 'hit_races': []
    })

    # 信頼度別
    by_confidence = defaultdict(lambda: {
        'total': 0, 'hit': 0, 'bet': 0, 'payout': 0
    })

    # 級別
    by_rank = defaultdict(lambda: {
        'total': 0, 'hit': 0, 'bet': 0, 'payout': 0
    })

    # 月別
    by_month = defaultdict(lambda: {
        'total': 0, 'hit': 0, 'bet': 0, 'payout': 0
    })

    # 信頼度 x 級別
    by_conf_rank = defaultdict(lambda: {
        'total': 0, 'hit': 0, 'bet': 0, 'payout': 0
    })

    total_races = 0
    processed_races = 0

    for race in races:
        race_id = race['race_id']
        venue_code = race['venue_code']
        race_date = race['race_date']
        month = race_date[:7]

        total_races += 1

        # 1コース級別を取得
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else None

        if not c1_rank or c1_rank not in ['A1', 'A2', 'B1', 'B2']:
            continue

        # 予測情報を取得（直前情報 = before）
        cursor.execute('''
            SELECT pit_number, confidence, rank_prediction
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']
        if confidence not in ['A', 'B', 'C', 'D']:
            continue

        # 予測トップ3
        top3 = [p['pit_number'] for p in preds[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

        # オッズ取得
        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                       (race_id, combo))
        odds_row = cursor.fetchone()

        if not odds_row or odds_row['odds'] is None:
            continue

        odds = odds_row['odds']
        odds_range = get_odds_range(odds)

        processed_races += 1

        # 集計用キー
        condition_key = (confidence, c1_rank, odds_range)

        # カウント
        all_conditions[condition_key]['total'] += 1
        all_conditions[condition_key]['bet'] += bet_amount
        by_confidence[confidence]['total'] += 1
        by_confidence[confidence]['bet'] += bet_amount
        by_rank[c1_rank]['total'] += 1
        by_rank[c1_rank]['bet'] += bet_amount
        by_month[month]['total'] += 1
        by_month[month]['bet'] += bet_amount
        by_conf_rank[(confidence, c1_rank)]['total'] += 1
        by_conf_rank[(confidence, c1_rank)]['bet'] += bet_amount

        # 実際の結果を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

            # 3連単完全一致判定
            if combo == actual_combo:
                # 的中！払戻金を取得
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    actual_payout = (bet_amount / 100) * payout_row['amount']

                    all_conditions[condition_key]['hit'] += 1
                    all_conditions[condition_key]['payout'] += actual_payout
                    all_conditions[condition_key]['hit_races'].append({
                        'race_id': race_id, 'date': race_date, 'combo': combo,
                        'odds': odds, 'payout': actual_payout
                    })
                    by_confidence[confidence]['hit'] += 1
                    by_confidence[confidence]['payout'] += actual_payout
                    by_rank[c1_rank]['hit'] += 1
                    by_rank[c1_rank]['payout'] += actual_payout
                    by_month[month]['hit'] += 1
                    by_month[month]['payout'] += actual_payout
                    by_conf_rank[(confidence, c1_rank)]['hit'] += 1
                    by_conf_rank[(confidence, c1_rank)]['payout'] += actual_payout

    conn.close()

    # ========================================
    # 結果出力
    # ========================================

    print(f"\n総レース数: {total_races:,}（2025年）")
    print(f"処理対象レース数: {processed_races:,}（予測 + オッズあり）")
    print()

    # Part 1: 信頼度別サマリー
    print("=" * 120)
    print("Part 1: 信頼度別サマリー")
    print("=" * 120)
    print(f"{'信頼度':<10} {'購入数':<10} {'的中数':<10} {'的中率':<12} {'投資額':<15} {'払戻':<15} {'収支':<15} {'ROI':<10}")
    print("-" * 120)

    for conf in ['A', 'B', 'C', 'D']:
        stats = by_confidence[conf]
        if stats['total'] > 0:
            hit_rate = stats['hit'] / stats['total'] * 100
            roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
            profit = stats['payout'] - stats['bet']
            print(f"{conf:<10} {stats['total']:<10} {stats['hit']:<10} {hit_rate:>8.2f}%    "
                  f"{stats['bet']:>12,.0f}円 {stats['payout']:>12,.0f}円 {profit:>+12,.0f}円 {roi:>8.1f}%")

    # Part 2: 1コース級別サマリー
    print()
    print("=" * 120)
    print("Part 2: 1コース級別サマリー")
    print("=" * 120)
    print(f"{'級別':<10} {'購入数':<10} {'的中数':<10} {'的中率':<12} {'投資額':<15} {'払戻':<15} {'収支':<15} {'ROI':<10}")
    print("-" * 120)

    for rank in ['A1', 'A2', 'B1', 'B2']:
        stats = by_rank[rank]
        if stats['total'] > 0:
            hit_rate = stats['hit'] / stats['total'] * 100
            roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
            profit = stats['payout'] - stats['bet']
            print(f"{rank:<10} {stats['total']:<10} {stats['hit']:<10} {hit_rate:>8.2f}%    "
                  f"{stats['bet']:>12,.0f}円 {stats['payout']:>12,.0f}円 {profit:>+12,.0f}円 {roi:>8.1f}%")

    # Part 3: 信頼度 x 級別
    print()
    print("=" * 120)
    print("Part 3: 信頼度 x 級別（クロス集計）")
    print("=" * 120)
    print(f"{'信頼度 x 級別':<15} {'購入数':<10} {'的中数':<10} {'的中率':<12} {'ROI':<10} {'収支':<15}")
    print("-" * 120)

    sorted_conf_rank = sorted(by_conf_rank.items(),
                              key=lambda x: x[1]['payout'] - x[1]['bet'], reverse=True)
    for (conf, rank), stats in sorted_conf_rank:
        if stats['total'] > 0:
            hit_rate = stats['hit'] / stats['total'] * 100
            roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
            profit = stats['payout'] - stats['bet']
            print(f"{conf} x {rank:<10} {stats['total']:<10} {stats['hit']:<10} {hit_rate:>8.2f}%    "
                  f"{roi:>8.1f}% {profit:>+12,.0f}円")

    # Part 4: 全条件マトリクス（有望条件 TOP 100）
    print()
    print("=" * 120)
    print("Part 4: 全条件マトリクス（ROI 100%以上 & 購入数10件以上）")
    print("=" * 120)

    # ROI 100%以上、購入数10件以上の条件を抽出
    profitable_conditions = []
    for condition_key, stats in all_conditions.items():
        if stats['total'] >= 10:  # 最低10件
            roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
            profit = stats['payout'] - stats['bet']
            if roi >= 100:  # ROI 100%以上
                conf, rank, odds_range = condition_key
                profitable_conditions.append({
                    'confidence': conf,
                    'c1_rank': rank,
                    'odds_range': odds_range,
                    'total': stats['total'],
                    'hit': stats['hit'],
                    'hit_rate': stats['hit'] / stats['total'] * 100,
                    'bet': stats['bet'],
                    'payout': stats['payout'],
                    'profit': profit,
                    'roi': roi,
                    'hit_races': stats['hit_races']
                })

    # ROI順にソート
    profitable_conditions.sort(key=lambda x: x['roi'], reverse=True)

    print(f"\n有望条件数: {len(profitable_conditions)}件")
    print()
    print(f"{'条件':<35} {'購入':<8} {'的中':<8} {'的中率':<10} {'ROI':<10} {'収支':<15}")
    print("-" * 120)

    for cond in profitable_conditions[:100]:  # TOP 100
        condition_str = f"{cond['confidence']} x {cond['c1_rank']} x {cond['odds_range']}"
        print(f"{condition_str:<35} {cond['total']:<8} {cond['hit']:<8} "
              f"{cond['hit_rate']:>6.2f}%    {cond['roi']:>8.1f}% {cond['profit']:>+12,.0f}円")

    # Part 5: 信頼度A・Bの詳細分析
    print()
    print("=" * 120)
    print("Part 5: 信頼度A・Bの詳細分析（除外判断の検証）")
    print("=" * 120)

    for conf in ['A', 'B']:
        print(f"\n--- 信頼度{conf}の全オッズ範囲 ---")
        conf_conditions = [(k, v) for k, v in all_conditions.items() if k[0] == conf]
        conf_conditions.sort(key=lambda x: x[1]['payout'] - x[1]['bet'], reverse=True)

        if not conf_conditions:
            print(f"  信頼度{conf}のデータなし")
            continue

        print(f"{'条件':<35} {'購入':<8} {'的中':<8} {'的中率':<10} {'ROI':<10} {'収支':<15}")
        print("-" * 100)

        for (_, rank, odds_range), stats in conf_conditions:
            if stats['total'] > 0:
                hit_rate = stats['hit'] / stats['total'] * 100
                roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
                profit = stats['payout'] - stats['bet']
                condition_str = f"{conf} x {rank} x {odds_range}"
                print(f"{condition_str:<35} {stats['total']:<8} {stats['hit']:<8} "
                      f"{hit_rate:>6.2f}%    {roi:>8.1f}% {profit:>+12,.0f}円")

    # Part 6: 月別推移
    print()
    print("=" * 120)
    print("Part 6: 月別推移（全レース対象）")
    print("=" * 120)
    print(f"{'月':<12} {'購入':<10} {'的中':<8} {'的中率':<10} {'ROI':<10} {'収支':<15}")
    print("-" * 80)

    for month in sorted(by_month.keys()):
        stats = by_month[month]
        if stats['total'] > 0:
            hit_rate = stats['hit'] / stats['total'] * 100
            roi = stats['payout'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
            profit = stats['payout'] - stats['bet']
            print(f"{month:<12} {stats['total']:<10} {stats['hit']:<8} "
                  f"{hit_rate:>6.2f}%    {roi:>8.1f}% {profit:>+12,.0f}円")

    # Part 7: 新戦略提案
    print()
    print("=" * 120)
    print("Part 7: 新戦略提案（有望条件の組み合わせ）")
    print("=" * 120)

    # 信頼度A・Bで ROI 100%以上の条件
    ab_profitable = [c for c in profitable_conditions if c['confidence'] in ['A', 'B']]
    # 信頼度C・Dで ROI 100%以上の条件
    cd_profitable = [c for c in profitable_conditions if c['confidence'] in ['C', 'D']]

    print(f"\n信頼度A・Bで有望な条件: {len(ab_profitable)}件")
    for cond in ab_profitable:
        condition_str = f"{cond['confidence']} x {cond['c1_rank']} x {cond['odds_range']}"
        print(f"  {condition_str}: ROI {cond['roi']:.1f}%, 購入{cond['total']}件, 的中{cond['hit']}件, 収支{cond['profit']:+,.0f}円")

    print(f"\n信頼度C・Dで有望な条件（上位20）: {len(cd_profitable)}件中")
    for cond in cd_profitable[:20]:
        condition_str = f"{cond['confidence']} x {cond['c1_rank']} x {cond['odds_range']}"
        print(f"  {condition_str}: ROI {cond['roi']:.1f}%, 購入{cond['total']}件, 的中{cond['hit']}件, 収支{cond['profit']:+,.0f}円")

    # 統合シミュレーション
    print()
    print("=" * 120)
    print("Part 8: 統合戦略シミュレーション")
    print("=" * 120)

    # 条件1: 現行戦略（信頼度C・D、特定条件）
    current_strategy = [c for c in profitable_conditions
                       if c['confidence'] in ['C', 'D']]

    # 条件2: 信頼度A・B追加（ROI 120%以上）
    ab_high_roi = [c for c in ab_profitable if c['roi'] >= 120]

    # 組み合わせ戦略
    combined = current_strategy[:10] + ab_high_roi  # 上位10 + A/B高ROI

    total_bet = sum(c['bet'] for c in combined)
    total_payout = sum(c['payout'] for c in combined)
    total_profit = total_payout - total_bet
    total_hit = sum(c['hit'] for c in combined)
    total_purchase = sum(c['total'] for c in combined)

    print(f"\n【統合戦略: C/D上位10 + A/B高ROI】")
    print(f"  購入条件数: {len(combined)}")
    print(f"  総購入: {total_purchase}件")
    print(f"  総的中: {total_hit}件（的中率 {total_hit/total_purchase*100:.2f}%）")
    print(f"  総投資: {total_bet:,.0f}円")
    print(f"  総払戻: {total_payout:,.0f}円")
    print(f"  総収支: {total_profit:+,.0f}円")
    print(f"  ROI: {total_payout/total_bet*100:.1f}%")

    # JSON出力用データ
    output_data = {
        'execution_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_races': total_races,
        'processed_races': processed_races,
        'by_confidence': {k: v for k, v in by_confidence.items()},
        'by_rank': {k: v for k, v in by_rank.items()},
        'profitable_conditions': profitable_conditions,
        'ab_profitable': ab_profitable,
    }

    # JSON保存
    output_path = ROOT_DIR / "docs" / "comprehensive_analysis_2025.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n詳細データを {output_path} に保存しました")
    print("=" * 120)

    return output_data


if __name__ == '__main__':
    main()
