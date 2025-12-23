# -*- coding: utf-8 -*-
"""
Phase 3: 2024年advance予測データでの検証

before予測データが少ないため、advance予測データを使用して
コース別ROIパターンが2024年でも見られるか検証
"""
import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def analyze_2024_advance():
    """2024年advance予測データの分析"""
    db_path = ROOT_DIR / 'data' / 'boatrace.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 2024年のレースを取得（advanceデータ）
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

        # 予測情報を取得（advance）
        cursor.execute('''
            SELECT pit_number, confidence, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY total_score DESC
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']

        # 信頼度A, Bは除外（戦略B条件）
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

        # 戦略B条件（簡易版）
        # 信頼度C/D、1コースA1、オッズ20-60倍
        is_target = False

        if c1_rank == 'A1' and 20 <= odds <= 60:
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

        # オッズ帯
        if odds < 30:
            odds_band = '20-30'
        elif odds < 40:
            odds_band = '30-40'
        elif odds < 50:
            odds_band = '40-50'
        else:
            odds_band = '50-60'

        data.append({
            'race_id': race_id,
            'race_date': race_date,
            'venue_code': venue_code,
            'c1_rank': c1_rank,
            'confidence': confidence,
            'top_pred': top_pred,
            'combo': combo,
            'odds': odds,
            'odds_band': odds_band,
            'bet_amount': bet_amount,
            'is_hit': is_hit,
            'payout': payout,
        })

    conn.close()

    return data


def print_stats(data):
    """統計を計算"""
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
    print("Phase 3: 2024年advance予測データでの検証")
    print("=" * 100)
    print()
    print("目的: 2025年で発見した高ROI条件（特に3コース予測）が")
    print("      2024年でも有効かを検証し、過学習リスクを評価する")
    print()

    data = analyze_2024_advance()
    print(f"2024年 購入対象件数: {len(data)}件")
    print()

    if len(data) == 0:
        print("2024年のadvance予測データが不足しています。")
        return

    # 全体統計
    print("=" * 100)
    print("1. 2024年全体サマリー（advance予測）")
    print("=" * 100)
    total_stats = print_stats(data)
    print(f"  購入: {total_stats['count']}件")
    print(f"  的中: {total_stats['hit']}件 (的中率 {total_stats['hit_rate']:.2f}%)")
    print(f"  投資: {total_stats['bet']:,.0f}円")
    print(f"  払戻: {total_stats['payout']:,.0f}円")
    print(f"  収支: {total_stats['profit']:+,.0f}円")
    print(f"  ROI: {total_stats['roi']:.1f}%")
    print()

    # 信頼度別
    print("=" * 100)
    print("2. 信頼度別（2024年）")
    print("=" * 100)
    print()

    for conf in ['C', 'D']:
        filtered = [d for d in data if d['confidence'] == conf]
        stats = print_stats(filtered)
        if stats['count'] > 0:
            print(f"信頼度{conf}: {stats['count']}件, 的中{stats['hit']}件, 的中率{stats['hit_rate']:.2f}%, ROI {stats['roi']:.1f}%, 収支 {stats['profit']:+,.0f}円")

    print()

    # 予測コース別
    print("=" * 100)
    print("3. 予測コース別（2024年）")
    print("=" * 100)
    print()

    print(f"{'コース':<8} {'購入':<8} {'的中':<8} {'的中率':<10} {'収支':<14} {'ROI':<10}")
    print("-" * 70)

    course_stats_2024 = {}
    for course in range(1, 7):
        filtered = [d for d in data if d['top_pred'] == course]
        stats = print_stats(filtered)
        course_stats_2024[course] = stats

        if stats['count'] > 0:
            print(f"{course}コース    {stats['count']:<8} {stats['hit']:<8} {stats['hit_rate']:>7.2f}% {stats['profit']:>+13,.0f} {stats['roi']:>8.1f}%")

    print()

    # 2025年との比較テーブル
    print("=" * 100)
    print("4. 2024年 vs 2025年 コース別ROI比較")
    print("=" * 100)
    print()

    # 2025年データ（先の分析結果から）
    course_stats_2025 = {
        1: {'count': 502, 'roi': 131.2, 'profit': 47010},
        2: {'count': 137, 'roi': 140.7, 'profit': 16710},
        3: {'count': 132, 'roi': 348.4, 'profit': 98370},
        4: {'count': 44, 'roi': 108.6, 'profit': 1140},
        5: {'count': 13, 'roi': 208.5, 'profit': 4230},
        6: {'count': 5, 'roi': 0.0, 'profit': -1500},
    }

    print(f"{'コース':<8} | {'2024年件数':<10} {'2024年ROI':<12} | {'2025年件数':<10} {'2025年ROI':<12} | {'差分':<10}")
    print("-" * 90)

    for course in range(1, 7):
        s2024 = course_stats_2024.get(course, {})
        s2025 = course_stats_2025.get(course, {})

        c2024 = s2024.get('count', 0)
        r2024 = s2024.get('roi', 0)
        c2025 = s2025.get('count', 0)
        r2025 = s2025.get('roi', 0)
        diff = r2025 - r2024 if c2024 > 0 else '-'

        diff_str = f"{diff:+.1f}pt" if isinstance(diff, float) else diff
        print(f"{course}コース    | {c2024:<10} {r2024:>10.1f}% | {c2025:<10} {r2025:>10.1f}% | {diff_str}")

    print()

    # 信頼度 × 予測コース
    print("=" * 100)
    print("5. 信頼度 × 予測コース（2024年）")
    print("=" * 100)
    print()

    print(f"{'条件':<20} {'購入':<8} {'的中':<8} {'的中率':<10} {'収支':<14} {'ROI':<10}")
    print("-" * 80)

    cross_2024 = {}
    for conf in ['C', 'D']:
        for course in range(1, 7):
            filtered = [d for d in data if d['confidence'] == conf and d['top_pred'] == course]
            stats = print_stats(filtered)
            key = f"{conf} × {course}コース"
            cross_2024[key] = stats

            if stats['count'] >= 5:
                print(f"{key:<20} {stats['count']:<8} {stats['hit']:<8} {stats['hit_rate']:>7.2f}% {stats['profit']:>+13,.0f} {stats['roi']:>8.1f}%")

    print()

    # D × 3コースの2024年 vs 2025年比較
    print("=" * 100)
    print("6. 重要条件の年度比較")
    print("=" * 100)
    print()

    d3_2024 = cross_2024.get('D × 3コース', {'count': 0, 'roi': 0, 'profit': 0})
    d3_2025 = {'count': 72, 'roi': 505.6, 'profit': 87600}

    print("【D × 3コース】")
    print(f"  2024年: {d3_2024['count']}件, ROI {d3_2024['roi']:.1f}%, 収支 {d3_2024['profit']:+,.0f}円")
    print(f"  2025年: {d3_2025['count']}件, ROI {d3_2025['roi']:.1f}%, 収支 {d3_2025['profit']:+,.0f}円")

    if d3_2024['count'] > 0:
        diff = d3_2025['roi'] - d3_2024['roi']
        print(f"  差分: ROI {diff:+.1f}pt")

        if d3_2024['roi'] > 150:
            print()
            print("  ==> 2024年も高ROI。過学習リスク: 低")
        elif d3_2024['roi'] > 100:
            print()
            print("  ==> 2024年はROI > 100%だが2025年ほど高くない。")
            print("      過学習リスク: 中（一部はデータの偏りの可能性）")
        else:
            print()
            print("  ==> 2024年はROI < 100%。過学習リスク: 高")
            print("      2025年の結果は偶然の可能性あり")
    else:
        print()
        print("  ==> 2024年データ不足。検証不可")

    print()

    # オッズ帯別
    print("=" * 100)
    print("7. オッズ帯別（2024年）")
    print("=" * 100)
    print()

    print(f"{'オッズ帯':<12} {'購入':<8} {'的中':<8} {'的中率':<10} {'収支':<14} {'ROI':<10}")
    print("-" * 70)

    for band in ['20-30', '30-40', '40-50', '50-60']:
        filtered = [d for d in data if d['odds_band'] == band]
        stats = print_stats(filtered)

        if stats['count'] > 0:
            print(f"{band}倍       {stats['count']:<8} {stats['hit']:<8} {stats['hit_rate']:>7.2f}% {stats['profit']:>+13,.0f} {stats['roi']:>8.1f}%")

    print()

    # 結論
    print("=" * 100)
    print("8. 過学習リスク評価の結論")
    print("=" * 100)
    print()

    # 3コース予測の2024年ROI
    c3_2024 = course_stats_2024.get(3, {'count': 0, 'roi': 0})
    if c3_2024['count'] >= 30:
        if c3_2024['roi'] > 200:
            risk = "低"
            conclusion = "2024年も高ROI。3コース予測の優位性は一貫している可能性が高い。"
        elif c3_2024['roi'] > 100:
            risk = "中"
            conclusion = "2024年もROI > 100%だが、2025年ほど高くない。増額は慎重に。"
        else:
            risk = "高"
            conclusion = "2024年はROI < 100%。2025年の高ROIは過学習の可能性あり。"
    else:
        risk = "評価不能"
        conclusion = "2024年のサンプルサイズが不足。追加データ収集が必要。"

    print(f"3コース予測の過学習リスク: {risk}")
    print(f"結論: {conclusion}")
    print()

    # 6コース予測の評価
    c6_2024 = course_stats_2024.get(6, {'count': 0, 'roi': 0})
    print(f"6コース予測（2024年）: {c6_2024['count']}件, ROI {c6_2024['roi']:.1f}%")
    if c6_2024['count'] > 0 and c6_2024['roi'] < 100:
        print("  ==> 2024年でもROI低。6コース除外は妥当。")
    elif c6_2024['count'] > 0 and c6_2024['roi'] >= 100:
        print("  ==> 2024年ではROI正常。2025年の結果は一時的な偏りの可能性。")
    else:
        print("  ==> 2024年データ不足。2025年データのみで判断。")

    print()
    print("=" * 100)

    return {
        'data': data,
        'course_stats_2024': course_stats_2024,
        'cross_2024': cross_2024,
    }


if __name__ == '__main__':
    main()
