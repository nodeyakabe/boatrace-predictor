# -*- coding: utf-8 -*-
"""
信頼度B専用買い目抽出スクリプト

分析結果に基づき、会場・季節フィルターを適用して
信頼度Bの推奨買い目を抽出し、フィルター前後の的中率を比較する
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime
import csv

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.confidence_filter import ConfidenceBFilter


def extract_confidence_b_races(cursor, start_date='2024-01-01', end_date='2024-12-31'):
    """信頼度Bのレースを抽出"""
    query = '''
        SELECT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            rp.confidence,
            rp.total_score as confidence_score
        FROM races r
        INNER JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= ? AND r.race_date <= ?
            AND rp.prediction_type = 'advance'
            AND rp.rank_prediction = 1
            AND rp.confidence = 'B'
        ORDER BY r.race_date, r.venue_code, r.race_number
    '''

    cursor.execute(query, (start_date, end_date))
    races = cursor.fetchall()

    return [dict(race) for race in races]


def get_prediction_and_result(cursor, race_id):
    """予測と実際の結果を取得"""
    # 予測（上位3艇）
    cursor.execute('''
        SELECT pit_number
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'advance'
        ORDER BY rank_prediction
        LIMIT 3
    ''', (race_id,))

    pred_rows = cursor.fetchall()
    if len(pred_rows) < 3:
        return None, None

    prediction = tuple(row['pit_number'] for row in pred_rows)

    # 実際の結果
    cursor.execute('''
        SELECT pit_number
        FROM results
        WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
        ORDER BY rank
        LIMIT 3
    ''', (race_id,))

    result_rows = cursor.fetchall()
    if len(result_rows) < 3:
        return prediction, None

    result = tuple(row['pit_number'] for row in result_rows)

    return prediction, result


def analyze_filter_effectiveness(races, filter_results, cursor):
    """フィルター効果の分析"""

    # フィルター前の統計
    total_races = len(races)
    total_hits = 0

    for race in races:
        pred, result = get_prediction_and_result(cursor, race['race_id'])
        if pred and result and pred == result:
            total_hits += 1

    # フィルター後の統計
    accepted_races = filter_results['accepted_races']
    accepted_hits = 0

    for race_info in accepted_races:
        pred, result = get_prediction_and_result(cursor, race_info['race_id'])
        if pred and result and pred == result:
            accepted_hits += 1

    # 除外レースの統計
    rejected_races = filter_results['rejected_races']
    rejected_hits = 0

    for race_info in rejected_races:
        pred, result = get_prediction_and_result(cursor, race_info['race_id'])
        if pred and result and pred == result:
            rejected_hits += 1

    return {
        'before_filter': {
            'races': total_races,
            'hits': total_hits,
            'hit_rate': total_hits / total_races * 100 if total_races > 0 else 0
        },
        'after_filter': {
            'races': len(accepted_races),
            'hits': accepted_hits,
            'hit_rate': accepted_hits / len(accepted_races) * 100 if accepted_races else 0
        },
        'rejected': {
            'races': len(rejected_races),
            'hits': rejected_hits,
            'hit_rate': rejected_hits / len(rejected_races) * 100 if rejected_races else 0
        }
    }


def save_to_csv(accepted_races, output_path):
    """推奨買い目をCSV保存"""
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([
            'レース日', '会場', '会場名', 'レース番号', '信頼度スコア',
            '期待的中率(%)', '会場的中率(%)', '月別的中率(%)', 'フィルター理由'
        ])

        for race in accepted_races:
            filter_result = race['filter_result']
            writer.writerow([
                race['race_date'],
                race['venue_code'],
                filter_result['venue_name'],
                race['race_number'],
                f"{race['confidence_score']:.1f}" if race.get('confidence_score') else 'N/A',
                f"{filter_result['expected_hit_rate']:.2f}",
                f"{filter_result['venue_hit_rate']:.2f}",
                f"{filter_result['monthly_hit_rate']:.2f}",
                filter_result['reason']
            ])


def main():
    print("=" * 80)
    print("信頼度B専用買い目抽出（会場・季節フィルター適用）")
    print("=" * 80)
    print()

    # データベース接続
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 信頼度Bレース抽出
    print("信頼度Bレースを抽出中...")
    races = extract_confidence_b_races(cursor)
    print(f"抽出レース数: {len(races)}")
    print()

    # フィルター初期化
    b_filter = ConfidenceBFilter(
        exclude_low_venues=True,
        venue_threshold=5.0,
        seasonal_adjustment=True,
        low_season_score_boost=2.0
    )

    # 会場別推奨・除外リスト表示
    print(b_filter.get_venue_summary())
    print()

    # フィルタリング実行
    print("=" * 80)
    print("フィルタリング実行中...")
    print("=" * 80)
    filter_results = b_filter.filter_race_list(races)

    summary = filter_results['summary']
    print(f"\n総レース数: {summary['total']}")
    print(f"受け入れ: {summary['accepted']} ({summary['acceptance_rate']:.1f}%)")
    print(f"除外: {summary['rejected']} ({100 - summary['acceptance_rate']:.1f}%)")
    print(f"期待平均的中率: {summary['expected_avg_hit_rate']:.2f}%")
    print()

    # フィルター効果分析
    print("=" * 80)
    print("フィルター効果分析（実際の的中率で検証）")
    print("=" * 80)

    effectiveness = analyze_filter_effectiveness(races, filter_results, cursor)

    before = effectiveness['before_filter']
    after = effectiveness['after_filter']
    rejected = effectiveness['rejected']

    print(f"\n【フィルター前】")
    print(f"  レース数: {before['races']}")
    print(f"  的中数: {before['hits']}")
    print(f"  的中率: {before['hit_rate']:.2f}%")

    print(f"\n【フィルター後（推奨買い目）】")
    print(f"  レース数: {after['races']}")
    print(f"  的中数: {after['hits']}")
    print(f"  的中率: {after['hit_rate']:.2f}%")

    improvement = after['hit_rate'] - before['hit_rate']
    print(f"\n  → 的中率改善: {improvement:+.2f}ポイント")

    print(f"\n【除外レース】")
    print(f"  レース数: {rejected['races']}")
    print(f"  的中数: {rejected['hits']}")
    print(f"  的中率: {rejected['hit_rate']:.2f}%")

    # CSV出力
    output_path = ROOT_DIR / 'output' / 'confidence_b_recommended_bets.csv'
    save_to_csv(filter_results['accepted_races'], output_path)
    print(f"\n推奨買い目をCSV出力: {output_path}")

    # 除外理由の集計
    print()
    print("=" * 80)
    print("除外理由の内訳")
    print("=" * 80)

    rejection_reasons = {}
    for race in filter_results['rejected_races']:
        adjustment = race['filter_result']['adjustment']
        rejection_reasons[adjustment] = rejection_reasons.get(adjustment, 0) + 1

    for reason, count in sorted(rejection_reasons.items(), key=lambda x: x[1], reverse=True):
        percentage = count / len(filter_results['rejected_races']) * 100 if filter_results['rejected_races'] else 0
        print(f"  {reason}: {count}件 ({percentage:.1f}%)")

    # 月別の受け入れ率
    print()
    print("=" * 80)
    print("月別フィルター適用状況")
    print("=" * 80)

    monthly_stats = {}
    for race in races:
        try:
            month = datetime.strptime(race['race_date'], '%Y-%m-%d').month
        except:
            month = 0

        if month not in monthly_stats:
            monthly_stats[month] = {'total': 0, 'accepted': 0}

        monthly_stats[month]['total'] += 1

    for race in filter_results['accepted_races']:
        try:
            month = datetime.strptime(race['race_date'], '%Y-%m-%d').month
        except:
            month = 0

        monthly_stats[month]['accepted'] += 1

    print(f"\n{'月':>4} | {'総数':>6} | {'受入':>6} | {'除外':>6} | {'受入率':>8}")
    print("-" * 50)
    for month in sorted(monthly_stats.keys()):
        if month == 0:
            continue
        stats = monthly_stats[month]
        rejected = stats['total'] - stats['accepted']
        accept_rate = stats['accepted'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"{month:4d} | {stats['total']:6d} | {stats['accepted']:6d} | {rejected:6d} | {accept_rate:7.1f}%")

    conn.close()

    print()
    print("=" * 80)
    print("完了")
    print("=" * 80)


if __name__ == '__main__':
    main()
