# -*- coding: utf-8 -*-
"""
指標データ（逃げ率・まくり率・差し率）を使った的中・不的中パターン分析

目的: B信頼度×50-100倍条件の購入件数削減・ROI維持のためのフィルター条件を発見
"""

import sqlite3
import sys
import os
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def analyze_patterns(db_path: str = 'data/boatrace.db'):
    """的中・不的中パターンを分析"""

    print("=" * 80)
    print("指標データを使った的中・不的中パターン分析")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ========================================
    # 1. B×50-100条件の的中・不的中レースを取得
    # ========================================
    print("\n[1] B×50-100条件のレースを取得中...")

    # まず予測の1-2-3位を取得
    query = '''
        WITH predictions AS (
            SELECT
                rp.race_id,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
                MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
                MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.racer_number END) as pred_1st_racer,
                MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.confidence END) as confidence
            FROM race_predictions rp
            WHERE rp.prediction_type = 'before'
            GROUP BY rp.race_id
        ),
        race_results AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank = '1' OR rank = 1 THEN pit_number END) as actual_1st,
                MAX(CASE WHEN rank = '2' OR rank = 2 THEN pit_number END) as actual_2nd,
                MAX(CASE WHEN rank = '3' OR rank = 3 THEN pit_number END) as actual_3rd
            FROM results
            WHERE is_invalid = 0
            GROUP BY race_id
        ),
        bet_races AS (
            SELECT
                r.id as race_id,
                r.venue_code,
                r.race_date,
                p.confidence,
                p.pred_1st,
                p.pred_2nd,
                p.pred_3rd,
                p.pred_1st_racer,
                t.odds,
                rr.actual_1st,
                rr.actual_2nd,
                rr.actual_3rd
            FROM races r
            JOIN predictions p ON r.id = p.race_id
            JOIN race_results rr ON r.id = rr.race_id
            LEFT JOIN trifecta_odds t ON r.id = t.race_id
                AND t.combination = p.pred_1st || '-' || p.pred_2nd || '-' || p.pred_3rd
            WHERE p.confidence = 'B'
              AND r.race_date >= '2020-01-01'
              AND rr.actual_1st IS NOT NULL
        )
        SELECT
            br.*,
            CASE
                WHEN br.pred_1st = br.actual_1st
                 AND br.pred_2nd = br.actual_2nd
                 AND br.pred_3rd = br.actual_3rd
                THEN 1 ELSE 0
            END as is_hit
        FROM bet_races br
        WHERE br.odds >= 50 AND br.odds <= 100
    '''

    cursor.execute(query)
    races = cursor.fetchall()
    print(f"   対象レース数: {len(races)}")

    hit_races = [r for r in races if r['is_hit'] == 1]
    miss_races = [r for r in races if r['is_hit'] == 0]
    print(f"   的中: {len(hit_races)}, 不的中: {len(miss_races)}")

    # ========================================
    # 2. 会場別まくり率・差し率との関係
    # ========================================
    print("\n" + "=" * 80)
    print("[2] 会場別まくり率・差し率との関係")
    print("=" * 80)

    # 会場指標を取得
    cursor.execute('''
        SELECT stadium_id, makuri_rate, sashi_rate, total_races
        FROM stadium_attack_stats
        WHERE period_start = '2000-01-01'
    ''')
    stadium_stats = {row['stadium_id']: dict(row) for row in cursor.fetchall()}

    # まくり率帯別の的中率
    makuri_bins = [
        (0.00, 0.20, "低(~20%)"),
        (0.20, 0.23, "中低(20-23%)"),
        (0.23, 0.26, "中高(23-26%)"),
        (0.26, 1.00, "高(26%~)")
    ]

    print("\n【まくり率帯別の的中率】")
    print("-" * 60)
    for low, high, label in makuri_bins:
        hits = 0
        total = 0
        for r in races:
            stats = stadium_stats.get(r['venue_code'])
            if stats and low <= stats['makuri_rate'] < high:
                total += 1
                if r['is_hit']:
                    hits += 1
        if total > 0:
            roi = calculate_roi(races, stadium_stats, 'makuri_rate', low, high)
            print(f"  {label:12s}: {hits:3d}/{total:4d} ({hits/total*100:5.1f}%) ROI: {roi:6.1f}%")

    # 差し率帯別の的中率
    sashi_bins = [
        (0.00, 0.18, "低(~18%)"),
        (0.18, 0.21, "中低(18-21%)"),
        (0.21, 0.24, "中高(21-24%)"),
        (0.24, 1.00, "高(24%~)")
    ]

    print("\n【差し率帯別の的中率】")
    print("-" * 60)
    for low, high, label in sashi_bins:
        hits = 0
        total = 0
        for r in races:
            stats = stadium_stats.get(r['venue_code'])
            if stats and low <= stats['sashi_rate'] < high:
                total += 1
                if r['is_hit']:
                    hits += 1
        if total > 0:
            roi = calculate_roi(races, stadium_stats, 'sashi_rate', low, high)
            print(f"  {label:12s}: {hits:3d}/{total:4d} ({hits/total*100:5.1f}%) ROI: {roi:6.1f}%")

    # ========================================
    # 3. 1コース選手の逃げ率との関係
    # ========================================
    print("\n" + "=" * 80)
    print("[3] 1コース選手の逃げ率との関係（予測1位が1コースの場合）")
    print("=" * 80)

    # 1コース予測レースを抽出
    course1_races = []
    for r in races:
        if r['pred_1st'] == 1 and r['pred_1st_racer']:
            # 選手の逃げ率を取得
            cursor.execute('''
                SELECT escape_rate, races_1course
                FROM player_escape_stats
                WHERE player_id = ? AND stadium_id IS NULL AND period_start = '2000-01-01'
            ''', (r['pred_1st_racer'],))
            row = cursor.fetchone()
            if row and row['escape_rate'] is not None:
                course1_races.append({
                    'race': r,
                    'escape_rate': row['escape_rate'],
                    'races_1course': row['races_1course']
                })

    print(f"\n   1コース予測レース数: {len(course1_races)}")

    # 逃げ率帯別の的中率
    escape_bins = [
        (0.00, 0.40, "低(~40%)"),
        (0.40, 0.50, "中低(40-50%)"),
        (0.50, 0.60, "中(50-60%)"),
        (0.60, 0.70, "中高(60-70%)"),
        (0.70, 1.00, "高(70%~)")
    ]

    print("\n【1コース選手の逃げ率帯別の的中率】")
    print("-" * 60)
    for low, high, label in escape_bins:
        hits = 0
        total = 0
        total_odds = 0
        for cr in course1_races:
            if low <= cr['escape_rate'] < high:
                total += 1
                total_odds += cr['race']['odds']
                if cr['race']['is_hit']:
                    hits += 1
        if total > 0:
            avg_odds = total_odds / total
            roi = (hits * avg_odds * 100) / (total * 100) * 100
            print(f"  {label:12s}: {hits:3d}/{total:4d} ({hits/total*100:5.1f}%) ROI: {roi:6.1f}% 平均オッズ: {avg_odds:.1f}")

    # ========================================
    # 4. 複合条件の分析
    # ========================================
    print("\n" + "=" * 80)
    print("[4] 複合条件の分析")
    print("=" * 80)

    # 条件組み合わせ
    conditions = [
        # (まくり率上限, 差し率上限, 逃げ率下限, 説明)
        (None, None, None, "全体（ベースライン）"),
        (0.23, None, None, "まくり率<23%"),
        (0.20, None, None, "まくり率<20%"),
        (None, 0.21, None, "差し率<21%"),
        (None, 0.18, None, "差し率<18%"),
        (0.23, 0.21, None, "まくり率<23% & 差し率<21%"),
        (0.20, 0.18, None, "まくり率<20% & 差し率<18%（固い会場）"),
        (None, None, 0.50, "1C予測時: 逃げ率>=50%"),
        (None, None, 0.60, "1C予測時: 逃げ率>=60%"),
        (0.23, None, 0.50, "まくり率<23% & 1C逃げ率>=50%"),
        (0.20, None, 0.60, "まくり率<20% & 1C逃げ率>=60%"),
    ]

    print("\n【複合条件別の的中率・ROI】")
    print("-" * 80)
    print(f"{'条件':<40s} {'件数':>6s} {'的中':>4s} {'的中率':>7s} {'ROI':>8s}")
    print("-" * 80)

    for makuri_max, sashi_max, escape_min, desc in conditions:
        hits = 0
        total = 0
        total_odds = 0

        for r in races:
            stats = stadium_stats.get(r['venue_code'])
            if not stats:
                continue

            # まくり率条件
            if makuri_max and stats['makuri_rate'] >= makuri_max:
                continue

            # 差し率条件
            if sashi_max and stats['sashi_rate'] >= sashi_max:
                continue

            # 逃げ率条件（1コース予測時のみ）
            if escape_min:
                if r['pred_1st'] != 1:
                    continue
                # 逃げ率を取得
                cursor.execute('''
                    SELECT escape_rate FROM player_escape_stats
                    WHERE player_id = ? AND stadium_id IS NULL AND period_start = '2000-01-01'
                ''', (r['pred_1st_racer'],))
                row = cursor.fetchone()
                if not row or row['escape_rate'] is None or row['escape_rate'] < escape_min:
                    continue

            total += 1
            total_odds += r['odds']
            if r['is_hit']:
                hits += 1

        if total > 0:
            hit_rate = hits / total * 100
            avg_odds = total_odds / total
            roi = (hits * avg_odds * 100) / (total * 100) * 100
            print(f"  {desc:<38s} {total:>6d} {hits:>4d} {hit_rate:>6.1f}% {roi:>7.1f}%")

    # ========================================
    # 5. 除外すべき条件の特定
    # ========================================
    print("\n" + "=" * 80)
    print("[5] 除外すべき条件の特定（ROI < 100%）")
    print("=" * 80)

    # 会場別の詳細
    print("\n【会場別ROI（B×50-100）】")
    print("-" * 70)

    venue_results = defaultdict(lambda: {'hits': 0, 'total': 0, 'odds_sum': 0})
    for r in races:
        v = r['venue_code']
        venue_results[v]['total'] += 1
        venue_results[v]['odds_sum'] += r['odds']
        if r['is_hit']:
            venue_results[v]['hits'] += 1

    # 会場名を取得
    cursor.execute('SELECT venue_code, venue_name FROM venue_data')
    venue_names = {row['venue_code']: row['venue_name'] for row in cursor.fetchall()}

    sorted_venues = sorted(venue_results.items(),
                          key=lambda x: (x[1]['hits'] * x[1]['odds_sum'] / x[1]['total']) / x[1]['total'] if x[1]['total'] > 0 else 0)

    print(f"{'会場':<8s} {'件数':>5s} {'的中':>4s} {'的中率':>7s} {'ROI':>8s} {'まくり率':>8s} {'差し率':>8s}")
    print("-" * 70)

    low_roi_venues = []
    for vc, data in sorted_venues:
        if data['total'] < 10:
            continue
        name = venue_names.get(vc, vc)
        hit_rate = data['hits'] / data['total'] * 100
        avg_odds = data['odds_sum'] / data['total']
        roi = (data['hits'] * avg_odds * 100) / (data['total'] * 100) * 100
        stats = stadium_stats.get(vc, {})
        makuri = stats.get('makuri_rate', 0) * 100
        sashi = stats.get('sashi_rate', 0) * 100

        marker = "<<< 除外候補" if roi < 100 else ""
        print(f"  {name:<6s} {data['total']:>5d} {data['hits']:>4d} {hit_rate:>6.1f}% {roi:>7.1f}% {makuri:>7.1f}% {sashi:>7.1f}% {marker}")

        if roi < 100:
            low_roi_venues.append((vc, name, roi, makuri, sashi))

    # ========================================
    # 6. 推奨フィルター条件
    # ========================================
    print("\n" + "=" * 80)
    print("[6] 推奨フィルター条件")
    print("=" * 80)

    print("\n【発見した傾向】")
    print("-" * 60)

    # まくり率高い会場を抽出
    high_makuri = [(vc, name, roi, makuri) for vc, name, roi, makuri, sashi in low_roi_venues if makuri > 24]
    if high_makuri:
        print("\n  ■ まくり率が高い会場はROIが低い傾向:")
        for vc, name, roi, makuri in high_makuri:
            print(f"    - {name}: まくり率 {makuri:.1f}%, ROI {roi:.1f}%")

    # ========================================
    # 7. 年度別安定性の検証
    # ========================================
    print("\n" + "=" * 80)
    print("[7] 年度別安定性の検証（有望条件）")
    print("=" * 80)

    # 有望条件: まくり率<20% & 逃げ率>=60%
    print("\n【まくり率<20% & 1C逃げ率>=60%】")
    print("-" * 70)
    print(f"{'年度':<6s} {'件数':>6s} {'的中':>4s} {'的中率':>7s} {'ROI':>8s}")
    print("-" * 70)

    for year in range(2020, 2026):
        year_start = f'{year}-01-01'
        year_end = f'{year}-12-31'

        hits = 0
        total = 0
        total_odds = 0

        for r in races:
            if not (year_start <= r['race_date'] <= year_end):
                continue

            stats = stadium_stats.get(r['venue_code'])
            if not stats or stats['makuri_rate'] >= 0.20:
                continue

            if r['pred_1st'] != 1:
                continue

            cursor.execute('''
                SELECT escape_rate FROM player_escape_stats
                WHERE player_id = ? AND stadium_id IS NULL AND period_start = '2000-01-01'
            ''', (r['pred_1st_racer'],))
            row = cursor.fetchone()
            if not row or row['escape_rate'] is None or row['escape_rate'] < 0.60:
                continue

            total += 1
            total_odds += r['odds']
            if r['is_hit']:
                hits += 1

        if total > 0:
            hit_rate = hits / total * 100
            avg_odds = total_odds / total
            roi = (hits * avg_odds * 100) / (total * 100) * 100
            status = "O" if roi >= 100 else "X"
            print(f"  {year}   {total:>6d} {hits:>4d} {hit_rate:>6.1f}% {roi:>7.1f}% {status}")
        else:
            print(f"  {year}   {total:>6d}    -      -        -")

    # ========================================
    # 8. 除外条件の検証
    # ========================================
    print("\n" + "=" * 80)
    print("[8] 除外条件の検証")
    print("=" * 80)

    # ROI 0%の会場を特定
    zero_roi_venues = [vc for vc, data in venue_results.items()
                       if data['total'] >= 10 and data['hits'] == 0]

    print(f"\n   ROI 0%の会場（10件以上）: {len(zero_roi_venues)}会場")

    # 除外した場合の効果
    print("\n【除外会場別の効果】")
    print("-" * 70)

    for exclude_list, desc in [
        (zero_roi_venues, "ROI 0%会場を全除外"),
        (['桐生', '戸田'], "まくり率高（桐生・戸田）を除外"),
    ]:
        # 会場コードに変換
        if isinstance(exclude_list[0], str) and len(exclude_list[0]) > 2:
            # 会場名の場合、コードに変換
            name_to_code = {v: k for k, v in venue_names.items()}
            exclude_codes = [name_to_code.get(n, n) for n in exclude_list]
        else:
            exclude_codes = exclude_list

        hits = 0
        total = 0
        total_odds = 0

        for r in races:
            if r['venue_code'] in exclude_codes:
                continue
            total += 1
            total_odds += r['odds']
            if r['is_hit']:
                hits += 1

        if total > 0:
            hit_rate = hits / total * 100
            avg_odds = total_odds / total
            roi = (hits * avg_odds * 100) / (total * 100) * 100
            print(f"  {desc}:")
            print(f"    件数: {total}, 的中: {hits}, ROI: {roi:.1f}%")

    # ========================================
    # 9. 結論
    # ========================================
    print("\n" + "=" * 80)
    print("[9] 分析結論")
    print("=" * 80)

    print("""
【B×50-100条件での指標活用】

■ ベースライン: 591件, 16的中, ROI 184.1%

■ 有効なフィルター条件:
  1. まくり率 < 20% & 1C逃げ率 >= 60%
     → 70件, 3的中, ROI 279.8% (+95.7pt)
     ※ 件数は減るが的中率・ROIが向上

  2. 差し率 < 18%
     → 216件, 6的中, ROI 187.5% (+3.4pt)
     ※ 件数を維持しつつROI微増

■ 除外すべき会場（ROI 0%、10件以上）:
  - 三国、住之江、鳴門、大村、下関、浜名湖、桐生、蒲郡、常滑、唐津、尼崎、若松

■ 意外な発見:
  - まくり率が高い会場（戸田29.6%、江戸川26.2%）のROIが高い
  - 「荒れる会場 = 避けるべき」とは限らない
  - 高オッズ帯（50-100倍）では荒れる方が的中時のリターンが大きい

■ 推奨戦略:
  1. B×50-100は現状維持（ROI 184%は十分高い）
  2. 件数削減が必要な場合:
     - 「まくり率<20% & 1C逃げ率>=60%」で絞り込み
     - 件数: 591→70（-88%）、ROI: 184%→280%
""")

    conn.close()


def calculate_roi(races, stadium_stats, key, low, high):
    """ROIを計算"""
    hits = 0
    total = 0
    total_odds = 0

    for r in races:
        stats = stadium_stats.get(r['venue_code'])
        if stats and low <= stats[key] < high:
            total += 1
            total_odds += r['odds']
            if r['is_hit']:
                hits += 1

    if total == 0:
        return 0

    avg_odds = total_odds / total
    return (hits * avg_odds * 100) / (total * 100) * 100


if __name__ == "__main__":
    analyze_patterns()
