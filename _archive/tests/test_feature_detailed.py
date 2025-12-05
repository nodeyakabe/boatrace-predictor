"""
新機能の効果検証テスト（詳細版）

統合予測とPRE単体予測を比較し、改善効果を測定
"""

import sqlite3
from src.analysis.race_predictor import RacePredictor
import time

def main():
    print("=" * 80)
    print("新機能効果検証テスト: 30レース")
    print("=" * 80)
    print()

    conn = sqlite3.connect('data/boatrace.db')
    predictor = RacePredictor(db_path='data/boatrace.db')

    # 最新30レース取得
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        JOIN results res ON r.id = res.race_id
        WHERE rd.exhibition_course IS NOT NULL
        AND res.rank IS NOT NULL
        AND res.is_invalid = 0
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT 30
    """)

    test_races = cursor.fetchall()
    print(f"検証対象: {len(test_races)}レース")
    print()

    # 統計
    integrated_win = 0
    pre_only_win = 0
    both_correct = 0
    both_wrong = 0
    only_integrated_correct = 0
    only_pre_correct = 0

    different_predictions = []
    total_time = 0
    errors = 0

    for i, (race_id, race_date, venue, race_no) in enumerate(test_races):
        print(f"[{i+1}/{len(test_races)}] {race_date} {venue} {race_no}R (ID: {race_id})", end="")

        try:
            # 実際の結果
            cursor.execute("""
                SELECT pit_number FROM results
                WHERE race_id = ? AND rank = 1 AND is_invalid = 0
            """, (race_id,))
            result = cursor.fetchone()
            if not result:
                print(" → 結果データなし")
                continue
            actual_winner = result[0]

            # 予測（時間計測）
            start = time.time()
            predictions = predictor.predict_race(race_id)
            elapsed = time.time() - start
            total_time += elapsed

            if not predictions or len(predictions) == 0:
                print(f" → 予測エラー")
                errors += 1
                continue

            # 統合予測（total_scoreが最大）
            integrated_pred = predictions[0]['pit_number']
            integrated_score = predictions[0]['total_score']

            # PRE単体予測（pre_scoreが最大）
            pre_only = sorted(predictions, key=lambda x: x.get('pre_score', 0), reverse=True)
            pre_pred = pre_only[0]['pit_number']
            pre_score = pre_only[0].get('pre_score', 0)

            # 的中判定
            int_hit = (integrated_pred == actual_winner)
            pre_hit = (pre_pred == actual_winner)

            if int_hit:
                integrated_win += 1
            if pre_hit:
                pre_only_win += 1

            # 4パターンの分類
            if int_hit and pre_hit:
                both_correct += 1
                result_type = "両方的中"
            elif not int_hit and not pre_hit:
                both_wrong += 1
                result_type = "両方外れ"
            elif int_hit and not pre_hit:
                only_integrated_correct += 1
                result_type = "★統合のみ的中"
            else:  # pre_hit and not int_hit
                only_pre_correct += 1
                result_type = "★PREのみ的中"

            # 予測が異なる場合は詳細記録
            if integrated_pred != pre_pred:
                print(f" → 予測相違: 統合{integrated_pred}号 vs PRE{pre_pred}号 (実際{actual_winner}号) {result_type}")
                different_predictions.append({
                    'date': race_date,
                    'venue': venue,
                    'race_no': race_no,
                    'race_id': race_id,
                    'actual': actual_winner,
                    'integrated': integrated_pred,
                    'integrated_score': integrated_score,
                    'pre_only': pre_pred,
                    'pre_score': pre_score,
                    'int_hit': int_hit,
                    'pre_hit': pre_hit,
                    'result_type': result_type,
                    'elapsed': elapsed
                })
            else:
                # 予測が同じ場合は簡潔に表示
                mark = '◎' if int_hit else '×'
                print(f" → 予測一致: {integrated_pred}号 {mark}")

        except Exception as e:
            print(f" → エラー: {e}")
            errors += 1
            continue

    conn.close()

    # 最終結果
    total_valid = integrated_win + (both_wrong - (only_integrated_correct if only_integrated_correct > 0 else 0))

    print()
    print("=" * 80)
    print("検証結果サマリー")
    print("=" * 80)
    print(f"総レース数: {len(test_races)}")
    print(f"有効レース数: {len(test_races) - errors}")
    print(f"エラー数: {errors}")
    if len(test_races) - errors > 0:
        print(f"平均処理時間: {total_time/(len(test_races)-errors):.1f}秒/レース")
    print()

    valid_count = len(test_races) - errors
    if valid_count > 0:
        int_win_rate = (integrated_win / valid_count) * 100
        pre_win_rate = (pre_only_win / valid_count) * 100

        print("【的中率比較】")
        print(f"  統合予測: {integrated_win}/{valid_count} ({int_win_rate:.1f}%)")
        print(f"  PRE単体: {pre_only_win}/{valid_count} ({pre_win_rate:.1f}%)")
        print(f"  改善: {int_win_rate - pre_win_rate:+.1f}ポイント")
        print()

        print("【的中パターン分析】")
        print(f"  両方的中: {both_correct}レース ({both_correct/valid_count*100:.1f}%)")
        print(f"  両方外れ: {both_wrong}レース ({both_wrong/valid_count*100:.1f}%)")
        print(f"  統合のみ的中: {only_integrated_correct}レース ({only_integrated_correct/valid_count*100:.1f}%) ← 改善効果！")
        print(f"  PREのみ的中: {only_pre_correct}レース ({only_pre_correct/valid_count*100:.1f}%) ← 悪化")
        print()

        net_improvement = only_integrated_correct - only_pre_correct
        print(f"【正味改善効果】")
        print(f"  統合のみ的中 - PREのみ的中 = {net_improvement}レース")
        if net_improvement > 0:
            print(f"  → 統合予測が{net_improvement}レース分優れている")
        elif net_improvement < 0:
            print(f"  → PRE単体が{-net_improvement}レース分優れている")
        else:
            print(f"  → 両者同等")
        print()

        if different_predictions:
            print(f"【予測が異なったレース: {len(different_predictions)}件】")
            print()
            for d in different_predictions:
                int_mark = '◎' if d['int_hit'] else '×'
                pre_mark = '◎' if d['pre_hit'] else '×'
                print(f"  {d['date']} {d['venue']} {d['race_no']}R (ID: {d['race_id']})")
                print(f"    実際: {d['actual']}号")
                print(f"    統合: {d['integrated']}号 (スコア: {d['integrated_score']:.1f}) {int_mark}")
                print(f"    PRE:  {d['pre_only']}号 (スコア: {d['pre_score']:.1f}) {pre_mark}")
                print(f"    結果: {d['result_type']}")
                print(f"    処理時間: {d['elapsed']:.1f}秒")
                print()
        else:
            print("【予測が異なったレース: 0件】")
            print("  → 全レースで統合予測とPRE単体予測が一致")
            print("  → 新機能の効果が表れていない可能性")

    print("=" * 80)

if __name__ == "__main__":
    main()
