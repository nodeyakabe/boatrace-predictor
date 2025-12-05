"""
3連複バックテストスクリプト（高速版）

処理速度向上の最適化:
1. 予測エンジンの再利用（初期化を1回のみ）
2. バッチキャッシュの効率的な利用
3. 進捗表示の最適化
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
from itertools import combinations
import json
import time


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


def get_actual_result_trio(cursor, race_id):
    """実際のレース結果（1-3着の組み合わせ）を取得"""
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


def generate_trio_combinations(sorted_predictions, strategy='balanced'):
    """3連複の買い目を生成"""
    if strategy == 'safe':
        top_3 = sorted([p['pit_number'] for p in sorted_predictions[:3]])
        return [f"{top_3[0]}={top_3[1]}={top_3[2]}"]
    elif strategy == 'balanced':
        top_4 = [p['pit_number'] for p in sorted_predictions[:4]]
        combos = []
        for combo in combinations(top_4, 3):
            sorted_combo = sorted(combo)
            combos.append(f"{sorted_combo[0]}={sorted_combo[1]}={sorted_combo[2]}")
        return combos
    elif strategy == 'wide':
        top_5 = [p['pit_number'] for p in sorted_predictions[:5]]
        combos = []
        for combo in combinations(top_5, 3):
            sorted_combo = sorted(combo)
            combos.append(f"{sorted_combo[0]}={sorted_combo[1]}={sorted_combo[2]}")
        return combos
    return []


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
    print("3連複バックテスト（高速版）")
    print("=" * 80)
    print()

    db_path = 'data/boatrace.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # テスト対象レースを取得（過去6ヶ月から1000レース）
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
            WHERE p.race_id = r.id AND p.bet_type = 'trio'
        )
        AND r.race_date >= date('now', '-6 months')
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT 1000
    """)
    all_races = cursor.fetchall()

    print(f"テスト対象: {len(all_races)}レース")
    print(f"期間: {all_races[-1][1]} 〜 {all_races[0][1]}")
    print()

    # 予測エンジンを1回だけ初期化（重要: use_cache=Trueで効率化）
    print("予測エンジン初期化中...")
    predictor = RacePredictor(db_path=db_path, use_cache=True)
    print("初期化完了\n")

    # 戦略定義
    strategies = {
        'safe': {'name': '堅実型(1点)', 'points': 1},
        'balanced': {'name': 'バランス型(4点)', 'points': 4},
        'wide': {'name': '広めカバー型(10点)', 'points': 10}
    }

    # 統計データ初期化
    strategy_stats = {}
    for key in strategies.keys():
        strategy_stats[key] = {
            'total_races': 0,
            'valid_predictions': 0,
            'hits': 0,
            'total_bet': 0,
            'total_return': 0,
            'payout_available': 0,
            'prediction_errors': 0
        }

    print("予測実行中...\n")
    start_time = time.time()

    # 日付ごとにグループ化して処理（BatchDataLoaderの効率化）
    races_by_date = defaultdict(list)
    for race_id, race_date, venue_code, race_number in all_races:
        races_by_date[race_date].append((race_id, race_date, venue_code, race_number))

    total_processed = 0
    total_races_count = len(all_races)

    for date_idx, (target_date, races_on_date) in enumerate(sorted(races_by_date.items()), 1):
        date_start_time = time.time()

        # 日付ごとのバッチロード（BatchDataLoaderが自動的にキャッシュを使う）
        if predictor.batch_loader:
            predictor.batch_loader.load_daily_data(target_date)

        for race_id, race_date, venue_code, race_number in races_on_date:
            total_processed += 1

            # 進捗表示（50レースごと）
            if total_processed % 50 == 0 or total_processed == 1:
                elapsed = time.time() - start_time
                avg_time = elapsed / total_processed
                remaining = avg_time * (total_races_count - total_processed)
                total_hits = sum(s['hits'] for s in strategy_stats.values())

                print(f"  {total_processed}/{total_races_count} ({total_processed/total_races_count*100:.1f}%) | "
                      f"経過: {format_time(elapsed)} | 残り: {format_time(remaining)} | "
                      f"的中: {total_hits}件 | 速度: {1/avg_time:.1f}レース/秒")

            try:
                # 予測実行（エンジンは再利用）
                predictions = predictor.predict_race_by_key(
                    race_date=race_date,
                    venue_code=venue_code,
                    race_number=race_number
                )

                if not predictions or len(predictions) < 6:
                    for key in strategies.keys():
                        strategy_stats[key]['prediction_errors'] += 1
                    continue

                sorted_predictions = sorted(predictions, key=lambda x: x.get('total_score', 0), reverse=True)
                actual_result = get_actual_result_trio(cursor, race_id)

                if not actual_result:
                    continue

                # 各戦略で検証
                for strategy_key, strategy_info in strategies.items():
                    stats = strategy_stats[strategy_key]
                    stats['total_races'] += 1

                    trio_combinations = generate_trio_combinations(sorted_predictions, strategy_key)
                    if not trio_combinations:
                        stats['prediction_errors'] += 1
                        continue

                    stats['valid_predictions'] += 1
                    bet_amount = 100 * len(trio_combinations)
                    stats['total_bet'] += bet_amount

                    is_hit = actual_result in trio_combinations
                    if is_hit:
                        stats['hits'] += 1
                        payout_value = get_trio_payout(cursor, race_id, actual_result)
                        if payout_value:
                            stats['total_return'] += payout_value
                            stats['payout_available'] += 1

            except Exception as e:
                for key in strategies.keys():
                    strategy_stats[key]['prediction_errors'] += 1
                continue

    conn.close()

    # 総実行時間
    total_time = time.time() - start_time
    print(f"\n総実行時間: {format_time(total_time)}")
    print(f"平均処理速度: {total_races_count/total_time:.2f}レース/秒")

    # 結果表示
    print("\n" + "=" * 80)
    print("バックテスト結果比較")
    print("=" * 80)
    print()

    results_summary = []
    for strategy_key, strategy_info in strategies.items():
        stats = strategy_stats[strategy_key]

        if stats['valid_predictions'] > 0:
            hit_rate = (stats['hits'] / stats['valid_predictions']) * 100
            recovery_rate = (stats['total_return'] / stats['total_bet']) * 100 if stats['total_bet'] > 0 else 0
            profit = stats['total_return'] - stats['total_bet']
            avg_payout = stats['total_return'] / stats['hits'] if stats['hits'] > 0 else 0

            results_summary.append({
                'strategy': strategy_info['name'],
                'points': strategy_info['points'],
                'races': stats['valid_predictions'],
                'hits': stats['hits'],
                'hit_rate': hit_rate,
                'total_bet': stats['total_bet'],
                'total_return': stats['total_return'],
                'profit': profit,
                'recovery_rate': recovery_rate,
                'avg_payout': avg_payout
            })

    # 結果表示
    print("【戦略別成績一覧】")
    print()
    print(f"{'戦略':<20} {'点数':<6} {'的中数':<10} {'的中率':<10} {'購入額':<15} {'払戻額':<15} {'収支':<15} {'回収率':<10}")
    print("-" * 120)

    for result in results_summary:
        print(f"{result['strategy']:<20} "
              f"{result['points']:<6} "
              f"{result['hits']}/{result['races']:<7} "
              f"{result['hit_rate']:>6.2f}% "
              f"{format_currency(result['total_bet']):<15} "
              f"{format_currency(result['total_return']):<15} "
              f"{format_currency(result['profit']):<15} "
              f"{result['recovery_rate']:>6.2f}%")

    print()

    # 詳細分析
    print("【詳細分析】")
    print()

    for result in results_summary:
        print(f"■ {result['strategy']}")
        print(f"  投資効率: 1レースあたり{result['points']*100}円")
        print(f"  的中率: {result['hit_rate']:.2f}%")
        print(f"  平均配当: {result['avg_payout']:.0f}円")
        print(f"  回収率: {result['recovery_rate']:.2f}%")
        print(f"  総収支: {format_currency(result['profit'])}")

        investment_per_race = result['points'] * 100
        if result['avg_payout'] > 0:
            breakeven = (investment_per_race / result['avg_payout']) * 100
            print(f"  損益分岐点: {breakeven:.2f}%")
            if result['hit_rate'] > breakeven:
                print(f"  ✓ 的中率が損益分岐点を{result['hit_rate'] - breakeven:.2f}%上回っています")
            else:
                print(f"  ✗ 的中率が損益分岐点を{breakeven - result['hit_rate']:.2f}%下回っています")
        print()

    # 推奨戦略
    print("【推奨戦略】")
    print()

    best_by_recovery = max(results_summary, key=lambda x: x['recovery_rate'])
    best_by_profit = max(results_summary, key=lambda x: x['profit'])

    print(f"回収率最優秀: {best_by_recovery['strategy']} (回収率{best_by_recovery['recovery_rate']:.2f}%)")
    print(f"総利益最大: {best_by_profit['strategy']} (利益{format_currency(best_by_profit['profit'])})")
    print()

    # 結果をJSONで保存
    output_file = 'temp/backtest_3fuku_comparison_result.json'
    os.makedirs('temp', exist_ok=True)

    result_data = {
        'test_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_time_seconds': total_time,
        'avg_speed_per_race': total_races_count / total_time,
        'strategies': results_summary
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"詳細結果を保存しました: {output_file}")
    print()
    print("=" * 80)


if __name__ == '__main__':
    main()
