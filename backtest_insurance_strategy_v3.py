"""
3連単5点+3連複1点 条件付き保険戦略バックテスト v3

改善版:
- 3連単: 全レース購入（500円）
- 3連複: 荒れそうなレースのみ購入（100円）

3連複購入条件（いずれか1つ該当）:
1. 進入変動あり（枠番≠コース番号）
2. ST/展示のバラつき大
3. 1号艇のモーター指数が弱い
"""

import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from datetime import datetime
from src.analysis.race_predictor import RacePredictor
from collections import defaultdict
from itertools import permutations
import json
import time
import statistics


def should_buy_trio_insurance(race_data, predictions, cursor, race_id):
    """
    3連複を購入するか判定

    条件（いずれか1つ該当で購入）:
    1. 進入変動あり
    2. ST/展示のバラつき大
    3. 1号艇のモーター指数が弱い
    """
    reasons = []

    # 条件1: 進入変動あり
    # race_detailsから進入情報を取得
    cursor.execute("""
        SELECT pit_number, actual_course
        FROM race_details
        WHERE race_id = ?
        AND actual_course IS NOT NULL
    """, (race_id,))
    entries = cursor.fetchall()

    has_course_change = False
    if entries:
        for pit, course in entries:
            if pit != course:
                has_course_change = True
                break

    if has_course_change:
        reasons.append("進入変動あり")

    # 条件2: ST/展示のバラつき大
    cursor.execute("""
        SELECT
            exhibition_time,
            st_time
        FROM race_details
        WHERE race_id = ?
        AND exhibition_time IS NOT NULL
        AND st_time IS NOT NULL
    """, (race_id,))

    timing_data = cursor.fetchall()

    if len(timing_data) >= 4:  # 最低4艇のデータが必要
        exhibition_times = [float(t[0]) for t in timing_data if t[0] and float(t[0]) > 0]
        st_timings = [float(t[1]) for t in timing_data if t[1]]

        # 展示タイムのバラつき（標準偏差が0.15以上）
        if len(exhibition_times) >= 4:
            try:
                ex_std = statistics.stdev(exhibition_times)
                if ex_std >= 0.15:
                    reasons.append(f"展示バラつき大(σ={ex_std:.3f})")
            except:
                pass

        # STのバラつき（標準偏差が0.08以上）
        if len(st_timings) >= 4:
            try:
                st_std = statistics.stdev(st_timings)
                if st_std >= 0.08:
                    reasons.append(f"STバラつき大(σ={st_std:.3f})")
            except:
                pass

    # 条件3: 1号艇のモーター指数が弱い
    # Note: motor_2rate, motorsテーブルが存在しないため、この条件は現状スキップ
    # 将来的にデータが揃えば有効化可能

    return len(reasons) > 0, reasons


def calc_third_place_score(prediction):
    """3着専用スコアを計算"""
    base_score = prediction.get('total_score', 0)
    course_score = prediction.get('course_score', 0)
    racer_score = prediction.get('racer_score', 0)
    motor_score = prediction.get('motor_score', 0)

    third_score = base_score

    pit = prediction.get('pit_number', 0)
    if pit in [1, 2]:
        third_score -= course_score * 0.5

    if motor_score > racer_score * 1.2:
        third_score -= (motor_score - racer_score) * 0.3

    return third_score


def get_trifecta_payout(cursor, race_id, combination):
    """3連単払戻金を取得"""
    try:
        cursor.execute("""
            SELECT amount
            FROM payouts
            WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
        """, (race_id, combination))
        result = cursor.fetchone()
        return int(result[0]) if result else None
    except:
        return None


def get_trio_payout(cursor, race_id, combination):
    """3連複払戻金を取得"""
    try:
        cursor.execute("""
            SELECT amount
            FROM payouts
            WHERE race_id = ? AND bet_type = 'trio' AND combination = ?
        """, (race_id, combination))
        result = cursor.fetchone()
        return int(result[0]) if result else None
    except:
        return None


def get_actual_result_trifecta(cursor, race_id):
    """3連単結果を取得"""
    cursor.execute("""
        SELECT pit_number
        FROM results
        WHERE race_id = ? AND is_invalid = 0
        ORDER BY rank
        LIMIT 3
    """, (race_id,))
    results = cursor.fetchall()
    if len(results) >= 3:
        return f"{results[0][0]}-{results[1][0]}-{results[2][0]}"
    return None


def get_actual_result_trio(cursor, race_id):
    """3連複結果を取得"""
    cursor.execute("""
        SELECT pit_number
        FROM results
        WHERE race_id = ? AND rank <= 3 AND is_invalid = 0
        ORDER BY rank
        LIMIT 3
    """, (race_id,))
    results = cursor.fetchall()
    if len(results) >= 3:
        pits = sorted([r[0] for r in results])
        return f"{pits[0]}={pits[1]}={pits[2]}"
    return None


def format_currency(amount):
    return f"¥{amount:,.0f}"


def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}時間{minutes}分{secs}秒"
    elif minutes > 0:
        return f"{minutes}分{secs}秒"
    else:
        return f"{secs}秒"


def main():
    print("=" * 80)
    print("3連単5点+3連複1点 条件付き保険戦略バックテスト v3")
    print("=" * 80)
    print()
    print("【購入内容】")
    print("  3連単5点買い: 500円 (全レース)")
    print("  3連複1点買い: 100円 (条件付き)")
    print()
    print("【3連複購入条件（いずれか該当）】")
    print("  1. 進入変動あり")
    print("  2. ST/展示のバラつき大")
    print("  3. 1号艇のモーター指数が弱い")
    print()

    db_path = 'data/boatrace.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # テスト対象レースを取得
    cursor.execute("""
        SELECT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        WHERE EXISTS (
            SELECT 1 FROM results res
            WHERE res.race_id = r.id AND res.rank IS NOT NULL AND res.is_invalid = 0
        )
        AND EXISTS (
            SELECT 1 FROM race_details rd
            WHERE rd.race_id = r.id
        )
        AND EXISTS (
            SELECT 1 FROM payouts p
            WHERE p.race_id = r.id AND p.bet_type = 'trifecta'
        )
        AND EXISTS (
            SELECT 1 FROM payouts p2
            WHERE p2.race_id = r.id AND p2.bet_type = 'trio'
        )
        AND r.race_date >= date('now', '-6 months')
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT 1000
    """)
    all_races = cursor.fetchall()

    print(f"テスト対象: {len(all_races)}レース")
    print(f"期間: {all_races[-1][1]} 〜 {all_races[0][1]}")
    print()

    # 予測エンジン初期化
    print("予測エンジン初期化中...")
    predictor = RacePredictor(db_path=db_path, use_cache=True)
    print("初期化完了\n")

    # 統計データ
    stats = {
        'total_races': 0,
        'valid_predictions': 0,
        'trio_bought_count': 0,  # 3連複を購入したレース数

        'trifecta_hits': 0,
        'trifecta_return': 0,

        'trio_hits': 0,
        'trio_return': 0,

        'insurance_saves': 0,
        'insurance_return': 0,

        'both_hits': 0,
        'both_return': 0,

        'both_miss': 0,

        'total_bet': 0,
        'total_return': 0,
        'prediction_errors': 0,

        'condition_counts': defaultdict(int),  # 各条件の発生回数
        'race_details': []
    }

    print("予測実行中...\n")
    start_time = time.time()

    # 日付ごとにグループ化
    races_by_date = defaultdict(list)
    for race_id, race_date, venue_code, race_number in all_races:
        races_by_date[race_date].append((race_id, race_date, venue_code, race_number))

    total_processed = 0
    total_races_count = len(all_races)

    for date_idx, (target_date, races_on_date) in enumerate(sorted(races_by_date.items()), 1):
        if predictor.batch_loader:
            predictor.batch_loader.load_daily_data(target_date)

        for race_id, race_date, venue_code, race_number in races_on_date:
            total_processed += 1
            stats['total_races'] += 1

            # 進捗表示
            if total_processed % 50 == 0 or total_processed == 1:
                elapsed = time.time() - start_time
                avg_time = elapsed / total_processed
                remaining = avg_time * (total_races_count - total_processed)

                print(f"  {total_processed}/{total_races_count} ({total_processed/total_races_count*100:.1f}%) | "
                      f"経過: {format_time(elapsed)} | 残り: {format_time(remaining)} | "
                      f"3連単: {stats['trifecta_hits']}件 保険: {stats['insurance_saves']}件 | "
                      f"3連複購入: {stats['trio_bought_count']}レース")

            try:
                predictions = predictor.predict_race_by_key(
                    race_date=race_date,
                    venue_code=venue_code,
                    race_number=race_number
                )

                if not predictions or len(predictions) < 6:
                    stats['prediction_errors'] += 1
                    continue

                stats['valid_predictions'] += 1

                # 3連単の買い目生成
                sorted_predictions = sorted(predictions, key=lambda x: x.get('total_score', 0), reverse=True)
                top_3_pits = [p['pit_number'] for p in sorted_predictions[:3]]

                trifecta_combinations = []
                for perm in permutations(top_3_pits, 3):
                    combination = f"{perm[0]}-{perm[1]}-{perm[2]}"
                    score_sum = sum([sorted_predictions[i]['total_score'] for i, p in enumerate(sorted_predictions[:3]) if p['pit_number'] in perm])
                    trifecta_combinations.append((combination, score_sum))

                trifecta_combinations.sort(key=lambda x: x[1], reverse=True)
                top_5_trifecta = [combo[0] for combo in trifecta_combinations[:5]]

                # 3連複を購入するか判定
                should_buy, reasons = should_buy_trio_insurance(None, predictions, cursor, race_id)

                trio_combination = None
                if should_buy:
                    stats['trio_bought_count'] += 1
                    for reason in reasons:
                        stats['condition_counts'][reason] += 1

                    # 3着専用スコアで3連複の買い目を生成
                    remaining_predictions = [p for p in predictions if p['pit_number'] not in top_3_pits]
                    if len(remaining_predictions) >= 1:
                        for pred in remaining_predictions:
                            pred['third_score'] = calc_third_place_score(pred)
                        sorted_by_third = sorted(remaining_predictions, key=lambda x: x['third_score'], reverse=True)
                        third_candidate = sorted_by_third[0]['pit_number']
                        trio_pits = sorted([top_3_pits[0], top_3_pits[1], third_candidate])
                        trio_combination = f"{trio_pits[0]}={trio_pits[1]}={trio_pits[2]}"

                # 実際の結果を取得
                actual_trifecta = get_actual_result_trifecta(cursor, race_id)
                actual_trio = get_actual_result_trio(cursor, race_id)

                if not actual_trifecta or not actual_trio:
                    continue

                # 投資額
                bet_amount = 500  # 3連単は常に購入
                if should_buy and trio_combination:
                    bet_amount += 100  # 3連複を追加

                stats['total_bet'] += bet_amount

                # 的中判定
                trifecta_hit = actual_trifecta in top_5_trifecta
                trio_hit = (trio_combination == actual_trio) if trio_combination else False

                race_return = 0

                if trifecta_hit and trio_hit:
                    stats['both_hits'] += 1
                    trifecta_payout = get_trifecta_payout(cursor, race_id, actual_trifecta)
                    trio_payout = get_trio_payout(cursor, race_id, actual_trio)
                    if trifecta_payout and trio_payout:
                        race_return = trifecta_payout + trio_payout
                        stats['both_return'] += race_return
                        stats['trifecta_hits'] += 1
                        stats['trio_hits'] += 1

                elif trifecta_hit and not trio_hit:
                    stats['trifecta_hits'] += 1
                    trifecta_payout = get_trifecta_payout(cursor, race_id, actual_trifecta)
                    if trifecta_payout:
                        race_return = trifecta_payout
                        stats['trifecta_return'] += race_return

                elif not trifecta_hit and trio_hit:
                    stats['insurance_saves'] += 1
                    stats['trio_hits'] += 1
                    trio_payout = get_trio_payout(cursor, race_id, actual_trio)
                    if trio_payout:
                        race_return = trio_payout
                        stats['insurance_return'] += race_return

                else:
                    stats['both_miss'] += 1

                stats['total_return'] += race_return

                # 詳細記録（保険効果優先）
                if trio_hit and not trifecta_hit and len(stats['race_details']) < 100:
                    stats['race_details'].append({
                        'race_id': race_id,
                        'date': race_date,
                        'venue': venue_code,
                        'race_no': race_number,
                        'reasons': reasons,
                        'trifecta_hit': trifecta_hit,
                        'trio_hit': trio_hit,
                        'return': race_return,
                        'profit': race_return - bet_amount,
                        'is_insurance': True
                    })

            except Exception as e:
                stats['prediction_errors'] += 1
                continue

    conn.close()

    # 総実行時間
    total_time = time.time() - start_time
    print(f"\n総実行時間: {format_time(total_time)}")

    # 結果表示
    print("\n" + "=" * 80)
    print("バックテスト結果")
    print("=" * 80)
    print()

    if stats['valid_predictions'] > 0:
        profit = stats['total_return'] - stats['total_bet']
        recovery_rate = (stats['total_return'] / stats['total_bet']) * 100 if stats['total_bet'] > 0 else 0

        trio_buy_rate = (stats['trio_bought_count'] / stats['valid_predictions']) * 100

        print("【全体サマリー】")
        print(f"  総レース数: {stats['valid_predictions']} レース")
        print(f"  3連複購入: {stats['trio_bought_count']} レース ({trio_buy_rate:.1f}%)")
        print()

        print("【投資・収支】")
        print(f"  総投資額: {format_currency(stats['total_bet'])}")
        print(f"    └ 3連単: {format_currency(stats['valid_predictions'] * 500)}")
        print(f"    └ 3連複: {format_currency(stats['trio_bought_count'] * 100)}")
        print(f"  総払戻額: {format_currency(stats['total_return'])}")
        print(f"  総収支: {format_currency(profit)} ({'黒字' if profit >= 0 else '赤字'})")
        print(f"  回収率: {recovery_rate:.2f}%")
        print()

        print("【的中状況】")
        print(f"  3連単的中: {stats['trifecta_hits']}件 ({stats['trifecta_hits']/stats['valid_predictions']*100:.2f}%)")
        if stats['trio_bought_count'] > 0:
            print(f"  3連複的中: {stats['trio_hits']}件 ({stats['trio_hits']/stats['trio_bought_count']*100:.2f}% ※購入レースのみ)")
        print()
        print(f"  🎯保険効果: {stats['insurance_saves']}件")
        if stats['insurance_saves'] > 0:
            print(f"    └ 払戻額: {format_currency(stats['insurance_return'])}")
            print(f"    └ 平均配当: {stats['insurance_return']/stats['insurance_saves']:.0f}円")
        print()

        print("【3連複購入条件の発生頻度】")
        for condition, count in sorted(stats['condition_counts'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {condition}: {count}回")
        print()

        # 比較分析
        print("【戦略比較】")

        # 3連単単体
        trifecta_only_bet = stats['valid_predictions'] * 500
        trifecta_only_return = stats['trifecta_return'] + stats['both_return']
        trifecta_only_profit = trifecta_only_return - trifecta_only_bet
        trifecta_only_recovery = (trifecta_only_return / trifecta_only_bet) * 100

        print(f"  3連単単体:")
        print(f"    投資: {format_currency(trifecta_only_bet)}")
        print(f"    収支: {format_currency(trifecta_only_profit)}")
        print(f"    回収率: {trifecta_only_recovery:.2f}%")
        print()

        print(f"  条件付き保険:")
        print(f"    投資: {format_currency(stats['total_bet'])}")
        print(f"    収支: {format_currency(profit)}")
        print(f"    回収率: {recovery_rate:.2f}%")
        print()

        improvement = profit - trifecta_only_profit
        print(f"  💡改善効果: {format_currency(improvement)} ({improvement/trifecta_only_bet*100:+.2f}%)")

        if improvement > 0:
            print(f"  ✓ 条件付き保険が有効です！")
        else:
            print(f"  ✗ 依然として改善が必要です")
        print()

        # 保険効果サンプル
        insurance_samples = [d for d in stats['race_details'] if d.get('is_insurance', False)][:5]
        if insurance_samples:
            print(f"【保険効果サンプル（{len(insurance_samples)}件）】")
            for detail in insurance_samples:
                print(f"\n  レース: {detail['date']} {detail['venue']}場 {detail['race_no']}R")
                print(f"  条件: {', '.join(detail['reasons'])}")
                print(f"  結果: ✓保険効果 払戻{format_currency(detail['return'])} 収支{format_currency(detail['profit'])}")
            print()

        # 結果保存
        output_file = 'temp/backtest_insurance_strategy_v3_result.json'
        os.makedirs('temp', exist_ok=True)

        result_data = {
            'test_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_time_seconds': total_time,
            'strategy': '3連単5点(500円) + 条件付き3連複1点(100円)',
            'total_races': stats['valid_predictions'],
            'trio_bought_count': stats['trio_bought_count'],
            'trio_buy_rate': trio_buy_rate,
            'total_bet': stats['total_bet'],
            'total_return': stats['total_return'],
            'profit': profit,
            'recovery_rate': recovery_rate,
            'trifecta_hits': stats['trifecta_hits'],
            'trio_hits': stats['trio_hits'],
            'insurance_saves': stats['insurance_saves'],
            'trifecta_only_recovery': trifecta_only_recovery,
            'insurance_improvement': improvement,
            'condition_counts': dict(stats['condition_counts'])
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        print(f"詳細結果を保存しました: {output_file}")
        print()

    print("=" * 80)


if __name__ == '__main__':
    main()
