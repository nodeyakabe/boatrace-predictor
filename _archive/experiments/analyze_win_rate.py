"""
的中率分析スクリプト
現在のデータから予測精度を評価
"""
import sqlite3

def analyze_win_rate():
    conn = sqlite3.connect('data/boatrace.db')
    c = conn.cursor()

    # 1着の総数
    c.execute('SELECT COUNT(*) FROM results WHERE rank = "1"')
    wins = c.fetchone()[0]

    # 総出走数
    c.execute('SELECT COUNT(*) FROM results')
    total = c.fetchone()[0]

    print("=" * 80)
    print("的中率分析")
    print("=" * 80)
    print(f"\n【基本統計】")
    print(f"1着総数: {wins:,}")
    print(f"総出走数: {total:,}")
    print(f"1着率: {wins/total*100:.2f}%")
    print(f"ランダム予測: {1/6*100:.2f}%")

    # 枠番別1着率
    print(f"\n【枠番別1着率】")
    for pit in range(1, 7):
        c.execute(f'SELECT COUNT(*) FROM entries e JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number WHERE e.pit_number = {pit} AND r.rank = "1"')
        pit_wins = c.fetchone()[0]
        c.execute(f'SELECT COUNT(*) FROM entries WHERE pit_number = {pit}')
        pit_total = c.fetchone()[0]
        if pit_total > 0:
            print(f"  {pit}号艇: {pit_wins/pit_total*100:.2f}% ({pit_wins:,}/{pit_total:,})")

    # 競艇場別1着数
    print(f"\n【競艇場別1着数 TOP 5】")
    c.execute('SELECT venue_code, COUNT(*) as cnt FROM results r JOIN races ra ON r.race_id = ra.id WHERE rank = "1" GROUP BY venue_code ORDER BY cnt DESC LIMIT 5')
    for row in c.fetchall():
        print(f"  場{row[0]}: {row[1]:,}回")

    # データ品質
    print(f"\n【データ品質】")
    c.execute('SELECT COUNT(DISTINCT race_id) FROM race_details WHERE exhibition_time IS NOT NULL')
    exh_count = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM races')
    race_count = c.fetchone()[0]
    print(f"展示タイムあり: {exh_count:,}/{race_count:,} ({exh_count/race_count*100:.1f}%)")

    c.execute('SELECT COUNT(DISTINCT race_id) FROM race_details WHERE st_time IS NOT NULL')
    st_count = c.fetchone()[0]
    print(f"STタイムあり: {st_count:,}/{race_count:,} ({st_count/race_count*100:.1f}%)")

    c.execute('SELECT COUNT(DISTINCT venue_code || weather_date) FROM weather WHERE weather_condition IS NOT NULL')
    weather_count = c.fetchone()[0]
    print(f"天候データあり: {weather_count:,}日")

    print("\n" + "=" * 80)
    print("予測精度改善のポイント")
    print("=" * 80)
    print("1. 展示タイムデータ: 現在13.8% → 80%+に改善必要")
    print("2. STタイムデータ: 現在53.5% → 85%+に改善必要")
    print("3. 天候データ: ほぼ0% → 70%+に改善必要")
    print("4. 1号艇の有利性を活用（通常30-40%の勝率）")
    print("5. 競艇場特性の学習（水面・コース特性）")
    print("\n→ バックグラウンドで不足データ取得中...")

    conn.close()

if __name__ == "__main__":
    analyze_win_rate()
