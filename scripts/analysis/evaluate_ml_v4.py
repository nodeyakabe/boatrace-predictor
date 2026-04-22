"""
Phase 2: ML v4 単体精度の測定

conditional_rank_v4 モデルと ルールベース（total_score）の
1着/2着/3着予測的中率を比較する。

比較対象:
  A) ML 1着予測: モデルの first_probs が最大の艇
  B) ルールベース 1着: total_score が最大の艇
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import pandas as pd
import numpy as np
from collections import defaultdict

from src.ml.conditional_rank_model import ConditionalRankModel

MODEL_NAME = "conditional_rank_v4_20260413_151415"
DB_PATH = "data/boatrace.db"
# 評価期間: 学習に使っていない直近6ヶ月（モデルの最終検証と同じ期間）
EVAL_START = "2025-07-01"
EVAL_END   = "2025-12-31"


def load_eval_data(db_path: str, start: str, end: str) -> pd.DataFrame:
    print(f"=== 評価データの読み込み ({start} ～ {end}) ===")
    conn = sqlite3.connect(db_path)
    query = f"""
    SELECT
        r.id as race_id,
        r.race_date,
        r.venue_code,
        CAST(res.pit_number AS INTEGER) as pit_number,
        CAST(res.rank AS INTEGER) as rank,
        e.win_rate,
        e.second_rate,
        e.third_rate,
        e.local_win_rate,
        e.local_second_rate,
        e.motor_second_rate,
        e.boat_second_rate,
        e.avg_st,
        rd.exhibition_time,
        rd.st_time        as exhibition_st,
        rd.exhibition_course,
        rd.tilt_angle,
        rc.wind_speed,
        rc.wave_height,
        rc.temperature,
        rc.water_temperature,
        COALESCE(rp_b.total_score, rp_a.total_score) as total_score
    FROM races r
    JOIN results res
        ON r.id = res.race_id
    JOIN entries e
        ON r.id = e.race_id AND res.pit_number = e.pit_number
    LEFT JOIN race_details rd
        ON r.id = rd.race_id AND res.pit_number = rd.pit_number
    LEFT JOIN race_conditions rc
        ON r.id = rc.race_id
    LEFT JOIN race_predictions rp_b
        ON r.id = rp_b.race_id
        AND rp_b.pit_number = CAST(res.pit_number AS INTEGER)
        AND rp_b.prediction_type = 'before'
    LEFT JOIN race_predictions rp_a
        ON r.id = rp_a.race_id
        AND rp_a.pit_number = CAST(res.pit_number AS INTEGER)
        AND rp_a.prediction_type = 'advance'
    WHERE r.race_date >= '{start}'
      AND r.race_date <= '{end}'
      AND res.rank IS NOT NULL
      AND CAST(res.rank AS INTEGER) BETWEEN 1 AND 6
    ORDER BY r.race_date, r.id, res.pit_number
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # 欠損値補完（中央値）
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].isnull().sum() > 0:
            df[col] = df[col].fillna(df[col].median())

    # 6艇揃っているレースのみ
    race_counts = df.groupby('race_id').size()
    valid = race_counts[race_counts == 6].index
    df = df[df['race_id'].isin(valid)].copy()

    print(f"  レコード数: {len(df):,}  ユニークレース: {df['race_id'].nunique():,}")
    print(f"  total_score有率: {df['total_score'].notna().mean()*100:.1f}%")
    return df


def evaluate(model: ConditionalRankModel, df: pd.DataFrame):
    """1着/連対/3連対 の的中率を ML と ルールベースで比較"""

    hits = defaultdict(int)
    total = 0
    errors = 0

    race_ids = df['race_id'].unique()

    for race_id in race_ids:
        race = df[df['race_id'] == race_id].copy().reset_index(drop=True)
        if len(race) != 6:
            continue

        actual_rank = race.set_index('pit_number')['rank'].to_dict()
        firsts  = [p for p, r in actual_rank.items() if r == 1]
        if not firsts:
            continue
        actual_first = firsts[0]

        # ルールベース: total_score 降順
        rule_sorted = race.sort_values('total_score', ascending=False)['pit_number'].tolist()

        # ML予測
        try:
            features = race.copy()
            # 1着確率
            X_1st = features.drop(
                [c for c in ['rank', 'race_id', 'race_date', 'venue_code'] if c in features.columns],
                axis=1
            )
            for col in model.feature_names:
                if col not in X_1st.columns:
                    X_1st[col] = 0
            X_1st_aligned = X_1st[model.feature_names]

            first_probs = model.models['first'].predict_proba(X_1st_aligned)[:, 1]
            ml_first_pos = np.argmax(first_probs)
            ml_first_pit = race.iloc[ml_first_pos]['pit_number']
        except Exception:
            errors += 1
            continue

        total += 1

        # 1着的中
        hits['rule_1st'] += (rule_sorted[0] == actual_first)
        hits['ml_1st']   += (ml_first_pit == actual_first)

        # 連対（1-2着どちらかが当たり）
        hits['rule_top2'] += (actual_first in rule_sorted[:2])
        # ML top2: first_probs 上位2艇
        top2_pos = np.argsort(first_probs)[::-1][:2]
        top2_pits = race.iloc[top2_pos]['pit_number'].tolist()
        hits['ml_top2'] += (actual_first in top2_pits)

        # 3着以内
        hits['rule_top3'] += (actual_first in rule_sorted[:3])
        top3_pos = np.argsort(first_probs)[::-1][:3]
        top3_pits = race.iloc[top3_pos]['pit_number'].tolist()
        hits['ml_top3'] += (actual_first in top3_pits)

    if total == 0:
        print("[ERROR] 評価できたレースが0件")
        return

    print(f"\n=== 評価結果 (n={total:,}レース, エラー={errors}) ===\n")
    print(f"  {'指標':<20}  {'ルールベース':>12}  {'ML v4':>12}  {'差分':>8}")
    print(f"  {'-'*55}")

    metrics = [
        ('1着的中率',  'rule_1st',  'ml_1st'),
        ('1-2着いずれか', 'rule_top2', 'ml_top2'),
        ('1-3着いずれか', 'rule_top3', 'ml_top3'),
    ]
    for label, rk, mk in metrics:
        r = hits[rk] / total * 100
        m = hits[mk] / total * 100
        diff = m - r
        sign = '+' if diff >= 0 else ''
        print(f"  {label:<20}  {r:>11.2f}%  {m:>11.2f}%  {sign}{diff:>6.2f}pt")

    # ランダム期待値
    print(f"\n  ランダム期待値（参考）")
    print(f"    1着: {1/6*100:.1f}%  連対: {2/6*100:.1f}%  3着以内: {3/6*100:.1f}%")


def main():
    print("=" * 65)
    print(f"Phase 2: ML v4 単体精度評価")
    print(f"モデル: {MODEL_NAME}")
    print(f"評価期間: {EVAL_START} ～ {EVAL_END}")
    print("=" * 65)

    model = ConditionalRankModel()
    model.load(MODEL_NAME)
    print(f"  1着特徴量: {len(model.feature_names)}")
    print(f"  2着特徴量: {len(model.second_feature_names)}")
    print(f"  3着特徴量: {len(model.third_feature_names)}")

    df = load_eval_data(DB_PATH, EVAL_START, EVAL_END)

    evaluate(model, df)

    print("\n" + "=" * 65)


if __name__ == "__main__":
    main()
