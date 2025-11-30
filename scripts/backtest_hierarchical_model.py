"""
階層的確率モデルのバックテスト
Phase 5: 過去データでの精度検証

使用方法:
  python scripts/backtest_hierarchical_model.py --start-date 2024-11-01 --end-date 2024-11-30
"""
import os
import sys
import sqlite3
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.features.feature_transforms import create_training_dataset_with_relative_features
from src.prediction.trifecta_calculator import TrifectaCalculator, NaiveTrifectaCalculator
from src.prediction.hierarchical_predictor import HierarchicalPredictor


def get_race_results(conn, race_id):
    """レース結果を取得"""
    query = """
        SELECT pit_number, CAST(rank AS INTEGER) as rank
        FROM results
        WHERE race_id = ? AND rank IN ('1', '2', '3', '4', '5', '6')
        ORDER BY CAST(rank AS INTEGER)
    """
    cursor = conn.cursor()
    cursor.execute(query, (race_id,))
    return {row[0]: row[1] for row in cursor.fetchall()}


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

    # 数値型に変換（欠損値対策）
    numeric_cols = ['win_rate', 'second_rate', 'motor_second_rate', 'boat_second_rate',
                    'exhibition_time', 'avg_st', 'actual_course']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def evaluate_prediction(predicted_probs, actual_results):
    """予測精度を評価"""
    if not actual_results or len(actual_results) < 3:
        return None

    # 実際の三連単
    actual_order = sorted(actual_results.items(), key=lambda x: x[1])[:3]
    actual_trifecta = f"{actual_order[0][0]}-{actual_order[1][0]}-{actual_order[2][0]}"

    # 予測の上位組み合わせ
    sorted_probs = sorted(predicted_probs.items(), key=lambda x: x[1], reverse=True)

    # 的中判定
    trifecta_hit = actual_trifecta in predicted_probs

    # 的中確率（予測確率）
    trifecta_prob = predicted_probs.get(actual_trifecta, 0)

    # 的中順位（何番目に高い確率だったか）
    trifecta_rank = None
    for i, (comb, _) in enumerate(sorted_probs):
        if comb == actual_trifecta:
            trifecta_rank = i + 1
            break

    # 1着・2着・3着の個別的中
    first_hit = sorted_probs[0][0].split('-')[0] == str(actual_order[0][0])
    second_hit = sorted_probs[0][0].split('-')[1] == str(actual_order[1][0])
    third_hit = sorted_probs[0][0].split('-')[2] == str(actual_order[2][0])

    return {
        'actual_trifecta': actual_trifecta,
        'predicted_top1': sorted_probs[0][0],
        'predicted_top1_prob': sorted_probs[0][1],
        'trifecta_hit': trifecta_hit,
        'trifecta_prob': trifecta_prob,
        'trifecta_rank': trifecta_rank,
        'first_hit': first_hit,
        'second_hit': second_hit,
        'third_hit': third_hit,
        'top5_hit': trifecta_rank is not None and trifecta_rank <= 5,
        'top10_hit': trifecta_rank is not None and trifecta_rank <= 10,
        'top20_hit': trifecta_rank is not None and trifecta_rank <= 20,
    }


def run_backtest(db_path, start_date, end_date, use_hierarchical=True):
    """バックテストを実行"""
    print("=" * 60)
    print(f"階層的確率モデル バックテスト")
    print(f"期間: {start_date} - {end_date}")
    print(f"モデル: {'階層的確率モデル（学習済み）' if use_hierarchical else 'ナイーブ法'}")
    print("=" * 60)

    # 学習済みモデルを読み込み
    predictor = None
    if use_hierarchical:
        try:
            predictor = HierarchicalPredictor(db_path)
            predictor.load_models()
            if predictor._model_loaded:
                print("学習済みモデルを読み込みました")
            else:
                print("警告: モデルが読み込めませんでした。ナイーブ法を使用します")
        except Exception as e:
            print(f"モデル読み込みエラー: {e}")
            predictor = None

    conn = sqlite3.connect(db_path)

    # 対象レースを取得
    query = """
        SELECT DISTINCT r.id as race_id, r.race_date, r.venue_code, r.race_number
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE r.race_date BETWEEN ? AND ?
          AND res.rank IN ('1', '2', '3')
        GROUP BY r.id
        HAVING COUNT(*) >= 3
        ORDER BY r.race_date, r.venue_code, r.race_number
    """
    races_df = pd.read_sql_query(query, conn, params=(start_date, end_date))

    print(f"対象レース数: {len(races_df)}")

    # 結果を蓄積
    results = []
    error_count = 0

    for idx, row in races_df.iterrows():
        race_id = row['race_id']

        try:
            # 特徴量を取得
            features_df = get_race_features(conn, race_id)
            if len(features_df) != 6:
                continue

            # 結果を取得
            actual_results = get_race_results(conn, race_id)
            if len(actual_results) < 3:
                continue

            # 予測
            if use_hierarchical and predictor is not None:
                # 学習済み階層的モデルを使用
                result = predictor.predict_race_from_features(features_df)
                if 'error' in result:
                    # エラー時はナイーブ法にフォールバック
                    win_rates = features_df['win_rate'].fillna(10).values
                    course_bonus = np.array([1.5, 1.2, 1.0, 0.9, 0.8, 0.7])
                    actual_courses = features_df['actual_course'].fillna(features_df['pit_number']).values.astype(int)
                    adjusted_rates = win_rates.copy()
                    for i, course in enumerate(actual_courses):
                        if 1 <= course <= 6:
                            adjusted_rates[i] *= course_bonus[course - 1]
                    first_probs = adjusted_rates / adjusted_rates.sum()
                    predicted_probs = NaiveTrifectaCalculator.calculate(first_probs)
                else:
                    predicted_probs = result.get('trifecta_probs', {})
            elif use_hierarchical:
                # モデルなしの場合はナイーブ法（コース補正あり）
                from src.features.feature_transforms import RaceRelativeFeatureBuilder
                builder = RaceRelativeFeatureBuilder()
                features_df = builder.build_training_data(features_df)

                win_rates = features_df['win_rate'].fillna(10).values
                course_bonus = np.array([1.5, 1.2, 1.0, 0.9, 0.8, 0.7])
                actual_courses = features_df['actual_course'].fillna(features_df['pit_number']).values.astype(int)

                adjusted_rates = win_rates.copy()
                for i, course in enumerate(actual_courses):
                    if 1 <= course <= 6:
                        adjusted_rates[i] *= course_bonus[course - 1]

                first_probs = adjusted_rates / adjusted_rates.sum()
                predicted_probs = NaiveTrifectaCalculator.calculate(first_probs)
            else:
                # ナイーブ法（均等確率）
                first_probs = np.ones(6) / 6
                predicted_probs = NaiveTrifectaCalculator.calculate(first_probs)

            # 評価
            eval_result = evaluate_prediction(predicted_probs, actual_results)
            if eval_result:
                eval_result['race_id'] = race_id
                eval_result['race_date'] = row['race_date']
                eval_result['venue_code'] = row['venue_code']
                results.append(eval_result)

        except Exception as e:
            error_count += 1
            if error_count <= 5:
                print(f"エラー (race_id={race_id}): {e}")

        # 進捗表示
        if (idx + 1) % 100 == 0:
            print(f"処理中: {idx + 1}/{len(races_df)}")

    conn.close()

    # 結果を集計
    if not results:
        print("評価可能なレースがありませんでした")
        return

    results_df = pd.DataFrame(results)

    print("\n" + "=" * 60)
    print("バックテスト結果")
    print("=" * 60)

    total_races = len(results_df)
    print(f"\n【全体統計】 ({total_races}レース)")

    # 三連単的中率
    trifecta_top1_hit = results_df['predicted_top1'] == results_df['actual_trifecta']
    print(f"  三連単的中率（TOP1予測）: {trifecta_top1_hit.sum()}/{total_races} = {trifecta_top1_hit.mean()*100:.2f}%")

    top5_hit = results_df['top5_hit'].sum()
    print(f"  三連単TOP5内的中率: {top5_hit}/{total_races} = {results_df['top5_hit'].mean()*100:.2f}%")

    top10_hit = results_df['top10_hit'].sum()
    print(f"  三連単TOP10内的中率: {top10_hit}/{total_races} = {results_df['top10_hit'].mean()*100:.2f}%")

    top20_hit = results_df['top20_hit'].sum()
    print(f"  三連単TOP20内的中率: {top20_hit}/{total_races} = {results_df['top20_hit'].mean()*100:.2f}%")

    # 着順別的中率
    print(f"\n【着順別的中率】")
    first_hit = results_df['first_hit'].mean() * 100
    second_hit = results_df['second_hit'].mean() * 100
    third_hit = results_df['third_hit'].mean() * 100
    print(f"  1着的中率: {first_hit:.2f}%")
    print(f"  2着的中率: {second_hit:.2f}%")
    print(f"  3着的中率: {third_hit:.2f}%")

    # 的中時の予測確率分布
    print(f"\n【的中時の予測確率】")
    hit_probs = results_df[results_df['trifecta_rank'].notna()]['trifecta_prob']
    if len(hit_probs) > 0:
        print(f"  平均: {hit_probs.mean()*100:.3f}%")
        print(f"  最大: {hit_probs.max()*100:.3f}%")
        print(f"  最小: {hit_probs.min()*100:.3f}%")

    # 会場別集計
    print(f"\n【会場別三連単TOP10内的中率】")
    venue_stats = results_df.groupby('venue_code').agg({
        'top10_hit': ['sum', 'count', 'mean']
    })
    venue_stats.columns = ['hit', 'total', 'rate']
    venue_stats = venue_stats.sort_values('rate', ascending=False)
    for venue_code, row in venue_stats.head(10).iterrows():
        print(f"  {venue_code}: {row['hit']:.0f}/{row['total']:.0f} = {row['rate']*100:.1f}%")

    print("\n" + "=" * 60)

    return results_df


def main():
    parser = argparse.ArgumentParser(description='階層的確率モデルのバックテスト')
    parser.add_argument('--db', default='data/boatrace.db', help='DBパス')
    parser.add_argument('--start-date', default='2024-11-01', help='開始日')
    parser.add_argument('--end-date', default='2024-11-30', help='終了日')
    parser.add_argument('--naive', action='store_true', help='ナイーブ法で比較')

    args = parser.parse_args()

    # DBパスを絶対パスに
    db_path = os.path.join(PROJECT_ROOT, args.db)
    if not os.path.exists(db_path):
        print(f"データベースが見つかりません: {db_path}")
        return

    results = run_backtest(
        db_path,
        args.start_date,
        args.end_date,
        use_hierarchical=not args.naive
    )


if __name__ == '__main__':
    main()
