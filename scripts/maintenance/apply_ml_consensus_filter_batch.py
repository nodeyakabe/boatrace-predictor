#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MLコンセンサスフィルター バッチ適用スクリプト

目的:
    既存の before 予測に対して、ML consensus filter を高速バッチ処理で適用する。
    generate_before_fast.py --force は1レースずつSQLを叩くため低速。
    本スクリプトは全レースの特徴量を一括クエリし、バッチ推論→バッチUPDATEで完結する。

処理概要:
    1. 対象レース（before予測あり）の特徴量を一括JOIN
    2. v4b モデルで全レース一括推論
    3. ML予測1着 != rule-based 1着 → confidence を1段階ダウングレード
    4. 変更対象のみ executemany でバッチ UPDATE

使用方法:
    python scripts/maintenance/apply_ml_consensus_filter_batch.py
    python scripts/maintenance/apply_ml_consensus_filter_batch.py --year 2025
    python scripts/maintenance/apply_ml_consensus_filter_batch.py --dry-run
"""
import sys
import os
import sqlite3
import argparse
import numpy as np
import pandas as pd
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

MODEL_NAME = 'conditional_rank_v4b_20260413_160607'

CONFIDENCE_ORDER = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1}
ORDER_TO_CONF    = {5: 'A', 4: 'B', 3: 'C', 2: 'D', 1: 'E'}


def load_model():
    from src.ml.conditional_rank_model import ConditionalRankModel
    model = ConditionalRankModel()
    model.load(MODEL_NAME)
    print(f"[OK] モデルロード完了: {MODEL_NAME}")
    print(f"     feature_names ({len(model.feature_names)}): {model.feature_names}")
    return model


def fetch_all_features(conn: sqlite3.Connection, year_filter: str = None) -> pd.DataFrame:
    """
    全 before 予測レースの特徴量を一括取得。
    rank_prediction=1 行から rule_confidence / rule_pit_number も取得する。
    """
    year_cond = ""
    if year_filter:
        year_cond = f"AND r.race_date LIKE '{year_filter}%'"

    query = f"""
    SELECT
        e.race_id,
        e.pit_number,
        e.win_rate,
        e.second_rate,
        e.third_rate,
        e.local_win_rate,
        e.local_second_rate,
        e.motor_second_rate,
        e.boat_second_rate,
        e.avg_st,
        rd.exhibition_time,
        rd.st_time        AS exhibition_st,
        rd.exhibition_course,
        rd.tilt_angle,
        rc.wind_speed,
        rc.wave_height,
        rc.temperature,
        rc.water_temperature,
        -- ルールベース予測 (1着) の confidence と pit_number
        rp1.confidence    AS rule_confidence,
        rp1.pit_number    AS rule_first_pit
    FROM entries e
    JOIN races r ON e.race_id = r.id
    -- before予測の1着レコードが存在するレースのみ
    JOIN race_predictions rp1
        ON e.race_id = rp1.race_id
        AND rp1.prediction_type = 'before'
        AND rp1.rank_prediction = 1
    LEFT JOIN race_details rd
        ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
    LEFT JOIN race_conditions rc
        ON e.race_id = rc.race_id
    WHERE 1=1
    {year_cond}
    ORDER BY e.race_id, e.pit_number
    """
    print(f"[INFO] 特徴量クエリ実行中...")
    df = pd.read_sql_query(query, conn)
    print(f"[INFO] 取得行数: {len(df):,} (レース×艇)")
    return df


def apply_batch(df: pd.DataFrame, model, dry_run: bool = False):
    """
    バッチ推論 → 変更リスト [(race_id, new_confidence)] を返す
    """
    import warnings
    warnings.filterwarnings('ignore', category=RuntimeWarning)

    feature_names = model.feature_names
    clf = model.models['first']

    # 欠損をレース内中央値で補完（race_predictor.py の逐次版と同じロジック）
    # 注: groupby transform は警告が出るが suppress 済み
    for col in feature_names:
        if col not in df.columns:
            df[col] = 0.0
        elif df[col].isnull().any():
            # まずレース内中央値で補完
            df[col] = df.groupby('race_id')[col].transform(
                lambda x: x.fillna(x.median())
            )
            # それでも残る欠損（レース内全艇が欠損）はグローバル中央値で補完
            if df[col].isnull().any():
                med = df[col].median()
                df[col] = df[col].fillna(med if pd.notna(med) else 0.0)

    # 全ボートまとめて一括 predict_proba
    X_all = df[feature_names].values.astype(np.float32)
    probs = clf.predict_proba(X_all)[:, 1]   # shape: (N_boats,)

    # レースごとに集計
    df = df.copy()
    df['ml_prob'] = probs

    updates = []
    skipped_incomplete = 0

    for race_id, group in df.groupby('race_id', sort=False):
        if len(group) != 6:
            skipped_incomplete += 1
            continue

        rule_conf     = group['rule_confidence'].iloc[0]
        rule_first_pit = int(group['rule_first_pit'].iloc[0])

        best_idx = group['ml_prob'].values.argmax()
        ml_first_pit = int(group['pit_number'].values[best_idx])

        if ml_first_pit != rule_first_pit:
            cur_level = CONFIDENCE_ORDER.get(rule_conf, 3)
            new_level = max(1, cur_level - 1)
            new_conf  = ORDER_TO_CONF[new_level]
            if new_conf != rule_conf:
                updates.append((new_conf, race_id))

    print(f"[INFO] 完全6艇レース以外スキップ: {skipped_incomplete:,}")
    return updates


def apply_updates(conn: sqlite3.Connection, updates: list, dry_run: bool):
    if not updates:
        print("[INFO] 更新対象なし")
        return

    print(f"[INFO] confidence 更新対象: {len(updates):,} レース")

    if dry_run:
        # サンプル表示
        print("[DRY-RUN] 変更サンプル（先頭20件）:")
        for new_conf, race_id in updates[:20]:
            print(f"  race_id={race_id}  => confidence={new_conf}")
        return

    sql = """
        UPDATE race_predictions
        SET confidence = ?, generated_at = ?
        WHERE race_id = ?
          AND prediction_type = 'before'
          AND rank_prediction = 1
    """
    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rows = [(new_conf, generated_at, race_id) for new_conf, race_id in updates]

    cur = conn.cursor()
    cur.executemany(sql, rows)
    conn.commit()
    print(f"[OK] {cur.rowcount:,} 行更新完了")


def main():
    parser = argparse.ArgumentParser(description='MLコンセンサスフィルター バッチ適用')
    parser.add_argument('--year', type=str, default=None, help='対象年度 (例: 2025)')
    parser.add_argument('--dry-run', action='store_true', help='DBを変更せずに変更件数のみ表示')
    args = parser.parse_args()

    t0 = datetime.now()
    print("=" * 60)
    print("MLコンセンサスフィルター バッチ適用")
    print(f"モデル: {MODEL_NAME}")
    print(f"対象年度: {args.year or '全年度 2020-2025'}")
    print(f"DRY-RUN: {args.dry_run}")
    print("=" * 60)

    # モデルロード
    model = load_model()

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        # 特徴量一括取得
        df = fetch_all_features(conn, year_filter=args.year)

        if df.empty:
            print("[WARN] 対象レースなし")
            return

        n_races = df['race_id'].nunique()
        print(f"[INFO] 対象レース数: {n_races:,}")

        # バッチ推論
        print("[INFO] バッチ推論中...")
        updates = apply_batch(df, model, dry_run=args.dry_run)

        # 変更分布
        from collections import Counter
        dist = Counter([c for c, _ in updates])
        print(f"[INFO] 変更後confidence分布: {dict(sorted(dist.items()))}")

        # DB更新
        apply_updates(conn, updates, dry_run=args.dry_run)

    finally:
        conn.close()

    elapsed = (datetime.now() - t0).total_seconds()
    print(f"\n[OK] 完了 ({elapsed:.1f}秒)")


if __name__ == '__main__':
    main()
