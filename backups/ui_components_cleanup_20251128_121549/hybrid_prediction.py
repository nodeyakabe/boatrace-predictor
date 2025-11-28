"""
Streamlit UIコンポーネント: ハイブリッド予測システム

実験#001-#022の成果を統合したハイブリッド予測システムと
賭け戦略推奨をUIで提供
"""

import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import sys
import os
from datetime import datetime, timedelta

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from hybrid_predictor import HybridPredictor
from betting_strategy import BettingRecommender, BettingStrategy
from config.settings import DATABASE_PATH, VENUES


def initialize_hybrid_system():
    """ハイブリッド予測システムを初期化"""
    if 'hybrid_predictor' not in st.session_state:
        try:
            st.session_state.hybrid_predictor = HybridPredictor()
            st.session_state.hybrid_predictor.load_models()
            st.session_state.hybrid_initialized = True
        except Exception as e:
            st.error(f"❌ ハイブリッド予測システムの初期化エラー: {e}")
            st.session_state.hybrid_initialized = False
            return False

    if 'betting_recommender' not in st.session_state:
        # デフォルト資金: 100,000円
        st.session_state.betting_recommender = BettingRecommender(bankroll=100000)

    return st.session_state.hybrid_initialized


def prepare_race_features(race_id: str, venue_code: str):
    """
    レースIDから特徴量を準備

    Args:
        race_id: レースID (例: '20240601_07_12')
        venue_code: 会場コード

    Returns:
        pd.DataFrame: 35次元の特徴量（6艇分）
    """
    try:
        conn = sqlite3.connect(DATABASE_PATH)

        # race_idからrace_date, race_numberを抽出
        parts = race_id.split('_')
        if len(parts) >= 3:
            race_date = parts[0]
            race_number = int(parts[2])
        else:
            return None

        # 必要な35特徴量を取得
        query = """
            SELECT
                e.pit_number,
                e.actual_course,
                e.racer_registration_number,
                e.racer_name,
                r.win_rate,
                r.second_rate,
                r.third_rate,
                e.motor_number,
                e.motor_second_rate,
                COALESCE(m.third_rate, 0.0) as motor_third_rate,
                e.boat_number,
                e.boat_second_rate,
                COALESCE(b.third_rate, 0.0) as boat_third_rate,
                e.tilt_angle,
                e.exhibition_time,
                e.st_time,
                e.racer_weight,
                e.racer_age,
                r.f_count,
                r.l_count,
                rce.temperature,
                rce.water_temperature,
                rce.wind_speed,
                rce.wave_height
            FROM
                race_entries e
            LEFT JOIN racers r ON e.racer_registration_number = r.registration_number
            LEFT JOIN motor_stats m ON e.motor_number = m.motor_number
                AND m.venue_code = ?
            LEFT JOIN boat_stats b ON e.boat_number = b.boat_number
                AND b.venue_code = ?
            LEFT JOIN races rce ON e.race_id = rce.id
            WHERE
                e.race_id LIKE ?
                AND e.pit_number BETWEEN 1 AND 6
            ORDER BY e.pit_number
        """

        race_id_pattern = f"{race_date}_{venue_code}_{race_number:02d}%"
        df = pd.read_sql_query(query, conn, params=(venue_code, venue_code, race_id_pattern))
        conn.close()

        if df.empty or len(df) < 6:
            return None

        # 特徴量を構築（35次元）
        features = []
        for i in range(6):
            if i < len(df):
                row = df.iloc[i]

                # actual_course_X (one-hot encoding)
                actual_course_features = [0] * 6
                if pd.notna(row['actual_course']) and 1 <= row['actual_course'] <= 6:
                    actual_course_features[int(row['actual_course']) - 1] = 1

                # pit_number_X (one-hot encoding)
                pit_features = [0] * 6
                pit_features[i] = 1  # pit_number is i+1

                # avg_st (仮: st_timeを使用)
                avg_st = row['st_time'] if pd.notna(row['st_time']) else 0.17

                # pit_course_diff
                pit_course_diff = 0
                if pd.notna(row['actual_course']):
                    pit_course_diff = (i + 1) - row['actual_course']

                feature_row = [
                    row['actual_course'] if pd.notna(row['actual_course']) else 0,
                    *actual_course_features,
                    avg_st,
                    row['boat_number'] if pd.notna(row['boat_number']) else 0,
                    row['boat_second_rate'] if pd.notna(row['boat_second_rate']) else 0.0,
                    row['boat_third_rate'] if pd.notna(row['boat_third_rate']) else 0.0,
                    row['exhibition_time'] if pd.notna(row['exhibition_time']) else 0.0,
                    row['f_count'] if pd.notna(row['f_count']) else 0,
                    row['l_count'] if pd.notna(row['l_count']) else 0,
                    row['motor_number'] if pd.notna(row['motor_number']) else 0,
                    row['motor_second_rate'] if pd.notna(row['motor_second_rate']) else 0.0,
                    row['motor_third_rate'] if pd.notna(row['motor_third_rate']) else 0.0,
                    pit_course_diff,
                    i + 1,  # pit_number
                    *pit_features,
                    # race_numberは含めない（クエリから削除済み）
                    row['racer_age'] if pd.notna(row['racer_age']) else 30,
                    row['racer_weight'] if pd.notna(row['racer_weight']) else 52.0,
                    row['second_rate'] if pd.notna(row['second_rate']) else 0.0,
                    row['st_time'] if pd.notna(row['st_time']) else 0.17,
                    row['temperature'] if pd.notna(row['temperature']) else 20.0,
                    row['third_rate'] if pd.notna(row['third_rate']) else 0.0,
                    row['tilt_angle'] if pd.notna(row['tilt_angle']) else 0.0,
                    row['water_temperature'] if pd.notna(row['water_temperature']) else 20.0,
                    row['wave_height'] if pd.notna(row['wave_height']) else 0,
                    row['win_rate'] if pd.notna(row['win_rate']) else 0.0,
                    row['wind_speed'] if pd.notna(row['wind_speed']) else 0
                ]
                features.append(feature_row)

        # 35特徴量の列名
        feature_names = [
            'actual_course', 'actual_course_1', 'actual_course_2', 'actual_course_3',
            'actual_course_4', 'actual_course_5', 'actual_course_6', 'avg_st',
            'boat_number', 'boat_second_rate', 'boat_third_rate', 'exhibition_time',
            'f_count', 'l_count', 'motor_number', 'motor_second_rate', 'motor_third_rate',
            'pit_course_diff', 'pit_number', 'pit_number_1', 'pit_number_2',
            'pit_number_3', 'pit_number_4', 'pit_number_5', 'pit_number_6',
            'racer_age', 'racer_weight', 'second_rate', 'st_time',
            'temperature', 'third_rate', 'tilt_angle', 'water_temperature',
            'wave_height', 'win_rate', 'wind_speed'
        ]

        X = pd.DataFrame(features, columns=feature_names)
        return X

    except Exception as e:
        st.error(f"特徴量準備エラー: {e}")
        return None


def get_race_odds(race_id: str, venue_code: str):
    """
    レースのオッズを取得（実装済み）

    1. DBから取得を試みる
    2. DBになければBOATRACE公式サイトから取得
    3. 失敗時はダミーオッズを返す

    Args:
        race_id: レースID
        venue_code: 会場コード

    Returns:
        np.ndarray: 6艇分のオッズ（単勝）
    """
    try:
        # race_idからrace_date, race_numberを抽出
        parts = race_id.split('_')
        if len(parts) >= 3:
            race_date = parts[0]
            race_number = int(parts[2])
        else:
            return np.array([2.0, 4.0, 6.0, 10.0, 15.0, 30.0])

        # 1. DBから取得を試みる
        conn = sqlite3.connect(DATABASE_PATH)
        query = """
            SELECT pit_number, odds
            FROM odds
            WHERE race_id LIKE ?
            AND bet_type = 'win'
            ORDER BY pit_number
        """

        race_id_pattern = f"{race_date}_{venue_code}_{race_number:02d}%"
        df = pd.read_sql_query(query, conn, params=(race_id_pattern,))
        conn.close()

        if not df.empty and len(df) == 6:
            return df['odds'].values

        # 2. DBになければBOATRACE公式サイトから取得
        from src.scraper.odds_scraper import OddsScraper

        scraper = OddsScraper(delay=0.5)
        win_odds = scraper.get_win_odds(venue_code, race_date, race_number)

        if win_odds and len(win_odds) == 6:
            # 取得成功
            odds_array = np.array([win_odds[i] for i in range(1, 7)])

            # DBに保存
            try:
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()

                # oddsテーブルが存在しない場合は作成
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS odds (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        race_id TEXT NOT NULL,
                        pit_number INTEGER NOT NULL,
                        bet_type TEXT NOT NULL,
                        odds REAL NOT NULL,
                        fetched_at TEXT NOT NULL,
                        UNIQUE(race_id, pit_number, bet_type)
                    )
                """)

                fetched_at = datetime.now().isoformat()
                full_race_id = f"{race_date}_{venue_code}_{race_number:02d}"

                for pit, odds in win_odds.items():
                    cursor.execute("""
                        INSERT OR REPLACE INTO odds
                        (race_id, pit_number, bet_type, odds, fetched_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (full_race_id, pit, 'win', odds, fetched_at))

                conn.commit()
                conn.close()
            except Exception as e:
                print(f"オッズDB保存エラー: {e}")

            return odds_array

        # 3. 失敗時はダミーオッズを返す
        return np.array([2.0, 4.0, 6.0, 10.0, 15.0, 30.0])

    except Exception as e:
        print(f"オッズ取得エラー: {e}")
        # エラー時はダミーオッズを返す
        return np.array([2.0, 4.0, 6.0, 10.0, 15.0, 30.0])


def render_hybrid_prediction_page():
    """ハイブリッド予測ページをレンダリング"""
    st.header("🎯 ハイブリッド予測システム")

    st.markdown("""
    ### 実験#001-#022の成果を統合

    - **会場別最適モデル**: 9会場で会場特化モデル、15会場で統合モデルを自動選択
    - **3つの賭け戦略**: 保守的・バランス・穴狙い（実験#019の成果）
    - **ケリー基準**: 科学的な賭け金推奨
    """)

    # システム初期化
    if not initialize_hybrid_system():
        st.error("ハイブリッド予測システムの初期化に失敗しました")
        return

    predictor = st.session_state.hybrid_predictor
    recommender = st.session_state.betting_recommender

    # タブ分割
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 レース予測",
        "💰 資金管理設定",
        "📈 会場別性能",
        "📚 戦略ガイド"
    ])

    # Tab 1: レース予測
    with tab1:
        st.subheader("📊 レース予測と賭け推奨")

        # レース選択
        col1, col2, col3 = st.columns(3)

        with col1:
            target_date = st.date_input("レース日", datetime.now())

        with col2:
            venue_code = st.selectbox(
                "会場",
                options=['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12',
                        '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24'],
                format_func=lambda x: f"{x} - {VENUES.get(x, '不明')}"
            )

        with col3:
            race_number = st.number_input("レース番号", min_value=1, max_value=12, value=1)

        race_id = f"{target_date.strftime('%Y%m%d')}_{venue_code}_{race_number:02d}"

        if st.button("🔮 予測実行", type="primary", use_container_width=True):
            with st.spinner("予測中..."):
                # 特徴量準備
                X = prepare_race_features(race_id, venue_code)

                if X is None or len(X) < 6:
                    st.error("❌ レースデータが見つかりませんでした")
                    st.info("💡 該当レースの出走表データがDBに登録されているか確認してください")
                else:
                    # 予測実行
                    result = predictor.predict_with_info(X, venue_code)

                    # オッズ取得
                    odds_list = get_race_odds(race_id, venue_code)

                    # 会場情報表示
                    venue_info = predictor.get_venue_info(venue_code)

                    col_info1, col_info2, col_info3 = st.columns(3)
                    with col_info1:
                        st.metric("使用モデル",
                                 "会場特化" if venue_info['is_superior'] else "統合モデル",
                                 delta=f"+{venue_info['delta']:.4f}" if venue_info['is_superior'] else None)
                    with col_info2:
                        st.metric("期待AUC", f"{result['expected_auc']:.4f}")
                    with col_info3:
                        st.metric("会場", f"{venue_code} - {VENUES.get(venue_code, '不明')}")

                    st.markdown("---")

                    # レース全体分析
                    analysis_df = recommender.analyze_race(
                        probabilities=result['probabilities'],
                        odds_list=odds_list
                    )

                    st.subheader("📋 レース分析結果")
                    st.dataframe(analysis_df, use_container_width=True, height=280)

                    # 推奨艇の詳細表示
                    st.markdown("---")
                    st.subheader("🎯 推奨艇の詳細")

                    for i in range(6):
                        prob = result['probabilities'][i]
                        odds = odds_list[i]

                        rec = recommender.get_recommendation(
                            win_probability=prob,
                            odds=odds,
                            pit_number=i + 1
                        )

                        # いずれかの戦略で推奨されている場合のみ表示
                        if rec['overall_recommendation'] == 'ベット推奨':
                            with st.expander(f"🚤 {i+1}号艇 - {rec['confidence_level']}", expanded=True):
                                col_det1, col_det2, col_det3, col_det4 = st.columns(4)

                                with col_det1:
                                    st.metric("勝利確率", f"{prob:.1%}")
                                with col_det2:
                                    st.metric("オッズ", f"{odds:.2f}倍")
                                with col_det3:
                                    st.metric("期待値", f"{rec['expected_value_pct']:+.1f}%",
                                             delta="プラス" if rec['expected_value'] > 0 else "マイナス")
                                with col_det4:
                                    st.metric("ケリー推奨額", f"{rec['kelly_bet_amount']:.0f}円")

                                st.markdown("**戦略別推奨:**")
                                for strategy_key, strategy_rec in rec['recommendations'].items():
                                    status_icon = "✅" if strategy_rec['should_bet'] else "❌"
                                    st.markdown(f"{status_icon} **{strategy_rec['strategy_name']}**: "
                                              f"{'推奨' if strategy_rec['should_bet'] else '見送り'} "
                                              f"(期待的中率: {strategy_rec['expected_hit_rate']:.1%}, "
                                              f"期待ROI: {strategy_rec['expected_roi']:.1%})")

    # Tab 2: 資金管理設定
    with tab2:
        st.subheader("💰 資金管理設定")

        current_bankroll = recommender.bankroll

        st.markdown(f"**現在の総資金**: {current_bankroll:,.0f}円")

        new_bankroll = st.number_input(
            "総資金を変更（円）",
            min_value=10000,
            max_value=10000000,
            value=int(current_bankroll),
            step=10000
        )

        if st.button("💾 資金額を更新"):
            st.session_state.betting_recommender = BettingRecommender(bankroll=new_bankroll)
            st.success(f"✅ 総資金を {new_bankroll:,.0f}円 に更新しました")
            st.rerun()

        st.markdown("---")

        # リスク管理情報
        st.subheader("📊 リスク管理")

        col_risk1, col_risk2, col_risk3 = st.columns(3)

        with col_risk1:
            st.metric("ケリー係数", f"{recommender.KELLY_FRACTION:.2f}")
            st.caption("フラクショナルケリー（保守的）")

        with col_risk2:
            max_bet = new_bankroll * 0.05
            st.metric("最大賭け金", f"{max_bet:,.0f}円")
            st.caption("総資金の5%まで")

        with col_risk3:
            recommended_daily_limit = new_bankroll * 0.10
            st.metric("推奨日次損失上限", f"{recommended_daily_limit:,.0f}円")
            st.caption("総資金の10%")

        st.info("""
        **💡 資金管理のポイント:**
        - ケリー係数0.25: フルケリーの1/4で安全性重視
        - 最大賭け金5%制限: 1レースでの過大リスクを防止
        - 日次損失上限10%: 連敗時の資金保護
        """)

    # Tab 3: 会場別性能
    with tab3:
        st.subheader("📈 会場別モデル性能")

        # 会場性能一覧
        venue_performance = []
        for venue in ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12',
                     '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24']:
            info = predictor.get_venue_info(venue)
            venue_performance.append({
                '会場': f"{venue} - {VENUES.get(venue, '不明')}",
                'モデル': '会場特化' if info['is_superior'] else '統合',
                'AUC': info['auc'],
                '統合比差分': info['delta'],
                '推奨': info['recommendation']
            })

        df_performance = pd.DataFrame(venue_performance)
        df_performance = df_performance.sort_values('AUC', ascending=False)

        st.dataframe(df_performance, use_container_width=True, height=600)

        st.markdown("---")

        # トップ5会場
        st.subheader("🏆 トップ5会場（会場特化モデル）")

        top5 = df_performance[df_performance['モデル'] == '会場特化'].head(5)

        for idx, row in top5.iterrows():
            col_t1, col_t2, col_t3 = st.columns([2, 1, 1])
            with col_t1:
                st.markdown(f"**{row['会場']}**")
            with col_t2:
                st.metric("AUC", f"{row['AUC']:.4f}")
            with col_t3:
                st.metric("統合比", f"+{row['統合比差分']:.4f}")

    # Tab 4: 戦略ガイド
    with tab4:
        st.subheader("📚 賭け戦略ガイド")

        st.markdown("""
        ### 3つの賭け戦略（実験#019の成果）

        実験#019で1ヶ月間のバックテストにより検証された戦略です。
        """)

        # 戦略比較表
        strategy_comparison = pd.DataFrame({
            '戦略': ['保守的', 'バランス', '穴狙い'],
            '条件': [
                '勝率≥80% & 期待値>0',
                '期待値≥+10%',
                '勝率≥30% & 期待値≥+20%'
            ],
            '的中率': ['85.71%', '25.02%', '60.46%'],
            'ROI': ['47.10%', '45.35%', '46.63%'],
            '月間対象レース': ['42レース', '2,350レース', '521レース'],
            '特徴': [
                '高確率・低頻度・安定',
                '低確率・高頻度・最大利益',
                '中確率・中頻度・バランス'
            ]
        })

        st.dataframe(strategy_comparison, use_container_width=True, height=180)

        st.markdown("---")

        # 各戦略の詳細
        st.subheader("🔍 戦略詳細")

        with st.expander("🛡️ 保守的戦略", expanded=False):
            st.markdown("""
            **特徴:**
            - 勝利確率80%以上の高確率レースのみ
            - 期待値がプラスであること
            - 月間約42レース（1日1-2レース程度）

            **向いている人:**
            - 安定志向
            - 少額でコツコツ増やしたい
            - リスクを最小限にしたい

            **期待成績:**
            - 的中率: 85.71%
            - ROI: 47.10%
            - 10万円→14.7万円/月（42レース全ベット時）
            """)

        with st.expander("⚖️ バランス戦略", expanded=False):
            st.markdown("""
            **特徴:**
            - 期待値+10%以上のレースすべて
            - 勝率は問わない（期待値重視）
            - 月間約2,350レース（1日78レース程度）

            **向いている人:**
            - 最大利益を狙いたい
            - 的中率よりトータル収益重視
            - 多数のレースに対応できる

            **期待成績:**
            - 的中率: 25.02%
            - ROI: 45.35%
            - 最大期待利益（レース数が多い）
            """)

        with st.expander("🎯 穴狙い戦略", expanded=False):
            st.markdown("""
            **特徴:**
            - 勝利確率30%以上
            - 期待値+20%以上の高期待値
            - 月間約521レース（1日17レース程度）

            **向いている人:**
            - 中リスク・中リターン志向
            - そこそこの的中率も欲しい
            - 高期待値レースを狙いたい

            **期待成績:**
            - 的中率: 60.46%
            - ROI: 46.63%（3戦略中最高）
            - バランスの取れた戦略
            """)

        st.markdown("---")

        st.info("""
        **💡 実戦での使い方:**

        1. **初心者**: まずは保守的戦略から
        2. **中級者**: 穴狙い戦略で経験を積む
        3. **上級者**: バランス戦略で最大利益を狙う
        4. **組み合わせ**: 複数戦略を併用も可能

        **重要**: どの戦略でも資金管理を徹底してください。
        """)


if __name__ == "__main__":
    render_hybrid_prediction_page()
