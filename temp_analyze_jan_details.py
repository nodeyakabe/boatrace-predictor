#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
1月の購入レース詳細分析
"""
import sqlite3
from datetime import datetime
from config.settings import DATABASE_PATH

def get_january_bet_details():
    """1月の購入レース詳細を取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 購入条件の定義（standard_backtestと同じ）
    conditions = {
        'A×A1×10-12+会場+逃げ率': {
            'grade': 'A', 'racer_grade': 'A1', 'odds_min': 10, 'odds_max': 12,
            'venues': [1, 3, 6, 9, 10, 12, 14, 20, 22, 24],
            'escape_rate_min': 70, 'bet_type': '1点'
        },
        'C×20-30×B1+会場': {
            'grade': 'C', 'racer_grade': 'B1', 'odds_min': 20, 'odds_max': 30,
            'venues': [1, 7, 10, 12, 13, 14, 16, 20, 22, 24],
            'exclude_venues': [23], 'bet_type': '1点'
        },
        '児島×C×B1×30-50': {
            'grade': 'C', 'racer_grade': 'B1', 'odds_min': 30, 'odds_max': 50,
            'venues': [12], 'bet_type': 'P.H'
        },
        '鳴門×C×A2×30-80': {
            'grade': 'C', 'racer_grade': 'A2', 'odds_min': 30, 'odds_max': 80,
            'venues': [5], 'bet_type': 'P.H'
        },
        '唐津×C×B1×20-30': {
            'grade': 'C', 'racer_grade': 'B1', 'odds_min': 20, 'odds_max': 30,
            'venues': [23], 'bet_type': '1点'
        },
        'D×40-50×B1×2連率20-30%': {
            'grade': 'D', 'racer_grade': 'B1', 'odds_min': 40, 'odds_max': 50,
            'quinella_rate_min': 20, 'quinella_rate_max': 30, 'bet_type': '1点'
        },
        'D×5コース予測×A2除外': {
            'grade': 'D', 'prediction_pit': 5, 'exclude_racer_grade': 'A2',
            'bet_type': 'P.H'
        },
    }

    # 2026年1月の購入対象レースを取得
    query = """
    WITH pred_priority AS (
        SELECT
            race_id,
            rank_prediction,
            pit_number,
            prediction_type,
            ROW_NUMBER() OVER (
                PARTITION BY race_id, rank_prediction
                ORDER BY CASE prediction_type WHEN 'before' THEN 1 WHEN 'advance' THEN 2 END
            ) as rn
        FROM race_predictions
        WHERE prediction_type IN ('before', 'advance')
    )
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        r.race_number,
        r.race_grade as grade,
        rp1.pit_number as pred1,
        rp2.pit_number as pred2,
        rp3.pit_number as pred3,
        rp1.prediction_type as pred_type,
        e1.racer_rank as pred1_grade,
        e1.second_rate as pred1_second_rate,
        t.odds,
        res1.rank as result1,
        res2.rank as result2,
        res3.rank as result3
    FROM races r
    INNER JOIN pred_priority rp1 ON r.id = rp1.race_id AND rp1.rank_prediction = 1 AND rp1.rn = 1
    INNER JOIN pred_priority rp2 ON r.id = rp2.race_id AND rp2.rank_prediction = 2 AND rp2.rn = 1
    INNER JOIN pred_priority rp3 ON r.id = rp3.race_id AND rp3.rank_prediction = 3 AND rp3.rn = 1
    LEFT JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = rp1.pit_number
    LEFT JOIN trifecta_odds t ON r.id = t.race_id
        AND t.combination = CAST(rp1.pit_number AS TEXT) || '-' || CAST(rp2.pit_number AS TEXT) || '-' || CAST(rp3.pit_number AS TEXT)
    LEFT JOIN results res1 ON r.id = res1.race_id AND res1.pit_number = rp1.pit_number
    LEFT JOIN results res2 ON r.id = res2.race_id AND res2.pit_number = rp2.pit_number
    LEFT JOIN results res3 ON r.id = res3.race_id AND res3.pit_number = rp3.pit_number
    WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-02-01'
    ORDER BY r.race_date, r.venue_code, r.race_number
    """

    cursor.execute(query)
    all_races = [dict(row) for row in cursor.fetchall()]

    print("=" * 100)
    print("1月購入レース詳細分析")
    print("=" * 100)
    print()

    # 各条件でフィルタリング
    bet_races = []

    for race in all_races:
        # 基本的な購入条件チェック（簡易版）
        odds = race['odds']
        if odds is None:
            continue

        # 条件マッチング（簡易版 - 主要条件のみ）
        matched_condition = None
        bet_type = None

        # A×A1×10-12+会場+逃げ率
        if (race['grade'] == 'A' and race['pred1_grade'] == 'A1' and
            10 <= odds <= 12 and race['venue_code'] in [1,3,6,9,10,12,14,20,22,24]):
            matched_condition = 'A×A1×10-12+会場+逃げ率'
            bet_type = '1点'

        # C×20-30×B1+会場
        elif (race['grade'] == 'C' and race['pred1_grade'] == 'B1' and
              20 <= odds <= 30 and race['venue_code'] in [1,7,10,12,13,14,16,20,22,24] and
              race['venue_code'] != 23):
            matched_condition = 'C×20-30×B1+会場'
            bet_type = '1点'

        # 児島×C×B1×30-50
        elif (race['grade'] == 'C' and race['pred1_grade'] == 'B1' and
              30 <= odds <= 50 and race['venue_code'] == 12):
            matched_condition = '児島×C×B1×30-50'
            bet_type = 'P.H'

        # 鳴門×C×A2×30-80
        elif (race['grade'] == 'C' and race['pred1_grade'] == 'A2' and
              30 <= odds <= 80 and race['venue_code'] == 5):
            matched_condition = '鳴門×C×A2×30-80'
            bet_type = 'P.H'

        # 唐津×C×B1×20-30
        elif (race['grade'] == 'C' and race['pred1_grade'] == 'B1' and
              20 <= odds <= 30 and race['venue_code'] == 23):
            matched_condition = '唐津×C×B1×20-30'
            bet_type = '1点'

        # D×40-50×B1×2連率20-30%
        elif (race['grade'] == 'D' and race['pred1_grade'] == 'B1' and
              40 <= odds <= 50):
            matched_condition = 'D×40-50×B1×2連率20-30%'
            bet_type = '1点'

        # D×5コース予測×A2除外
        elif (race['grade'] == 'D' and race['pred1'] == 5 and
              race['pred1_grade'] != 'A2'):
            matched_condition = 'D×5コース予測×A2除外'
            bet_type = 'P.H'

        if matched_condition:
            # 的中判定
            is_hit = False
            payout = 0

            if bet_type == '1点':
                # 1-2-3が完全一致
                if (race['result1'] == 1 and race['result2'] == 2 and race['result3'] == 3):
                    is_hit = True
                    payout = int(odds * 100)
            else:  # P.H (3点買い)
                # 1-2-3, 1-3-2, 2-1-3 のいずれか
                if ((race['result1'] == 1 and race['result2'] == 2 and race['result3'] == 3) or
                    (race['result1'] == 1 and race['result2'] == 3 and race['result3'] == 2) or
                    (race['result1'] == 2 and race['result2'] == 1 and race['result3'] == 3)):
                    is_hit = True
                    # 実際の払戻を取得する必要があるが、ここでは簡易的にオッズを使用
                    payout = int(odds * 400 / 3)  # 3点のうち1点が的中

            bet_races.append({
                'condition': matched_condition,
                'bet_type': bet_type,
                'race_date': race['race_date'],
                'venue_code': race['venue_code'],
                'race_number': race['race_number'],
                'grade': race['grade'],
                'prediction': f"{race['pred1']}-{race['pred2']}-{race['pred3']}",
                'pred1_grade': race['pred1_grade'],
                'odds': odds,
                'result1': race['result1'],
                'result2': race['result2'],
                'result3': race['result3'],
                'is_hit': is_hit,
                'payout': payout
            })

    # 的中レース
    hit_races = [r for r in bet_races if r['is_hit']]
    miss_races = [r for r in bet_races if not r['is_hit']]

    print(f"【的中レース: {len(hit_races)}件】")
    print("=" * 100)
    for i, race in enumerate(hit_races, 1):
        venue_name = get_venue_name(race['venue_code'])
        result = f"{race['result1']}-{race['result2']}-{race['result3']}"

        print(f"\n{i}. {race['race_date']} {venue_name}({race['venue_code']:02d}) {race['race_number']}R [{race['grade']}級]")
        print(f"   条件: {race['condition']} ({race['bet_type']})")
        print(f"   予想: {race['prediction']} (1着={race['pred1_grade']}, オッズ={race['odds']:.1f}倍)")
        print(f"   結果: {result}")
        print(f"   払戻: {race['payout']:,}円")

    print("\n" + "=" * 100)
    print(f"\n【ハズレレース: {len(miss_races)}件】")
    print("=" * 100)

    # 条件別にグループ化
    by_condition = {}
    for race in miss_races:
        cond = race['condition']
        if cond not in by_condition:
            by_condition[cond] = []
        by_condition[cond].append(race)

    for cond, races in sorted(by_condition.items()):
        print(f"\n■ {cond} ({races[0]['bet_type']}) - {len(races)}件")
        print("-" * 100)

        for race in races:
            venue_name = get_venue_name(race['venue_code'])
            result = f"{race['result1'] if race['result1'] else '?'}-{race['result2'] if race['result2'] else '?'}-{race['result3'] if race['result3'] else '?'}"

            print(f"  {race['race_date']} {venue_name:6s}({race['venue_code']:02d}) {race['race_number']:2d}R [{race['grade']}] "
                  f"予想:{race['prediction']} オッズ:{race['odds']:5.1f}倍 → 結果:{result}")

    print("\n" + "=" * 100)
    print(f"\n【サマリー】")
    print(f"  購入レース数: {len(bet_races)}件")
    if len(bet_races) > 0:
        print(f"  的中: {len(hit_races)}件 ({len(hit_races)/len(bet_races)*100:.1f}%)")
        print(f"  ハズレ: {len(miss_races)}件 ({len(miss_races)/len(bet_races)*100:.1f}%)")
        print(f"  総払戻: {sum(r['payout'] for r in hit_races):,}円")
    else:
        print("  ※購入対象レースなし")

    conn.close()

def get_venue_name(venue_code):
    """会場コードから会場名を取得"""
    venues = {
        1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
        7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: 'びわこ', 12: '住之江',
        13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
        19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
    }
    return venues.get(venue_code, f'不明({venue_code})')

if __name__ == '__main__':
    get_january_bet_details()
