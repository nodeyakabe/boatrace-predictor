"""
3連複バックテストスクリプト（複数戦略比較）- 進捗表示強化版

現在の予想ロジックで3連複の各戦略を比較検証:
1. 堅実型（上位3艇BOX: 1点）
2. バランス型（上位4艇から3艇: 4点）
3. 広めカバー型（上位5艇から3艇: 10点）
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
        # combination は "1=2=3" の形式
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
        # 3連複は順不同なのでソート
        pits = sorted([r[0] for r in results])
        return f"{pits[0]}={pits[1]}={pits[2]}"
    return None


def generate_trio_combinations(sorted_predictions, strategy='balanced'):
    """
    3連複の買い目を生成

    Args:
        sorted_predictions: スコア順にソートされた予測リスト
        strategy: 'safe'(1点), 'balanced'(4点), 'wide'(10点)

    Returns:
        買い目のリスト（例: ['1=2=3', '1=2=4', ...]）
    """
    if strategy == 'safe':
        # 上位3艇のみ（1点）
        top_3 = sorted([p['pit_number'] for p in sorted_predictions[:3]])
        return [f"{top_3[0]}={top_3[1]}={top_3[2]}"]

    elif strategy == 'balanced':
        # 上位4艇から3艇を選ぶ（4点）
        top_4 = [p['pit_number'] for p in sorted_predictions[:4]]
        combos = []
        for combo in combinations(top_4, 3):
            sorted_combo = sorted(combo)
            combos.append(f"{sorted_combo[0]}={sorted_combo[1]}={sorted_combo[2]}")
        return combos

    elif strategy == 'wide':
        # 上位5艇から3艇を選ぶ（10点）
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
    print("3連複バックテスト（複数戦略比較）- 進捗表示強化版")
    print("=" * 80)
    print()

    db_path = 'data/boatrace.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # テスト期間を設定（過去6ヶ月分から1000レースサンプリング）
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

    # 予測エンジン初期化
    predictor = RacePredictor(db_path=db_path)

    # 3つの戦略を同時にテスト
    strategies = {
        'safe': {'name': '堅実型(1点)', 'points': 1},
        'balanced': {'name': 'バランス型(4点)', 'points': 4},
        'wide': {'name': '広めカバー型(10点)', 'points': 10}
    }

    # 各戦略の統計データ
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

    # 開始時刻記録
    start_time = time.time()
    last_update_time = start_time

    for idx, (race_id, race_date, venue_code, race_number) in enumerate(all_races, 1):

        # 進捗表示（10レースごと）
        if idx % 10 == 0 or idx == 1:
            current_time = time.time()
            elapsed_time = current_time - start_time
            avg_time_per_race = elapsed_time / idx
            remaining_races = len(all_races) - idx
            estimated_remaining_time = avg_time_per_race * remaining_races

            # 現在の的中状況
            total_hits = sum(s['hits'] for s in strategy_stats.values())
            total_valid = sum(s['valid_predictions'] for s in strategy_stats.values())

            print(f"  進捗: {idx}/{len(all_races)} ({idx/len(all_races)*100:.1f}%) | "
                  f"経過: {format_time(elapsed_time)} | "
                  f"残り推定: {format_time(estimated_remaining_time)} | "
                  f"的中: {total_hits}件")

        try:
            # 予測実行
            predictions = predictor.predict_race_by_key(
                race_date=race_date,
                venue_code=venue_code,
                race_number=race_number
            )

            if not predictions or len(predictions) < 6:
                for key in strategies.keys():
                    strategy_stats[key]['prediction_errors'] += 1
                continue

            # スコア順にソート
            sorted_predictions = sorted(predictions, key=lambda x: x.get('total_score', 0), reverse=True)

            # 実際の結果を取得
            actual_result = get_actual_result_trio(cursor, race_id)
            if not actual_result:
                continue

            # 各戦略で検証
            for strategy_key, strategy_info in strategies.items():
                stats = strategy_stats[strategy_key]
                stats['total_races'] += 1

                # 買い目を生成
                trio_combinations = generate_trio_combinations(sorted_predictions, strategy_key)

                if not trio_combinations:
                    stats['prediction_errors'] += 1
                    continue

                stats['valid_predictions'] += 1

                # 購入金額
                bet_amount = 100 * len(trio_combinations)
                stats['total_bet'] += bet_amount

                # 的中判定
                is_hit = actual_result in trio_combinations

                if is_hit:
                    stats['hits'] += 1
                    payout_value = get_trio_payout(cursor, race_id, actual_result)
                    if payout_value:
                        return_amount = payout_value
                        stats['total_return'] += return_amount
                        stats['payout_available'] += 1

        except Exception as e:
            # エラーは静かに記録
            for key in strategies.keys():
                strategy_stats[key]['prediction_errors'] += 1
            continue

    conn.close()

    # 総実行時間
    total_time = time.time() - start_time
    print(f"\n総実行時間: {format_time(total_time)}")

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

    # 結果を表形式で表示
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

        # 損益分岐点
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

    # 回収率で最良の戦略を選択
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
        'strategies': results_summary
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"詳細結果を保存しました: {output_file}")
    print()
    print("=" * 80)


if __name__ == '__main__':
    main()
