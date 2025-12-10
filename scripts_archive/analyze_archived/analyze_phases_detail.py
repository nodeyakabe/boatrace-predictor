# -*- coding: utf-8 -*-
"""
Phase 1-4 詳細分析スクリプト
"""

import sqlite3
import sys
sys.path.insert(0, '.')

from src.analysis import MissPatternAnalyzer, CompoundRuleFinder
from src.database import AttackPatternDB, PatternBasedPredictor
from src.second_model import SecondFeaturesGenerator


def analyze_phase1():
    """Phase 1: ミスパターン分析の詳細"""
    print("=" * 70)
    print("PHASE 1: 予測外れパターン分類の詳細")
    print("=" * 70)

    analyzer = MissPatternAnalyzer()
    results = analyzer.analyze_second_place_misses(
        start_date='2025-11-01',
        end_date='2025-11-30'
    )

    print(f"\n【基本統計】")
    print(f"  分析レース数: {results['total_races']}")
    print(f"  1着的中: {results['hit_1st_races']} ({results['hit_1st_races']/results['total_races']*100:.1f}%)")
    print(f"  2着外れ (234にいない): {results['miss_2nd_in_234']} ({results['miss_2nd_in_234']/max(1,results['hit_1st_races'])*100:.1f}%)")

    print(f"\n【信頼度別の外れ率】")
    for conf, data in sorted(results.get('by_confidence', {}).items()):
        if data['total'] > 0:
            miss_rate = data['miss'] / data['total'] * 100
            print(f"  {conf}: {data['miss']}/{data['total']} ({miss_rate:.1f}%)")

    print(f"\n【1着コース別の2着外れ傾向】")
    for course, data in sorted(results.get('by_winner_course', {}).items()):
        if data['total'] > 0:
            miss_rate = data['miss'] / data['total'] * 100
            print(f"  {course}C勝利時: 外れ {data['miss']}/{data['total']} ({miss_rate:.1f}%)")

    print(f"\n【外れた時の実際の2着コース分布】")
    actual_dist = results.get('actual_2nd_course_when_miss', {})
    for course, count in sorted(actual_dist.items(), key=lambda x: -x[1]):
        print(f"  {course}C: {count}回")

    print(f"\n【外れた2着の予測順位分布】")
    pred_rank_dist = results.get('predicted_rank_of_actual_2nd', {})
    for rank, count in sorted(pred_rank_dist.items()):
        print(f"  {rank}位予測: {count}回")


def analyze_phase2():
    """Phase 2: 2着特徴量の詳細"""
    print("\n" + "=" * 70)
    print("PHASE 2: 2着予測特徴量の詳細")
    print("=" * 70)

    generator = SecondFeaturesGenerator()

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT r.id, r.venue_code, res.pit_number as winner_pit
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE r.race_date LIKE '2025-11%' AND res.rank = 1 AND res.is_invalid = 0
        LIMIT 100
    ''')
    races = cursor.fetchall()

    hits_top1 = 0
    hits_top2 = 0
    hits_top3 = 0
    total = 0

    for race_id, venue_code, winner_pit in races:
        candidates = generator.rank_second_candidates(race_id, winner_pit)
        if not candidates:
            continue

        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND rank = 2 AND is_invalid = 0
        ''', (race_id,))
        actual = cursor.fetchone()

        if not actual:
            continue

        actual_2nd = actual[0]
        total += 1

        predicted_order = [c[0] for c in candidates]
        if actual_2nd in predicted_order:
            rank = predicted_order.index(actual_2nd) + 1
            if rank == 1:
                hits_top1 += 1
            if rank <= 2:
                hits_top2 += 1
            if rank <= 3:
                hits_top3 += 1

    print(f"\n【2着予測精度（1着確定後）】")
    print(f"  分析レース数: {total}")
    print(f"  Top1的中: {hits_top1}/{total} ({hits_top1/total*100:.1f}%)")
    print(f"  Top2的中: {hits_top2}/{total} ({hits_top2/total*100:.1f}%)")
    print(f"  Top3的中: {hits_top3}/{total} ({hits_top3/total*100:.1f}%)")

    print(f"\n【会場別2着パターン】")
    for venue_code in ['01', '12', '24']:
        cursor.execute('SELECT venue_name FROM venue_data WHERE venue_code = ? LIMIT 1', (venue_code,))
        vn = cursor.fetchone()
        venue_name = vn[0] if vn else venue_code

        print(f"\n  {venue_code} {venue_name}:")
        for winner_course in [1, 2, 3]:
            prob_by_2nd = {}
            for second_course in range(1, 7):
                if second_course == winner_course:
                    continue
                prob = generator.get_venue_second_probability(venue_code, winner_course, second_course)
                prob_by_2nd[second_course] = prob

            sorted_probs = sorted(prob_by_2nd.items(), key=lambda x: -x[1])
            top3 = sorted_probs[:3]
            top3_str = ', '.join([f'{c}C:{p*100:.1f}%' for c, p in top3])
            print(f"    1着{winner_course}C時 -> 2着確率: {top3_str}")

    conn.close()


def analyze_phase3():
    """Phase 3: アタックパターンDBの詳細"""
    print("\n" + "=" * 70)
    print("PHASE 3: Attack Pattern DB 詳細")
    print("=" * 70)

    db = AttackPatternDB()

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    cursor.execute('SELECT DISTINCT venue_code FROM venue_data ORDER BY venue_code')
    venues = [r[0] for r in cursor.fetchall()]

    print(f"\n【会場別パターン (全{len(venues)}会場)】")

    print("\n  ■ 1コース勝率ランキング (Top 5):")
    venue_1c_rates = []
    for vc in venues:
        p = db.get_venue_pattern(vc)
        if p:
            venue_1c_rates.append((vc, p['venue_name'], p['course_win_rates'][0]))
    venue_1c_rates.sort(key=lambda x: -x[2])
    for vc, name, rate in venue_1c_rates[:5]:
        print(f"    {vc} {name}: {rate*100:.1f}%")

    print("\n  ■ 荒れやすい会場 (波乱率 Top 5):")
    upset_venues = db.get_upset_risk_venues(0.40)
    for vc, rate in upset_venues[:5]:
        p = db.get_venue_pattern(vc)
        if p:
            print(f"    {vc} {p['venue_name']}: 波乱率 {rate*100:.1f}%")

    print("\n  ■ 逃げ率ランキング (Top 5):")
    nige_rates = []
    for vc in venues:
        p = db.get_venue_pattern(vc)
        if p:
            nige_rates.append((vc, p['venue_name'], p['nige_rate']))
    nige_rates.sort(key=lambda x: -x[2])
    for vc, name, rate in nige_rates[:5]:
        print(f"    {vc} {name}: 逃げ率 {rate*100:.1f}%")

    print("\n  ■ 差し率ランキング (Top 5):")
    sashi_rates = []
    for vc in venues:
        p = db.get_venue_pattern(vc)
        if p:
            sashi_rates.append((vc, p['venue_name'], p['sashi_rate']))
    sashi_rates.sort(key=lambda x: -x[2])
    for vc, name, rate in sashi_rates[:5]:
        print(f"    {vc} {name}: 差し率 {rate*100:.1f}%")

    print("\n  ■ まくり率ランキング (Top 5):")
    makuri_rates = []
    for vc in venues:
        p = db.get_venue_pattern(vc)
        if p:
            makuri_rates.append((vc, p['venue_name'], p['makuri_rate']))
    makuri_rates.sort(key=lambda x: -x[2])
    for vc, name, rate in makuri_rates[:5]:
        print(f"    {vc} {name}: まくり率 {rate*100:.1f}%")

    conn.close()


def analyze_phase4():
    """Phase 4: 複合ルールの詳細"""
    print("\n" + "=" * 70)
    print("PHASE 4: Compound Rule Finder 詳細")
    print("=" * 70)

    finder = CompoundRuleFinder()
    rules = finder.load_rules()

    if not rules:
        print("ルールが見つかりません。発見中...")
        rules = finder.discover_all_rules()

    print(f"\n【発見ルール総数: {len(rules)}】")

    # カテゴリ分類
    first_place_rules = [r for r in rules if 'C1' in r.rule_id or 'C2' in r.rule_id or 'C3' in r.rule_id]
    second_place_rules = [r for r in rules if 'W' in r.rule_id or '2ND' in r.rule_id]
    upset_rules = [r for r in rules if 'UPSET' in r.rule_id]

    print(f"\n【1着予測ルール: {len(first_place_rules)}件】")
    print("  Top 10 (的中率順):")
    for r in sorted(first_place_rules, key=lambda x: -x.hit_rate)[:10]:
        print(f"    {r.rule_id}: {r.hit_rate*100:.1f}% ({r.total_races}レース)")
        print(f"      条件: {r.description}")

    print(f"\n【2着予測ルール: {len(second_place_rules)}件】")
    print("  Top 10 (的中率順):")
    for r in sorted(second_place_rules, key=lambda x: -x.hit_rate)[:10]:
        print(f"    {r.rule_id}: {r.hit_rate*100:.1f}% ({r.total_races}レース)")
        print(f"      条件: {r.description}")

    print(f"\n【波乱警告ルール: {len(upset_rules)}件】")
    for r in upset_rules:
        print(f"    {r.rule_id}: {r.hit_rate*100:.1f}% ({r.total_races}レース)")
        print(f"      条件: {r.description}")

    # ルールの適用例
    print("\n【ルール適用例】")
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date LIKE '2025-11%'
        LIMIT 3
    ''')
    sample_races = cursor.fetchall()

    for race_id, venue_code, race_date, race_number in sample_races:
        cursor.execute('SELECT venue_name FROM venue_data WHERE venue_code = ? LIMIT 1', (venue_code,))
        vn = cursor.fetchone()
        venue_name = vn[0] if vn else venue_code

        print(f"\n  Race {race_id} ({venue_name} {race_number}R):")
        for pit in range(1, 4):  # 1-3号艇のみチェック
            applicable = finder.get_applicable_rules(race_id, pit)
            if applicable:
                print(f"    Pit {pit}: {len(applicable)}ルール適用")
                for r in applicable[:2]:
                    print(f"      - {r.rule_id}: {r.hit_rate*100:.1f}%")

    conn.close()


def main():
    print("=" * 70)
    print("PHASE 1-4 詳細分析レポート")
    print("=" * 70)

    analyze_phase1()
    analyze_phase2()
    analyze_phase3()
    analyze_phase4()

    print("\n" + "=" * 70)
    print("分析完了")
    print("=" * 70)


if __name__ == "__main__":
    main()
