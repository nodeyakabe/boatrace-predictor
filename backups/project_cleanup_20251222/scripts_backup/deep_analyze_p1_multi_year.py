# -*- coding: utf-8 -*-
"""
P-1パラドックス検証（2024年+2025年の2年分）

サンプルサイズを拡大して統計的信頼性を確保
"""
import sys
import sqlite3
import io
import json
from pathlib import Path
from collections import defaultdict

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


def analyze_year(cursor, evaluator, forward_movers, year_start, year_end, year_label):
    """指定年のP-1効果を分析"""

    cursor.execute('''
        SELECT r.id as race_id, r.venue_code
        FROM races r
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND EXISTS (SELECT 1 FROM race_predictions WHERE race_id = r.id AND prediction_type = 'before')
          AND EXISTS (SELECT 1 FROM results WHERE race_id = r.id AND is_invalid = 0)
    ''', (year_start, year_end))
    races = cursor.fetchall()

    stats = {
        'forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
        'no_forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
    }

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0

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

        bet_amount = result.bet_amount
        category = 'forward' if has_forward else 'no_forward'
        stats[category]['target'] += 1
        stats[category]['bet'] += bet_amount

        # 的中判定
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

            if combo == actual_combo:
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    payout = (bet_amount / 100) * payout_row['amount']
                    stats[category]['hit'] += 1
                    stats[category]['payout'] += payout

    return stats


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    forward_movers = load_forward_movers()

    # ab_rank ON設定
    ff.FEATURE_FLAGS['ab_rank_special_betting'] = True
    evaluator = BetTargetEvaluator()

    print("=" * 100)
    print("P-1パラドックス検証（2年分: 2024年 + 2025年）")
    print("=" * 100)
    print(f"前付け常習者リスト: {len(forward_movers)}名")
    print()

    # 年別分析
    years_data = {}
    years_data['2024'] = analyze_year(cursor, evaluator, forward_movers, '2024-01-01', '2024-12-31', '2024年')
    years_data['2025'] = analyze_year(cursor, evaluator, forward_movers, '2025-01-01', '2025-11-30', '2025年')

    # 合計
    combined = {
        'forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
        'no_forward': {'target': 0, 'hit': 0, 'bet': 0, 'payout': 0},
    }
    for year, data in years_data.items():
        for cat in ['forward', 'no_forward']:
            for key in ['target', 'hit', 'bet', 'payout']:
                combined[cat][key] += data[cat][key]

    conn.close()

    # 結果表示
    def calc_stats(s):
        roi = s['payout'] / s['bet'] * 100 if s['bet'] > 0 else 0
        hit_rate = s['hit'] / s['target'] * 100 if s['target'] > 0 else 0
        profit = s['payout'] - s['bet']
        return roi, hit_rate, profit

    print("=" * 100)
    print("年別結果")
    print("=" * 100)

    for year in ['2024', '2025']:
        data = years_data[year]
        print(f"\n【{year}年】")
        print(f"{'カテゴリ':<15} {'購入数':>8} {'的中数':>6} {'的中率':>8} {'ROI':>10} {'収支':>15}")
        print("-" * 70)

        for cat, label in [('forward', '前付けあり'), ('no_forward', '前付けなし')]:
            s = data[cat]
            roi, hit_rate, profit = calc_stats(s)
            print(f"{label:<15} {s['target']:>8,} {s['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+14,.0f}円")

        # 差分
        f_roi, _, f_profit = calc_stats(data['forward'])
        n_roi, _, n_profit = calc_stats(data['no_forward'])
        print(f"{'差分':<15} {'-':>8} {'-':>6} {'-':>8} {f_roi - n_roi:>+9.1f}pt {f_profit - n_profit:>+14,.0f}円")

    print()
    print("=" * 100)
    print("2年間合計（統計的信頼性向上）")
    print("=" * 100)
    print(f"\n{'カテゴリ':<15} {'購入数':>8} {'的中数':>6} {'的中率':>8} {'ROI':>10} {'収支':>15}")
    print("-" * 70)

    for cat, label in [('forward', '前付けあり'), ('no_forward', '前付けなし')]:
        s = combined[cat]
        roi, hit_rate, profit = calc_stats(s)
        print(f"{label:<15} {s['target']:>8,} {s['hit']:>6} {hit_rate:>7.2f}% {roi:>9.1f}% {profit:>+14,.0f}円")

    f_roi, f_hit_rate, f_profit = calc_stats(combined['forward'])
    n_roi, n_hit_rate, n_profit = calc_stats(combined['no_forward'])

    print("-" * 70)
    print(f"{'差分':<15} {'-':>8} {'-':>6} {f_hit_rate - n_hit_rate:>+7.2f}% {f_roi - n_roi:>+9.1f}pt {f_profit - n_profit:>+14,.0f}円")

    print()
    print("=" * 100)
    print("統計的検定（Z検定）")
    print("=" * 100)

    n1 = combined['forward']['target']
    n2 = combined['no_forward']['target']
    p1 = combined['forward']['hit'] / n1 if n1 > 0 else 0
    p2 = combined['no_forward']['hit'] / n2 if n2 > 0 else 0

    # プールされた比率
    p_pool = (combined['forward']['hit'] + combined['no_forward']['hit']) / (n1 + n2)

    # 標準誤差
    import math
    se = math.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2)) if n1 > 0 and n2 > 0 else 1

    # Z統計量
    z = (p1 - p2) / se if se > 0 else 0

    print(f"\n前付けあり: n={n1}, 的中率={p1*100:.2f}%")
    print(f"前付けなし: n={n2}, 的中率={p2*100:.2f}%")
    print(f"Z統計量: {z:.3f}")

    if abs(z) < 1.96:
        print("判定: 的中率に統計的有意差なし（p > 0.05）")
    else:
        print("判定: 的中率に統計的有意差あり（p < 0.05）")

    print()
    print("=" * 100)
    print("結論")
    print("=" * 100)

    if f_roi > n_roi:
        diff = f_roi - n_roi
        print(f"\n前付けありレースの方がROIが高い（+{diff:.1f}pt）")
        print("\n【考察】")
        print("1. 前付けでレースが荒れる → オッズ上昇 → 的中時の払戻増加")
        print("2. 市場が前付けリスクを過大評価 → 実際より高いオッズ")
        print("3. 我々の予測モデルが前付け影響を適切に織り込んでいる")
        print("\n【推奨】")
        print("P-1フィルターは無効のまま維持（高収益レースを除外しないため）")
    else:
        diff = n_roi - f_roi
        print(f"\n前付けなしレースの方がROIが高い（+{diff:.1f}pt）")
        print("\n【推奨】")
        print("P-1フィルターを有効化すべき（ただしab_rank依存に注意）")


if __name__ == "__main__":
    main()
