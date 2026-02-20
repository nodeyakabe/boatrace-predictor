#!/usr/bin/env python
"""
パターンボーナス効果分析スクリプト

各パターンが的中率向上に貢献しているか、または逆効果かを分析する。
"""

import sqlite3
import json
from collections import defaultdict
from datetime import datetime
import math
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "boatrace.db")


def get_connection():
    """データベース接続を取得"""
    return sqlite3.connect(DB_PATH)


def analyze_prediction_data_structure():
    """予測データの構造を分析"""
    conn = get_connection()
    cursor = conn.cursor()

    print("=" * 80)
    print("1. 予測データの構造確認")
    print("=" * 80)

    # テーブル構造
    cursor.execute("PRAGMA table_info(race_predictions)")
    columns = cursor.fetchall()
    print("\nrace_predictions テーブルのカラム:")
    for col in columns:
        print(f"  {col[1]} ({col[2]})")

    # 予測タイプ別の件数
    cursor.execute("""
        SELECT prediction_type, COUNT(*) as cnt
        FROM race_predictions
        GROUP BY prediction_type
    """)
    print("\n予測タイプ別件数:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,} 件")

    # 信頼度別件数
    cursor.execute("""
        SELECT confidence, COUNT(*) as cnt
        FROM race_predictions
        WHERE rank_prediction = 1
        GROUP BY confidence
        ORDER BY confidence
    """)
    print("\n信頼度別件数（1着予測）:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,} 件")

    # applied_rulesのサンプル
    cursor.execute("""
        SELECT applied_rules
        FROM race_predictions
        WHERE applied_rules IS NOT NULL AND applied_rules != ''
        LIMIT 5
    """)
    print("\napplied_rulesサンプル:")
    for row in cursor.fetchall():
        print(f"  {row[0][:200]}..." if len(str(row[0])) > 200 else f"  {row[0]}")

    conn.close()


def analyze_patterns_from_race_details():
    """
    race_detailsから展示タイム・ST情報を取得し、
    パターン適用時/非適用時の的中率を比較
    """
    conn = get_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("2. パターン別的中率分析（2020-2024年データ）")
    print("=" * 80)

    # 分析対象期間の予測データを取得
    # before予測（パターンボーナス適用後）と結果を結合
    query = """
    WITH valid_races AS (
        SELECT DISTINCT r.id as race_id
        FROM races r
        INNER JOIN results res ON r.id = res.race_id
        WHERE r.race_date >= '2020-01-01'
          AND r.race_date <= '2024-12-31'
          AND res.is_invalid = 0
          AND res.rank = '1'
    ),
    prediction_with_result AS (
        SELECT
            rp.race_id,
            rp.pit_number,
            rp.rank_prediction,
            rp.confidence,
            rp.total_score,
            rp.applied_rules,
            res.rank as actual_rank
        FROM race_predictions rp
        INNER JOIN valid_races vr ON rp.race_id = vr.race_id
        LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        WHERE rp.prediction_type = 'before'
    )
    SELECT * FROM prediction_with_result
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    if not rows:
        print("before予測データがありません。advance予測で分析します...")
        # advance予測で分析
        query = query.replace("prediction_type = 'before'", "prediction_type = 'advance'")
        cursor.execute(query)
        rows = cursor.fetchall()

    print(f"\n分析対象レコード数: {len(rows):,}")

    # パターン適用状況の分析（applied_rulesから）
    # 1着予測のみを対象に的中率を計算
    first_place_predictions = [r for r in rows if r[2] == 1]  # rank_prediction = 1

    print(f"1着予測レコード数: {len(first_place_predictions):,}")

    # 全体の1着的中率（ベースライン）
    total_hit = sum(1 for r in first_place_predictions if r[6] == '1')  # actual_rank = '1'
    baseline_rate = total_hit / len(first_place_predictions) if first_place_predictions else 0

    print(f"\n全体の1着的中率（ベースライン）: {baseline_rate:.2%} ({total_hit}/{len(first_place_predictions)})")

    conn.close()
    return rows, first_place_predictions, baseline_rate


def calculate_pattern_stats_from_details():
    """
    race_detailsから展示タイム・ST情報を取得し、
    各パターンの効果を計算
    """
    conn = get_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("3. 詳細パターン分析（race_details使用）")
    print("=" * 80)

    # パターン定義
    patterns_1st = [
        {'name': 'pre1_st1', 'description': 'PRE1位 & ST1位', 'multiplier': 1.411, 'target_rank': 1},
        {'name': 'pre1_ex1', 'description': 'PRE1位 & 展示1位', 'multiplier': 1.286, 'target_rank': 1},
        {'name': 'pre1_ex1_3_st1_3', 'description': 'PRE1位 & 展示1-3位 & ST1-3位', 'multiplier': 1.328, 'target_rank': 1},
        {'name': 'pre1_st1_3', 'description': 'PRE1位 & ST1-3位', 'multiplier': 1.310, 'target_rank': 1},
    ]

    patterns_2nd = [
        {'name': 'pre2_3_ex1_2', 'description': 'PRE2-3位 & 展示1-2位', 'multiplier': 1.084, 'target_rank': 2},
        {'name': 'pre2_ex1_3_st1_3', 'description': 'PRE2位 & 展示1-3位 & ST1-3位', 'multiplier': 1.081, 'target_rank': 2},
        {'name': 'ex1_3_pre2_3', 'description': '展示1-3位 & PRE2-3位', 'multiplier': 1.069, 'target_rank': 2},
        {'name': 'pre2_st1_3', 'description': 'PRE2位 & ST1-3位', 'multiplier': 1.064, 'target_rank': 2},
        {'name': 'pre2_ex1_3', 'description': 'PRE2位 & 展示1-3位', 'multiplier': 1.063, 'target_rank': 2},
        {'name': 'ex_rank_2', 'description': '展示2位', 'multiplier': 1.035, 'target_rank': 2},
        {'name': 'st_rank_2_3', 'description': 'ST2-3位', 'multiplier': 1.034, 'target_rank': 2},
    ]

    patterns_3rd = [
        {'name': 'pre3_4_ex2_4', 'description': 'PRE3-4位 & 展示2-4位', 'multiplier': 1.032, 'target_rank': 3},
        {'name': 'pre3_ex1_3', 'description': 'PRE3位 & 展示1-3位', 'multiplier': 1.031, 'target_rank': 3},
        {'name': 'outer_st1_2', 'description': 'アウトコース(4-6枠) & ST1-2位', 'multiplier': 1.022, 'target_rank': 3},
        {'name': 'pre3_4_ex1_3_st1_3', 'description': 'PRE3-4位 & 展示1-3位 & ST1-3位', 'multiplier': 1.020, 'target_rank': 3},
    ]

    patterns_top3 = [
        {'name': 'pre1_3_st1_3', 'description': 'PRE1-3位 & ST1-3位', 'multiplier': 1.130, 'target_rank': 'top3'},
        {'name': 'pre1_3_ex1_3', 'description': 'PRE1-3位 & 展示1-3位', 'multiplier': 1.123, 'target_rank': 'top3'},
        {'name': 'ex1_3_st1_3', 'description': '展示1-3位 & ST1-3位', 'multiplier': 1.108, 'target_rank': 'top3'},
        {'name': 'pre1_4_ex1_2', 'description': 'PRE1-4位 & 展示1-2位', 'multiplier': 1.104, 'target_rank': 'top3'},
        {'name': 'ex_rank_1_2', 'description': '展示1-2位', 'multiplier': 1.051, 'target_rank': 'top3'},
    ]

    all_patterns = patterns_1st + patterns_2nd + patterns_3rd + patterns_top3

    # 分析用クエリ - レースごとの展示タイム・ST情報を取得
    # このデータをもとにパターンマッチングを行う
    query = """
    WITH race_with_before AS (
        SELECT
            r.id as race_id,
            r.race_date,
            rd.pit_number,
            rd.exhibition_time,
            rd.st_time,
            res.rank as actual_rank
        FROM races r
        INNER JOIN race_details rd ON r.id = rd.race_id
        LEFT JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= '2020-01-01'
          AND r.race_date <= '2024-12-31'
          AND rd.exhibition_time IS NOT NULL
          AND rd.st_time IS NOT NULL
          AND res.is_invalid = 0
    ),
    ranked_data AS (
        SELECT
            race_id,
            race_date,
            pit_number,
            exhibition_time,
            st_time,
            actual_rank,
            RANK() OVER (PARTITION BY race_id ORDER BY exhibition_time ASC) as ex_rank,
            RANK() OVER (PARTITION BY race_id ORDER BY ABS(st_time) ASC) as st_rank
        FROM race_with_before
    )
    SELECT * FROM ranked_data
    ORDER BY race_id, pit_number
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"分析対象レコード数（BEFORE情報あり）: {len(rows):,}")

    # レースIDごとにグループ化
    races = defaultdict(list)
    for row in rows:
        race_id = row[0]
        races[race_id].append({
            'pit_number': row[2],
            'exhibition_time': row[3],
            'st_time': row[4],
            'actual_rank': row[5],
            'ex_rank': row[6],
            'st_rank': row[7]
        })

    # 6艇すべて揃っているレースのみを分析対象にする
    valid_races = {k: v for k, v in races.items() if len(v) == 6}
    print(f"有効レース数（6艇揃い）: {len(valid_races):,}")

    # 予測データを取得（PRE順位を算出するため）
    pred_query = """
    SELECT race_id, pit_number, rank_prediction, confidence
    FROM race_predictions
    WHERE prediction_type IN ('before', 'advance')
    ORDER BY race_id, rank_prediction
    """
    cursor.execute(pred_query)
    pred_rows = cursor.fetchall()

    # 予測データをレースIDごとにグループ化
    predictions = defaultdict(list)
    for row in pred_rows:
        predictions[row[0]].append({
            'pit_number': row[1],
            'rank_prediction': row[2],
            'confidence': row[3]
        })

    # パターン効果の分析
    pattern_stats = {}

    for pattern in all_patterns:
        pattern_stats[pattern['name']] = {
            'description': pattern['description'],
            'multiplier': pattern['multiplier'],
            'target_rank': pattern['target_rank'],
            'match_count': 0,
            'hit_count': 0,
            'by_confidence': {
                'A': {'match': 0, 'hit': 0},
                'B': {'match': 0, 'hit': 0},
                'C': {'match': 0, 'hit': 0},
                'D': {'match': 0, 'hit': 0},
                'E': {'match': 0, 'hit': 0},
            }
        }

    # ベースライン計算用
    baseline_stats = {
        '1st': {'total': 0, 'hit': 0},
        '2nd': {'total': 0, 'hit': 0},
        '3rd': {'total': 0, 'hit': 0},
        'top3': {'total': 0, 'hit': 0},
        'by_confidence': {
            'A': {'total': 0, 'hit': 0},
            'B': {'total': 0, 'hit': 0},
            'C': {'total': 0, 'hit': 0},
            'D': {'total': 0, 'hit': 0},
            'E': {'total': 0, 'hit': 0},
        }
    }

    # 各レースを処理
    for race_id, race_data in valid_races.items():
        if race_id not in predictions:
            continue

        pred_data = predictions[race_id]
        if len(pred_data) != 6:
            continue

        # PRE順位マップを作成
        pre_rank_map = {p['pit_number']: p['rank_prediction'] for p in pred_data}

        # 信頼度を取得（1着予測の信頼度）
        top_pred = next((p for p in pred_data if p['rank_prediction'] == 1), None)
        confidence = top_pred['confidence'] if top_pred else 'C'

        # 各艇についてパターンマッチング
        for boat in race_data:
            pit_number = boat['pit_number']
            ex_rank = boat['ex_rank']
            st_rank = boat['st_rank']
            actual_rank = boat['actual_rank']
            pre_rank = pre_rank_map.get(pit_number, 6)

            # 1着予測の基準（ベースライン）
            if pre_rank == 1:
                baseline_stats['1st']['total'] += 1
                if actual_rank == '1':
                    baseline_stats['1st']['hit'] += 1
                if confidence in baseline_stats['by_confidence']:
                    baseline_stats['by_confidence'][confidence]['total'] += 1
                    if actual_rank == '1':
                        baseline_stats['by_confidence'][confidence]['hit'] += 1

            # 2着予測の基準
            if pre_rank == 2:
                baseline_stats['2nd']['total'] += 1
                if actual_rank == '2':
                    baseline_stats['2nd']['hit'] += 1

            # 3着予測の基準
            if pre_rank == 3:
                baseline_stats['3rd']['total'] += 1
                if actual_rank == '3':
                    baseline_stats['3rd']['hit'] += 1

            # 3着以内予測の基準
            if pre_rank <= 3:
                baseline_stats['top3']['total'] += 1
                if actual_rank in ['1', '2', '3']:
                    baseline_stats['top3']['hit'] += 1

            # 1着パターンチェック
            if pre_rank == 1:
                # pre1_st1
                if st_rank == 1:
                    pattern_stats['pre1_st1']['match_count'] += 1
                    if actual_rank == '1':
                        pattern_stats['pre1_st1']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre1_st1']['by_confidence'][confidence]['match'] += 1
                        if actual_rank == '1':
                            pattern_stats['pre1_st1']['by_confidence'][confidence]['hit'] += 1

                # pre1_ex1
                if ex_rank == 1:
                    pattern_stats['pre1_ex1']['match_count'] += 1
                    if actual_rank == '1':
                        pattern_stats['pre1_ex1']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre1_ex1']['by_confidence'][confidence]['match'] += 1
                        if actual_rank == '1':
                            pattern_stats['pre1_ex1']['by_confidence'][confidence]['hit'] += 1

                # pre1_ex1_3_st1_3
                if ex_rank <= 3 and st_rank <= 3:
                    pattern_stats['pre1_ex1_3_st1_3']['match_count'] += 1
                    if actual_rank == '1':
                        pattern_stats['pre1_ex1_3_st1_3']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre1_ex1_3_st1_3']['by_confidence'][confidence]['match'] += 1
                        if actual_rank == '1':
                            pattern_stats['pre1_ex1_3_st1_3']['by_confidence'][confidence]['hit'] += 1

                # pre1_st1_3
                if st_rank <= 3:
                    pattern_stats['pre1_st1_3']['match_count'] += 1
                    if actual_rank == '1':
                        pattern_stats['pre1_st1_3']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre1_st1_3']['by_confidence'][confidence]['match'] += 1
                        if actual_rank == '1':
                            pattern_stats['pre1_st1_3']['by_confidence'][confidence]['hit'] += 1

            # 2着パターンチェック
            if pre_rank in [2, 3]:
                # pre2_3_ex1_2
                if ex_rank <= 2:
                    pattern_stats['pre2_3_ex1_2']['match_count'] += 1
                    if actual_rank == '2':
                        pattern_stats['pre2_3_ex1_2']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre2_3_ex1_2']['by_confidence'][confidence]['match'] += 1
                        if actual_rank == '2':
                            pattern_stats['pre2_3_ex1_2']['by_confidence'][confidence]['hit'] += 1

                # ex1_3_pre2_3
                if ex_rank <= 3:
                    pattern_stats['ex1_3_pre2_3']['match_count'] += 1
                    if actual_rank == '2':
                        pattern_stats['ex1_3_pre2_3']['hit_count'] += 1
                    if confidence:
                        pattern_stats['ex1_3_pre2_3']['by_confidence'][confidence]['match'] += 1
                        if actual_rank == '2':
                            pattern_stats['ex1_3_pre2_3']['by_confidence'][confidence]['hit'] += 1

            if pre_rank == 2:
                # pre2_ex1_3_st1_3
                if ex_rank <= 3 and st_rank <= 3:
                    pattern_stats['pre2_ex1_3_st1_3']['match_count'] += 1
                    if actual_rank == '2':
                        pattern_stats['pre2_ex1_3_st1_3']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre2_ex1_3_st1_3']['by_confidence'][confidence]['match'] += 1
                        if actual_rank == '2':
                            pattern_stats['pre2_ex1_3_st1_3']['by_confidence'][confidence]['hit'] += 1

                # pre2_st1_3
                if st_rank <= 3:
                    pattern_stats['pre2_st1_3']['match_count'] += 1
                    if actual_rank == '2':
                        pattern_stats['pre2_st1_3']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre2_st1_3']['by_confidence'][confidence]['match'] += 1
                        if actual_rank == '2':
                            pattern_stats['pre2_st1_3']['by_confidence'][confidence]['hit'] += 1

                # pre2_ex1_3
                if ex_rank <= 3:
                    pattern_stats['pre2_ex1_3']['match_count'] += 1
                    if actual_rank == '2':
                        pattern_stats['pre2_ex1_3']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre2_ex1_3']['by_confidence'][confidence]['match'] += 1
                        if actual_rank == '2':
                            pattern_stats['pre2_ex1_3']['by_confidence'][confidence]['hit'] += 1

            # ex_rank_2
            if ex_rank == 2:
                pattern_stats['ex_rank_2']['match_count'] += 1
                if actual_rank == '2':
                    pattern_stats['ex_rank_2']['hit_count'] += 1
                if confidence:
                    pattern_stats['ex_rank_2']['by_confidence'][confidence]['match'] += 1
                    if actual_rank == '2':
                        pattern_stats['ex_rank_2']['by_confidence'][confidence]['hit'] += 1

            # st_rank_2_3
            if st_rank in [2, 3]:
                pattern_stats['st_rank_2_3']['match_count'] += 1
                if actual_rank == '2':
                    pattern_stats['st_rank_2_3']['hit_count'] += 1
                if confidence:
                    pattern_stats['st_rank_2_3']['by_confidence'][confidence]['match'] += 1
                    if actual_rank == '2':
                        pattern_stats['st_rank_2_3']['by_confidence'][confidence]['hit'] += 1

            # 3着パターンチェック
            if pre_rank in [3, 4]:
                # pre3_4_ex2_4
                if 2 <= ex_rank <= 4:
                    pattern_stats['pre3_4_ex2_4']['match_count'] += 1
                    if actual_rank == '3':
                        pattern_stats['pre3_4_ex2_4']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre3_4_ex2_4']['by_confidence'][confidence]['match'] += 1
                        if actual_rank == '3':
                            pattern_stats['pre3_4_ex2_4']['by_confidence'][confidence]['hit'] += 1

                # pre3_4_ex1_3_st1_3
                if ex_rank <= 3 and st_rank <= 3:
                    pattern_stats['pre3_4_ex1_3_st1_3']['match_count'] += 1
                    if actual_rank == '3':
                        pattern_stats['pre3_4_ex1_3_st1_3']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre3_4_ex1_3_st1_3']['by_confidence'][confidence]['match'] += 1
                        if actual_rank == '3':
                            pattern_stats['pre3_4_ex1_3_st1_3']['by_confidence'][confidence]['hit'] += 1

            if pre_rank == 3:
                # pre3_ex1_3
                if ex_rank <= 3:
                    pattern_stats['pre3_ex1_3']['match_count'] += 1
                    if actual_rank == '3':
                        pattern_stats['pre3_ex1_3']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre3_ex1_3']['by_confidence'][confidence]['match'] += 1
                        if actual_rank == '3':
                            pattern_stats['pre3_ex1_3']['by_confidence'][confidence]['hit'] += 1

            # outer_st1_2
            if pit_number >= 4 and st_rank <= 2:
                pattern_stats['outer_st1_2']['match_count'] += 1
                if actual_rank == '3':
                    pattern_stats['outer_st1_2']['hit_count'] += 1
                if confidence:
                    pattern_stats['outer_st1_2']['by_confidence'][confidence]['match'] += 1
                    if actual_rank == '3':
                        pattern_stats['outer_st1_2']['by_confidence'][confidence]['hit'] += 1

            # TOP3パターンチェック
            if pre_rank <= 3:
                # pre1_3_st1_3
                if st_rank <= 3:
                    pattern_stats['pre1_3_st1_3']['match_count'] += 1
                    if actual_rank in ['1', '2', '3']:
                        pattern_stats['pre1_3_st1_3']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre1_3_st1_3']['by_confidence'][confidence]['match'] += 1
                        if actual_rank in ['1', '2', '3']:
                            pattern_stats['pre1_3_st1_3']['by_confidence'][confidence]['hit'] += 1

                # pre1_3_ex1_3
                if ex_rank <= 3:
                    pattern_stats['pre1_3_ex1_3']['match_count'] += 1
                    if actual_rank in ['1', '2', '3']:
                        pattern_stats['pre1_3_ex1_3']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre1_3_ex1_3']['by_confidence'][confidence]['match'] += 1
                        if actual_rank in ['1', '2', '3']:
                            pattern_stats['pre1_3_ex1_3']['by_confidence'][confidence]['hit'] += 1

            if pre_rank <= 4:
                # pre1_4_ex1_2
                if ex_rank <= 2:
                    pattern_stats['pre1_4_ex1_2']['match_count'] += 1
                    if actual_rank in ['1', '2', '3']:
                        pattern_stats['pre1_4_ex1_2']['hit_count'] += 1
                    if confidence:
                        pattern_stats['pre1_4_ex1_2']['by_confidence'][confidence]['match'] += 1
                        if actual_rank in ['1', '2', '3']:
                            pattern_stats['pre1_4_ex1_2']['by_confidence'][confidence]['hit'] += 1

            # ex1_3_st1_3
            if ex_rank <= 3 and st_rank <= 3:
                pattern_stats['ex1_3_st1_3']['match_count'] += 1
                if actual_rank in ['1', '2', '3']:
                    pattern_stats['ex1_3_st1_3']['hit_count'] += 1
                if confidence:
                    pattern_stats['ex1_3_st1_3']['by_confidence'][confidence]['match'] += 1
                    if actual_rank in ['1', '2', '3']:
                        pattern_stats['ex1_3_st1_3']['by_confidence'][confidence]['hit'] += 1

            # ex_rank_1_2
            if ex_rank <= 2:
                pattern_stats['ex_rank_1_2']['match_count'] += 1
                if actual_rank in ['1', '2', '3']:
                    pattern_stats['ex_rank_1_2']['hit_count'] += 1
                if confidence:
                    pattern_stats['ex_rank_1_2']['by_confidence'][confidence]['match'] += 1
                    if actual_rank in ['1', '2', '3']:
                        pattern_stats['ex_rank_1_2']['by_confidence'][confidence]['hit'] += 1

    conn.close()
    return pattern_stats, baseline_stats


def calculate_p_value(hit_rate, baseline_rate, n):
    """
    二項検定のp値を計算（簡易版）
    """
    if n == 0:
        return 1.0

    # z-score
    if baseline_rate == 0 or baseline_rate == 1:
        return 1.0

    se = math.sqrt(baseline_rate * (1 - baseline_rate) / n)
    if se == 0:
        return 1.0

    z = (hit_rate - baseline_rate) / se

    # 標準正規分布のp値（近似）
    # 両側検定
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))

    return p


def generate_report(pattern_stats, baseline_stats):
    """分析レポートを生成"""

    report = []
    report.append("# パターンボーナス効果分析レポート")
    report.append(f"\n**生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"**分析期間**: 2020年1月〜2024年12月")
    report.append("")

    # ベースライン
    report.append("## 1. ベースライン（パターン非適用時の的中率）")
    report.append("")
    report.append("| 予測対象 | 的中数 | 総数 | 的中率 |")
    report.append("|----------|--------|------|--------|")

    for target, label in [('1st', '1着予測'), ('2nd', '2着予測'), ('3rd', '3着予測'), ('top3', '3着以内予測')]:
        stats = baseline_stats[target]
        rate = stats['hit'] / stats['total'] if stats['total'] > 0 else 0
        report.append(f"| {label} | {stats['hit']:,} | {stats['total']:,} | {rate:.2%} |")

    # 信頼度別ベースライン
    report.append("\n### 信頼度別ベースライン（1着予測）")
    report.append("")
    report.append("| 信頼度 | 的中数 | 総数 | 的中率 |")
    report.append("|--------|--------|------|--------|")

    for conf in ['A', 'B', 'C', 'D', 'E']:
        stats = baseline_stats['by_confidence'][conf]
        rate = stats['hit'] / stats['total'] if stats['total'] > 0 else 0
        report.append(f"| {conf} | {stats['hit']:,} | {stats['total']:,} | {rate:.2%} |")

    # パターン別効果（効果の高い順）
    report.append("\n## 2. パターン別効果一覧（効果の高い順）")
    report.append("")

    # ベースライン的中率を取得
    baseline_1st = baseline_stats['1st']['hit'] / baseline_stats['1st']['total'] if baseline_stats['1st']['total'] > 0 else 0
    baseline_2nd = baseline_stats['2nd']['hit'] / baseline_stats['2nd']['total'] if baseline_stats['2nd']['total'] > 0 else 0
    baseline_3rd = baseline_stats['3rd']['hit'] / baseline_stats['3rd']['total'] if baseline_stats['3rd']['total'] > 0 else 0
    baseline_top3 = baseline_stats['top3']['hit'] / baseline_stats['top3']['total'] if baseline_stats['top3']['total'] > 0 else 0

    def get_baseline_for_target(target):
        if target == 1:
            return baseline_1st
        elif target == 2:
            return baseline_2nd
        elif target == 3:
            return baseline_3rd
        else:
            return baseline_top3

    # パターンごとの効果を計算
    pattern_effects = []
    for name, stats in pattern_stats.items():
        if stats['match_count'] > 0:
            hit_rate = stats['hit_count'] / stats['match_count']
            baseline = get_baseline_for_target(stats['target_rank'])
            effect = hit_rate - baseline
            p_value = calculate_p_value(hit_rate, baseline, stats['match_count'])

            pattern_effects.append({
                'name': name,
                'description': stats['description'],
                'multiplier': stats['multiplier'],
                'target_rank': stats['target_rank'],
                'match_count': stats['match_count'],
                'hit_count': stats['hit_count'],
                'hit_rate': hit_rate,
                'baseline': baseline,
                'effect': effect,
                'p_value': p_value,
                'by_confidence': stats['by_confidence']
            })

    # 効果の高い順にソート
    pattern_effects.sort(key=lambda x: x['effect'], reverse=True)

    report.append("| パターン名 | 説明 | 倍率 | 対象 | サンプル数 | 的中率 | ベースライン | 効果 | p値 | 判定 |")
    report.append("|------------|------|------|------|------------|--------|--------------|------|-----|------|")

    for p in pattern_effects:
        target_label = f"{p['target_rank']}着" if isinstance(p['target_rank'], int) else "3着以内"
        effect_str = f"+{p['effect']:.1%}" if p['effect'] >= 0 else f"{p['effect']:.1%}"

        # 判定
        if p['p_value'] < 0.05 and p['effect'] > 0:
            judgment = "有効"
        elif p['p_value'] < 0.05 and p['effect'] < 0:
            judgment = "**逆効果**"
        elif p['match_count'] < 100:
            judgment = "サンプル不足"
        else:
            judgment = "効果なし"

        report.append(f"| {p['name']} | {p['description']} | {p['multiplier']:.3f} | {target_label} | {p['match_count']:,} | {p['hit_rate']:.2%} | {p['baseline']:.2%} | {effect_str} | {p['p_value']:.4f} | {judgment} |")

    # 信頼度×パターンのクロス分析
    report.append("\n## 3. 信頼度×パターンのクロス分析（1着パターンのみ）")
    report.append("")

    # 1着パターンのみ抽出
    first_patterns = [p for p in pattern_effects if p['target_rank'] == 1]

    report.append("| パターン | 信頼度A | 信頼度B | 信頼度C | 信頼度D | 信頼度E |")
    report.append("|----------|---------|---------|---------|---------|---------|")

    for p in first_patterns:
        row = [p['name']]
        for conf in ['A', 'B', 'C', 'D', 'E']:
            conf_stats = p['by_confidence'][conf]
            if conf_stats['match'] > 0:
                rate = conf_stats['hit'] / conf_stats['match']
                baseline_conf = baseline_stats['by_confidence'][conf]['hit'] / baseline_stats['by_confidence'][conf]['total'] if baseline_stats['by_confidence'][conf]['total'] > 0 else 0
                effect = rate - baseline_conf
                effect_str = f"+{effect:.1%}" if effect >= 0 else f"{effect:.1%}"
                row.append(f"{rate:.1%} ({effect_str}, n={conf_stats['match']})")
            else:
                row.append("-")
        report.append("| " + " | ".join(row) + " |")

    # 逆効果パターンの特定
    report.append("\n## 4. 逆効果パターンの特定")
    report.append("")

    negative_patterns = [p for p in pattern_effects if p['effect'] < 0 and p['match_count'] >= 100]

    if negative_patterns:
        report.append("### 統計的に有意な逆効果パターン（p < 0.05）")
        report.append("")
        for p in negative_patterns:
            if p['p_value'] < 0.05:
                report.append(f"- **{p['name']}** ({p['description']})")
                report.append(f"  - 的中率: {p['hit_rate']:.2%} vs ベースライン: {p['baseline']:.2%} (効果: {p['effect']:.1%})")
                report.append(f"  - サンプル数: {p['match_count']:,}, p値: {p['p_value']:.4f}")
                report.append(f"  - 現在の倍率: {p['multiplier']:.3f}")
                report.append("")

        report.append("### 効果が不明確なパターン（効果がほぼゼロ）")
        report.append("")
        marginal_patterns = [p for p in pattern_effects if abs(p['effect']) < 0.02 and p['match_count'] >= 100]
        for p in marginal_patterns:
            report.append(f"- **{p['name']}** ({p['description']})")
            report.append(f"  - 効果: {p['effect']:.1%} (ほぼゼロ)")
            report.append(f"  - サンプル数: {p['match_count']:,}")
            report.append("")
    else:
        report.append("明確な逆効果パターンは検出されませんでした。")

    # 信頼度別の逆効果
    report.append("\n### 特定信頼度で逆効果のパターン")
    report.append("")

    for p in pattern_effects:
        for conf in ['A', 'B', 'C', 'D', 'E']:
            conf_stats = p['by_confidence'][conf]
            if conf_stats['match'] >= 50:
                rate = conf_stats['hit'] / conf_stats['match']
                baseline_conf = baseline_stats['by_confidence'][conf]['hit'] / baseline_stats['by_confidence'][conf]['total'] if baseline_stats['by_confidence'][conf]['total'] > 0 else 0
                effect = rate - baseline_conf
                if effect < -0.05:  # 5%以上の逆効果
                    report.append(f"- **{p['name']}** @ 信頼度{conf}: 的中率 {rate:.1%} vs ベースライン {baseline_conf:.1%} (効果: {effect:.1%}, n={conf_stats['match']})")

    # 改善提案
    report.append("\n## 5. 具体的な改善提案")
    report.append("")

    report.append("### 無効化を検討すべきパターン")
    report.append("")

    for p in pattern_effects:
        if p['effect'] < -0.02 and p['match_count'] >= 200:
            report.append(f"1. **{p['name']}** ({p['description']})")
            report.append(f"   - 理由: ベースラインより {abs(p['effect']):.1%} 低い的中率")
            report.append(f"   - 提案: 倍率を1.0に設定するか、パターン自体を無効化")
            report.append("")

    report.append("### 倍率調整を検討すべきパターン")
    report.append("")

    for p in pattern_effects:
        if p['effect'] > 0 and p['match_count'] >= 200:
            # 効果に見合った倍率を計算
            expected_multiplier = 1 + (p['effect'] / p['baseline']) if p['baseline'] > 0 else 1.0
            if abs(expected_multiplier - p['multiplier']) > 0.05:
                report.append(f"1. **{p['name']}** ({p['description']})")
                report.append(f"   - 現在の倍率: {p['multiplier']:.3f}")
                report.append(f"   - 実効果に基づく推奨倍率: {expected_multiplier:.3f}")
                report.append(f"   - 効果: +{p['effect']:.1%}")
                report.append("")

    report.append("### 信頼度別の適用制限を検討すべきパターン")
    report.append("")

    for p in pattern_effects:
        negative_confs = []
        for conf in ['A', 'B', 'C', 'D', 'E']:
            conf_stats = p['by_confidence'][conf]
            if conf_stats['match'] >= 50:
                rate = conf_stats['hit'] / conf_stats['match']
                baseline_conf = baseline_stats['by_confidence'][conf]['hit'] / baseline_stats['by_confidence'][conf]['total'] if baseline_stats['by_confidence'][conf]['total'] > 0 else 0
                effect = rate - baseline_conf
                if effect < -0.03:
                    negative_confs.append(conf)

        if negative_confs:
            report.append(f"1. **{p['name']}**: 信頼度 {', '.join(negative_confs)} で逆効果")
            report.append(f"   - 提案: これらの信頼度ではパターンボーナスを適用しない")
            report.append("")

    # サマリー
    report.append("\n## 6. サマリー")
    report.append("")

    effective_count = len([p for p in pattern_effects if p['effect'] > 0.02 and p['p_value'] < 0.05])
    negative_count = len([p for p in pattern_effects if p['effect'] < -0.02 and p['p_value'] < 0.05])
    neutral_count = len(pattern_effects) - effective_count - negative_count

    report.append(f"- **有効なパターン**: {effective_count} 個")
    report.append(f"- **逆効果パターン**: {negative_count} 個")
    report.append(f"- **効果不明確**: {neutral_count} 個")
    report.append("")

    if negative_count > 0:
        report.append("**緊急対応推奨**: 逆効果パターンが存在します。これらのパターンの無効化を検討してください。")

    return "\n".join(report)


def main():
    """メイン処理"""
    print("パターンボーナス効果分析を開始します...")
    print("")

    # データ構造確認
    analyze_prediction_data_structure()

    # パターン分析
    pattern_stats, baseline_stats = calculate_pattern_stats_from_details()

    # レポート生成
    report = generate_report(pattern_stats, baseline_stats)

    # ファイルに保存
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs",
        "PATTERN_EFFECTIVENESS_ANALYSIS_20251217.md"
    )

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n\nレポートを保存しました: {output_path}")
    print("\n" + "=" * 80)
    print("レポート内容:")
    print("=" * 80)
    print(report)


if __name__ == "__main__":
    main()
