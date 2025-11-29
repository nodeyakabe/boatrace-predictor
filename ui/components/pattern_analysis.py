"""
パターン分析UIコンポーネント

プリセットルールと発見されたパターンを表示・管理
"""

import streamlit as st
import sqlite3
import pandas as pd
import json
from config.settings import DATABASE_PATH


def render_pattern_analysis_page():
    """パターン分析ページをレンダリング"""
    st.subheader("🔍 パターン分析")

    # サブメニュー
    analysis_type = st.radio(
        "表示内容",
        ["プリセットルール", "発見されたパターン", "パターン検索"],
        horizontal=True
    )

    st.markdown("---")

    if analysis_type == "プリセットルール":
        render_preset_rules()
    elif analysis_type == "発見されたパターン":
        render_discovered_patterns()
    elif analysis_type == "パターン検索":
        render_pattern_search()


def render_preset_rules():
    """プリセットルール（複合条件バフ）を表示"""
    st.markdown("### 📋 プリセットルール（複合条件バフ）")
    st.info("複数の条件が組み合わさった時に発生するバフ/デバフのルールです。予測スコアに自動適用されます。")

    try:
        from src.analysis.compound_buff_system import CompoundBuffSystem
        system = CompoundBuffSystem(DATABASE_PATH)
        rules = system.get_all_rules()

        if not rules:
            st.warning("プリセットルールがありません")
            return

        # ルール数表示
        active_count = sum(1 for r in rules if r['is_active'])
        st.metric(f"ルール数", f"{active_count} / {len(rules)} 有効")

        # フィルター
        col1, col2 = st.columns(2)
        with col1:
            show_active_only = st.checkbox("有効ルールのみ表示", value=True)
        with col2:
            buff_filter = st.selectbox(
                "バフタイプ",
                ["すべて", "プラスバフのみ", "マイナスバフのみ"]
            )

        # フィルタリング
        filtered_rules = rules
        if show_active_only:
            filtered_rules = [r for r in filtered_rules if r['is_active']]
        if buff_filter == "プラスバフのみ":
            filtered_rules = [r for r in filtered_rules if r['buff_value'] > 0]
        elif buff_filter == "マイナスバフのみ":
            filtered_rules = [r for r in filtered_rules if r['buff_value'] < 0]

        # ルール一覧
        st.markdown("---")

        for rule in sorted(filtered_rules, key=lambda x: abs(x['buff_value']), reverse=True):
            buff_color = "🔺" if rule['buff_value'] > 0 else "🔻"
            status_icon = "✅" if rule['is_active'] else "⏸️"

            with st.expander(
                f"{status_icon} {buff_color} **{rule['name']}** ({rule['buff_value']:+.1f}点)",
                expanded=False
            ):
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("バフ値", f"{rule['buff_value']:+.1f}点")
                with col2:
                    st.metric("信頼度", f"{rule['confidence']*100:.0f}%")
                with col3:
                    st.metric("的中率", f"{rule['hit_rate']*100:.1f}%")

                st.markdown(f"**説明:** {rule['description']}")
                st.markdown(f"**サンプル数:** {rule['sample_count']:,}件")
                st.markdown(f"**条件数:** {rule['condition_count']}条件")
                st.markdown(f"**ルールID:** `{rule['rule_id']}`")

        st.markdown("---")
        st.caption(f"表示中: {len(filtered_rules)}件 / 全{len(rules)}件")

    except ImportError as e:
        st.error(f"CompoundBuffSystemの読み込みに失敗: {e}")
    except Exception as e:
        st.error(f"エラー: {e}")


def render_discovered_patterns():
    """発見されたパターンを表示"""
    st.markdown("### 🔬 発見されたパターン")
    st.info("データ分析により統計的に有意と判定されたパターンです。")

    try:
        conn = sqlite3.connect(DATABASE_PATH)

        # パターンテーブルが存在するか確認
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='discovered_patterns'
        """)
        if not cursor.fetchone():
            st.warning("パターン分析がまだ実行されていません。scripts/analyze_venue_patterns.py を実行してください。")
            conn.close()
            return

        # 統計情報
        cursor.execute("SELECT COUNT(*) FROM discovered_patterns")
        total_patterns = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM discovered_patterns WHERE is_active = 1")
        active_patterns = cursor.fetchone()[0]

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("総パターン数", f"{total_patterns:,}")
        with col2:
            st.metric("有効パターン", f"{active_patterns:,}")
        with col3:
            cursor.execute("SELECT AVG(reliability_score) FROM discovered_patterns WHERE is_active = 1")
            avg_reliability = cursor.fetchone()[0] or 0
            st.metric("平均信頼性", f"{avg_reliability:.0f}")

        st.markdown("---")

        # フィルター
        col1, col2, col3 = st.columns(3)

        with col1:
            # 会場フィルター
            cursor.execute("SELECT DISTINCT venue_code FROM discovered_patterns ORDER BY venue_code")
            venue_codes = [row[0] for row in cursor.fetchall()]
            venue_filter = st.selectbox(
                "会場",
                ["すべて"] + venue_codes
            )

        with col2:
            # パターンタイプ
            cursor.execute("SELECT DISTINCT pattern_type FROM discovered_patterns ORDER BY pattern_type")
            pattern_types = [row[0] for row in cursor.fetchall()]
            type_filter = st.selectbox(
                "パターンタイプ",
                ["すべて"] + pattern_types
            )

        with col3:
            # 最小信頼性
            min_reliability = st.slider("最小信頼性スコア", 0, 100, 60)

        # ソート
        sort_option = st.radio(
            "ソート",
            ["信頼性スコア順", "勝率順", "リフト順", "サンプル数順"],
            horizontal=True
        )

        sort_mapping = {
            "信頼性スコア順": "reliability_score DESC",
            "勝率順": "win_rate DESC",
            "リフト順": "lift DESC",
            "サンプル数順": "sample_count DESC"
        }

        # クエリ構築
        query = """
            SELECT
                pattern_id, pattern_type, venue_code, description,
                sample_count, win_rate, baseline_rate, lift,
                confidence_interval_low, confidence_interval_high,
                p_value, effect_size, reliability_score, is_active
            FROM discovered_patterns
            WHERE reliability_score >= ?
        """
        params = [min_reliability]

        if venue_filter != "すべて":
            query += " AND venue_code = ?"
            params.append(venue_filter)

        if type_filter != "すべて":
            query += " AND pattern_type = ?"
            params.append(type_filter)

        query += f" ORDER BY {sort_mapping[sort_option]} LIMIT 100"

        df = pd.read_sql_query(query, conn, params=params)

        if df.empty:
            st.warning("条件に一致するパターンがありません")
            conn.close()
            return

        st.markdown("---")
        st.markdown(f"**{len(df)}件のパターンが見つかりました**")

        # パターン一覧を表示
        for idx, row in df.iterrows():
            reliability = row['reliability_score']

            # 信頼性に応じた色
            if reliability >= 80:
                badge = "🟢"
            elif reliability >= 60:
                badge = "🟡"
            else:
                badge = "🟠"

            with st.expander(
                f"{badge} **{row['description']}** (信頼性: {reliability:.0f})",
                expanded=False
            ):
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("勝率", f"{row['win_rate']*100:.1f}%")
                with col2:
                    st.metric("基準勝率", f"{row['baseline_rate']*100:.1f}%")
                with col3:
                    lift_value = row['lift']
                    st.metric("リフト", f"{lift_value:.2f}x")
                with col4:
                    st.metric("サンプル数", f"{row['sample_count']:,}")

                # 詳細情報
                st.markdown("**詳細:**")
                st.write(f"- 信頼区間: {row['confidence_interval_low']*100:.1f}% - {row['confidence_interval_high']*100:.1f}%")
                st.write(f"- p値: {row['p_value']:.4f}")
                st.write(f"- 効果量: {row['effect_size']:.2f}点")
                st.write(f"- パターンタイプ: {row['pattern_type']}")
                st.write(f"- 会場コード: {row['venue_code']}")
                st.write(f"- パターンID: `{row['pattern_id']}`")

                # 推奨アクション
                if row['effect_size'] >= 5:
                    st.success(f"💡 推奨: このパターンに該当する場合、+{row['effect_size']:.1f}点のバフが有効")

        conn.close()

    except Exception as e:
        st.error(f"エラー: {e}")
        import traceback
        st.code(traceback.format_exc())


def render_pattern_search():
    """パターン検索機能"""
    st.markdown("### 🔎 パターン検索")
    st.info("条件を指定してパターンを検索します。")

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # テーブル確認
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='discovered_patterns'
        """)
        if not cursor.fetchone():
            st.warning("パターン分析がまだ実行されていません。")
            conn.close()
            return

        # 会場名マッピング
        VENUE_NAMES = {
            "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
            "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
            "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
            "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
            "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
            "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村"
        }

        # 検索フォーム
        col1, col2 = st.columns(2)

        with col1:
            venue_options = ["指定なし"] + [f"{code}: {name}" for code, name in VENUE_NAMES.items()]
            selected_venue = st.selectbox("会場を選択", venue_options)

            if selected_venue != "指定なし":
                venue_code = selected_venue.split(":")[0]
            else:
                venue_code = None

        with col2:
            course = st.selectbox("コース", ["指定なし", "1", "2", "3", "4", "5", "6"])
            if course == "指定なし":
                course = None

        col3, col4 = st.columns(2)

        with col3:
            pattern_type = st.selectbox(
                "パターンタイプ",
                ["指定なし", "kimarite", "tide", "tide_kimarite"]
            )
            if pattern_type == "指定なし":
                pattern_type = None

        with col4:
            keyword = st.text_input("キーワード検索（説明文から）", "")

        # 検索実行
        if st.button("🔍 検索", type="primary"):
            query = """
                SELECT
                    pattern_id, pattern_type, venue_code, description,
                    sample_count, win_rate, baseline_rate, lift,
                    reliability_score, effect_size
                FROM discovered_patterns
                WHERE is_active = 1
            """
            params = []

            if venue_code:
                query += " AND venue_code = ?"
                params.append(venue_code)

            if course:
                query += " AND description LIKE ?"
                params.append(f"%{course}コース%")

            if pattern_type:
                query += " AND pattern_type = ?"
                params.append(pattern_type)

            if keyword:
                query += " AND description LIKE ?"
                params.append(f"%{keyword}%")

            query += " ORDER BY reliability_score DESC LIMIT 50"

            df = pd.read_sql_query(query, conn, params=params)

            if df.empty:
                st.warning("条件に一致するパターンが見つかりませんでした")
            else:
                st.success(f"✅ {len(df)}件のパターンが見つかりました")

                # 結果をテーブル表示
                display_df = df[['description', 'win_rate', 'baseline_rate', 'lift', 'reliability_score', 'sample_count']].copy()
                display_df.columns = ['パターン', '勝率', '基準勝率', 'リフト', '信頼性', 'サンプル数']
                display_df['勝率'] = display_df['勝率'].apply(lambda x: f"{x*100:.1f}%")
                display_df['基準勝率'] = display_df['基準勝率'].apply(lambda x: f"{x*100:.1f}%")
                display_df['リフト'] = display_df['リフト'].apply(lambda x: f"{x:.2f}x")
                display_df['信頼性'] = display_df['信頼性'].apply(lambda x: f"{x:.0f}")
                display_df['サンプル数'] = display_df['サンプル数'].apply(lambda x: f"{x:,}")

                st.dataframe(display_df, use_container_width=True, hide_index=True)

                # 推奨パターンをハイライト
                high_reliability = df[df['reliability_score'] >= 70]
                if not high_reliability.empty:
                    st.markdown("---")
                    st.markdown("### ⭐ 高信頼性パターン（信頼性70以上）")

                    for idx, row in high_reliability.iterrows():
                        venue_name = VENUE_NAMES.get(row['venue_code'], row['venue_code'])
                        st.markdown(f"""
                        **{row['description']}**
                        - 会場: {venue_name}
                        - 勝率: {row['win_rate']*100:.1f}% (基準: {row['baseline_rate']*100:.1f}%)
                        - リフト: {row['lift']:.2f}x
                        - 信頼性: {row['reliability_score']:.0f}
                        - 推奨バフ: +{row['effect_size']:.1f}点
                        """)

        conn.close()

    except Exception as e:
        st.error(f"エラー: {e}")
        import traceback
        st.code(traceback.format_exc())


if __name__ == "__main__":
    render_pattern_analysis_page()
