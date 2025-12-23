# -*- coding: utf-8 -*-
"""Tier 3オッズ範囲拡張のバックテスト

現状: D × B1 × 5-10倍
提案: D × B1 × 5-15倍

目標:
- 月間的中数の向上（3-5回 → 5-7回）
- ROI 110%維持
- 年間収支の向上
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def run_backtest(db_path, odds_min=5, odds_max=15, bet_amount=300):
    """
    Tier 3バックテスト実行

    Args:
        db_path: データベースパス
        odds_min: 最小オッズ
        odds_max: 最大オッズ
        bet_amount: 賭け金（1買い目あたり）

    Returns:
        結果辞書
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print(f"\n{'='*100}")
    print(f"Tier 3バックテスト: オッズ範囲 {odds_min}-{odds_max}倍")
    print(f"{'='*100}\n")

    # 対象レースを取得（2025年全期間）
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    stats = {
        'total': 0,
        'target': 0,
        'hit': 0,
        'bet': 0,
        'payout': 0,
        'by_month': {}
    }

    for race in races:
        race_id = race['race_id']
        month = race['race_date'][:7]  # YYYY-MM

        if month not in stats['by_month']:
            stats['by_month'][month] = {
                'target': 0, 'hit': 0, 'bet': 0, 'payout': 0
            }

        # 1コース級別
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # B1以外は対象外
        if c1_rank != 'B1':
            continue

        # 予測情報（信頼度D）
        cursor.execute('''
            SELECT pit_number, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        stats['total'] += 1

        confidence = preds[0]['confidence']

        # 信頼度D以外は対象外
        if confidence != 'D':
            continue

        # 予測トップ3
        top3 = [p['pit_number'] for p in preds[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

        # オッズ取得
        cursor.execute('SELECT combination, odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                       (race_id, combo))
        odds_row = cursor.fetchone()

        if not odds_row:
            continue

        odds = odds_row['odds']

        # オッズ範囲チェック
        if not (odds_min <= odds < odds_max):
            continue

        # ★購入対象★
        stats['target'] += 1
        stats['bet'] += bet_amount
        stats['by_month'][month]['target'] += 1
        stats['by_month'][month]['bet'] += bet_amount

        # 実際の結果
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

            if combo == actual_combo:
                # 的中
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    # 払戻金は100円あたりなので、実際の賭け金に応じて計算
                    actual_payout = (bet_amount / 100) * payout_row['amount']
                    stats['hit'] += 1
                    stats['payout'] += actual_payout
                    stats['by_month'][month]['hit'] += 1
                    stats['by_month'][month]['payout'] += actual_payout

    conn.close()

    # 結果集計
    purchase_count = stats['target']
    hit_count = stats['hit']
    hit_rate = (hit_count / purchase_count * 100) if purchase_count > 0 else 0
    total_investment = stats['bet']
    total_return = stats['payout']
    roi = (total_return / total_investment * 100) if total_investment > 0 else 0
    profit = total_return - total_investment

    # 月間平均
    month_count = len([m for m in stats['by_month'].values() if m['target'] > 0])
    avg_monthly_purchase = purchase_count / month_count if month_count > 0 else 0
    avg_monthly_hit = hit_count / month_count if month_count > 0 else 0

    # 結果表示
    print(f"対象レース数: {stats['total']}レース（信頼度D × 1コースB1）\n")
    print(f"{'='*100}")
    print(f"全体サマリー")
    print(f"{'='*100}\n")
    print(f"購入レース数: {purchase_count}レース")
    print(f"的中数: {hit_count}回")
    print(f"的中率: {hit_rate:.1f}%")
    print(f"総投資額: {total_investment:,.0f}円")
    print(f"総払戻額: {total_return:,.0f}円")
    print(f"**収支**: {profit:+,.0f}円")
    print(f"**ROI**: {roi:.1f}%")
    print(f"\n月間平均:")
    print(f"  購入: {avg_monthly_purchase:.1f}レース/月")
    print(f"  的中: {avg_monthly_hit:.1f}回/月")

    # 月別詳細
    print(f"\n{'='*100}")
    print(f"月別集計")
    print(f"{'='*100}\n")
    print(f"{'月':<10} {'購入':<8} {'的中':<8} {'的中率':<10} {'投資額':<12} {'払戻額':<12} {'収支':<12} {'ROI':<10}")
    print('-' * 100)

    for month in sorted(stats['by_month'].keys()):
        mstats = stats['by_month'][month]
        if mstats['target'] == 0:
            continue

        month_purchase = mstats['target']
        month_hit = mstats['hit']
        month_hit_rate = (month_hit / month_purchase * 100) if month_purchase > 0 else 0
        month_investment = mstats['bet']
        month_return = mstats['payout']
        month_profit = month_return - month_investment
        month_roi = (month_return / month_investment * 100) if month_investment > 0 else 0

        print(f"{month:<10} {month_purchase:<8} {month_hit:<8} {month_hit_rate:>6.1f}% "
              f"{month_investment:>10,.0f}円 {month_return:>10,.0f}円 "
              f"{month_profit:>+10,.0f}円 {month_roi:>8.1f}%")

    print(f"\n{'='*100}\n")

    return {
        'purchase_count': purchase_count,
        'hit_count': hit_count,
        'hit_rate': hit_rate,
        'total_investment': total_investment,
        'total_return': total_return,
        'profit': profit,
        'roi': roi,
        'avg_monthly_purchase': avg_monthly_purchase,
        'avg_monthly_hit': avg_monthly_hit,
        'monthly_stats': stats['by_month']
    }


def main():
    """メイン処理"""
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print(f"\n{'='*100}")
    print(f"Tier 3オッズ範囲拡張バックテスト")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*100}")

    # ベースライン（現状）: 5-10倍
    print(f"\n## ベースライン（現状）: 5-10倍\n")
    baseline = run_backtest(db_path, odds_min=5, odds_max=10)

    # 提案: 5-15倍
    print(f"\n## 提案: 5-15倍\n")
    expanded = run_backtest(db_path, odds_min=5, odds_max=15)

    # 比較
    if baseline and expanded:
        print(f"\n{'='*100}")
        print(f"比較結果")
        print(f"{'='*100}\n")
        print(f"{'項目':<20} {'現状(5-10倍)':<20} {'提案(5-15倍)':<20} {'差分':<20}")
        print('-' * 100)

        purchase_diff = expanded['purchase_count'] - baseline['purchase_count']
        hit_diff = expanded['hit_count'] - baseline['hit_count']
        hit_rate_diff = expanded['hit_rate'] - baseline['hit_rate']
        profit_diff = expanded['profit'] - baseline['profit']
        roi_diff = expanded['roi'] - baseline['roi']
        monthly_purchase_diff = expanded['avg_monthly_purchase'] - baseline['avg_monthly_purchase']
        monthly_hit_diff = expanded['avg_monthly_hit'] - baseline['avg_monthly_hit']

        print(f"{'購入レース数':<20} {baseline['purchase_count']:<20} {expanded['purchase_count']:<20} {purchase_diff:+}")
        print(f"{'的中数':<20} {baseline['hit_count']:<20} {expanded['hit_count']:<20} {hit_diff:+}")
        print(f"{'的中率':<20} {baseline['hit_rate']:<18.1f}% {expanded['hit_rate']:<18.1f}% {hit_rate_diff:+.1f}%")
        print(f"{'年間収支':<20} {baseline['profit']:<18,.0f}円 {expanded['profit']:<18,.0f}円 {profit_diff:+,.0f}円")
        print(f"{'ROI':<20} {baseline['roi']:<18.1f}% {expanded['roi']:<18.1f}% {roi_diff:+.1f}%")
        print(f"{'月間購入平均':<20} {baseline['avg_monthly_purchase']:<18.1f} {expanded['avg_monthly_purchase']:<18.1f} {monthly_purchase_diff:+.1f}")
        print(f"{'月間的中平均':<20} {baseline['avg_monthly_hit']:<18.1f} {expanded['avg_monthly_hit']:<18.1f} {monthly_hit_diff:+.1f}")

        print(f"\n{'='*100}")
        print(f"判定")
        print(f"{'='*100}\n")

        # 判定基準
        roi_ok = expanded['roi'] >= 100  # ROI 100%以上維持
        hit_increase = monthly_hit_diff >= 1.5  # 月間的中+1.5回以上
        profit_ok = profit_diff >= 0  # 収支プラス

        print(f"[OK/NG] ROI維持（100%以上）: {expanded['roi']:.1f}% {'OK' if roi_ok else 'NG'}")
        print(f"[OK/NG] 月間的中増加（+1.5回以上）: {monthly_hit_diff:+.1f}回 {'OK' if hit_increase else 'NG'}")
        print(f"[OK/NG] 収支改善: {profit_diff:+,.0f}円 {'OK' if profit_ok else 'NG'}")

        if roi_ok and hit_increase and profit_ok:
            print(f"\n【判定: 採用推奨】")
            print(f"   オッズ範囲を5-15倍に拡張することで、月間的中数が向上し、")
            print(f"   ROIも維持されるため、Tier 3の安定性が向上します。")
        elif roi_ok and profit_ok:
            print(f"\n【判定: 条件付き採用】")
            print(f"   ROIと収支は維持されますが、月間的中数の増加が限定的です。")
            print(f"   より広範なオッズ範囲（5-20倍など）も検討価値があります。")
        else:
            print(f"\n【判定: 不採用】")
            print(f"   ROIまたは収支が悪化するため、現状維持を推奨します。")

        print(f"\n{'='*100}\n")


if __name__ == "__main__":
    main()
