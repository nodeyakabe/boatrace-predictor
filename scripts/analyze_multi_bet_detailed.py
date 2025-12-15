# -*- coding: utf-8 -*-
"""
複数点買いパターン詳細分析スクリプト

文字化け対策としてUTF-8出力を強制
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from itertools import permutations
import io

# UTF-8出力を強制
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


# パターン関数定義
def pattern_single(race):
    """現行戦略: 1点買い"""
    return [{'combo': race['combo_123'], 'odds': race['main_odds'], 'bet': 300}]


def pattern_a_axis_flow(race, num_points=4):
    """パターンA: 1着軸固定流し"""
    preds = race['predictions']
    all_odds = race['all_odds']
    axis_1st = preds[0]
    candidates = preds[1:5]

    bets = []
    for second in candidates:
        for third in candidates:
            if second != third:
                combo = f"{axis_1st}-{second}-{third}"
                if combo in all_odds:
                    bets.append({'combo': combo, 'odds': all_odds[combo]})

    return sorted(bets, key=lambda x: x['odds'])[:num_points]


def pattern_b_12_axis(race, num_points=4):
    """パターンB: 1-2着軸固定"""
    preds = race['predictions']
    all_odds = race['all_odds']
    axis_1st, axis_2nd = preds[0], preds[1]
    candidates = preds[2:6]

    bets = []
    for third in candidates:
        if third != axis_1st and third != axis_2nd:
            combo = f"{axis_1st}-{axis_2nd}-{third}"
            if combo in all_odds:
                bets.append({'combo': combo, 'odds': all_odds[combo]})

    return bets[:num_points]


def pattern_c_top4_box(race, num_points=12):
    """パターンC: 上位4艇ボックス"""
    preds = race['predictions']
    all_odds = race['all_odds']
    top4 = preds[:4]

    bets = []
    for combo_tuple in permutations(top4, 3):
        combo = f"{combo_tuple[0]}-{combo_tuple[1]}-{combo_tuple[2]}"
        if combo in all_odds:
            bets.append({'combo': combo, 'odds': all_odds[combo]})

    return sorted(bets, key=lambda x: x['odds'])[:num_points]


def pattern_e_12_and_21(race):
    """パターンE: 1-2軸と2-1軸"""
    preds = race['predictions']
    all_odds = race['all_odds']
    p1, p2 = preds[0], preds[1]
    third_candidates = preds[2:5]

    bets = []
    for third in third_candidates:
        if third != p1 and third != p2:
            combo = f"{p1}-{p2}-{third}"
            if combo in all_odds:
                bets.append({'combo': combo, 'odds': all_odds[combo]})
            combo = f"{p2}-{p1}-{third}"
            if combo in all_odds:
                bets.append({'combo': combo, 'odds': all_odds[combo]})

    return bets


def pattern_f_top3_flow(race):
    """パターンF: 予測Top3流し"""
    preds = race['predictions']
    all_odds = race['all_odds']
    top3 = preds[:3]

    bets = []
    for combo_tuple in permutations(top3, 3):
        combo = f"{combo_tuple[0]}-{combo_tuple[1]}-{combo_tuple[2]}"
        if combo in all_odds:
            bets.append({'combo': combo, 'odds': all_odds[combo]})

    return bets


def pattern_g_1st_axis_top3(race):
    """パターンG: 1着軸-2,3,4位"""
    preds = race['predictions']
    all_odds = race['all_odds']
    axis = preds[0]
    candidates = preds[1:4]

    bets = []
    for second in candidates:
        for third in candidates:
            if second != third:
                combo = f"{axis}-{second}-{third}"
                if combo in all_odds:
                    bets.append({'combo': combo, 'odds': all_odds[combo]})

    return bets


def pattern_b12_weighted(race):
    """パターンH: 1-2軸3点（傾斜配分）"""
    preds = race['predictions']
    all_odds = race['all_odds']
    axis_1st, axis_2nd = preds[0], preds[1]
    candidates = preds[2:5]

    bets = []
    for i, third in enumerate(candidates):
        if third != axis_1st and third != axis_2nd:
            combo = f"{axis_1st}-{axis_2nd}-{third}"
            if combo in all_odds:
                # 傾斜配分: 1点目200円、2点目100円、3点目100円
                bet_amount = 200 if i == 0 else 100
                bets.append({'combo': combo, 'odds': all_odds[combo], 'bet': bet_amount})

    return bets


def pattern_hybrid(race):
    """パターンI: ハイブリッド（1-2-3と1-2-4の2点）"""
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


def evaluate_pattern(races, pattern_func, total_budget=300, use_fixed_bet=False):
    """パターンを評価"""
    stats = {
        'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0,
        'max_drawdown': 0, 'cumulative_pnl': [], 'hit_details': [],
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

        # 配分計算
        if use_fixed_bet:
            # 固定金額（bet属性使用）
            race_investment = sum(b.get('bet', 100) for b in bets)
        else:
            bet_per_point = max(100, (total_budget // num_bets // 100) * 100)
            race_investment = bet_per_point * num_bets

        stats['investment'] += race_investment

        hit = False
        for bet in bets:
            if bet['combo'] == race['actual_combo'] and race['payout']:
                hit = True
                if use_fixed_bet:
                    bet_amount = bet.get('bet', 100)
                else:
                    bet_amount = bet_per_point
                race_payout = (bet_amount / 100) * race['payout']
                stats['payout'] += race_payout
                stats['hit_details'].append({
                    'race_id': race['race_id'],
                    'date': race['race_date'],
                    'combo': bet['combo'],
                    'odds': bet['odds'],
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


def main():
    """メイン処理"""
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 120)
    print("複数点買いパターン詳細分析")
    print("=" * 120)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    print("戦略B対象レースを取得中...")
    races = get_strategy_b_races(cursor)
    print(f"対象レース数: {len(races)}")

    # 条件別内訳
    conf_c = [r for r in races if r['confidence'] == 'C']
    conf_d = [r for r in races if r['confidence'] == 'D']
    print(f"  - 信頼度C: {len(conf_c)}レース")
    print(f"  - 信頼度D: {len(conf_d)}レース")
    print()

    # パターン定義
    patterns = [
        ('現行1点買い(300円)', pattern_single, 300, False),
        ('A: 1着軸流し4点(400円)', lambda r: pattern_a_axis_flow(r, 4), 400, False),
        ('A: 1着軸流し6点(600円)', lambda r: pattern_a_axis_flow(r, 6), 600, False),
        ('B: 1-2軸3点(300円)', lambda r: pattern_b_12_axis(r, 3), 300, False),
        ('B: 1-2軸4点(400円)', lambda r: pattern_b_12_axis(r, 4), 400, False),
        ('C: Top4BOX6点(600円)', lambda r: pattern_c_top4_box(r, 6), 600, False),
        ('C: Top4BOX12点(1200円)', lambda r: pattern_c_top4_box(r, 12), 1200, False),
        ('E: 1-2+2-1軸(600円)', pattern_e_12_and_21, 600, False),
        ('F: Top3流し6点(600円)', pattern_f_top3_flow, 600, False),
        ('G: 1着軸-234位6点(600円)', pattern_g_1st_axis_top3, 600, False),
        ('H: 1-2軸傾斜(400円)', pattern_b12_weighted, 400, True),
        ('I: 1-2-3+1-2-4(300円)', pattern_hybrid, 300, True),
    ]

    results = []

    print("=" * 120)
    print("パターン別検証結果（全体）")
    print("=" * 120)
    print()
    header = f"{'パターン':<28} {'レース':>6} {'平均点':>6} {'的中':>5} {'的中率':>7} {'投資':>11} {'払戻':>11} {'収支':>12} {'ROI':>7} {'MaxDD':>9}"
    print(header)
    print("-" * 120)

    for name, func, budget, use_fixed in patterns:
        stats = evaluate_pattern(races, func, budget, use_fixed)

        if stats['races'] == 0:
            continue

        avg_bets = stats['bets'] / stats['races']
        hit_rate = (stats['hits'] / stats['races'] * 100) if stats['races'] > 0 else 0
        profit = stats['payout'] - stats['investment']
        roi = (stats['payout'] / stats['investment'] * 100) if stats['investment'] > 0 else 0

        results.append({
            'name': name, 'races': stats['races'], 'avg_bets': avg_bets,
            'hits': stats['hits'], 'hit_rate': hit_rate,
            'investment': stats['investment'], 'payout': stats['payout'],
            'profit': profit, 'roi': roi, 'max_drawdown': stats['max_drawdown'],
        })

        print(f"{name:<28} {stats['races']:>6} {avg_bets:>6.1f} {stats['hits']:>5} {hit_rate:>6.1f}% "
              f"{stats['investment']:>10,.0f} {stats['payout']:>10,.0f} {profit:>+11,.0f} {roi:>6.1f}% {stats['max_drawdown']:>8,.0f}")

    # 収支ランキング
    print()
    print("=" * 120)
    print("【収支ランキング】上位5パターン")
    print("=" * 120)

    sorted_by_profit = sorted(results, key=lambda x: x['profit'], reverse=True)
    for i, r in enumerate(sorted_by_profit[:5], 1):
        print(f"{i}位: {r['name']}")
        print(f"     収支: {r['profit']:+,.0f}円 | ROI: {r['roi']:.1f}% | 的中率: {r['hit_rate']:.1f}%")
        print(f"     投資: {r['investment']:,.0f}円 | 払戻: {r['payout']:,.0f}円 | MaxDD: {r['max_drawdown']:,.0f}円")
        print()

    # 現行戦略との比較
    print("=" * 120)
    print("【現行戦略との比較】")
    print("=" * 120)

    baseline = next((r for r in results if '現行' in r['name']), None)
    if baseline:
        print(f"現行戦略: 収支 {baseline['profit']:+,.0f}円 | ROI {baseline['roi']:.1f}% | 的中率 {baseline['hit_rate']:.1f}%")
        print()

        print("改善パターン:")
        for r in sorted_by_profit:
            if '現行' not in r['name'] and r['profit'] > baseline['profit']:
                diff_profit = r['profit'] - baseline['profit']
                diff_roi = r['roi'] - baseline['roi']
                diff_hit = r['hit_rate'] - baseline['hit_rate']

                print(f"  {r['name']}:")
                print(f"    収支: {r['profit']:+,.0f}円 (差額 {diff_profit:+,.0f}円)")
                print(f"    ROI: {r['roi']:.1f}% ({diff_roi:+.1f}pt) | 的中率: {r['hit_rate']:.1f}% ({diff_hit:+.1f}pt)")
                print()

    # 信頼度別分析
    print("=" * 120)
    print("【信頼度別分析】")
    print("=" * 120)

    for conf_name, conf_races in [('信頼度C', conf_c), ('信頼度D', conf_d)]:
        print(f"\n{conf_name}（{len(conf_races)}レース）")
        print("-" * 100)

        conf_results = []
        for name, func, budget, use_fixed in patterns:
            stats = evaluate_pattern(conf_races, func, budget, use_fixed)
            if stats['races'] > 0:
                hit_rate = stats['hits'] / stats['races'] * 100
                profit = stats['payout'] - stats['investment']
                roi = stats['payout'] / stats['investment'] * 100 if stats['investment'] > 0 else 0
                conf_results.append({
                    'name': name, 'hits': stats['hits'], 'races': stats['races'],
                    'hit_rate': hit_rate, 'profit': profit, 'roi': roi
                })

        conf_results.sort(key=lambda x: x['profit'], reverse=True)
        for r in conf_results[:5]:
            print(f"  {r['name']:<28}: 的中{r['hits']:>2}/{r['races']:<3} ({r['hit_rate']:>5.1f}%) 収支{r['profit']:>+10,.0f}円 ROI{r['roi']:>6.1f}%")

    # 条件別詳細
    print()
    print("=" * 120)
    print("【条件別詳細分析】（各条件での最適パターン）")
    print("=" * 120)

    conditions = [
        ('C', 'B1', 30, 40),
        ('C', 'A1', 30, 40),
        ('D', 'B1', 40, 50),
        ('D', 'A1', 40, 50),
        ('D', 'A2', 20, 30),
    ]

    for conf, rank, o_min, o_max in conditions:
        cond_races = [r for r in races if r['condition'] == (conf, rank, o_min, o_max)]
        if len(cond_races) < 10:
            continue

        print(f"\n{conf} x {rank} x {o_min}-{o_max}倍（{len(cond_races)}レース）")
        print("-" * 80)

        cond_results = []
        for name, func, budget, use_fixed in patterns:
            stats = evaluate_pattern(cond_races, func, budget, use_fixed)
            if stats['races'] > 0:
                hit_rate = stats['hits'] / stats['races'] * 100
                profit = stats['payout'] - stats['investment']
                roi = stats['payout'] / stats['investment'] * 100 if stats['investment'] > 0 else 0
                cond_results.append({
                    'name': name, 'hits': stats['hits'], 'races': stats['races'],
                    'hit_rate': hit_rate, 'profit': profit, 'roi': roi
                })

        cond_results.sort(key=lambda x: x['profit'], reverse=True)
        for r in cond_results[:3]:
            print(f"    {r['name']:<28}: 的中{r['hits']:>2}/{r['races']:<3} ({r['hit_rate']:>5.1f}%) 収支{r['profit']:>+10,.0f}円 ROI{r['roi']:>6.1f}%")

    conn.close()

    print()
    print("=" * 120)
    print("分析完了")
    print("=" * 120)

    return results


if __name__ == '__main__':
    main()
