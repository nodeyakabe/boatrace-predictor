"""
データ整合性チェックスクリプト

公式サイトから最新データを取得してDBと照合
- レース結果
- 選手データ
- 潮位データ
- オッズデータ

などの整合性を確認
"""

import sqlite3
from datetime import datetime, timedelta
import time
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.scraper.result_scraper_improved_v3 import ImprovedResultScraperV3


class DataIntegrityChecker:
    """データ整合性チェッカー"""

    def __init__(self, db_path="data/boatrace.db"):
        """
        初期化

        Args:
            db_path: データベースパス
        """
        self.db_path = db_path
        self.scraper = ImprovedResultScraperV3()

    def check_race_data(self, start_date: str, end_date: str, venue_codes: list = None):
        """
        指定期間のレースデータ整合性チェック

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)
            venue_codes: チェック対象会場コード（Noneの場合は全会場）
        """
        print("="*80)
        print("データ整合性チェック")
        print("="*80)
        print(f"期間: {start_date} ～ {end_date}")
        print("="*80)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # チェック対象のレースを取得
        if venue_codes:
            placeholders = ','.join('?' * len(venue_codes))
            query = f"""
                SELECT
                    r.id,
                    r.venue_code,
                    r.race_date,
                    r.race_number
                FROM races r
                WHERE r.race_date >= ? AND r.race_date <= ?
                  AND r.venue_code IN ({placeholders})
                ORDER BY r.race_date, r.venue_code, r.race_number
            """
            cursor.execute(query, [start_date, end_date] + venue_codes)
        else:
            cursor.execute("""
                SELECT
                    r.id,
                    r.venue_code,
                    r.race_date,
                    r.race_number
                FROM races r
                WHERE r.race_date >= ? AND r.race_date <= ?
                ORDER BY r.race_date, r.venue_code, r.race_number
            """, (start_date, end_date))

        races = cursor.fetchall()
        print(f"\nチェック対象レース数: {len(races):,}")

        if len(races) == 0:
            print("チェック対象のレースがありません")
            conn.close()
            return

        # 統計情報
        total_checked = 0
        match_count = 0
        mismatch_count = 0
        missing_in_db = 0
        missing_in_official = 0
        errors = 0

        mismatches = []

        print("\nチェック中...")

        for i, (race_id, venue_code, race_date, race_number) in enumerate(races):
            try:
                # 進捗表示
                if (i + 1) % 10 == 0:
                    print(f"  進捗: {i+1}/{len(races)} ({(i+1)/len(races)*100:.1f}%)")

                # DB内のレース詳細データを取得（複数テーブルから結合）
                cursor.execute("""
                    SELECT
                        e.pit_number,
                        e.boat_number,
                        e.racer_number,
                        e.racer_name,
                        res.rank,
                        rd.st_time
                    FROM entries e
                    LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
                    LEFT JOIN race_details rd ON e.race_id = rd.race_id AND e.pit_number = rd.pit_number
                    WHERE e.race_id = ?
                    ORDER BY e.pit_number
                """, (race_id,))

                db_details = cursor.fetchall()

                if not db_details:
                    # DBにレース詳細がない
                    missing_in_db += 1
                    mismatches.append({
                        'type': 'missing_in_db',
                        'race_id': race_id,
                        'venue': venue_code,
                        'date': race_date,
                        'race_num': race_number,
                        'detail': 'DBにレース詳細データなし'
                    })
                    continue

                # 公式サイトからデータ取得
                official_data = self.scraper.get_race_result_complete(venue_code, race_date, race_number)

                if not official_data:
                    # 公式サイトにデータがない（まだ開催されていない、または取得エラー）
                    missing_in_official += 1
                    continue

                # データ比較
                if 'details' not in official_data or not official_data['details']:
                    missing_in_official += 1
                    continue

                official_details = official_data['details']

                # ピット番号でマッチング
                db_dict = {pit_number: detail for pit_number, *detail in db_details}
                official_dict = {d['pit']: d for d in official_details}

                # 各ピットのデータを比較
                has_mismatch = False
                mismatch_details = []

                for pit in range(1, 7):
                    if pit not in db_dict or pit not in official_dict:
                        if pit not in db_dict:
                            mismatch_details.append(f"Pit{pit}: DBにデータなし")
                        if pit not in official_dict:
                            mismatch_details.append(f"Pit{pit}: 公式にデータなし")
                        has_mismatch = True
                        continue

                    db_data = db_dict[pit]
                    official = official_dict[pit]

                    # 比較項目
                    # 0: boat_number, 1: racer_number, 2: racer_name
                    # 3: rank, 4: st_time

                    # 選手登録番号チェック
                    db_racer_num = db_data[1]
                    official_racer_num = official.get('racer_registration_number')
                    if db_racer_num != official_racer_num:
                        mismatch_details.append(
                            f"Pit{pit} 登録番号: DB={db_racer_num} != 公式={official_racer_num}"
                        )
                        has_mismatch = True

                    # 着順チェック（重要）
                    db_finish = db_data[3]
                    official_finish = official.get('finish_position')

                    # 着順の比較（数値として）
                    if db_finish and official_finish:
                        try:
                            db_finish_int = int(db_finish)
                            official_finish_int = int(official_finish)
                            if db_finish_int != official_finish_int:
                                mismatch_details.append(
                                    f"Pit{pit} 着順: DB={db_finish} != 公式={official_finish}"
                                )
                                has_mismatch = True
                        except (ValueError, TypeError):
                            if str(db_finish) != str(official_finish):
                                mismatch_details.append(
                                    f"Pit{pit} 着順: DB={db_finish} != 公式={official_finish}"
                                )
                                has_mismatch = True

                    # ST時間チェック
                    db_st = db_data[4]
                    official_st = official.get('st_time')
                    if db_st and official_st:
                        # 小数点以下の誤差を許容
                        try:
                            if abs(float(db_st) - float(official_st)) > 0.01:
                                mismatch_details.append(
                                    f"Pit{pit} ST: DB={db_st} != 公式={official_st}"
                                )
                                has_mismatch = True
                        except (ValueError, TypeError):
                            pass

                if has_mismatch:
                    mismatch_count += 1
                    mismatches.append({
                        'type': 'mismatch',
                        'race_id': race_id,
                        'venue': venue_code,
                        'date': race_date,
                        'race_num': race_number,
                        'details': mismatch_details
                    })
                else:
                    match_count += 1

                total_checked += 1

                # レート制限
                time.sleep(0.5)

            except Exception as e:
                print(f"\n  [ERROR] レースID {race_id}: {e}")
                errors += 1

        conn.close()

        # 結果表示
        print("\n" + "="*80)
        print("チェック結果")
        print("="*80)
        print(f"チェック済み: {total_checked:,}/{len(races):,}")
        print(f"  一致: {match_count:,} ({match_count/total_checked*100 if total_checked > 0 else 0:.1f}%)")
        print(f"  不一致: {mismatch_count:,} ({mismatch_count/total_checked*100 if total_checked > 0 else 0:.1f}%)")
        print(f"  DBに詳細なし: {missing_in_db:,}")
        print(f"  公式にデータなし: {missing_in_official:,}")
        print(f"  エラー: {errors:,}")
        print("="*80)

        # 不一致の詳細表示
        if mismatches:
            print(f"\n不一致の詳細（最大20件表示）:")
            print("-"*80)
            for i, mismatch in enumerate(mismatches[:20]):
                if mismatch['type'] == 'missing_in_db':
                    print(f"\n{i+1}. 会場{mismatch['venue']} {mismatch['date']} {mismatch['race_num']}R")
                    print(f"   {mismatch['detail']}")
                elif mismatch['type'] == 'mismatch':
                    print(f"\n{i+1}. 会場{mismatch['venue']} {mismatch['date']} {mismatch['race_num']}R")
                    for detail in mismatch['details']:
                        print(f"   - {detail}")

            if len(mismatches) > 20:
                print(f"\n... 他 {len(mismatches) - 20} 件の不一致")

        # サマリー
        print("\n" + "="*80)
        if mismatch_count == 0 and missing_in_db == 0:
            print("[OK] データは正常です")
        elif mismatch_count > 0:
            print(f"[WARN] {mismatch_count} 件の不一致が見つかりました")
        if missing_in_db > 0:
            print(f"[WARN] {missing_in_db} 件のレースがDBに詳細データがありません")
        print("="*80)

        return {
            'total': len(races),
            'checked': total_checked,
            'match': match_count,
            'mismatch': mismatch_count,
            'missing_in_db': missing_in_db,
            'missing_in_official': missing_in_official,
            'errors': errors,
            'mismatches': mismatches
        }


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description='レースデータの整合性チェック'
    )
    parser.add_argument('--start', default='2025-04-01', help='開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2025-04-30', help='終了日 (YYYY-MM-DD)')
    parser.add_argument('--venues', nargs='+', help='対象会場コード（例: 01 02 03）')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')

    args = parser.parse_args()

    checker = DataIntegrityChecker(db_path=args.db)

    result = checker.check_race_data(
        start_date=args.start,
        end_date=args.end,
        venue_codes=args.venues
    )

    print("\n整合性チェック完了")


if __name__ == '__main__':
    main()
