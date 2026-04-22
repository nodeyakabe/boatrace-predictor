#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
採用条件サブセット限定 ML consensus agree/disagree 分析

目的:
    OOS全レース評価（+35.49pt差）が採用条件サブセットでも有効かを検証。
    Opusが指摘した「全レース統計 ≠ 採用条件サブセット統計」の実測確認。

手順:
    1. 2025年ホールドアウトで採用条件にマッチするレースを抽出
    2. v4b モデルで推論し ML 1着を計算
    3. ML agree(=ルールベース1着と一致) / disagree でグループ分け
    4. 三連単的中率を比較
"""
import sys, os
import sqlite3
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from config.bet_conditions import STANDARD_BET_CONDITIONS
from scripts.backtest.backtest_helpers import get_race_ids_for_condition

MODEL_NAME = 'conditional_rank_v4b_20260413_160607'

def load_model():
    from src.ml.conditional_rank_model import ConditionalRankModel
    m = ConditionalRankModel()
    m.load(MODEL_NAME)
    print(f"[OK] モデルロード: {MODEL_NAME}")
    return m

def get_features_for_races(conn, race_ids):
    """対象レースの特徴量を一括取得"""
    ids_str = ','.join(str(r) for r in race_ids)
    query = f"""
    SELECT
        e.race_id,
        e.pit_number,
        e.win_rate, e.second_rate, e.third_rate,
        e.local_win_rate, e.local_second_rate,
        e.motor_second_rate, e.boat_second_rate,
        e.avg_st,
        rd.exhibition_time,
        rd.st_time        AS exhibition_st,
        rd.exhibition_course,
        rd.tilt_angle,
        rc.wind_speed, rc.wave_height,
        rc.temperature, rc.water_temperature,
        rp1.pit_number    AS rule_first_pit,
        rp1.confidence    AS rule_confidence
    FROM entries e
    JOIN race_predictions rp1
        ON e.race_id = rp1.race_id
        AND rp1.prediction_type = 'before'
        AND rp1.rank_prediction = 1
    LEFT JOIN race_details rd
        ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
    LEFT JOIN race_conditions rc
        ON e.race_id = rc.race_id
    WHERE e.race_id IN ({ids_str})
    ORDER BY e.race_id, e.pit_number
    """
    return pd.read_sql_query(query, conn)

def prefetch_actual_first(conn, race_ids):
    """対象レース全件の1着艇番を一括取得 → {race_id: actual_1st_pit}"""
    ids_str = ','.join(str(r) for r in race_ids)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT race_id, pit_number FROM results
        WHERE race_id IN ({ids_str})
          AND rank = 1
          AND (is_invalid IS NULL OR is_invalid = 0)
    """)
    return {row[0]: row[1] for row in cur.fetchall()}

def infer_ml_first(df_race, model):
    """レース内の6艇に対してML推論し1着pit_numberを返す"""
    feature_names = model.feature_names
    for col in feature_names:
        if col not in df_race.columns:
            df_race[col] = 0.0
    # 欠損をレース内中央値で補完
    for col in feature_names:
        if df_race[col].isnull().any():
            med = df_race[col].median()
            df_race[col] = df_race[col].fillna(med if pd.notna(med) else 0.0)
    X = df_race[feature_names].values.astype(np.float32)
    probs = model.models['first'].predict_proba(X)[:, 1]
    best = int(np.argmax(probs))
    return int(df_race.iloc[best]['pit_number'])

def main():
    print("=" * 65)
    print("採用条件サブセット限定 ML agree/disagree 分析（2025年 OOS）")
    print("=" * 65)

    model = load_model()
    conn = sqlite3.connect(DATABASE_PATH)
    cur  = conn.cursor()

    # 2025年のレースIDを取得（採用条件全体）
    active_conds = [c for c in STANDARD_BET_CONDITIONS if 'confidence' in c and c.get('confidence')]
    all_target_races = set()
    cond_race_map = {}
    for cond in active_conds:
        race_ids = get_race_ids_for_condition(cur, cond, '2025-01-01', '2025-12-31')
        cond_race_map[cond['id']] = race_ids
        all_target_races.update(race_ids)

    print(f"\n採用条件マッチレース数（2025年）: {len(all_target_races):,}件")
    for cond in active_conds:
        print(f"  {cond['id']}: {len(cond_race_map[cond['id']]):,}件")

    # 特徴量一括取得
    print(f"\n特徴量取得中...")
    df = get_features_for_races(conn, list(all_target_races))
    print(f"取得行数: {len(df):,}")

    # 1着結果を事前一括取得（ループ内でcursorを使わないようにする）
    print("1着結果を一括取得中...")
    actual_firsts = prefetch_actual_first(conn, list(all_target_races))
    print(f"1着結果取得: {len(actual_firsts):,}件")

    # レースごとにML推論
    print("ML推論中（レース内中央値補完）...")
    results = []
    skipped = 0
    for race_id, group in df.groupby('race_id', sort=False):
        if len(group) != 6:
            skipped += 1
            continue
        rule_first = int(group['rule_first_pit'].iloc[0])
        rule_conf  = group['rule_confidence'].iloc[0]
        ml_first   = infer_ml_first(group.copy(), model)
        agree      = (ml_first == rule_first)

        # 1着的中チェック（事前取得済みデータから）
        actual_first = actual_firsts.get(race_id)
        if actual_first is None:
            continue
        hit = (actual_first == rule_first)

        results.append({
            'race_id': race_id,
            'agree': agree,
            'hit': hit,
            'rule_conf': rule_conf
        })

    conn.close()
    print(f"スキップ（6艇未満）: {skipped}")

    df_res = pd.DataFrame(results)
    total = len(df_res)
    print(f"\n分析対象レース: {total:,}件")

    # ── 全体のagree/disagree分布 ──
    agree_cnt    = df_res['agree'].sum()
    disagree_cnt = total - agree_cnt
    agree_hit    = df_res[df_res['agree']]['hit'].mean() * 100
    disagree_hit = df_res[~df_res['agree']]['hit'].mean() * 100
    print(f"\n【全体 agree/disagree】")
    print(f"  agree    : {agree_cnt:,}件  1着的中率 {agree_hit:.2f}%")
    print(f"  disagree : {disagree_cnt:,}件  1着的中率 {disagree_hit:.2f}%")
    print(f"  差       : {agree_hit - disagree_hit:+.2f}pt")

    # ── 信頼度別 ──
    print(f"\n【信頼度別 agree/disagree 1着的中率】")
    print(f"{'信頼度':<6} {'agree件数':>8} {'agree的中%':>10} {'disagree件数':>12} {'disagree的中%':>13} {'差':>7}")
    for conf in ['A', 'B', 'C']:
        sub = df_res[df_res['rule_conf'] == conf]
        if len(sub) == 0:
            continue
        a  = sub[sub['agree']]
        d  = sub[~sub['agree']]
        ah = a['hit'].mean() * 100 if len(a) > 0 else 0
        dh = d['hit'].mean() * 100 if len(d) > 0 else 0
        print(f"  {conf:<6} {len(a):>8,} {ah:>10.2f}% {len(d):>12,} {dh:>13.2f}% {ah-dh:>+7.2f}pt")

    # ── 購入条件別 ──
    print(f"\n【購入条件別 agree/disagree 1着的中率（2025年サブセット）】")
    print(f"{'条件ID':<25} {'agree':>6} {'agree%':>8} {'disagree':>9} {'dis%':>7} {'差':>7}")
    for cond in active_conds:
        cond_ids = set(cond_race_map[cond['id']])
        sub = df_res[df_res['race_id'].isin(cond_ids)]
        if len(sub) == 0:
            continue
        a  = sub[sub['agree']]
        d  = sub[~sub['agree']]
        ah = a['hit'].mean() * 100 if len(a) > 0 else 0
        dh = d['hit'].mean() * 100 if len(d) > 0 else 0
        print(f"  {cond['id']:<25} {len(a):>6,} {ah:>8.2f}% {len(d):>9,} {dh:>7.2f}% {ah-dh:>+7.2f}pt")

    print("\n" + "=" * 65)
    print("[参考] 全レースOOS（2025年）: agree 60.93% vs disagree 25.43% = +35.49pt")
    print("[比較] 採用条件サブセット全体: agree {:.2f}% vs disagree {:.2f}% = {:+.2f}pt".format(
        agree_hit, disagree_hit, agree_hit - disagree_hit))
    print("=" * 65)

if __name__ == '__main__':
    main()
