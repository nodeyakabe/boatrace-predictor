"""予想生成状況を確認するスクリプト"""
import sqlite3

conn = sqlite3.connect('data/boatrace.db')
cur = conn.cursor()

print("="*70)
print("予想生成状況サマリー")
print("="*70)

# 年度別の状況を確認
for year in ['2020', '2021', '2022', '2023', '2024', '2025']:
    cur.execute(f"SELECT COUNT(DISTINCT id) FROM races WHERE race_date LIKE '{year}%'")
    total_races = cur.fetchone()[0]

    for pred_type in ['advance', 'before']:
        cur.execute(f"""
            SELECT COUNT(DISTINCT rp.race_id)
            FROM race_predictions rp
            JOIN races r ON r.id = rp.race_id
            WHERE r.race_date LIKE '{year}%'
            AND rp.prediction_type = '{pred_type}'
        """)
        generated = cur.fetchone()[0]
        pct = 100 * generated / total_races if total_races > 0 else 0
        remaining = total_races - generated
        print(f"{year}年 {pred_type:8s}: {generated:6,}/{total_races:6,}レース ({pct:5.1f}%) 残り{remaining:5,}")

    print()

conn.close()
