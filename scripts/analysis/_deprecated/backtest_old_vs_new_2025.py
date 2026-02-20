#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
旧版（DB）vs 新スコア版（CSV）のROI比較バックテスト - 2025年1-10月限定

旧版: race_predictionsテーブル（2026-01-08生成、Phase 2前）
新版: new_scores_test_2025_01_10.csv（Phase 2後、motor_second_rate/venue_affinity追加）

標準の購入条件を適用して、実際のROI・収支を比較します。
"""
import sys
import os
import io
import pandas as pd
import sqlite3
from collections import defaultdict

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def load_csv_predictions(csv_path):
    """CSVから新スコア版予測を読み込む"""
    print(f'\n新スコア版予測を読み込み中: {csv_path}')
    df = pd.read_csv(csv_path)

    # race_id, pit_number ごとに予測順位とスコアを取得
    predictions = {}
    for _, row in df.iterrows():
        race_id = row['race_id']
        pit_number = row['pit_number']
        rank_pred = row['rank_prediction']
        total_score = row['total_score']

        if race_id not in predictions:
            predictions[race_id] = {}
        predictions[race_id][pit_number] = {
            'rank_prediction': rank_pred,
            'total_score': total_score
        }

    print(f'  読み込み完了: {len(predictions)}レース')
    return predictions


def load_db_predictions(conn, race_ids):
    """DBから旧版予測を読み込む"""
    print(f'\n旧版予測を読み込み中（race_predictions）...')

    chunk_size = 500
    all_predictions = {}

    for i in range(0, len(race_ids), chunk_size):
        chunk_ids = race_ids[i:i+chunk_size]
        placeholders = ','.join(['?'] * len(chunk_ids))

        query = f"""
            SELECT race_id, pit_number, rank_prediction, total_score
            FROM race_predictions
            WHERE race_id IN ({placeholders})
            AND prediction_type = 'before'
        """

        cursor = conn.cursor()
        cursor.execute(query, chunk_ids)

        for race_id, pit_number, rank_pred, total_score in cursor.fetchall():
            if race_id not in all_predictions:
                all_predictions[race_id] = {}
            all_predictions[race_id][pit_number] = {
                'rank_prediction': rank_pred,
                'total_score': total_score
            }

    print(f'  読み込み完了: {len(all_predictions)}レース')
    return all_predictions


def load_trifecta_odds_and_results(conn, race_ids):
    """3連単オッズと結果を読み込む"""
    print(f'\n3連単オッズと結果を読み込み中...')

    chunk_size = 500
    all_data = {}

    for i in range(0, len(race_ids), chunk_size):
        chunk_ids = race_ids[i:i+chunk_size]
        placeholders = ','.join(['?'] * len(chunk_ids))

        # オッズと結果を同時取得
        query = f"""
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                r.race_number,
                t.combination,
                t.odds,
                res1.rank as rank1,
                res2.rank as rank2,
                res3.rank as rank3,
                res4.rank as rank4,
                res5.rank as rank5,
                res6.rank as rank6
            FROM races r
            LEFT JOIN trifecta_odds t ON r.id = t.race_id
            LEFT JOIN results res1 ON r.id = res1.race_id AND res1.pit_number = 1
            LEFT JOIN results res2 ON r.id = res2.race_id AND res2.pit_number = 2
            LEFT JOIN results res3 ON r.id = res3.race_id AND res3.pit_number = 3
            LEFT JOIN results res4 ON r.id = res4.race_id AND res4.pit_number = 4
            LEFT JOIN results res5 ON r.id = res5.race_id AND res5.pit_number = 5
            LEFT JOIN results res6 ON r.id = res6.race_id AND res6.pit_number = 6
            WHERE r.id IN ({placeholders})
        """

        cursor = conn.cursor()
        cursor.execute(query, chunk_ids)

        for row in cursor.fetchall():
            race_id = row[0]
            race_date = row[1]
            venue_code = row[2]
            race_number = row[3]
            combination = row[4]
            odds = row[5]

            if race_id not in all_data:
                all_data[race_id] = {
                    'race_date': race_date,
                    'venue_code': venue_code,
                    'race_number': race_number,
                    'odds': {},
                    'actual_ranks': {}
                }

            # オッズ情報
            if combination and odds:
                all_data[race_id]['odds'][combination] = odds

            # 実結果（1回だけ設定）
            if 'pit_ranks_set' not in all_data[race_id]:
                for pit in range(1, 7):
                    rank_val = row[6 + pit - 1]
                    if rank_val:
                        try:
                            all_data[race_id]['actual_ranks'][pit] = int(rank_val)
                        except (ValueError, TypeError):
                            pass
                all_data[race_id]['pit_ranks_set'] = True

    print(f'  読み込み完了: {len(all_data)}レース')
    return all_data


def simulate_betting(predictions, race_data, version_name):
    """
    購入条件を適用してバックテスト

    購入条件:
    - 1-2-3の3連単1点買い
    - オッズ10倍以上
    - 1位艇のスコアが2位艇より3点以上高い
    """
    print(f'\n{version_name} のバックテスト実行中...')

    total_bet = 0
    total_return = 0
    total_races = 0
    hit_count = 0

    bet_details = []

    for race_id, pred_data in predictions.items():
        if race_id not in race_data:
            continue

        # 6艇すべての予測がある場合のみ
        if len(pred_data) != 6:
            continue

        # 予測順位でソート
        sorted_preds = sorted(pred_data.items(), key=lambda x: x[1]['rank_prediction'])

        # 1位、2位、3位を取得
        pit1, data1 = sorted_preds[0]
        pit2, data2 = sorted_preds[1]
        pit3, data3 = sorted_preds[2]

        score1 = data1['total_score']
        score2 = data2['total_score']

        # 購入条件チェック
        combination = f"{pit1}-{pit2}-{pit3}"

        # オッズ取得
        odds_dict = race_data[race_id].get('odds', {})
        if combination not in odds_dict:
            continue

        odds = odds_dict[combination]

        # 条件1: オッズ10倍以上
        if odds < 10.0:
            continue

        # 条件2: 1位のスコアが2位より3点以上高い
        if score1 - score2 < 3.0:
            continue

        # ここまで来たら購入
        total_bet += 100
        total_races += 1

        # 的中判定
        actual_ranks = race_data[race_id].get('actual_ranks', {})
        if len(actual_ranks) == 6:
            # 実際の1-2-3位を取得
            actual_sorted = sorted(actual_ranks.items(), key=lambda x: x[1])
            actual_1st = actual_sorted[0][0]
            actual_2nd = actual_sorted[1][0]
            actual_3rd = actual_sorted[2][0]

            if pit1 == actual_1st and pit2 == actual_2nd and pit3 == actual_3rd:
                # 的中
                payout = 100 * odds
                total_return += payout
                hit_count += 1
                hit = True
            else:
                hit = False

            bet_details.append({
                'race_date': race_data[race_id]['race_date'],
                'venue_code': race_data[race_id]['venue_code'],
                'race_number': race_data[race_id]['race_number'],
                'combination': combination,
                'odds': odds,
                'score1': score1,
                'score2': score2,
                'score_diff': score1 - score2,
                'hit': hit,
                'return': payout if hit else 0
            })

    # 結果集計
    roi = (total_return / total_bet * 100) if total_bet > 0 else 0
    profit = total_return - total_bet
    hit_rate = (hit_count / total_races * 100) if total_races > 0 else 0

    result = {
        'version': version_name,
        'total_races': total_races,
        'total_bet': total_bet,
        'total_return': total_return,
        'profit': profit,
        'roi': roi,
        'hit_count': hit_count,
        'hit_rate': hit_rate,
        'bet_details': bet_details
    }

    print(f'  購入レース数: {total_races}')
    print(f'  的中数: {hit_count}')
    print(f'  的中率: {hit_rate:.2f}%')
    print(f'  ROI: {roi:.2f}%')
    print(f'  収支: {profit:+.0f}円')

    return result


def print_comparison(old_result, new_result):
    """比較結果を表示"""
    print('\n' + '='*80)
    print('ROI比較: 旧版（DB） vs 新スコア版（CSV）')
    print('='*80)
    print(f'\n対象期間: 2025年1月〜10月')
    print(f'購入条件: 1-2-3の3連単1点買い、オッズ10倍以上、1位スコアが2位より3点以上高い')

    print(f'\n' + '-'*80)
    print(f'{"指標":<20} | {"旧版":>15} | {"新版":>15} | {"差分":>15}')
    print('-'*80)

    # 購入レース数
    print(f'{"購入レース数":<20} | {old_result["total_races"]:>15} | {new_result["total_races"]:>15} | {new_result["total_races"] - old_result["total_races"]:>+15}')

    # 的中数
    print(f'{"的中数":<20} | {old_result["hit_count"]:>15} | {new_result["hit_count"]:>15} | {new_result["hit_count"] - old_result["hit_count"]:>+15}')

    # 的中率
    old_hit_rate = old_result['hit_rate']
    new_hit_rate = new_result['hit_rate']
    hit_rate_diff = new_hit_rate - old_hit_rate
    print(f'{"的中率":<20} | {old_hit_rate:>14.2f}% | {new_hit_rate:>14.2f}% | {hit_rate_diff:>+14.2f}pt')

    # ROI
    old_roi = old_result['roi']
    new_roi = new_result['roi']
    roi_diff = new_roi - old_roi
    print(f'{"ROI":<20} | {old_roi:>14.2f}% | {new_roi:>14.2f}% | {roi_diff:>+14.2f}pt')

    # 収支
    old_profit = old_result['profit']
    new_profit = new_result['profit']
    profit_diff = new_profit - old_profit
    print(f'{"収支":<20} | {old_profit:>+14.0f}円 | {new_profit:>+14.0f}円 | {profit_diff:>+14.0f}円')

    print('-'*80)

    # 総合評価
    print('\n' + '='*80)
    print('総合評価')
    print('='*80)

    improvements = []
    deteriorations = []

    if roi_diff > 0:
        improvements.append(f'ROI: {roi_diff:+.2f}pt')
    elif roi_diff < 0:
        deteriorations.append(f'ROI: {roi_diff:+.2f}pt')

    if profit_diff > 0:
        improvements.append(f'収支: {profit_diff:+.0f}円')
    elif profit_diff < 0:
        deteriorations.append(f'収支: {profit_diff:+.0f}円')

    if hit_rate_diff > 0:
        improvements.append(f'的中率: {hit_rate_diff:+.2f}pt')
    elif hit_rate_diff < 0:
        deteriorations.append(f'的中率: {hit_rate_diff:+.2f}pt')

    print(f'\n改善項目 ({len(improvements)}):')
    for item in improvements:
        print(f'  ✅ {item}')

    print(f'\n悪化項目 ({len(deteriorations)}):')
    for item in deteriorations:
        print(f'  ❌ {item}')

    # 推奨アクション
    print('\n' + '='*80)
    print('推奨アクション')
    print('='*80)

    if roi_diff > 5.0 and profit_diff > 0:
        print('\n✅ 新スコアによる明確な改善効果が確認されました')
        print('   → DB反映を推奨')
    elif roi_diff > 0 and profit_diff > 0:
        print('\n⚠️  新スコアによる改善効果が確認されましたが、効果は限定的です')
        print('   → ウェイト調整やさらなる改善を検討')
    elif abs(roi_diff) < 2.0:
        print('\n⚠️  新旧の差がほとんどありません（ノイズ範囲内）')
        print('   → 統計的に有意な差がない可能性')
    else:
        print('\n❌ 新スコアによる改善効果が確認できませんでした')
        print('   → DB反映は非推奨、アルゴリズム見直しを検討')


if __name__ == '__main__':
    csv_path = os.path.join(PROJECT_ROOT, 'temp', 'new_scores_test_2025_01_10.csv')

    print('='*80)
    print('2025年1-10月 ROI比較バックテスト')
    print('='*80)
    print(f'旧版: race_predictions (2026-01-08生成、Phase 2前)')
    print(f'新版: {csv_path}')

    # CSVから新スコア版予測を読み込む
    new_predictions = load_csv_predictions(csv_path)

    # DBに接続
    conn = sqlite3.connect(DATABASE_PATH)

    # 対象race_idリスト（新版のrace_id）
    race_ids = list(new_predictions.keys())

    # DBから旧版予測を読み込む
    old_predictions = load_db_predictions(conn, race_ids)

    # オッズと結果を読み込む
    race_data = load_trifecta_odds_and_results(conn, race_ids)

    # 旧版バックテスト
    old_result = simulate_betting(old_predictions, race_data, '旧版（DB）')

    # 新版バックテスト
    new_result = simulate_betting(new_predictions, race_data, '新版（CSV）')

    # 比較結果を表示
    print_comparison(old_result, new_result)

    conn.close()

    print('\n処理完了')
