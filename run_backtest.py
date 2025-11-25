"""
条件付きモデルを使ったバックテスト
実際のオッズデータを使用して回収率をシミュレーション
"""
import sys
import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ml.conditional_rank_model import ConditionalRankModel


def load_race_data_with_odds(db_path: str, start_date: str, end_date: str) -> pd.DataFrame:
    """オッズ情報を含むレースデータを読み込み"""
    print(f"データ読み込み: {start_date} ~ {end_date}")

    with sqlite3.connect(db_path) as conn:
        query = """
            SELECT
                r.id as race_id,
                r.race_date,
                e.pit_number,
                COALESCE(e.win_rate, 0) as win_rate,
                COALESCE(e.second_rate, 0) as second_rate,
                COALESCE(e.third_rate, 0) as third_rate,
                COALESCE(e.motor_second_rate, 0) as motor_2nd_rate,
                COALESCE(e.motor_third_rate, 0) as motor_3rd_rate,
                COALESCE(e.boat_second_rate, 0) as boat_2nd_rate,
                COALESCE(e.boat_third_rate, 0) as boat_3rd_rate,
                COALESCE(e.racer_weight, 52) as weight,
                COALESCE(e.avg_st, 0.15) as avg_st,
                COALESCE(e.local_win_rate, 0) as local_win_rate,
                e.racer_rank,
                res.rank as result_rank
            FROM races r
            JOIN entries e ON r.id = e.race_id
            JOIN results res ON r.id = res.race_id AND e.pit_number = res.pit_number
            WHERE r.race_date BETWEEN ? AND ?
                AND res.rank IN ('1', '2', '3', '4', '5', '6')
            ORDER BY r.race_date, r.id, e.pit_number
        """
        df = pd.read_sql_query(query, conn, params=(start_date, end_date))

        # オッズデータを取得（payoutsテーブルから確定オッズを算出）
        odds_df = pd.DataFrame()
        try:
            # payoutsテーブルから3連単払戻データを取得
            odds_query = """
                SELECT
                    p.race_id,
                    p.combination as trifecta_combo,
                    p.amount / 100.0 as odds
                FROM payouts p
                JOIN races r ON p.race_id = r.id
                WHERE p.bet_type = 'trifecta'
                    AND r.race_date BETWEEN ? AND ?
            """
            odds_df = pd.read_sql_query(odds_query, conn, params=(start_date, end_date))
            print(f"  確定オッズデータ: {len(odds_df)}レース")
        except Exception as e:
            print(f"  オッズデータ: 利用不可（固定オッズを使用）- {e}")

    print(f"  レースデータ: {len(df)}行")

    return df, odds_df


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """特徴量を準備"""
    rank_map = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
    df['racer_rank_score'] = df['racer_rank'].map(rank_map).fillna(2)

    feature_cols = [
        'race_id', 'pit_number',
        'win_rate', 'second_rate', 'third_rate',
        'motor_2nd_rate', 'motor_3rd_rate',
        'boat_2nd_rate', 'boat_3rd_rate',
        'weight', 'avg_st', 'local_win_rate', 'racer_rank_score'
    ]

    # 欠損値処理
    for col in feature_cols:
        if col in df.columns and col not in ['race_id', 'pit_number']:
            df[col] = df[col].fillna(df[col].median() if df[col].dtype in ['float64', 'int64'] else 0)

    df['rank'] = df['result_rank'].astype(int)

    return df[feature_cols + ['rank']].copy()


def run_backtest(model: ConditionalRankModel, race_df: pd.DataFrame, odds_df: pd.DataFrame,
                 bet_amount: float = 100.0, min_prob_threshold: float = 0.01,
                 min_expected_value: float = 1.0) -> dict:
    """バックテストを実行"""
    print("\n" + "=" * 60)
    print("バックテスト実行")
    print("=" * 60)

    race_ids = race_df['race_id'].unique()
    total_races = len(race_ids)
    print(f"対象レース数: {total_races}")

    # サンプリング（テスト用）
    if total_races > 100:
        np.random.seed(42)
        race_ids = np.random.choice(race_ids, 100, replace=False)
        print(f"サンプリング: {len(race_ids)}レース")

    # オッズをDictに変換（的中組み合わせの確定オッズ）
    odds_dict = {}
    if len(odds_df) > 0:
        for _, row in odds_df.iterrows():
            key = (row['race_id'], row['trifecta_combo'])
            odds_dict[key] = row['odds']

    total_bet = 0.0
    total_return = 0.0
    bets_placed = 0
    wins = 0
    top3_hits = 0

    # デバッグ用統計
    prob_stats = []

    for race_id in race_ids:
        race_data = race_df[race_df['race_id'] == race_id].copy()

        if len(race_data) != 6:
            continue

        # 特徴量準備
        feature_cols = [col for col in race_data.columns if col not in ['race_id', 'rank']]

        try:
            race_features = race_data[feature_cols].copy()
            trifecta_probs = model.predict_trifecta_probabilities(race_features)

            if not trifecta_probs:
                continue

            # 実際の結果
            actual_ranks = race_data.sort_values('rank')
            actual_combo = f"{int(actual_ranks.iloc[0]['pit_number'])}-{int(actual_ranks.iloc[1]['pit_number'])}-{int(actual_ranks.iloc[2]['pit_number'])}"

            # 最高確率の組み合わせを選択
            top_combo = max(trifecta_probs.items(), key=lambda x: x[1])
            pred_combo, pred_prob = top_combo

            prob_stats.append(pred_prob)

            # 確定オッズを取得（的中組み合わせのみ）
            actual_odds = odds_dict.get((race_id, actual_combo), 0)

            # 予測組み合わせのオッズを確率ベースで推定
            # 3連単の120通りに対し、確率の逆数をオッズとして推定
            # 控除率25%を考慮して0.75を掛ける
            if pred_prob > 0:
                estimated_odds = (1.0 / pred_prob) * 0.75
                estimated_odds = max(1.0, min(estimated_odds, 10000.0))
            else:
                estimated_odds = 100.0

            # 期待値計算（予測確率 × 推定オッズ）
            # 注意: これは推定期待値であり、実際のオッズは異なる可能性が高い
            expected_value = pred_prob * estimated_odds

            # 賭け条件: 確率閾値のみでフィルタ（期待値は常に約0.75になるため）
            if pred_prob >= min_prob_threshold:
                total_bet += bet_amount
                bets_placed += 1

                # 的中判定
                if pred_combo == actual_combo:
                    # 的中した場合は確定オッズを使用（あれば）
                    if actual_odds > 0:
                        win_amount = bet_amount * actual_odds
                    else:
                        # 確定オッズがない場合は推定オッズを使用
                        win_amount = bet_amount * estimated_odds
                    total_return += win_amount
                    wins += 1

            # Top3含有率チェック（統計用）
            top3_combos = sorted(trifecta_probs.items(), key=lambda x: x[1], reverse=True)[:3]
            if any(combo == actual_combo for combo, _ in top3_combos):
                top3_hits += 1

        except Exception as e:
            continue

    # 結果集計
    roi = (total_return / total_bet * 100) if total_bet > 0 else 0
    hit_rate = (wins / bets_placed * 100) if bets_placed > 0 else 0
    top3_rate = (top3_hits / len(race_ids) * 100) if len(race_ids) > 0 else 0

    # 確率統計
    if prob_stats:
        avg_prob = np.mean(prob_stats)
        max_prob = np.max(prob_stats)
        min_prob = np.min(prob_stats)
        print(f"\n予測確率統計:")
        print(f"  平均: {avg_prob:.4f} ({avg_prob*100:.2f}%)")
        print(f"  最大: {max_prob:.4f} ({max_prob*100:.2f}%)")
        print(f"  最小: {min_prob:.4f} ({min_prob*100:.2f}%)")

    print(f"\n=== バックテスト結果 ===")
    print(f"賭けレース数: {bets_placed}")
    print(f"的中数: {wins}")
    print(f"的中率: {hit_rate:.2f}%")
    print(f"Top3含有率: {top3_rate:.2f}%")
    print(f"総賭け金: {total_bet:,.0f}円")
    print(f"総払戻金: {total_return:,.0f}円")
    print(f"回収率: {roi:.1f}%")
    print(f"損益: {total_return - total_bet:+,.0f}円")

    return {
        'total_races': len(race_ids),
        'bets_placed': bets_placed,
        'wins': wins,
        'hit_rate': hit_rate,
        'top3_rate': top3_rate,
        'total_bet': total_bet,
        'total_return': total_return,
        'roi': roi,
        'profit': total_return - total_bet
    }


def main():
    """メイン実行"""
    print("=" * 60)
    print("条件付きモデル バックテスト")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    db_path = "data/boatrace.db"

    if not os.path.exists(db_path):
        print(f"[ERROR] DBファイルが見つかりません: {db_path}")
        return

    # モデル読み込み
    print("\nモデル読み込み中...")
    model = ConditionalRankModel(model_dir='models')
    model.load('conditional_rank_v1')
    print(f"特徴量数: {len(model.feature_names)}")

    # テストデータ読み込み（2025年3月のデータを使用）
    test_start = "2025-03-01"
    test_end = "2025-03-31"

    race_df, odds_df = load_race_data_with_odds(db_path, test_start, test_end)

    if len(race_df) == 0:
        print("[ERROR] テストデータが見つかりません")
        return

    # 特徴量準備
    race_df = prepare_features(race_df)
    print(f"準備完了: {len(race_df)//6}レース")

    # バックテスト実行
    # 戦略1: 高期待値のみ
    print("\n--- 戦略1: 期待値1.5以上 ---")
    results1 = run_backtest(model, race_df, odds_df,
                           min_prob_threshold=0.01, min_expected_value=1.5)

    # 戦略2: より厳しい条件
    print("\n--- 戦略2: 期待値2.0以上 ---")
    results2 = run_backtest(model, race_df, odds_df,
                           min_prob_threshold=0.02, min_expected_value=2.0)

    # 結果保存
    import json
    with open('models/backtest_results.json', 'w', encoding='utf-8') as f:
        json.dump({
            'strategy_1': results1,
            'strategy_2': results2,
            'test_period': f"{test_start} ~ {test_end}",
            'timestamp': datetime.now().isoformat()
        }, f, indent=2, ensure_ascii=False)

    print(f"\n結果を models/backtest_results.json に保存しました")


if __name__ == "__main__":
    main()
