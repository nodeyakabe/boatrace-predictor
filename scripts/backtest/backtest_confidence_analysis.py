"""
信頼度別的中率分析バックテスト

予測の信頼度指標を計算し、信頼度ごとの的中率・回収率を分析。
購入判断基準の最適化を目指す。

信頼度指標:
1. トップスコア差 (1位と2位のスコア差)
2. 上位3艇の平均スコア
3. 1位の絶対スコア
4. スコアの標準偏差
"""

import sys
import os
import io

# 文字コード問題を回避
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


def calculate_confidence_metrics(sorted_predictions):
    """予測の信頼度指標を計算"""
    if len(sorted_predictions) < 3:
        return None

    scores = [p.get('total_score', 0) for p in sorted_predictions]

    metrics = {
        # 1位と2位のスコア差（大きいほど確信度が高い）
        'top_gap': scores[0] - scores[1] if len(scores) >= 2 else 0,

        # 1位と3位のスコア差
        'top_3rd_gap': scores[0] - scores[2] if len(scores) >= 3 else 0,

        # 上位3艇の平均スコア（高いほど全体的に強い）
        'top3_avg': sum(scores[:3]) / 3,

        # 1位の絶対スコア
        'top1_score': scores[0],

        # 全艇のスコア標準偏差（大きいほど力の差が明確）
        'score_std': statistics.stdev(scores) if len(scores) >= 2 else 0,

        # 上位3艇のスコア標準偏差（小さいほど接戦）
        'top3_std': statistics.stdev(scores[:3]) if len(scores) >= 3 else 0,
    }

    return metrics


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
    print("信頼度別的中率分析バックテスト")
    print("=" * 80)
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

    # 全レースの結果を収集
    race_results = []

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

            # 進捗表示
            if total_processed % 50 == 0 or total_processed == 1:
                elapsed = time.time() - start_time
                avg_time = elapsed / total_processed
                remaining = avg_time * (total_races_count - total_processed)

                print(f"  {total_processed}/{total_races_count} ({total_processed/total_races_count*100:.1f}%) | "
                      f"経過: {format_time(elapsed)} | 残り: {format_time(remaining)}")

            try:
                predictions = predictor.predict_race_by_key(
                    race_date=race_date,
                    venue_code=venue_code,
                    race_number=race_number
                )

                if not predictions or len(predictions) < 6:
                    continue

                sorted_predictions = sorted(predictions, key=lambda x: x.get('total_score', 0), reverse=True)

                # 信頼度指標を計算
                confidence = calculate_confidence_metrics(sorted_predictions)
                if not confidence:
                    continue

                # 3連単5点の買い目生成
                top_3_pits = [p['pit_number'] for p in sorted_predictions[:3]]
                trifecta_combinations = []
                for perm in permutations(top_3_pits, 3):
                    combination = f"{perm[0]}-{perm[1]}-{perm[2]}"
                    trifecta_combinations.append(combination)

                top_5_trifecta = trifecta_combinations[:5]

                # 実際の結果
                actual_result = get_actual_result_trifecta(cursor, race_id)
                if not actual_result:
                    continue

                # 的中判定
                is_hit = actual_result in top_5_trifecta
                payout = 0
                if is_hit:
                    payout_value = get_trifecta_payout(cursor, race_id, actual_result)
                    if payout_value:
                        payout = payout_value

                race_results.append({
                    'race_id': race_id,
                    'date': race_date,
                    'confidence': confidence,
                    'is_hit': is_hit,
                    'payout': payout
                })

            except Exception as e:
                continue

    conn.close()

    total_time = time.time() - start_time
    print(f"\n総実行時間: {format_time(total_time)}")
    print(f"有効レース数: {len(race_results)}レース")
    print()

    # 信頼度別に分析
    print("=" * 80)
    print("信頼度別分析結果")
    print("=" * 80)
    print()

    # 各指標でグループ分け
    confidence_groups = {
        'top_gap': [
            ('非常に低い', lambda x: x < 5),
            ('低い', lambda x: 5 <= x < 10),
            ('中程度', lambda x: 10 <= x < 15),
            ('高い', lambda x: 15 <= x < 20),
            ('非常に高い', lambda x: x >= 20),
        ],
        'top_3rd_gap': [
            ('非常に低い', lambda x: x < 10),
            ('低い', lambda x: 10 <= x < 20),
            ('中程度', lambda x: 20 <= x < 30),
            ('高い', lambda x: 30 <= x < 40),
            ('非常に高い', lambda x: x >= 40),
        ],
        'top1_score': [
            ('非常に低い', lambda x: x < 50),
            ('低い', lambda x: 50 <= x < 60),
            ('中程度', lambda x: 60 <= x < 70),
            ('高い', lambda x: 70 <= x < 80),
            ('非常に高い', lambda x: x >= 80),
        ],
        'score_std': [
            ('非常に低い', lambda x: x < 5),
            ('低い', lambda x: 5 <= x < 10),
            ('中程度', lambda x: 10 <= x < 15),
            ('高い', lambda x: 15 <= x < 20),
            ('非常に高い', lambda x: x >= 20),
        ],
    }

    for metric_name, groups in confidence_groups.items():
        print(f"【{metric_name} (指標名)】")
        print()
        print(f"{'信頼度':<15} {'レース数':<10} {'的中数':<10} {'的中率':<10} {'購入額':<12} {'払戻額':<12} {'回収率':<10}")
        print("-" * 85)

        for group_name, condition in groups:
            group_races = [r for r in race_results if condition(r['confidence'][metric_name])]

            if len(group_races) == 0:
                continue

            total_races = len(group_races)
            hits = sum(1 for r in group_races if r['is_hit'])
            hit_rate = (hits / total_races) * 100 if total_races > 0 else 0

            total_bet = total_races * 500
            total_return = sum(r['payout'] for r in group_races)
            recovery_rate = (total_return / total_bet) * 100 if total_bet > 0 else 0

            print(f"{group_name:<15} {total_races:<10} {hits:<10} {hit_rate:>6.2f}% "
                  f"{format_currency(total_bet):<12} {format_currency(total_return):<12} {recovery_rate:>6.2f}%")

        print()

    # 推奨基準を提案
    print("=" * 80)
    print("推奨購入基準")
    print("=" * 80)
    print()

    # top_gapで回収率100%超えのグループを探す
    best_groups = []
    for metric_name, groups in confidence_groups.items():
        for group_name, condition in groups:
            group_races = [r for r in race_results if condition(r['confidence'][metric_name])]

            if len(group_races) < 50:  # サンプル数が少なすぎる場合はスキップ
                continue

            total_races = len(group_races)
            hits = sum(1 for r in group_races if r['is_hit'])
            hit_rate = (hits / total_races) * 100

            total_bet = total_races * 500
            total_return = sum(r['payout'] for r in group_races)
            recovery_rate = (total_return / total_bet) * 100

            if recovery_rate >= 100:
                best_groups.append({
                    'metric': metric_name,
                    'group': group_name,
                    'races': total_races,
                    'hit_rate': hit_rate,
                    'recovery_rate': recovery_rate
                })

    if best_groups:
        print("✓ 回収率100%以上のグループ:")
        print()
        for group in sorted(best_groups, key=lambda x: x['recovery_rate'], reverse=True):
            print(f"  【{group['metric']}】 {group['group']}")
            print(f"    レース数: {group['races']}")
            print(f"    的中率: {group['hit_rate']:.2f}%")
            print(f"    回収率: {group['recovery_rate']:.2f}%")
            print()
    else:
        print("✗ 回収率100%以上のグループは見つかりませんでした")
        print()

        # 次善策: 最も回収率が高いグループ
        all_groups = []
        for metric_name, groups in confidence_groups.items():
            for group_name, condition in groups:
                group_races = [r for r in race_results if condition(r['confidence'][metric_name])]

                if len(group_races) < 30:
                    continue

                total_races = len(group_races)
                hits = sum(1 for r in group_races if r['is_hit'])
                hit_rate = (hits / total_races) * 100

                total_bet = total_races * 500
                total_return = sum(r['payout'] for r in group_races)
                recovery_rate = (total_return / total_bet) * 100

                all_groups.append({
                    'metric': metric_name,
                    'group': group_name,
                    'races': total_races,
                    'hit_rate': hit_rate,
                    'recovery_rate': recovery_rate
                })

        if all_groups:
            best = max(all_groups, key=lambda x: x['recovery_rate'])
            print("最も回収率が高いグループ:")
            print()
            print(f"  【{best['metric']}】 {best['group']}")
            print(f"    レース数: {best['races']}")
            print(f"    的中率: {best['hit_rate']:.2f}%")
            print(f"    回収率: {best['recovery_rate']:.2f}%")
            print()

    # 結果をJSONで保存
    output_file = 'temp/backtest_confidence_analysis_result.json'
    os.makedirs('temp', exist_ok=True)

    result_data = {
        'test_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_time_seconds': total_time,
        'total_races': len(race_results),
        'race_results': race_results,
        'best_groups': best_groups if best_groups else all_groups[:5]
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"詳細結果を保存しました: {output_file}")
    print()
    print("=" * 80)


if __name__ == '__main__':
    main()
