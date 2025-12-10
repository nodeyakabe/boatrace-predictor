# -*- coding: utf-8 -*-
"""
2連単戦略の最適化バックテスト
払戻レンジ別に収支を分析し、最適な条件を探る
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DATABASE_PATH


def run_exacta_optimization():
    """2連単戦略の最適化"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("2連単戦略 最適化バックテスト")
    print("=" * 80)

    # 信頼度・級別・払戻レンジ別に集計
    stats = defaultdict(lambda: {'count': 0, 'hits': 0, 'bet': 0, 'win': 0})

    # レースデータ取得
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2025-12-01'
          AND rp.confidence IN ('C', 'D')
          AND rp.prediction_type = 'advance'
          AND rp.rank_prediction = 1
    ''')
    races = cursor.fetchall()

    for race_id, race_date in races:
        # 予測取得
        cursor.execute('''
            SELECT pit_number, confidence FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction LIMIT 2
        ''', (race_id,))
        preds = cursor.fetchall()
        if len(preds) < 2:
            continue

        pred_1st, confidence = preds[0]
        pred_2nd = preds[1][0]
        pred_exacta = f"{pred_1st}-{pred_2nd}"

        # 1コース級別
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1_row = cursor.fetchone()
        c1_rank = c1_row[0] if c1_row else 'B1'

        # 結果取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND rank IN ('1', '2')
            ORDER BY CAST(rank AS INTEGER)
        ''', (race_id,))
        results = [row[0] for row in cursor.fetchall()]
        if len(results) < 2:
            continue

        actual_exacta = f"{results[0]}-{results[1]}"

        # 払戻取得
        cursor.execute('SELECT bet_type, amount FROM payouts WHERE race_id = ?', (race_id,))
        payouts = {row[0]: row[1] for row in cursor.fetchall()}
        exacta_payout = payouts.get('exacta', 0)

        # 的中判定
        is_hit = (pred_exacta == actual_exacta)

        # 払戻レンジ判定（的中時の実際の払戻金額）
        payout_ranges = [
            ('0-500', 0, 500),
            ('500-1000', 500, 1000),
            ('1000-1500', 1000, 1500),
            ('1500-2000', 1500, 2000),
            ('2000-3000', 2000, 3000),
            ('3000+', 3000, 99999),
        ]

        # 信頼度・級別ごとに全レースを記録
        key_all = (confidence, c1_rank, 'all')
        stats[key_all]['count'] += 1
        stats[key_all]['bet'] += 100
        if is_hit:
            stats[key_all]['hits'] += 1
            stats[key_all]['win'] += exacta_payout

        # 的中時のみ払戻レンジ別に記録
        if is_hit and exacta_payout > 0:
            for range_name, min_p, max_p in payout_ranges:
                if min_p <= exacta_payout < max_p:
                    key = (confidence, c1_rank, range_name)
                    # この的中が該当レンジに入っていた
                    stats[key]['hits'] += 1
                    stats[key]['win'] += exacta_payout
                    break

    conn.close()

    # 結果表示
    print("\n" + "=" * 80)
    print("【信頼度 × 1C級別 × 2連単成績】")
    print("=" * 80)
    print(f"{'信頼度':>5} {'1C級':>5} {'件数':>8} {'的中':>6} {'的中率':>8} {'回収率':>8}")
    print("-" * 55)

    for conf in ['C', 'D']:
        for rank in ['A1', 'A2', 'B1', 'B2']:
            key = (conf, rank, 'all')
            s = stats.get(key, {'count': 0, 'hits': 0, 'bet': 0, 'win': 0})
            if s['count'] < 10:
                continue
            hit_rate = s['hits'] / s['count'] * 100
            roi = s['win'] / s['bet'] * 100 if s['bet'] > 0 else 0
            status = " [OK]" if roi >= 100 else ""
            print(f"{conf:>5} {rank:>5} {s['count']:>8} {s['hits']:>6} {hit_rate:>7.1f}% {roi:>7.1f}%{status}")
        print("-" * 55)

    # 的中時の払戻分布
    print("\n" + "=" * 80)
    print("【的中時の払戻金額分布】")
    print("=" * 80)

    for conf in ['C', 'D']:
        for rank in ['A1', 'A2']:
            key_all = (conf, rank, 'all')
            s_all = stats.get(key_all, {'count': 0, 'hits': 0, 'bet': 0, 'win': 0})
            if s_all['hits'] < 5:
                continue

            print(f"\n{conf} × {rank}:")
            print(f"  全体: {s_all['count']}件中 {s_all['hits']}的中 ({s_all['hits']/s_all['count']*100:.1f}%) ROI={s_all['win']/s_all['bet']*100:.1f}%")

            for range_name in ['0-500', '500-1000', '1000-1500', '1500-2000', '2000-3000', '3000+']:
                key = (conf, rank, range_name)
                s = stats.get(key, {'hits': 0, 'win': 0})
                if s['hits'] > 0:
                    avg_payout = s['win'] / s['hits']
                    print(f"    {range_name}円: {s['hits']}件 (平均{avg_payout:.0f}円)")

    # 推奨条件
    print("\n" + "=" * 80)
    print("【2連単 推奨条件】")
    print("=" * 80)

    best_conditions = []
    for conf in ['C', 'D']:
        for rank in ['A1', 'A2']:
            key = (conf, rank, 'all')
            s = stats.get(key, {'count': 0, 'hits': 0, 'bet': 0, 'win': 0})
            if s['count'] >= 50 and s['bet'] > 0:
                roi = s['win'] / s['bet'] * 100
                hit_rate = s['hits'] / s['count'] * 100
                if roi >= 100:
                    best_conditions.append({
                        'conf': conf,
                        'rank': rank,
                        'count': s['count'],
                        'hit_rate': hit_rate,
                        'roi': roi
                    })

    if best_conditions:
        for bc in sorted(best_conditions, key=lambda x: -x['roi']):
            print(f"  {bc['conf']} × {bc['rank']}: サンプル{bc['count']}件, 的中率{bc['hit_rate']:.1f}%, ROI {bc['roi']:.1f}%")
    else:
        print("  収益条件が見つかりませんでした")


if __name__ == "__main__":
    run_exacta_optimization()
