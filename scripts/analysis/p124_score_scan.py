# -*- coding: utf-8 -*-
"""P124 (p1-p2-p4) × C信頼度 × 150-200倍 スコア帯別 IS/OOS スキャン"""
import sys, io, sqlite3, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, "data/boatrace.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

CONF = 'C'
ODDS_LO = 150
ODDS_HI = 200

BASE_WHERE = f"""
    r.race_date>='2020-01-01' AND r.race_date<='2025-12-31'
    AND rp1.confidence='{CONF}'
    AND CAST(t.odds AS REAL)>={ODDS_LO} AND CAST(t.odds AS REAL)<{ODDS_HI}
    AND e1.racer_rank IN ('A1','A2','B1','B2')
"""

BASE_JOINS = """
    JOIN race_predictions rp1 ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
    JOIN race_predictions rp2 ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
    JOIN race_predictions rp4 ON r.id=rp4.race_id AND rp4.prediction_type='before' AND rp4.rank_prediction=4
    JOIN trifecta_odds t ON r.id=t.race_id
        AND t.combination=CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)
    JOIN entries e1 ON r.id=e1.race_id AND e1.pit_number=1
    JOIN results rs1 ON r.id=rs1.race_id AND rs1.rank='1'
    JOIN results rs2 ON r.id=rs2.race_id AND rs2.rank='2'
    JOIN results rs3 ON r.id=rs3.race_id AND rs3.rank='3'
"""

HIT = "rs1.pit_number=rp1.pit_number AND rs2.pit_number=rp2.pit_number AND rs3.pit_number=rp4.pit_number"

print("="*75)
print("P124 (p1-p2-p4) × C信頼度 × 150-200倍 スコア帯別 IS/OOS スキャン")
print("  IS=2020-2022 / OOS=2023-2025 / c1_rank A1/A2/B1/B2")
print("="*75)

# スコア分布確認
cur.execute(f"""
SELECT MIN(rp1.total_score), MAX(rp1.total_score), AVG(rp1.total_score), COUNT(*)
FROM races r {BASE_JOINS}
WHERE {BASE_WHERE}
""")
row = cur.fetchone()
print(f"\nスコア分布: min={row[0]:.1f} / max={row[1]:.1f} / avg={row[2]:.1f} / 総件数={row[3]:,}")


def calc_isoos(lo_s, hi_s):
    q = f"""
    SELECT
        SUM(CASE WHEN CAST(strftime('%Y',r.race_date) AS INT)<=2022 THEN 1 ELSE 0 END),
        SUM(CASE WHEN CAST(strftime('%Y',r.race_date) AS INT)<=2022 AND {HIT}
            THEN CAST(t.odds AS REAL)*100 ELSE 0 END),
        SUM(CASE WHEN CAST(strftime('%Y',r.race_date) AS INT)>2022 THEN 1 ELSE 0 END),
        SUM(CASE WHEN CAST(strftime('%Y',r.race_date) AS INT)>2022 AND {HIT}
            THEN CAST(t.odds AS REAL)*100 ELSE 0 END),
        SUM(CASE WHEN {HIT} THEN 1 ELSE 0 END)
    FROM races r {BASE_JOINS}
    WHERE {BASE_WHERE}
        AND rp1.total_score>={lo_s} AND rp1.total_score<{hi_s}
    """
    cur.execute(q)
    return cur.fetchone()


def calc_year(lo_s, hi_s):
    q = f"""
    SELECT
        CAST(strftime('%Y',r.race_date) AS INT) AS yr,
        COUNT(*) AS n,
        SUM(CASE WHEN {HIT} THEN 1 ELSE 0 END) AS hits,
        SUM(CASE WHEN {HIT} THEN CAST(t.odds AS REAL)*100 ELSE 0 END) - COUNT(*)*100 AS profit
    FROM races r {BASE_JOINS}
    WHERE {BASE_WHERE}
        AND rp1.total_score>={lo_s} AND rp1.total_score<{hi_s}
    GROUP BY yr ORDER BY yr
    """
    cur.execute(q)
    return cur.fetchall()


def print_scan(bands, title):
    print(f"\n{title}")
    print(f"  {'スコア帯':>10} | {'件数':>5} | {'的中':>4} | {'IS件':>5} | {'IS ROI':>7} | {'OOS件':>5} | {'OOS ROI':>8} | 判定")
    print(f"  {'-'*72}")
    cands = []
    for lo, hi in bands:
        row = calc_isoos(lo, hi)
        ni, ip, no, op, th = row
        if not ni or ni < 10: continue
        roi_i = ip/(ni*100)*100 if ni>0 else 0
        roi_o = op/(no*100)*100 if no>0 else 0
        mi = '★' if roi_i>=100 else ' '
        mo = '★' if roi_o>=100 else ' '
        both = '◎' if roi_i>=100 and roi_o>=100 else ' '
        print(f"  {lo:>3}-{hi:<3}点 | {ni+no:>5} | {th:>4} | {ni:>5} | {roi_i:>6.1f}%{mi} | {no:>5} | {roi_o:>7.1f}%{mo} | {both}")
        if roi_i >= 100 and roi_o >= 100:
            cands.append((lo, hi, ni, no, roi_i, roi_o))
    return cands


# 10点幅
cands1 = print_scan([(s, s+10) for s in range(50, 105, 10)], "【10点幅スキャン】")

# 6点幅（細かく）
cands2 = print_scan([(s, s+6) for s in range(50, 102, 3)], "【6点幅スキャン（詳細）】")

# 8点幅（P142/P132採用時と同様の粒度）
cands3 = print_scan([(s, s+8) for s in range(50, 102, 4)], "【8点幅スキャン（P142/P132比較用）】")

all_cands = {}
for c in cands1 + cands2 + cands3:
    key = (c[0], c[1])
    if key not in all_cands:
        all_cands[key] = c

# 年度別詳細
if all_cands:
    print(f"\n{'='*75}")
    print("【◎候補 年度別詳細】")
    print(f"{'='*75}")
    for (lo, hi), (lo2, hi2, ni, no, roi_i, roi_o) in sorted(all_cands.items()):
        rows = calc_year(lo, hi)
        if not rows: continue
        total_n = sum(r[1] for r in rows)
        total_h = sum(r[2] for r in rows)
        total_pay = sum((r[3] + r[1]*100) for r in rows)
        total_roi = total_pay/(total_n*100)*100 if total_n>0 else 0
        total_pr = int(total_pay - total_n*100)
        black = sum(1 for r in rows if r[3] > 0)
        print(f"\n  スコア {lo}-{hi}点 | IS {roi_i:.1f}% / OOS {roi_o:.1f}% | {total_n}件/{total_h}的中 | {black}/6年黒字")
        print(f"  {'年':>4} | {'件数':>5} | {'的中':>4} | {'ROI':>7} | {'収支':>10}")
        for r in rows:
            mark = '○' if r[3] > 0 else '×'
            roi_y = (r[3]+r[1]*100)/(r[1]*100)*100 if r[1]>0 else 0
            print(f"  {r[0]} | {r[1]:>5} | {r[2]:>4} | {roi_y:>6.1f}% | {int(r[3]):>+10,}円 | {mark}")
        print(f"  合計 | {total_n:>5} | {total_h:>4} | {total_roi:>6.1f}% | {total_pr:>+10,}円 | {black}/6年")
else:
    print("\n◎候補なし")

# スコアなしの全体も再掲
print(f"\n{'='*75}")
print("【参考: スコアフィルターなし（全スコア）】")
row = calc_isoos(0, 9999)
ni, ip, no, op, th = row
roi_i = ip/(ni*100)*100
roi_o = op/(no*100)*100
rows = calc_year(0, 9999)
black = sum(1 for r in rows if r[3]>0)
total_pr = int(ip+op - (ni+no)*100)
print(f"  IS {ni}件/ROI {roi_i:.1f}% / OOS {no}件/ROI {roi_o:.1f}% / {th}的中 / {black}/6年黒字 / 合計{total_pr:+,}円")

conn.close()
print("\n完了")
