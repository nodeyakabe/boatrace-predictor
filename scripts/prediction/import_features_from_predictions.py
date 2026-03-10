#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
prediction_features テーブルを race_predictions から高速インポート

目的:
    generate_features.py（predict_race() 再実行）の代わりに、
    既存の race_predictions テーブルから prediction_features を即座に作成する。
    confidence_only モードの fast_backtest.py が使えるようになる。

所要時間: 数分（generate_features.py の ~25時間/年 に対して）

制限事項:
    - total_score_final は完全に正確（race_predictions.total_score を使用）
    - racer_score_raw 等の raw スコアは近似値（race_predictions の対応フィールドを流用）
    - ext_* サブコンポーネント（ExtendedScorer）は 0（race_predictions に保存されていない）
    - full モードでの scoring_weights 再計算は近似（confidence_only は完全正確）

推奨用途:
    fast_backtest.py --conf-a-gap 12 のような confidence 閾値変更テスト

使用方法:
    # 全期間
    python scripts/prediction/import_features_from_predictions.py --full

    # 特定年度
    python scripts/prediction/import_features_from_predictions.py --year 2024

    # 強制上書き
    python scripts/prediction/import_features_from_predictions.py --full --force
"""
import sys
import os
import io
import sqlite3
import warnings
import argparse
from datetime import datetime

warnings.filterwarnings('ignore')

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

UPSERT_SQL = """
INSERT INTO prediction_features (
    race_id, pit_number,
    racer_number, racer_name, racer_rank, motor_number,
    venue_code, race_grade, race_date, data_quality,
    exhibition_time, st_time,
    course_score_raw, racer_score_raw, motor_score_raw,
    kimarite_score_raw, grade_score_raw, extended_score_raw, compound_buff,
    ext_class_score, ext_fl_penalty, ext_capsizing_penalty,
    ext_session_score, ext_prev_race_score, ext_course_entry_score,
    ext_matchup_score, ext_motor_score, ext_start_timing_score,
    ext_exhibition_score, ext_tilt_score, ext_chikusen_time_score,
    ext_recent_form_score, ext_venue_affinity_score,
    ext_place_rate_score, ext_motor_second_rate_score,
    total_score_final,
    racer_overall_races, motor_total_races,
    original_confidence, original_rank_prediction,
    feature_version, updated_at
) VALUES (
    ?,?,  ?,?,?,?,  ?,?,?,?,  ?,?,
    ?,?,?,  ?,?,?,?,
    ?,?,?,  ?,?,?,  ?,?,?,  ?,?,?,  ?,?,  ?,?,
    ?,  ?,?,  ?,?,  ?,?
)
ON CONFLICT(race_id, pit_number) DO UPDATE SET
    racer_number=excluded.racer_number, racer_name=excluded.racer_name,
    racer_rank=excluded.racer_rank, motor_number=excluded.motor_number,
    venue_code=excluded.venue_code, race_grade=excluded.race_grade,
    race_date=excluded.race_date, data_quality=excluded.data_quality,
    exhibition_time=excluded.exhibition_time, st_time=excluded.st_time,
    course_score_raw=excluded.course_score_raw, racer_score_raw=excluded.racer_score_raw,
    motor_score_raw=excluded.motor_score_raw, kimarite_score_raw=excluded.kimarite_score_raw,
    grade_score_raw=excluded.grade_score_raw, extended_score_raw=excluded.extended_score_raw,
    compound_buff=excluded.compound_buff,
    ext_class_score=excluded.ext_class_score, ext_fl_penalty=excluded.ext_fl_penalty,
    ext_capsizing_penalty=excluded.ext_capsizing_penalty,
    ext_session_score=excluded.ext_session_score, ext_prev_race_score=excluded.ext_prev_race_score,
    ext_course_entry_score=excluded.ext_course_entry_score,
    ext_matchup_score=excluded.ext_matchup_score, ext_motor_score=excluded.ext_motor_score,
    ext_start_timing_score=excluded.ext_start_timing_score,
    ext_exhibition_score=excluded.ext_exhibition_score, ext_tilt_score=excluded.ext_tilt_score,
    ext_chikusen_time_score=excluded.ext_chikusen_time_score,
    ext_recent_form_score=excluded.ext_recent_form_score,
    ext_venue_affinity_score=excluded.ext_venue_affinity_score,
    ext_place_rate_score=excluded.ext_place_rate_score,
    ext_motor_second_rate_score=excluded.ext_motor_second_rate_score,
    total_score_final=excluded.total_score_final,
    racer_overall_races=excluded.racer_overall_races,
    motor_total_races=excluded.motor_total_races,
    original_confidence=excluded.original_confidence,
    original_rank_prediction=excluded.original_rank_prediction,
    feature_version=excluded.feature_version,
    updated_at=excluded.updated_at
"""


def import_features(start_date: str, end_date: str, force: bool = False):
    """race_predictions → prediction_features インポート"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # スキップ対象の確認
    if not force:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(DISTINCT race_id) FROM prediction_features
            WHERE race_date >= ? AND race_date <= ?
        """, (start_date, end_date))
        existing = cursor.fetchone()[0]
        if existing > 0:
            print(f"  既に {existing} レース分のデータが存在します（--force で上書き可）")
            conn.close()
            return 0

    # race_predictions（before）+ entries + races + race_details を結合して取得
    print(f"  データ取得中（{start_date} 〜 {end_date}）...")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            rp.race_id,
            rp.pit_number,
            CAST(rp.racer_number AS INTEGER) AS racer_number,
            rp.racer_name,
            COALESCE(e.racer_rank, 'B2') AS racer_rank,
            COALESCE(e.motor_number, 0) AS motor_number,
            COALESCE(r.venue_code, '') AS venue_code,
            COALESCE(r.race_grade, '一般') AS race_grade,
            r.race_date,
            rd.exhibition_time,
            rd.st_time,
            COALESCE(rp.course_score, 0.0) AS course_score_raw,
            COALESCE(rp.racer_score, 0.0) AS racer_score_raw,
            COALESCE(rp.motor_score, 0.0) AS motor_score_raw,
            COALESCE(rp.kimarite_score, 0.0) AS kimarite_score_raw,
            COALESCE(rp.grade_score, 0.0) AS grade_score_raw,
            rp.total_score AS total_score_final,
            CASE WHEN rp.rank_prediction = 1 THEN rp.confidence ELSE NULL END AS original_confidence,
            rp.rank_prediction AS original_rank_prediction
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
        LEFT JOIN race_details rd ON rp.race_id = rd.race_id AND rp.pit_number = rd.pit_number
        WHERE rp.prediction_type = 'before'
          AND r.race_date >= ?
          AND r.race_date <= ?
        ORDER BY r.race_date, r.venue_code, r.race_number, rp.pit_number
    """, (start_date, end_date))

    rows_raw = cursor.fetchall()
    print(f"  {len(rows_raw)} 行取得完了")

    if not rows_raw:
        print("  データなし。race_predictions に before 型が存在するか確認してください。")
        conn.close()
        return 0

    # UPSERT 用の行を構築（ext_* は 0、compound_buff は 0）
    rows = []
    for row in rows_raw:
        (race_id, pit_number, racer_number, racer_name, racer_rank, motor_number,
         venue_code, race_grade, race_date,
         exhibition_time, st_time,
         course_score_raw, racer_score_raw, motor_score_raw,
         kimarite_score_raw, grade_score_raw, total_score_final,
         original_confidence, original_rank_prediction) = row

        rows.append((
            race_id, pit_number,
            racer_number, racer_name, racer_rank, motor_number,
            venue_code, race_grade, race_date, None,  # data_quality
            exhibition_time, st_time,
            course_score_raw, racer_score_raw, motor_score_raw,
            kimarite_score_raw, grade_score_raw,
            0.0,  # extended_score_raw（近似不可→0）
            0.0,  # compound_buff（近似不可→0）
            # ext_* サブコンポーネント 16個（race_predictions に保存なし→0）
            0.0, 0.0, 0.0,  # class, fl_penalty, capsizing_penalty
            0.0, 0.0, 0.0,  # session, prev_race, course_entry
            0.0, 0.0, 0.0,  # matchup, motor, start_timing
            0.0, 0.0, 0.0,  # exhibition, tilt, chikusen_time
            0.0, 0.0,        # recent_form, venue_affinity
            0.0, 0.0,        # place_rate, motor_second_rate
            total_score_final,
            0, 0,            # racer_overall_races, motor_total_races
            original_confidence,        # 元の信頼度（rank1のみ、他はNULL）
            original_rank_prediction,   # 元の予測順位（全pit）
            '1.0-fast',      # feature_version（生成方法を明記）
            now,
        ))

    # バッチ UPSERT（10,000件ずつ）
    batch_size = 10000
    total_inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        conn.executemany(UPSERT_SQL, batch)
        conn.commit()
        total_inserted += len(batch)
        print(f"  ... {total_inserted}/{len(rows)} 件完了", flush=True)

    conn.close()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(
        description='race_predictions から prediction_features を高速インポート'
    )
    parser.add_argument('--full', action='store_true', help='全期間（2020-2025）')
    parser.add_argument('--year', type=int, help='対象年度（例: 2024）')
    parser.add_argument('--start', type=str, help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end',   type=str, help='終了日（YYYY-MM-DD）')
    parser.add_argument('--force', action='store_true', help='既存データも上書き')
    args = parser.parse_args()

    if args.full:
        start_date = '2020-01-01'
        end_date   = '2025-12-31'
    elif args.year:
        start_date = f'{args.year}-01-01'
        end_date   = f'{args.year}-12-31'
    elif args.start:
        start_date = args.start
        end_date   = args.end or '2099-12-31'
    else:
        parser.error('--full, --year, または --start を指定してください')

    print(f"=== prediction_features 高速インポート ===")
    print(f"期間: {start_date} 〜 {end_date}")
    print(f"ソース: race_predictions (prediction_type='before')")
    print(f"注意: confidence_only モード最適化（ext_* は 0）")

    t0 = datetime.now()
    total = import_features(start_date, end_date, force=args.force)
    elapsed = (datetime.now() - t0).total_seconds()

    print(f"\n=== 完了 ===")
    print(f"インポート件数: {total:,} 行")
    print(f"所要時間: {elapsed:.1f}秒")

    if total > 0:
        print(f"\n次のステップ:")
        print(f"  # confidence 閾値変更テスト（confidence_only モード）")
        print(f"  python scripts/backtest/fast_backtest.py --full")
        print(f"  python scripts/backtest/fast_backtest.py --full --conf-a-gap 12")
        print(f"")
        print(f"  ※ --motor-weight 等の重みテスト（full モード）には")
        print(f"    generate_features.py での完全再生成が必要")


if __name__ == '__main__':
    main()
