#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新スコアのウェイト最適化（超高速版）

既存CSVデータを使ってウェイトのみを調整し、ROIを比較する。
予測再生成不要、数秒で完了。
"""
import sys
import os
import pandas as pd
import sqlite3

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def recalculate_scores_and_rankings(csv_path, motor_weight, venue_weight):
    """
    CSVデータを読み込み、ウェイトを調整してスコアと順位を再計算

    Args:
        csv_path: 既存のCSVファイルパス
        motor_weight: motor_second_rateのウェイト倍率
        venue_weight: venue_affinityのウェイト倍率

    Returns:
        再計算後のDataFrame
    """
    # CSVを読み込む
    df = pd.read_csv(csv_path)

    # 現在のウェイトを確認（デフォルト: motor=5.0, venue=8.0）
    # extended_scoreには既に全てのスコアが含まれているが、
    # motor_second_rate_scoreとvenue_affinity_scoreは別途記録されている

    # ウェイト調整
    # 元のtotal_score = extended_score + motor_second_rate_score(5.0) + venue_affinity_score(8.0)
    # 調整後total_score = extended_score + motor_second_rate_value * motor_weight + affinity_diff * (venue_weight/8.0の調整係数)

    # ただし、スコアは既に計算済みなので、ウェイト倍率で調整
    df['adjusted_motor_score'] = df['motor_second_rate_score'] * (motor_weight / 5.0)  # 5.0がデフォルト
    df['adjusted_venue_score'] = df['venue_affinity_score'] * (venue_weight / 8.0)  # 8.0がデフォルト

    # total_scoreを再計算
    # 元のtotal_scoreから旧スコアを引いて、新スコアを足す
    df['adjusted_total_score'] = (
        df['total_score']
        - df['motor_second_rate_score']
        - df['venue_affinity_score']
        + df['adjusted_motor_score']
        + df['adjusted_venue_score']
    )

    # レースごとに順位を再計算
    df['adjusted_rank_prediction'] = df.groupby('race_id')['adjusted_total_score'].rank(
        ascending=False, method='first'
    ).astype(int)

    return df


def run_backtest_from_dataframe(df, conn):
    """
    DataFrameから直接バックテストを実行

    Args:
        df: 予測データ（adjusted_rank_prediction含む）
        conn: データベース接続

    Returns:
        バックテスト結果
    """
    from scripts.analysis.backtest_old_vs_new_2025 import load_trifecta_odds_and_results, simulate_betting

    # race_idリストを取得
    race_ids = df['race_id'].unique().tolist()

    # オッズと結果を読み込む
    race_data = load_trifecta_odds_and_results(conn, race_ids)

    # DataFrameを予測辞書に変換
    predictions = {}
    for _, row in df.iterrows():
        race_id = row['race_id']
        pit_number = row['pit_number']
        rank_pred = row['adjusted_rank_prediction']
        total_score = row['adjusted_total_score']

        if race_id not in predictions:
            predictions[race_id] = {}
        predictions[race_id][pit_number] = {
            'rank_prediction': rank_pred,
            'total_score': total_score
        }

    # バックテスト実行
    result = simulate_betting(predictions, race_data, 'テスト')

    return result


def main():
    """
    メイン処理: 複数のウェイトパターンをテスト
    """
    # コマンドライン引数でCSVパスを指定可能
    import sys
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = os.path.join(PROJECT_ROOT, 'temp', 'new_scores_test_2025_01_10.csv')

    print('='*80)
    print('新スコアのウェイト最適化（超高速版）')
    print('='*80)
    print(f'入力CSV: {csv_path}')
    print(f'方式: 既存データのウェイト調整のみ（予測再生成なし）')
    print('='*80)

    # テストパターン
    # (motor_weight_multiplier, venue_weight_multiplier)
    weight_patterns = [
        (0.0, 0.0),    # 新スコア無効化
        (0.5, 0.5),    # 半減
        (1.0, 1.0),    # 現在（デフォルト: motor=5.0, venue=8.0）
        (1.5, 1.0),    # motor強化
        (2.0, 1.0),    # motor大幅強化
        (1.0, 1.5),    # venue強化
        (1.0, 2.0),    # venue大幅強化
        (0.6, 1.5),    # motor減・venue増
    ]

    results = []

    # DBに接続
    conn = sqlite3.connect(DATABASE_PATH)

    print(f'\n対象パターン数: {len(weight_patterns)}')
    print('処理開始...\n')

    for idx, (motor_mult, venue_mult) in enumerate(weight_patterns, 1):
        motor_weight = 5.0 * motor_mult  # 実際のウェイト値
        venue_weight = 8.0 * venue_mult

        print(f'[{idx}/{len(weight_patterns)}] motor={motor_weight:.1f} (x{motor_mult}), venue={venue_weight:.1f} (x{venue_mult})', end=' ... ')

        # スコアと順位を再計算
        df_adjusted = recalculate_scores_and_rankings(csv_path, motor_weight, venue_weight)

        # バックテスト実行
        backtest_result = run_backtest_from_dataframe(df_adjusted, conn)

        # 結果を記録
        results.append({
            'pattern_id': idx,
            'motor_weight': motor_weight,
            'venue_weight': venue_weight,
            'motor_mult': motor_mult,
            'venue_mult': venue_mult,
            'roi': backtest_result['roi'],
            'profit': backtest_result['profit'],
            'hit_rate': backtest_result['hit_rate'],
            'total_races': backtest_result['total_races'],
            'hit_count': backtest_result['hit_count']
        })

        print(f'ROI={backtest_result["roi"]:.2f}%, 収支={backtest_result["profit"]:+.0f}円')

    conn.close()

    # 結果をソートして表示
    print(f'\n{"="*80}')
    print('最適化結果サマリー（ROI順）')
    print(f'{"="*80}')

    results_sorted = sorted(results, key=lambda x: x['roi'], reverse=True)

    print(f'\n{"順位":<4} | {"motor":<7} | {"venue":<7} | {"倍率":<12} | {"ROI":>10} | {"収支":>12} | {"的中率":>8} | {"購入数":>6}')
    print('-'*90)

    for rank, r in enumerate(results_sorted, 1):
        mult_str = f'{r["motor_mult"]:.1f}x, {r["venue_mult"]:.1f}x'
        print(f'{rank:<4} | {r["motor_weight"]:<7.1f} | {r["venue_weight"]:<7.1f} | {mult_str:<12} | {r["roi"]:>9.2f}% | {r["profit"]:>+11.0f}円 | {r["hit_rate"]:>7.2f}% | {r["total_races"]:>6}')

    # 最適パターンを表示
    best = results_sorted[0]
    worst = results_sorted[-1]

    print(f'\n{"="*80}')
    print('最適ウェイト')
    print(f'{"="*80}')
    print(f'motor_second_rate: {best["motor_weight"]:.1f} (デフォルトの{best["motor_mult"]:.1f}倍)')
    print(f'venue_affinity: {best["venue_weight"]:.1f} (デフォルトの{best["venue_mult"]:.1f}倍)')
    print(f'ROI: {best["roi"]:.2f}%')
    print(f'収支: {best["profit"]:+.0f}円')
    print(f'的中率: {best["hit_rate"]:.2f}%')

    print(f'\n{"="*80}')
    print('デフォルト（1.0x, 1.0x）との比較')
    print(f'{"="*80}')

    default_result = next((r for r in results if r['motor_mult'] == 1.0 and r['venue_mult'] == 1.0), None)
    if default_result:
        roi_diff = best['roi'] - default_result['roi']
        profit_diff = best['profit'] - default_result['profit']

        print(f'ROI差分: {roi_diff:+.2f}pt')
        print(f'収支差分: {profit_diff:+.0f}円')

        if roi_diff > 2.0:
            print(f'\n✅ ウェイト調整による改善効果が確認されました')
        elif roi_diff > 0:
            print(f'\n⚠️  わずかな改善が見られますが、効果は限定的です')
        else:
            print(f'\n❌ デフォルトが最適、またはウェイト調整の効果なし')

    # 新スコア無効化（0.0, 0.0）との比較
    disabled_result = next((r for r in results if r['motor_mult'] == 0.0 and r['venue_mult'] == 0.0), None)
    if disabled_result and default_result:
        roi_diff = default_result['roi'] - disabled_result['roi']
        profit_diff = default_result['profit'] - disabled_result['profit']

        print(f'\n{"="*80}')
        print('新スコアの効果検証（有効 vs 無効）')
        print(f'{"="*80}')
        print(f'新スコア有効（デフォルト）: ROI={default_result["roi"]:.2f}%, 収支={default_result["profit"]:+.0f}円')
        print(f'新スコア無効（0.0, 0.0）: ROI={disabled_result["roi"]:.2f}%, 収支={disabled_result["profit"]:+.0f}円')
        print(f'差分: ROI {roi_diff:+.2f}pt, 収支 {profit_diff:+.0f}円')

        if roi_diff > 2.0:
            print(f'\n✅ 新スコアによる明確な改善効果あり')
        elif abs(roi_diff) < 2.0:
            print(f'\n⚠️  新スコアの効果は誤差範囲内（統計的に有意でない）')
        else:
            print(f'\n❌ 新スコアが逆効果（無効化した方が良い）')


if __name__ == '__main__':
    main()
