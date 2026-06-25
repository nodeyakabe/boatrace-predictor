"""
shadow_bets 精度集計スクリプト

shadow（多点仮想）と現行1点購入の的中率・収支を比較表示する。

使用例:
    python scripts/monitoring/shadow_accuracy.py           # 直近30日
    python scripts/monitoring/shadow_accuracy.py --days 60
    python scripts/monitoring/shadow_accuracy.py --days 7
"""
import sys
import sqlite3
import argparse
from datetime import datetime, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

DB_PATH = project_root / "data" / "boatrace.db"

VENUE_MAP = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}


def fetch_shadow_stats(conn, start_date: str, end_date: str) -> dict:
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*)                                                AS total,
            SUM(CASE WHEN hit_combination IS NOT NULL THEN 1 ELSE 0 END) AS hits,
            SUM(CASE WHEN odds_if_hit IS NOT NULL
                     THEN odds_if_hit * 100 ELSE 0 END)           AS gross_return
        FROM shadow_bets sb
        JOIN races r ON sb.race_id = r.id
        WHERE sb.reconciled_at IS NOT NULL
          AND r.race_date >= ? AND r.race_date <= ?
    """, (start_date, end_date))
    row = cur.fetchone()
    total, hits, gross = row[0] or 0, row[1] or 0, row[2] or 0.0

    # p1 的中率（実1着が予測p1と一致した件数）
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN
                actual_result IS NOT NULL AND
                CAST(SUBSTR(actual_result, 1, INSTR(actual_result, '-') - 1) AS INTEGER) =
                CAST(SUBSTR(combinations,  1, INSTR(combinations,  '-') - 1) AS INTEGER)
            THEN 1 ELSE 0 END) AS p1_hits
        FROM shadow_bets sb
        JOIN races r ON sb.race_id = r.id
        WHERE sb.reconciled_at IS NOT NULL
          AND r.race_date >= ? AND r.race_date <= ?
    """, (start_date, end_date))
    row2 = cur.fetchone()
    p1_total, p1_hits = row2[0] or 0, row2[1] or 0

    # 1点ずつの詳細（結果ありのもの）
    cur.execute("""
        SELECT
            r.race_date, r.venue_code, r.race_number,
            sb.combinations, sb.actual_result, sb.hit_combination, sb.odds_if_hit
        FROM shadow_bets sb
        JOIN races r ON sb.race_id = r.id
        WHERE sb.reconciled_at IS NOT NULL
          AND r.race_date >= ? AND r.race_date <= ?
        ORDER BY r.race_date DESC, r.race_number DESC
    """, (start_date, end_date))
    details = []
    for row in cur.fetchall():
        venue = VENUE_MAP.get(str(row[1]).zfill(2), f'会場{row[1]}')
        details.append({
            'date': row[0], 'venue': venue, 'race_num': row[2],
            'combinations': row[3], 'actual': row[4],
            'hit': row[5], 'odds': row[6],
        })

    return {
        'total': total, 'hits': hits, 'gross': gross,
        'p1_total': p1_total, 'p1_hits': p1_hits,
        'details': details,
    }


def fetch_onebet_stats(conn, start_date: str, end_date: str) -> dict:
    cur = conn.cursor()
    # bet_notifications テーブルが存在するか確認
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bet_notifications'")
    if not cur.fetchone():
        return {'total': 0, 'hits': 0, 'gross': 0.0}

    cur.execute("""
        SELECT
            COUNT(*)                          AS total,
            SUM(CASE WHEN
                res1.pit_number IS NOT NULL AND res2.pit_number IS NOT NULL AND res3.pit_number IS NOT NULL
                AND (res1.pit_number || '-' || res2.pit_number || '-' || res3.pit_number) = bn.combinations
            THEN 1 ELSE 0 END)               AS hits,
            SUM(CASE WHEN
                res1.pit_number IS NOT NULL AND res2.pit_number IS NOT NULL AND res3.pit_number IS NOT NULL
                AND (res1.pit_number || '-' || res2.pit_number || '-' || res3.pit_number) = bn.combinations
            THEN COALESCE(t.odds, 0) * 100 ELSE 0 END) AS gross_return
        FROM bet_notifications bn
        JOIN races r ON bn.race_id = r.id
        LEFT JOIN results res1 ON res1.race_id = bn.race_id AND res1.rank = 1 AND res1.is_invalid = 0
        LEFT JOIN results res2 ON res2.race_id = bn.race_id AND res2.rank = 2 AND res2.is_invalid = 0
        LEFT JOIN results res3 ON res3.race_id = bn.race_id AND res3.rank = 3 AND res3.is_invalid = 0
        LEFT JOIN trifecta_odds t ON t.race_id = bn.race_id AND t.combination = bn.combinations
        WHERE bn.notification_type = 'confirmed'
          AND r.race_date >= ? AND r.race_date <= ?
    """, (start_date, end_date))
    row = cur.fetchone()
    return {
        'total': row[0] or 0,
        'hits': row[1] or 0,
        'gross': row[2] or 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description="shadow多点 vs 1点購入 精度比較")
    parser.add_argument("--days", type=int, default=30, help="集計対象日数（デフォルト30日）")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--detail", action="store_true", help="レース別詳細を表示")
    args = parser.parse_args()

    end_date   = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')

    conn = sqlite3.connect(args.db)
    try:
        sh = fetch_shadow_stats(conn, start_date, end_date)
        ob = fetch_onebet_stats(conn, start_date, end_date)
    finally:
        conn.close()

    print(f"\n=== shadow精度集計  {start_date} ~ {end_date}（{args.days}日間）===")

    print(f"\n【shadow 多点（仮想観測・100円/点）】")
    if sh['total'] > 0:
        n = sh['total']
        combos_per_race = len(sh['details'][0]['combinations'].split(',')) if sh['details'] else 5
        invest = n * combos_per_race * 100
        gross  = sh['gross']
        profit = gross - invest
        rate   = sh['hits'] / n * 100
        roi    = gross / invest * 100 if invest > 0 else 0.0
        sign   = '+' if profit >= 0 else ''
        print(f"  対象件数  : {n}件")
        print(f"  的中率    : {sh['hits']}/{n}  ({rate:.1f}%)")
        print(f"  p1的中率  : {sh['p1_hits']}/{sh['p1_total']}  "
              f"({sh['p1_hits']/sh['p1_total']*100:.1f}%)" if sh['p1_total'] > 0 else "  p1的中率: N/A")
        print(f"  理論ROI   : {roi:.1f}%")
        print(f"  理論収支  : {sign}{profit:,.0f}円  (投資{invest:,}円 / 回収{gross:,.0f}円)")
    else:
        print("  データなし（shadow_bets 突合せ済みレコードが期間内にない）")

    print(f"\n【現行1点購入（同期間の confirmed 通知）】")
    if ob['total'] > 0:
        n = ob['total']
        invest = n * 100
        gross  = ob['gross']
        profit = gross - invest
        rate   = ob['hits'] / n * 100
        roi    = gross / invest * 100 if invest > 0 else 0.0
        sign   = '+' if profit >= 0 else ''
        print(f"  対象件数  : {n}件")
        print(f"  的中率    : {ob['hits']}/{n}  ({rate:.1f}%)")
        print(f"  ROI       : {roi:.1f}%")
        print(f"  収支      : {sign}{profit:,.0f}円  (投資{invest:,}円 / 回収{gross:,.0f}円)")
    else:
        print("  データなし")

    if args.detail and sh['details']:
        print(f"\n【shadow レース別詳細（直近{min(len(sh['details']), 20)}件）】")
        for d in sh['details'][:20]:
            combos_list = [c.strip() for c in d['combinations'].split(',') if c.strip()]
            if d['hit']:
                odds_str = f"  {d['odds']:.1f}倍" if d['odds'] else ''
                mark = f"HIT `{d['hit']}`{odds_str}"
            else:
                mark = f"MISS  実={d['actual'] or 'N/A'}"
            print(f"  {d['date']} {d['venue']} {d['race_num']}R  {mark}")
            print(f"    {' / '.join(combos_list)}")


if __name__ == "__main__":
    main()
