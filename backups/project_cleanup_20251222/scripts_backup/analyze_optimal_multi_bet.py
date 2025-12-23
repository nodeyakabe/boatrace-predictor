# -*- coding: utf-8 -*-
"""
最適複数点買いパターン詳細分析

最有望パターンの詳細検証とバリエーション分析
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from itertools import permutations
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def get_strategy_b_races(cursor):
    """戦略B対象レースを取得"""
    conditions = [
        ('C', ['B1'], 30, 40),
        ('C', ['A1'], 30, 40),
        ('D', ['B1'], 40, 50),
        ('D', ['A1'], 40, 50),
        ('D', ['A2'], 20, 30),
    ]

    races = []

    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    all_races = cursor.fetchall()

    for race in all_races:
        race_id = race['race_id']

        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else None
        if not c1_rank:
            continue

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
        if confidence in ['A', 'B']:
            continue

        predictions = [p['pit_number'] for p in preds]
        combo_123 = f"{predictions[0]}-{predictions[1]}-{predictions[2]}"

        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                       (race_id, combo_123))
        odds_row = cursor.fetchone()

        if not odds_row:
            continue

        main_odds = odds_row['odds']

        matched_condition = None
        for conf, ranks, odds_min, odds_max in conditions:
            if confidence == conf and c1_rank in ranks and odds_min <= main_odds < odds_max:
                matched_condition = (conf, c1_rank, odds_min, odds_max)
                break

        if not matched_condition:
            continue

        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
        all_odds = {row['combination']: row['odds'] for row in cursor.fetchall()}

        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank IN ('1', '2', '3')
            ORDER BY CAST(rank AS INTEGER)
        ''', (race_id,))
        results = cursor.fetchall()

        actual_combo = None
        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

        payout = None
        if actual_combo:
            cursor.execute('''
                SELECT amount FROM payouts
                WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
            ''', (race_id, actual_combo))
            payout_row = cursor.fetchone()
            if payout_row:
                payout = payout_row['amount']

        races.append({
            'race_id': race_id,
            'race_date': race['race_date'],
            'venue_code': race['venue_code'],
            'race_number': race['race_number'],
            'confidence': confidence,
            'c1_rank': c1_rank,
            'predictions': predictions,
            'combo_123': combo_123,
            'main_odds': main_odds,
            'all_odds': all_odds,
            'actual_combo': actual_combo,
            'payout': payout,
            'condition': matched_condition,
        })

    return races


def evaluate_pattern_with_fixed_bets(races, pattern_func):
    """固定金額パターンを評価"""
    stats = {
        'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0,
        'max_drawdown': 0, 'cumulative_pnl': [], 'hit_details': [],
        'monthly_stats': defaultdict(lambda: {'hits': 0, 'investment': 0, 'payout': 0}),
    }

    cumulative = 0
    peak = 0

    for race in races:
        bets = pattern_func(race)
        if not bets:
            continue

        stats['races'] += 1
        num_bets = len(bets)
        stats['bets'] += num_bets

        race_investment = sum(b['bet'] for b in bets)
        stats['investment'] += race_investment

        month = race['race_date'][:7]
        stats['monthly_stats'][month]['investment'] += race_investment

        hit = False
        for bet in bets:
            if bet['combo'] == race['actual_combo'] and race['payout']:
                hit = True
                race_payout = (bet['bet'] / 100) * race['payout']
                stats['payout'] += race_payout
                stats['monthly_stats'][month]['payout'] += race_payout
                stats['monthly_stats'][month]['hits'] += 1
                stats['hit_details'].append({
                    'race_id': race['race_id'],
                    'date': race['race_date'],
                    'combo': bet['combo'],
                    'odds': bet['odds'],
                    'bet': bet['bet'],
                    'payout': race_payout,
                })
                break

        if hit:
            stats['hits'] += 1
            cumulative += race_payout - race_investment
        else:
            cumulative -= race_investment

        stats['cumulative_pnl'].append(cumulative)

        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        if drawdown > stats['max_drawdown']:
            stats['max_drawdown'] = drawdown

    return stats


# 最有望パターンのバリエーション
def pattern_current(race):
    """現行戦略: 1点買い 300円"""
    return [{'combo': race['combo_123'], 'odds': race['main_odds'], 'bet': 300}]


def pattern_h_original(race):
    """パターンH: 1-2軸傾斜配分（200/100/100）"""
    preds = race['predictions']
    all_odds = race['all_odds']
    axis_1st, axis_2nd = preds[0], preds[1]
    candidates = preds[2:5]

    bets = []
    for i, third in enumerate(candidates):
        if third != axis_1st and third != axis_2nd:
            combo = f"{axis_1st}-{axis_2nd}-{third}"
            if combo in all_odds:
                bet_amount = 200 if i == 0 else 100
                bets.append({'combo': combo, 'odds': all_odds[combo], 'bet': bet_amount})

    return bets


def pattern_h_v2(race):
    """パターンH-V2: 1-2軸傾斜配分（150/100/50）"""
    preds = race['predictions']
    all_odds = race['all_odds']
    axis_1st, axis_2nd = preds[0], preds[1]
    candidates = preds[2:5]

    bet_amounts = [150, 100, 50]
    bets = []
    for i, third in enumerate(candidates):
        if third != axis_1st and third != axis_2nd:
            combo = f"{axis_1st}-{axis_2nd}-{third}"
            if combo in all_odds:
                bets.append({'combo': combo, 'odds': all_odds[combo], 'bet': bet_amounts[i]})

    return bets


def pattern_h_v3(race):
    """パターンH-V3: 1-2軸4点傾斜配分（150/100/100/50）"""
    preds = race['predictions']
    all_odds = race['all_odds']
    axis_1st, axis_2nd = preds[0], preds[1]
    candidates = preds[2:6]

    bet_amounts = [150, 100, 100, 50]
    bets = []
    idx = 0
    for third in candidates:
        if third != axis_1st and third != axis_2nd and idx < 4:
            combo = f"{axis_1st}-{axis_2nd}-{third}"
            if combo in all_odds:
                bets.append({'combo': combo, 'odds': all_odds[combo], 'bet': bet_amounts[idx]})
                idx += 1

    return bets


def pattern_b3_equal(race):
    """パターンB: 1-2軸3点均等（100/100/100）"""
    preds = race['predictions']
    all_odds = race['all_odds']
    axis_1st, axis_2nd = preds[0], preds[1]
    candidates = preds[2:5]

    bets = []
    for third in candidates:
        if third != axis_1st and third != axis_2nd:
            combo = f"{axis_1st}-{axis_2nd}-{third}"
            if combo in all_odds:
                bets.append({'combo': combo, 'odds': all_odds[combo], 'bet': 100})

    return bets


def pattern_i_original(race):
    """パターンI: 1-2-3+1-2-4（200+100）"""
    preds = race['predictions']
    all_odds = race['all_odds']
    p1, p2, p3, p4 = preds[0], preds[1], preds[2], preds[3]

    bets = []
    combo1 = f"{p1}-{p2}-{p3}"
    if combo1 in all_odds:
        bets.append({'combo': combo1, 'odds': all_odds[combo1], 'bet': 200})

    combo2 = f"{p1}-{p2}-{p4}"
    if combo2 in all_odds:
        bets.append({'combo': combo2, 'odds': all_odds[combo2], 'bet': 100})

    return bets


def pattern_i_v2(race):
    """パターンI-V2: 1-2-3+1-2-4+1-2-5（150+100+50）"""
    preds = race['predictions']
    all_odds = race['all_odds']
    p1, p2 = preds[0], preds[1]
    third_list = [preds[2], preds[3], preds[4]]
    bet_amounts = [150, 100, 50]

    bets = []
    for i, third in enumerate(third_list):
        combo = f"{p1}-{p2}-{third}"
        if combo in all_odds:
            bets.append({'combo': combo, 'odds': all_odds[combo], 'bet': bet_amounts[i]})

    return bets


def pattern_hybrid_12_21(race):
    """パターンJ: 1-2-3 + 2-1-3（150+150）"""
    preds = race['predictions']
    all_odds = race['all_odds']
    p1, p2, p3 = preds[0], preds[1], preds[2]

    bets = []
    combo1 = f"{p1}-{p2}-{p3}"
    if combo1 in all_odds:
        bets.append({'combo': combo1, 'odds': all_odds[combo1], 'bet': 150})

    combo2 = f"{p2}-{p1}-{p3}"
    if combo2 in all_odds:
        bets.append({'combo': combo2, 'odds': all_odds[combo2], 'bet': 150})

    return bets


def pattern_k_comprehensive(race):
    """パターンK: 1-2-3 + 1-2-4 + 2-1-3（150+100+50）"""
    preds = race['predictions']
    all_odds = race['all_odds']
    p1, p2, p3, p4 = preds[0], preds[1], preds[2], preds[3]

    bets = []
    combos_with_bets = [
        (f"{p1}-{p2}-{p3}", 150),
        (f"{p1}-{p2}-{p4}", 100),
        (f"{p2}-{p1}-{p3}", 50),
    ]

    for combo, bet in combos_with_bets:
        if combo in all_odds:
            bets.append({'combo': combo, 'odds': all_odds[combo], 'bet': bet})

    return bets


def pattern_l_focused(race):
    """パターンL: 1-2-3のみ重点（300円）+ 1-2-4軽く（100円）"""
    preds = race['predictions']
    all_odds = race['all_odds']
    p1, p2, p3, p4 = preds[0], preds[1], preds[2], preds[3]

    bets = []
    combo1 = f"{p1}-{p2}-{p3}"
    if combo1 in all_odds:
        bets.append({'combo': combo1, 'odds': all_odds[combo1], 'bet': 300})

    combo2 = f"{p1}-{p2}-{p4}"
    if combo2 in all_odds:
        bets.append({'combo': combo2, 'odds': all_odds[combo2], 'bet': 100})

    return bets


def main():
    """メイン処理"""
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 130)
    print("最適複数点買いパターン詳細分析")
    print("=" * 130)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    print("戦略B対象レースを取得中...")
    races = get_strategy_b_races(cursor)
    print(f"対象レース数: {len(races)}")
    print()

    # パターン定義（名前, 関数, 説明）
    patterns = [
        ('現行(1点300円)', pattern_current, '予測1-2-3のみ300円'),
        ('H: 傾斜200/100/100', pattern_h_original, '1-2軸、3着候補に傾斜配分'),
        ('H-V2: 傾斜150/100/50', pattern_h_v2, '1-2軸、より傾斜を強調'),
        ('H-V3: 4点150/100/100/50', pattern_h_v3, '1-2軸4点、傾斜配分'),
        ('B: 均等100x3', pattern_b3_equal, '1-2軸3点均等配分'),
        ('I: 2点200+100', pattern_i_original, '1-2-3と1-2-4の2点'),
        ('I-V2: 3点150+100+50', pattern_i_v2, '1-2-3,4,5の3点傾斜'),
        ('J: 12+21(150x2)', pattern_hybrid_12_21, '1-2-3と2-1-3の2点'),
        ('K: 総合150+100+50', pattern_k_comprehensive, '1-2-3,1-2-4,2-1-3'),
        ('L: 重点300+100', pattern_l_focused, '1-2-3重点+1-2-4軽く'),
    ]

    results = []

    print("=" * 130)
    print("パターン別検証結果")
    print("=" * 130)
    header = f"{'パターン':<22} {'説明':<30} {'レース':>5} {'的中':>4} {'的中率':>6} {'投資':>10} {'払戻':>10} {'収支':>11} {'ROI':>6} {'MaxDD':>8}"
    print(header)
    print("-" * 130)

    for name, func, desc in patterns:
        stats = evaluate_pattern_with_fixed_bets(races, func)

        if stats['races'] == 0:
            continue

        hit_rate = (stats['hits'] / stats['races'] * 100) if stats['races'] > 0 else 0
        profit = stats['payout'] - stats['investment']
        roi = (stats['payout'] / stats['investment'] * 100) if stats['investment'] > 0 else 0

        results.append({
            'name': name, 'desc': desc, 'races': stats['races'],
            'hits': stats['hits'], 'hit_rate': hit_rate,
            'investment': stats['investment'], 'payout': stats['payout'],
            'profit': profit, 'roi': roi, 'max_drawdown': stats['max_drawdown'],
            'monthly_stats': stats['monthly_stats'],
        })

        print(f"{name:<22} {desc:<30} {stats['races']:>5} {stats['hits']:>4} {hit_rate:>5.1f}% "
              f"{stats['investment']:>9,.0f} {stats['payout']:>9,.0f} {profit:>+10,.0f} {roi:>5.1f}% {stats['max_drawdown']:>7,.0f}")

    # 収支ランキング
    print()
    print("=" * 130)
    print("【収支ランキング】")
    print("=" * 130)

    sorted_by_profit = sorted(results, key=lambda x: x['profit'], reverse=True)
    for i, r in enumerate(sorted_by_profit, 1):
        status = "★ 推奨" if i <= 3 else ""
        print(f"{i:>2}位: {r['name']:<22} 収支{r['profit']:>+10,.0f}円 ROI{r['roi']:>6.1f}% 的中率{r['hit_rate']:>5.1f}% {status}")

    # 現行戦略との比較
    print()
    print("=" * 130)
    print("【現行戦略との詳細比較】")
    print("=" * 130)

    baseline = next((r for r in results if '現行' in r['name']), None)
    if baseline:
        print(f"現行戦略: 収支 {baseline['profit']:+,.0f}円 | ROI {baseline['roi']:.1f}% | 的中率 {baseline['hit_rate']:.1f}%")
        print(f"          投資 {baseline['investment']:,.0f}円 | 払戻 {baseline['payout']:,.0f}円 | MaxDD {baseline['max_drawdown']:,.0f}円")
        print()

        print("現行を上回るパターン:")
        for r in sorted_by_profit:
            if '現行' not in r['name'] and r['profit'] > baseline['profit']:
                diff_profit = r['profit'] - baseline['profit']
                diff_roi = r['roi'] - baseline['roi']
                diff_hit = r['hit_rate'] - baseline['hit_rate']
                diff_investment = r['investment'] - baseline['investment']

                print(f"\n  {r['name']}:")
                print(f"    収支: {r['profit']:+,.0f}円 (現行比 {diff_profit:+,.0f}円 / {diff_profit/abs(baseline['profit'])*100:+.1f}%)")
                print(f"    ROI: {r['roi']:.1f}% ({diff_roi:+.1f}pt)")
                print(f"    的中率: {r['hit_rate']:.1f}% ({diff_hit:+.1f}pt)")
                print(f"    投資額: {r['investment']:,.0f}円 ({diff_investment:+,.0f}円)")
                print(f"    MaxDD: {r['max_drawdown']:,.0f}円")

    # 月別ROI比較（上位3パターン）
    print()
    print("=" * 130)
    print("【月別ROI比較】（上位3パターン + 現行）")
    print("=" * 130)

    top_patterns = [r for r in sorted_by_profit[:3] if '現行' not in r['name']]
    if baseline and baseline not in top_patterns:
        comparison_patterns = [baseline] + top_patterns
    else:
        comparison_patterns = sorted_by_profit[:4]

    # ヘッダー
    months = sorted(set(m for r in comparison_patterns for m in r['monthly_stats'].keys()))
    print(f"{'パターン':<22} " + " ".join([f"{m[-2:]}月" for m in months]) + " | 年間")
    print("-" * 130)

    for r in comparison_patterns:
        row = f"{r['name']:<22} "
        year_profit = 0
        for m in months:
            mstats = r['monthly_stats'].get(m, {'investment': 0, 'payout': 0, 'hits': 0})
            if mstats['investment'] > 0:
                m_profit = mstats['payout'] - mstats['investment']
                year_profit += m_profit
                row += f"{m_profit:>+6,.0f} "
            else:
                row += "    -- "
        row += f"| {year_profit:>+9,.0f}"
        print(row)

    # トリガミリスク分析
    print()
    print("=" * 130)
    print("【トリガミリスク分析】（上位3パターン）")
    print("=" * 130)

    for r in top_patterns:
        name = r['name']
        investment_per_race = r['investment'] / r['races']
        avg_payout_when_hit = r['payout'] / r['hits'] if r['hits'] > 0 else 0

        # トリガミ（払戻<投資）になる率を推定
        print(f"\n{name}:")
        print(f"  1レースあたり平均投資: {investment_per_race:,.0f}円")
        print(f"  的中時平均払戻: {avg_payout_when_hit:,.0f}円")
        print(f"  平均収益倍率: {avg_payout_when_hit/investment_per_race:.2f}倍")

        # トリガミ閾値オッズを計算
        if investment_per_race > 0:
            trigami_threshold = investment_per_race / 100 * 100  # 100円単位
            print(f"  トリガミ閾値オッズ: {trigami_threshold/100:.1f}倍以下で赤字")

    # 最終推奨
    print()
    print("=" * 130)
    print("【最終推奨】")
    print("=" * 130)

    best = sorted_by_profit[0]
    print(f"\n推奨パターン: {best['name']}")
    print(f"説明: {best['desc']}")
    print()
    print(f"予想実績:")
    print(f"  - 年間収支: {best['profit']:+,.0f}円")
    print(f"  - ROI: {best['roi']:.1f}%")
    print(f"  - 的中率: {best['hit_rate']:.1f}%（{best['hits']}/{best['races']}）")
    print(f"  - 総投資: {best['investment']:,.0f}円")
    print(f"  - 総払戻: {best['payout']:,.0f}円")
    print(f"  - 最大ドローダウン: {best['max_drawdown']:,.0f}円")

    if baseline:
        improvement = best['profit'] - baseline['profit']
        print()
        print(f"現行戦略からの改善:")
        print(f"  - 収支改善: {improvement:+,.0f}円（{improvement/abs(baseline['profit'])*100:+.1f}%）")
        print(f"  - 的中率改善: {best['hit_rate'] - baseline['hit_rate']:+.1f}ポイント")

    conn.close()

    print()
    print("=" * 130)
    print("分析完了")
    print("=" * 130)

    return results


if __name__ == '__main__':
    main()
