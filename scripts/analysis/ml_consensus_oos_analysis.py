"""
MLコンセンサスフィルター OOS（Out-of-Sample）効果分析

【方針】
- モデル: conditional_rank_v4b（total_score除外・2020-2024学習）
- 評価期間: 2025年（完全 hold-out）
- 方式: 一括クエリでデータをメモリに読み込み → pandasバッチ推論（高速）

【測定内容】
  race_predictions（confidence A/B/C、rank_prediction=1）に対して
  ML top-1 が一致/不一致の 2グループで 1着的中率を比較。

  差 ≥ 5pt → MLコンセンサスフィルターに独立した信号がある（採用）
  差 < 5pt → 効果薄（MLフィルターは棚上げ）
"""

import sys
import os
import warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import pandas as pd
import numpy as np
from glob import glob

from src.ml.conditional_rank_model import ConditionalRankModel

DB_PATH   = 'data/boatrace.db'
EVAL_START = '2025-01-01'
EVAL_END   = '2025-12-31'


def find_latest_v4b_model():
    """最新の v4b モデル名を取得"""
    files = glob('models/conditional_rank_v4b_*_first.json')
    if not files:
        raise FileNotFoundError("v4bモデルが見つかりません。train_conditional_v4b.py を先に実行してください")
    latest = sorted(files)[-1]
    return os.path.basename(latest).replace('_first.json', '')


def load_all_data(conn, start, end):
    """
    一括クエリ: 評価期間の全特徴量 + race_predictions(confidence/rank) + 実結果 を取得。
    1回のSQL JOINで完結させてメモリに乗せる。
    """
    print(f"=== 一括クエリでデータ読み込み中 ({start} 〜 {end}) ===")
    query = f"""
    SELECT
        r.id as race_id,
        r.race_date,
        CAST(e.pit_number AS INTEGER) as pit_number,
        -- ML特徴量（total_score除外）
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
        -- ルールベース情報
        rp.confidence,
        rp.rank_prediction,
        -- 実結果
        CAST(res.rank AS INTEGER) as actual_rank
    FROM races r
    JOIN entries e ON r.id = e.race_id
    LEFT JOIN race_details rd
        ON r.id = rd.race_id AND e.pit_number = rd.pit_number
    LEFT JOIN race_conditions rc
        ON r.id = rc.race_id
    LEFT JOIN race_predictions rp
        ON r.id = rp.race_id
        AND rp.pit_number = e.pit_number
        AND rp.prediction_type = 'before'
    LEFT JOIN results res
        ON r.id = res.race_id AND e.pit_number = res.pit_number
    WHERE r.race_date >= '{start}'
      AND r.race_date <= '{end}'
    ORDER BY r.race_date, r.id, e.pit_number
    """
    df = pd.read_sql_query(query, conn)
    print(f"  読み込み: {len(df):,}行  レース: {df['race_id'].nunique():,}件")
    return df


def compute_ml_predictions(model, df):
    """
    全レースに対してML 1着確率をバッチ計算し、
    「ML が最も高い確率を付けた pit_number」を race ごとに返す。
    """
    print("=== ML推論（バッチ処理） ===")

    # 欠損補完
    feat_cols = model.feature_names
    for col in feat_cols:
        if col not in df.columns:
            df[col] = 0.0
    df[feat_cols] = df[feat_cols].fillna(df[feat_cols].median())

    # XGBoost predict_proba（全行一括）
    X = df[feat_cols].values.astype(np.float32)
    proba = model.models['first'].predict_proba(X)[:, 1]
    df = df.copy()
    df['ml_first_prob'] = proba

    # レースごとに ML top-1 pit を選択
    ml_top1 = (
        df.groupby('race_id')
          .apply(lambda g: int(g.loc[g['ml_first_prob'].idxmax(), 'pit_number']))
          .reset_index()
          .rename(columns={0: 'ml_first_pit'})
    )
    print(f"  推論完了: {len(ml_top1):,}レース")
    return ml_top1


def analyze_consensus_effect(df, ml_top1):
    """
    race_predictions で confidence A/B/C かつ rank_prediction=1 の行を対象に
    ML 同意/不同意 で 1着的中率を比較。
    """
    print("=== コンセンサス効果分析 ===")

    # 対象: confidence A/B/C の rank_prediction=1 行
    target = df[
        df['rank_prediction'] == 1
    ].copy()
    target = target[target['confidence'].isin(['A', 'B', 'C'])]

    if target.empty:
        print("  [ERROR] 対象レースが0件")
        return

    # ML top-1 をマージ
    target = target.merge(ml_top1, on='race_id', how='inner')

    # 同意フラグ
    target['ml_agrees'] = (target['ml_first_pit'] == target['pit_number'])
    target['is_hit'] = (target['actual_rank'] == 1)

    n_total  = len(target)
    n_agree  = target['ml_agrees'].sum()
    n_dis    = n_total - n_agree

    print(f"\n  対象レース総数: {n_total:,}")
    print(f"  ML同意: {n_agree:,} ({n_agree/n_total*100:.1f}%)")
    print(f"  ML不同意: {n_dis:,} ({n_dis/n_total*100:.1f}%)")

    hit_agree = target[target['ml_agrees']]['is_hit'].mean() * 100
    hit_dis   = target[~target['ml_agrees']]['is_hit'].mean() * 100
    hit_all   = target['is_hit'].mean() * 100
    diff      = hit_agree - hit_dis

    print(f"\n  {'グループ':<15} {'件数':>7}  {'1着的中率':>10}")
    print(f"  {'-'*38}")
    print(f"  {'全体':<15} {n_total:>7,}  {hit_all:>9.2f}%")
    print(f"  {'ML同意':<15} {n_agree:>7,}  {hit_agree:>9.2f}%")
    print(f"  {'ML不同意':<15} {n_dis:>7,}  {hit_dis:>9.2f}%")
    print(f"\n  同意 vs 不同意の差: {diff:+.2f}pt")

    # 信頼度別
    print(f"\n  --- 信頼度別 ---")
    print(f"  {'信頼度':<5} {'同意的中率':>10}  {'不同意的中率':>12}  {'差':>8}  {'不同意割合':>10}")
    for conf in ('A', 'B', 'C'):
        sub = target[target['confidence'] == conf]
        if len(sub) == 0:
            continue
        h_a = sub[sub['ml_agrees']]['is_hit'].mean() * 100
        h_d = sub[~sub['ml_agrees']]['is_hit'].mean() * 100
        d   = h_a - h_d
        dis_rate = (~sub['ml_agrees']).mean() * 100
        print(f"  {conf:<5} {h_a:>9.2f}%  {h_d:>11.2f}%  {d:>+7.2f}pt  {dis_rate:>9.1f}%")

    # 判定
    print(f"\n{'=' * 60}")
    if diff >= 5.0:
        print(f"  [OK] 判定: 採用推奨 (差 {diff:.2f}pt >= 5pt)")
        print(f"     -> MLコンセンサスフィルターに独立した信号がある")
        print(f"     -> Phase3 有効化 + 全年度再生成へ進む")
    elif diff >= 2.0:
        print(f"  [!] 判定: 要検討 (差 {diff:.2f}pt, 2-5pt)")
        print(f"     -> 効果は小さい。採用するか棚上げか判断が必要")
    else:
        print(f"  [NG] 判定: 棚上げ (差 {diff:.2f}pt < 2pt)")
        print(f"     -> MLフィルターに独立した信号がない（total_score依存）")
    print(f"{'=' * 60}")


def main():
    model_name = find_latest_v4b_model()
    print("=" * 60)
    print("ML コンセンサスフィルター OOS 効果分析")
    print(f"モデル: {model_name}")
    print(f"評価期間: {EVAL_START} 〜 {EVAL_END}")
    print("=" * 60)

    model = ConditionalRankModel()
    model.load(model_name)
    print(f"  1着特徴量数: {len(model.feature_names)}")
    print(f"  特徴量: {model.feature_names}")

    conn = sqlite3.connect(DB_PATH)
    df = load_all_data(conn, EVAL_START, EVAL_END)
    conn.close()

    ml_top1 = compute_ml_predictions(model, df)
    analyze_consensus_effect(df, ml_top1)


if __name__ == '__main__':
    main()
