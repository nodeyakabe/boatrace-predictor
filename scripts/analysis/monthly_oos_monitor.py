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

集計方式:
    - standard_backtest_unique と同じ優先度順重複除外を適用
    - 1レース1条件（実運用シミュレーション）
"""
import sys
import os
import io
import json
import sqlite3
import argparse
from datetime import datetime

# Windows コンソールの文字化け対策
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from scripts.backtest.backtest_helpers import get_race_ids_for_condition


def assign_races_to_conditions(cursor, conditions, start_date, end_date):
    """優先度順に重複除外してレースを条件に割り当て（standard_backtest_uniqueと同ロジック）"""
    sorted_conditions = sorted(
        conditions,
        key=lambda x: (x.get('priority', 999), conditions.index(x))
    )
    assigned = set()
    condition_to_races = {}
    for cond in sorted_conditions:
        race_ids = get_race_ids_for_condition(cursor, cond, start_date, end_date)
        new_ids = race_ids - assigned
        assigned |= new_ids
        condition_to_races[cond['id']] = new_ids
    return condition_to_races


def analyze_race_result(cursor, cond, race_id):
    """1レースの実績を計算。オッズ範囲外・データ欠損はNoneを返す"""
    use_pattern_h = cond.get('use_pattern_h', False)
    odds_min = cond.get('odds_min', 0)
    odds_max = cond.get('odds_max', 9999)

    # 予測を取得（before、rank 1-5）
    cursor.execute("""
        SELECT pit_number FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'before'
        ORDER BY rank_prediction
        LIMIT 5
    """, (race_id,))
    pits = [row[0] for row in cursor.fetchall()]
    if len(pits) < 3:
        return None

    # 実際の結果を取得
    cursor.execute("""
        SELECT res1.pit_number, res2.pit_number, res3.pit_number
        FROM results res1
        JOIN results res2 ON res2.race_id = ? AND res2.rank = '2'
        JOIN results res3 ON res3.race_id = ? AND res3.rank = '3'
        WHERE res1.race_id = ? AND res1.rank = '1'
    """, (race_id, race_id, race_id))
    row = cursor.fetchone()
    if not row:
        return None
    a1, a2, a3 = row

    exclude_p5 = cond.get('pattern_h_exclude_p5', False)
    if use_pattern_h and exclude_p5 and len(pits) >= 4:
        # パターンH2: p1-p2-{p3,p4} を 200/100円（p5除外版）
        combos = [
            (f"{pits[0]}-{pits[1]}-{pits[2]}", pits[0], pits[1], pits[2], 200),
            (f"{pits[0]}-{pits[1]}-{pits[3]}", pits[0], pits[1], pits[3], 100),
        ]
    elif use_pattern_h and len(pits) >= 5:
        # パターンH: p1-p2-{p3,p4,p5} を 200/100/100円
        combos = [
            (f"{pits[0]}-{pits[1]}-{pits[2]}", pits[0], pits[1], pits[2], 200),
            (f"{pits[0]}-{pits[1]}-{pits[3]}", pits[0], pits[1], pits[3], 100),
            (f"{pits[0]}-{pits[1]}-{pits[4]}", pits[0], pits[1], pits[4], 100),
        ]
    else:
        combos = [(f"{pits[0]}-{pits[1]}-{pits[2]}", pits[0], pits[1], pits[2], 100)]

    total_bet = 0
    total_return = 0.0
    hit = False

    for combo, p1, p2, p3, bet_amt in combos:
        cursor.execute(
            "SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?",
            (race_id, combo)
        )
        row = cursor.fetchone()
        if row is None or row[0] is None:
            continue
        odds = row[0]
        if not (odds_min <= odds < odds_max):
            continue
        total_bet += bet_amt
        if p1 == a1 and p2 == a2 and p3 == a3:
            total_return += odds * bet_amt
            hit = True

    if total_bet == 0:
        return None

    return {'bet': total_bet, 'return': total_return, 'hit': hit}


def get_monthly_results(year: int, month: int = None):
    """指定年（月）の実運用成績を集計（優先度順重複除外あり）"""
    if month:
        start = f"{year}-{month:02d}-01"
        end = f"{year+1}-01-01" if month == 12 else f"{year}-{month+1:02d}-01"
    else:
        start = f"{year}-01-01"
        end = f"{year+1}-01-01"

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 優先度順の重複除外でレースを割り当て
    condition_to_races = assign_races_to_conditions(cursor, STANDARD_BET_CONDITIONS, start, end)

    results = {}
    for cond in STANDARD_BET_CONDITIONS:
        cid = cond['id']
        race_ids = condition_to_races.get(cid, set())

        total_bet = 0
        total_ret = 0.0
        hits = 0
        valid_races = 0

        for race_id in race_ids:
            r = analyze_race_result(cursor, cond, race_id)
            if r is None:
                continue
            valid_races += 1
            total_bet += r['bet']
            total_ret += r['return']
            if r['hit']:
                hits += 1

        results[cid] = {
            'name': cond['name'],
            'races': valid_races,
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
    print(f"集計方式: standard_backtest_unique準拠（優先度順重複除外あり）")
    print(f"{'='*65}")

    total_bet = sum(v['bet'] for v in results.values())
    total_ret = sum(v['return'] for v in results.values())
    total_hits = sum(v['hits'] for v in results.values())
    total_races = sum(v['races'] for v in results.values())
    total_roi = total_ret / total_bet * 100 if total_bet > 0 else 0.0
    total_profit = total_ret - total_bet

    print(f"\n【全体サマリー】")
    print(f"  購入件数: {total_races}件（重複除外後）")
    print(f"  ROI:      {total_roi:.1f}%")
    print(f"  収支:     {total_profit:+,.0f}円")
    print(f"  的中数:   {total_hits}件")

    # ベースライン比較
    if baseline_path and os.path.exists(baseline_path):
        with open(baseline_path, 'r', encoding='utf-8') as f:
            base = json.load(f)
        base_roi = base['total']['roi']
        # standard_backtest_unique は 'bets' キー、fast_backtest は 'races' キーを使用
        base_total_races = base['total'].get('bets', base['total'].get('races', 1))
        base_profit_per_race = base['total']['profit'] / base_total_races if base_total_races > 0 else 0
        est_profit = base_profit_per_race * total_races
        param_desc = base.get('param_desc', os.path.basename(baseline_path))
        print(f"\n【ベースライン比較（{param_desc}）】")
        print(f"  バックテストROI: {base_roi:.1f}%  →  実運用ROI: {total_roi:.1f}%  (差: {total_roi - base_roi:+.1f}pt)")
        print(f"  期待収支（件数比例）: {est_profit:+,.0f}円  →  実績収支: {total_profit:+,.0f}円")
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
        print(f"{name:<32} {v['races']:>5} {v['roi']:>7.1f}% {v['profit']:>+10,.0f} {v['hits']:>4}")

    print('-' * 65)
    print(f"{'合計':<32} {total_races:>5} {total_roi:>7.1f}% {total_profit:>+10,.0f} {total_hits:>4}")

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
