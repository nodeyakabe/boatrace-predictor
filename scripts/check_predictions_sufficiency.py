"""
予想データ（race_predictions）充足状況確認スクリプト

2024年・2025年の予想データの充足状況を調査
"""
import os
import sys
import sqlite3
from datetime import datetime

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def check_predictions_sufficiency():
    """予想データ充足状況を確認"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 100)
    print("予想データ（race_predictions）充足状況確認")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    # 2024年と2025年のデータを確認
    years = [2024, 2025]

    for year in years:
        start_date = f'{year}-01-01'
        end_date = f'{year}-12-31'

        print(f'\n■ {year}年')
        print('-' * 100)

        # 対象レース数
        cursor.execute("""
            SELECT COUNT(*) as total_races
            FROM races
            WHERE race_date >= ? AND race_date <= ?
        """, (start_date, end_date))
        total_races = cursor.fetchone()[0]

        # 予想データあるレース数（advance）
        cursor.execute("""
            SELECT COUNT(DISTINCT rp.race_id) as races_with_predictions
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rp.prediction_type = 'advance'
        """, (start_date, end_date))
        races_with_advance = cursor.fetchone()[0]

        # 予想データあるレース数（before）
        cursor.execute("""
            SELECT COUNT(DISTINCT rp.race_id) as races_with_predictions
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rp.prediction_type = 'before'
        """, (start_date, end_date))
        races_with_before = cursor.fetchone()[0]

        # 総予想データ件数（advance）
        cursor.execute("""
            SELECT COUNT(*) as total_predictions
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rp.prediction_type = 'advance'
        """, (start_date, end_date))
        total_advance = cursor.fetchone()[0]

        # 総予想データ件数（before）
        cursor.execute("""
            SELECT COUNT(*) as total_predictions
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rp.prediction_type = 'before'
        """, (start_date, end_date))
        total_before = cursor.fetchone()[0]

        # 信頼度別の件数（advance）
        cursor.execute("""
            SELECT confidence, COUNT(*) as count
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rp.prediction_type = 'advance'
            GROUP BY confidence
            ORDER BY confidence
        """, (start_date, end_date))
        confidence_advance = cursor.fetchall()

        # 信頼度別の件数（before）
        cursor.execute("""
            SELECT confidence, COUNT(*) as count
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rp.prediction_type = 'before'
            GROUP BY confidence
            ORDER BY confidence
        """, (start_date, end_date))
        confidence_before = cursor.fetchall()

        # 結果表示
        print(f'  総レース数: {total_races:,}レース')
        print(f'')
        print(f'  [事前予想（advance）]')
        advance_coverage = (races_with_advance / total_races * 100) if total_races > 0 else 0
        print(f'    予想あるレース: {races_with_advance:,}レース / {total_races:,}レース ({advance_coverage:.1f}%)')
        print(f'    総予想件数: {total_advance:,}件（期待値: {races_with_advance * 6:,}件）')

        if confidence_advance:
            print(f'    信頼度別:')
            for conf, count in confidence_advance:
                print(f'      {conf or "なし"}: {count:,}件')

        print(f'')
        print(f'  [直前予想（before）]')
        before_coverage = (races_with_before / total_races * 100) if total_races > 0 else 0
        print(f'    予想あるレース: {races_with_before:,}レース / {total_races:,}レース ({before_coverage:.1f}%)')
        print(f'    総予想件数: {total_before:,}件（期待値: {races_with_before * 6:,}件）')

        if confidence_before:
            print(f'    信頼度別:')
            for conf, count in confidence_before:
                print(f'      {conf or "なし"}: {count:,}件')

    # 月別の予想データあるレース数（2025年のみ）
    print(f'\n■ 2025年の月別予想データ充足状況')
    print('-' * 100)

    cursor.execute("""
        SELECT
            strftime('%m', r.race_date) as month,
            COUNT(DISTINCT r.id) as total_races,
            COUNT(DISTINCT CASE WHEN rp.prediction_type = 'advance' THEN rp.race_id END) as with_advance,
            COUNT(DISTINCT CASE WHEN rp.prediction_type = 'before' THEN rp.race_id END) as with_before
        FROM races r
        LEFT JOIN race_predictions rp ON r.id = rp.race_id
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        GROUP BY month
        ORDER BY month
    """)
    monthly_data = cursor.fetchall()

    print(f'  月   総レース  事前予想  充足率  直前予想  充足率')
    print('-' * 100)
    for month, total, advance, before in monthly_data:
        advance_pct = (advance / total * 100) if total > 0 else 0
        before_pct = (before / total * 100) if total > 0 else 0
        print(f'  {month}月  {total:>6}    {advance:>6}   {advance_pct:>5.1f}%   {before:>6}   {before_pct:>5.1f}%')

    conn.close()
    print('\n' + '=' * 100)
    print('レポート終了')
    print('=' * 100 + '\n')


if __name__ == '__main__':
    check_predictions_sufficiency()
