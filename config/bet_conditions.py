"""購入条件の一元管理

このファイルを修正すると、バックテストと実運用の両方に反映されます。
条件追加時は必ずバックテストで検証してから実運用に適用してください。

Version: v2.2.0
Last Updated: 2026-02-16
"""

from typing import List, Dict, Any, Optional

# ============================================================
# バージョン管理
# ============================================================
CONDITION_VERSION = "v2.2.0"
LAST_UPDATED = "2026-02-16"

# ============================================================
# 標準BetTargetEvaluatorのパラメータ
# ============================================================
STANDARD_EVALUATOR_PARAMS = {
    'use_multi_bet': True,
    'multi_bet_pattern': 'PATTERN_H',  # MultiBetPattern.PATTERN_H
    'enable_venue_wind_filter': True,
    'enable_venue_course_adjustment': True,
    'venue_course_adjustment_scale': 1.0,
}

# ============================================================
# 10条件の定義（2026-02-16更新：優先度追加）
# ============================================================
# 購入条件定義（bet_target_evaluator.py と完全同期）
# ※このファイルがマスターです。変更時はバックテストで必ず検証してください。


# ============================================================
# 重複レース時の優先度
# ============================================================
# 重複レースの場合、優先度の高い条件（小さい数値）を優先
# 例: 同じレースがD×40-50×B1(priority=9)とD×5コース(priority=10)に
#     該当する場合、D×40-50×B1が優先される


# ============================================================
# 重複レース時の優先度
# ============================================================
# 重複レースの場合、優先度の高い条件（小さい数値）を優先
# 例: 同じレースがD×40-50×B1(priority=9)とD×5コース(priority=10)に
#     該当する場合、D×40-50×B1が優先される

STANDARD_BET_CONDITIONS = [
    # ----------------------------------------------------------------
    # A条件（2026-01-07改善版）
    # ----------------------------------------------------------------
    # 【2026-01-07改善】A×A1×10-12 + 会場フィルター
    # 改善前: 6年間ROI 98.3%, -2,000円（赤字）
    # 改善後: 6年間ROI 103.5%, +1,150円（黒字）
    {
        'id': 'A_A1_10_12',
        'priority': 1,
        'name': 'A×A1×10-12+会場+逃げ率',
        'confidence': 'A',
        'c1_rank': ['A1'],
        'odds_min': 10,
        'odds_max': 12,
        # 黒字6会場: 三国,鳴門,芦屋,徳山,常滑,びわこ（下関除外 2026-02-13）
        'venue_filter': [10, 14, 21, 18, 8, 12],
        'escape_rate_min': 0.70,  # 逃げ率70%以上（2026-01-09追加）
        'predicted_course': 1,  # 1コース予測時のみ適用
        'description': 'A×A1級×10-12倍+会場+逃げ率70%+（2026-01-09改善）',
        'use_pattern_h': False,  # 1点買い（低オッズ帯）
        'version': '1.1',
        'added_date': '2026-01-07',
        'backtest_period': '2020-2025',
        'backtest_roi': 114.2,
        'backtest_profit': 3090,
        'backtest_black_years': '5/6',
    },

    # ----------------------------------------------------------------
    # B条件（高オッズ帯→パターンH推奨）
    # ----------------------------------------------------------------
    # 【2026-01-13更新】4月除外追加（6年間的中0回の完全赤字月）
    # 効果: 1180件→1082件(-8.3%), ROI 168.2%→183.6%(+15.4pt), 収支+15,300円
    {
        'id': 'B_50_100',
        'priority': 2,
        'name': 'B×50-100×冬+4月除外+会場最適化',
        'confidence': 'B',
        'c1_rank': ['A1', 'B1'],  # A2除外
        'odds_min': 50,
        'odds_max': 100,
        # 【2026-02-13更新】正確な会場別分析に基づく11会場（ROI≥150%, サンプル≥20）
        # 平和島(676%),蒲郡(477%),下関(428%),福岡(422%),戸田(340%),宮島(300%),芦屋(292%),びわこ(277%),常滑(260%),桐生(207%),津(162%)
        'venue_filter': [4, 7, 19, 22, 2, 17, 21, 11, 8, 1, 9],
        'month_exclude': [12, 1, 2, 4],  # 冬季+4月除外（2026-01-13追加）
        'description': 'B×50-100倍×冬+4月除外×11会場（期待ROI 300-400%）',
        'use_pattern_h': True,  # パターンH（高オッズ帯）
        'version': '1.2',
        'added_date': '2026-01-09',
        'backtest_period': '2020-2025',
        'backtest_roi': 183.6,
        'backtest_profit': 139910,
        'backtest_black_years': '6/6',
    },

    # 【2026-01-13更新】会場を高ROI上位4会場に限定
    # 変更前: 10会場, ROI 130.7%, 4/6年黒字, 2025年-11,680円
    # 変更後: 4会場, ROI 196.7%, 6/6年黒字, 2025年+1,220円
    {
        'id': 'B_30_50_B1',
        'priority': 3,
        'name': 'B×30-50×B1+4会場',
        'confidence': 'B',
        'c1_rank': ['B1'],
        'odds_min': 30,
        'odds_max': 50,
        # 津,三国,芦屋,浜名湖（高ROI上位4会場のみ）
        'venue_filter': [9, 10, 21, 6],
        'description': 'B×30-50倍×B1級×4会場（ROI 196.7%）',
        'use_pattern_h': True,  # パターンH（高オッズ帯）
        'version': '1.1',
        'added_date': '2026-01-13',
        'backtest_period': '2020-2025',
        'backtest_roi': 187.4,
        'backtest_profit': 17560,
        'backtest_black_years': '6/6',
    },

    # 【2026-01-13追加】B×10-30倍×穴源×黒字会場
    # バイアス指数分析で発見: 予想より上に来やすい選手（穴源）を狙う
    # 検証結果: 202件, ROI 168.8%, +13,890円, 4/6年黒字
    {
        'id': 'B_10_30_bias',
        'priority': 4,
        'name': 'B×10-30×穴源×会場',
        'confidence': 'B',
        'c1_rank': ['A1', 'A2', 'B1'],
        'odds_min': 10,
        'odds_max': 30,
        # 黒字会場: 浜名湖,蒲郡,常滑,三国,丸亀,下関
        'venue_filter': [6, 7, 8, 10, 15, 19],
        'bias_max': -0.3,  # バイアス指数<-0.3（穴源選手）
        'description': 'B×10-30倍×穴源(bias<-0.3)×会場',
        'use_pattern_h': False,  # 1点買い（低オッズ帯）
        'version': '1.0',
        'added_date': '2026-01-13',
        'backtest_period': '2020-2025',
        'backtest_roi': 142.8,
        'backtest_profit': 4920,
        'backtest_black_years': '5/6',
    },

    # ----------------------------------------------------------------
    # C条件
    # ----------------------------------------------------------------
    # 【2026-01-13更新】唐津(23)を除外（唐津×C×B1×20-30条件と完全重複のため）
    {
        'id': 'C_20_30_B1',
        'priority': 5,
        'name': 'C×20-30×B1+会場',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20,
        'odds_max': 30,
        # 徳山,多摩川,平和島,津,丸亀,常滑,大村,若松,宮島（唐津除外）
        'venue_filter': [18, 5, 4, 9, 15, 8, 24, 20, 17],
        'description': 'C×20-30倍×B1級（会場フィルター・唐津除外）',
        'use_pattern_h': False,  # 1点買い（低オッズ帯）
        'version': '1.1',
        'added_date': '2026-01-08',
        'backtest_period': '2020-2025',
        'backtest_roi': 138.6,
        'backtest_profit': 22020,
        'backtest_black_years': '5/6',
    },

    {
        'id': 'C_Naruto_A2',
        'priority': 6,
        'name': '鳴門×C×A2×30-80',
        'confidence': 'C',
        'c1_rank': ['A2'],
        'odds_min': 30,
        'odds_max': 80,
        'venue_filter': [14],  # 鳴門のみ
        'description': '鳴門×C×A2級×30-80倍（直近4年連続黒字）',
        'use_pattern_h': True,  # パターンH（高オッズ帯）
        'version': '1.0',
        'added_date': '2026-01-08',
        'backtest_period': '2020-2025',
        'backtest_roi': 154.3,
        'backtest_profit': 37250,
        'backtest_black_years': '4/6',
    },

    # 【2026-01-08追加】唐津×C×B1×20-30倍
    # 探索結果: ROI 175.5%, +9,290円, 直近4年連続黒字
    {
        'id': 'C_Karatsu_B1',
        'priority': 7,
        'name': '唐津×C×B1×20-30',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 20,
        'odds_max': 30,
        'venue_filter': [23],  # 唐津のみ
        'description': '唐津×C×B1級×20-30倍（直近4年連続黒字）',
        'use_pattern_h': False,  # 1点買い（低オッズ帯）
        'version': '1.0',
        'added_date': '2026-01-08',
        'backtest_period': '2020-2025',
        'backtest_roi': 175.5,
        'backtest_profit': 9290,
        'backtest_black_years': '4/6',
    },

    # 【2026-01-08追加】児島×C×B1×30-50倍
    # 探索結果: ROI 184.3%, +13,650円, 直近3年連続黒字
    {
        'id': 'C_Kojima_B1',
        'priority': 8,
        'name': '児島×C×B1×30-50',
        'confidence': 'C',
        'c1_rank': ['B1'],
        'odds_min': 30,
        'odds_max': 50,
        'venue_filter': [16],  # 児島のみ
        'description': '児島×C×B1級×30-50倍（直近3年連続黒字）',
        'use_pattern_h': True,  # パターンH（高オッズ帯）
        'version': '1.0',
        'added_date': '2026-01-08',
        'backtest_period': '2020-2025',
        'backtest_roi': 125.7,
        'backtest_profit': 18400,
        'backtest_black_years': '5/6',
    },

    # ----------------------------------------------------------------
    # D条件
    # ----------------------------------------------------------------
    {
        'id': 'D_40_50_B1',
        'priority': 9,
        'name': 'D×40-50×B1×2連率20-30%',
        'confidence': 'D',
        'c1_rank': ['B1'],
        'odds_min': 40,
        'odds_max': 50,
        'venue_filter': None,
        'c1_second_rate_min': 20,
        'c1_second_rate_max': 30,
        'month_exclude': [2, 4],  # 2月・4月除外（2026-02-16追加、季節調整）
        'description': 'D×B1級×40-50倍×2連率20-30%（2月・4月除外）',
        'use_pattern_h': False,  # 1点買い
        'version': '1.1',  # 季節調整対応
        'added_date': '2026-01-08',
        'backtest_period': '2020-2025',
        'backtest_roi': 135.2,
        'backtest_profit': 9210,
        'backtest_black_years': '5/6',
    },

    # 【2026-01-13更新】A2級を除外（6年間ROI 23.8%, -19,800円の大赤字）
    # 変更前: 全級別, 493件, ROI 142.9%, 収支+50,530円, 5/6年黒字
    # 変更後: A2除外, 379件, ROI 176.6%, 収支+70,330円, 5/6年黒字
    {
        'id': 'D_course5',
        'priority': 10,
        'name': 'D×5コース予測×A2除外+会場最適化',
        'confidence': 'D',
        'c1_rank': ['A1', 'B1', 'B2'],  # A2除外（2026-01-13）
        'odds_min': 10,
        'odds_max': 200,
        # 【2026-02-13更新】正確な会場別分析に基づく4会場（ROI≥150%, サンプル≥20）
        # 多摩川(412%,29件),浜名湖(160%,164件),桐生(156%,57件),平和島(154%,65件)
        'venue_filter': [5, 6, 1, 4],
        'predicted_course': 5,
        'month_exclude': [2, 4],  # 2月・4月除外（2026-02-16追加、季節調整）
        'description': 'D×5コース予測×A2除外×4会場（2月・4月除外）',
        'use_pattern_h': True,  # パターンH
        'version': '1.2',  # 季節調整対応
        'added_date': '2026-01-13',
        'backtest_period': '2020-2025',
        'backtest_roi': 176.6,
        'backtest_profit': 70330,
        'backtest_black_years': '5/6',
    },

    # ----------------------------------------------------------------
    # B2条件（市場との差を活用）
    # ----------------------------------------------------------------
    # 【2026-02-13一時無効化】Tier 3検証のため
    # 【2026-02-12追加】B2×20-30倍（予測1-3位のB2級）
    # 検証結果: 785件, ROI 135.0%, +109,960円, 黒字5/6年
    # 年度別: 2020:-25,960円, 2021-2025:連続黒字
    # {
    #     'id': 'B2_20_30',
    #     'name': 'B2×20-30倍×会場限定',
    #     'confidence': None,  # 全信頼度
    #     'c1_rank': ['A1', 'A2', 'B1', 'B2'],  # 全級別（predicted_rank_has_classで絞る）
    #     'predicted_rank_has_class': ['B2級'],  # 予測1-3位のいずれかがB2級
    #     'predicted_rank_range': [1, 3],
    #     'odds_min': 20,
    #     'odds_max': 30,
    #     'venue_filter': [23, 10],  # 唐津,三国（2026-02-13追加、芦屋-24,000円損失源除外）
    #     'description': 'B2級×20-30倍×会場（唐津,三国）',
    #     'use_pattern_h': False,  # 1点買い
    #     'version': '1.1',
    #     'added_date': '2026-02-12',
    #     'backtest_period': '2020-2025',
    #     'backtest_roi': 133.1,
    #     'backtest_profit': 29170,
    #     'backtest_black_years': '5/6',
    # },
]

# ============================================================
# フィルター閾値の一元管理
# ============================================================
FILTER_THRESHOLDS = {
    'escape_rate_min_default': 0.70,
    'bias_index_max_default': -0.3,
    'motor_second_rate_min_default': 40,
}

# ============================================================
# ヘルパー関数
# ============================================================
def get_conditions_by_confidence(confidence: str) -> List[Dict]:
    """信頼度で条件をフィルタリング"""
    return [c for c in STANDARD_BET_CONDITIONS if c.get('confidence') == confidence]

def get_condition_by_id(condition_id: str) -> Optional[Dict]:
    """条件IDで検索"""
    return next((c for c in STANDARD_BET_CONDITIONS if c['id'] == condition_id), None)

def validate_conditions() -> bool:
    """条件定義の整合性チェック"""
    # 重複ID検査
    ids = [c['id'] for c in STANDARD_BET_CONDITIONS]
    if len(ids) != len(set(ids)):
        raise ValueError("重複した条件IDが存在します")

    # 必須フィールド検査
    required_fields = ['id', 'name', 'confidence', 'c1_rank', 'odds_min', 'odds_max']
    for cond in STANDARD_BET_CONDITIONS:
        for field in required_fields:
            if field not in cond and field != 'confidence':  # confidenceはNoneを許容
                raise ValueError(f"条件 {cond.get('id', 'unknown')} に必須フィールド {field} がありません")

    return True

# 起動時に検証
if __name__ == '__main__':
    try:
        validate_conditions()
        print(f"✅ 条件定義の検証成功: {len(STANDARD_BET_CONDITIONS)}条件")
        print(f"バージョン: {CONDITION_VERSION}")
        print(f"最終更新: {LAST_UPDATED}")
    except Exception as e:
        print(f"❌ 条件定義のエラー: {e}")
