"""
予想バックテストページ
"""
import streamlit as st
import sys
import os
from datetime import datetime, timedelta
import pandas as pd


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from backtest_prediction import PredictionBacktester


def render_backtest_page():
    """バックテストページのレンダリング"""
    st.header("🧪 予想バックテスト")
    st.markdown("収集済みの過去データを使って予想ロジックの精度を検証")

    # 説明
    with st.expander("💡 バックテストとは", expanded=False):
        st.markdown("""
        **バックテストとは**

        過去のレースデータを使って、予想ロジックがどれくらい的中するかを検証する機能です。

        **仕組み:**
        1. 過去のレースを取得
        2. 結果を隠した状態で予想を実行
        3. 実際の結果と比較して的中率を計算

        **現在の予想ロジック:**
        - コース別基礎点（1コースが最も有利）
        - 選手級別・勝率
        - モーター2連率
        - 展示タイム（直進タイム）

        これらを総合的に評価してスコアリングし、最もスコアの高い艇を予想します。
        """)

    # パラメータ設定
    st.subheader("📅 テスト期間設定")

    col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input(
            "開始日",
            value=datetime.now() - timedelta(days=180),  # 6ヶ月に拡張
            key="backtest_start_date"
        )

    with col2:
        end_date = st.date_input(
            "終了日",
            value=datetime.now() - timedelta(days=1),
            key="backtest_end_date"
        )

    # 会場選択
    venue_option = st.selectbox(
        "会場",
        ["全会場"] + [f"{i:02d}" for i in range(1, 25)],
        key="backtest_venue"
    )

    venue_code = None if venue_option == "全会場" else venue_option

    # 実行ボタン
    st.markdown("---")

    if st.button("🚀 バックテスト実行", type="primary", use_container_width=True):
        if start_date >= end_date:
            st.error("開始日は終了日より前に設定してください")
            return

        # バックテスト実行
        with st.spinner("バックテスト実行中..."):
            backtester = PredictionBacktester()

            # プログレスバー用のプレースホルダー
            progress_placeholder = st.empty()
            status_placeholder = st.empty()

            result = backtester.run_backtest(
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d'),
                venue_code
            )

        if not result:
            st.error("テスト対象のレースが見つかりませんでした")
            return

        # 結果表示
        st.success("バックテスト完了!")

        st.markdown("---")
        st.subheader("📊 総合結果")

        # メトリクス表示
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "テスト実施レース数",
                f"{result['total_races']:,}"
            )

        with col2:
            st.metric(
                "単勝的中数",
                f"{result['win_hits']:,}",
                delta=f"{result['win_rate']*100:.1f}%"
            )

        with col3:
            st.metric(
                "単勝的中率",
                f"{result['win_rate']*100:.2f}%"
            )

        with col4:
            st.metric(
                "複勝的中率",
                f"{result['place_rate']*100:.2f}%"
            )

        # 会場別結果
        if result['venue_stats'] and len(result['venue_stats']) > 1:
            st.markdown("---")
            st.subheader("🏟️ 会場別的中率")

            venue_data = []
            for venue_code, stats in sorted(result['venue_stats'].items()):
                win_rate = stats['win_hits'] / stats['total'] * 100 if stats['total'] > 0 else 0
                venue_data.append({
                    '会場': venue_code,
                    'テスト数': stats['total'],
                    '的中数': stats['win_hits'],
                    '的中率': f"{win_rate:.1f}%",
                    '的中率(数値)': win_rate
                })

            df_venue = pd.DataFrame(venue_data)

            # 横棒グラフ
            st.bar_chart(df_venue.set_index('会場')['的中率(数値)'])

            # テーブル
            st.dataframe(
                df_venue[['会場', 'テスト数', '的中数', '的中率']],
                use_container_width=True,
                hide_index=True
            )

        # 詳細結果
        st.markdown("---")
        st.subheader("📋 詳細結果")

        # 最新20件を表示
        if result['results']:
            detail_data = []

            for r in result['results'][:20]:
                race = r['race']
                evaluation = r['evaluation']

                detail_data.append({
                    '日付': race['race_date'],
                    '会場': race['venue_code'],
                    'R': race['race_number'],
                    '予想': evaluation['predicted_winner'],
                    '結果': evaluation['actual_winner'],
                    '単勝': '○' if evaluation['win_hit'] else '×',
                    '複勝': '○' if evaluation['place_hit'] else '×'
                })

            df_detail = pd.DataFrame(detail_data)

            st.dataframe(
                df_detail,
                use_container_width=True,
                hide_index=True
            )

            st.caption(f"表示: 最新20件 / 全{len(result['results'])}件")

            # CSV出力
            if st.button("📥 全結果をCSVでダウンロード"):
                full_data = []

                for r in result['results']:
                    race = r['race']
                    evaluation = r['evaluation']

                    full_data.append({
                        '日付': race['race_date'],
                        '会場': race['venue_code'],
                        'レース': race['race_number'],
                        '予想': evaluation['predicted_winner'],
                        '結果': evaluation['actual_winner'],
                        '単勝': '○' if evaluation['win_hit'] else '×',
                        '複勝': '○' if evaluation['place_hit'] else '×',
                        '予想トップ3': ','.join(map(str, evaluation['predicted_top3'])),
                        '実際トップ3': ','.join(map(str, evaluation['actual_top3']))
                    })

                df_full = pd.DataFrame(full_data)

                csv = df_full.to_csv(index=False, encoding='utf-8-sig')

                st.download_button(
                    label="💾 CSVダウンロード",
                    data=csv,
                    file_name=f"backtest_{start_date}_{end_date}.csv",
                    mime="text/csv"
                )

        # 考察
        st.markdown("---")
        st.subheader("💭 考察")

        considerations = []

        if result['win_rate'] >= 0.30:
            considerations.append("✅ 単勝的中率30%以上 - 良好な予想精度")
        elif result['win_rate'] >= 0.20:
            considerations.append("⚠️ 単勝的中率20%台 - 改善の余地あり")
        else:
            considerations.append("❌ 単勝的中率20%未満 - 予想ロジックの見直しが必要")

        if result['place_rate'] >= 0.60:
            considerations.append("✅ 複勝的中率60%以上 - 上位予想は安定")
        elif result['place_rate'] >= 0.50:
            considerations.append("⚠️ 複勝的中率50%台 - まずまずの精度")

        # 会場別のバラつき
        if result['venue_stats']:
            venue_rates = [
                stats['win_hits'] / stats['total']
                for stats in result['venue_stats'].values()
                if stats['total'] >= 10
            ]

            if venue_rates:
                max_rate = max(venue_rates)
                min_rate = min(venue_rates)
                diff = (max_rate - min_rate) * 100

                if diff > 10:
                    considerations.append(f"📊 会場による的中率の差が大きい（{diff:.1f}ポイント）- 会場別のパラメータ調整が有効かも")

        for consideration in considerations:
            st.markdown(f"- {consideration}")

        # 改善案
        with st.expander("💡 予想精度向上のヒント", expanded=False):
            st.markdown("""
            **予想精度を向上させるには:**

            1. **重み付けの調整**
               - 現在のスコアリング重みを調整
               - 会場ごとに異なる重み付けを適用

            2. **追加要素の検討**
               - 風向・風速の影響
               - 潮位の影響
               - 時間帯による傾向
               - 選手の相性

            3. **機械学習の導入**
               - 過去データから最適なパラメータを学習
               - より複雑なパターンを認識

            4. **場攻略情報の活用**
               - ボーターズ情報をスコアリングに反映
               - 会場別の特性を考慮
            """)
