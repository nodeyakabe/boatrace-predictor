"""
統合分析テーブル作成スクリプト
==============================

複合条件の法則性調査のための事前結合テーブルを作成する。
毎回の分析で多数のJOINを実行する代わりに、事前計算済みのテーブルを使用。

使用例:
    python scripts/analysis/create_analysis_table.py
    python scripts/analysis/create_analysis_table.py --rebuild  # 再構築
"""

import sqlite3
import argparse
from pathlib import Path
from datetime import datetime


def create_analysis_table(db_path: str, rebuild: bool = False):
    """統合分析テーブルを作成"""

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 既存テーブルの確認
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ml_analysis_features'")
    exists = cur.fetchone() is not None

    if exists and not rebuild:
        cur.execute("SELECT COUNT(*) FROM ml_analysis_features")
        count = cur.fetchone()[0]
        print(f"ml_analysis_features テーブルは既に存在します ({count:,}件)")
        print("再構築するには --rebuild オプションを使用してください")
        return

    if exists:
        print("既存テーブルを削除中...")
        cur.execute("DROP TABLE IF EXISTS ml_analysis_features")

    print("統合分析テーブルを作成中...")
    start_time = datetime.now()

    # 統合テーブル作成SQL
    create_sql = """
    CREATE TABLE ml_analysis_features AS
    SELECT
        -- 基本情報
        r.id as race_id,
        r.venue_code,
        substr(r.race_date, 1, 4) as year,
        r.race_date,
        r.race_number,
        r.race_grade,
        r.is_nighter,

        -- 予測情報（1着予測のみ）
        rp.confidence,
        rp.total_score as score_rank1,
        rp.pit_number as predicted_pit,
        rp.prediction_type,

        -- 2着予測のスコア（スコア差計算用）
        (SELECT rp2.total_score FROM race_predictions rp2
         WHERE rp2.race_id = r.id AND rp2.rank_prediction = 2
         AND rp2.prediction_type = rp.prediction_type
         LIMIT 1) as score_rank2,

        -- 1コースレーサー情報
        e1.racer_rank as course1_rank,
        e1.win_rate as course1_win_rate,
        e1.motor_second_rate as course1_motor,
        e1.avg_st as course1_avg_st,

        -- 予測艇のレーサー情報
        ep.racer_rank as predicted_rank,
        ep.win_rate as predicted_win_rate,
        ep.motor_second_rate as predicted_motor,

        -- 天候条件
        rc.weather,
        rc.wind_direction,
        rc.wind_speed,
        rc.wave_height,

        -- 3連単オッズ（予測買い目）
        (SELECT t.odds FROM trifecta_odds t
         WHERE t.race_id = r.id
         AND t.combination = (
             SELECT
                 CAST((SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 1 AND prediction_type = rp.prediction_type LIMIT 1) AS TEXT) || '-' ||
                 CAST((SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 2 AND prediction_type = rp.prediction_type LIMIT 1) AS TEXT) || '-' ||
                 CAST((SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 3 AND prediction_type = rp.prediction_type LIMIT 1) AS TEXT)
         )
         LIMIT 1) as predicted_odds,

        -- 結果情報
        res1.rank as actual_rank1,
        res2.rank as actual_rank2,
        res3.rank as actual_rank3,
        res1.kimarite,

        -- 的中判定
        CASE
            WHEN res1.rank = '1'
             AND res2.rank = '2'
             AND res3.rank = '3'
            THEN 1 ELSE 0
        END as is_trifecta_hit,

        -- 配当（的中時のみ）
        CASE
            WHEN res1.rank = '1' AND res2.rank = '2' AND res3.rank = '3'
            THEN p.amount
            ELSE 0
        END as trifecta_payout

    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id

    -- 1コースのエントリー情報
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1

    -- 予測1着のエントリー情報
    JOIN entries ep ON r.id = ep.race_id AND ep.pit_number = rp.pit_number

    -- 天候条件（LEFT JOIN: 欠損許容）
    LEFT JOIN race_conditions rc ON r.id = rc.race_id

    -- 予測結果（1-2-3着）
    LEFT JOIN (
        SELECT race_id, pit_number, rank_prediction, prediction_type
        FROM race_predictions WHERE rank_prediction IN (1, 2, 3)
    ) pred123 ON rp.race_id = pred123.race_id AND rp.prediction_type = pred123.prediction_type

    -- 結果（各着順）
    LEFT JOIN results res1 ON r.id = res1.race_id
        AND res1.pit_number = (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 1 AND prediction_type = rp.prediction_type LIMIT 1)
    LEFT JOIN results res2 ON r.id = res2.race_id
        AND res2.pit_number = (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 2 AND prediction_type = rp.prediction_type LIMIT 1)
    LEFT JOIN results res3 ON r.id = res3.race_id
        AND res3.pit_number = (SELECT pit_number FROM race_predictions WHERE race_id = r.id AND rank_prediction = 3 AND prediction_type = rp.prediction_type LIMIT 1)

    -- 3連単配当
    LEFT JOIN payouts p ON r.id = p.race_id AND p.bet_type = 'trifecta'

    WHERE rp.rank_prediction = 1  -- 1着予測のみ
    """

    cur.execute(create_sql)

    # レコード数確認
    cur.execute("SELECT COUNT(*) FROM ml_analysis_features")
    count = cur.fetchone()[0]

    print(f"レコード作成完了: {count:,}件")

    # インデックス作成
    print("インデックスを作成中...")
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_maf_venue ON ml_analysis_features(venue_code)",
        "CREATE INDEX IF NOT EXISTS idx_maf_year ON ml_analysis_features(year)",
        "CREATE INDEX IF NOT EXISTS idx_maf_conf ON ml_analysis_features(confidence)",
        "CREATE INDEX IF NOT EXISTS idx_maf_hit ON ml_analysis_features(is_trifecta_hit)",
        "CREATE INDEX IF NOT EXISTS idx_maf_type ON ml_analysis_features(prediction_type)",
        "CREATE INDEX IF NOT EXISTS idx_maf_c1rank ON ml_analysis_features(course1_rank)",
        "CREATE INDEX IF NOT EXISTS idx_maf_odds ON ml_analysis_features(predicted_odds)",
    ]

    for idx_sql in indices:
        cur.execute(idx_sql)

    conn.commit()

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"完了! 所要時間: {elapsed:.1f}秒")

    # 統計表示
    print("\n=== テーブル統計 ===")

    cur.execute("""
        SELECT year, prediction_type, COUNT(*), SUM(is_trifecta_hit)
        FROM ml_analysis_features
        GROUP BY year, prediction_type
        ORDER BY year, prediction_type
    """)

    print(f"{'年度':<6} {'タイプ':<10} {'レース数':>10} {'的中数':>8} {'的中率':>8}")
    print("-" * 50)
    for row in cur.fetchall():
        year, ptype, total, hits = row
        hits = hits or 0
        rate = (hits / total * 100) if total > 0 else 0
        print(f"{year:<6} {ptype:<10} {total:>10,} {hits:>8,} {rate:>7.2f}%")

    conn.close()


def add_derived_columns(db_path: str):
    """派生カラム（オッズ帯、スコア差帯など）を追加"""

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("\n派生カラムを追加中...")

    # オッズ帯カラム追加
    try:
        cur.execute("ALTER TABLE ml_analysis_features ADD COLUMN odds_band TEXT")
    except:
        pass  # 既に存在

    cur.execute("""
        UPDATE ml_analysis_features
        SET odds_band = CASE
            WHEN predicted_odds IS NULL THEN 'unknown'
            WHEN predicted_odds < 10 THEN '0-10'
            WHEN predicted_odds < 20 THEN '10-20'
            WHEN predicted_odds < 30 THEN '20-30'
            WHEN predicted_odds < 50 THEN '30-50'
            WHEN predicted_odds < 100 THEN '50-100'
            ELSE '100+'
        END
    """)

    # スコア差帯カラム追加
    try:
        cur.execute("ALTER TABLE ml_analysis_features ADD COLUMN score_diff REAL")
        cur.execute("ALTER TABLE ml_analysis_features ADD COLUMN score_diff_band TEXT")
    except:
        pass

    cur.execute("""
        UPDATE ml_analysis_features
        SET score_diff = score_rank1 - COALESCE(score_rank2, score_rank1)
    """)

    cur.execute("""
        UPDATE ml_analysis_features
        SET score_diff_band = CASE
            WHEN score_diff IS NULL THEN 'unknown'
            WHEN score_diff < 5 THEN '0-5'
            WHEN score_diff < 10 THEN '5-10'
            WHEN score_diff < 20 THEN '10-20'
            ELSE '20+'
        END
    """)

    # モーター帯カラム追加
    try:
        cur.execute("ALTER TABLE ml_analysis_features ADD COLUMN motor_band TEXT")
    except:
        pass

    cur.execute("""
        UPDATE ml_analysis_features
        SET motor_band = CASE
            WHEN course1_motor IS NULL THEN 'unknown'
            WHEN course1_motor < 30 THEN '30-'
            WHEN course1_motor < 40 THEN '30-40'
            ELSE '40+'
        END
    """)

    # 風速帯カラム追加
    try:
        cur.execute("ALTER TABLE ml_analysis_features ADD COLUMN wind_band TEXT")
    except:
        pass

    cur.execute("""
        UPDATE ml_analysis_features
        SET wind_band = CASE
            WHEN wind_speed IS NULL THEN 'unknown'
            WHEN wind_speed < 2 THEN '0-2'
            WHEN wind_speed < 4 THEN '2-4'
            ELSE '4+'
        END
    """)

    # 追加インデックス
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_maf_odds_band ON ml_analysis_features(odds_band)",
        "CREATE INDEX IF NOT EXISTS idx_maf_score_diff ON ml_analysis_features(score_diff_band)",
        "CREATE INDEX IF NOT EXISTS idx_maf_motor ON ml_analysis_features(motor_band)",
        "CREATE INDEX IF NOT EXISTS idx_maf_wind ON ml_analysis_features(wind_band)",
    ]

    for idx_sql in indices:
        cur.execute(idx_sql)

    conn.commit()
    conn.close()

    print("派生カラム追加完了!")


def main():
    parser = argparse.ArgumentParser(description='統合分析テーブル作成')
    parser.add_argument('--rebuild', action='store_true', help='既存テーブルを再構築')
    args = parser.parse_args()

    db_path = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

    create_analysis_table(str(db_path), rebuild=args.rebuild)
    add_derived_columns(str(db_path))


if __name__ == "__main__":
    main()
