"""
改善機能表示コンポーネント
Laplace平滑化、1着固定、信頼度フィルタなどの改善情報を表示
"""
import streamlit as st
import pandas as pd
from typing import Dict, List, Optional
import json
from pathlib import Path

from src.analysis.smoothing import LaplaceSmoothing
from src.analysis.first_place_lock import FirstPlaceLockAnalyzer
from src.analysis.confidence_filter import ConfidenceFilter
from src.analysis.motor_ewma import MotorEWMA


def render_improvement_badges(prediction: Dict) -> str:
    """
    予測に適用された改善機能のバッジを生成

    Args:
        prediction: 予測結果辞書

    Returns:
        HTMLバッジ文字列
    """
    badges = []

    # Laplace平滑化が適用されているか
    if prediction.get('smoothing_applied'):
        badges.append('🔧 平滑化')

    # 1着固定マークがついているか
    if prediction.get('first_place_locked'):
        badges.append('🔒 1着固定')

    # 較正が適用されているか
    if prediction.get('calibration_applied'):
        badges.append('📊 較正済')

    # EWMA適用
    if prediction.get('ewma_applied'):
        badges.append('📈 EWMA')

    return ' '.join(badges) if badges else ''


def render_improvement_panel():
    """改善機能の設定パネルを表示"""

    st.subheader("⚙️ 改善機能の設定")

    # 設定ファイルのパスを取得
    config_path = Path(__file__).parent.parent.parent / 'config' / 'prediction_improvements.json'

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        st.error(f"設定ファイル読み込みエラー: {e}")
        return

    # 各改善機能の状態を表示
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 即効性改善")

        # 1. Laplace平滑化
        laplace_enabled = config['laplace_smoothing']['enabled']
        st.markdown(f"**🔧 Laplace平滑化**")
        st.write(f"状態: {'✅ 有効' if laplace_enabled else '❌ 無効'}")
        if laplace_enabled:
            st.write(f"alpha値: {config['laplace_smoothing']['alpha']}")
            st.caption("外枠のゼロ化問題を解決")

        st.markdown("---")

        # 2. 1着固定ルール
        lock_enabled = config['first_place_lock']['enabled']
        st.markdown(f"**🔒 1着固定ルール**")
        st.write(f"状態: {'✅ 有効' if lock_enabled else '❌ 無効'}")
        if lock_enabled:
            st.write(f"閾値: {config['first_place_lock']['win_rate_threshold']}")
            st.write(f"最小データ充実度: {config['first_place_lock']['min_data_completeness']}")
            st.caption("高勝率1号艇を1着固定")

        st.markdown("---")

        # 3. 信頼度フィルタ
        filter_enabled = config['confidence_filter']['enabled']
        st.markdown(f"**🚫 信頼度Eフィルタ**")
        st.write(f"状態: {'✅ 有効' if filter_enabled else '❌ 無効'}")
        if filter_enabled:
            st.write(f"除外: {'E判定' if config['confidence_filter']['exclude_e_level'] else 'なし'}")
            st.write(f"最小表示レベル: {config['confidence_filter']['min_display_level']}")
            st.caption("低信頼度予測を除外")

    with col2:
        st.markdown("### 中長期改善")

        # 5. モーターEWMA
        ewma_enabled = config['motor_ewma']['enabled']
        st.markdown(f"**📈 モーターEWMA**")
        st.write(f"状態: {'✅ 有効' if ewma_enabled else '❌ 無効'}")
        if ewma_enabled:
            st.write(f"alpha値: {config['motor_ewma']['alpha']}")
            st.caption("直近の調子を重視")

        st.markdown("---")

        # 6. 潮位補正
        tide_enabled = config['tide_adjustment']['enabled']
        st.markdown(f"**🌊 潮位補正**")
        st.write(f"状態: {'✅ 有効' if tide_enabled else '❌ 無効'}")
        if tide_enabled:
            st.caption("8会場の潮位影響を補正")

        st.markdown("---")

        # 10. 確率較正
        calibration_enabled = config['probability_calibration']['enabled']
        st.markdown(f"**📊 確率較正**")
        st.write(f"状態: {'✅ 有効' if calibration_enabled else '❌ 無効'}")
        if calibration_enabled:
            st.caption("予測確率を実績に合わせて調整")


def render_smoothing_details(predictions: List[Dict]):
    """
    Laplace平滑化の効果を表示

    Args:
        predictions: 予測結果リスト
    """
    st.subheader("🔧 Laplace平滑化の効果")

    # 平滑化が適用されている予測を抽出
    smoothed = [p for p in predictions if p.get('smoothing_applied')]

    if not smoothed:
        st.info("この予測には平滑化は適用されていません")
        return

    st.success(f"{len(smoothed)}艇に平滑化を適用")

    # 効果を表格で表示
    data = []
    for p in smoothed:
        if 'raw_win_rate' in p and 'estimated_win_rate' in p:
            data.append({
                '艇番': p['pit_number'],
                '選手': p.get('racer_name', '不明'),
                '元の勝率': f"{p['raw_win_rate']:.1f}%",
                '平滑化後': f"{p['estimated_win_rate']:.1f}%",
                '差分': f"+{p['estimated_win_rate'] - p['raw_win_rate']:.1f}%"
            })

    if data:
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.caption("💡 データ不足の艇ほど大きく補正されます")


def render_first_place_lock_details(predictions: List[Dict]):
    """
    1着固定ルールの詳細を表示

    Args:
        predictions: 予測結果リスト
    """
    st.subheader("🔒 1着固定ルール")

    # 1号艇の予測を取得
    pit1 = next((p for p in predictions if p['pit_number'] == 1), None)

    if not pit1:
        st.warning("1号艇のデータがありません")
        return

    # FirstPlaceLockAnalyzerを使用して判定
    lock_analyzer = FirstPlaceLockAnalyzer()

    # 推定勝率を取得（仮に total_score から計算）
    estimated_win_rate = pit1.get('estimated_win_rate', pit1['total_score'] / 100.0)
    data_completeness = pit1.get('data_completeness_score', 50)

    result = lock_analyzer.should_lock_first_place(
        pit_number=1,
        estimated_win_rate=estimated_win_rate,
        data_completeness_score=data_completeness
    )

    if result['should_lock']:
        st.success(f"✅ 1着固定条件を満たしています")
        st.write(f"理由: {result['reason']}")
        st.metric("推定勝率", f"{estimated_win_rate:.1%}")
        st.metric("データ充実度", f"{data_completeness:.0f}")
        st.info("💰 この1号艇は鉄板です！")
    else:
        st.info(f"❌ 1着固定条件を満たしていません")
        st.write(f"理由: {result['reason']}")
        st.metric("推定勝率", f"{estimated_win_rate:.1%}")
        st.metric("データ充実度", f"{data_completeness:.0f}")


def render_motor_ewma_details(venue_code: str, motor_numbers: List[int]):
    """
    モーターEWMAの詳細を表示

    Args:
        venue_code: 会場コード
        motor_numbers: モーター番号のリスト
    """
    st.subheader("📈 モーター調子（EWMA分析）")

    motor_ewma = MotorEWMA()

    if not motor_ewma.enabled:
        st.info("モーターEWMAは無効になっています")
        st.caption("config/prediction_improvements.json で有効化できます")
        return

    st.success("✅ モーターEWMAが有効です")

    # 各モーターの状態を表示
    data = []
    for i, motor_num in enumerate(motor_numbers, 1):
        summary = motor_ewma.get_motor_condition_summary(venue_code, motor_num)
        ewma_info = motor_ewma.calculate_motor_ewma(venue_code, motor_num)

        data.append({
            '艇番': i,
            'モーター': motor_num,
            '状態': summary,
            'EWMAスコア': f"{ewma_info['ewma_score']:.1f}",
            '傾向': ewma_info['recent_trend'],
            'レース数': ewma_info['total_races']
        })

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.caption("💡 EWMAスコアは直近の成績を重視した指標です（50が基準）")


def render_confidence_filter_info(predictions: List[Dict]):
    """
    信頼度フィルタの情報を表示

    Args:
        predictions: 予測結果リスト
    """
    st.subheader("🚫 信頼度フィルタ")

    confidence_filter = ConfidenceFilter()

    if not confidence_filter.enabled:
        st.info("信頼度フィルタは無効になっています")
        return

    st.success("✅ 信頼度フィルタが有効です")

    # フィルタ設定を表示
    st.write(f"E判定除外: {'はい' if confidence_filter.exclude_e_level else 'いいえ'}")
    st.write(f"最小表示レベル: {confidence_filter.min_display_level}")

    # 予測の信頼度分布を表示
    confidence_dist = {}
    for p in predictions:
        conf = p.get('confidence', 'E')
        confidence_dist[conf] = confidence_dist.get(conf, 0) + 1

    st.markdown("**信頼度分布:**")
    for level in ['A', 'B', 'C', 'D', 'E']:
        count = confidence_dist.get(level, 0)
        if count > 0:
            bar = '█' * count
            st.write(f"{level}: {bar} ({count}艇)")


def render_improvements_summary_page():
    """改善機能のサマリーページ（設定・管理タブ用）"""

    st.header("📈 予測精度改善機能")

    st.markdown("""
    このシステムには10項目の予測精度改善機能が実装されています。
    各機能の状態と効果を確認できます。
    """)

    # タブで分類
    tab1, tab2, tab3 = st.tabs(["💡 即効性改善", "🔧 中長期改善", "📊 評価指標"])

    with tab1:
        st.markdown("### 即効性の高い改善（1-4）")

        st.markdown("""
        #### 1. Laplace平滑化（alpha=2.0）
        - **目的**: 外枠（4-6号艇）のゼロ化問題を解決
        - **効果**: 0勝/2レース → 33.3%に救済
        - **設定**: `config/prediction_improvements.json`

        #### 2. 1着固定ルール（閾値0.55）
        - **目的**: 高勝率1号艇を1着確定とマーク
        - **閾値**: 勝率55%以上 + データ充実度60以上
        - **効果**: 約50-60%のレースに適用可能

        #### 3. 信頼度Eフィルタ
        - **目的**: 低信頼度予測を除外
        - **効果**: E判定を完全除外し、運用可能なレースのみ表示

        #### 4. 評価指標の追加
        - **指標**: Brier Score、Log Loss、ECE、信頼度別的中率
        - **目的**: 予測精度を定量的に評価
        """)

    with tab2:
        st.markdown("### 中長期的な改善（5-10）")

        st.markdown("""
        #### 5. 進入予想（前付け傾向）
        - **目的**: 選手の進入変化傾向を分析
        - **効果**: 1着固定を外すべきかを判定

        #### 6. 潮位補正ロジック
        - **対象**: 8会場（江戸川、浜名湖、鳴門、若松、芦屋、福岡、唐津、大村）
        - **効果**: 潮位による各コースへの影響を補正

        #### 7. DBインデックス最適化
        - **目的**: クエリパフォーマンス向上
        - **効果**: 12個の複合インデックスを追加

        #### 8. モーター指数加重移動平均（EWMA）
        - **alpha値**: 0.3（デフォルト）
        - **効果**: 直近のレース結果に大きな重みを付けて評価

        #### 9. 展示データ自動取得
        - **状態**: テンプレート実装済み
        - **TODO**: 実際のURL・HTML構造に応じた実装が必要

        #### 10. 確率較正（Calibration）
        - **手法**: Isotonic Regression
        - **効果**: 予測確率を実際の頻度に合わせて調整
        """)

    with tab3:
        st.markdown("### 📊 評価指標")

        st.markdown("""
        実装された評価指標:

        1. **Brier Score**: 確率予測の精度（0に近いほど良い）
        2. **Log Loss**: 対数損失（0に近いほど良い）
        3. **ECE (Expected Calibration Error)**: 較正誤差（0に近いほど良い）
        4. **信頼度別的中率**: A/B/C/D/Eごとの的中率

        これらの指標を使って予測モデルの精度を定量的に評価できます。
        """)

    st.markdown("---")

    # 現在の設定を表示
    render_improvement_panel()

    st.markdown("---")

    # ドキュメントへのリンク
    st.info("📖 詳細は `docs/improvements_summary.md` を参照してください")
