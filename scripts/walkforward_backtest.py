"""
Walk-forward Backtest - 時系列を考慮したバックテスト

データを時系列で分割し、過学習の有無を確認する
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from datetime import datetime
from src.analysis.race_predictor import RacePredictor

def main():
    print("=" * 80)
    print("Walk-forward Backtest")
    print("=" * 80)
    print()

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # データを時系列で分割（3ヶ月ごと）
    cursor.execute("""
        SELECT MIN(race_date), MAX(race_date)
        FROM races
        WHERE id IN (
            SELECT DISTINCT r.id
            FROM races r
            JOIN race_details rd ON r.id = rd.race_id
            JOIN results res ON r.id = res.race_id
            WHERE rd.exhibition_course IS NOT NULL
            AND res.rank IS NOT NULL
            AND res.is_invalid = 0
        )
    """)
    min_date, max_date = cursor.fetchone()

    print(f"データ期間: {min_date} 〜 {max_date}")
    print()

    # 最新300レースを取得（約1週間分）
    cursor.execute("""
        SELECT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        JOIN results res ON r.id = res.race_id
        WHERE rd.exhibition_course IS NOT NULL
        AND res.rank IS NOT NULL
        AND res.is_invalid = 0
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT 300
    """)
    all_races = cursor.fetchall()

    # 新しい順なので逆順にして古い順にする
    all_races = list(reversed(all_races))

    print(f"テスト対象: {len(all_races)}レース")
    print()

    # 50レースずつのウィンドウで検証（6ウィンドウ）
    window_size = 50
    results_by_window = []

    predictor = RacePredictor(db_path='data/boatrace.db')

    for window_idx in range(6):
        start_idx = window_idx * window_size
        end_idx = start_idx + window_size

        if end_idx > len(all_races):
            break

        window_races = all_races[start_idx:end_idx]
        window_start_date = window_races[0][1]
        window_end_date = window_races[-1][1]

        print(f"Window {window_idx + 1}: {window_start_date} 〜 {window_end_date} ({len(window_races)}レース)")

        # 統計
        integrated_win = 0
        pre_only_win = 0
        total = 0
        errors = 0

        for race_id, race_date, venue, race_no in window_races:
            try:
                # 実際の結果
                cursor.execute("""
                    SELECT pit_number FROM results
                    WHERE race_id = ? AND rank = 1 AND is_invalid = 0
                """, (race_id,))
                result = cursor.fetchone()
                if not result:
                    continue
                actual_winner = result[0]

                # 統合スコアで予測
                predictions = predictor.predict_race(race_id)
                if not predictions or len(predictions) == 0:
                    errors += 1
                    continue

                integrated_pred = predictions[0]['pit_number']

                # PRE単体での予測
                pre_only = sorted(predictions, key=lambda x: x.get('pre_score', 0), reverse=True)
                pre_pred = pre_only[0]['pit_number']

                # 的中判定
                if integrated_pred == actual_winner:
                    integrated_win += 1
                if pre_pred == actual_winner:
                    pre_only_win += 1

                total += 1

            except Exception as e:
                errors += 1
                continue

        if total > 0:
            int_rate = (integrated_win / total) * 100
            pre_rate = (pre_only_win / total) * 100

            print(f"  統合予測: {integrated_win}/{total} ({int_rate:.1f}%)")
            print(f"  PRE単体: {pre_only_win}/{total} ({pre_rate:.1f}%)")
            print(f"  差分: {int_rate - pre_rate:+.1f}ポイント")
            print(f"  エラー: {errors}件")
            print()

            results_by_window.append({
                'window': window_idx + 1,
                'start': window_start_date,
                'end': window_end_date,
                'total': total,
                'int_win': integrated_win,
                'int_rate': int_rate,
                'pre_win': pre_only_win,
                'pre_rate': pre_rate,
                'diff': int_rate - pre_rate
            })

    conn.close()

    print("=" * 80)
    print("全体サマリー")
    print("=" * 80)

    if results_by_window:
        # 全体平均
        total_races = sum(w['total'] for w in results_by_window)
        total_int_win = sum(w['int_win'] for w in results_by_window)
        total_pre_win = sum(w['pre_win'] for w in results_by_window)

        overall_int_rate = (total_int_win / total_races) * 100 if total_races > 0 else 0
        overall_pre_rate = (total_pre_win / total_races) * 100 if total_races > 0 else 0

        print(f"総レース数: {total_races}")
        print(f"統合予測全体: {total_int_win}/{total_races} ({overall_int_rate:.2f}%)")
        print(f"PRE単体全体: {total_pre_win}/{total_races} ({overall_pre_rate:.2f}%)")
        print(f"全体差分: {overall_int_rate - overall_pre_rate:+.2f}ポイント")
        print()

        # 時間経過による変動を確認
        print("時系列変動:")
        print("-" * 80)
        for w in results_by_window:
            print(f"Window {w['window']}: 統合{w['int_rate']:.1f}% / PRE{w['pre_rate']:.1f}% / 差{w['diff']:+.1f}%")

        # 標準偏差
        import statistics
        int_rates = [w['int_rate'] for w in results_by_window]
        pre_rates = [w['pre_rate'] for w in results_by_window]

        int_std = statistics.stdev(int_rates) if len(int_rates) > 1 else 0
        pre_std = statistics.stdev(pre_rates) if len(pre_rates) > 1 else 0

        print()
        print(f"統合予測の標準偏差: {int_std:.2f}% (安定性指標)")
        print(f"PRE単体の標準偏差: {pre_std:.2f}% (安定性指標)")
        print()

        # 過学習判定
        if int_std < 5.0 and pre_std < 5.0:
            print("判定: 過学習なし（時系列で安定）")
        elif int_std > 10.0:
            print("警告: 統合予測が不安定（過学習の可能性）")
        else:
            print("判定: 概ね安定（許容範囲内）")

    print()
    print("=" * 80)

if __name__ == "__main__":
    main()
