"""
2025年全期間シミュレーション（改善版）

改善点:
1. 賭け金を300円に修正（3連単1点買い想定）
2. 低オッズ戦略（D×A1×20-25倍、D×B1×5-10倍）を追加
3. 全8条件を完全実装
"""

import sys
from pathlib import Path
import sqlite3
import pandas as pd
from datetime import datetime

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
    戦略Aの購入条件に該当するかを判定（全8条件）

    戦略A条件（残タスク一覧.mdより）:
    Tier 1: 超高配当狙い
    - D × B1 × 200-300倍
    - D × A1 × 100-150倍
    - D × A1 × 200-300倍
    - C × B1 × 150-200倍

    Tier 2: 中高配当狙い
    - D × A2 × 30-40倍
    - D × A1 × 40-50倍
    - D × A1 × 20-25倍

    Tier 3: 堅実狙い
    - D × B1 × 5-10倍
    """
    confidence = row['confidence']
    c1_rank = row['c1_rank']
    rank_pred = row['rank_prediction']

    # 1着予想のみ
    if rank_pred != 1:
        return None, None, None

    # オッズ情報がない場合は購入対象外
    if pd.isna(trifecta_avg):
        return None, None, None

    # 信頼度C
    if confidence == 'C':
        if c1_rank == 'B1' and 150 <= trifecta_avg < 200:
            return 'C', 'C×B1×150-200倍', 'Tier1'

    # 信頼度D
    elif confidence == 'D':
        # Tier1
        if c1_rank == 'B1' and 200 <= trifecta_avg < 300:
            return 'D', 'D×B1×200-300倍', 'Tier1'
        elif c1_rank == 'A1' and 100 <= trifecta_avg < 150:
            return 'D', 'D×A1×100-150倍', 'Tier1'
        elif c1_rank == 'A1' and 200 <= trifecta_avg < 300:
            return 'D', 'D×A1×200-300倍', 'Tier1'

        # Tier2
        elif c1_rank == 'A2' and 30 <= trifecta_avg < 40:
            return 'D', 'D×A2×30-40倍', 'Tier2'
        elif c1_rank == 'A1' and 40 <= trifecta_avg < 50:
            return 'D', 'D×A1×40-50倍', 'Tier2'
        elif c1_rank == 'A1' and 20 <= trifecta_avg < 25:
            return 'D', 'D×A1×20-25倍', 'Tier2'

        # Tier3
        elif c1_rank == 'B1' and 5 <= trifecta_avg < 10:
            return 'D', 'D×B1×5-10倍', 'Tier3'

    return None, None, None


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

    first = int(ranks_sorted[0][0])
    second = int(ranks_sorted[1][0])
    third = int(ranks_sorted[2][0])

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
    print("2025年全期間シミュレーション（改善版）")
    print("=" * 100)
    print("\n【改善点】")
    print("  1. 賭け金: 300円（3連単1点買い想定）")
    print("  2. 低オッズ戦略追加: D×A1×20-25倍、D×B1×5-10倍")
    print("  3. 全8条件完全実装")
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
    df_first['tier'] = df_first.apply(
        lambda row: determine_betting_strategy(row, row['trifecta_avg'])[2],
        axis=1
    )

    # 購入対象のみ
    df_bet = df_first[df_first['strategy'].notna()].copy()
    print(f"購入対象: {len(df_bet)}レース")

    # 月別データ作成
    df_bet['month'] = df_bet['race_date'].str[:7]

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

        # NaN除外
        all_results = all_results[all_results['actual_rank'].notna()].copy()

        # 6艇分のデータが揃っていない場合はスキップ
        if len(all_results) < 6:
            continue

        actual_ranks = dict(zip(all_results['pit_number'].astype(int), all_results['actual_rank'].astype(int)))

        # 1着的中判定
        is_hit_1st = actual_ranks.get(1) == 1

        # 3連単払戻金計算（1点買い 300円）
        bet_amount = 300
        payout = 0

        if is_hit_1st:
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
            'tier': race_data['tier'],
            'trifecta_avg': race_data['trifecta_avg'],
            'is_hit': is_hit_1st,
            'bet_amount': bet_amount,
            'payout': payout,
            'profit': payout - bet_amount
        })

    print(f"1着的中: {hit_count_check}件")
    print(f"3連単的中（払戻取得）: {payout_count_check}件")

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
    hit_count = (df_results['payout'] > 0).sum()  # 3連単的中数
    hit_rate = (hit_count / total_races * 100) if total_races > 0 else 0
    roi = (total_payout / total_bet * 100) if total_bet > 0 else 0

    print(f"\n【全体サマリー】")
    print(f"  購入レース数: {total_races:,}レース")
    print(f"  総投資額: {total_bet:,}円")
    print(f"  総払戻額: {total_payout:,}円")
    print(f"  総収支: {total_profit:+,}円")
    print(f"  3連単的中数: {hit_count}レース")
    print(f"  3連単的中率: {hit_rate:.2f}%")
    print(f"  回収率: {roi:.1f}%")

    # Tier別集計
    print("\n" + "=" * 100)
    print("Tier別集計")
    print("=" * 100)

    for tier in ['Tier1', 'Tier2', 'Tier3']:
        tier_data = df_results[df_results['tier'] == tier]

        if len(tier_data) == 0:
            continue

        t_races = len(tier_data)
        t_bet = tier_data['bet_amount'].sum()
        t_payout = tier_data['payout'].sum()
        t_profit = tier_data['profit'].sum()
        t_hit = (tier_data['payout'] > 0).sum()
        t_hit_rate = (t_hit / t_races * 100) if t_races > 0 else 0
        t_roi = (t_payout / t_bet * 100) if t_bet > 0 else 0

        print(f"\n【{tier}】")
        print(f"  購入数: {t_races}レース")
        print(f"  投資額: {t_bet:,}円")
        print(f"  払戻額: {t_payout:,}円")
        print(f"  収支: {t_profit:+,}円")
        print(f"  的中数: {t_hit}レース")
        print(f"  的中率: {t_hit_rate:.2f}%")
        print(f"  回収率: {t_roi:.1f}%")

    # 戦略詳細別集計
    print("\n" + "=" * 100)
    print("戦略詳細別集計")
    print("=" * 100)
    print(f"\n{'戦略詳細':<30} {'購入数':>8} {'投資額':>12} {'払戻額':>12} {'収支':>12} {'的中数':>8} {'的中率':>8} {'回収率':>8}")
    print("-" * 100)

    strategy_stats = []

    for strategy in sorted(df_results['strategy_detail'].unique()):
        if pd.isna(strategy):
            continue

        strat_data = df_results[df_results['strategy_detail'] == strategy]

        s_races = len(strat_data)
        s_bet = strat_data['bet_amount'].sum()
        s_payout = strat_data['payout'].sum()
        s_profit = strat_data['profit'].sum()
        s_hit = (strat_data['payout'] > 0).sum()
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
        'strategies': strategy_stats
    }


def main():
    # シミュレーション実行
    df_results = simulate_betting()

    # レポート生成
    report = generate_report(df_results)

    print("\n" + "=" * 100)
    print("前回実績との比較")
    print("=" * 100)

    print(f"\n【前回実績（残タスク一覧.md）】")
    print(f"  購入数: 637レース")
    print(f"  収支: +380,070円")
    print(f"  的中数: 52回")
    print(f"  的中率: 8.2%")
    print(f"  ROI: 298.9%")

    print(f"\n【今回シミュレーション（改善版）】")
    print(f"  購入数: {report['summary']['races']}レース")
    print(f"  収支: {report['summary']['profit']:+,}円")
    print(f"  的中数: {report['summary']['hit']}回")
    print(f"  的中率: {report['summary']['hit_rate']:.2f}%")
    print(f"  ROI: {report['summary']['roi']:.1f}%")

    print(f"\n【差分】")
    print(f"  購入数: {report['summary']['races'] - 637:+} ({(report['summary']['races'] / 637 - 1) * 100:+.1f}%)")
    print(f"  収支: {report['summary']['profit'] - 380070:+,}円")
    print(f"  ROI: {report['summary']['roi'] - 298.9:+.1f}pt")

    print("\n" + "=" * 100)
    print("シミュレーション完了")
    print("=" * 100)


if __name__ == '__main__':
    main()
