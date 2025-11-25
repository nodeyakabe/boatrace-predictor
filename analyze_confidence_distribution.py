"""
信頼度分布を分析して改善策を検討するスクリプト
"""
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/boatrace.db')
cursor = conn.cursor()

# 最新の予想データを取得
cursor.execute("""
    SELECT
        rp.confidence,
        rp.total_score,
        r.race_date,
        r.venue_code,
        r.race_number
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    WHERE r.race_date >= date('now', '-7 days')
    ORDER BY r.race_date DESC, r.venue_code, r.race_number
""")

predictions = cursor.fetchall()

print("=" * 80)
print("過去7日間の予想データ分析")
print("=" * 80)

# 信頼度の分布
confidence_dist = Counter([p[0] for p in predictions])
print("\n【信頼度の分布】")
total = len(predictions)
for level in ['A', 'B', 'C', 'D', 'E']:
    count = confidence_dist.get(level, 0)
    pct = count / total * 100 if total > 0 else 0
    print(f"{level}: {count:4d}件 ({pct:5.1f}%)")

print(f"\n総予想数: {total}件")

# スコア分布
scores_by_confidence = {}
for conf in ['A', 'B', 'C', 'D', 'E']:
    scores = [p[1] for p in predictions if p[0] == conf]
    if scores:
        scores_by_confidence[conf] = {
            'count': len(scores),
            'avg': sum(scores) / len(scores),
            'max': max(scores),
            'min': min(scores)
        }

print("\n【信頼度別のスコア分布】")
for conf in ['A', 'B', 'C', 'D', 'E']:
    if conf in scores_by_confidence:
        stats = scores_by_confidence[conf]
        print(f"{conf}: 平均{stats['avg']:.1f} (最大{stats['max']:.1f}, 最小{stats['min']:.1f})")

# 最新日のデータ
cursor.execute("""
    SELECT MAX(race_date) FROM races
    WHERE race_date IN (SELECT DISTINCT r.race_date FROM race_predictions rp JOIN races r ON rp.race_id = r.id)
""")
latest_date = cursor.fetchone()[0]

if latest_date:
    cursor.execute("""
        SELECT
            rp.confidence,
            rp.total_score,
            r.venue_code,
            r.race_number,
            rp.pit_number,
            rp.racer_name
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date = ?
        ORDER BY r.venue_code, r.race_number, rp.rank_prediction
    """, (latest_date,))

    latest_preds = cursor.fetchall()

    print(f"\n【{latest_date}の予想】")
    latest_conf = Counter([p[0] for p in latest_preds])
    print(f"信頼度分布: A={latest_conf.get('A', 0)} B={latest_conf.get('B', 0)} C={latest_conf.get('C', 0)} D={latest_conf.get('D', 0)} E={latest_conf.get('E', 0)}")

    print("\n【サンプル（上位3レースの1着予想）】")
    venues_shown = set()
    count = 0
    for p in latest_preds:
        venue = p[2]
        if venue not in venues_shown and count < 10:
            print(f"会場{venue:02d} R{p[3]:02d} {p[4]}号艇 {p[5][:8]:8s} スコア:{p[1]:5.1f} 信頼度:{p[0]}")
            venues_shown.add(venue)
            count += 1

# 的中率分析（結果データがある場合）
print("\n" + "=" * 80)
print("的中率分析（信頼度別）")
print("=" * 80)

cursor.execute("""
    SELECT
        rp.confidence,
        COUNT(*) as total,
        SUM(CASE WHEN rp.rank_prediction = 1 AND res.finish_order = 1 THEN 1 ELSE 0 END) as correct
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
    WHERE r.race_date >= date('now', '-30 days')
    AND r.race_date < date('now')
    GROUP BY rp.confidence
""")

accuracy_data = cursor.fetchall()

if accuracy_data:
    print("\n【過去30日間の1着的中率（信頼度別）】")
    for conf, total, correct in accuracy_data:
        accuracy = correct / total * 100 if total > 0 else 0
        print(f"{conf}: {correct}/{total} = {accuracy:.1f}%")
else:
    print("\n結果データが不足しているため、的中率は計算できません。")

conn.close()

print("\n" + "=" * 80)
print("改善提案")
print("=" * 80)
print("""
1. 信頼度A/Bが少ない場合:
   → データ量基準が厳しすぎる可能性

2. 信頼度C/D/Eが多い場合:
   → スコアリングロジックの改善が必要

3. 的中率が信頼度と相関していない場合:
   → 信頼度判定ロジック自体の見直しが必要

4. 高スコアでも低信頼度の場合:
   → データ量制約が厳しすぎる（ただし的中率を確認すること）
""")
