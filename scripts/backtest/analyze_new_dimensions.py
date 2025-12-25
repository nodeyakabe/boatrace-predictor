#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新視点での不的中パターン分析

分析視点:
1. 開催日程（初日/中日/最終日）
2. ナイター vs デイレース
3. グレード別（一般戦/G3/G2/G1/SG）
4. 風速帯×風向別
"""
import sqlite3
import sys
import io
import os

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

# ナイター会場（18時以降開催）
NIGHT_VENUES = [2, 4, 6, 7, 10, 11, 14, 17, 20, 21, 24]  # 戸田,平和島,浜名湖,蒲郡,三国,琵琶湖,鳴門,宮島,若松,芦屋,大村

# 現在の購入条件
CONDITIONS = [
    {'name': 'A×A1×10-12', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 10, 'odds_max': 12, 'venue_filter': None, 'motor_min': None},
    {'name': 'A×A1×14-16', 'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 14, 'odds_max': 16, 'venue_filter': None, 'motor_min': None},
    {'name': 'A×B1×Motor40%+', 'confidence': 'A', 'c1_rank': ['B1'], 'odds_min': 10, 'odds_max': 100, 'venue_filter': None, 'motor_min': 40},
    {'name': 'B×50-100', 'confidence': 'B', 'c1_rank': ['A1', 'B1'], 'odds_min': 50, 'odds_max': 100, 'venue_filter': None, 'motor_min': None},
    {'name': 'B×30-50×B1+会場', 'confidence': 'B', 'c1_rank': ['B1'], 'odds_min': 30, 'odds_max': 50,
     'venue_filter': [10, 6, 16, 21, 9, 13, 20, 24, 7, 8], 'motor_min': None},
    {'name': 'C×20-30×B1+会場', 'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30,
     'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17], 'motor_min': None},
    {'name': '鳴門×C×A2×30-80', 'confidence': 'C', 'c1_rank': ['A2'], 'odds_min': 30, 'odds_max': 80,
     'venue_filter': [14], 'motor_min': None},
    {'name': 'D×40-50×B1', 'confidence': 'D', 'c1_rank': ['B1'], 'odds_min': 40, 'odds_max': 50, 'venue_filter': None, 'motor_min': None},
    {'name': 'D×35-60', 'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1'], 'odds_min': 35, 'odds_max': 60, 'venue_filter': None, 'motor_min': None,
     'race_exclude': [9], 'venue_exclude': [10]},
]


def get_all_bets_with_details(year_start=2020, year_end=2025):
    """全購入データを詳細情報付きで取得"""
    all_bets = []

    for cond in CONDITIONS:
        c1_rank_str = "','".join(cond['c1_rank'])
        venue_clause = ""
        if cond.get('venue_filter'):
            venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"
        motor_clause = ""
        if cond.get('motor_min'):
            motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"
        race_exclude_clause = ""
        if cond.get('race_exclude'):
            race_exclude_clause = f"AND r.race_number NOT IN ({','.join(map(str, cond['race_exclude']))})"
        venue_exclude_clause = ""
        if cond.get('venue_exclude'):
            venue_exclude_clause = f"AND r.venue_code NOT IN ({','.join(map(str, cond['venue_exclude']))})"

        query = f'''
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_number,
            r.race_date,
            r.race_grade,
            r.is_nighter,
            rc.wind_speed,
            rc.wind_direction,
            e1.racer_rank as c1_rank,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') as actual_2nd,
            (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') as actual_3rd,
            COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = r.id
                 AND o.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
                ), 0
            ) as pred_odds
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE rp.rank_prediction = 1
        AND rp.confidence = '{cond["confidence"]}'
        AND e1.racer_rank IN ('{c1_rank_str}')
        AND r.race_date >= '{year_start}-01-01'
        AND r.race_date < '{year_end}-12-01'
        {venue_clause}
        {motor_clause}
        {race_exclude_clause}
        {venue_exclude_clause}
        '''
        cursor.execute(query)
        rows = cursor.fetchall()

        for row in rows:
            (race_id, venue_code, race_number, race_date, grade,
             is_nighter, wind_speed, wind_direction, c1_rank, p1, p2, p3, a1, a2, a3, pred_odds) = row

            if pred_odds >= cond['odds_min'] and pred_odds < cond['odds_max']:
                is_hit = (p1 == a1 and p2 == a2 and p3 == a3)
                payout = pred_odds * 100 if is_hit else 0

                # 開催日程の分類（レース番号で代替）
                if race_number <= 4:
                    schedule = '前半(1-4R)'
                elif race_number <= 8:
                    schedule = '中盤(5-8R)'
                else:
                    schedule = '後半(9-12R)'

                # ナイター判定
                is_night = bool(is_nighter)

                # グレード分類
                if grade in ['SG', 'G1', 'G2', 'G3']:
                    grade_category = grade
                else:
                    grade_category = '一般'

                # 風速帯
                if wind_speed is None:
                    wind_band = '不明'
                elif wind_speed <= 2:
                    wind_band = '0-2m'
                elif wind_speed <= 4:
                    wind_band = '3-4m'
                elif wind_speed <= 6:
                    wind_band = '5-6m'
                else:
                    wind_band = '7m+'

                # 風向分類（文字列の場合）
                if wind_direction is None:
                    wind_dir = '不明'
                elif isinstance(wind_direction, str):
                    if wind_direction in ['北', '北東', '北西']:
                        wind_dir = '追い風'
                    elif wind_direction in ['南', '南東', '南西']:
                        wind_dir = '向かい風'
                    elif wind_direction in ['東', '西']:
                        wind_dir = '横風'
                    else:
                        wind_dir = '不明'
                elif isinstance(wind_direction, (int, float)):
                    # 数値の場合
                    if wind_direction in [1, 2, 8]:  # 北、北東、北西
                        wind_dir = '追い風'
                    elif wind_direction in [4, 5, 6]:  # 南、南東、南西
                        wind_dir = '向かい風'
                    else:  # 3, 7 東、西
                        wind_dir = '横風'
                else:
                    wind_dir = '不明'

                all_bets.append({
                    'condition': cond['name'],
                    'confidence': cond['confidence'],
                    'venue_code': venue_code,
                    'race_number': race_number,
                    'race_date': race_date,
                    'schedule': schedule,
                    'is_night': is_night,
                    'grade': grade_category,
                    'wind_speed': wind_speed,
                    'wind_band': wind_band,
                    'wind_dir': wind_dir,
                    'is_hit': is_hit,
                    'payout': payout,
                    'profit': payout - 100,
                    'odds': pred_odds,
                })

    return all_bets


def analyze_dimension(bets, dim_key, dim_name, confidences=['A', 'B', 'C', 'D']):
    """特定の次元で信頼度別に分析"""
    print(f"\n{'='*100}")
    print(f"【{dim_name}別分析】")
    print(f"{'='*100}")

    # 次元の値を取得
    dim_values = sorted(set(b[dim_key] for b in bets))

    for conf in confidences:
        conf_bets = [b for b in bets if b['confidence'] == conf]
        if not conf_bets:
            continue

        print(f"\n[信頼度{conf}]")
        print(f"{'カテゴリ':<15} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>14}")
        print("-" * 70)

        results = []
        for val in dim_values:
            val_bets = [b for b in conf_bets if b[dim_key] == val]
            if not val_bets:
                continue

            total = len(val_bets)
            hits = sum(1 for b in val_bets if b['is_hit'])
            profit = sum(b['profit'] for b in val_bets)
            roi = 100.0 * (profit + total * 100) / (total * 100) if total > 0 else 0
            hit_rate = 100.0 * hits / total if total > 0 else 0

            results.append({
                'value': val,
                'total': total,
                'hits': hits,
                'hit_rate': hit_rate,
                'roi': roi,
                'profit': profit,
            })

        # ROI順でソート
        results.sort(key=lambda x: x['roi'])

        for r in results:
            status = "★" if r['roi'] >= 100 else "×" if r['profit'] < -1000 else ""
            val_str = str(r['value'])
            if dim_key == 'is_night':
                val_str = 'ナイター' if r['value'] else 'デイ'
            print(f"{val_str:<15} {r['total']:>8} {r['hits']:>6} {r['hit_rate']:>7.1f}% {r['roi']:>9.1f}% {r['profit']:>+13,.0f} {status}")

        # 合計
        total_all = len(conf_bets)
        hits_all = sum(1 for b in conf_bets if b['is_hit'])
        profit_all = sum(b['profit'] for b in conf_bets)
        roi_all = 100.0 * (profit_all + total_all * 100) / (total_all * 100) if total_all > 0 else 0
        print("-" * 70)
        print(f"{'合計':<15} {total_all:>8} {hits_all:>6} {100.0*hits_all/total_all:>7.1f}% {roi_all:>9.1f}% {profit_all:>+13,.0f}")


def analyze_wind_combined(bets, confidences=['A', 'B', 'C', 'D']):
    """風速×風向の組み合わせ分析"""
    print(f"\n{'='*100}")
    print(f"【風速帯×風向別分析】")
    print(f"{'='*100}")

    wind_bands = ['0-2m', '3-4m', '5-6m', '7m+']
    wind_dirs = ['追い風', '向かい風', '横風']

    for conf in confidences:
        conf_bets = [b for b in bets if b['confidence'] == conf]
        if not conf_bets:
            continue

        print(f"\n[信頼度{conf}]")
        print(f"{'風速×風向':<20} {'件数':>8} {'的中':>6} {'的中率':>8} {'ROI':>10} {'収支':>14}")
        print("-" * 75)

        results = []
        for band in wind_bands:
            for direction in wind_dirs:
                combo_bets = [b for b in conf_bets if b['wind_band'] == band and b['wind_dir'] == direction]
                if not combo_bets:
                    continue

                total = len(combo_bets)
                hits = sum(1 for b in combo_bets if b['is_hit'])
                profit = sum(b['profit'] for b in combo_bets)
                roi = 100.0 * (profit + total * 100) / (total * 100) if total > 0 else 0
                hit_rate = 100.0 * hits / total if total > 0 else 0

                results.append({
                    'combo': f"{band}×{direction}",
                    'total': total,
                    'hits': hits,
                    'hit_rate': hit_rate,
                    'roi': roi,
                    'profit': profit,
                })

        # ROI順でソート
        results.sort(key=lambda x: x['roi'])

        for r in results:
            status = "★" if r['roi'] >= 100 else "×" if r['profit'] < -1000 else ""
            print(f"{r['combo']:<20} {r['total']:>8} {r['hits']:>6} {r['hit_rate']:>7.1f}% {r['roi']:>9.1f}% {r['profit']:>+13,.0f} {status}")


def find_exclusion_candidates(bets):
    """除外候補を発見"""
    print(f"\n{'='*100}")
    print(f"【除外候補サマリー（赤字パターン）】")
    print(f"{'='*100}")

    exclusions = []

    # 各次元で赤字パターンを探す
    dimensions = [
        ('schedule', '開催日程'),
        ('is_night', 'ナイター'),
        ('grade', 'グレード'),
        ('wind_band', '風速帯'),
    ]

    for dim_key, dim_name in dimensions:
        for conf in ['A', 'B', 'C', 'D']:
            conf_bets = [b for b in bets if b['confidence'] == conf]
            if not conf_bets:
                continue

            dim_values = set(b[dim_key] for b in conf_bets)
            for val in dim_values:
                val_bets = [b for b in conf_bets if b[dim_key] == val]
                if len(val_bets) < 20:  # 最低20件
                    continue

                profit = sum(b['profit'] for b in val_bets)
                total = len(val_bets)
                roi = 100.0 * (profit + total * 100) / (total * 100) if total > 0 else 0

                if profit < -2000:  # 2000円以上の赤字
                    val_str = 'ナイター' if dim_key == 'is_night' and val else ('デイ' if dim_key == 'is_night' else str(val))
                    exclusions.append({
                        'confidence': conf,
                        'dimension': dim_name,
                        'value': val_str,
                        'total': total,
                        'profit': profit,
                        'roi': roi,
                        'improvement': -profit,
                    })

    # 風速×風向の組み合わせ
    wind_bands = ['0-2m', '3-4m', '5-6m', '7m+']
    wind_dirs = ['追い風', '向かい風', '横風']

    for conf in ['A', 'B', 'C', 'D']:
        conf_bets = [b for b in bets if b['confidence'] == conf]
        if not conf_bets:
            continue

        for band in wind_bands:
            for direction in wind_dirs:
                combo_bets = [b for b in conf_bets if b['wind_band'] == band and b['wind_dir'] == direction]
                if len(combo_bets) < 20:
                    continue

                profit = sum(b['profit'] for b in combo_bets)
                total = len(combo_bets)
                roi = 100.0 * (profit + total * 100) / (total * 100) if total > 0 else 0

                if profit < -2000:
                    exclusions.append({
                        'confidence': conf,
                        'dimension': '風速×風向',
                        'value': f"{band}×{direction}",
                        'total': total,
                        'profit': profit,
                        'roi': roi,
                        'improvement': -profit,
                    })

    # 改善効果順でソート
    exclusions.sort(key=lambda x: x['improvement'], reverse=True)

    if exclusions:
        print(f"\n{'信頼度':<8} {'次元':<12} {'値':<18} {'件数':>8} {'ROI':>10} {'収支':>14} {'改善効果':>12}")
        print("-" * 95)
        for e in exclusions[:20]:
            print(f"{e['confidence']:<8} {e['dimension']:<12} {e['value']:<18} {e['total']:>8} {e['roi']:>9.1f}% {e['profit']:>+13,.0f} {e['improvement']:>+11,.0f}")
    else:
        print("\n顕著な赤字パターンは見つかりませんでした。")


def main():
    print("=" * 100)
    print("新視点での不的中パターン分析")
    print("対象期間: 2020年-2025年（6年間）")
    print("=" * 100)

    # 全購入データを取得
    print("\nデータ取得中...")
    bets = get_all_bets_with_details(2020, 2025)
    print(f"総件数: {len(bets)}件")
    print(f"的中: {sum(1 for b in bets if b['is_hit'])}件")

    # 1. 開催日程別分析
    analyze_dimension(bets, 'schedule', '開催日程')

    # 2. ナイター vs デイ
    analyze_dimension(bets, 'is_night', 'ナイター/デイ')

    # 3. グレード別
    analyze_dimension(bets, 'grade', 'グレード')

    # 4. 風速帯×風向
    analyze_wind_combined(bets)

    # 除外候補サマリー
    find_exclusion_candidates(bets)

    conn.close()


if __name__ == '__main__':
    main()
