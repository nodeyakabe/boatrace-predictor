"""
階層的確率モデルの回収率シミュレーション
オッズデータがある期間での回収率を計算

使用方法:
  python scripts/backtest_return_rate.py --start-date 2025-10-01 --end-date 2025-10-31
"""
import os
import sys
import sqlite3
import argparse
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.features.feature_transforms import RaceRelativeFeatureBuilder
from src.prediction.trifecta_calculator import TrifectaCalculator, NaiveTrifectaCalculator
from src.prediction.hierarchical_predictor import HierarchicalPredictor


def get_race_results_with_odds(conn, race_id):
    """レース結果とオッズを取得"""
    query = """
        SELECT
            pit_number,
            CAST(rank AS INTEGER) as rank,
            trifecta_odds
        FROM results
        WHERE race_id = ? AND rank IN ('1', '2', '3', '4', '5', '6')
        ORDER BY CAST(rank AS INTEGER)
    """
    cursor = conn.cursor()
    cursor.execute(query, (race_id,))
    rows = cursor.fetchall()

    results = {row[0]: row[1] for row in rows}

    # 三連単オッズは1着のレコードから取得
    trifecta_odds = None
    for row in rows:
        if row[1] == 1 and row[2]:  # 1着のレコード
            try:
                trifecta_odds = float(row[2])
            except (ValueError, TypeError):
                pass
            break

    return results, trifecta_odds


def get_race_features(conn, race_id):
    """レースの特徴量を取得"""
    query = """
        SELECT
            e.pit_number,
            e.racer_number,
            e.win_rate,
            e.second_rate,
            e.motor_second_rate,
            e.boat_second_rate,
            rd.exhibition_time,
            rd.st_time as avg_st,
            COALESCE(rd.actual_course, e.pit_number) as actual_course
        FROM entries e
        LEFT JOIN race_details rd
            ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
        WHERE e.race_id = ?
        ORDER BY e.pit_number
    """
    df = pd.read_sql_query(query, conn, params=(race_id,))
    df['race_id'] = race_id

    # 数値型に変換
    numeric_cols = ['win_rate', 'second_rate', 'motor_second_rate', 'boat_second_rate',
                    'exhibition_time', 'avg_st', 'actual_course']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def calculate_return_rate(db_path, start_date, end_date, betting_strategy='top1'):
    """
    回収率シミュレーションを実行

    Args:
        db_path: DBパス
        start_date: 開始日
        end_date: 終了日
        betting_strategy: 賭け戦略
            - 'top1': 確率最大の組み合わせに賭ける
            - 'top3': 上位3組に均等に賭ける
            - 'top5': 上位5組に均等に賭ける
            - 'positive_ev': 期待値プラスの組み合わせに賭ける
    """
    print("=" * 60)
    print(f"回収率シミュレーション")
    print(f"期間: {start_date} - {end_date}")
    print(f"戦略: {betting_strategy}")
    print("=" * 60)

    # 階層的予測モデルを読み込み
    predictor = HierarchicalPredictor(db_path)
    try:
        predictor.load_models()
        model_loaded = predictor._model_loaded
        print(f"モデル: {'階層的確率モデル' if model_loaded else 'ナイーブ法（フォールバック）'}")
    except Exception as e:
        print(f"モデル読み込みエラー: {e}")
        model_loaded = False

    conn = sqlite3.connect(db_path)
    feature_builder = RaceRelativeFeatureBuilder()

    # オッズがあるレースを取得
    query = """
        SELECT DISTINCT r.id as race_id, r.race_date, r.venue_code, r.race_number
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE r.race_date BETWEEN ? AND ?
          AND res.rank = '1'
          AND res.trifecta_odds IS NOT NULL
        ORDER BY r.race_date, r.venue_code, r.race_number
    """
    races_df = pd.read_sql_query(query, conn, params=(start_date, end_date))

    print(f"対象レース数: {len(races_df)}")

    # 結果を蓄積
    results = []
    total_bet = 0
    total_return = 0

    for idx, row in races_df.iterrows():
        race_id = row['race_id']

        try:
            # 特徴量を取得
            features_df = get_race_features(conn, race_id)
            if len(features_df) != 6:
                continue

            # 結果とオッズを取得
            actual_results, trifecta_odds = get_race_results_with_odds(conn, race_id)
            if len(actual_results) < 3 or trifecta_odds is None:
                continue

            # 実際の三連単
            actual_order = sorted(actual_results.items(), key=lambda x: x[1])[:3]
            actual_trifecta = f"{actual_order[0][0]}-{actual_order[1][0]}-{actual_order[2][0]}"

            # 予測
            features_df = feature_builder.build_training_data(features_df)

            if model_loaded:
                result = predictor.predict_race_from_features(features_df)
                if 'error' in result:
                    continue
                predicted_probs = result.get('trifecta_probs', {})
            else:
                # ナイーブ法
                win_rates = features_df['win_rate'].fillna(10).values
                course_bonus = np.array([1.5, 1.2, 1.0, 0.9, 0.8, 0.7])
                actual_courses = features_df['actual_course'].fillna(features_df['pit_number']).values.astype(int)
                adjusted_rates = win_rates.copy()
                for i, course in enumerate(actual_courses):
                    if 1 <= course <= 6:
                        adjusted_rates[i] *= course_bonus[course - 1]
                first_probs = adjusted_rates / adjusted_rates.sum()
                predicted_probs = NaiveTrifectaCalculator.calculate(first_probs)

            # 賭け戦略に基づいて賭け
            sorted_probs = sorted(predicted_probs.items(), key=lambda x: x[1], reverse=True)

            if betting_strategy == 'top1':
                bets = [(sorted_probs[0][0], 100)]  # 100円
            elif betting_strategy == 'top3':
                bets = [(comb, 100) for comb, _ in sorted_probs[:3]]
            elif betting_strategy == 'top5':
                bets = [(comb, 100) for comb, _ in sorted_probs[:5]]
            elif betting_strategy == 'positive_ev':
                # 期待値プラスの組み合わせを選択
                # オッズは実際の三連単オッズを参考に推定
                # ここでは簡易的に上位3つの期待値を計算
                bets = []
                for comb, prob in sorted_probs[:10]:
                    # 推定オッズ: 1/prob * 0.75 (控除率25%を考慮)
                    estimated_odds = 1 / prob * 0.75 if prob > 0 else 0
                    ev = prob * estimated_odds - 1
                    if ev > 0 and prob >= 0.01:  # 期待値プラスかつ確率1%以上
                        bets.append((comb, 100))
                if not bets:  # 期待値プラスがなければ最上位に
                    bets = [(sorted_probs[0][0], 100)]
            else:
                bets = [(sorted_probs[0][0], 100)]

            # 的中判定
            bet_amount = sum(b[1] for b in bets)
            return_amount = 0
            hit = False

            for comb, amount in bets:
                if comb == actual_trifecta:
                    return_amount = amount * trifecta_odds
                    hit = True
                    break

            total_bet += bet_amount
            total_return += return_amount

            # 予測確率と順位
            pred_rank = None
            pred_prob = predicted_probs.get(actual_trifecta, 0)
            for i, (comb, _) in enumerate(sorted_probs):
                if comb == actual_trifecta:
                    pred_rank = i + 1
                    break

            results.append({
                'race_id': race_id,
                'race_date': row['race_date'],
                'venue_code': row['venue_code'],
                'actual_trifecta': actual_trifecta,
                'trifecta_odds': trifecta_odds,
                'bet_amount': bet_amount,
                'return_amount': return_amount,
                'hit': hit,
                'pred_rank': pred_rank,
                'pred_prob': pred_prob,
            })

        except Exception as e:
            continue

        # 進捗表示
        if (idx + 1) % 50 == 0:
            print(f"処理中: {idx + 1}/{len(races_df)}")

    conn.close()

    # 結果を集計
    if not results:
        print("評価可能なレースがありませんでした")
        return None

    results_df = pd.DataFrame(results)

    print("\n" + "=" * 60)
    print("回収率シミュレーション結果")
    print("=" * 60)

    total_races = len(results_df)
    hit_count = results_df['hit'].sum()
    hit_rate = hit_count / total_races * 100
    return_rate = total_return / total_bet * 100 if total_bet > 0 else 0

    print(f"\n【全体統計】")
    print(f"  対象レース数: {total_races}")
    print(f"  総投資額: {total_bet:,.0f}円")
    print(f"  総回収額: {total_return:,.0f}円")
    print(f"  収支: {total_return - total_bet:+,.0f}円")
    print(f"  回収率: {return_rate:.1f}%")
    print(f"  的中数: {hit_count}/{total_races} ({hit_rate:.2f}%)")

    # 的中時の分析
    hit_df = results_df[results_df['hit'] == True]
    if len(hit_df) > 0:
        print(f"\n【的中レースの分析】")
        print(f"  的中レース数: {len(hit_df)}")
        print(f"  平均オッズ: {hit_df['trifecta_odds'].mean():.1f}倍")
        print(f"  最高オッズ: {hit_df['trifecta_odds'].max():.1f}倍")
        print(f"  最低オッズ: {hit_df['trifecta_odds'].min():.1f}倍")
        print(f"  平均予測確率: {hit_df['pred_prob'].mean()*100:.2f}%")
        print(f"  平均予測順位: {hit_df['pred_rank'].mean():.1f}位")

    # 予測順位別の的中分布
    print(f"\n【予測順位別の的中分布】")
    for rank_range, label in [((1, 1), 'TOP1'), ((2, 5), 'TOP2-5'), ((6, 10), 'TOP6-10'), ((11, 20), 'TOP11-20')]:
        mask = results_df['pred_rank'].between(rank_range[0], rank_range[1])
        count = results_df[mask & results_df['hit']].shape[0]
        total = results_df[mask].shape[0]
        print(f"  {label}: {count}/{total} ({count/total*100:.1f}%)" if total > 0 else f"  {label}: 0/0")

    # 日別の推移
    print(f"\n【日別回収率】")
    daily_stats = results_df.groupby('race_date').agg({
        'bet_amount': 'sum',
        'return_amount': 'sum',
        'hit': 'sum'
    }).reset_index()
    daily_stats['return_rate'] = daily_stats['return_amount'] / daily_stats['bet_amount'] * 100

    for _, day in daily_stats.iterrows():
        rr = day['return_rate']
        marker = '★' if rr >= 100 else ''
        print(f"  {day['race_date']}: {rr:.1f}% ({day['hit']:.0f}的中) {marker}")

    print("\n" + "=" * 60)

    return results_df


def main():
    parser = argparse.ArgumentParser(description='回収率シミュレーション')
    parser.add_argument('--db', default='data/boatrace.db', help='DBパス')
    parser.add_argument('--start-date', default='2025-10-01', help='開始日')
    parser.add_argument('--end-date', default='2025-10-31', help='終了日')
    parser.add_argument('--strategy', default='top1',
                        choices=['top1', 'top3', 'top5', 'positive_ev'],
                        help='賭け戦略')

    args = parser.parse_args()

    # DBパスを絶対パスに
    db_path = os.path.join(PROJECT_ROOT, args.db)
    if not os.path.exists(db_path):
        print(f"データベースが見つかりません: {db_path}")
        return

    results = calculate_return_rate(
        db_path,
        args.start_date,
        args.end_date,
        args.strategy
    )


if __name__ == '__main__':
    main()
