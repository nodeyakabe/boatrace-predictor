# -*- coding: utf-8 -*-
"""最終改善案のまとめ"""
import sqlite3
import pandas as pd
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from config.settings import DATABASE_PATH

conn = sqlite3.connect(DATABASE_PATH)

print('='*80)
print('購入条件改善分析レポート')
print('='*80)

print('''
================================================================================
【課題1】A×B1×Motor40%+ (赤字条件)
================================================================================

■ 現状
  - 6年間: 458件, ROI 92.0%, 収支 -3,680円
  - 黒字年数: 1/6年（2025年のみ+270円の微黒字）
  - 問題: 6年中5年が赤字、年度安定性なし

■ 検討した改善案

  案1: 黒字会場 + 30-50倍限定
    → 10件, ROI 765.0%, +6,650円 だがサンプル少、2/6年黒字
    → 採用基準未達

  案2: モーター50%+に引き上げ
    → 101件, ROI 44.4%, -5,620円
    → 逆効果（悪化）

  案3: 1コース2連率30%以上を追加
    → 175件, ROI 119.3%, +3,370円、2/6年黒字
    → 件数減、年度安定性なし

■ 結論: 廃止を推奨
  - どの改善案も採用基準（直近4年で3年以上黒字）を満たさない
  - 条件維持のメリットが少なく、リスクが大きい
  - 廃止による影響: 全体ROI +0.5pt改善、収支+3,680円改善

================================================================================
【課題2】B×50-100 (的中率が低い)
================================================================================

■ 現状（A1/B1級限定）
  - 6年間: 455件, ROI 213.2%, 収支 +51,520円
  - 黒字年数: 4/6年（2021年、2022年が赤字）
  - 的中率: 3.1%（14/455件）

■ 高ROIの理由
  - 的中時の平均オッズ: 69.3倍
  - 1コース逃げ予測の精度が高い（的中の71%が1コース1着予測）
  - B1級の寄与が大きい（B1: ROI 222.5% vs A1: 197.2%）

■ 検討した改善案

  案1: 会場フィルター追加（黒字11会場限定）
    → 89件, ROI 434.9%, +29,810円
    → 但し黒字年数3/6年（安定性改善なし）、件数大幅減

  案2: A2級除外（現在実装済み）
    → A2級: ROI 77.0%, -2,480円（赤字）
    → A1/B1限定は正しい判断

■ 結論: 現状維持を推奨
  - 既にA2除外で最適化済み
  - 会場フィルターは年度安定性を改善しないため不採用
  - 年度ブレは高オッズ帯の特性として許容
  - 4/6年黒字は採用基準を満たす

================================================================================
【総合推奨】
================================================================================

1. A×B1×Motor40%+ → 廃止
   - 効果: +3,680円の収支改善
   - 理由: 6年間赤字、改善案も効果なし

2. B×50-100 → 現状維持
   - 理由: 4/6年黒字で採用基準を満たす
   - 高オッズ帯の特性上、年度ブレは許容範囲

3. 全体への影響
   - 現状: 4,625件, ROI 134.7%, +235,100円
   - 改善後: 4,167件, ROI 約136%, +238,780円（推定）
''')

# 実際の数値を計算
query = '''
WITH race_base AS (
    SELECT
        r.id as race_id,
        rp.confidence,
        e1.racer_rank as c1_rank,
        e1.motor_second_rate,
        rp1.pit_number as p1,
        rp2.pit_number as p2,
        rp3.pit_number as p3
    FROM races r
    JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
    JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
    JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
    JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
    JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
    WHERE rp.rank_prediction = 1
    AND rp.confidence = 'A'
    AND e1.racer_rank = 'B1'
    AND e1.motor_second_rate >= 40
    AND r.race_date >= '2020-01-01'
    AND r.race_date < '2026-01-01'
),
race_bets AS (
    SELECT
        rb.*,
        COALESCE(
            (SELECT o.odds FROM trifecta_odds o
             WHERE o.race_id = rb.race_id
             AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
            ), 0
        ) as pred_odds
    FROM race_base rb
)
SELECT COUNT(*) as removed_bets
FROM race_bets
WHERE pred_odds >= 10 AND pred_odds < 100
'''
df = pd.read_sql_query(query, conn)
removed = df['removed_bets'].iloc[0]
print(f'■ A×B1×Motor40%+ 廃止による削減件数: {removed}件')

conn.close()
