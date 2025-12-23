# -*- coding: utf-8 -*-
"""
Phase 1-4 Integration Test

All modules integration and verification
"""

import sqlite3
import sys
sys.path.insert(0, '.')

from src.analysis import MissPatternAnalyzer, CompoundRuleFinder
from src.database import AttackPatternDB, PatternBasedPredictor
from src.second_model import SecondFeaturesGenerator


def test_phase1_miss_pattern():
    """Phase 1: Miss Pattern Analyzer"""
    print("\n" + "=" * 70)
    print("Phase 1: Miss Pattern Analyzer")
    print("=" * 70)

    analyzer = MissPatternAnalyzer()

    # Analyze 2nd place miss patterns for November 2025
    print("Analyzing 2nd place miss patterns...")
    results = analyzer.analyze_second_place_misses(
        start_date='2025-11-01',
        end_date='2025-11-30'
    )

    print(f"  Total races: {results['total_races']}")
    print(f"  1st place hits: {results['hit_1st_races']}")
    if results['hit_1st_races'] > 0:
        miss_rate = results['miss_2nd_in_234'] / results['hit_1st_races'] * 100
        print(f"  2nd place miss (not in 234): {results['miss_2nd_in_234']} ({miss_rate:.1f}%)")

    print("[OK] Phase 1 test passed")
    return True


def test_phase2_second_features():
    """Phase 2: Second Place Features"""
    print("\n" + "=" * 70)
    print("Phase 2: Second Place Features Generator")
    print("=" * 70)

    generator = SecondFeaturesGenerator()

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.id, res.pit_number as winner_pit
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE r.race_date LIKE '2025-11%' AND res.rank = 1
        LIMIT 3
    ''')
    races = cursor.fetchall()

    print(f"Testing with {len(races)} sample races...")

    for race_id, winner_pit in races:
        candidates = generator.rank_second_candidates(race_id, winner_pit)
        if candidates:
            print(f"  Race {race_id}, Winner Pit {winner_pit}:")
            for i, (pit, score) in enumerate(candidates[:3], 1):
                print(f"    {i}. Pit {pit}: Score {score:.2f}")

            # Check actual result
            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND rank = 2
            ''', (race_id,))
            actual = cursor.fetchone()
            if actual:
                print(f"    -> Actual 2nd: Pit {actual[0]}")

    conn.close()
    print("[OK] Phase 2 test passed")
    return True


def test_phase3_attack_patterns():
    """Phase 3: Attack Pattern DB"""
    print("\n" + "=" * 70)
    print("Phase 3: Attack Pattern Database")
    print("=" * 70)

    db = AttackPatternDB()

    # Test venue patterns
    print("\nVenue Patterns:")
    for vc in ['01', '12', '24']:
        p = db.get_venue_pattern(vc)
        if p:
            print(f"  [{vc}] {p['venue_name']}")
            print(f"    1C Win: {p['course_win_rates'][0]*100:.1f}%")
            print(f"    Upset Rate: {p['upset_rate']*100:.1f}%")
            print(f"    Nige Rate: {p['nige_rate']*100:.1f}%")

    # Test upset risk venues
    print("\nHigh Upset Risk Venues:")
    upset_venues = db.get_upset_risk_venues(0.50)
    for vc, rate in upset_venues[:3]:
        p = db.get_venue_pattern(vc)
        if p:
            print(f"  [{vc}] {p['venue_name']}: {rate*100:.1f}%")

    # Test pattern-based predictor
    print("\nPattern-Based Predictor:")
    predictor = PatternBasedPredictor()

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM races WHERE race_date LIKE '2025-11%' LIMIT 1
    ''')
    race = cursor.fetchone()
    conn.close()

    if race:
        base_scores = {1: 10.0, 2: 8.0, 3: 6.0, 4: 5.0, 5: 4.0, 6: 3.0}
        adjusted = predictor.get_prediction_adjustments(race[0], base_scores)
        print(f"  Race {race[0]} adjustments:")
        for pit, score in sorted(adjusted.items()):
            print(f"    Pit {pit}: {base_scores[pit]:.1f} -> {score:.1f}")

    print("[OK] Phase 3 test passed")
    return True


def test_phase4_compound_rules():
    """Phase 4: Compound Rule Finder"""
    print("\n" + "=" * 70)
    print("Phase 4: Compound Rule Finder")
    print("=" * 70)

    finder = CompoundRuleFinder()

    # Load existing rules
    rules = finder.load_rules()
    print(f"Loaded {len(rules)} rules from database")

    if not rules:
        print("No rules found, discovering...")
        rules = finder.discover_all_rules()

    # Show top rules by category
    first_place_rules = [r for r in rules if 'C1' in r.rule_id or 'C2' in r.rule_id]
    second_place_rules = [r for r in rules if 'W' in r.rule_id or '2ND' in r.rule_id]
    upset_rules = [r for r in rules if 'UPSET' in r.rule_id]

    print(f"\n1st Place Rules: {len(first_place_rules)}")
    for r in sorted(first_place_rules, key=lambda x: -x.hit_rate)[:3]:
        print(f"  {r.rule_id}: {r.hit_rate*100:.1f}% ({r.total_races} races)")

    print(f"\n2nd Place Rules: {len(second_place_rules)}")
    for r in sorted(second_place_rules, key=lambda x: -x.hit_rate)[:3]:
        print(f"  {r.rule_id}: {r.hit_rate*100:.1f}% ({r.total_races} races)")

    print(f"\nUpset Warning Rules: {len(upset_rules)}")
    for r in upset_rules:
        print(f"  {r.rule_id}: {r.hit_rate*100:.1f}% ({r.total_races} races)")

    # Test rule application
    print("\nTesting rule application...")
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM races WHERE race_date LIKE '2025-11%' LIMIT 1
    ''')
    race = cursor.fetchone()
    conn.close()

    if race:
        applicable = finder.get_applicable_rules(race[0], 1)
        print(f"  Race {race[0]}, Pit 1: {len(applicable)} rules apply")
        for r in applicable[:3]:
            print(f"    - {r.rule_id}: {r.hit_rate*100:.1f}%")

    print("[OK] Phase 4 test passed")
    return True


def test_integrated_prediction():
    """Integrated prediction using all phases"""
    print("\n" + "=" * 70)
    print("INTEGRATED PREDICTION TEST")
    print("=" * 70)

    # Initialize all components
    attack_db = AttackPatternDB()
    second_gen = SecondFeaturesGenerator()
    rule_finder = CompoundRuleFinder()
    predictor = PatternBasedPredictor()

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # Get races with results
    cursor.execute('''
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date LIKE '2025-11%'
        LIMIT 5
    ''')
    races = cursor.fetchall()

    hits_1st = 0
    hits_2nd = 0
    total = 0

    for race_id, venue_code, race_date, race_number in races:
        # Get venue pattern
        venue_pattern = attack_db.get_venue_pattern(venue_code)

        # Get actual results
        cursor.execute('''
            SELECT pit_number, rank FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) < 3:
            continue

        actual_1st = results[0][0]
        actual_2nd = results[1][0]

        # Get applicable rules for pit 1
        rules_pit1 = rule_finder.get_applicable_rules(race_id, 1)

        # Simple prediction: if high confidence rules apply to pit 1, predict pit 1
        pred_1st = 1 if any(r.hit_rate >= 0.65 for r in rules_pit1) else None

        # If no strong rule, use venue pattern
        if pred_1st is None and venue_pattern:
            best_course = max(range(6), key=lambda i: venue_pattern['course_win_rates'][i]) + 1
            pred_1st = best_course

        if pred_1st is None:
            pred_1st = 1  # default

        # Second place prediction using SecondFeaturesGenerator
        second_candidates = second_gen.rank_second_candidates(race_id, pred_1st)
        pred_2nd = second_candidates[0][0] if second_candidates else 2

        # Check accuracy
        hit_1st = (pred_1st == actual_1st)
        hit_2nd = (pred_2nd == actual_2nd) if hit_1st else False

        if hit_1st:
            hits_1st += 1
        if hit_2nd:
            hits_2nd += 1
        total += 1

        print(f"Race {race_id} ({venue_code}): Pred={pred_1st}-{pred_2nd}, Actual={actual_1st}-{actual_2nd}"
              f" [1st:{'O' if hit_1st else 'X'}, 2nd:{'O' if hit_2nd else 'X'}]")

    conn.close()

    if total > 0:
        print(f"\nResults: 1st Hit {hits_1st}/{total} ({hits_1st/total*100:.1f}%), "
              f"2nd Hit {hits_2nd}/{total} ({hits_2nd/total*100:.1f}%)")

    print("[OK] Integrated test passed")
    return True


def main():
    print("=" * 70)
    print("PHASE 1-4 INTEGRATION TEST")
    print("=" * 70)

    results = []

    try:
        results.append(("Phase 1: Miss Pattern", test_phase1_miss_pattern()))
    except Exception as e:
        print(f"[ERROR] Phase 1 failed: {e}")
        results.append(("Phase 1: Miss Pattern", False))

    try:
        results.append(("Phase 2: Second Features", test_phase2_second_features()))
    except Exception as e:
        print(f"[ERROR] Phase 2 failed: {e}")
        results.append(("Phase 2: Second Features", False))

    try:
        results.append(("Phase 3: Attack Patterns", test_phase3_attack_patterns()))
    except Exception as e:
        print(f"[ERROR] Phase 3 failed: {e}")
        results.append(("Phase 3: Attack Patterns", False))

    try:
        results.append(("Phase 4: Compound Rules", test_phase4_compound_rules()))
    except Exception as e:
        print(f"[ERROR] Phase 4 failed: {e}")
        results.append(("Phase 4: Compound Rules", False))

    try:
        results.append(("Integrated Prediction", test_integrated_prediction()))
    except Exception as e:
        print(f"[ERROR] Integrated test failed: {e}")
        results.append(("Integrated Prediction", False))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    all_passed = all(r[1] for r in results)
    print("\n" + ("ALL TESTS PASSED!" if all_passed else "SOME TESTS FAILED"))
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
