# -*- coding: utf-8 -*-
"""
Phase 3: 2024年データでの検証（過学習リスク確認）

2025年で発見した高ROI条件が、2024年でも有効かを検証
"""
import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def analyze_2024_data():
    """2024年データの分析"""
    db_path = ROOT_DIR / 'data' / 'boatrace.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 2024年のレースを取得（beforeデータがあるもの）
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2024-01-01' AND r.race_date <= '2024-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    data = []

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0
        race_date = race['race_date']

        # 1コース級別を取得
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

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

        top3 = [p['pit_number'] for p in preds[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"
        top_pred = top3[0]

        # オッズ取得
        cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                       (race_id, combo))
        odds_row = cursor.fetchone()

        if not odds_row:
            continue

        odds = odds_row['odds']

        # 簡易的な購入条件（戦略B条件に近似）
        # 信頼度C: オッズ20-50倍
        # 信頼度D: オッズ20-50倍
        # 1コースA1条件も適用
        is_target = False

        if confidence == 'C':
            if c1_rank == 'A1' and 30 <= odds <= 50:
                is_target = True
        elif confidence == 'D':
            if c1_rank == 'A1' and 20 <= odds <= 50:
                is_target = True

        if not is_target:
            continue

        bet_amount = 300

        # 実際の結果を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results_rows = cursor.fetchall()

        if len(results_rows) < 3:
            continue

        actual_combo = f"{results_rows[0]['pit_number']}-{results_rows[1]['pit_number']}-{results_rows[2]['pit_number']}"
        is_hit = (combo == actual_combo)

        # 払戻取得
        payout = 0
        if is_hit:
            cursor.execute('''
                SELECT amount FROM payouts
                WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
            ''', (race_id, actual_combo))
            payout_row = cursor.fetchone()
            if payout_row:
                payout = (bet_amount / 100) * payout_row['amount']

        data.append({
            'race_id': race_id,
            'race_date': race_date,
            'venue_code': venue_code,
            'c1_rank': c1_rank,
            'confidence': confidence,
            'top_pred': top_pred,
            'combo': combo,
            'odds': odds,
            'bet_amount': bet_amount,
            'is_hit': is_hit,
            'payout': payout,
        })

    conn.close()

    return data


def print_stats(data, label=""):
    """統計を表示"""
    if not data:
        return {'count': 0, 'hit': 0, 'bet': 0, 'payout': 0, 'roi': 0, 'hit_rate': 0, 'profit': 0}

    count = len(data)
    hit = sum(1 for d in data if d['is_hit'])
    bet = sum(d['bet_amount'] for d in data)
    payout = sum(d['payout'] for d in data)

    hit_rate = (hit / count * 100) if count > 0 else 0
    roi = (payout / bet * 100) if bet > 0 else 0
    profit = payout - bet

    return {
        'count': count,
        'hit': hit,
        'bet': bet,
        'payout': payout,
        'roi': roi,
        'hit_rate': hit_rate,
        'profit': profit
    }


def main():
    print("=" * 100)
    print("Phase 3: 2024年データでの検証（過学習リスク確認）")
    print("=" * 100)
    print()

    data = analyze_2024_data()
    print(f"2024年 購入対象件数: {len(data)}件")
    print()

    if len(data) == 0:
        print("2024年のbefore予測データが不足しています。")
        print("advance予測データで代替検証を行います。")
        return

    # 全体統計
    print("=" * 100)
    print("1. 2024年全体サマリー")
    print("=" * 100)
    total_stats = print_stats(data)
    print(f"  購入: {total_stats['count']}件")
    print(f"  的中: {total_stats['hit']}件 (的中率 {total_stats['hit_rate']:.2f}%)")
    print(f"  投資: {total_stats['bet']:,.0f}円")
    print(f"  払戻: {total_stats['payout']:,.0f}円")
    print(f"  収支: {total_stats['profit']:+,.0f}円")
    print(f"  ROI: {total_stats['roi']:.1f}%")
    print()

    # 予測コース別
    print("=" * 100)
    print("2. 予測コース別分析（2024年）")
    print("=" * 100)
    print()

    print(f"{'コース':<8} {'購入':<8} {'的中':<8} {'的中率':<10} {'収支':<14} {'ROI':<10}")
    print("-" * 70)

    for course in range(1, 7):
        filtered = [d for d in data if d['top_pred'] == course]
        stats = print_stats(filtered)

        if stats['count'] > 0:
            print(f"{course}コース    {stats['count']:<8} {stats['hit']:<8} {stats['hit_rate']:>7.2f}% {stats['profit']:>+13,.0f} {stats['roi']:>8.1f}%")

    print()

    # 信頼度 × 予測コース
    print("=" * 100)
    print("3. 信頼度 × 予測コース（2024年）")
    print("=" * 100)
    print()

    print(f"{'条件':<20} {'購入':<8} {'的中':<8} {'的中率':<10} {'収支':<14} {'ROI':<10}")
    print("-" * 80)

    for conf in ['C', 'D']:
        for course in range(1, 7):
            filtered = [d for d in data if d['confidence'] == conf and d['top_pred'] == course]
            stats = print_stats(filtered)

            if stats['count'] >= 3:
                print(f"{conf} × {course}コース      {stats['count']:<8} {stats['hit']:<8} {stats['hit_rate']:>7.2f}% {stats['profit']:>+13,.0f} {stats['roi']:>8.1f}%")

    print()

    # 2025年との比較
    print("=" * 100)
    print("4. 2025年との比較（3コース予測）")
    print("=" * 100)
    print()

    course3_data = [d for d in data if d['top_pred'] == 3]
    course3_stats = print_stats(course3_data)

    print("【3コース予測】")
    print(f"  2024年: {course3_stats['count']}件, ROI {course3_stats['roi']:.1f}%, 収支 {course3_stats['profit']:+,.0f}円")
    print(f"  2025年: 132件, ROI 348.4%, 収支 +98,370円")
    print()

    d3_data = [d for d in data if d['confidence'] == 'D' and d['top_pred'] == 3]
    d3_stats = print_stats(d3_data)

    print("【D × 3コース】")
    print(f"  2024年: {d3_stats['count']}件, ROI {d3_stats['roi']:.1f}%, 収支 {d3_stats['profit']:+,.0f}円")
    print(f"  2025年: 72件, ROI 505.6%, 収支 +87,600円")
    print()

    print("=" * 100)


if __name__ == '__main__':
    main()
