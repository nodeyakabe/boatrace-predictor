"""
2025年全期間シミュレーション

現状の予想ロジックと戦略Aを使用して、2025年1年間の運用シミュレーションを実施
月別、信頼度別、回収率、払戻金などを詳細に分析
"""

import sys
from pathlib import Path
import sqlite3
import pandas as pd
from collections import defaultdict
from datetime import datetime

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

DB_PATH = project_root / 'data' / 'boatrace.db'


def load_all_predictions():
    """2025年の全予測データを取得"""
    conn = sqlite3.connect(str(DB_PATH))

    query = """
    SELECT
        p.race_id,
        p.pit_number,
        p.rank_prediction,
        p.total_score,
        p.confidence,
        p.prediction_type,
        r.venue_code,
        r.race_date,
        r.race_number,
        res.rank as actual_rank,
        res.is_invalid,
        e.racer_rank as c1_rank
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
    LEFT JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number
    LEFT JOIN entries e ON p.race_id = e.race_id AND e.pit_number = 1
    WHERE r.race_date LIKE '2025%'
      AND p.prediction_type = 'before'
    ORDER BY r.race_date, r.venue_code, r.race_number, p.rank_prediction
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df


def load_trifecta_odds(race_ids):
    """3連単オッズデータを取得"""
    if len(race_ids) == 0:
        return pd.DataFrame()

    conn = sqlite3.connect(str(DB_PATH))

    # race_idを5000件ずつに分割して取得（SQLiteの変数制限対策）
    chunk_size = 5000
    all_odds = []

    for i in range(0, len(race_ids), chunk_size):
        chunk = race_ids[i:i + chunk_size]

        query = f"""
        SELECT
            race_id,
            combination,
            odds
        FROM trifecta_odds
        WHERE race_id IN ({','.join(map(str, chunk))})
          AND combination LIKE '1-%'
        """

        chunk_df = pd.read_sql_query(query, conn)
        all_odds.append(chunk_df)

    conn.close()

    if len(all_odds) == 0:
        return pd.DataFrame()

    odds_df = pd.concat(all_odds, ignore_index=True)

    # 各レースの平均オッズを計算
    avg_odds = odds_df.groupby('race_id')['odds'].mean().reset_index()
    avg_odds.columns = ['race_id', 'trifecta_avg']

    return avg_odds


def load_trifecta_payouts(race_ids):
    """3連単払戻データを全て取得してメモリに格納"""
    if len(race_ids) == 0:
        return {}

    conn = sqlite3.connect(str(DB_PATH))

    # race_idを5000件ずつに分割して取得
    chunk_size = 5000
    all_payouts = []

    for i in range(0, len(race_ids), chunk_size):
        chunk = race_ids[i:i + chunk_size]

        query = f"""
        SELECT
            race_id,
            combination,
            amount
        FROM payouts
        WHERE race_id IN ({','.join(map(str, chunk))})
          AND bet_type = 'trifecta'
        """

        chunk_df = pd.read_sql_query(query, conn)
        all_payouts.append(chunk_df)

    conn.close()

    if len(all_payouts) == 0:
        return {}

    payouts_df = pd.concat(all_payouts, ignore_index=True)

    # 辞書形式に変換: {(race_id, combination): amount}
    payout_dict = {}
    for _, row in payouts_df.iterrows():
        key = (row['race_id'], row['combination'])
        payout_dict[key] = row['amount']

    return payout_dict


def determine_betting_strategy(row, trifecta_avg):
    """
    戦略Aの購入条件に該当するかを判定

    戦略A条件（残タスク一覧.mdより）:
    - 信頼度C: B1 × 150-200倍
    - 信頼度D:
      - Tier1: B1 × 200-300倍
      - Tier2: A1 × 100-150倍, A1 × 200-300倍, A2 × 30-40倍
      - Tier3: A1 × 40-50倍, A1 × 20-25倍
    """
    confidence = row['confidence']
    c1_rank = row['c1_rank']
    rank_pred = row['rank_prediction']

    # 1着予想のみ
    if rank_pred != 1:
        return None, None

    # オッズ情報がない場合は購入対象外
    if pd.isna(trifecta_avg):
        return None, None

    # 信頼度C
    if confidence == 'C':
        if c1_rank == 'B1' and 150 <= trifecta_avg < 200:
            return 'C', 'C×B1×150-200倍'

    # 信頼度D
    elif confidence == 'D':
        if c1_rank == 'B1' and 200 <= trifecta_avg < 300:
            return 'D', 'D×B1×200-300倍 [Tier1]'
        elif c1_rank == 'A1' and 100 <= trifecta_avg < 150:
            return 'D', 'D×A1×100-150倍 [Tier2]'
        elif c1_rank == 'A1' and 200 <= trifecta_avg < 300:
            return 'D', 'D×A1×200-300倍 [Tier2]'
        elif c1_rank == 'A2' and 30 <= trifecta_avg < 40:
            return 'D', 'D×A2×30-40倍 [Tier2]'
        elif c1_rank == 'A1' and 40 <= trifecta_avg < 50:
            return 'D', 'D×A1×40-50倍 [Tier3]'
        elif c1_rank == 'A1' and 20 <= trifecta_avg < 25:
            return 'D', 'D×A1×20-25倍 [Tier3]'

    return None, None


def calculate_trifecta_payout(race_id, actual_ranks, payout_dict):
    """
    実際の3連単払戻金を取得（辞書参照方式）

    actual_ranks: {pit_number: rank} の辞書
    payout_dict: {(race_id, combination): amount} の辞書
    """
    # 1-2-3着を取得
    ranks_sorted = sorted(actual_ranks.items(), key=lambda x: x[1])

    if len(ranks_sorted) < 3:
        return 0

    first = int(ranks_sorted[0][0])  # 1着の艇番（整数に変換）
    second = int(ranks_sorted[1][0])  # 2着の艇番（整数に変換）
    third = int(ranks_sorted[2][0])  # 3着の艇番（整数に変換）

    # 1着が1番でない場合は不的中
    if first != 1:
        return 0

    # 3連単の組み合わせ
    combination = f"{first}-{second}-{third}"

    # 辞書から払戻金を取得
    key = (race_id, combination)
    return payout_dict.get(key, 0)


def simulate_betting():
    """購入シミュレーション実行"""
    print("=" * 100)
    print("2025年全期間シミュレーション")
    print("=" * 100)
    print()

    # データロード
    print("予測データロード中...")
    df = load_all_predictions()
    print(f"総予測データ: {len(df)}件")

    # 1着予想のみに絞る
    df_first = df[df['rank_prediction'] == 1].copy()
    print(f"1着予測データ: {len(df_first)}件")

    # オッズデータロード
    print("\nオッズデータロード中...")
    race_ids = df_first['race_id'].unique().tolist()
    odds_df = load_trifecta_odds(race_ids)
    print(f"オッズデータ: {len(odds_df)}レース")

    # オッズをマージ
    df_first = df_first.merge(odds_df, on='race_id', how='left')

    # 払戻データロード
    print("\n払戻データロード中...")
    payout_dict = load_trifecta_payouts(race_ids)
    print(f"払戻データ: {len(payout_dict)}件")

    # 購入判定
    print("\n購入判定中...")
    df_first['strategy'] = df_first.apply(
        lambda row: determine_betting_strategy(row, row['trifecta_avg'])[0],
        axis=1
    )
    df_first['strategy_detail'] = df_first.apply(
        lambda row: determine_betting_strategy(row, row['trifecta_avg'])[1],
        axis=1
    )

    # 購入対象のみ
    df_bet = df_first[df_first['strategy'].notna()].copy()
    print(f"購入対象: {len(df_bet)}レース")

    # 月別データ作成
    df_bet['month'] = df_bet['race_date'].str[:7]  # YYYY-MM

    # actual_rankを数値に変換
    df_bet['actual_rank'] = pd.to_numeric(df_bet['actual_rank'], errors='coerce')

    # レースごとの結果を集約
    print("\n払戻金計算中...")
    race_results = []
    hit_count_check = 0
    payout_count_check = 0

    for race_id in df_bet['race_id'].unique():
        race_data = df_bet[df_bet['race_id'] == race_id].iloc[0]

        # 実際の着順を取得
        all_results = df[df['race_id'] == race_id][['pit_number', 'actual_rank', 'is_invalid']].copy()
        all_results['actual_rank'] = pd.to_numeric(all_results['actual_rank'], errors='coerce')

        # 無効レース除外
        if all_results['is_invalid'].any():
            continue

        # NaN除外（actual_rankがNullのものは除外）
        all_results = all_results[all_results['actual_rank'].notna()].copy()

        # 6艇分のデータが揃っていない場合はスキップ
        if len(all_results) < 6:
            continue

        actual_ranks = dict(zip(all_results['pit_number'].astype(int), all_results['actual_rank'].astype(int)))

        # 1着的中判定
        is_hit = actual_ranks.get(1) == 1

        # 3連単払戻金計算（20通り買い）
        bet_amount = 100 * 20  # 100円 × 20通り
        payout = 0

        if is_hit:
            hit_count_check += 1
            payout = calculate_trifecta_payout(race_id, actual_ranks, payout_dict)
            if payout > 0:
                payout_count_check += 1

        race_results.append({
            'race_id': race_id,
            'race_date': race_data['race_date'],
            'month': race_data['month'],
            'confidence': race_data['confidence'],
            'c1_rank': race_data['c1_rank'],
            'strategy': race_data['strategy'],
            'strategy_detail': race_data['strategy_detail'],
            'trifecta_avg': race_data['trifecta_avg'],
            'is_hit': is_hit,
            'bet_amount': bet_amount,
            'payout': payout,
            'profit': payout - bet_amount
        })

    print(f"的中レース: {hit_count_check}件")
    print(f"払戻取得: {payout_count_check}件")

    df_results = pd.DataFrame(race_results)

    return df_results


def generate_report(df_results):
    """詳細レポート生成"""
    print("\n" + "=" * 100)
    print("シミュレーション結果")
    print("=" * 100)

    # 全体サマリー
    total_races = len(df_results)
    total_bet = df_results['bet_amount'].sum()
    total_payout = df_results['payout'].sum()
    total_profit = df_results['profit'].sum()
    hit_count = df_results['is_hit'].sum()
    hit_rate = (hit_count / total_races * 100) if total_races > 0 else 0
    roi = (total_payout / total_bet * 100) if total_bet > 0 else 0

    print(f"\n【全体サマリー】")
    print(f"  購入レース数: {total_races:,}レース")
    print(f"  総投資額: {total_bet:,}円")
    print(f"  総払戻額: {total_payout:,}円")
    print(f"  総収支: {total_profit:+,}円")
    print(f"  的中数: {hit_count}レース")
    print(f"  的中率: {hit_rate:.2f}%")
    print(f"  回収率: {roi:.1f}%")

    # 月別集計
    print("\n" + "=" * 100)
    print("月別集計")
    print("=" * 100)
    print(f"\n{'月':<10} {'購入数':>8} {'投資額':>12} {'払戻額':>12} {'収支':>12} {'的中数':>8} {'的中率':>8} {'回収率':>8}")
    print("-" * 100)

    monthly_stats = []

    for month in sorted(df_results['month'].unique()):
        month_data = df_results[df_results['month'] == month]

        m_races = len(month_data)
        m_bet = month_data['bet_amount'].sum()
        m_payout = month_data['payout'].sum()
        m_profit = month_data['profit'].sum()
        m_hit = month_data['is_hit'].sum()
        m_hit_rate = (m_hit / m_races * 100) if m_races > 0 else 0
        m_roi = (m_payout / m_bet * 100) if m_bet > 0 else 0

        print(f"{month:<10} {m_races:>8} {m_bet:>11,}円 {m_payout:>11,}円 {m_profit:>+11,}円 "
              f"{m_hit:>8} {m_hit_rate:>7.2f}% {m_roi:>7.1f}%")

        monthly_stats.append({
            'month': month,
            'races': m_races,
            'bet': m_bet,
            'payout': m_payout,
            'profit': m_profit,
            'hit': m_hit,
            'hit_rate': m_hit_rate,
            'roi': m_roi
        })

    # 信頼度別集計
    print("\n" + "=" * 100)
    print("信頼度別集計")
    print("=" * 100)
    print(f"\n{'信頼度':<10} {'購入数':>8} {'投資額':>12} {'払戻額':>12} {'収支':>12} {'的中数':>8} {'的中率':>8} {'回収率':>8}")
    print("-" * 100)

    confidence_stats = []

    for conf in ['C', 'D']:
        conf_data = df_results[df_results['confidence'] == conf]

        if len(conf_data) == 0:
            continue

        c_races = len(conf_data)
        c_bet = conf_data['bet_amount'].sum()
        c_payout = conf_data['payout'].sum()
        c_profit = conf_data['profit'].sum()
        c_hit = conf_data['is_hit'].sum()
        c_hit_rate = (c_hit / c_races * 100) if c_races > 0 else 0
        c_roi = (c_payout / c_bet * 100) if c_bet > 0 else 0

        print(f"{conf:<10} {c_races:>8} {c_bet:>11,}円 {c_payout:>11,}円 {c_profit:>+11,}円 "
              f"{c_hit:>8} {c_hit_rate:>7.2f}% {c_roi:>7.1f}%")

        confidence_stats.append({
            'confidence': conf,
            'races': c_races,
            'bet': c_bet,
            'payout': c_payout,
            'profit': c_profit,
            'hit': c_hit,
            'hit_rate': c_hit_rate,
            'roi': c_roi
        })

    # 戦略詳細別集計
    print("\n" + "=" * 100)
    print("戦略詳細別集計")
    print("=" * 100)
    print(f"\n{'戦略詳細':<30} {'購入数':>8} {'投資額':>12} {'払戻額':>12} {'収支':>12} {'的中数':>8} {'的中率':>8} {'回収率':>8}")
    print("-" * 100)

    strategy_stats = []

    for strategy in df_results['strategy_detail'].unique():
        if pd.isna(strategy):
            continue

        strat_data = df_results[df_results['strategy_detail'] == strategy]

        s_races = len(strat_data)
        s_bet = strat_data['bet_amount'].sum()
        s_payout = strat_data['payout'].sum()
        s_profit = strat_data['profit'].sum()
        s_hit = strat_data['is_hit'].sum()
        s_hit_rate = (s_hit / s_races * 100) if s_races > 0 else 0
        s_roi = (s_payout / s_bet * 100) if s_bet > 0 else 0

        print(f"{strategy:<30} {s_races:>8} {s_bet:>11,}円 {s_payout:>11,}円 {s_profit:>+11,}円 "
              f"{s_hit:>8} {s_hit_rate:>7.2f}% {s_roi:>7.1f}%")

        strategy_stats.append({
            'strategy': strategy,
            'races': s_races,
            'bet': s_bet,
            'payout': s_payout,
            'profit': s_profit,
            'hit': s_hit,
            'hit_rate': s_hit_rate,
            'roi': s_roi
        })

    return {
        'summary': {
            'races': total_races,
            'bet': total_bet,
            'payout': total_payout,
            'profit': total_profit,
            'hit': hit_count,
            'hit_rate': hit_rate,
            'roi': roi
        },
        'monthly': monthly_stats,
        'confidence': confidence_stats,
        'strategy': strategy_stats
    }


def save_detailed_report(report, df_results):
    """詳細レポートをMarkdown形式で保存"""
    output_path = project_root / 'docs' / 'simulation_2025_full_year.md'

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# 2025年全期間シミュレーション結果\n\n")
        f.write(f"**実行日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## 概要\n\n")
        f.write("現状の予想ロジックと戦略Aを使用して、2025年1年間の運用をシミュレーション。\n")
        f.write("信頼度C/Dの予測に対して、既存の購入条件を適用した場合の結果を分析。\n\n")

        # 全体サマリー
        f.write("## 全体サマリー\n\n")
        summary = report['summary']
        f.write(f"| 項目 | 値 |\n")
        f.write(f"|------|------|\n")
        f.write(f"| 購入レース数 | {summary['races']:,}レース |\n")
        f.write(f"| 総投資額 | {summary['bet']:,}円 |\n")
        f.write(f"| 総払戻額 | {summary['payout']:,}円 |\n")
        f.write(f"| 総収支 | {summary['profit']:+,}円 |\n")
        f.write(f"| 的中数 | {summary['hit']}レース |\n")
        f.write(f"| 的中率 | {summary['hit_rate']:.2f}% |\n")
        f.write(f"| 回収率 | {summary['roi']:.1f}% |\n\n")

        # 月別集計
        f.write("## 月別集計\n\n")
        f.write("| 月 | 購入数 | 投資額 | 払戻額 | 収支 | 的中数 | 的中率 | 回収率 |\n")
        f.write("|-----|--------|--------|--------|------|--------|--------|--------|\n")
        for m in report['monthly']:
            f.write(f"| {m['month']} | {m['races']} | {m['bet']:,}円 | {m['payout']:,}円 | "
                   f"{m['profit']:+,}円 | {m['hit']} | {m['hit_rate']:.2f}% | {m['roi']:.1f}% |\n")
        f.write("\n")

        # 信頼度別集計
        f.write("## 信頼度別集計\n\n")
        f.write("| 信頼度 | 購入数 | 投資額 | 払戻額 | 収支 | 的中数 | 的中率 | 回収率 |\n")
        f.write("|--------|--------|--------|--------|------|--------|--------|--------|\n")
        for c in report['confidence']:
            f.write(f"| {c['confidence']} | {c['races']} | {c['bet']:,}円 | {c['payout']:,}円 | "
                   f"{c['profit']:+,}円 | {c['hit']} | {c['hit_rate']:.2f}% | {c['roi']:.1f}% |\n")
        f.write("\n")

        # 戦略詳細別集計
        f.write("## 戦略詳細別集計\n\n")
        f.write("| 戦略詳細 | 購入数 | 投資額 | 払戻額 | 収支 | 的中数 | 的中率 | 回収率 |\n")
        f.write("|----------|--------|--------|--------|------|--------|--------|--------|\n")
        for s in report['strategy']:
            f.write(f"| {s['strategy']} | {s['races']} | {s['bet']:,}円 | {s['payout']:,}円 | "
                   f"{s['profit']:+,}円 | {s['hit']} | {s['hit_rate']:.2f}% | {s['roi']:.1f}% |\n")
        f.write("\n")

        # 考察
        f.write("## 考察\n\n")
        f.write("### 全体的な傾向\n\n")

        if summary['roi'] > 100:
            f.write(f"- 回収率{summary['roi']:.1f}%と、**プラス収支**を達成\n")
            f.write(f"- 年間収支: **{summary['profit']:+,}円**\n")
        else:
            f.write(f"- 回収率{summary['roi']:.1f}%と、マイナス収支\n")
            f.write(f"- 年間収支: {summary['profit']:+,}円\n")

        f.write(f"- 的中率: {summary['hit_rate']:.2f}%\n")
        f.write(f"- 購入機会: {summary['races']:,}レース（2025年全体から抽出）\n\n")

        f.write("### 信頼度別の特徴\n\n")
        for c in report['confidence']:
            f.write(f"**信頼度{c['confidence']}**:\n")
            f.write(f"- 購入数: {c['races']}レース\n")
            f.write(f"- 的中率: {c['hit_rate']:.2f}%\n")
            f.write(f"- 回収率: {c['roi']:.1f}%\n")
            if c['roi'] > 100:
                f.write(f"- 評価: **プラス収支** ({c['profit']:+,}円)\n\n")
            else:
                f.write(f"- 評価: マイナス収支 ({c['profit']:+,}円)\n\n")

        f.write("### 戦略別の評価\n\n")
        for s in sorted(report['strategy'], key=lambda x: x['roi'], reverse=True):
            f.write(f"**{s['strategy']}**:\n")
            f.write(f"- 購入数: {s['races']}レース\n")
            f.write(f"- 的中率: {s['hit_rate']:.2f}%\n")
            f.write(f"- 回収率: {s['roi']:.1f}%\n")
            f.write(f"- 収支: {s['profit']:+,}円\n\n")

        f.write("---\n\n")
        f.write("*自動生成レポート*\n")

    print(f"\n詳細レポートを保存しました: {output_path}")


def main():
    # シミュレーション実行
    df_results = simulate_betting()

    # レポート生成
    report = generate_report(df_results)

    # 詳細レポート保存
    save_detailed_report(report, df_results)

    print("\n" + "=" * 100)
    print("シミュレーション完了")
    print("=" * 100)


if __name__ == '__main__':
    main()
