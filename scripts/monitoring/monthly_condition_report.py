"""
月次条件別成績レポート

bet_notifications / shadow_bets から条件別・月次成績と
shadow組み合わせ別的中率・見送り擬似ROIを集計して表示する。

Usage:
    python scripts/monitoring/monthly_condition_report.py
    python scripts/monitoring/monthly_condition_report.py --months 6
    python scripts/monitoring/monthly_condition_report.py --since 2026-04-01
"""
import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

DB_PATH = project_root / "data" / "boatrace.db"


def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# B-1: 条件別月次成績
# ---------------------------------------------------------------------------

def get_condition_monthly_stats(
    db_path: str,
    since_date: Optional[str] = None,
    months: int = 3,
) -> List[Dict]:
    """
    bet_notifications から条件別 × 月次成績を返す（reconcile済みのみ）。
    since_date が指定された場合はその日以降を集計。
    """
    conn = _get_conn(db_path)
    try:
        cur = conn.cursor()
        # テーブル存在確認
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bet_notifications'")
        if not cur.fetchone():
            return []

        if since_date:
            where_date = "AND DATE(bn.notified_at) >= ?"
            date_params: tuple = (since_date,)
        else:
            where_date = f"AND DATE(bn.notified_at) >= DATE('now', 'localtime', '-{months} months')"
            date_params = ()

        cur.execute(f"""
            SELECT
                bn.condition_id,
                strftime('%Y-%m', bn.notified_at) AS month,
                COUNT(*) AS total,
                SUM(CASE WHEN bn.is_hit = 1 THEN 1 ELSE 0 END) AS hits,
                SUM(COALESCE(bn.bet_amount, 100)) AS total_bet,
                SUM(CASE WHEN bn.is_hit = 1 THEN COALESCE(bn.actual_payout, 0) ELSE 0 END) AS total_return
            FROM bet_notifications bn
            WHERE bn.notification_type = 'confirmed'
              AND bn.is_hit IS NOT NULL
              {where_date}
            GROUP BY bn.condition_id, month
            ORDER BY month DESC, total DESC
        """, date_params)
        rows = []
        for r in cur.fetchall():
            cid = r['condition_id'] or '?'
            total_bet = r['total_bet'] or 0
            total_return = r['total_return'] or 0
            roi = (total_return / total_bet * 100) if total_bet > 0 else 0
            rows.append({
                'condition_id': cid,
                'month': r['month'],
                'total': r['total'],
                'hits': r['hits'] or 0,
                'hit_rate': (r['hits'] or 0) / r['total'] * 100 if r['total'] > 0 else 0,
                'total_bet': total_bet,
                'total_return': total_return,
                'profit': total_return - total_bet,
                'roi': roi,
            })
        return rows
    finally:
        conn.close()


def get_condition_totals(db_path: str, since_date: Optional[str] = None, months: int = 3) -> List[Dict]:
    """条件別累計（月まとめなし）"""
    conn = _get_conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bet_notifications'")
        if not cur.fetchone():
            return []

        if since_date:
            where_date = "AND DATE(bn.notified_at) >= ?"
            date_params: tuple = (since_date,)
        else:
            where_date = f"AND DATE(bn.notified_at) >= DATE('now', 'localtime', '-{months} months')"
            date_params = ()

        cur.execute(f"""
            SELECT
                bn.condition_id,
                COUNT(*) AS total,
                SUM(CASE WHEN bn.is_hit = 1 THEN 1 ELSE 0 END) AS hits,
                SUM(COALESCE(bn.bet_amount, 100)) AS total_bet,
                SUM(CASE WHEN bn.is_hit = 1 THEN COALESCE(bn.actual_payout, 0) ELSE 0 END) AS total_return
            FROM bet_notifications bn
            WHERE bn.notification_type = 'confirmed'
              AND bn.is_hit IS NOT NULL
              {where_date}
            GROUP BY bn.condition_id
            ORDER BY total DESC
        """, date_params)
        rows = []
        for r in cur.fetchall():
            cid = r['condition_id'] or '?'
            total_bet = r['total_bet'] or 0
            total_return = r['total_return'] or 0
            roi = (total_return / total_bet * 100) if total_bet > 0 else 0
            rows.append({
                'condition_id': cid,
                'total': r['total'],
                'hits': r['hits'] or 0,
                'hit_rate': (r['hits'] or 0) / r['total'] * 100 if r['total'] > 0 else 0,
                'total_bet': total_bet,
                'total_return': total_return,
                'profit': total_return - total_bet,
                'roi': roi,
            })
        return rows
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# B-2: shadow 組み合わせ別的中率・見送り擬似ROI
# ---------------------------------------------------------------------------

def get_shadow_combo_stats(db_path: str, since_date: Optional[str] = None, months: int = 3) -> Dict:
    """
    shadow_bets から組み合わせ別的中率と見送り擬似ROIを集計。

    Returns:
        {
            'confirmed': [{'combo_prefix', 'total', 'hits', 'hit_rate', 'avg_odds', 'pseudo_roi'}, ...],
            'dismissed': [{'combo_prefix', 'total', 'hits', 'hit_rate', 'avg_odds', 'pseudo_roi'}, ...],
            'confirmed_summary': {'total', 'hits', 'pseudo_profit'},
            'dismissed_summary': {'total', 'hits', 'pseudo_profit'},
        }
    """
    conn = _get_conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shadow_bets'")
        if not cur.fetchone():
            return {'confirmed': [], 'dismissed': [], 'confirmed_summary': {}, 'dismissed_summary': {}}

        if since_date:
            where_date = "AND DATE(sb.created_at) >= ?"
            date_params: tuple = (since_date,)
        else:
            where_date = f"AND DATE(sb.created_at) >= DATE('now', 'localtime', '-{months} months')"
            date_params = ()

        # shadow_bets は複数の組み合わせを combinations に格納している（カンマ区切り）
        # hit_combination が NULL でない → 的中
        # reconciled_at IS NOT NULL: 未照合分（当日など）は除外して偽の損失を防ぐ
        cur.execute(f"""
            SELECT
                COALESCE(sb.notification_type, 'confirmed') AS ntype,
                sb.race_id,
                sb.combinations,
                sb.hit_combination,
                sb.odds_if_hit
            FROM shadow_bets sb
            WHERE sb.reconciled_at IS NOT NULL {where_date}
        """, date_params)
        rows = cur.fetchall()

        result: Dict[str, Dict[str, Dict]] = {'confirmed': {}, 'dismissed': {}}
        summaries: Dict[str, Dict] = {
            'confirmed': {'total_bets': 0, 'hits': 0, 'pseudo_profit': 0},
            'dismissed': {'total_bets': 0, 'hits': 0, 'pseudo_profit': 0},
        }

        for row in rows:
            ntype = row['ntype'] if row['ntype'] in ('confirmed', 'dismissed') else 'confirmed'
            combos = [c.strip() for c in (row['combinations'] or '').split(',') if c.strip()]
            is_hit = row['hit_combination'] is not None
            odds = row['odds_if_hit'] or 0.0

            for combo in combos:
                parts = combo.split('-')
                prefix = parts[0] if parts else '?'

                group = result[ntype]
                if prefix not in group:
                    group[prefix] = {'total': 0, 'hits': 0, 'odds_sum': 0.0, 'pseudo_profit': 0}

                group[prefix]['total'] += 1
                summaries[ntype]['total_bets'] += 1

                if is_hit and combo == row['hit_combination']:
                    group[prefix]['hits'] += 1
                    if odds > 0:
                        group[prefix]['odds_sum'] += odds
                        group[prefix]['pseudo_profit'] += int(odds * 100) - 100
                        summaries[ntype]['pseudo_profit'] += int(odds * 100) - 100
                    else:
                        # odds未取得ヒット: 収支はミスと同等（-100）として警告
                        print(f"  [WARN] shadow hit but odds_if_hit=NULL: race_id={row.get('race_id', '?')}")
                        group[prefix]['pseudo_profit'] -= 100
                        summaries[ntype]['pseudo_profit'] -= 100
                    summaries[ntype]['hits'] += 1
                else:
                    group[prefix]['pseudo_profit'] -= 100
                    summaries[ntype]['pseudo_profit'] -= 100

        def _format_group(group_dict: Dict) -> List[Dict]:
            out = []
            for prefix, d in sorted(group_dict.items(), key=lambda x: -x[1]['total']):
                avg_odds = (d['odds_sum'] / d['hits']) if d['hits'] > 0 else 0.0
                total_bet = d['total'] * 100
                total_return = d['pseudo_profit'] + total_bet
                roi = (total_return / total_bet * 100) if total_bet > 0 else 0
                out.append({
                    'combo_prefix': f"{prefix}コース軸",
                    'total': d['total'],
                    'hits': d['hits'],
                    'hit_rate': d['hits'] / d['total'] * 100 if d['total'] > 0 else 0,
                    'avg_odds': avg_odds,
                    'pseudo_profit': d['pseudo_profit'],
                    'roi': roi,
                })
            return out

        def _fmt_summary(s: Dict) -> Dict:
            total_bet = s['total_bets'] * 100
            total_return = s['pseudo_profit'] + total_bet
            roi = (total_return / total_bet * 100) if total_bet > 0 else 0
            return {
                'total': s['total_bets'],
                'hits': s['hits'],
                'hit_rate': s['hits'] / s['total_bets'] * 100 if s['total_bets'] > 0 else 0,
                'pseudo_profit': s['pseudo_profit'],
                'roi': roi,
            }

        return {
            'confirmed': _format_group(result['confirmed']),
            'dismissed': _format_group(result['dismissed']),
            'confirmed_summary': _fmt_summary(summaries['confirmed']),
            'dismissed_summary': _fmt_summary(summaries['dismissed']),
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# レポート表示
# ---------------------------------------------------------------------------

def print_report(db_path: str, months: int = 3, since_date: Optional[str] = None) -> None:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    label = f"直近{months}ヶ月" if not since_date else f"{since_date}以降"
    print(f"\n{'='*60}")
    print(f"  月次条件別成績レポート ({label})")
    print(f"{'='*60}\n")

    # B-1: 条件別累計
    totals = get_condition_totals(db_path, since_date=since_date, months=months)
    if not totals:
        print("【条件別累計】reconcile済みデータなし\n")
    else:
        print("【条件別累計】")
        print(f"{'条件ID':<36} {'件数':>5} {'的中':>5} {'的中率':>7} {'収支':>10} {'ROI':>8}")
        print('-' * 73)
        for r in totals:
            cid = r['condition_id'][:34]
            sign = '+' if r['profit'] >= 0 else ''
            print(f"{cid:<36} {r['total']:>5} {r['hits']:>5} {r['hit_rate']:>6.1f}%"
                  f" {sign}{r['profit']:>9,}  {r['roi']:>6.1f}%")
        print()

    # B-1: 条件別月次ブレークダウン
    monthly = get_condition_monthly_stats(db_path, since_date=since_date, months=months)
    if monthly:
        print("【条件別 × 月次ブレークダウン】")
        print(f"{'条件ID':<36} {'月':>8} {'件数':>5} {'的中':>5} {'的中率':>7} {'収支':>10}")
        print('-' * 73)
        for r in monthly:
            cid = r['condition_id'][:34]
            sign = '+' if r['profit'] >= 0 else ''
            print(f"{cid:<36} {r['month']:>8} {r['total']:>5} {r['hits']:>5}"
                  f" {r['hit_rate']:>6.1f}% {sign}{r['profit']:>9,}")
        print()

    # B-2: shadow stats
    shadow = get_shadow_combo_stats(db_path, since_date=since_date, months=months)

    confirmed_shadow = shadow.get('confirmed', [])
    dismissed_shadow = shadow.get('dismissed', [])
    cs = shadow.get('confirmed_summary', {})
    ds = shadow.get('dismissed_summary', {})

    def _print_shadow_section(title: str, rows: List[Dict], summary: Dict) -> None:
        if not rows and not summary.get('total'):
            print(f"【{title}】データなし\n")
            return
        print(f"【{title}】")
        if summary.get('total', 0) > 0:
            sign = '+' if summary.get('pseudo_profit', 0) >= 0 else ''
            print(f"  総計: {summary['total']}点追跡 / {summary['hits']}点的中"
                  f" ({summary['hit_rate']:.1f}%) / 擬似収支{sign}{summary['pseudo_profit']:,}円"
                  f" (ROI {summary['roi']:.1f}%)")
        print(f"  {'軸コース':<12} {'追跡点':>6} {'的中':>5} {'的中率':>7} {'平均倍率':>8} {'擬似ROI':>8}")
        print('  ' + '-' * 52)
        for r in rows:
            avg = f"{r['avg_odds']:.1f}倍" if r['avg_odds'] > 0 else '-'
            print(f"  {r['combo_prefix']:<12} {r['total']:>6} {r['hits']:>5}"
                  f" {r['hit_rate']:>6.1f}% {avg:>8} {r['roi']:>7.1f}%")
        print()

    _print_shadow_section("shadow購入分（的中率・擬似ROI）", confirmed_shadow, cs)
    _print_shadow_section("shadow見送り分（見逃し機会コスト）", dismissed_shadow, ds)


def main() -> None:
    import re
    parser = argparse.ArgumentParser(description='月次条件別成績レポート')
    parser.add_argument('--months', type=int, default=3, help='集計月数（デフォルト: 3）')
    parser.add_argument('--since', type=str, default=None, help='集計開始日 (YYYY-MM-DD)')
    parser.add_argument('--db', type=str, default=str(DB_PATH), help='DBパス')
    args = parser.parse_args()

    if args.since and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', args.since):
        print(f"[ERROR] --since の形式が不正です: '{args.since}' (YYYY-MM-DD 形式で指定してください)")
        sys.exit(1)

    print_report(db_path=args.db, months=args.months, since_date=args.since)


if __name__ == '__main__':
    main()
