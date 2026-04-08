#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
月次OOS監視スクリプト

目的:
    2026年以降の実運用成績を月次で集計し、バックテストベースラインと比較する。
    2020-2025は「見てしまったデータ」のため唯一の真のOOSは2026年以降の実運用成績。

使用方法:
    # 2026年の月次成績を表示
    python scripts/analysis/monthly_oos_monitor.py --year 2026

    # 特定月のみ
    python scripts/analysis/monthly_oos_monitor.py --year 2026 --month 4

    # ベースラインJSONと比較（全体ROIの傾向確認）
    python scripts/analysis/monthly_oos_monitor.py --year 2026 --baseline data/baselines/v2.44.0.json

運用ルール（docs/guides/VALIDATION_WORKFLOW.md 参照）:
    - 月次: 記録のみ（件数少のため判断不要）
    - 半年（2026年10月末）: 全体ROI < 100% なら原因調査
    - 年次（2026年12月末）: 条件別退出判定
"""
import sys
import os
import io
import json
import sqlite3
import argparse
from datetime import datetime, date

# Windows コンソールの文字化け対策
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS


def get_monthly_results(year: int, month: int = None):
    """指定年（月）の実運用成績を集計"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    if month:
        start = f"{year}-{month:02d}-01"
        if month == 12:
            end = f"{year+1}-01-01"
        else:
            end = f"{year}-{month+1:02d}-01"
        months = [month]
    else:
        start = f"{year}-01-01"
        end = f"{year+1}-01-01"
        months = list(range(1, 13))

    results = {}

    for cond in STANDARD_BET_CONDITIONS:
        cid = cond['id']
        cname = cond['name']
        odds_min = cond.get('odds_min', 0)
        odds_max = cond.get('odds_max', 9999)
        confidence = cond.get('confidence')
        c1_ranks = cond.get('c1_rank', [])
        venue_filter = cond.get('venue_filter', [])
        use_pattern_h = cond.get('use_pattern_h', False)
        advance_before_match = cond.get('advance_before_match', False)

        # GLOBAL_MONTH_EXCLUDES = [4]
        month_exclude_clause = "AND CAST(strftime('%m', r.race_date) AS INTEGER) != 4"

        # 会場フィルター
        if venue_filter:
            venue_codes = [f"'{str(v).zfill(2)}'" for v in venue_filter]
            venue_clause = f"AND r.venue_code IN ({','.join(venue_codes)})"
        else:
            venue_clause = ""

        # ランクフィルター
        if c1_ranks:
            ranks_str = ','.join(f"'{r}'" for r in c1_ranks)
            rank_clause = f"AND e1.racer_rank IN ({ranks_str})"
        else:
            rank_clause = ""

        # 信頼度フィルター
        if confidence:
            conf_clause = f"AND rp.confidence = '{confidence}'"
        else:
            conf_clause = ""

        # advance/before一致フィルター
        if advance_before_match:
            adv_join = """
            LEFT JOIN race_predictions adv1 ON r.id = adv1.race_id AND adv1.prediction_type = 'advance' AND adv1.rank_prediction = 1
            LEFT JOIN race_predictions adv2 ON r.id = adv2.race_id AND adv2.prediction_type = 'advance' AND adv2.rank_prediction = 2
            LEFT JOIN race_predictions adv3 ON r.id = adv3.race_id AND adv3.prediction_type = 'advance' AND adv3.rank_prediction = 3
            """
            adv_clause = """
            AND (r.venue_code = '11' OR adv1.pit_number IS NULL
                 OR (adv1.pit_number = rp1.pit_number AND adv2.pit_number = rp2.pit_number AND adv3.pit_number = rp3.pit_number))
            """
        else:
            adv_join = ""
            adv_clause = ""

        query = f"""
        SELECT
            r.race_date,
            rp1.pit_number as p1, rp2.pit_number as p2, rp3.pit_number as p3,
            res1.pit_number as actual1, res2.pit_number as actual2, res3.pit_number as actual3,
            t.odds as odds_123
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before' AND rp.rank_prediction = 1
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        JOIN results res1 ON r.id = res1.race_id AND res1.rank = '1'
        JOIN results res2 ON r.id = res2.race_id AND res2.rank = '2'
        JOIN results res3 ON r.id = res3.race_id AND res3.rank = '3'
        LEFT JOIN trifecta_odds t ON r.id = t.race_id
            AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
        {adv_join}
        WHERE r.race_date >= '{start}' AND r.race_date < '{end}'
        {conf_clause}
        {rank_clause}
        {venue_clause}
        {month_exclude_clause}
        {adv_clause}
        AND t.odds >= {odds_min} AND t.odds < {odds_max}
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        total_bet = 0
        total_ret = 0
        hits = 0
        for row in rows:
            _, p1, p2, p3, a1, a2, a3, odds = row
            if odds is None:
                continue
            bet_amt = 200 if use_pattern_h else 100
            total_bet += bet_amt
            if p1 == a1 and p2 == a2 and p3 == a3:
                total_ret += odds * bet_amt
                hits += 1

        results[cid] = {
            'name': cname,
            'races': len(rows),
            'bet': total_bet,
            'return': total_ret,
            'hits': hits,
            'roi': total_ret / total_bet * 100 if total_bet > 0 else 0.0,
            'profit': total_ret - total_bet,
        }

    conn.close()
    return results


def print_monthly_report(year: int, month: int = None, results: dict = None, baseline_path: str = None):
    """月次成績レポートを表示"""
    period = f"{year}年{month}月" if month else f"{year}年（累計）"
    print(f"\n{'='*65}")
    print(f"月次OOS監視レポート [{period}]")
    print(f"集計日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*65}")

    total_bet = sum(v['bet'] for v in results.values())
    total_ret = sum(v['return'] for v in results.values())
    total_hits = sum(v['hits'] for v in results.values())
    total_races = sum(v['races'] for v in results.values())
    total_roi = total_ret / total_bet * 100 if total_bet > 0 else 0.0
    total_profit = total_ret - total_bet

    print(f"\n【全体サマリー】")
    print(f"  購入件数: {total_races}件")
    print(f"  ROI:      {total_roi:.1f}%")
    print(f"  収支:     {total_profit:+,}円")
    print(f"  的中数:   {total_hits}件")

    # ベースライン比較
    if baseline_path and os.path.exists(baseline_path):
        with open(baseline_path, 'r', encoding='utf-8') as f:
            base = json.load(f)
        base_roi = base['total']['roi']
        base_profit_per_race = base['total']['profit'] / base['total']['races'] if base['total']['races'] > 0 else 0
        est_profit = base_profit_per_race * total_races
        print(f"\n【ベースライン比較（{base['param_desc']}）】")
        print(f"  バックテストROI: {base_roi:.1f}%  →  実運用ROI: {total_roi:.1f}%  (差: {total_roi - base_roi:+.1f}pt)")
        print(f"  ※件数が少ないため統計的な判断は月次では不可。参考値として記録のみ。")

    print(f"\n【条件別成績】")
    print(f"{'条件':^32} {'件数':>5} {'ROI':>8} {'収支':>10} {'的中':>4}")
    print('-' * 65)
    for cond in STANDARD_BET_CONDITIONS:
        cid = cond['id']
        v = results.get(cid, {})
        if not v or v['races'] == 0:
            continue
        name = v['name'][:30]
        print(f"{name:<32} {v['races']:>5} {v['roi']:>7.1f}% {v['profit']:>+10,} {v['hits']:>4}")

    print('-' * 65)
    print(f"{'合計':<32} {total_races:>5} {total_roi:>7.1f}% {total_profit:>+10,} {total_hits:>4}")

    # 警告
    print(f"\n【判定】")
    if total_races < 50:
        print(f"  [情報] サンプル不足（{total_races}件）: 統計的判断不可。記録のみ。")
    elif total_roi < 100:
        print(f"  [要注意] ROI {total_roi:.1f}% < 100% : 半年累計でも同様なら原因調査を。")
    elif total_roi < 130:
        print(f"  [監視] ROI {total_roi:.1f}%: バックテスト平均より低め。継続監視。")
    else:
        print(f"  [良好] ROI {total_roi:.1f}%")

    print(f"\n{'='*65}")


def main():
    parser = argparse.ArgumentParser(description='月次OOS監視スクリプト')
    parser.add_argument('--year', type=int, required=True, help='対象年（例: 2026）')
    parser.add_argument('--month', type=int, help='対象月（省略時は年間累計）')
    parser.add_argument('--baseline', type=str, default='data/baselines/v2.44.0.json',
                        help='比較用ベースラインJSON（デフォルト: data/baselines/v2.44.0.json）')
    args = parser.parse_args()

    results = get_monthly_results(args.year, args.month)
    print_monthly_report(args.year, args.month, results, args.baseline)


if __name__ == '__main__':
    main()
