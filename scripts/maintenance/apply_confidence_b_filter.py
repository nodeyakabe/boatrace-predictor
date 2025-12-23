# -*- coding: utf-8 -*-
"""
信頼度Bフィルター適用スクリプト

予測生成後に実行し、信頼度Bの予測に対してフィルター判定を行い、
結果をconfidence_b_filter_resultsテーブルに保存する
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime
import argparse

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analysis.confidence_filter import ConfidenceBFilter
from config.settings import DATABASE_PATH


def apply_filter_to_date(target_date: str, force: bool = False):
    """
    指定日の信頼度B予測にフィルターを適用

    Args:
        target_date: 対象日（YYYY-MM-DD）
        force: 既存のフィルター結果を上書きするか
    """
    print("=" * 80)
    print("信頼度Bフィルター適用")
    print("=" * 80)
    print(f"対象日: {target_date}")
    print(f"上書きモード: {'有効' if force else '無効'}")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 信頼度Bの予測を抽出
    query = """
        SELECT DISTINCT
            r.id as race_id,
            r.venue_code,
            r.race_date,
            r.race_number,
            rp.total_score as confidence_score
        FROM races r
        INNER JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date = ?
            AND rp.prediction_type = 'advance'
            AND rp.rank_prediction = 1
            AND rp.confidence = 'B'
        ORDER BY r.venue_code, r.race_number
    """

    cursor.execute(query, (target_date,))
    races = cursor.fetchall()

    if not races:
        print(f"\n[!] {target_date} に信頼度Bの予測が見つかりませんでした")
        conn.close()
        return

    print(f"\n信頼度Bレース: {len(races)}件")

    # フィルター初期化
    b_filter = ConfidenceBFilter(
        exclude_low_venues=True,
        venue_threshold=5.0,
        seasonal_adjustment=True,
        low_season_score_boost=2.0
    )

    # 既存のフィルター結果をチェック
    if not force:
        cursor.execute("""
            SELECT COUNT(*) FROM confidence_b_filter_results
            WHERE race_id IN (
                SELECT DISTINCT r.id
                FROM races r
                INNER JOIN race_predictions rp ON r.id = rp.race_id
                WHERE r.race_date = ?
                    AND rp.prediction_type = 'advance'
                    AND rp.rank_prediction = 1
                    AND rp.confidence = 'B'
            )
        """, (target_date,))

        existing_count = cursor.fetchone()[0]
        if existing_count > 0:
            print(f"\n[!] 既に{existing_count}件のフィルター結果が存在します")
            print("[!] 上書きする場合は --force オプションを使用してください")
            conn.close()
            return

    # フィルター適用
    print("\nフィルター適用中...")

    accepted_count = 0
    rejected_count = 0

    # 既存のフィルター結果を削除（force=Trueの場合）
    if force:
        cursor.execute("""
            DELETE FROM confidence_b_filter_results
            WHERE race_id IN (
                SELECT DISTINCT r.id
                FROM races r
                INNER JOIN race_predictions rp ON r.id = rp.race_id
                WHERE r.race_date = ?
                    AND rp.prediction_type = 'advance'
                    AND rp.rank_prediction = 1
                    AND rp.confidence = 'B'
            )
        """, (target_date,))
        conn.commit()

    for race in races:
        race_id = race[0]
        venue_code = race[1]
        race_date = race[2]
        race_number = race[3]
        confidence_score = race[4]

        # フィルター判定
        filter_result = b_filter.should_accept_bet(
            venue_code=venue_code,
            race_date=race_date,
            confidence_score=confidence_score
        )

        # DB保存
        cursor.execute("""
            INSERT INTO confidence_b_filter_results (
                race_id, filter_accept, filter_reason, expected_hit_rate,
                venue_hit_rate, monthly_hit_rate, adjustment_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            race_id,
            1 if filter_result['accept'] else 0,
            filter_result['reason'],
            filter_result['expected_hit_rate'],
            filter_result.get('venue_hit_rate'),
            filter_result.get('monthly_hit_rate'),
            filter_result['adjustment']
        ))

        if filter_result['accept']:
            accepted_count += 1
        else:
            rejected_count += 1

    conn.commit()

    print("\n" + "=" * 80)
    print("フィルター適用完了")
    print("=" * 80)
    print(f"総レース数: {len(races)}")
    print(f"受け入れ: {accepted_count} ({accepted_count/len(races)*100:.1f}%)")
    print(f"除外: {rejected_count} ({rejected_count/len(races)*100:.1f}%)")

    # 除外理由の集計
    print("\n除外理由の内訳:")
    cursor.execute("""
        SELECT adjustment_type, COUNT(*) as cnt
        FROM confidence_b_filter_results
        WHERE filter_accept = 0
            AND race_id IN (
                SELECT DISTINCT r.id
                FROM races r
                WHERE r.race_date = ?
            )
        GROUP BY adjustment_type
        ORDER BY cnt DESC
    """, (target_date,))

    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}件")

    print("=" * 80)

    conn.close()


def main():
    parser = argparse.ArgumentParser(description='信頼度Bフィルター適用')
    parser.add_argument('--date', type=str, help='対象日（YYYY-MM-DD）。未指定の場合は今日')
    parser.add_argument('--force', action='store_true', help='既存のフィルター結果を上書き')

    args = parser.parse_args()

    # 対象日の決定
    if args.date:
        target_date = args.date
    else:
        target_date = datetime.now().strftime('%Y-%m-%d')

    try:
        apply_filter_to_date(target_date, force=args.force)
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
