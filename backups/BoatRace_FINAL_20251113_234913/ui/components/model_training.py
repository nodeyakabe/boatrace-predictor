"""
モデル学習・評価UIページ
"""
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import sys
import os
from datetime import datetime, timedelta
import json
import plotly.graph_objects as go
import plotly.express as px
import traceback


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from src.ml.model_trainer import ModelTrainer
from src.analysis.feature_generator import FeatureGenerator
from ui.components.stage2_training import (
    render_data_preparation_tab as render_stage2_data_prep,
    render_model_training_tab as render_stage2_model_training,
    render_model_evaluation_tab as render_stage2_model_eval,
    render_model_management_tab as render_stage2_model_mgmt
)


def display_error_with_traceback(error: Exception, context: str = ""):
    """
    エラーメッセージとトレースバックを表示

    Args:
        error: 発生した例外
        context: エラーの文脈情報
    """
    st.error(f"❌ エラーが発生しました{': ' + context if context else ''}")

    # エラー詳細をエキスパンダーで表示
    with st.expander("🔍 エラー詳細を表示", expanded=False):
        st.markdown(f"**エラータイプ**: `{type(error).__name__}`")
        st.markdown(f"**エラーメッセージ**: {str(error)}")

        st.markdown("---")
        st.markdown("**トレースバック:**")

        # トレースバックを整形して表示
        tb_str = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        st.code(tb_str, language="python")

        # トラブルシューティングのヒント
        st.markdown("---")
        st.markdown("**💡 トラブルシューティングのヒント:**")

        if "No module named" in str(error):
            st.info("モジュールが見つかりません。必要なライブラリがインストールされているか確認してください。")
        elif "does not exist" in str(error) or "No such file" in str(error):
            st.info("ファイルまたはテーブルが見つかりません。データベースが正しく初期化されているか確認してください。")
        elif "no such column" in str(error):
            st.info("データベースのカラムが見つかりません。テーブル構造を確認してください。")
        elif "out of memory" in str(error).lower():
            st.info("メモリ不足です。データサイズを減らすか、メモリを増やしてください。")
        else:
            st.info("エラーの詳細を確認し、適切な対処を行ってください。")


def render_model_training_page():
    """モデル学習ページのレンダリング"""
    st.header("🤖 機械学習モデル学習・評価")

    # タブで機能を分割
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 データ準備 (Stage2)",
        "🎯 モデル学習 (Stage2)",
        "📈 モデル評価 (Stage2)",
        "💾 モデル管理 (Stage2)",
        "🎲 Stage1学習",
        "📏 確率校正"
    ])

    # Tab 1: データ準備 (Stage2)
    with tab1:
        render_stage2_data_prep()

    # Tab 2: モデル学習 (Stage2)
    with tab2:
        render_stage2_model_training()

    # Tab 3: モデル評価 (Stage2)
    with tab3:
        render_stage2_model_eval()

    # Tab 4: モデル管理 (Stage2)
    with tab4:
        render_stage2_model_mgmt()

    # Tab 5: Stage1学習
    with tab5:
        render_stage1_training_tab()

    # Tab 6: 確率校正
    with tab6:
        render_calibration_tab()


def render_data_preparation_tab():
    """データ準備タブ"""
    st.subheader("📊 学習データの準備")

    # データ期間の設定
    st.markdown("### データ期間の設定")
    col1, col2 = st.columns(2)

    with col1:
        days_back = st.slider(
            "過去何日分のデータを使用するか",
            min_value=30,
            max_value=365,
            value=180,
            step=30,
            key="data_days_back"
        )

    with col2:
        train_ratio = st.slider(
            "訓練データの割合（残りは検証データ）",
            min_value=0.5,
            max_value=0.9,
            value=0.8,
            step=0.05,
            key="train_ratio"
        )

    st.markdown("---")

    # データの統計情報を表示
    with st.expander("📊 データの統計情報", expanded=True):
        with st.spinner("データを読み込み中..."):
            conn = sqlite3.connect(DATABASE_PATH)

            # レース数を取得
            query_races = f"""
                SELECT COUNT(DISTINCT r.id) as race_count
                FROM races r
                WHERE r.race_date >= date('now', '-{days_back} days')
            """
            df_races = pd.read_sql_query(query_races, conn)

            # 艇数を取得
            query_boats = f"""
                SELECT COUNT(*) as boat_count
                FROM results res
                JOIN races r ON res.race_id = r.id
                WHERE r.race_date >= date('now', '-{days_back} days')
            """
            df_boats = pd.read_sql_query(query_boats, conn)

            # 1着データの分布
            query_winners = f"""
                SELECT
                    rd.actual_course as course,
                    COUNT(*) as count
                FROM results res
                JOIN races r ON res.race_id = r.id
                JOIN race_details rd ON res.race_id = rd.race_id AND res.pit_number = rd.pit_number
                WHERE r.race_date >= date('now', '-{days_back} days')
                  AND res.rank = 1
                GROUP BY rd.actual_course
                ORDER BY rd.actual_course
            """
            df_winners = pd.read_sql_query(query_winners, conn)

            conn.close()

        # 統計情報を表示
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("📅 対象期間", f"過去{days_back}日間")

        with col2:
            race_count = df_races['race_count'].iloc[0] if not df_races.empty else 0
            st.metric("🏁 レース数", f"{race_count:,}回")

        with col3:
            boat_count = df_boats['boat_count'].iloc[0] if not df_boats.empty else 0
            st.metric("🚤 データ数", f"{boat_count:,}件")

        # 訓練/検証データの分割情報
        st.markdown("---")
        st.markdown("**データ分割**")

        train_count = int(boat_count * train_ratio)
        valid_count = boat_count - train_count

        col1, col2 = st.columns(2)
        with col1:
            st.metric("訓練データ", f"{train_count:,}件 ({train_ratio*100:.0f}%)")
        with col2:
            st.metric("検証データ", f"{valid_count:,}件 ({(1-train_ratio)*100:.0f}%)")

        # コース別1着分布のグラフ
        if not df_winners.empty:
            st.markdown("---")
            st.markdown("**コース別1着分布**")

            fig = px.bar(
                df_winners,
                x='course',
                y='count',
                labels={'course': 'コース', 'count': '1着回数'},
            )
            st.plotly_chart(fig, use_container_width=True)

            # クラス不均衡の情報
            max_count = df_winners['count'].max()
            min_count = df_winners['count'].min()
            imbalance_ratio = max_count / min_count

            if imbalance_ratio > 5:
                st.info(f"ℹ️ クラス不均衡: {imbalance_ratio:.1f}倍（1コース有利が反映されています）\n\n"
                       "XGBoostの`scale_pos_weight`パラメータで自動調整されます。")
            else:
                st.success("✅ クラスバランスは良好です")

    # 特徴量の選択
    st.markdown("---")
    st.markdown("### 特徴量の選択")

    feature_groups = {
        "基本特徴量": [
            "win_rate", "second_rate", "third_rate",
            "local_win_rate", "local_second_rate", "local_third_rate",
            "avg_st", "class_score", "pit_advantage"
        ],
        "機材特徴量": [
            "motor_second_rate", "motor_third_rate",
            "boat_second_rate", "boat_third_rate",
            "motor_performance", "boat_performance", "equipment_advantage"
        ],
        "派生特徴量": [
            "experience_score", "relative_win_rate", "relative_st"
        ]
    }

    selected_features = []

    for group_name, features in feature_groups.items():
        with st.expander(f"✅ {group_name} ({len(features)}個)", expanded=False):
            select_all = st.checkbox(f"すべて選択", value=True, key=f"select_all_{group_name}")

            if select_all:
                selected_features.extend(features)
                st.success(f"✓ {len(features)}個の特徴量を選択中")
            else:
                st.info("個別に特徴量を選択してください")
                for feature in features:
                    if st.checkbox(feature, value=False, key=f"feature_{feature}"):
                        selected_features.append(feature)

    st.session_state['selected_features'] = selected_features
    # days_backとtrain_ratioはウィジェットのkeyで管理されているため、直接代入不要

    st.markdown("---")

    if len(selected_features) > 0:
        st.success(f"✅ 合計 {len(selected_features)}個の特徴量を選択")
        with st.expander("選択中の特徴量を表示", expanded=False):
            st.write(", ".join(selected_features))
    else:
        st.error("⚠️ 特徴量が選択されていません")


def render_model_training_tab():
    """モデル学習タブ"""
    st.subheader("🎯 モデルの学習")

    if 'selected_features' not in st.session_state or len(st.session_state['selected_features']) == 0:
        st.warning("⚠️ まず「データ準備」タブで特徴量を選択してください")
        return

    st.info(f"📊 選択された特徴量: {len(st.session_state['selected_features'])}個")

    # ハイパーパラメータ設定
    st.markdown("### ハイパーパラメータ設定")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**基本パラメータ**")
        max_depth = st.slider("最大深度 (max_depth)", 3, 10, 6, key="max_depth")
        learning_rate = st.slider("学習率 (learning_rate)", 0.01, 0.3, 0.05, 0.01, key="learning_rate")
        num_boost_round = st.slider("ブースティング回数", 100, 2000, 1000, 100, key="num_boost_round")

    with col2:
        st.markdown("**正則化パラメータ**")
        subsample = st.slider("サブサンプル率 (subsample)", 0.5, 1.0, 0.8, 0.05, key="subsample")
        colsample_bytree = st.slider("列サンプル率 (colsample_bytree)", 0.5, 1.0, 0.8, 0.05, key="colsample_bytree")
        early_stopping_rounds = st.slider("Early Stopping", 20, 100, 50, 10, key="early_stopping")

    # 予測対象の選択
    st.markdown("---")
    st.markdown("### 予測対象")

    prediction_target = st.radio(
        "何を予測しますか？",
        ["1着", "3連対（1-3着）", "2連対（1-2着）"],
        key="prediction_target"
    )

    st.markdown("---")

    # 学習実行ボタン
    if st.button("🚀 学習を開始", type="primary", use_container_width=True):
        run_training(
            selected_features=st.session_state['selected_features'],
            days_back=st.session_state.get('data_days_back', 180),  # ウィジェットのkeyから取得
            train_ratio=st.session_state.get('train_ratio', 0.8),    # ウィジェットのkeyから取得
            max_depth=max_depth,
            learning_rate=learning_rate,
            num_boost_round=num_boost_round,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            early_stopping_rounds=early_stopping_rounds,
            prediction_target=prediction_target
        )


def run_training(**kwargs):
    """実際の学習処理"""
    st.markdown("---")
    st.markdown("### 🔄 学習実行中...")

    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # ステップ1: データ読み込み
        status_text.text("📥 データを読み込み中...")
        progress_bar.progress(10)

        # TODO: 実装
        st.error("❌ データ読み込みが未実装です")
        return

    except Exception as e:
        display_error_with_traceback(e, "モデル学習処理中")


def render_model_evaluation_tab():
    """モデル評価タブ"""
    st.subheader("📈 モデルの評価")

    # 保存済みモデルの一覧
    model_dir = os.path.join(PROJECT_ROOT, "models")

    if not os.path.exists(model_dir):
        st.info("💡 まだモデルが学習されていません。「モデル学習」タブから学習を実行してください。")
        return

    model_files = [f for f in os.listdir(model_dir) if f.endswith('.json') and not f.endswith('.meta.json')]

    if len(model_files) == 0:
        st.info("💡 まだモデルが学習されていません。「モデル学習」タブから学習を実行してください。")
        return

    # モデル選択
    selected_model = st.selectbox(
        "評価するモデルを選択",
        model_files,
        key="eval_model_select"
    )

    if selected_model:
        st.markdown(f"### モデル: {selected_model}")

        # モデル情報を表示
        model_path = os.path.join(model_dir, selected_model)

        # TODO: モデル評価の実装
        st.info("💡 モデル評価機能は実装中です")


def render_prediction_simulation_tab():
    """予想シミュレーションタブ"""
    st.subheader("💰 予想シミュレーション")

    st.markdown("""
    学習したモデルを使用して、過去のレースでシミュレーションを実行します。

    **シミュレーション内容:**
    - 的中率の計算
    - 回収率の計算
    - 期待値に基づく購入戦略の検証
    """)

    # TODO: 予想シミュレーションの実装
    st.info("💡 予想シミュレーション機能は実装中です")


def render_stage1_training_tab():
    """Stage1レース選別モデル学習タブ"""
    st.subheader("🎲 Stage1: レース選別モデル学習")

    st.markdown("""
    **Stage1モデルの目的:**
    - 予想しやすいレースを自動判定
    - `buy_score`（0〜1）を出力
    - スコアが高いレース = 予想しやすい
    - スコアが低いレース = 予想困難（見送り推奨）

    **使用される特徴量:**
    1. データ充足率（展示タイム、選手成績、モーター性能）
    2. レース安定性（コース分散、スキルギャップ）
    3. 波乱耐性（逃げ率、内枠勝率、波乱率）
    """)

    st.markdown("---")

    # データ期間設定
    st.markdown("### 📅 学習データ期間")
    col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input(
            "開始日",
            value=pd.Timestamp.now() - pd.Timedelta(days=180),
            key="stage1_start_date"
        )

    with col2:
        end_date = st.date_input(
            "終了日",
            value=pd.Timestamp.now() - pd.Timedelta(days=1),
            key="stage1_end_date"
        )

    # 学習パラメータ
    st.markdown("---")
    st.markdown("### ⚙️ 学習パラメータ")

    col1, col2, col3 = st.columns(3)

    with col1:
        max_depth = st.slider("最大深度", 3, 10, 6, key="stage1_max_depth")
        learning_rate = st.slider("学習率", 0.01, 0.3, 0.1, step=0.01, key="stage1_lr")

    with col2:
        num_boost_round = st.slider("ブースト回数", 50, 500, 200, step=50, key="stage1_boost")
        subsample = st.slider("サブサンプル", 0.5, 1.0, 0.8, step=0.1, key="stage1_subsample")

    with col3:
        train_ratio = st.slider("訓練データ比率", 0.6, 0.9, 0.8, step=0.05, key="stage1_train_ratio")
        early_stopping = st.slider("早期停止", 10, 50, 20, step=5, key="stage1_early_stop")

    st.markdown("---")

    # 学習実行ボタン
    if st.button("🚀 Stage1モデルを学習", type="primary", use_container_width=True):
        with st.spinner("Stage1モデルを学習中..."):
            try:
                from src.ml.race_selector import RaceSelector
                from datetime import datetime

                # RaceSelectorインスタンス
                selector = RaceSelector()

                # ステータス表示
                status_container = st.empty()
                progress_bar = st.progress(0)

                # データ準備
                status_container.info("📥 学習データを準備中...")
                progress_bar.progress(20)

                X, y = selector.prepare_training_data(
                    start_date=start_date.strftime('%Y-%m-%d'),
                    end_date=end_date.strftime('%Y-%m-%d')
                )

                st.success(f"✅ データ準備完了: {len(X)}レース")

                # 訓練/検証分割
                status_container.info("🔀 データ分割中...")
                progress_bar.progress(40)

                from sklearn.model_selection import train_test_split

                # race_idを除外
                feature_cols = [col for col in X.columns if col != 'race_id']
                X_features = X[feature_cols]

                X_train, X_valid, y_train, y_valid = train_test_split(
                    X_features, y, test_size=(1-train_ratio), random_state=42
                )

                st.info(f"訓練データ: {len(X_train)}件 / 検証データ: {len(X_valid)}件")

                # モデル学習
                status_container.info("🎯 モデル学習中...")
                progress_bar.progress(60)

                params = {
                    'max_depth': max_depth,
                    'learning_rate': learning_rate,
                    'n_estimators': num_boost_round,
                    'subsample': subsample,
                    'objective': 'binary:logistic',
                    'eval_metric': 'auc'
                }

                summary = selector.train(
                    X_train, y_train,
                    X_valid, y_valid,
                    params=params
                )

                st.success(f"✅ 学習完了!")

                # 結果表示
                progress_bar.progress(80)
                status_container.info("💾 モデル保存中...")

                model_path = selector.save_model('race_selector.json')
                st.success(f"✅ モデル保存: {model_path}")

                progress_bar.progress(100)
                status_container.success("🎉 すべて完了!")

                # サマリー表示
                st.markdown("---")
                st.markdown("### 📊 学習結果サマリー")

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("訓練AUC", f"{summary.get('train_auc', 0):.4f}")

                with col2:
                    st.metric("検証AUC", f"{summary.get('valid_auc', 0):.4f}")

                with col3:
                    overfitting = summary.get('train_auc', 0) - summary.get('valid_auc', 0)
                    st.metric("過学習度", f"{overfitting:.4f}")

                if overfitting > 0.1:
                    st.warning("⚠️ 過学習の可能性があります。パラメータを調整してください。")
                else:
                    st.success("✅ 良好なモデルです！")

            except Exception as e:
                display_error_with_traceback(e, "Stage1モデル学習中")

    # 保存済みモデル情報
    st.markdown("---")
    st.markdown("### 📦 保存済みモデル")

    model_path = os.path.join(PROJECT_ROOT, 'models', 'race_selector.json')

    if os.path.exists(model_path):
        st.success(f"✅ Stage1モデルが保存されています")
        st.info(f"パス: {model_path}")

        # モデルのメタデータ表示
        meta_path = os.path.join(PROJECT_ROOT, 'models', 'race_selector.meta.json')
        if os.path.exists(meta_path):
            import json
            with open(meta_path, 'r') as f:
                meta = json.load(f)

            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**特徴量数:** {len(meta.get('feature_names', []))}")
            with col2:
                st.write(f"**作成日:** {meta.get('created_at', 'N/A')}")
    else:
        st.warning("⚠️ Stage1モデルが見つかりません。上記ボタンから学習を実行してください。")


def render_calibration_tab():
    """確率校正タブのレンダリング"""
    st.subheader("📏 確率校正 (Probability Calibration)")

    st.markdown("""
    確率校正は、モデルの予測確率を実際の勝率に近づけるプロセスです。

    **メリット:**
    - 期待値計算の精度が向上
    - Kelly基準での賭け金配分がより正確に
    - モデルの信頼性向上

    **方法:**
    - **Platt Scaling**: ロジスティック回帰で校正（高速、少量データでも有効）
    - **Isotonic Regression**: ノンパラメトリック校正（大量データで精度が高い）
    """)

    # モデルの存在確認
    model_path = os.path.join(PROJECT_ROOT, 'models', 'xgboost_model.json')

    if not os.path.exists(model_path):
        st.warning("⚠️ Stage2モデルが見つかりません。先に「🎯 モデル学習 (Stage2)」タブでモデルを学習してください。")
        return

    st.success(f"✅ Stage2モデルが見つかりました")

    st.markdown("---")
    st.markdown("### 🔧 校正パラメータ")

    col1, col2 = st.columns(2)

    with col1:
        # データ期間
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=180)

        calib_start_date = st.date_input(
            "校正データ開始日",
            value=start_date,
            key='calib_start_date'
        )

        calib_end_date = st.date_input(
            "校正データ終了日",
            value=end_date,
            key='calib_end_date'
        )

    with col2:
        # 校正方法
        calib_method = st.selectbox(
            "校正方法",
            options=['platt', 'isotonic'],
            format_func=lambda x: 'Platt Scaling (推奨)' if x == 'platt' else 'Isotonic Regression',
            key='calib_method'
        )

        # データ分割比率
        calib_ratio = st.slider(
            "校正データ比率",
            min_value=0.1,
            max_value=0.5,
            value=0.3,
            step=0.05,
            help="学習データの何%を校正に使うか",
            key='calib_ratio'
        )

    st.markdown("---")

    # 学習ボタン
    if st.button("🚀 確率校正を実行", type="primary", key='run_calibration'):
        with st.spinner("確率校正を実行中..."):
            try:
                status_placeholder = st.empty()
                progress_bar = st.progress(0)

                # ステップ1: データ読み込み
                status_placeholder.info("📊 データを読み込み中...")
                progress_bar.progress(10)

                from src.ml.dataset_builder import DatasetBuilder

                dataset_builder = DatasetBuilder()
                X, y = dataset_builder.build_dataset(
                    start_date=calib_start_date.strftime('%Y-%m-%d'),
                    end_date=calib_end_date.strftime('%Y-%m-%d')
                )

                if X is None or len(X) == 0:
                    st.error("❌ データが見つかりませんでした")
                    return

                status_placeholder.success(f"✅ データ読み込み完了: {len(X)}件")
                progress_bar.progress(30)

                # ステップ2: データ分割
                status_placeholder.info("🔀 データを分割中...")

                from sklearn.model_selection import train_test_split

                # 校正用データと評価用データに分割
                X_calib, X_eval, y_calib, y_eval = train_test_split(
                    X, y, test_size=(1 - calib_ratio), random_state=42, stratify=y
                )

                status_placeholder.success(f"✅ データ分割完了: 校正 {len(X_calib)}件, 評価 {len(X_eval)}件")
                progress_bar.progress(50)

                # ステップ3: モデル読み込み
                status_placeholder.info("🤖 モデルを読み込み中...")

                trainer = ModelTrainer()
                trainer.load_model('xgboost_model.json')

                status_placeholder.success("✅ モデル読み込み完了")
                progress_bar.progress(60)

                # ステップ4: 確率校正
                status_placeholder.info(f"📏 確率校正中 ({calib_method})...")

                calibration_metrics = trainer.train_calibrator(
                    X_calib=X_calib,
                    y_calib=y_calib,
                    method=calib_method
                )

                status_placeholder.success("✅ 確率校正完了")
                progress_bar.progress(80)

                # ステップ5: モデル保存
                status_placeholder.info("💾 モデルを保存中...")

                trainer.save_model('xgboost_model.json')

                status_placeholder.success("✅ 校正済みモデルを保存しました")
                progress_bar.progress(100)

                # 結果サマリー表示
                st.markdown("---")
                st.markdown("### 📊 校正結果サマリー")

                col1, col2, col3 = st.columns(3)

                with col1:
                    raw_logloss = calibration_metrics.get('raw_logloss', 0)
                    st.metric("校正前 Log Loss", f"{raw_logloss:.4f}")

                with col2:
                    cal_logloss = calibration_metrics.get('calibrated_logloss', 0)
                    st.metric("校正後 Log Loss", f"{cal_logloss:.4f}")

                with col3:
                    improvement = raw_logloss - cal_logloss
                    st.metric("改善度", f"{improvement:.4f}", delta=f"{improvement:.4f}")

                col1, col2 = st.columns(2)

                with col1:
                    raw_brier = calibration_metrics.get('raw_brier', 0)
                    st.metric("校正前 Brier Score", f"{raw_brier:.4f}")

                with col2:
                    cal_brier = calibration_metrics.get('calibrated_brier', 0)
                    st.metric("校正後 Brier Score", f"{cal_brier:.4f}")

                if improvement > 0:
                    st.success("✅ 校正により予測精度が向上しました！")
                elif improvement > -0.01:
                    st.info("ℹ️ 校正の効果は限定的です。")
                else:
                    st.warning("⚠️ 校正により精度が低下しました。元のモデルを使用することを推奨します。")

                # 校正曲線の表示
                if 'calibration_curve_fig' in calibration_metrics:
                    st.markdown("---")
                    st.markdown("### 📈 校正曲線")
                    st.plotly_chart(calibration_metrics['calibration_curve_fig'], use_container_width=True)

            except Exception as e:
                display_error_with_traceback(e, "Stage1モデル学習中")

    # 保存済み校正モデル情報
    st.markdown("---")
    st.markdown("### 📦 校正モデル情報")

    calibrator_path = os.path.join(PROJECT_ROOT, 'models', 'xgboost_model_calibrator.pkl')

    if os.path.exists(calibrator_path):
        st.success(f"✅ 校正モデルが保存されています")
        st.info(f"パス: {calibrator_path}")

        # メタデータ表示
        meta_path = os.path.join(PROJECT_ROOT, 'models', 'xgboost_model.json')
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                meta = json.load(f)

            if meta.get('use_calibration', False):
                st.success("📏 このモデルは確率校正が有効になっています")
            else:
                st.warning("⚠️ このモデルは確率校正が無効です")
    else:
        st.warning("⚠️ 校正モデルが見つかりません。上記ボタンから校正を実行してください。")
