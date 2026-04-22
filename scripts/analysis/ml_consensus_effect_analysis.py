"""
MLコンセンサスフィルターの効果分析

既存のrace_predictions（confidence='A','B','C'）に対して
conditional_rank_v4 の同意/不同意でヒット率・ROIを比較する。

これにより、MLコンセンサスフィルターを有効にした場合の効果を推定する。
"""

import sys
import os
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import pandas as pd
import numpy as np
from collections import defaultdict

from src.ml.conditional_rank_model import ConditionalRankModel

MODEL_NAME = "conditional_rank_v4_20260413_151415"
DB_PATH = "data/boatrace.db"
EVAL_START = "2020-01-01"
EVAL_END   = "2025-12-31"
CONFIDENCE_FILTER = ('A', 'B', 'C')  # バックテストで対象になる信頼度


def load_bet_candidates(conn, start, end):
    """
    race_predictions から信頼度A/B/Cかつ rank_prediction=1 のレース一覧を取得。
    実際にバックテストで買い目候補になるレース（予測1着艇の情報）。
    """
    query = f"""
    SELECT
        rp.race_id,
        rp.pit_number as pred_first_pit,
        rp.confidence,
        rp.total_score,
        r.race_date,
        res.rank as actual_rank
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    LEFT JOIN results res
        ON rp.race_id = res.race_id
        AND rp.pit_number = res.pit_number
    WHERE rp.prediction_type = 'before'
      AND rp.rank_prediction = 1
      AND rp.confidence IN ('A', 'B', 'C')
      AND r.race_date >= '{start}'
      AND r.race_date <= '{end}'
    ORDER BY r.race_date, rp.race_id
    """
    return pd.read_sql_query(query, conn)


def load_ml_features(conn, race_id):
    """1レース分のML特徴量をDBから取得"""
    query = """
    SELECT
        e.pit_number,
        e.win_rate, e.second_rate, e.third_rate,
        e.local_win_rate, e.local_second_rate,
        e.motor_second_rate, e.boat_second_rate,
        e.avg_st,
        rd.exhibition_time,
        rd.st_time        as exhibition_st,
        rd.exhibition_course,
        rd.tilt_angle,
        rc.wind_speed, rc.wave_height, rc.temperature, rc.water_temperature,
        COALESCE(rp_b.total_score, rp_a.total_score) as total_score
    FROM entries e
    LEFT JOIN race_details rd
        ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
    LEFT JOIN race_conditions rc
        ON e.race_id = rc.race_id
    LEFT JOIN race_predictions rp_b
        ON e.race_id = rp_b.race_id
        AND rp_b.pit_number = e.pit_number
        AND rp_b.prediction_type = 'before'
    LEFT JOIN race_predictions rp_a
        ON e.race_id = rp_a.race_id
        AND rp_a.pit_number = e.pit_number
        AND rp_a.prediction_type = 'advance'
    WHERE e.race_id = ?
    ORDER BY e.pit_number
    """
    df = pd.read_sql_query(query, conn, params=(race_id,))
    return df if len(df) == 6 else None


def get_ml_first_prediction(model, features_df):
    """ML モデルが最も高い1着確率を付けた pit_number を返す"""
    X = features_df.drop(['pit_number'], axis=1, errors='ignore')
    for col in model.feature_names:
        if col not in X.columns:
            X[col] = 0.0
    X = X[model.feature_names]
    # 欠損補完
    X = X.fillna(X.median())
    first_probs = model.models['first'].predict_proba(X)[:, 1]
    return int(features_df.iloc[int(np.argmax(first_probs))]['pit_number'])


def main():
    print("=" * 65)
    print("ML コンセンサスフィルター効果分析")
    print(f"評価期間: {EVAL_START} ～ {EVAL_END}")
    print(f"信頼度フィルター: {CONFIDENCE_FILTER}")
    print("=" * 65)

    model = ConditionalRankModel()
    model.load(MODEL_NAME)

    conn = sqlite3.connect(DB_PATH)

    # バックテスト対象レースを取得
    bets = load_bet_candidates(conn, EVAL_START, EVAL_END)
    print(f"\n対象レース数: {len(bets):,}  (信頼度A/B/C・rank_prediction=1)\n")

    stats = defaultdict(lambda: {'total': 0, 'hit': 0})
    errors = 0

    for _, row in bets.iterrows():
        race_id = row['race_id']
        pred_first = int(row['pred_first_pit'])
        actual_rank = row.get('actual_rank')
        hit = (actual_rank == 1) if pd.notna(actual_rank) else None

        features = load_ml_features(conn, race_id)
        if features is None:
            errors += 1
            continue

        try:
            ml_first = get_ml_first_prediction(model, features)
        except Exception:
            errors += 1
            continue

        conf = row['confidence']
        agrees = (ml_first == pred_first)
        key = f"{conf}_{'agree' if agrees else 'disagree'}"

        stats[key]['total'] += 1
        stats[conf + '_all']['total'] += 1
        if hit is not None:
            if hit:
                stats[key]['hit'] += 1
                stats[conf + '_all']['hit'] += 1

    conn.close()

    print(f"処理完了 (エラー={errors})\n")

    print(f"  {'ラベル':<20} {'件数':>7}  {'的中率':>8}  {'対全体比':>8}")
    print(f"  {'-'*50}")

    total_all = sum(v['total'] for k, v in stats.items() if k.endswith('_all'))
    for conf in ('A', 'B', 'C'):
        all_key  = conf + '_all'
        agr_key  = conf + '_agree'
        dis_key  = conf + '_disagree'

        for key in [all_key, agr_key, dis_key]:
            d = stats.get(key, {'total': 0, 'hit': 0})
            n = d['total']
            h = d['hit']
            rate = h / n * 100 if n > 0 else 0
            ratio = n / total_all * 100 if total_all > 0 else 0
            print(f"  {key:<20} {n:>7,}  {rate:>7.2f}%  {ratio:>7.1f}%")
        print()

    # 全体サマリー
    all_agree   = sum(v['total'] for k, v in stats.items() if k.endswith('_agree'))
    all_disagree = sum(v['total'] for k, v in stats.items() if k.endswith('_disagree'))
    hit_agree   = sum(v['hit']   for k, v in stats.items() if k.endswith('_agree'))
    hit_disagree = sum(v['hit']  for k, v in stats.items() if k.endswith('_disagree'))

    print(f"  {'全体(同意)':<20} {all_agree:>7,}  {hit_agree/all_agree*100:>7.2f}%")
    print(f"  {'全体(不同意)':<20} {all_disagree:>7,}  {hit_disagree/all_disagree*100:>7.2f}%")
    diff = hit_agree/all_agree*100 - hit_disagree/all_disagree*100
    print(f"\n  同意 vs 不同意の1着的中率差: {diff:+.2f}pt")
    print(f"  不同意の割合: {all_disagree/(all_agree+all_disagree)*100:.1f}%")
    print(f"  → フィルター適用で約 {all_disagree/(all_agree+all_disagree)*100:.1f}% の賭けを排除")
    print("=" * 65)


if __name__ == "__main__":
    main()
