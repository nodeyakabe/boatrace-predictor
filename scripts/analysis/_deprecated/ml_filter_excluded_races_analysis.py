#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MLコンセンサスフィルターで除外された54件の三連単結果分析

目的:
    フィルター適用時に 823件→769件 と減少した54件が
    実際にどんな三連単結果だったかを直接確認する。

    「disagree群に高配当三連単的中が含まれていたのか？」を実証。

手順:
    1. フィルターなし（現行）バックテストで買い目リストを取得
    2. フィルターあり（v4b disagree→confidence downgrade）で買い目リストを取得
    3. 差分（除外54件）の三連単的中・配当・ROIを集計
    4. agree/disagree 別の三連単的中率・ROIも計算
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

CONFIDENCE_ORDER = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1}
ORDER_TO_CONF    = {5: 'A', 4: 'B', 3: 'C', 2: 'D', 1: 'E'}


def load_model():
    from src.ml.conditional_rank_model import ConditionalRankModel
    m = ConditionalRankModel()
    m.load(MODEL_NAME)
    return m


def get_ml_disagree_races(conn, model):
    """
    全期間の before 予測レースに対して v4b を適用し、
    disagree レースの race_id と元のconfidence を返す
    """
    query = """
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
        rp1.confidence    AS rule_confidence,
        rp1.pit_number    AS rule_first_pit
    FROM entries e
    JOIN race_predictions rp1
        ON e.race_id = rp1.race_id
        AND rp1.prediction_type = 'before'
        AND rp1.rank_prediction = 1
    LEFT JOIN race_details rd
        ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
    LEFT JOIN race_conditions rc
        ON e.race_id = rc.race_id
    ORDER BY e.race_id, e.pit_number
    """
    print("[INFO] 特徴量一括取得中...")
    df = pd.read_sql_query(query, conn)
    print(f"[INFO] 取得行数: {len(df):,}")

    feature_names = model.feature_names
    clf = model.models['first']

    for col in feature_names:
        if col not in df.columns:
            df[col] = 0.0
        elif df[col].isnull().any():
            df[col] = df.groupby('race_id')[col].transform(
                lambda x: x.fillna(x.median())
            )
            if df[col].isnull().any():
                med = df[col].median()
                df[col] = df[col].fillna(med if pd.notna(med) else 0.0)

    X_all = df[feature_names].values.astype(np.float32)
    probs = clf.predict_proba(X_all)[:, 1]
    df['ml_prob'] = probs

    disagree_map = {}  # {race_id: (rule_confidence, downgraded_confidence)}
    agree_set = set()
    skipped = 0

    for race_id, group in df.groupby('race_id', sort=False):
        if len(group) != 6:
            skipped += 1
            continue
        rule_conf      = group['rule_confidence'].iloc[0]
        rule_first_pit = int(group['rule_first_pit'].iloc[0])
        ml_first_pit   = int(group['pit_number'].values[group['ml_prob'].values.argmax()])

        if ml_first_pit != rule_first_pit:
            cur_level = CONFIDENCE_ORDER.get(rule_conf, 3)
            new_level = max(1, cur_level - 1)
            new_conf  = ORDER_TO_CONF[new_level]
            disagree_map[race_id] = (rule_conf, new_conf)
        else:
            agree_set.add(race_id)

    print(f"[INFO] skipped（6艇未満）: {skipped:,}")
    print(f"[INFO] agree: {len(agree_set):,}件 / disagree: {len(disagree_map):,}件")
    return agree_set, disagree_map


def get_backtest_bets(conn, confidence_override=None):
    """
    採用条件でマッチするレースの買い目を取得。
    confidence_override: {race_id: new_conf} で信頼度を上書きする（フィルター適用シミュレーション）

    戻り値: DataFrame with columns [race_id, cond_id, confidence, p1, p2, p3, odds, hit, payout]
    """
    active_conds = [c for c in STANDARD_BET_CONDITIONS if c.get('confidence')]
    cur = conn.cursor()

    rows = []
    for cond in active_conds:
        race_ids = get_race_ids_for_condition(cur, cond, '2020-01-01', '2025-12-31')
        for race_id in race_ids:
            # 予測取得
            cur.execute("""
                SELECT rank_prediction, pit_number, confidence
                FROM race_predictions
                WHERE race_id = ? AND prediction_type = 'before' AND rank_prediction IN (1,2,3)
                ORDER BY rank_prediction
            """, (race_id,))
            preds = cur.fetchall()
            if len(preds) < 3:
                continue
            pred_map = {r: p for r, p, _ in preds}
            orig_conf = preds[0][2]  # rank_prediction=1 の confidence

            # フィルター適用後の confidence
            eff_conf = confidence_override.get(race_id, orig_conf) if confidence_override else orig_conf

            # 信頼度チェック
            if eff_conf not in cond.get('confidence', []):
                continue

            p1 = pred_map.get(1)
            p2 = pred_map.get(2)
            p3 = pred_map.get(3)
            if None in (p1, p2, p3):
                continue

            combo = f"{p1}-{p2}-{p3}"

            # オッズ取得
            cur.execute("""
                SELECT odds FROM trifecta_odds
                WHERE race_id = ? AND combination = ?
            """, (race_id, combo))
            odds_row = cur.fetchone()
            if odds_row is None:
                continue
            odds = odds_row[0]
            if odds < cond.get('odds_min', 0) or odds > cond.get('odds_max', 9999):
                continue

            # 結果取得
            cur.execute("""
                SELECT pit_number, rank FROM results
                WHERE race_id = ? AND rank IN (1,2,3) AND (is_invalid IS NULL OR is_invalid = 0)
                ORDER BY rank
            """, (race_id,))
            result_rows = cur.fetchall()
            if len(result_rows) < 3:
                continue
            actual = {rank: pit for pit, rank in result_rows}
            hit = (actual.get(1) == p1 and actual.get(2) == p2 and actual.get(3) == p3)
            payout = int(odds * 100) if hit else 0

            rows.append({
                'race_id': race_id,
                'cond_id': cond['id'],
                'orig_conf': orig_conf,
                'eff_conf': eff_conf,
                'p1': p1, 'p2': p2, 'p3': p3,
                'odds': odds,
                'hit': hit,
                'payout': payout,
            })

    return pd.DataFrame(rows)


def main():
    print("=" * 65)
    print("MLフィルター除外54件の三連単結果分析")
    print("=" * 65)

    model = load_model()
    conn  = sqlite3.connect(DATABASE_PATH)

    # Step1: agree/disagree 分類
    print("\n[Step1] ML agree/disagree 分類...")
    agree_set, disagree_map = get_ml_disagree_races(conn, model)

    # confidence_override: disagree → downgrade
    conf_override = {race_id: new_conf for race_id, (_, new_conf) in disagree_map.items()}

    # Step2: フィルターなし買い目リスト
    print("\n[Step2] フィルターなし買い目リスト取得...")
    df_no_filter = get_backtest_bets(conn, confidence_override=None)
    print(f"  フィルターなし: {len(df_no_filter):,}件")

    # Step3: フィルターあり買い目リスト
    print("\n[Step3] フィルターあり買い目リスト取得...")
    df_with_filter = get_backtest_bets(conn, confidence_override=conf_override)
    print(f"  フィルターあり: {len(df_with_filter):,}件")

    conn.close()

    # ── 除外レース特定 ──
    no_filter_ids  = set(df_no_filter['race_id'].unique())
    with_filter_ids = set(df_with_filter['race_id'].unique())
    excluded_ids = no_filter_ids - with_filter_ids
    print(f"\n除外レース数: {len(excluded_ids):,}件")

    df_excluded = df_no_filter[df_no_filter['race_id'].isin(excluded_ids)].copy()

    print(f"\n{'='*65}")
    print("【除外54件の三連単結果】")
    print(f"{'='*65}")
    print(f"  件数       : {len(df_excluded):,}件")
    hit_cnt = df_excluded['hit'].sum()
    hit_rate = df_excluded['hit'].mean() * 100
    total_paid = df_excluded['payout'].sum()
    total_invest = len(df_excluded) * 100
    roi = total_paid / total_invest * 100 if total_invest > 0 else 0
    print(f"  三連単的中  : {hit_cnt}件  ({hit_rate:.2f}%)")
    print(f"  収支       : {total_paid - total_invest:+,}円")
    print(f"  ROI        : {roi:.1f}%")
    if hit_cnt > 0:
        print(f"\n  的中した買い目:")
        for _, r in df_excluded[df_excluded['hit']].iterrows():
            print(f"    race_id={r['race_id']}  odds={r['odds']:.1f}倍  "
                  f"payout={r['payout']:,}円  conf={r['orig_conf']}→{r['eff_conf']}  条件={r['cond_id']}")

    # ── agree/disagree 別の三連単成績 ──
    print(f"\n{'='*65}")
    print("【agree / disagree 別の三連単成績（全期間・採用条件内）】")
    print(f"{'='*65}")

    df_no_filter['group'] = df_no_filter['race_id'].apply(
        lambda x: 'disagree' if x in disagree_map else 'agree'
    )
    for grp in ['agree', 'disagree']:
        sub = df_no_filter[df_no_filter['group'] == grp]
        if len(sub) == 0:
            continue
        h  = sub['hit'].sum()
        hr = sub['hit'].mean() * 100
        pd_ = sub['payout'].sum()
        inv = len(sub) * 100
        roi_ = pd_ / inv * 100 if inv > 0 else 0
        print(f"  {grp:<10}: {len(sub):,}件  三連単的中率 {hr:.2f}%  収支 {pd_-inv:+,}円  ROI {roi_:.1f}%")

    print(f"\n{'='*65}")
    print("[参考] フィルターなし全体: "
          f"{len(df_no_filter):,}件  "
          f"ROI {df_no_filter['payout'].sum() / (len(df_no_filter)*100) * 100:.1f}%")
    print(f"[参考] フィルターあり全体: "
          f"{len(df_with_filter):,}件  "
          f"ROI {df_with_filter['payout'].sum() / (len(df_with_filter)*100) * 100:.1f}%")
    print(f"{'='*65}")


if __name__ == '__main__':
    main()
