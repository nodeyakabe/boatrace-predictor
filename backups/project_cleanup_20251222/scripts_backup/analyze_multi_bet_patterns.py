# -*- coding: utf-8 -*-
"""
複数点買いパターン分析スクリプト

現在の1点買い戦略Bに対し、複数点買いによる改善可能性を検証する
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from itertools import permutations

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def get_strategy_b_races(cursor):
    """
    戦略B対象レースを取得
    条件: 信頼度C/D、指定オッズレンジ、1コース級別条件
    """
    # 戦略Bの条件定義（bet_target_evaluator.pyより）
    # C: B1 30-40, A1 30-40
    # D: B1 40-50, A1 40-50, A2 20-30
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

        # 1コース級別を取得
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else None
        if not c1_rank:
            continue

        # 予測情報を取得
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

        # 信頼度A, Bは除外
        if confidence in ['A', 'B']:
            continue

        # 予測順位（1位〜6位）
        predictions = [p['pit_number'] for p in preds]

        # 予測1-2-3の組み合わせ
        combo_123 = f"{predictions[0]}-{predictions[1]}-{predictions[2]}"

        # オッズ取得（予測1-2-3）
        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                       (race_id, combo_123))
        odds_row = cursor.fetchone()

        if not odds_row:
            continue

        main_odds = odds_row['odds']

        # 条件に合致するかチェック
        matched_condition = None
        for conf, ranks, odds_min, odds_max in conditions:
            if confidence == conf and c1_rank in ranks and odds_min <= main_odds < odds_max:
                matched_condition = (conf, c1_rank, odds_min, odds_max)
                break

        if not matched_condition:
            continue

        # 全オッズを取得
        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ?', (race_id,))
        all_odds = {row['combination']: row['odds'] for row in cursor.fetchall()}

        # 結果を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank IN ('1', '2', '3')
            ORDER BY CAST(rank AS INTEGER)
        ''', (race_id,))
        results = cursor.fetchall()

        actual_combo = None
        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

        # 払戻金を取得
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


def pattern_single(race):
    """現行戦略: 1点買い（予測1-2-3のみ）"""
    combo = race['combo_123']
    odds = race['main_odds']

    return [{'combo': combo, 'odds': odds, 'bet': 300}]


def pattern_a_axis_flow(race, num_points=4):
    """
    パターンA: 1着軸固定流し
    1着予測を軸に、2-3着を複数組み合わせ
    """
    preds = race['predictions']
    all_odds = race['all_odds']

    # 1着軸（予測1位）
    axis_1st = preds[0]

    # 2-3着候補（予測2位〜5位）
    candidates = preds[1:5]

    bets = []
    for second in candidates:
        for third in candidates:
            if second != third:
                combo = f"{axis_1st}-{second}-{third}"
                if combo in all_odds:
                    bets.append({'combo': combo, 'odds': all_odds[combo]})

    # オッズ順でソート（低い方を優先）して上位N点を選択
    bets = sorted(bets, key=lambda x: x['odds'])[:num_points]

    return bets


def pattern_b_12_axis(race, num_points=4):
    """
    パターンB: 1-2着軸固定
    1-2着予測を軸に、3着を複数
    """
    preds = race['predictions']
    all_odds = race['all_odds']

    axis_1st = preds[0]
    axis_2nd = preds[1]

    # 3着候補（予測3位〜6位）
    candidates = preds[2:6]

    bets = []
    for third in candidates:
        if third != axis_1st and third != axis_2nd:
            combo = f"{axis_1st}-{axis_2nd}-{third}"
            if combo in all_odds:
                bets.append({'combo': combo, 'odds': all_odds[combo]})

    return bets[:num_points]


def pattern_c_top4_box(race, num_points=12):
    """
    パターンC: 上位4艇ボックス
    予測上位4艇から3連単を複数点
    """
    preds = race['predictions']
    all_odds = race['all_odds']

    top4 = preds[:4]

    bets = []
    for combo_tuple in permutations(top4, 3):
        combo = f"{combo_tuple[0]}-{combo_tuple[1]}-{combo_tuple[2]}"
        if combo in all_odds:
            bets.append({'combo': combo, 'odds': all_odds[combo]})

    # オッズ順でソートして上位N点
    bets = sorted(bets, key=lambda x: x['odds'])[:num_points]

    return bets


def pattern_d_odds_range(race, odds_min=20, odds_max=50, num_points=4):
    """
    パターンD: オッズ帯重視
    特定オッズレンジ内の組み合わせを複数点
    """
    preds = race['predictions']
    all_odds = race['all_odds']

    # 予測上位5艇の組み合わせでオッズ範囲内のものを探す
    top5 = preds[:5]

    bets = []
    for combo_tuple in permutations(top5, 3):
        combo = f"{combo_tuple[0]}-{combo_tuple[1]}-{combo_tuple[2]}"
        if combo in all_odds:
            odds = all_odds[combo]
            if odds_min <= odds <= odds_max:
                bets.append({'combo': combo, 'odds': odds})

    # オッズ順でソート
    bets = sorted(bets, key=lambda x: x['odds'])[:num_points]

    return bets


def pattern_e_12_and_21(race):
    """
    パターンE: 1-2軸と2-1軸の組み合わせ
    予測1-2-X と 2-1-X を両方買う
    """
    preds = race['predictions']
    all_odds = race['all_odds']

    p1, p2, p3 = preds[0], preds[1], preds[2]
    third_candidates = preds[2:5]  # 3着候補

    bets = []

    # 1-2-X パターン
    for third in third_candidates:
        if third != p1 and third != p2:
            combo = f"{p1}-{p2}-{third}"
            if combo in all_odds:
                bets.append({'combo': combo, 'odds': all_odds[combo]})

    # 2-1-X パターン
    for third in third_candidates:
        if third != p1 and third != p2:
            combo = f"{p2}-{p1}-{third}"
            if combo in all_odds:
                bets.append({'combo': combo, 'odds': all_odds[combo]})

    return bets


def pattern_f_top3_flow(race):
    """
    パターンF: 予測Top3流し
    1-2-3, 1-3-2, 2-1-3, 2-3-1, 3-1-2, 3-2-1の6点
    """
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
    """
    パターンG: 1着軸-2,3着を予測2-4位から
    1着は予測1位固定、2-3着は予測2-4位から選択
    """
    preds = race['predictions']
    all_odds = race['all_odds']

    axis = preds[0]
    candidates = preds[1:4]  # 予測2-4位

    bets = []
    for second in candidates:
        for third in candidates:
            if second != third:
                combo = f"{axis}-{second}-{third}"
                if combo in all_odds:
                    bets.append({'combo': combo, 'odds': all_odds[combo]})

    return bets


def evaluate_pattern(races, pattern_func, pattern_name, total_budget=300, allocation='equal'):
    """
    パターンを評価

    Args:
        races: 対象レースリスト
        pattern_func: パターン関数
        pattern_name: パターン名
        total_budget: 1レースあたりの総賭金
        allocation: 配分方法 ('equal', 'weighted')
    """
    stats = {
        'races': 0,
        'bets': 0,
        'hits': 0,
        'investment': 0,
        'payout': 0,
        'max_drawdown': 0,
        'cumulative_pnl': [],
        'hit_details': [],
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
        if allocation == 'equal':
            # 均等配分（100円単位に丸め）
            bet_per_point = max(100, (total_budget // num_bets // 100) * 100)
        else:
            # 重み付け配分（低オッズに多く配分）
            bet_per_point = max(100, (total_budget // num_bets // 100) * 100)

        race_investment = bet_per_point * num_bets
        stats['investment'] += race_investment

        # 的中判定
        hit = False
        for bet in bets:
            if bet['combo'] == race['actual_combo'] and race['payout']:
                # 的中！
                hit = True
                race_payout = (bet_per_point / 100) * race['payout']
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

        # ドローダウン計算
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
    print("複数点買いパターン分析")
    print("=" * 120)
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 戦略B対象レースを取得
    print("戦略B対象レースを取得中...")
    races = get_strategy_b_races(cursor)
    print(f"対象レース数: {len(races)}")
    print()

    # 各パターンを評価
    patterns = [
        ('現行1点買い', pattern_single, 300),
        ('A: 1着軸流し(4点)', lambda r: pattern_a_axis_flow(r, 4), 400),
        ('A: 1着軸流し(6点)', lambda r: pattern_a_axis_flow(r, 6), 600),
        ('B: 1-2着軸(3点)', lambda r: pattern_b_12_axis(r, 3), 300),
        ('B: 1-2着軸(4点)', lambda r: pattern_b_12_axis(r, 4), 400),
        ('C: Top4 BOX(6点)', lambda r: pattern_c_top4_box(r, 6), 600),
        ('C: Top4 BOX(12点)', lambda r: pattern_c_top4_box(r, 12), 1200),
        ('D: オッズ20-50(4点)', lambda r: pattern_d_odds_range(r, 20, 50, 4), 400),
        ('E: 1-2軸+2-1軸', pattern_e_12_and_21, 600),
        ('F: Top3流し(6点)', pattern_f_top3_flow, 600),
        ('G: 1着軸-2,3,4位(6点)', pattern_g_1st_axis_top3, 600),
    ]

    results = []

    print("=" * 120)
    print("パターン別検証結果")
    print("=" * 120)
    print()
    print(f"{'パターン':<25} {'レース':<8} {'平均点数':<8} {'的中':<6} {'的中率':<8} {'投資':<12} {'払戻':<12} {'収支':<14} {'ROI':<8} {'MaxDD':<10}")
    print("-" * 120)

    for name, func, budget in patterns:
        stats = evaluate_pattern(races, func, name, budget)

        if stats['races'] == 0:
            continue

        avg_bets = stats['bets'] / stats['races']
        hit_rate = (stats['hits'] / stats['races'] * 100) if stats['races'] > 0 else 0
        profit = stats['payout'] - stats['investment']
        roi = (stats['payout'] / stats['investment'] * 100) if stats['investment'] > 0 else 0

        results.append({
            'name': name,
            'races': stats['races'],
            'avg_bets': avg_bets,
            'hits': stats['hits'],
            'hit_rate': hit_rate,
            'investment': stats['investment'],
            'payout': stats['payout'],
            'profit': profit,
            'roi': roi,
            'max_drawdown': stats['max_drawdown'],
            'details': stats.get('hit_details', []),
        })

        print(f"{name:<25} {stats['races']:<8} {avg_bets:<8.1f} {stats['hits']:<6} {hit_rate:<8.1f}% "
              f"{stats['investment']:>10,.0f}円 {stats['payout']:>10,.0f}円 {profit:>+12,.0f}円 {roi:>6.1f}% {stats['max_drawdown']:>8,.0f}円")

    # 最適パターンの特定
    print()
    print("=" * 120)
    print("収支ランキング（上位5パターン）")
    print("=" * 120)

    sorted_by_profit = sorted(results, key=lambda x: x['profit'], reverse=True)
    for i, r in enumerate(sorted_by_profit[:5], 1):
        print(f"{i}位: {r['name']}")
        print(f"    収支: {r['profit']:+,.0f}円, ROI: {r['roi']:.1f}%, 的中率: {r['hit_rate']:.1f}%")
        print(f"    投資: {r['investment']:,.0f}円, 払戻: {r['payout']:,.0f}円")
        print()

    # 現行戦略との比較
    print("=" * 120)
    print("現行戦略（1点買い）との比較")
    print("=" * 120)

    baseline = next((r for r in results if '現行' in r['name']), None)
    if baseline:
        print(f"現行戦略: 収支 {baseline['profit']:+,.0f}円, ROI {baseline['roi']:.1f}%, 的中率 {baseline['hit_rate']:.1f}%")
        print()

        for r in sorted_by_profit[:5]:
            if '現行' not in r['name']:
                diff_profit = r['profit'] - baseline['profit']
                diff_roi = r['roi'] - baseline['roi']
                diff_hit = r['hit_rate'] - baseline['hit_rate']

                print(f"{r['name']}:")
                print(f"    収支差: {diff_profit:+,.0f}円 ({'+' if diff_profit >= 0 else ''}{diff_profit/max(1, abs(baseline['profit']))*100:.1f}%)")
                print(f"    ROI差: {diff_roi:+.1f}ポイント")
                print(f"    的中率差: {diff_hit:+.1f}ポイント")
                print()

    # 条件別の詳細分析
    print("=" * 120)
    print("条件別×パターン別詳細分析")
    print("=" * 120)

    # 信頼度別
    for conf in ['C', 'D']:
        conf_races = [r for r in races if r['confidence'] == conf]
        print(f"\n【信頼度{conf}】（{len(conf_races)}レース）")
        print("-" * 100)

        for name, func, budget in patterns[:6]:  # 上位6パターンのみ
            stats = evaluate_pattern(conf_races, func, name, budget)
            if stats['races'] > 0:
                hit_rate = stats['hits'] / stats['races'] * 100
                profit = stats['payout'] - stats['investment']
                roi = stats['payout'] / stats['investment'] * 100 if stats['investment'] > 0 else 0
                print(f"  {name:<25}: 的中{stats['hits']:>2}/{stats['races']:<3} ({hit_rate:>5.1f}%) 収支{profit:>+10,.0f}円 ROI{roi:>6.1f}%")

    conn.close()

    print()
    print("=" * 120)
    print("分析完了")
    print("=" * 120)

    return results


if __name__ == '__main__':
    main()
