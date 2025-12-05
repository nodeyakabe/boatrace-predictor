"""
予測精度検証スクリプト
統合スコア（PRE + BEFORE）vs PRE単体の精度比較
"""

import sqlite3
from src.analysis.race_predictor import RacePredictor
from typing import List, Dict, Tuple
import sys

def get_actual_results(conn, race_id: int) -> Dict[int, int]:
    """実際のレース結果（着順）を取得"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pit_number, CAST(rank AS INTEGER) as rank
        FROM results
        WHERE race_id = ? AND rank IS NOT NULL AND is_invalid = 0
        ORDER BY rank
    ''', (race_id,))

    results = {}
    for pit_number, rank in cursor.fetchall():
        results[pit_number] = rank

    return results

def simulate_pre_only_prediction(predictions: List[Dict]) -> List[Dict]:
    """PRE_SCOREのみでの予測をシミュレート（統合前の状態）"""
    # pre_scoreでソート
    pre_only = []
    for pred in predictions:
        pre_only.append({
            'pit_number': pred['pit_number'],
            'score': pred.get('pre_score', pred['total_score']),
            'racer_name': pred['racer_name']
        })

    # PRE_SCOREで降順ソート
    pre_only.sort(key=lambda x: x['score'], reverse=True)
    return pre_only

def calculate_accuracy(predictions: List[Dict], actual_results: Dict[int, int]) -> Tuple[bool, bool]:
    """
    的中判定
    Returns: (1着的中, 3着以内的中)
    """
    if not predictions or not actual_results:
        return False, False

    # 予測1位の艇番
    predicted_winner = predictions[0]['pit_number']

    # 実際の1着
    actual_winner = None
    for pit, rank in actual_results.items():
        if rank == 1:
            actual_winner = pit
            break

    # 1着的中判定
    is_winner_correct = (predicted_winner == actual_winner)

    # 3着以内的中判定（予測1位が実際に3着以内に入ったか）
    is_top3_correct = actual_results.get(predicted_winner, 999) <= 3

    return is_winner_correct, is_top3_correct

def main():
    print('=' * 80)
    print('予測精度検証: 統合スコア vs PRE単体')
    print('=' * 80)

    conn = sqlite3.connect('data/boatrace.db')
    predictor = RacePredictor(db_path='data/boatrace.db')

    # 直前情報があり、かつ結果が確定しているレースを取得
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        JOIN results res ON r.id = res.race_id
        WHERE rd.exhibition_course IS NOT NULL
        AND res.rank IS NOT NULL
        AND res.is_invalid = 0
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT 30
    ''')

    test_races = cursor.fetchall()

    if not test_races:
        print('[ERROR] テスト可能なレースが見つかりませんでした')
        print('条件: 直前情報あり & 結果確定済み')
        conn.close()
        sys.exit(1)

    print(f'\n[検証対象] {len(test_races)}レース')
    print('=' * 80)

    # 統計用カウンター
    integrated_win_count = 0
    integrated_top3_count = 0
    pre_only_win_count = 0
    pre_only_top3_count = 0
    total_races = 0

    # 詳細結果リスト
    details = []

    for race_id, race_date, venue_code, race_number in test_races:
        try:
            # 実際の結果を取得
            actual_results = get_actual_results(conn, race_id)
            if not actual_results:
                continue

            # 統合スコアで予測
            integrated_predictions = predictor.predict_race(race_id)
            if not integrated_predictions:
                continue

            # PRE単体での予測をシミュレート
            pre_only_predictions = simulate_pre_only_prediction(integrated_predictions)

            # 的中判定
            int_win, int_top3 = calculate_accuracy(integrated_predictions, actual_results)
            pre_win, pre_top3 = calculate_accuracy(pre_only_predictions, actual_results)

            # カウント
            if int_win:
                integrated_win_count += 1
            if int_top3:
                integrated_top3_count += 1
            if pre_win:
                pre_only_win_count += 1
            if pre_top3:
                pre_only_top3_count += 1

            total_races += 1

            # 実際の1着
            actual_winner = None
            for pit, rank in actual_results.items():
                if rank == 1:
                    actual_winner = pit
                    break

            # 詳細記録
            details.append({
                'race_id': race_id,
                'date': race_date,
                'venue': venue_code,
                'race_no': race_number,
                'actual_winner': actual_winner,
                'integrated_pred': integrated_predictions[0]['pit_number'],
                'pre_only_pred': pre_only_predictions[0]['pit_number'],
                'int_win': int_win,
                'pre_win': pre_win
            })

        except Exception as e:
            print(f'[WARN] race_id={race_id} の処理でエラー: {e}')
            continue

    conn.close()

    # 結果サマリー
    print('\n' + '=' * 80)
    print('検証結果サマリー')
    print('=' * 80)
    print(f'総レース数: {total_races}')
    print()

    if total_races > 0:
        int_win_rate = (integrated_win_count / total_races) * 100
        int_top3_rate = (integrated_top3_count / total_races) * 100
        pre_win_rate = (pre_only_win_count / total_races) * 100
        pre_top3_rate = (pre_only_top3_count / total_races) * 100

        print('【統合スコア（PRE 60% + BEFORE 40%）】')
        print(f'  1着的中: {integrated_win_count}/{total_races} ({int_win_rate:.1f}%)')
        print(f'  3着内的中: {integrated_top3_count}/{total_races} ({int_top3_rate:.1f}%)')
        print()
        print('【PRE単体スコア】')
        print(f'  1着的中: {pre_only_win_count}/{total_races} ({pre_win_rate:.1f}%)')
        print(f'  3着内的中: {pre_only_top3_count}/{total_races} ({pre_top3_rate:.1f}%)')
        print()
        print('【改善効果】')
        win_diff = int_win_rate - pre_win_rate
        top3_diff = int_top3_rate - pre_top3_rate
        print(f'  1着的中率: {win_diff:+.1f}ポイント')
        print(f'  3着内的中率: {top3_diff:+.1f}ポイント')

        # 差が顕著なレースを表示
        print('\n' + '=' * 80)
        print('予測が異なったレースの詳細')
        print('=' * 80)
        print('日付       | 会場 | R# | 実際 | 統合 | PRE | 統合結果 | PRE結果')
        print('-' * 80)

        diff_count = 0
        for detail in details[:20]:  # 最大20件表示
            if detail['integrated_pred'] != detail['pre_only_pred']:
                int_mark = '◎' if detail['int_win'] else '×'
                pre_mark = '◎' if detail['pre_win'] else '×'
                print(f'{detail["date"]} | {detail["venue"]:4s} | {detail["race_no"]:2d}R | '
                      f'{detail["actual_winner"]}号 | {detail["integrated_pred"]}号 | '
                      f'{detail["pre_only_pred"]}号 | {int_mark:^8s} | {pre_mark:^7s}')
                diff_count += 1

        if diff_count == 0:
            print('  (予測が異なるレースはありませんでした)')

    print('\n' + '=' * 80)
    print('検証完了')
    print('=' * 80)

if __name__ == '__main__':
    main()
