# -*- coding: utf-8 -*-
"""
信頼度Bの詳細分析 - 鉄板レースの改善可能性を探る
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DATABASE_PATH


def analyze_confidence_b():
    """信頼度Bの詳細分析"""

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("信頼度Bの詳細分析 - 鉄板レースの改善可能性")
    print("=" * 80)

    # 1. 信頼度Bのレース一覧を取得
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date, rp.confidence
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2025-12-01'
          AND rp.confidence = 'B'
          AND rp.rank_prediction = 1
    ''')
    b_race_ids = [row[0] for row in cursor.fetchall()]
    print(f"\n信頼度Bのレース数: {len(b_race_ids)}")

    # 2. 各レースの予測、結果、オッズを取得
    stats_by_pattern = defaultdict(lambda: {'count': 0, 'hits': 0, 'bet': 0, 'win': 0})
    stats_by_c1rank = defaultdict(lambda: {'count': 0, 'hits': 0, 'bet': 0, 'win': 0, 'odds_sum': 0})
    stats_by_odds_range = defaultdict(lambda: {'count': 0, 'hits': 0, 'bet': 0, 'win': 0})

    hit_odds_list = []  # 的中時のオッズを記録

    for race_id in b_race_ids:
        # 予測を取得
        cursor.execute('''
            SELECT pit_number FROM race_predictions
            WHERE race_id = ? AND confidence = 'B'
            ORDER BY rank_prediction LIMIT 3
        ''', (race_id,))
        preds = [row[0] for row in cursor.fetchall()]
        if len(preds) < 3:
            continue
        pred_combo = f'{preds[0]}-{preds[1]}-{preds[2]}'

        # 結果を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND rank IN ('1', '2', '3')
            ORDER BY CAST(rank AS INTEGER)
        ''', (race_id,))
        results = [row[0] for row in cursor.fetchall()]
        if len(results) < 3:
            continue
        result_combo = f'{results[0]}-{results[1]}-{results[2]}'

        # 1コース級別
        cursor.execute('''
            SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1
        ''', (race_id,))
        c1_row = cursor.fetchone()
        c1_rank = c1_row[0] if c1_row else 'B1'

        # オッズ
        cursor.execute('''
            SELECT combination, odds FROM trifecta_odds WHERE race_id = ?
        ''', (race_id,))
        odds_dict = {row[0]: row[1] for row in cursor.fetchall()}

        pred_odds = odds_dict.get(pred_combo, 0)
        result_odds = odds_dict.get(result_combo, 0)

        if pred_odds == 0:
            continue

        # オッズ範囲を決定
        if pred_odds < 10:
            odds_range = '0-10'
        elif pred_odds < 20:
            odds_range = '10-20'
        elif pred_odds < 30:
            odds_range = '20-30'
        elif pred_odds < 50:
            odds_range = '30-50'
        else:
            odds_range = '50+'

        is_hit = (pred_combo == result_combo)

        # パターン別集計
        key = (pred_combo, c1_rank)
        stats_by_pattern[key]['count'] += 1
        stats_by_pattern[key]['bet'] += 100
        if is_hit:
            stats_by_pattern[key]['hits'] += 1
            stats_by_pattern[key]['win'] += result_odds * 100

        # 1-2-3専用集計
        if pred_combo == '1-2-3':
            stats_by_c1rank[c1_rank]['count'] += 1
            stats_by_c1rank[c1_rank]['bet'] += 100
            stats_by_c1rank[c1_rank]['odds_sum'] += pred_odds
            if is_hit:
                stats_by_c1rank[c1_rank]['hits'] += 1
                stats_by_c1rank[c1_rank]['win'] += result_odds * 100
                hit_odds_list.append(result_odds)

            # オッズ範囲別
            stats_by_odds_range[(c1_rank, odds_range)]['count'] += 1
            stats_by_odds_range[(c1_rank, odds_range)]['bet'] += 100
            if is_hit:
                stats_by_odds_range[(c1_rank, odds_range)]['hits'] += 1
                stats_by_odds_range[(c1_rank, odds_range)]['win'] += result_odds * 100

    # 結果表示
    print("\n" + "=" * 80)
    print("【信頼度Bの予測パターン別 成績】")
    print("=" * 80)
    print(f"{'予測':>10} {'1C級':>5} {'件数':>6} {'的中':>5} {'的中率':>8} {'回収率':>8}")
    print("-" * 55)

    sorted_patterns = sorted(stats_by_pattern.items(), key=lambda x: -x[1]['count'])
    for (pred, c1_rank), stats in sorted_patterns[:15]:
        if stats['count'] < 5:
            continue
        hit_rate = stats['hits'] / stats['count'] * 100
        roi = stats['win'] / stats['bet'] * 100
        print(f"{pred:>10} {c1_rank:>5} {stats['count']:>6} {stats['hits']:>5} {hit_rate:>7.1f}% {roi:>7.1f}%")

    print("\n" + "=" * 80)
    print("【信頼度B × 1-2-3（鉄板）級別成績】")
    print("=" * 80)
    print(f"{'1C級':>5} {'件数':>6} {'的中':>5} {'的中率':>8} {'平均ｵｯｽﾞ':>10} {'回収率':>8}")
    print("-" * 55)

    for c1_rank in ['A1', 'A2', 'B1', 'B2']:
        stats = stats_by_c1rank.get(c1_rank, {'count': 0, 'hits': 0, 'bet': 0, 'win': 0, 'odds_sum': 0})
        if stats['count'] == 0:
            continue
        hit_rate = stats['hits'] / stats['count'] * 100
        roi = stats['win'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
        avg_odds = stats['odds_sum'] / stats['count']
        print(f"{c1_rank:>5} {stats['count']:>6} {stats['hits']:>5} {hit_rate:>7.1f}% {avg_odds:>9.1f}倍 {roi:>7.1f}%")

    total = sum(s['count'] for s in stats_by_c1rank.values())
    total_hits = sum(s['hits'] for s in stats_by_c1rank.values())
    total_bet = sum(s['bet'] for s in stats_by_c1rank.values())
    total_win = sum(s['win'] for s in stats_by_c1rank.values())
    if total > 0:
        print("-" * 55)
        print(f"{'合計':>5} {total:>6} {total_hits:>5} {total_hits/total*100:>7.1f}% {'':>10} {total_win/total_bet*100:>7.1f}%")

    print("\n" + "=" * 80)
    print("【信頼度B × 1-2-3 × オッズ範囲別成績】")
    print("=" * 80)
    print(f"{'1C級':>5} {'ｵｯｽﾞ範囲':>10} {'件数':>6} {'的中':>5} {'的中率':>8} {'回収率':>8}")
    print("-" * 60)

    for c1_rank in ['A1', 'A2']:
        for odds_range in ['0-10', '10-20', '20-30', '30-50', '50+']:
            key = (c1_rank, odds_range)
            stats = stats_by_odds_range.get(key, {'count': 0, 'hits': 0, 'bet': 0, 'win': 0})
            if stats['count'] < 3:
                continue
            hit_rate = stats['hits'] / stats['count'] * 100
            roi = stats['win'] / stats['bet'] * 100 if stats['bet'] > 0 else 0
            status = " [OK]" if roi >= 100 else ""
            print(f"{c1_rank:>5} {odds_range:>10} {stats['count']:>6} {stats['hits']:>5} {hit_rate:>7.1f}% {roi:>7.1f}%{status}")
        print("-" * 60)

    # 的中時のオッズ分布
    if hit_odds_list:
        print("\n" + "=" * 80)
        print("【信頼度B × 1-2-3 的中時のオッズ分布】")
        print("=" * 80)
        hit_odds_list.sort()
        print(f"  最小: {min(hit_odds_list):.1f}倍")
        print(f"  最大: {max(hit_odds_list):.1f}倍")
        print(f"  平均: {sum(hit_odds_list)/len(hit_odds_list):.1f}倍")
        print(f"  中央値: {hit_odds_list[len(hit_odds_list)//2]:.1f}倍")

    conn.close()

    # 改善提案
    print("\n" + "=" * 80)
    print("【分析結果と改善提案】")
    print("=" * 80)
    print("""
現状の課題:
  - 信頼度Bは「1-2-3」予測が大半で、低オッズ（平均5-10倍）
  - 的中率は高いが、回収率100%未満になりがち

改善の方向性:
  1. 【オッズフィルター】信頼度B × 1-2-3 × 高オッズ（20倍以上）のみ狙う
     → 的中時に高配当を得られる条件を絞る

  2. 【2着3着の改良】1着は1号艇固定で、2着3着を変える
     → 例: 1-2-3 → 1-3-2 や 1-2-4 に変更する条件を探す

  3. 【2連単/2連複の活用】3連単より的中率を上げつつ配当確保
     → 信頼度Bの高的中率を活かす
""")


if __name__ == "__main__":
    analyze_confidence_b()
