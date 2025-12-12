# -*- coding: utf-8 -*-
"""標準バックテストスクリプト（3連単完全一致方式）

このスクリプトは以下の仕様に従います:
- bet_target_evaluator.pyのBET_CONDITIONS自動読み込み
- 3連単完全一致方式（予測と実際の着順が完全一致した場合のみ払戻）
- prediction_type = 'before'（直前情報）を使用
- 月別、Tier別、条件別の詳細レポート生成
- 全ての戦略バックテストの標準テンプレート
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def run_backtest(
    db_path,
    start_date='2025-01-01',
    end_date='2025-12-31',
    prediction_type='before',
    use_both_methods=True
):
    """
    標準バックテスト実行

    Args:
        db_path: データベースパス
        start_date: 開始日（YYYY-MM-DD）
        end_date: 終了日（YYYY-MM-DD）
        prediction_type: 予測タイプ（'before' or 'advance'）
        use_both_methods: 両方式対応（旧新両方チェック）

    Returns:
        結果辞書
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print(f"\n{'='*100}")
    print(f"標準バックテスト実行")
    print(f"期間: {start_date} ～ {end_date}")
    print(f"予測タイプ: {prediction_type}")
    print(f"{'='*100}\n")

    # BetTargetEvaluatorインスタンス作成
    evaluator = BetTargetEvaluator()

    # 全BET_CONDITIONSを取得
    all_conditions = []
    for confidence in ['C', 'D']:
        if confidence in BetTargetEvaluator.BET_CONDITIONS:
            for cond in BetTargetEvaluator.BET_CONDITIONS[confidence]:
                all_conditions.append({
                    'confidence': confidence,
                    **cond
                })

    print(f"読み込んだ購入条件: {len(all_conditions)}件\n")
    for i, cond in enumerate(all_conditions, 1):
        print(f"  {i}. {cond['confidence']} × {cond.get('description', 'N/A')}")
        print(f"     オッズ: {cond['odds_min']}-{cond['odds_max']}倍, "
              f"1コース級別: {cond.get('c1_rank', [])}, "
              f"賭け金: {cond['bet_amount']}円")
    print()

    # 対象レース取得
    cursor.execute(f'''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= ? AND r.race_date <= ?
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (start_date, end_date))
    races = cursor.fetchall()

    print(f"対象レース数: {len(races)}レース\n")
    print(f"{'='*100}\n")

    # 統計データ構造
    stats = {
        'total_races': len(races),
        'total_target': 0,
        'total_hit': 0,
        'total_bet': 0,
        'total_payout': 0,
        'by_month': defaultdict(lambda: {
            'target': 0, 'hit': 0, 'bet': 0, 'payout': 0
        }),
        'by_confidence': defaultdict(lambda: {
            'target': 0, 'hit': 0, 'bet': 0, 'payout': 0
        }),
        'by_tier': defaultdict(lambda: {
            'target': 0, 'hit': 0, 'bet': 0, 'payout': 0
        }),
        'by_condition': defaultdict(lambda: {
            'target': 0, 'hit': 0, 'bet': 0, 'payout': 0,
            'description': ''
        })
    }

    # レース単位でループ
    for race in races:
        race_id = race['race_id']
        venue_code = race['venue_code']
        race_date = race['race_date']
        month = race_date[:7]  # YYYY-MM

        # 1コース級別取得
        cursor.execute(
            'SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1',
            (race_id,)
        )
        c1_row = cursor.fetchone()
        c1_rank = c1_row['racer_rank'] if c1_row else 'B1'

        # 予測情報取得
        cursor.execute('''
            SELECT pit_number, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = ?
            ORDER BY rank_prediction
        ''', (race_id, prediction_type))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']

        # 信頼度A/Bは除外
        if confidence in ['A', 'B']:
            continue

        # 予測トップ3
        top3 = [p['pit_number'] for p in preds[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"

        # オッズ取得
        cursor.execute(
            'SELECT combination, odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
            (race_id, combo)
        )
        odds_row = cursor.fetchone()

        if not odds_row:
            continue

        odds = odds_row['odds']

        # bet_target_evaluatorで購入判定
        result = evaluator.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=combo,
            new_combo=combo,
            old_odds=odds,
            new_odds=odds,
            has_beforeinfo=(prediction_type == 'before'),
            venue_code=venue_code
        )

        # 購入対象かチェック
        if result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            continue

        # ★購入対象★
        bet_amount = result.bet_amount
        condition_key = f"{confidence}×{c1_rank}×{result.odds_range}"
        tier = extract_tier(result.reason)

        stats['total_target'] += 1
        stats['total_bet'] += bet_amount
        stats['by_month'][month]['target'] += 1
        stats['by_month'][month]['bet'] += bet_amount
        stats['by_confidence'][confidence]['target'] += 1
        stats['by_confidence'][confidence]['bet'] += bet_amount
        stats['by_tier'][tier]['target'] += 1
        stats['by_tier'][tier]['bet'] += bet_amount
        stats['by_condition'][condition_key]['target'] += 1
        stats['by_condition'][condition_key]['bet'] += bet_amount
        stats['by_condition'][condition_key]['description'] = result.reason

        # 実際の結果取得（3連単完全一致チェック）
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) >= 3:
            actual_combo = f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"

            # 3連単完全一致の場合のみ的中
            if combo == actual_combo:
                # 払戻金取得
                cursor.execute('''
                    SELECT amount FROM payouts
                    WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                ''', (race_id, actual_combo))
                payout_row = cursor.fetchone()

                if payout_row:
                    # 払戻金は100円あたりなので、実際の賭け金に応じて計算
                    actual_payout = (bet_amount / 100) * payout_row['amount']

                    stats['total_hit'] += 1
                    stats['total_payout'] += actual_payout
                    stats['by_month'][month]['hit'] += 1
                    stats['by_month'][month]['payout'] += actual_payout
                    stats['by_confidence'][confidence]['hit'] += 1
                    stats['by_confidence'][confidence]['payout'] += actual_payout
                    stats['by_tier'][tier]['hit'] += 1
                    stats['by_tier'][tier]['payout'] += actual_payout
                    stats['by_condition'][condition_key]['hit'] += 1
                    stats['by_condition'][condition_key]['payout'] += actual_payout

    conn.close()

    # 結果表示
    print_results(stats, start_date, end_date)

    return stats


def extract_tier(description):
    """条件説明からTier番号を抽出"""
    if 'Tier1' in description:
        return 'Tier1'
    elif 'Tier2' in description:
        return 'Tier2'
    elif 'Tier3' in description:
        return 'Tier3'
    else:
        return 'その他'


def print_results(stats, start_date, end_date):
    """結果レポート表示"""
    print(f"\n{'='*100}")
    print(f"全体サマリー")
    print(f"{'='*100}\n")

    purchase_count = stats['total_target']
    hit_count = stats['total_hit']
    hit_rate = (hit_count / purchase_count * 100) if purchase_count > 0 else 0
    total_investment = stats['total_bet']
    total_return = stats['total_payout']
    roi = (total_return / total_investment * 100) if total_investment > 0 else 0
    profit = total_return - total_investment

    print(f"対象レース数: {stats['total_races']}レース")
    print(f"購入レース数: {purchase_count}レース")
    print(f"的中数: {hit_count}回")
    print(f"的中率: {hit_rate:.1f}%")
    print(f"総投資額: {total_investment:,.0f}円")
    print(f"総払戻額: {total_return:,.0f}円")
    print(f"**収支**: {profit:+,.0f}円")
    print(f"**ROI**: {roi:.1f}%")

    # 月別詳細
    print(f"\n{'='*100}")
    print(f"月別集計")
    print(f"{'='*100}\n")
    print(f"{'月':<12} {'購入':<8} {'的中':<8} {'的中率':<10} {'投資額':<14} {'払戻額':<14} {'収支':<14} {'ROI':<10}")
    print('-' * 100)

    for month in sorted(stats['by_month'].keys()):
        mstats = stats['by_month'][month]
        if mstats['target'] == 0:
            continue

        m_purchase = mstats['target']
        m_hit = mstats['hit']
        m_hit_rate = (m_hit / m_purchase * 100) if m_purchase > 0 else 0
        m_investment = mstats['bet']
        m_return = mstats['payout']
        m_profit = m_return - m_investment
        m_roi = (m_return / m_investment * 100) if m_investment > 0 else 0

        print(f"{month:<12} {m_purchase:<8} {m_hit:<8} {m_hit_rate:>6.1f}% "
              f"{m_investment:>12,.0f}円 {m_return:>12,.0f}円 "
              f"{m_profit:>+12,.0f}円 {m_roi:>8.1f}%")

    # 信頼度別集計
    print(f"\n{'='*100}")
    print(f"信頼度別集計")
    print(f"{'='*100}\n")
    print(f"{'信頼度':<10} {'購入':<8} {'的中':<8} {'的中率':<10} {'投資額':<14} {'払戻額':<14} {'収支':<14} {'ROI':<10}")
    print('-' * 100)

    for confidence in sorted(stats['by_confidence'].keys()):
        cstats = stats['by_confidence'][confidence]
        if cstats['target'] == 0:
            continue

        c_purchase = cstats['target']
        c_hit = cstats['hit']
        c_hit_rate = (c_hit / c_purchase * 100) if c_purchase > 0 else 0
        c_investment = cstats['bet']
        c_return = cstats['payout']
        c_profit = c_return - c_investment
        c_roi = (c_return / c_investment * 100) if c_investment > 0 else 0

        print(f"{confidence:<10} {c_purchase:<8} {c_hit:<8} {c_hit_rate:>6.1f}% "
              f"{c_investment:>12,.0f}円 {c_return:>12,.0f}円 "
              f"{c_profit:>+12,.0f}円 {c_roi:>8.1f}%")

    # Tier別集計
    print(f"\n{'='*100}")
    print(f"Tier別集計")
    print(f"{'='*100}\n")
    print(f"{'Tier':<12} {'購入':<8} {'的中':<8} {'的中率':<10} {'投資額':<14} {'払戻額':<14} {'収支':<14} {'ROI':<10}")
    print('-' * 100)

    for tier in ['Tier1', 'Tier2', 'Tier3', 'その他']:
        if tier not in stats['by_tier']:
            continue
        tstats = stats['by_tier'][tier]
        if tstats['target'] == 0:
            continue

        t_purchase = tstats['target']
        t_hit = tstats['hit']
        t_hit_rate = (t_hit / t_purchase * 100) if t_purchase > 0 else 0
        t_investment = tstats['bet']
        t_return = tstats['payout']
        t_profit = t_return - t_investment
        t_roi = (t_return / t_investment * 100) if t_investment > 0 else 0

        print(f"{tier:<12} {t_purchase:<8} {t_hit:<8} {t_hit_rate:>6.1f}% "
              f"{t_investment:>12,.0f}円 {t_return:>12,.0f}円 "
              f"{t_profit:>+12,.0f}円 {t_roi:>8.1f}%")

    # 条件別詳細
    print(f"\n{'='*100}")
    print(f"条件別詳細")
    print(f"{'='*100}\n")
    print(f"{'条件':<30} {'説明':<30} {'購入':<8} {'的中':<8} {'的中率':<10} {'ROI':<10} {'収支':<14}")
    print('-' * 100)

    for condition_key in sorted(stats['by_condition'].keys()):
        cond_stats = stats['by_condition'][condition_key]
        if cond_stats['target'] == 0:
            continue

        cond_purchase = cond_stats['target']
        cond_hit = cond_stats['hit']
        cond_hit_rate = (cond_hit / cond_purchase * 100) if cond_purchase > 0 else 0
        cond_investment = cond_stats['bet']
        cond_return = cond_stats['payout']
        cond_profit = cond_return - cond_investment
        cond_roi = (cond_return / cond_investment * 100) if cond_investment > 0 else 0
        cond_desc = cond_stats['description'][:28]

        print(f"{condition_key:<30} {cond_desc:<30} {cond_purchase:<8} {cond_hit:<8} "
              f"{cond_hit_rate:>6.1f}% {cond_roi:>8.1f}% {cond_profit:>+12,.0f}円")

    print(f"\n{'='*100}\n")


def main():
    """メイン処理"""
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print(f"\n{'='*100}")
    print(f"標準バックテストスクリプト（3連単完全一致方式）")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*100}")

    # 2025年全期間でバックテスト実行
    run_backtest(
        db_path=db_path,
        start_date='2025-01-01',
        end_date='2025-12-31',
        prediction_type='before',  # 直前情報使用
        use_both_methods=True
    )


if __name__ == "__main__":
    main()
