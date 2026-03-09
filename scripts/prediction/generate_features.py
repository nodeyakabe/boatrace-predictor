#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
prediction_features テーブル生成スクリプト

目的:
    predict_race() が計算した raw スコアを prediction_features テーブルに保存する。
    fast_backtest.py が、このテーブルから高速にスコア・信頼度を再計算できる。

使用方法:
    # 特定年度
    python scripts/prediction/generate_features.py --year 2024

    # 全年度（2020-2025）
    python scripts/prediction/generate_features.py --start 2020-01-01 --end 2025-12-31

    # 強制再生成（既存上書き）
    python scripts/prediction/generate_features.py --year 2024 --force

フロー:
    BatchDataLoader で日次キャッシュ → predict_races_batch() → prediction_features に UPSERT

テーブル: prediction_features
    - raw スコア（racer_score_raw, motor_score_raw, extended_score_raw 等）
    - ExtendedScorer の 16 サブコンポーネント
    - メタデータ（venue_code, race_grade, racer_rank 等）
    - 最終スコア（total_score_final: 全補正適用後の確定値）
"""
import sys
import os
import io
import sqlite3
import warnings
import argparse
from datetime import datetime
from pathlib import Path

warnings.filterwarnings('ignore')

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.prediction.predictor_helpers import create_standard_predictor
from config.settings import DATABASE_PATH

# テーブル DDL
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS prediction_features (
    race_id INTEGER NOT NULL,
    pit_number INTEGER NOT NULL,

    -- メタデータ（adjusted_weights 再計算・フィルタリングに必要）
    racer_number INTEGER,
    racer_name TEXT,
    racer_rank TEXT,
    motor_number INTEGER,
    venue_code TEXT,
    race_grade TEXT,
    race_date TEXT,
    data_quality REAL,

    -- 直前情報（パターンボーナス再計算用）
    exhibition_time REAL,
    st_time REAL,

    -- 主要スコアコンポーネント（raw: 重み変更時の再計算に必要）
    course_score_raw REAL DEFAULT 0,       -- calculate_course_rank_score 戻り値（course_weight適用済み）
    racer_score_raw REAL DEFAULT 0,        -- 40点満点での生スコア
    motor_score_raw REAL DEFAULT 0,        -- 20点満点での生スコア
    kimarite_score_raw REAL DEFAULT 0,     -- kimarite_weight点満点
    grade_score_raw REAL DEFAULT 0,        -- grade_weight点満点
    extended_score_raw REAL DEFAULT 0,     -- total_extended_score（-10〜75）
    compound_buff REAL DEFAULT 0,

    -- ExtendedScorer サブコンポーネント（個別重み変更時の再計算に必要）
    ext_class_score REAL DEFAULT 0,
    ext_fl_penalty REAL DEFAULT 0,
    ext_capsizing_penalty REAL DEFAULT 0,
    ext_session_score REAL DEFAULT 0,
    ext_prev_race_score REAL DEFAULT 0,
    ext_course_entry_score REAL DEFAULT 0,
    ext_matchup_score REAL DEFAULT 0,
    ext_motor_score REAL DEFAULT 0,
    ext_start_timing_score REAL DEFAULT 0,
    ext_exhibition_score REAL DEFAULT 0,
    ext_tilt_score REAL DEFAULT 0,
    ext_chikusen_time_score REAL DEFAULT 0,
    ext_recent_form_score REAL DEFAULT 0,
    ext_venue_affinity_score REAL DEFAULT 0,
    ext_place_rate_score REAL DEFAULT 0,
    ext_motor_second_rate_score REAL DEFAULT 0,

    -- 最終スコア（全補正・パターンボーナス適用後の確定値）
    -- NOTE: confidence 閾値変更のみの場合はこの値をそのまま使用（再計算不要）
    total_score_final REAL DEFAULT 0,

    -- 統計要約（_calculate_confidence の再現に必要）
    racer_overall_races INTEGER DEFAULT 0,
    motor_total_races INTEGER DEFAULT 0,

    -- 管理
    feature_version TEXT DEFAULT '1.0',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),

    PRIMARY KEY (race_id, pit_number)
);
CREATE INDEX IF NOT EXISTS idx_pf_race_date ON prediction_features(race_date);
CREATE INDEX IF NOT EXISTS idx_pf_venue_code ON prediction_features(venue_code);
"""

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
    feature_version, updated_at
)
VALUES (
    ?,?,  ?,?,?,?,  ?,?,?,?,  ?,?,
    ?,?,?,  ?,?,?,?,
    ?,?,?,  ?,?,?,  ?,?,?,  ?,?,?,  ?,?,  ?,?,
    ?,  ?,?,  ?,?
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
    feature_version=excluded.feature_version,
    updated_at=excluded.updated_at;
"""


def ensure_table():
    """prediction_features テーブルを作成（なければ）"""
    conn = sqlite3.connect(DATABASE_PATH)
    for stmt in CREATE_TABLE_SQL.strip().split(';'):
        s = stmt.strip()
        if s:
            conn.execute(s)
    conn.commit()
    conn.close()


def get_s(d, key, default=0.0):
    """dict から score キーを安全に取得"""
    if d is None:
        return default
    if isinstance(d, dict):
        return d.get(key, default)
    return default


def predictions_to_feature_rows(race_id, predictions, race_meta):
    """
    predict_race() の結果と race_meta から prediction_features 行を生成

    Args:
        race_id: int
        predictions: predict_race() の戻り値
        race_meta: {pit_number: {venue_code, race_grade, race_date, racer_rank,
                                  exhibition_time, st_time}}
    Returns:
        list of tuples（UPSERT_SQL の ? に対応）
    """
    rows = []
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for pred in predictions:
        pit = pred['pit_number']
        meta = race_meta.get(pit, {})

        ed = pred.get('extended_detail') or {}

        def gs(key):
            return get_s(ed.get(key), 'score')

        def gp(key):
            """penalty キー用"""
            return get_s(ed.get(key), 'penalty')

        rows.append((
            race_id, pit,
            pred.get('racer_number'),
            pred.get('racer_name'),
            meta.get('racer_rank', 'B2'),
            pred.get('motor_number'),
            meta.get('venue_code', ''),
            meta.get('race_grade', '一般'),
            meta.get('race_date', ''),
            None,  # data_quality（後述: racer_overall_races から推定）
            meta.get('exhibition_time'),
            meta.get('st_time'),
            # raw スコア
            pred.get('_course_score_raw', pred.get('course_score', 0.0)),
            pred.get('_racer_score_raw', 0.0),
            pred.get('_motor_score_raw', 0.0),
            pred.get('_kimarite_score_raw', pred.get('kimarite_score', 0.0)),
            pred.get('_grade_score_raw', pred.get('grade_score', 0.0)),
            pred.get('_extended_score_raw', 0.0),
            pred.get('compound_buff', 0.0),
            # ExtendedScorer サブコンポーネント
            gs('class'),
            gp('fl_penalty'),
            gp('capsizing_penalty'),
            gs('session'),
            gs('prev_race'),
            gs('course_entry'),
            get_s(ed.get('matchup'), 'relative_score') if ed.get('matchup') else 0.0,
            gs('motor_extended') or gs('motor'),  # 'motor_extended' or 'motor'
            gs('start_timing'),
            gs('exhibition'),
            gs('tilt'),
            gs('chikusen_time'),
            gs('recent_form'),
            gs('venue_affinity'),
            gs('place_rate'),
            gs('motor_second_rate'),
            # 最終スコア
            pred.get('total_score', 0.0),
            pred.get('_racer_overall_races', 0),
            pred.get('_motor_total_races', 0),
            '1.0',
            now,
        ))
    return rows


def get_race_meta(conn, race_ids):
    """
    race_ids に対して必要なメタ情報を一括取得

    Returns:
        {race_id: {pit_number: {venue_code, race_grade, race_date, racer_rank,
                                 exhibition_time, st_time}}}
    """
    if not race_ids:
        return {}

    placeholders = ','.join('?' * len(race_ids))
    cursor = conn.cursor()

    cursor.execute(f"""
        SELECT r.id AS race_id, r.venue_code, r.race_grade, r.race_date,
               e.pit_number, e.racer_rank, e.motor_number,
               rd.exhibition_time, rd.st_time
        FROM races r
        JOIN entries e ON r.id = e.race_id
        LEFT JOIN race_details rd ON r.id = rd.race_id AND e.pit_number = rd.pit_number
        WHERE r.id IN ({placeholders})
    """, race_ids)

    result = {}
    for row in cursor.fetchall():
        rid = row[0]
        pit = row[4]
        if rid not in result:
            result[rid] = {}
        result[rid][pit] = {
            'venue_code': row[1] or '',
            'race_grade': row[2] or '一般',
            'race_date': row[3] or '',
            'racer_rank': row[5] or 'B2',
            'motor_number': row[6],
            'exhibition_time': row[7],
            'st_time': row[8],
        }
    cursor.close()
    return result


def get_target_races(year=None, start_date=None, end_date=None, force=False):
    """
    特徴量生成対象のレースを取得

    Args:
        year: 年度（start_date/end_date が指定された場合は無視）
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）
        force: True の場合、既存特徴量も再生成

    Returns:
        [(race_id, race_date, venue_code, race_number), ...]
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    sd = start_date or f'{year}-01-01'
    ed = end_date   or f'{year}-12-31'

    # 既存特徴量があるレース
    if force:
        existing_ids = set()
    else:
        cursor.execute("""
            SELECT DISTINCT race_id FROM prediction_features
            WHERE race_id IN (SELECT id FROM races WHERE race_date >= ? AND race_date <= ?)
        """, (sd, ed))
        existing_ids = set(row[0] for row in cursor.fetchall())

    # 対象レース（entries が存在するもの）
    cursor.execute("""
        SELECT id, race_date, venue_code, race_number
        FROM races
        WHERE race_date >= ? AND race_date <= ?
        AND EXISTS (SELECT 1 FROM entries e WHERE e.race_id = races.id)
        ORDER BY race_date, venue_code, race_number
    """, (sd, ed))
    all_races = cursor.fetchall()
    conn.close()

    remaining = [(r[0], r[1], r[2], r[3]) for r in all_races if r[0] not in existing_ids]
    return remaining, len(existing_ids)


def _group_races_by_date(races):
    from collections import OrderedDict
    grouped = OrderedDict()
    for race_id, race_date, venue_code, race_number in races:
        grouped.setdefault(race_date, []).append((race_id, race_date, venue_code, race_number))
    return grouped


def generate_features_for_races(remaining_races, predictor):
    """
    対象レースの特徴量を生成して prediction_features テーブルに保存

    Returns:
        {'success': int, 'failed': int, 'elapsed': float}
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    success_count = 0
    failed_count = 0
    start_time = datetime.now()
    processed_races = 0

    use_batch = hasattr(predictor, 'predict_races_batch')
    grouped = _group_races_by_date(remaining_races)

    for date_idx, (race_date, day_races) in enumerate(grouped.items()):
        if processed_races > 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = success_count / elapsed if elapsed > 0 else 0
            remaining_count = len(remaining_races) - processed_races
            remaining_time = remaining_count / rate / 60 if rate > 0 else 0
            print(f" [{success_count}/{processed_races}] {rate:.1f}/s, {remaining_time:.0f}min left")

        print(f"[{race_date}] ({len(day_races)}R)", end='', flush=True)

        # 日次キャッシュをロード
        if predictor.batch_loader:
            predictor.batch_loader.load_daily_data(race_date)

        day_race_ids = [r[0] for r in day_races]

        # メタ情報を一括取得
        race_meta = get_race_meta(conn, day_race_ids)

        if use_batch:
            try:
                batch_results = predictor.predict_races_batch(day_race_ids, use_beforeinfo=True)
            except Exception as e:
                print(f"\n  [!] バッチ推論エラー: {type(e).__name__}: {str(e)[:100]}", flush=True)
                batch_results = {}

            rows_to_upsert = []
            for race_id, _, _, _ in day_races:
                processed_races += 1
                predictions = batch_results.get(race_id, [])
                if predictions:
                    meta = race_meta.get(race_id, {})
                    rows = predictions_to_feature_rows(race_id, predictions, meta)
                    rows_to_upsert.extend(rows)
                    success_count += 1
                    if success_count % 100 == 0:
                        print('.', end='', flush=True)
                else:
                    failed_count += 1
        else:
            rows_to_upsert = []
            consecutive_errors = 0
            for race_id, _, _, _ in day_races:
                processed_races += 1
                try:
                    predictions = predictor.predict_race(race_id, use_beforeinfo=True)
                    if predictions:
                        meta = race_meta.get(race_id, {})
                        rows = predictions_to_feature_rows(race_id, predictions, meta)
                        rows_to_upsert.extend(rows)
                        success_count += 1
                        consecutive_errors = 0
                        if success_count % 100 == 0:
                            print('.', end='', flush=True)
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    consecutive_errors += 1
                    if consecutive_errors == 1 or consecutive_errors % 100 == 0:
                        print(f"\n  [!] エラー(race_id={race_id}): {type(e).__name__}: {str(e)[:100]}", flush=True)
                    if consecutive_errors == 50:
                        if predictor.batch_loader:
                            try:
                                predictor.batch_loader.clear_cache()
                                predictor.batch_loader.load_daily_data(race_date)
                            except Exception:
                                pass

        # 日単位でまとめてUPSERT
        if rows_to_upsert:
            try:
                conn.executemany(UPSERT_SQL, rows_to_upsert)
                conn.commit()
            except Exception as e:
                print(f"\n  [!] DB保存エラー: {e}", flush=True)
                conn.rollback()

    conn.close()
    elapsed = (datetime.now() - start_time).total_seconds()
    print()
    return {'success': success_count, 'failed': failed_count, 'elapsed': elapsed}


def main():
    parser = argparse.ArgumentParser(description='prediction_features テーブル生成')
    parser.add_argument('--year', type=int, help='対象年度（例: 2024）')
    parser.add_argument('--start', type=str, help='開始日（YYYY-MM-DD）')
    parser.add_argument('--end',   type=str, help='終了日（YYYY-MM-DD）')
    parser.add_argument('--force', action='store_true', help='既存特徴量も再生成（上書き）')
    args = parser.parse_args()

    if not args.year and not args.start:
        parser.error('--year または --start/--end を指定してください')

    if args.start or args.end:
        start_date = args.start
        end_date   = args.end or '2099-12-31'
        year_label = f"{start_date}〜{end_date}"
    else:
        start_date = None
        end_date   = None
        year_label = str(args.year)

    print(f"=== prediction_features 生成 [{year_label}] {'(--force)' if args.force else ''} ===")
    print(f"DB: {DATABASE_PATH}")

    # テーブル確保
    ensure_table()
    print("テーブル確認OK")

    # 対象レース取得
    remaining, already_done = get_target_races(
        year=args.year, start_date=start_date, end_date=end_date, force=args.force
    )
    print(f"対象: {len(remaining)}レース（スキップ済み: {already_done}件）")

    if not remaining:
        print("生成対象なし。終了します。")
        return

    # Predictor 作成
    print("Predictor 初期化中...")
    predictor = create_standard_predictor()
    print("Predictor 準備完了")

    # 生成実行
    result = generate_features_for_races(remaining, predictor)

    elapsed_min = result['elapsed'] / 60
    print(f"\n=== 完了 ===")
    print(f"成功: {result['success']}件 / 失敗: {result['failed']}件")
    print(f"所要時間: {elapsed_min:.1f}分")

    if result['success'] > 0:
        print(f"\n次のステップ: fast_backtest.py でパラメータ変更の効果を高速確認できます")
        print(f"  python scripts/backtest/fast_backtest.py --full")
        print(f"  python scripts/backtest/fast_backtest.py --full --conf-a-gap 12")


if __name__ == '__main__':
    main()
