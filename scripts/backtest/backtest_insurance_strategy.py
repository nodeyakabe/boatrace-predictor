"""
3連単5点+3連複1点 保険戦略バックテスト

戦略:
- 3連単5点買い (500円): 高配当狙い
- 3連複1点買い (100円): 保険（上位3艇BOX）
- 合計投資: 600円/レース

目的:
3連単が外れても3連複で拾って損失を軽減する
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


def get_trifecta_payout(cursor, race_id, combination):
    """3連単払戻金を取得（100円あたり）"""
    try:
        cursor.execute("""
            SELECT amount
            FROM payouts
            WHERE race_id = ?
            AND bet_type = 'trifecta'
            AND combination = ?
        """, (race_id, combination))
        result = cursor.fetchone()
        return int(result[0]) if result else None
    except:
        return None


def get_trio_payout(cursor, race_id, combination):
    """3連複払戻金を取得（100円あたり）"""
    try:
        cursor.execute("""
            SELECT amount
            FROM payouts
            WHERE race_id = ?
            AND bet_type = 'trio'
            AND combination = ?
        """, (race_id, combination))
        result = cursor.fetchone()
        return int(result[0]) if result else None
    except:
        return None


def get_actual_result_trifecta(cursor, race_id):
    """実際のレース結果（3連単: 1-2-3着）を取得"""
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
    """実際のレース結果（3連複: 1-3着の組み合わせ）を取得"""
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
    """金額をフォーマット"""
    return f"¥{amount:,.0f}"


def format_time(seconds):
    """秒数を時:分:秒形式にフォーマット"""
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
    print("3連単5点+3連複1点 保険戦略バックテスト")
    print("=" * 80)
    print()
    print("【購入内容】")
    print("  3連単5点買い: 500円 (高配当狙い)")
    print("  3連複1点買い: 100円 (保険)")
    print("  合計投資: 600円/レース")
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

        # 3連単成績
        'trifecta_hits': 0,
        'trifecta_return': 0,

        # 3連複成績
        'trio_hits': 0,
        'trio_return': 0,

        # 保険効果（3連単外れ & 3連複的中）
        'insurance_saves': 0,
        'insurance_return': 0,

        # 両方的中（ボーナス）
        'both_hits': 0,
        'both_return': 0,

        # 両方外れ
        'both_miss': 0,

        'total_bet': 0,
        'total_return': 0,
        'prediction_errors': 0,
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

            # 進捗表示（50レースごと）
            if total_processed % 50 == 0 or total_processed == 1:
                elapsed = time.time() - start_time
                avg_time = elapsed / total_processed
                remaining = avg_time * (total_races_count - total_processed)

                print(f"  {total_processed}/{total_races_count} ({total_processed/total_races_count*100:.1f}%) | "
                      f"経過: {format_time(elapsed)} | 残り: {format_time(remaining)} | "
                      f"3連単: {stats['trifecta_hits']}件 保険: {stats['insurance_saves']}件")

            try:
                # 予測実行
                predictions = predictor.predict_race_by_key(
                    race_date=race_date,
                    venue_code=venue_code,
                    race_number=race_number
                )

                if not predictions or len(predictions) < 6:
                    stats['prediction_errors'] += 1
                    continue

                stats['valid_predictions'] += 1

                # スコア順にソート
                sorted_predictions = sorted(predictions, key=lambda x: x.get('total_score', 0), reverse=True)
                top_3_pits = [p['pit_number'] for p in sorted_predictions[:3]]

                # 3連単5点の買い目生成
                trifecta_combinations = []
                for perm in permutations(top_3_pits, 3):
                    combination = f"{perm[0]}-{perm[1]}-{perm[2]}"
                    score_sum = sum([sorted_predictions[i]['total_score'] for i, p in enumerate(sorted_predictions[:3]) if p['pit_number'] in perm])
                    trifecta_combinations.append((combination, score_sum))

                trifecta_combinations.sort(key=lambda x: x[1], reverse=True)
                top_5_trifecta = [combo[0] for combo in trifecta_combinations[:5]]

                # 3連複1点の買い目生成（上位3艇BOX）
                top_3_sorted = sorted(top_3_pits)
                trio_combination = f"{top_3_sorted[0]}={top_3_sorted[1]}={top_3_sorted[2]}"

                # 実際の結果を取得
                actual_trifecta = get_actual_result_trifecta(cursor, race_id)
                actual_trio = get_actual_result_trio(cursor, race_id)

                if not actual_trifecta or not actual_trio:
                    continue

                # 投資額（毎レース固定）
                bet_amount = 600  # 3連単500円 + 3連複100円
                stats['total_bet'] += bet_amount

                # 的中判定
                trifecta_hit = actual_trifecta in top_5_trifecta
                trio_hit = actual_trio == trio_combination

                race_return = 0

                if trifecta_hit and trio_hit:
                    # 両方的中（ボーナス）
                    stats['both_hits'] += 1
                    trifecta_payout = get_trifecta_payout(cursor, race_id, actual_trifecta)
                    trio_payout = get_trio_payout(cursor, race_id, actual_trio)
                    if trifecta_payout and trio_payout:
                        race_return = trifecta_payout + trio_payout
                        stats['both_return'] += race_return
                        stats['trifecta_hits'] += 1
                        stats['trio_hits'] += 1

                elif trifecta_hit and not trio_hit:
                    # 3連単のみ的中
                    stats['trifecta_hits'] += 1
                    trifecta_payout = get_trifecta_payout(cursor, race_id, actual_trifecta)
                    if trifecta_payout:
                        race_return = trifecta_payout
                        stats['trifecta_return'] += race_return

                elif not trifecta_hit and trio_hit:
                    # 保険が効いた（3連単外れ & 3連複的中）
                    stats['insurance_saves'] += 1
                    stats['trio_hits'] += 1
                    trio_payout = get_trio_payout(cursor, race_id, actual_trio)
                    if trio_payout:
                        race_return = trio_payout
                        stats['insurance_return'] += race_return

                else:
                    # 両方外れ
                    stats['both_miss'] += 1

                stats['total_return'] += race_return

                # 詳細記録（最初の10件と的中したレースのみ）
                if len(stats['race_details']) < 10 or trifecta_hit or trio_hit:
                    stats['race_details'].append({
                        'race_id': race_id,
                        'date': race_date,
                        'venue': venue_code,
                        'race_no': race_number,
                        'trifecta_predicted': top_5_trifecta,
                        'trio_predicted': trio_combination,
                        'actual_trifecta': actual_trifecta,
                        'actual_trio': actual_trio,
                        'trifecta_hit': trifecta_hit,
                        'trio_hit': trio_hit,
                        'return': race_return,
                        'profit': race_return - bet_amount
                    })

            except Exception as e:
                stats['prediction_errors'] += 1
                continue

    conn.close()

    # 総実行時間
    total_time = time.time() - start_time
    print(f"\n総実行時間: {format_time(total_time)}")
    print(f"平均処理速度: {total_races_count/total_time:.2f}レース/秒")

    # 結果表示
    print("\n" + "=" * 80)
    print("バックテスト結果")
    print("=" * 80)
    print()

    if stats['valid_predictions'] > 0:
        profit = stats['total_return'] - stats['total_bet']
        recovery_rate = (stats['total_return'] / stats['total_bet']) * 100

        print("【全体サマリー】")
        print(f"  総レース数: {stats['total_races']} レース")
        print(f"  予測成功: {stats['valid_predictions']} レース")
        print()

        print("【投資・収支】")
        print(f"  総投資額: {format_currency(stats['total_bet'])} (600円 × {stats['valid_predictions']}レース)")
        print(f"  総払戻額: {format_currency(stats['total_return'])}")
        print(f"  総収支: {format_currency(profit)} ({'黒字' if profit >= 0 else '赤字'})")
        print(f"  回収率: {recovery_rate:.2f}%")
        print()

        print("【的中状況】")
        print(f"  3連単的中: {stats['trifecta_hits']}件 ({stats['trifecta_hits']/stats['valid_predictions']*100:.2f}%)")
        print(f"  3連複的中: {stats['trio_hits']}件 ({stats['trio_hits']/stats['valid_predictions']*100:.2f}%)")
        print()
        print(f"  両方的中（ボーナス）: {stats['both_hits']}件 ({stats['both_hits']/stats['valid_predictions']*100:.2f}%)")
        print(f"    └ 払戻額: {format_currency(stats['both_return'])}")
        print()
        print(f"  保険効果（3連単外れ→3連複的中）: {stats['insurance_saves']}件 ({stats['insurance_saves']/stats['valid_predictions']*100:.2f}%)")
        print(f"    └ 払戻額: {format_currency(stats['insurance_return'])}")
        print(f"    └ 損失軽減効果: {format_currency(stats['insurance_return'] - stats['insurance_saves']*600)}")
        print()
        print(f"  両方外れ: {stats['both_miss']}件 ({stats['both_miss']/stats['valid_predictions']*100:.2f}%)")
        print()

        # 保険戦略の効果分析
        print("【保険戦略の効果】")

        # 3連単単体の成績（仮想）
        trifecta_only_bet = stats['valid_predictions'] * 500
        trifecta_only_return = stats['trifecta_return'] + stats['both_return']
        trifecta_only_profit = trifecta_only_return - trifecta_only_bet
        trifecta_only_recovery = (trifecta_only_return / trifecta_only_bet) * 100

        print(f"  3連単単体（500円）の場合:")
        print(f"    投資: {format_currency(trifecta_only_bet)}")
        print(f"    払戻: {format_currency(trifecta_only_return)}")
        print(f"    収支: {format_currency(trifecta_only_profit)}")
        print(f"    回収率: {trifecta_only_recovery:.2f}%")
        print()

        print(f"  保険付き（3連単500円+3連複100円）の場合:")
        print(f"    投資: {format_currency(stats['total_bet'])}")
        print(f"    払戻: {format_currency(stats['total_return'])}")
        print(f"    収支: {format_currency(profit)}")
        print(f"    回収率: {recovery_rate:.2f}%")
        print()

        improvement = profit - trifecta_only_profit
        print(f"  保険効果による収支改善: {format_currency(improvement)}")
        print(f"  保険効果による回収率変化: {recovery_rate - trifecta_only_recovery:+.2f}%")
        print()

        # サンプル表示
        print("【予測サンプル（的中レースから5件）】")
        hit_samples = [d for d in stats['race_details'] if d['trifecta_hit'] or d['trio_hit']][:5]

        for detail in hit_samples:
            print(f"\n  レース: {detail['date']} {detail['venue']}場 {detail['race_no']}R")
            print(f"  3連単予測: {', '.join(detail['trifecta_predicted'])}")
            print(f"  3連複予測: {detail['trio_predicted']}")
            print(f"  実際結果: 3連単={detail['actual_trifecta']}, 3連複={detail['actual_trio']}")

            if detail['trifecta_hit'] and detail['trio_hit']:
                print(f"  結果: ✓両方的中 払戻{format_currency(detail['return'])} 収支{format_currency(detail['profit'])}")
            elif detail['trifecta_hit']:
                print(f"  結果: ✓3連単的中 払戻{format_currency(detail['return'])} 収支{format_currency(detail['profit'])}")
            elif detail['trio_hit']:
                print(f"  結果: ✓保険効果 払戻{format_currency(detail['return'])} 収支{format_currency(detail['profit'])}")
        print()

        # 結果をJSONで保存
        output_file = 'temp/backtest_insurance_strategy_result.json'
        os.makedirs('temp', exist_ok=True)

        result_data = {
            'test_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_time_seconds': total_time,
            'strategy': '3連単5点(500円) + 3連複1点(100円)',
            'total_races': stats['valid_predictions'],
            'total_bet': stats['total_bet'],
            'total_return': stats['total_return'],
            'profit': profit,
            'recovery_rate': recovery_rate,
            'trifecta_hits': stats['trifecta_hits'],
            'trio_hits': stats['trio_hits'],
            'both_hits': stats['both_hits'],
            'insurance_saves': stats['insurance_saves'],
            'both_miss': stats['both_miss'],
            'trifecta_only_recovery': trifecta_only_recovery,
            'insurance_improvement': improvement
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        print(f"詳細結果を保存しました: {output_file}")
        print()

    else:
        print("予測可能なレースがありませんでした。")

    print("=" * 80)


if __name__ == '__main__':
    main()
