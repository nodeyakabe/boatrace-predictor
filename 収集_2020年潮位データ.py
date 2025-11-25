"""
2020年潮位データ収集スクリプト
気象庁の潮位データは2011-2020年のみ利用可能
このスクリプトで2020年10月の潮位データを収集して動作確認を行う
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.append('src')

import sqlite3
from datetime import datetime, timedelta
from scraper.tide_browser_scraper import TideBrowserScraper
from tqdm import tqdm
import time

print("="*80)
print("2020年潮位データ収集（気象庁データ利用可能期間）")
print("="*80)

# 海水場の会場コード
SEAWATER_VENUES = ['15', '16', '17', '18', '20', '22', '24']

# 2020年10月の期間を設定（気象庁データが利用可能）
start_date = datetime(2020, 10, 1)
end_date = datetime(2020, 10, 31)
days = (end_date - start_date).days + 1
dates = [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days)]

print(f"\n収集対象:")
print(f"  会場: {len(SEAWATER_VENUES)}会場（海水場のみ）")
print(f"  期間: {dates[0]} ～ {dates[-1]} ({len(dates)}日分)")
print(f"  合計: {len(SEAWATER_VENUES) * len(dates)}会場日")

# 会場名マッピング
venue_names = {
    '15': '児島',
    '16': '鳴門',
    '17': '丸亀',
    '18': '宮島',
    '20': '若松',
    '22': '福岡',
    '24': '大村'
}

# DBに接続
conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# すでに収集済みのデータを確認
cursor.execute("""
    SELECT COUNT(*) FROM tide
    WHERE tide_date BETWEEN ? AND ?
""", (dates[0], dates[-1]))
existing_count = cursor.fetchone()[0]

if existing_count > 0:
    print(f"\n注意: すでに{existing_count}件のデータが存在します")
    print("  既存データはスキップします")

# 潮位データを収集
scraper = TideBrowserScraper(headless=True, delay=2.0)
success_count = 0
no_data_count = 0
error_count = 0
skip_count = 0

# 全組み合わせを生成
all_combos = [(venue, date) for venue in SEAWATER_VENUES for date in dates]

print(f"\n潮位データ収集を開始します...")
print(f"  総件数: {len(all_combos)}会場日")
print()

for venue_code, tide_date in tqdm(all_combos, desc="潮位データ収集"):
    try:
        # すでに潮位データがあるかチェック
        cursor.execute("""
            SELECT COUNT(*) FROM tide
            WHERE venue_code = ? AND tide_date = ?
        """, (venue_code, tide_date))

        existing = cursor.fetchone()[0]

        if existing > 0:
            # すでにデータがある場合はスキップ
            skip_count += 1
            continue

        # 潮位データを取得
        tide_data = scraper.get_tide_data(venue_code, tide_date)

        if tide_data:
            # データをDBに保存
            for data in tide_data:
                cursor.execute("""
                    INSERT INTO tide (venue_code, tide_date, tide_time, tide_type, tide_level, created_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                """, (venue_code, tide_date, data['time'], data['type'], data['level']))

            conn.commit()
            success_count += 1
        else:
            no_data_count += 1

        # レート制限対策（適度な待機時間）
        time.sleep(2.0)

    except Exception as e:
        error_count += 1
        tqdm.write(f"エラー ({venue_names.get(venue_code, venue_code)}, {tide_date}): {e}")

scraper.close()

# 収集結果をレポート
print("\n" + "="*80)
print("収集完了")
print("="*80)
print(f"成功: {success_count}会場日")
print(f"データなし: {no_data_count}会場日")
print(f"スキップ: {skip_count}会場日（既存データ）")
print(f"失敗: {error_count}会場日")
total = success_count + no_data_count + skip_count + error_count
if total > 0:
    print(f"成功率: {success_count/total*100:.1f}%")

# 保存されたデータを確認
print("\n" + "="*80)
print("保存データ確認")
print("="*80)

cursor.execute("""
    SELECT
        venue_code,
        COUNT(DISTINCT tide_date) as days,
        COUNT(*) as records,
        MIN(tide_date) as min_date,
        MAX(tide_date) as max_date
    FROM tide
    WHERE tide_date BETWEEN ? AND ?
    GROUP BY venue_code
    ORDER BY venue_code
""", (dates[0], dates[-1]))

rows = cursor.fetchall()

if rows:
    print("\n会場別潮位データ:")
    for venue_code, days, records, min_date, max_date in rows:
        venue_name = venue_names.get(venue_code, f"場{venue_code}")
        print(f"  {venue_name}(場{venue_code}): {days}日分 ({records}件) [{min_date} ～ {max_date}]")
else:
    print("\n潮位データがありません")

# 最新データのサンプル表示
cursor.execute("""
    SELECT venue_code, tide_date, tide_time, tide_type, tide_level
    FROM tide
    WHERE tide_date BETWEEN ? AND ?
    ORDER BY tide_date DESC, venue_code, tide_time
    LIMIT 10
""", (dates[0], dates[-1]))

sample_rows = cursor.fetchall()

if sample_rows:
    print("\nデータサンプル（最新10件）:")
    for venue_code, tide_date, tide_time, tide_type, tide_level in sample_rows:
        venue_name = venue_names.get(venue_code, f"場{venue_code}")
        print(f"  {venue_name} {tide_date} {tide_time} {tide_type}: {tide_level}cm")

conn.close()
print("\n" + "="*80)
print("\n注意事項:")
print("  - 気象庁の潮位データは2011-2020年のみ利用可能です")
print("  - 現在のレースデータ(2022-2025年)には潮位データを紐付けできません")
print("  - このデータは参考データとして活用してください")
print("="*80)
