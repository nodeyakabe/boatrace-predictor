# -*- coding: utf-8 -*-
"""
P-1（前付け常習者フィルター）効果検証

ベースライン（ROI 167.0%）に対して、P-1フィルター適用時の効果を測定
"""
import sys
import sqlite3
import json
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def load_forward_movers():
    """前付け常習者リストを読み込む"""
    path = ROOT_DIR / "config" / "forward_movers.json"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(str(rn) for rn in data.get('racer_numbers', []))
    except:
        return set()


def main():
    db_path = ROOT_DIR / 'data' / 'boatrace.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()
    forward_movers = load_forward_movers()

    print("=" * 100)
    print("P-1（前付け常習者フィルター）効果検証")
    print("=" * 100)
    print(f"前付け常習者リスト: {len(forward_movers)}名")
    print(f"対象者: {sorted(forward_movers)}")
    print()

    # 2025年1月〜11月のレースを取得（ベースラインと同じ期間）
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-11-30'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    # フィルターなし（ベースライン）
    baseline = {'purchase': 0, 'hit': 0, 'bet': 0, 'payout': 0}
    # フィルターあり（P-1適用）
    filtered = {'purchase': 0, 'hit': 0, 'bet': 0, 'payout': 0}
    # 除外されたレース
    excluded_races = []

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0
        race_date = race['race_date']

        # 1コース級別を取得
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # 出走選手番号を取得
        cursor.execute('SELECT racer_number FROM entries WHERE race_id = ?', (race_id,))
        racer_numbers = [str(row['racer_number']) for row in cursor.fetchall()]

        # 前付け常習者がいるかチェック
        has_forward_mover = bool(set(racer_numbers) & forward_movers)
        matched_movers = set(racer_numbers) & forward_movers

        # 予測情報を取得（直前情報 = before）
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

        # 信頼度A, Bは除外
        if confidence in ['A', 'B']:
            continue

        # 予測トップ3
        top3 = [p['pit_number'] for p in preds[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

        # オッズ取得
        cursor.execute(
            'SELECT combination, odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
            (race_id, combo))
        odds_row = cursor.fetchone()

        if not odds_row:
            continue

        odds = odds_row['odds']

        # bet_target_evaluatorで購入判定
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

        # ★購入対象★
        bet_amount = result.bet_amount

        # 実際の結果取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        is_hit = False
        payout_amount = 0

        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

            if combo == actual_combo:
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    payout_amount = (bet_amount / 100) * payout_row['amount']
                    is_hit = True

        # ベースラインに加算
        baseline['purchase'] += 1
        baseline['bet'] += bet_amount
        if is_hit:
            baseline['hit'] += 1
            baseline['payout'] += payout_amount

        # P-1フィルター適用（前付け常習者なしのレースのみ）
        if not has_forward_mover:
            filtered['purchase'] += 1
            filtered['bet'] += bet_amount
            if is_hit:
                filtered['hit'] += 1
                filtered['payout'] += payout_amount
        else:
            excluded_races.append({
                'date': race_date,
                'venue': venue_code,
                'movers': list(matched_movers),
                'combo': combo,
                'hit': is_hit,
                'payout': payout_amount if is_hit else 0
            })

    conn.close()

    # 結果表示
    print("=" * 100)
    print("結果比較")
    print("=" * 100)

    baseline_roi = baseline['payout'] / baseline['bet'] * 100 if baseline['bet'] > 0 else 0
    baseline_hit_rate = baseline['hit'] / baseline['purchase'] * 100 if baseline['purchase'] > 0 else 0
    baseline_profit = baseline['payout'] - baseline['bet']

    filtered_roi = filtered['payout'] / filtered['bet'] * 100 if filtered['bet'] > 0 else 0
    filtered_hit_rate = filtered['hit'] / filtered['purchase'] * 100 if filtered['purchase'] > 0 else 0
    filtered_profit = filtered['payout'] - filtered['bet']

    diff_roi = filtered_roi - baseline_roi
    diff_profit = filtered_profit - baseline_profit

    print(f"\n{'指標':<20} {'ベースライン':>15} {'P-1適用':>15} {'差分':>15}")
    print("-" * 70)
    print(f"{'購入レース数':<20} {baseline['purchase']:>15,} {filtered['purchase']:>15,} {filtered['purchase'] - baseline['purchase']:>+15,}")
    print(f"{'的中数':<20} {baseline['hit']:>15,} {filtered['hit']:>15,} {filtered['hit'] - baseline['hit']:>+15,}")
    print(f"{'的中率':<20} {baseline_hit_rate:>14.2f}% {filtered_hit_rate:>14.2f}% {filtered_hit_rate - baseline_hit_rate:>+14.2f}%")
    print(f"{'投資額':<20} {baseline['bet']:>14,.0f}円 {filtered['bet']:>14,.0f}円 {filtered['bet'] - baseline['bet']:>+14,.0f}円")
    print(f"{'払戻額':<20} {baseline['payout']:>14,.0f}円 {filtered['payout']:>14,.0f}円 {filtered['payout'] - baseline['payout']:>+14,.0f}円")
    print(f"{'収支':<20} {baseline_profit:>+14,.0f}円 {filtered_profit:>+14,.0f}円 {diff_profit:>+14,.0f}円")
    print(f"{'ROI':<20} {baseline_roi:>14.1f}% {filtered_roi:>14.1f}% {diff_roi:>+14.1f}%")

    print(f"\n除外されたレース: {len(excluded_races)}件")

    # 除外レースの的中分析
    excluded_hits = [r for r in excluded_races if r['hit']]
    excluded_payout = sum(r['payout'] for r in excluded_hits)

    print(f"  除外レース内の的中: {len(excluded_hits)}件")
    print(f"  除外レース内の払戻: {excluded_payout:,.0f}円")

    # 判定
    print("\n" + "=" * 100)
    print("判定")
    print("=" * 100)

    if diff_profit > 10000:
        print(f"[プラス効果] P-1フィルターにより収支が{diff_profit:+,.0f}円改善")
    elif diff_profit > -10000:
        print(f"[ほぼ変化なし] P-1フィルターの影響は軽微（{diff_profit:+,.0f}円）")
    else:
        print(f"[マイナス効果] P-1フィルターにより収支が{diff_profit:+,.0f}円悪化")

    # 除外レース詳細（的中したものを表示）
    if excluded_hits:
        print(f"\n除外された的中レース詳細:")
        for r in excluded_hits:
            print(f"  {r['date']} {r['venue']}場 | 前付け: {r['movers']} | 払戻: {r['payout']:,.0f}円")


if __name__ == "__main__":
    main()
