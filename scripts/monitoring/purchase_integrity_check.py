"""
購入整合性チェック - Task 5
修正後の運用が正しいことを継続確認するための監視スクリプト

チェック項目:
1. 直近購入の条件一致率（before値で再評価して95%+を維持しているか）
2. before不在スキップ件数
3. 条件別発火件数の累計（バックテストの年間ペース比）
4. 閾値逸脱時（一致率<95% / スキップ率>10%）はログに ALERT を出す

実行方法:
  python scripts/monitoring/purchase_integrity_check.py
  python scripts/monitoring/purchase_integrity_check.py --days 30  # 直近30日
  python scripts/monitoring/purchase_integrity_check.py --full-2026 # 2026年全体
"""
import sys
import os
import sqlite3
import argparse
from datetime import datetime, timedelta
from collections import defaultdict, Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DB_PATH = os.path.join(os.path.dirname(__file__), '../../data/boatrace.db')
SKIP_LOG = os.path.join(os.path.dirname(__file__), '../../logs/before_missing_skips.log')

try:
    from config.bet_conditions import STANDARD_BET_CONDITIONS
    ACTIVE_CONDITIONS = {c['id']: c for c in STANDARD_BET_CONDITIONS if c.get('active', True) is not False}
except ImportError:
    ACTIVE_CONDITIONS = {}

# バックテスト年間ペース（v2.65.0: 4906件/6年 = 817件/年）
BACKTEST_ANNUAL_RATE = {
    'A_B1_30_50_3VENUES': 23,
    'A_A1_30_50_4VENUES': 37,
    'B_A1_30_50_8VENUES': 67,
    'C_TSU_B1_30_50': 12,
    'C_B1_30_50_ASHIYA': 5,
    'C_A2_50_70_EDO_HAMA': 11,
    'D_B1_30_50_5VENUES': 13,
    'D_ST_CONTRAST_100_300': 62,
    'A_P142_125_300': 562,
    'C_P132_200_300': 435,
    'D_P143_200_300': 226,
    'C_P143_125_150': 151,
    'C_P132_150_175': 288,
    'C_P143_175_200': 552,
}


def check_condition_match(cond, conf, score):
    """before値が条件を通過するか"""
    if conf is None or score is None:
        return False
    cond_conf = cond.get('confidence')
    if cond_conf and conf != cond_conf:
        return False
    score_min = cond.get('score_min', -999)
    score_max = cond.get('score_max', 9999)
    if score < score_min or score >= score_max:
        return False
    return True


def run_check(days=14, full_2026=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 期間設定
    if full_2026:
        start_date = '2026-01-01'
        end_date = '2026-12-31'
        period_label = '2026年全体'
    else:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days)
        start_date = start_dt.strftime('%Y-%m-%d')
        end_date = end_dt.strftime('%Y-%m-%d')
        period_label = f'直近{days}日 ({start_date}〜{end_date})'

    # 期間内の購入を取得
    cur.execute("""
        SELECT
            bn.race_id, r.race_date, bn.condition_id, bn.odds_at_notification,
            bn.had_exhibition, bn.pred_type_used, bn.is_hit, bn.actual_payout
        FROM bet_notifications bn
        JOIN races r ON bn.race_id = r.id
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND bn.notification_type = 'confirmed'
        ORDER BY r.race_date
    """, (start_date, end_date))
    purchases = [dict(r) for r in cur.fetchall()]

    # before予測取得
    if purchases:
        race_ids = [p['race_id'] for p in purchases]
        placeholders = ','.join(['?'] * len(race_ids))
        cur.execute(f"""
            SELECT race_id, confidence, total_score
            FROM race_predictions
            WHERE race_id IN ({placeholders})
              AND prediction_type = 'before' AND rank_prediction = 1
        """, race_ids)
        bef_preds = {r['race_id']: {'conf': r['confidence'], 'score': r['total_score']} for r in cur.fetchall()}
    else:
        bef_preds = {}

    conn.close()

    # ============================================================
    # 1. 条件一致率チェック
    # ============================================================
    total = len(purchases)
    new_code_purchases = [p for p in purchases if p['had_exhibition'] is not None]
    old_code_purchases = [p for p in purchases if p['had_exhibition'] is None]

    match_count = 0
    mismatch_count = 0
    before_missing_count = 0
    unknown_cond_count = 0

    mismatch_details = []
    for p in new_code_purchases:
        race_id = p['race_id']
        cid = p['condition_id']
        cond = ACTIVE_CONDITIONS.get(cid) if cid else None
        bef = bef_preds.get(race_id, {})
        bef_conf = bef.get('conf')
        bef_score = bef.get('score')

        if not cond:
            unknown_cond_count += 1
            continue
        if bef_conf is None:
            before_missing_count += 1
            mismatch_details.append(f"  {race_id} {p['race_date']} [{cid}] before予測なし")
            mismatch_count += 1
            continue

        if check_condition_match(cond, bef_conf, bef_score):
            match_count += 1
        else:
            mismatch_count += 1
            reason = ""
            if cond.get('confidence') and bef_conf != cond['confidence']:
                reason = f"信頼度:{bef_conf}≠{cond['confidence']}"
            elif bef_score is not None:
                if bef_score < cond.get('score_min', -999):
                    reason = f"スコア下限:{bef_score:.1f}<{cond.get('score_min')}"
                elif bef_score >= cond.get('score_max', 9999):
                    reason = f"スコア上限:{bef_score:.1f}>={cond.get('score_max')}"
            score_str = f"{bef_score:.1f}" if bef_score is not None else "N/A"
            mismatch_details.append(f"  {race_id} {p['race_date']} [{cid}] bef:{bef_conf}/{score_str} 理由:{reason}")

    evaluable = match_count + mismatch_count
    match_rate = match_count / evaluable * 100 if evaluable > 0 else 0
    skip_rate = before_missing_count / total * 100 if total > 0 else 0

    # ============================================================
    # 2. before不在スキップ件数（ログファイルから）
    # ============================================================
    skip_log_count = 0
    if os.path.exists(SKIP_LOG):
        with open(SKIP_LOG, encoding='utf-8') as f:
            lines = [l for l in f if start_date <= l[:10] <= end_date]
            skip_log_count = len(lines)

    # ============================================================
    # 3. 条件別発火件数
    # ============================================================
    cond_counts = Counter()
    for p in purchases:
        cid = p['condition_id']
        if cid and cid in ACTIVE_CONDITIONS:
            cond_counts[cid] += 1

    # ============================================================
    # 出力
    # ============================================================
    alert = False
    print(f"\n{'='*60}")
    print(f"購入整合性チェック {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"期間: {period_label}")
    print(f"{'='*60}")
    print(f"\n【チェック1: 条件一致率（before値）】")
    print(f"  期間内購入: {total}件（新コード:{len(new_code_purchases)}件 旧コード:{len(old_code_purchases)}件）")
    print(f"  評価可能: {evaluable}件（未知条件:{unknown_cond_count}件除外）")
    print(f"  一致: {match_count}件 / 不一致: {mismatch_count}件（うちbefore未生成:{before_missing_count}件）")
    print(f"  一致率: {match_rate:.1f}%", end="")
    if match_rate < 95 and evaluable >= 10:
        print("  ← [ALERT] 95%未満!", end="")
        alert = True
    print()
    if mismatch_details and len(mismatch_details) <= 20:
        print("  不一致詳細:")
        for d in mismatch_details:
            print(d)

    print(f"\n【チェック2: before不在スキップ（ログ）】")
    print(f"  スキップ件数（ログ）: {skip_log_count}件")
    print(f"  スキップ率: {skip_rate:.1f}%", end="")
    if skip_rate > 10:
        print("  ← [ALERT] 10%超過!", end="")
        alert = True
    print()

    print(f"\n【チェック3: 条件別発火件数（バックテストペース比）】")
    total_days = (datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days or 1
    year_fraction = total_days / 365
    for cid in sorted(BACKTEST_ANNUAL_RATE.keys()):
        actual = cond_counts.get(cid, 0)
        expected = BACKTEST_ANNUAL_RATE.get(cid, 0) * year_fraction
        ratio = actual / expected if expected > 0 else 0
        flag = ""
        if actual > 0 and (ratio < 0.3 or ratio > 3.0):
            flag = " ← [注意]"
        print(f"  {cid:<35} 実績:{actual:3d}件 期待:{expected:5.1f}件 比率:{ratio:.2f}{flag}")

    print(f"\n【総合判定】")
    if alert:
        print("  [ALERT] 閾値逸脱あり。詳細を確認してください。")
    else:
        print("  [OK] 異常なし")

    print(f"{'='*60}\n")
    return not alert


def main():
    parser = argparse.ArgumentParser(description='購入整合性チェック')
    parser.add_argument('--days', type=int, default=14, help='直近N日（デフォルト:14）')
    parser.add_argument('--full-2026', action='store_true', help='2026年全体をチェック')
    args = parser.parse_args()
    ok = run_check(days=args.days, full_2026=args.full_2026)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
