# -*- coding: utf-8 -*-
"""
メタ指数の効果検証スクリプト

「買わない判断」を強化できるかを検証する。
現行購入条件にメタ指数フィルターを追加した場合のROI変化を測定。
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple
import sys

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

DB_PATH = project_root / "data" / "boatrace.db"


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def analyze_meta_index_distribution():
    """メタ指数の分布を確認"""
    conn = get_connection()
    cursor = conn.cursor()

    print("=" * 60)
    print("メタ指数の分布")
    print("=" * 60)

    # 安定度エントロピーの分布
    cursor.execute("""
    SELECT
        CASE
            WHEN stability_entropy < 0.7 THEN '0.0-0.7 (安定)'
            WHEN stability_entropy < 0.8 THEN '0.7-0.8 (やや安定)'
            WHEN stability_entropy < 0.9 THEN '0.8-0.9 (普通)'
            ELSE '0.9-1.0 (不安定)'
        END as entropy_band,
        COUNT(*) as cnt,
        AVG(stability_entropy) as avg_entropy
    FROM player_meta_stats
    WHERE stability_entropy IS NOT NULL
    GROUP BY 1
    ORDER BY 1
    """)
    print("\n【安定度エントロピー分布】")
    print("帯域             | 件数   | 平均")
    print("-" * 40)
    for row in cursor.fetchall():
        print(f"{row[0]:16} | {row[1]:5} | {row[2]:.4f}")

    # 上位独占率の分布
    cursor.execute("""
    SELECT
        CASE
            WHEN dominance_rate >= 0.45 THEN '0.45+ (上位)'
            WHEN dominance_rate >= 0.35 THEN '0.35-0.45 (中上位)'
            WHEN dominance_rate >= 0.25 THEN '0.25-0.35 (中位)'
            ELSE '<0.25 (下位)'
        END as dom_band,
        COUNT(*) as cnt,
        AVG(dominance_rate) as avg_dom
    FROM player_meta_stats
    WHERE dominance_rate IS NOT NULL
    GROUP BY 1
    ORDER BY 1
    """)
    print("\n【上位独占率分布】")
    print("帯域               | 件数   | 平均")
    print("-" * 40)
    for row in cursor.fetchall():
        print(f"{row[0]:18} | {row[1]:5} | {row[2]:.4f}")

    conn.close()


def analyze_meta_index_vs_actual():
    """メタ指数と実際の的中・ROIの関係を分析"""
    conn = get_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("メタ指数と的中率・ROIの関係分析")
    print("=" * 60)

    # 現行購入条件（B×50-100）のレースを対象に分析
    # 1コース選手のメタ指数で購入判定を変えた場合の効果を検証

    query = """
    WITH target_races AS (
        -- B×50-100条件のレース（冬除外後）
        SELECT
            rp.race_id,
            rc.race_date,
            rc.venue_code,
            e1.racer_number as c1_racer,
            rp.confidence,
            t.odds,
            CASE
                WHEN r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3' THEN 1
                ELSE 0
            END as is_hit
        FROM race_predictions rp
        JOIN races rc ON rp.race_id = rc.id
        JOIN entries e1 ON rp.race_id = e1.race_id AND e1.pit_number = 1
        JOIN trifecta_odds t ON rp.race_id = t.race_id AND t.combination = '1-2-3'
        JOIN results r1 ON rp.race_id = r1.race_id AND r1.pit_number = 1
        JOIN results r2 ON rp.race_id = r2.race_id AND r2.pit_number = 2
        JOIN results r3 ON rp.race_id = r3.race_id AND r3.pit_number = 3
        WHERE rp.prediction_type = 'before'
          AND rp.pit_number = 1
          AND rp.rank_prediction = 1
          AND rp.confidence = 'B'
          AND t.odds BETWEEN 50 AND 100
          AND CAST(strftime('%m', rc.race_date) AS INTEGER) NOT IN (1, 2, 12)
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    )
    SELECT
        tr.race_id,
        tr.race_date,
        tr.c1_racer,
        tr.confidence,
        tr.odds,
        tr.is_hit,
        pms.stability_entropy,
        pms.dominance_rate,
        pms.total_races
    FROM target_races tr
    LEFT JOIN player_meta_stats pms ON tr.c1_racer = pms.player_id AND pms.stadium_id IS NULL
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"\n分析対象: B×50-100（冬除外）条件 {len(rows)}レース")

    # メタ指数帯域別の分析
    entropy_bands = {
        '安定 (<0.85)': [],
        'やや安定 (0.85-0.90)': [],
        '普通 (0.90-0.95)': [],
        '不安定 (>=0.95)': []
    }

    dominance_bands = {
        '上位 (>=0.45)': [],
        '中上位 (0.35-0.45)': [],
        '中位 (0.25-0.35)': [],
        '下位 (<0.25)': []
    }

    for row in rows:
        race_id, race_date, c1_racer, conf, odds, is_hit, entropy, dominance, total = row

        # メタ指数がある場合のみ
        if entropy is not None:
            if entropy < 0.85:
                entropy_bands['安定 (<0.85)'].append((is_hit, odds))
            elif entropy < 0.90:
                entropy_bands['やや安定 (0.85-0.90)'].append((is_hit, odds))
            elif entropy < 0.95:
                entropy_bands['普通 (0.90-0.95)'].append((is_hit, odds))
            else:
                entropy_bands['不安定 (>=0.95)'].append((is_hit, odds))

        if dominance is not None:
            if dominance >= 0.45:
                dominance_bands['上位 (>=0.45)'].append((is_hit, odds))
            elif dominance >= 0.35:
                dominance_bands['中上位 (0.35-0.45)'].append((is_hit, odds))
            elif dominance >= 0.25:
                dominance_bands['中位 (0.25-0.35)'].append((is_hit, odds))
            else:
                dominance_bands['下位 (<0.25)'].append((is_hit, odds))

    def calc_roi(data):
        if not data:
            return 0, 0, 0
        hits = sum(1 for h, _ in data if h)
        total_return = sum(o * 100 if h else 0 for h, o in data)
        total_bet = len(data) * 400  # パターンH（400円）
        roi = total_return / total_bet * 100 if total_bet > 0 else 0
        return len(data), hits, roi

    print("\n【1コース選手の安定度エントロピー別】")
    print("帯域                  | 件数  | 的中 | ROI")
    print("-" * 50)
    for band, data in entropy_bands.items():
        cnt, hits, roi = calc_roi(data)
        print(f"{band:20} | {cnt:5} | {hits:4} | {roi:6.1f}%")

    print("\n【1コース選手の上位独占率別】")
    print("帯域                | 件数  | 的中 | ROI")
    print("-" * 50)
    for band, data in dominance_bands.items():
        cnt, hits, roi = calc_roi(data)
        print(f"{band:18} | {cnt:5} | {hits:4} | {roi:6.1f}%")

    # 複合条件の分析
    print("\n【複合条件分析】")
    combined_results = {
        'base': [],  # フィルターなし
        'entropy<0.92': [],  # 安定度のみ
        'dominance>=0.35': [],  # 上位独占率のみ
        'entropy<0.92 & dom>=0.35': []  # 両方
    }

    for row in rows:
        race_id, race_date, c1_racer, conf, odds, is_hit, entropy, dominance, total = row

        combined_results['base'].append((is_hit, odds))

        if entropy is not None and entropy < 0.92:
            combined_results['entropy<0.92'].append((is_hit, odds))

        if dominance is not None and dominance >= 0.35:
            combined_results['dominance>=0.35'].append((is_hit, odds))

        if entropy is not None and dominance is not None:
            if entropy < 0.92 and dominance >= 0.35:
                combined_results['entropy<0.92 & dom>=0.35'].append((is_hit, odds))

    print("条件                        | 件数  | 的中 | ROI    | 収支")
    print("-" * 65)
    for name, data in combined_results.items():
        cnt, hits, roi = calc_roi(data)
        profit = sum(o * 100 if h else 0 for h, o in data) - cnt * 400
        print(f"{name:25} | {cnt:5} | {hits:4} | {roi:6.1f}% | {profit:+,}円")

    conn.close()


def analyze_all_conditions():
    """全購入条件にメタ指数フィルターを適用した場合の効果"""
    conn = get_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("全条件へのメタ指数フィルター効果")
    print("=" * 60)

    # 各条件ごとの分析
    conditions = [
        ('A×A1×10-12+会場', "rp.confidence = 'A' AND e1.racer_rank = 'A1' AND t.odds BETWEEN 10 AND 12"),
        ('B×50-100×冬除外', "rp.confidence = 'B' AND t.odds BETWEEN 50 AND 100 AND CAST(strftime('%m', rc.race_date) AS INTEGER) NOT IN (1, 2, 12)"),
        ('B×30-50×B1+会場', "rp.confidence = 'B' AND e1.racer_rank = 'B1' AND t.odds BETWEEN 30 AND 50"),
        ('C×20-30×B1+会場', "rp.confidence = 'C' AND e1.racer_rank = 'B1' AND t.odds BETWEEN 20 AND 30"),
        ('D×40-50×B1', "rp.confidence = 'D' AND e1.racer_rank = 'B1' AND t.odds BETWEEN 40 AND 50"),
    ]

    print("\n条件                  | ベース件数 | フィルター後 | ベースROI | フィルターROI | 差分")
    print("-" * 85)

    for name, where in conditions:
        # ベース
        base_query = f"""
        SELECT
            CASE WHEN r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3' THEN 1 ELSE 0 END as is_hit,
            t.odds,
            pms.stability_entropy,
            pms.dominance_rate
        FROM race_predictions rp
        JOIN races rc ON rp.race_id = rc.id
        JOIN entries e1 ON rp.race_id = e1.race_id AND e1.pit_number = 1
        JOIN trifecta_odds t ON rp.race_id = t.race_id AND t.combination = '1-2-3'
        JOIN results r1 ON rp.race_id = r1.race_id AND r1.pit_number = 1
        JOIN results r2 ON rp.race_id = r2.race_id AND r2.pit_number = 2
        JOIN results r3 ON rp.race_id = r3.race_id AND r3.pit_number = 3
        LEFT JOIN player_meta_stats pms ON e1.racer_number = pms.player_id AND pms.stadium_id IS NULL
        WHERE rp.prediction_type = 'before'
          AND rp.pit_number = 1
          AND rp.rank_prediction = 1
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
          AND {where}
        """

        cursor.execute(base_query)
        rows = cursor.fetchall()

        base_data = [(h, o) for h, o, e, d in rows]
        filtered_data = [(h, o) for h, o, e, d in rows
                        if e is not None and d is not None
                        and e < 0.92 and d >= 0.35]

        def calc_roi(data, bet_amount=400):
            if not data:
                return 0, 0, 0
            total_return = sum(o * 100 if h else 0 for h, o in data)
            total_bet = len(data) * bet_amount
            roi = total_return / total_bet * 100 if total_bet > 0 else 0
            return len(data), sum(1 for h, _ in data if h), roi

        base_cnt, _, base_roi = calc_roi(base_data)
        filt_cnt, _, filt_roi = calc_roi(filtered_data)

        diff = filt_roi - base_roi if base_roi > 0 else 0

        print(f"{name:20} | {base_cnt:10} | {filt_cnt:12} | {base_roi:9.1f}% | {filt_roi:13.1f}% | {diff:+.1f}pt")

    conn.close()


def find_optimal_threshold():
    """最適な閾値を探索"""
    conn = get_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("最適閾値探索（B×50-100条件）")
    print("=" * 60)

    # B×50-100条件のデータ取得
    query = """
    SELECT
        CASE WHEN r1.rank = '1' AND r2.rank = '2' AND r3.rank = '3' THEN 1 ELSE 0 END as is_hit,
        t.odds,
        pms.stability_entropy,
        pms.dominance_rate
    FROM race_predictions rp
    JOIN races rc ON rp.race_id = rc.id
    JOIN entries e1 ON rp.race_id = e1.race_id AND e1.pit_number = 1
    JOIN trifecta_odds t ON rp.race_id = t.race_id AND t.combination = '1-2-3'
    JOIN results r1 ON rp.race_id = r1.race_id AND r1.pit_number = 1
    JOIN results r2 ON rp.race_id = r2.race_id AND r2.pit_number = 2
    JOIN results r3 ON rp.race_id = r3.race_id AND r3.pit_number = 3
    LEFT JOIN player_meta_stats pms ON e1.racer_number = pms.player_id AND pms.stadium_id IS NULL
    WHERE rp.prediction_type = 'before'
      AND rp.pit_number = 1
      AND rp.rank_prediction = 1
      AND rp.confidence = 'B'
      AND t.odds BETWEEN 50 AND 100
      AND CAST(strftime('%m', rc.race_date) AS INTEGER) NOT IN (1, 2, 12)
      AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    # 有効なデータのみ
    valid_data = [(h, o, e, d) for h, o, e, d in rows if e is not None and d is not None]

    print(f"総レース数: {len(rows)}")
    print(f"メタ指数あり: {len(valid_data)}")

    # グリッドサーチ
    print("\n【安定度エントロピー閾値】")
    print("閾値   | 件数  | 的中 | ROI    | 収支")
    print("-" * 45)

    for threshold in [0.80, 0.85, 0.88, 0.90, 0.92, 0.95, 1.0]:
        filtered = [(h, o) for h, o, e, d in valid_data if e <= threshold]
        if filtered:
            hits = sum(1 for h, _ in filtered if h)
            total_return = sum(o * 100 if h else 0 for h, o in filtered)
            total_bet = len(filtered) * 400
            roi = total_return / total_bet * 100
            profit = total_return - total_bet
            print(f"<={threshold:.2f} | {len(filtered):5} | {hits:4} | {roi:6.1f}% | {profit:+,}円")

    print("\n【上位独占率閾値】")
    print("閾値    | 件数  | 的中 | ROI    | 収支")
    print("-" * 45)

    for threshold in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
        filtered = [(h, o) for h, o, e, d in valid_data if d >= threshold]
        if filtered:
            hits = sum(1 for h, _ in filtered if h)
            total_return = sum(o * 100 if h else 0 for h, o in filtered)
            total_bet = len(filtered) * 400
            roi = total_return / total_bet * 100
            profit = total_return - total_bet
            print(f">={threshold:.2f}  | {len(filtered):5} | {hits:4} | {roi:6.1f}% | {profit:+,}円")

    conn.close()


def main():
    print("メタ指数効果検証")
    print("=" * 60)

    # 1. 分布確認
    analyze_meta_index_distribution()

    # 2. 的中率・ROIとの関係
    analyze_meta_index_vs_actual()

    # 3. 最適閾値探索
    find_optimal_threshold()

    # 4. 全条件への効果
    analyze_all_conditions()


if __name__ == "__main__":
    main()
