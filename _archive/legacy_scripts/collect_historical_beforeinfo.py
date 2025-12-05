"""
過去のレースの直前情報を収集するスクリプト
精度検証用のデータを準備する
"""

import sqlite3
from src.scraper.beforeinfo_scraper import BeforeInfoScraper
import time

def main():
    print('=' * 80)
    print('過去レースの直前情報収集（精度検証用）')
    print('=' * 80)

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 11/17のレース（結果が確定している）を取得
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE res.rank IS NOT NULL
        AND res.is_invalid = 0
        AND r.race_date = '2025-11-17'
        ORDER BY r.venue_code, r.race_number
        LIMIT 30
    ''')

    target_races = cursor.fetchall()
    conn.close()

    if not target_races:
        print('[ERROR] 対象レースが見つかりませんでした')
        return

    print(f'\n[対象レース] {len(target_races)}件')
    print('race_id | 日付       | 会場 | R#')
    print('-' * 80)
    for race in target_races[:10]:
        print(f'{race[0]:7d} | {race[1]} | {race[2]:4s} | {race[3]:2d}')
    if len(target_races) > 10:
        print(f'...他{len(target_races) - 10}件')

    # 直前情報スクレイパーを初期化
    scraper = BeforeInfoScraper()

    print('\n' + '=' * 80)
    print('直前情報を収集中...')
    print('=' * 80)

    success_count = 0
    skip_count = 0
    error_count = 0

    for i, (race_id, race_date, venue_code, race_number) in enumerate(target_races, 1):
        # 日付を YYYYMMDD 形式に変換
        date_str = race_date.replace('-', '')

        print(f'\n[{i}/{len(target_races)}] race_id={race_id} ({venue_code} {race_number}R)... ', end='', flush=True)

        try:
            # 直前情報を取得
            beforeinfo = scraper.get_race_beforeinfo(venue_code, date_str, race_number)

            if beforeinfo and beforeinfo.get('is_published'):
                # DBに保存
                if scraper.save_to_db(race_id, beforeinfo):
                    print('✓ 保存成功')
                    success_count += 1
                else:
                    print('× 保存失敗')
                    error_count += 1
            else:
                print('- 未公開（スキップ）')
                skip_count += 1

        except Exception as e:
            print(f'✗ エラー: {e}')
            error_count += 1

        # API負荷軽減のため待機
        time.sleep(1.5)

    scraper.close()

    # 結果サマリー
    print('\n' + '=' * 80)
    print('収集結果サマリー')
    print('=' * 80)
    print(f'成功: {success_count}件')
    print(f'スキップ: {skip_count}件')
    print(f'エラー: {error_count}件')
    print(f'合計: {len(target_races)}件')

    if success_count > 0:
        print('\n直前情報の収集が完了しました。')
        print('次に test_prediction_accuracy.py を実行して精度検証を行えます。')
    else:
        print('\n[警告] 直前情報が1件も収集できませんでした。')
        print('過去のレースの直前情報は公式サイトから削除されている可能性があります。')

if __name__ == '__main__':
    main()
