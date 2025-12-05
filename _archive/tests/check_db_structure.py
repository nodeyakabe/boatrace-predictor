"""
データベース構造を確認
"""
import sqlite3
import sys
import io

# Windows環境でのUTF-8出力対応
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('data/boatrace.db')
c = conn.cursor()

# results テーブルのスキーマ
print("=" * 80)
print("results テーブルのスキーマ")
print("=" * 80)
c.execute('PRAGMA table_info(results)')
for col in c.fetchall():
    print(f"{col[1]:20s} {col[2]:10s} (NULL可: {not col[3]})")
print()

# results テーブルのサンプルデータ
print("=" * 80)
print("results テーブルのサンプルデータ (最初の5件)")
print("=" * 80)
c.execute('SELECT * FROM results LIMIT 5')
rows = c.fetchall()
if rows:
    c.execute('PRAGMA table_info(results)')
    columns = [col[1] for col in c.fetchall()]
    print(f"カラム: {', '.join(columns)}")
    for row in rows:
        print(row)
else:
    print("⚠️ データがありません")
print()

# results テーブルのデータ件数
c.execute('SELECT COUNT(*) FROM results')
result_count = c.fetchone()[0]
print(f"results テーブル総件数: {result_count:,}件")
print()

# rank カラムの値の種類を確認
print("=" * 80)
print("rank カラムの値の分布")
print("=" * 80)
c.execute('SELECT rank, COUNT(*) as count FROM results GROUP BY rank ORDER BY rank')
for row in c.fetchall():
    print(f"rank = '{row[0]}': {row[1]:,}件")
print()

# entries と results の JOIN 確認
print("=" * 80)
print("entries と results の JOIN テスト")
print("=" * 80)
c.execute("""
    SELECT
        e.racer_number,
        e.racer_name,
        r.venue_code,
        res.rank,
        COUNT(*) as count
    FROM entries e
    JOIN races r ON e.race_id = r.id
    LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank IS NOT NULL
    GROUP BY e.racer_number, e.racer_name, r.venue_code, res.rank
    LIMIT 10
""")
rows = c.fetchall()
if rows:
    print("JOIN成功 - サンプルデータ:")
    for row in rows:
        print(f"  選手#{row[0]} {row[1]:10s} 場{row[2]} rank={row[3]} ({row[4]}件)")
else:
    print("⚠️ JOIN結果がありません")
print()

# rank='1' で絞り込んでみる
print("=" * 80)
print("rank='1' のデータ確認")
print("=" * 80)
c.execute("""
    SELECT
        e.racer_number,
        e.racer_name,
        COUNT(*) as win_count
    FROM entries e
    JOIN races r ON e.race_id = r.id
    LEFT JOIN results res ON e.race_id = res.race_id AND e.pit_number = res.pit_number
    WHERE res.rank = '1'
    GROUP BY e.racer_number, e.racer_name
    ORDER BY win_count DESC
    LIMIT 10
""")
rows = c.fetchall()
if rows:
    print("1着回数上位10名:")
    for row in rows:
        print(f"  選手#{row[0]} {row[1]:10s}: {row[2]}勝")
else:
    print("⚠️ rank='1'のデータがありません")
print()

conn.close()
print("=" * 80)
