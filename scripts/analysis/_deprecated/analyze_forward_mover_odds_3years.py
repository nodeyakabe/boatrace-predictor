# -*- coding: utf-8 -*-
"""
前付けレース × オッズ帯分析（3年分: 2023-2025）

サンプル数を増やして統計的信頼性を高める
"""
import sys
import sqlite3
import io
import json
from pathlib import Path
from collections import defaultdict
import math

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config.feature_flags as ff
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def load_forward_movers():
    path = ROOT_DIR / "config" / "forward_movers.json"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(str(rn) for rn in data.get('racer_numbers', []))
    except:
        return set()


def z_test_proportion(n1, p1, n2, p2):
    """2標本比率のZ検定"""
    if n1 == 0 or n2 == 0:
        return 0, 1.0

    p_pool = (n1 * p1 + n2 * p2) / (n1 + n2)
    if p_pool == 0 or p_pool == 1:
        return 0, 1.0

    se = math.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
    if se == 0:
        return 0, 1.0

    z = (p1 - p2) / se
    # 両側検定のp値（近似）
    p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return z, p_value


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    forward_movers = load_forward_movers()

    ff.FEATURE_FLAGS['ab_rank_special_betting'] = True
    evaluator = BetTargetEvaluator()

    print("=" * 120)
    print("前付けレース × オッズ帯分析（3年分: 2023-2025）")
    print("=" * 120)
    print()

    # 3年分のデータ（2023-2025）
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date
        FROM races r
        WHERE r.race_date >= '2023-01-01' AND r.race_date <= '2025-11-30'
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
    ''')
    races = cursor.fetchall()

    print(f"対象レース数: {len(races):,}件（2023年1月〜2025年11月）")
    print()

    # 統計収集
    forward_by_odds = defaultdict(lambda: {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0})
    no_forward_by_odds = defaultdict(lambda: {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0})

    # 年別統計も収集
    by_year = defaultdict(lambda: defaultdict(lambda: {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}))

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0
        year = race['race_date'][:4]

        # 前付け常習者チェック
        cursor.execute('SELECT racer_number FROM entries WHERE race_id = ?', (race_id,))
        racer_numbers = [str(row['racer_number']) for row in cursor.fetchall()]
        has_forward = bool(set(racer_numbers) & forward_movers)

        # 予測取得
        cursor.execute('''
            SELECT pit_number, confidence, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY total_score DESC
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']
        top3 = [p['pit_number'] for p in preds[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

        # 1コース級別
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # オッズ
        cursor.execute(
            'SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
            (race_id, combo))
        odds_row = cursor.fetchone()
        if not odds_row:
            continue

        odds = odds_row['odds']

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

        if result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            continue

        # オッズ帯
        if odds < 10:
            band = "0-10"
        elif odds < 20:
            band = "10-20"
        elif odds < 30:
            band = "20-30"
        elif odds < 50:
            band = "30-50"
        elif odds < 100:
            band = "50-100"
        else:
            band = "100+"

        bet_amount = result.bet_amount
        stats = forward_by_odds[band] if has_forward else no_forward_by_odds[band]
        stats['target'] += 1
        stats['bet'] += bet_amount

        # 年別
        year_key = f"{year}_forward" if has_forward else f"{year}_no_forward"
        by_year[band][year_key]['target'] += 1
        by_year[band][year_key]['bet'] += bet_amount

        # 的中判定
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        actual_results = cursor.fetchall()

        if len(actual_results) >= 3:
            actual_combo = f"{actual_results[0]['pit_number']}-{actual_results[1]['pit_number']}-{actual_results[2]['pit_number']}"

            if combo == actual_combo:
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    payout = (bet_amount / 100) * payout_row['amount']
                    stats['hit'] += 1
                    stats['payout'] += payout
                    by_year[band][year_key]['hit'] += 1
                    by_year[band][year_key]['payout'] += payout

    conn.close()

    # 結果表示
    bands = ["0-10", "10-20", "20-30", "30-50", "50-100", "100+"]

    print("=" * 120)
    print("【前付けあり - 購入対象のみ】3年分")
    print("=" * 120)
    print(f"{'オッズ帯':<10} {'購入数':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>15} {'判定':<10}")
    print("-" * 80)

    total_forward = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}
    for band in bands:
        s = forward_by_odds[band]
        if s['target'] == 0:
            continue
        total_forward['target'] += s['target']
        total_forward['hit'] += s['hit']
        total_forward['bet'] += s['bet']
        total_forward['payout'] += s['payout']

        roi = s['payout'] / s['bet'] * 100 if s['bet'] > 0 else 0
        hit_rate = s['hit'] / s['target'] * 100 if s['target'] > 0 else 0
        profit = s['payout'] - s['bet']

        if roi >= 150:
            judgment = "✅ 超優良"
        elif roi >= 100:
            judgment = "✅ 黒字"
        elif roi >= 80:
            judgment = "🟡 微損"
        else:
            judgment = "❌ 赤字"

        print(f"{band:<10} {s['target']:>8} {s['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+14,.0f}円 {judgment}")

    print("-" * 80)
    roi = total_forward['payout'] / total_forward['bet'] * 100 if total_forward['bet'] > 0 else 0
    hit_rate = total_forward['hit'] / total_forward['target'] * 100 if total_forward['target'] > 0 else 0
    profit = total_forward['payout'] - total_forward['bet']
    print(f"{'合計':<10} {total_forward['target']:>8} {total_forward['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+14,.0f}円")

    print()
    print("=" * 120)
    print("【前付けなし - 購入対象のみ】3年分")
    print("=" * 120)
    print(f"{'オッズ帯':<10} {'購入数':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>15}")
    print("-" * 80)

    total_no_forward = {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0}
    for band in bands:
        s = no_forward_by_odds[band]
        if s['target'] == 0:
            continue
        total_no_forward['target'] += s['target']
        total_no_forward['hit'] += s['hit']
        total_no_forward['bet'] += s['bet']
        total_no_forward['payout'] += s['payout']

        roi = s['payout'] / s['bet'] * 100 if s['bet'] > 0 else 0
        hit_rate = s['hit'] / s['target'] * 100 if s['target'] > 0 else 0
        profit = s['payout'] - s['bet']
        print(f"{band:<10} {s['target']:>8} {s['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+14,.0f}円")

    print("-" * 80)
    roi = total_no_forward['payout'] / total_no_forward['bet'] * 100 if total_no_forward['bet'] > 0 else 0
    hit_rate = total_no_forward['hit'] / total_no_forward['target'] * 100 if total_no_forward['target'] > 0 else 0
    profit = total_no_forward['payout'] - total_no_forward['bet']
    print(f"{'合計':<10} {total_no_forward['target']:>8} {total_no_forward['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+14,.0f}円")

    # 年別推移
    print()
    print("=" * 120)
    print("【年別推移】前付けあり × オッズ帯")
    print("=" * 120)

    for band in bands:
        band_data = by_year[band]
        has_data = False
        for year in ['2023', '2024', '2025']:
            if band_data.get(f'{year}_forward', {}).get('target', 0) > 0:
                has_data = True
                break

        if not has_data:
            continue

        print(f"\n【{band}倍帯】")
        print(f"{'年':>6} {'購入数':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>12}")
        print("-" * 60)

        for year in ['2023', '2024', '2025']:
            s = band_data.get(f'{year}_forward', {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0})
            if s['target'] == 0:
                continue
            roi = s['payout'] / s['bet'] * 100 if s['bet'] > 0 else 0
            hit_rate = s['hit'] / s['target'] * 100 if s['target'] > 0 else 0
            profit = s['payout'] - s['bet']
            print(f"{year:>6} {s['target']:>8} {s['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+11,.0f}円")

    # 統計的検定
    print()
    print("=" * 120)
    print("【統計的検定】オッズ帯別の的中率比較（前付けあり vs なし）")
    print("=" * 120)
    print(f"\n{'オッズ帯':<10} {'前付けあり':>12} {'前付けなし':>12} {'Z統計量':>10} {'p値':>10} {'有意性':<10}")
    print("-" * 80)

    for band in bands:
        f = forward_by_odds[band]
        nf = no_forward_by_odds[band]

        if f['target'] == 0 or nf['target'] == 0:
            continue

        p1 = f['hit'] / f['target'] if f['target'] > 0 else 0
        p2 = nf['hit'] / nf['target'] if nf['target'] > 0 else 0

        z, p_value = z_test_proportion(f['target'], p1, nf['target'], p2)

        significance = "有意" if p_value < 0.05 else "n.s."

        print(f"{band:<10} {f['hit']}/{f['target']:>5} ({p1*100:>5.2f}%) {nf['hit']}/{nf['target']:>5} ({p2*100:>5.2f}%) {z:>9.2f} {p_value:>9.4f} {significance}")

    # フィルターシミュレーション
    print()
    print("=" * 120)
    print("【フィルターシミュレーション】")
    print("=" * 120)

    # 現状
    total_all = {
        'target': total_forward['target'] + total_no_forward['target'],
        'hit': total_forward['hit'] + total_no_forward['hit'],
        'bet': total_forward['bet'] + total_no_forward['bet'],
        'payout': total_forward['payout'] + total_no_forward['payout'],
    }
    baseline_roi = total_all['payout'] / total_all['bet'] * 100 if total_all['bet'] > 0 else 0
    baseline_profit = total_all['payout'] - total_all['bet']

    print(f"\n現状: {total_all['target']:,}件, ROI {baseline_roi:.1f}%, 収支 {baseline_profit:+,.0f}円")

    # 各オッズ帯除外のシミュレーション
    print(f"\n{'除外条件':<30} {'購入数':>8} {'的中':>6} {'ROI':>10} {'収支':>15} {'ROI差':>10}")
    print("-" * 90)

    for band in bands:
        excluded = forward_by_odds[band]
        if excluded['target'] == 0:
            continue

        new_total = {
            'target': total_all['target'] - excluded['target'],
            'hit': total_all['hit'] - excluded['hit'],
            'bet': total_all['bet'] - excluded['bet'],
            'payout': total_all['payout'] - excluded['payout'],
        }
        new_roi = new_total['payout'] / new_total['bet'] * 100 if new_total['bet'] > 0 else 0
        new_profit = new_total['payout'] - new_total['bet']
        roi_diff = new_roi - baseline_roi

        excluded_profit = excluded['payout'] - excluded['bet']
        label = f"前付け×{band}倍帯除外 (n={excluded['target']}, {excluded_profit:+,.0f}円)"
        print(f"{label:<30} {new_total['target']:>8,} {new_total['hit']:>6} {new_roi:>9.1f}% {new_profit:>+14,.0f}円 {roi_diff:>+9.2f}pt")

    # 結論
    print()
    print("=" * 120)
    print("【結論】")
    print("=" * 120)

    # 赤字オッズ帯を特定
    red_bands = []
    for band in bands:
        s = forward_by_odds[band]
        if s['target'] > 0:
            profit = s['payout'] - s['bet']
            if profit < 0:
                red_bands.append((band, s['target'], profit))

    if red_bands:
        print("\n赤字のオッズ帯（前付けあり）:")
        for band, n, profit in red_bands:
            print(f"  - {band}倍帯: {n}件, 収支 {profit:,.0f}円")
    else:
        print("\n全オッズ帯で黒字（前付けあり）")

    # 推奨
    print("\n" + "=" * 120)


if __name__ == "__main__":
    main()
