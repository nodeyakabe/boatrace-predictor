#!/usr/bin/env python3
"""
信頼度分布自動チェックスクリプト (E-1 再発防止策D)

2スケール混在問題の再発を防ぐため、信頼度分布を自動チェックする。

正常範囲（新コード基準）:
  advance: A%/予測 = 2-5%、A%/レース = 12-30%
  before:  A%/予測 = 2-9%、A%/レース = 12-54%
  A%/予測 > 10% → 旧コード混入の疑い（要再生成）

使用法:
  python scripts/analysis/check_confidence_distribution.py            # 全年度
  python scripts/analysis/check_confidence_distribution.py --year 2025
  python scripts/analysis/check_confidence_distribution.py --type before
  python scripts/analysis/check_confidence_distribution.py --alert-only
"""

import sqlite3
import argparse
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boatrace.db"

# 正常範囲（新コード基準）
NORMAL_RANGES = {
    "advance": {
        "A_per_pred_min": 2.0,
        "A_per_pred_max": 5.0,
        "A_per_race_min": 12.0,
        "A_per_race_max": 30.0,
        "alert_threshold": 10.0,   # A%/予測がこれを超えたらアラート
        "min_samples": 1000,        # チェック対象とする最低件数
    },
    "before": {
        "A_per_pred_min": 2.0,
        "A_per_pred_max": 9.0,
        "A_per_race_min": 12.0,
        "A_per_race_max": 54.0,
        "alert_threshold": 10.0,
        "min_samples": 1000,
    },
}


def get_distribution(conn, year=None, pred_type=None):
    """信頼度分布を年度・タイプ別に取得"""
    where_clauses = []
    params = []

    if year:
        where_clauses.append("strftime('%Y', r.race_date) = ?")
        params.append(str(year))

    if pred_type:
        where_clauses.append("rp.prediction_type = ?")
        params.append(pred_type)

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    sql = f"""
    SELECT
        strftime('%Y', r.race_date) AS year,
        rp.prediction_type,
        COUNT(*) AS total_predictions,
        SUM(CASE WHEN rp.confidence = 'A' THEN 1 ELSE 0 END) AS A_count,
        SUM(CASE WHEN rp.confidence = 'B' THEN 1 ELSE 0 END) AS B_count,
        SUM(CASE WHEN rp.confidence = 'C' THEN 1 ELSE 0 END) AS C_count,
        ROUND(100.0 * SUM(CASE WHEN rp.confidence = 'A' THEN 1 ELSE 0 END) / COUNT(*), 1) AS A_pct,
        ROUND(100.0 * SUM(CASE WHEN rp.confidence = 'B' THEN 1 ELSE 0 END) / COUNT(*), 1) AS B_pct,
        ROUND(100.0 * SUM(CASE WHEN rp.confidence = 'C' THEN 1 ELSE 0 END) / COUNT(*), 1) AS C_pct,
        COUNT(DISTINCT rp.race_id) AS total_races,
        COUNT(DISTINCT CASE WHEN rp.confidence = 'A' THEN rp.race_id END) AS A_races
    FROM race_predictions rp
    JOIN races r ON rp.race_id = r.id
    {where_sql}
    GROUP BY year, rp.prediction_type
    ORDER BY year, rp.prediction_type
    """

    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def main():
    parser = argparse.ArgumentParser(
        description="信頼度分布チェック（2スケール混在問題 再発防止策D）"
    )
    parser.add_argument("--year", type=int, help="対象年度（省略時: 全年度）")
    parser.add_argument(
        "--type",
        dest="pred_type",
        choices=["advance", "before"],
        help="予測タイプ（省略時: 両方）",
    )
    parser.add_argument(
        "--alert-only", action="store_true", help="異常のある行のみ表示"
    )
    parser.add_argument("--db", default=str(DB_PATH), help="DBパス")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    rows = get_distribution(conn, year=args.year, pred_type=args.pred_type)
    conn.close()

    alerts = []
    warnings_list = []

    header = f"{'年度':<6} {'タイプ':<10} {'A%/予測':>8} {'B%/予測':>8} {'C%/予測':>8} {'A%/レース':>10} {'件数':>8} {'レース':>7} {'判定'}"
    separator = "-" * 90

    print("=" * 90)
    print("信頼度分布チェック（再発防止策D）")
    print("=" * 90)
    print(header)
    print(separator)

    for row in rows:
        (
            year, pred_type, total_pred,
            A_count, B_count, C_count,
            A_pct, B_pct, C_pct,
            total_races, A_races
        ) = row

        A_race_pct = round(100.0 * A_races / total_races, 1) if total_races > 0 else 0.0

        if pred_type not in NORMAL_RANGES:
            status = "?"
        else:
            ranges = NORMAL_RANGES[pred_type]

            if total_pred < ranges["min_samples"]:
                status = "SKIP(少)"
            elif A_pct > ranges["alert_threshold"]:
                status = "!!! ALERT"
                alerts.append({
                    "year": year,
                    "type": pred_type,
                    "A_pct": A_pct,
                    "A_race_pct": A_race_pct,
                    "total": total_pred,
                })
            elif A_pct < ranges["A_per_pred_min"]:
                status = "WARN(低)"
                warnings_list.append({
                    "year": year,
                    "type": pred_type,
                    "A_pct": A_pct,
                    "reason": f"A%/予測が正常下限({ranges['A_per_pred_min']}%)未満",
                })
            else:
                status = "OK"

        if args.alert_only and status in ("OK", "SKIP(少)"):
            continue

        print(
            f"{year:<6} {pred_type:<10} "
            f"{A_pct:>7.1f}%  {B_pct:>7.1f}%  {C_pct:>7.1f}%  "
            f"{A_race_pct:>9.1f}%  {total_pred:>7,}  {total_races:>6,}  {status}"
        )

    print("=" * 90)

    # 正常範囲の表示
    print("\n【正常範囲（新コード基準）】")
    print("  advance: A%/予測=2-5%、A%/レース=12-30%")
    print("  before:  A%/予測=2-9%、A%/レース=12-54%")
    print("  A%/予測 > 10% → 旧コード混入疑い（要再生成）")

    # アラート表示
    if alerts:
        print("\n" + "!" * 60)
        print("[!!! ALERT] 旧コード混入の疑いがある年度・タイプ:")
        for a in alerts:
            ranges = NORMAL_RANGES[a["type"]]
            print(
                f"  {a['year']} {a['type']}: A%/予測={a['A_pct']:.1f}%"
                f" (正常: {ranges['A_per_pred_min']}-{ranges['A_per_pred_max']}%)"
            )
        print("\n対応コマンド:")
        for a in alerts:
            script = "generate_advance_fast.py" if a["type"] == "advance" else "generate_before_fast.py"
            print(f"  python scripts/prediction/{script} --year {a['year']} --force")
        print("!" * 60)
        sys.exit(1)
    elif warnings_list:
        print("\n[WARN] 正常下限を下回っている年度・タイプ（要確認）:")
        for w in warnings_list:
            print(f"  {w['year']} {w['type']}: {w['reason']} (A%={w['A_pct']:.1f}%)")
        sys.exit(0)
    else:
        print("\n[OK] 全年度・全タイプで正常範囲内です")
        sys.exit(0)


if __name__ == "__main__":
    main()
