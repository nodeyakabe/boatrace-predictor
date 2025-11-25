"""
Stage2モデル学習UIコンポーネント

Stage2予測モデルの学習・評価・管理を行うStreamlitインターフェース
"""

import streamlit as st
import pandas as pd
import numpy as np
import sys
import os
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from src.training.stage2_trainer import Stage2Trainer
import sqlite3


def render_stage2_training_page():
    """Stage2モデル学習ページのメイン表示"""
    st.header("🤖 Stage2モデル学習")

    st.markdown("""
    Stage2モデルは、Stage1の予測結果を入力として最終的な着順を予測します。
    - **入力**: Stage1の1-2-3着確率 + 追加特徴量
    - **出力**: 各艇の着順（1-6着）の確率
    - **アルゴリズム**: LightGBM（6つのバイナリ分類器）
    """)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📚 データ準備",
        "🎯 モデル学習",
        "📊 モデル評価",
        "💾 モデル管理"
    ])

    with tab1:
        render_data_preparation_tab()

    with tab2:
        render_model_training_tab()

    with tab3:
        render_model_evaluation_tab()

    with tab4:
        render_model_management_tab()


def render_data_preparation_tab():
    """データ準備タブ"""
    st.subheader("📚 学習データ準備")

    st.markdown("""
    ### データ要件
    Stage2モデルの学習には以下のデータが必要です：
    1. **Stage1予測結果**: 各艇の1-2-3着確率
    2. **レース結果**: 実際の着順（1-6）
    3. **追加特徴量**（オプション）:
       - オッズ情報
       - 気象データ
       - 選手・モーター成績
    """)

    # データベースからレース結果を取得
    st.markdown("---")
    st.markdown("### データベース統計")

    with st.spinner("データ取得中..."):
        stats = get_database_stats()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("総レース数", f"{stats['total_races']:,}レース")

    with col2:
        st.metric("総出走艇数", f"{stats['total_entries']:,}艇")

    with col3:
        date_range = f"{stats['date_from']} ~ {stats['date_to']}"
        st.metric("データ期間", date_range)

    # サンプルデータ生成
    st.markdown("---")
    st.markdown("### サンプルデータ生成（デモ用）")

    col1, col2 = st.columns(2)

    with col1:
        n_samples = st.number_input(
            "生成するサンプル数",
            min_value=100,
            max_value=10000,
            value=1000,
            step=100
        )

    with col2:
        test_ratio = st.slider(
            "テストデータの割合",
            min_value=0.1,
            max_value=0.5,
            value=0.2,
            step=0.05
        )

    if st.button("サンプルデータ生成", type="primary"):
        with st.spinner("データ生成中..."):
            X, y = generate_sample_data(n_samples)

            st.success(f"サンプルデータ生成完了: {len(X)}件")

            # セッションステートに保存
            st.session_state['stage2_X'] = X
            st.session_state['stage2_y'] = y
            st.session_state['stage2_test_ratio'] = test_ratio

            # データプレビュー
            st.markdown("#### データプレビュー")
            st.dataframe(X.head(10), use_container_width=True)

            st.markdown("#### 着順分布")
            fig = px.histogram(
                y,
                x=y.values,
                nbins=6,
                title="着順の分布",
                labels={'x': '着順', 'y': '件数'}
            )
            st.plotly_chart(fig, use_container_width=True)


def render_model_training_tab():
    """モデル学習タブ"""
    st.subheader("🎯 モデル学習")

    # データの確認
    if 'stage2_X' not in st.session_state or 'stage2_y' not in st.session_state:
        st.warning("先にデータを準備してください（データ準備タブ）")
        return

    X = st.session_state['stage2_X']
    y = st.session_state['stage2_y']
    test_ratio = st.session_state.get('stage2_test_ratio', 0.2)

    st.info(f"準備済みデータ: {len(X)}件（訓練: {int(len(X)*(1-test_ratio))}件、テスト: {int(len(X)*test_ratio)}件）")

    # 学習設定
    st.markdown("### 学習設定")

    col1, col2, col3 = st.columns(3)

    with col1:
        num_boost_round = st.number_input(
            "ブースティング回数",
            min_value=50,
            max_value=5000,
            value=1000,
            step=50
        )

    with col2:
        early_stopping = st.number_input(
            "Early Stopping",
            min_value=10,
            max_value=200,
            value=50,
            step=10
        )

    with col3:
        learning_rate = st.number_input(
            "学習率",
            min_value=0.001,
            max_value=0.5,
            value=0.05,
            step=0.01,
            format="%.3f"
        )

    # 詳細設定（展開式）
    with st.expander("詳細設定"):
        col1, col2 = st.columns(2)

        with col1:
            num_leaves = st.slider("num_leaves", 20, 100, 31)
            feature_fraction = st.slider("feature_fraction", 0.5, 1.0, 0.8, 0.05)

        with col2:
            bagging_fraction = st.slider("bagging_fraction", 0.5, 1.0, 0.8, 0.05)
            bagging_freq = st.slider("bagging_freq", 1, 10, 5)

    params = {
        'objective': 'binary',
        'metric': 'auc',
        'boosting_type': 'gbdt',
        'num_leaves': num_leaves,
        'learning_rate': learning_rate,
        'feature_fraction': feature_fraction,
        'bagging_fraction': bagging_fraction,
        'bagging_freq': bagging_freq,
        'verbose': -1,
        'seed': 42
    }

    st.markdown("---")

    # 学習実行
    col1, col2 = st.columns(2)

    with col1:
        if st.button("全着順モデル学習開始", type="primary", use_container_width=True):
            run_training(X, y, test_ratio, params, num_boost_round, early_stopping)

    with col2:
        if st.button("ハイパーパラメータ最適化", use_container_width=True):
            run_hyperparameter_tuning(X, y, test_ratio)


def render_model_evaluation_tab():
    """モデル評価タブ"""
    st.subheader("📊 モデル評価")

    if 'stage2_trainer' not in st.session_state:
        st.warning("先にモデルを学習してください（モデル学習タブ）")
        return

    trainer = st.session_state['stage2_trainer']
    X_test = st.session_state.get('stage2_X_test')
    y_test = st.session_state.get('stage2_y_test')

    if X_test is None or y_test is None:
        st.error("テストデータが見つかりません")
        return

    # 評価実行
    st.markdown("### モデル性能評価")

    with st.spinner("評価中..."):
        eval_result = trainer.evaluate(X_test, y_test)

    # 的中率表示
    st.markdown("#### 🎯 的中率")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("1着的中率", f"{eval_result['1着的中率']:.1%}")

    with col2:
        st.metric("2着的中率", f"{eval_result['2着的中率']:.1%}")

    with col3:
        st.metric("3着的中率", f"{eval_result['3着的中率']:.1%}")

    with col4:
        st.metric("全体的中率", f"{eval_result['全体的中率']:.1%}")

    # AUCスコア表示
    st.markdown("---")
    st.markdown("#### 📈 AUCスコア（着順別）")

    auc_scores = eval_result['AUC_scores']

    # バーチャート
    positions = list(auc_scores.keys())
    scores = list(auc_scores.values())

    fig = go.Figure(data=[
        go.Bar(
            x=positions,
            y=scores,
            text=[f"{s:.3f}" for s in scores],
            textposition='auto',
            marker_color=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
        )
    ])

    fig.update_layout(
        title="着順別AUCスコア",
        xaxis_title="着順",
        yaxis_title="AUC",
        yaxis_range=[0, 1],
        height=400
    )

    st.plotly_chart(fig, use_container_width=True)

    # 詳細評価
    st.markdown("---")
    st.markdown("#### 📋 詳細評価結果")

    eval_df = pd.DataFrame({
        '着順': positions,
        'AUC': scores
    })

    st.dataframe(eval_df, use_container_width=True)

    # 予測分布
    st.markdown("---")
    st.markdown("#### 🎲 予測分布")

    with st.spinner("予測実行中..."):
        prob_df = trainer.predict_probabilities(X_test)
        pred_ranks = trainer.predict_rank(X_test)

    # 予測着順の分布
    fig = px.histogram(
        pred_ranks,
        x=pred_ranks,
        nbins=6,
        title="予測着順の分布",
        labels={'x': '予測着順', 'y': '件数'}
    )
    st.plotly_chart(fig, use_container_width=True)

    # 混同行列風の表示
    st.markdown("#### 🔢 予測 vs 実際（サンプル）")

    comparison_df = pd.DataFrame({
        '実際の着順': y_test.values[:50],
        '予測着順': pred_ranks[:50],
        '1着確率': prob_df['prob_1'].values[:50],
        '2着確率': prob_df['prob_2'].values[:50],
        '3着確率': prob_df['prob_3'].values[:50]
    })

    st.dataframe(
        comparison_df.style.format({
            '1着確率': '{:.2%}',
            '2着確率': '{:.2%}',
            '3着確率': '{:.2%}'
        }),
        use_container_width=True
    )


def render_model_management_tab():
    """モデル管理タブ"""
    st.subheader("💾 モデル管理")

    # モデル保存
    st.markdown("### モデル保存")

    if 'stage2_trainer' in st.session_state:
        trainer = st.session_state['stage2_trainer']

        model_name = st.text_input(
            "モデル名",
            value=f"stage2_model_{datetime.now().strftime('%Y%m%d')}",
            help="保存するモデルの名前を入力"
        )

        if st.button("モデル保存", type="primary"):
            with st.spinner("保存中..."):
                try:
                    save_path = trainer.save_models(model_name)
                    st.success(f"モデル保存完了: {save_path}")
                except Exception as e:
                    st.error(f"保存エラー: {e}")

    else:
        st.info("保存可能なモデルがありません。先に学習を実行してください。")

    st.markdown("---")

    # モデル読み込み
    st.markdown("### モデル読み込み")

    models_dir = Path("models/stage2")
    models_dir.mkdir(parents=True, exist_ok=True)

    # 保存済みモデル一覧
    saved_models = list(models_dir.glob("stage2_model_*"))

    if saved_models:
        model_options = [m.name for m in saved_models]

        selected_model = st.selectbox(
            "読み込むモデルを選択",
            options=model_options,
            help="保存済みモデルから選択"
        )

        if st.button("モデル読み込み"):
            with st.spinner("読み込み中..."):
                try:
                    trainer = Stage2Trainer()
                    model_path = models_dir / selected_model
                    trainer.load_models(str(model_path))

                    st.session_state['stage2_trainer'] = trainer
                    st.success(f"モデル読み込み完了: {selected_model}")

                except Exception as e:
                    st.error(f"読み込みエラー: {e}")

    else:
        st.info("保存済みモデルが見つかりません。")

    st.markdown("---")

    # モデル情報
    if 'stage2_trainer' in st.session_state:
        st.markdown("### 現在のモデル情報")

        trainer = st.session_state['stage2_trainer']

        if trainer.models:
            st.markdown(f"**学習済み着順**: {list(trainer.models.keys())}")

            if trainer.feature_names:
                st.markdown(f"**特徴量数**: {len(trainer.feature_names)}")

                with st.expander("特徴量リスト"):
                    st.write(trainer.feature_names)


# ========================================
# ヘルパー関数
# ========================================

def get_database_stats() -> dict:
    """データベース統計を取得"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)

        # レース数
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM races")
        total_races = cursor.fetchone()[0]

        # 出走艇数
        cursor.execute("SELECT COUNT(*) FROM entries")
        total_entries = cursor.fetchone()[0]

        # データ期間
        cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
        date_from, date_to = cursor.fetchone()

        conn.close()

        return {
            'total_races': total_races,
            'total_entries': total_entries,
            'date_from': date_from or 'N/A',
            'date_to': date_to or 'N/A'
        }

    except Exception as e:
        st.error(f"データベースエラー: {e}")
        return {
            'total_races': 0,
            'total_entries': 0,
            'date_from': 'N/A',
            'date_to': 'N/A'
        }


def generate_sample_data(n_samples: int = 1000) -> tuple:
    """サンプルデータ生成（デモ用）"""
    np.random.seed(42)

    # Stage1予測結果（1-2-3着確率）を模擬
    prob_1st = np.random.beta(2, 5, n_samples)  # 1着確率
    prob_2nd = np.random.beta(2, 5, n_samples)  # 2着確率
    prob_3rd = np.random.beta(2, 5, n_samples)  # 3着確率

    # 正規化
    total_prob = prob_1st + prob_2nd + prob_3rd
    prob_1st = prob_1st / total_prob
    prob_2nd = prob_2nd / total_prob
    prob_3rd = prob_3rd / total_prob

    # 追加特徴量
    racer_win_rate = np.random.uniform(0.1, 0.4, n_samples)
    motor_win_rate = np.random.uniform(0.1, 0.5, n_samples)
    course_number = np.random.choice([1, 2, 3, 4, 5, 6], n_samples)
    avg_st = np.random.normal(0.15, 0.05, n_samples)

    # データフレーム作成
    X = pd.DataFrame({
        'prob_1st': prob_1st,
        'prob_2nd': prob_2nd,
        'prob_3rd': prob_3rd,
        'racer_win_rate': racer_win_rate,
        'motor_win_rate': motor_win_rate,
        'course_number': course_number,
        'avg_st': avg_st
    })

    # 着順生成（確率に基づく）
    # 簡易的に1着確率が高いほど上位着順になりやすいように設定
    weights = prob_1st * 3 + prob_2nd * 2 + prob_3rd
    ranks = []

    for w in weights:
        if w > 0.4:
            ranks.append(np.random.choice([1, 2, 3], p=[0.6, 0.3, 0.1]))
        elif w > 0.25:
            ranks.append(np.random.choice([2, 3, 4], p=[0.5, 0.3, 0.2]))
        else:
            ranks.append(np.random.choice([4, 5, 6], p=[0.4, 0.3, 0.3]))

    y = pd.Series(ranks)

    return X, y


def run_training(X, y, test_ratio, params, num_boost_round, early_stopping):
    """モデル学習実行"""
    with st.spinner("モデル学習中..."):
        try:
            # トレーナー初期化
            trainer = Stage2Trainer()

            # データ分割
            X_train, X_test, y_train, y_test = trainer.prepare_training_data(
                X, y, test_size=test_ratio
            )

            # 進捗表示
            progress_bar = st.progress(0)
            status_text = st.empty()

            # 全着順モデル学習
            status_text.text("全着順モデルを学習中...")

            results = trainer.train_all_positions(
                X_train, y_train,
                X_test, y_test,
                params=params,
                num_boost_round=num_boost_round,
                early_stopping_rounds=early_stopping
            )

            progress_bar.progress(100)
            status_text.text("学習完了！")

            # セッションステートに保存
            st.session_state['stage2_trainer'] = trainer
            st.session_state['stage2_X_test'] = X_test
            st.session_state['stage2_y_test'] = y_test
            st.session_state['stage2_results'] = results

            st.success("モデル学習完了！")

            # 結果表示
            st.markdown("### 学習結果")

            result_df = pd.DataFrame(results).T
            result_df.index.name = '着順'

            st.dataframe(
                result_df[['train_auc', 'valid_auc']].style.format({
                    'train_auc': '{:.4f}',
                    'valid_auc': '{:.4f}'
                }),
                use_container_width=True
            )

        except Exception as e:
            st.error(f"学習エラー: {e}")
            import traceback
            st.code(traceback.format_exc())


def run_hyperparameter_tuning(X, y, test_ratio, n_trials=50):
    """ハイパーパラメータ最適化実行"""
    with st.spinner(f"ハイパーパラメータ最適化中（{n_trials}試行）..."):
        try:
            trainer = Stage2Trainer()

            # データ分割
            X_train, X_test, y_train, y_test = trainer.prepare_training_data(
                X, y, test_size=test_ratio
            )

            # 進捗表示
            progress_bar = st.progress(0)
            status_text = st.empty()

            status_text.text("1着モデルの最適化中...")

            # 1着モデルのみ最適化（デモ）
            result = trainer.optimize_hyperparameters(
                X_train, y_train,
                X_test, y_test,
                target_position=1,
                n_trials=n_trials
            )

            progress_bar.progress(100)
            status_text.text("最適化完了！")

            st.success(f"最適化完了！Best AUC: {result['best_score']:.4f}")

            # 最適パラメータ表示
            st.markdown("### 最適パラメータ")
            st.json(result['best_params'])

        except Exception as e:
            st.error(f"最適化エラー: {e}")
            import traceback
            st.code(traceback.format_exc())


if __name__ == "__main__":
    # Streamlit単体実行用（デバッグ）
    render_stage2_training_page()
