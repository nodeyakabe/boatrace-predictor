"""
高度なモデルトレーニングとベンチマーク
Phase 1-4の機能を統合
"""
import streamlit as st
import subprocess
import sys
import os
from datetime import datetime
import json


def render_advanced_training():
    """高度なモデルトレーニング画面"""
    st.header("🎓 高度なモデルトレーニング")

    st.info("""
    **Phase 1-3の最適化機能を使用したモデル再トレーニング**:
    - ✨ 最適化特徴量（不要な5特徴量除外、5新特徴量追加）
    - ✨ 最適化ハイパーパラメータ（過学習防止）
    - ✨ 時系列特徴量（19個追加）
    - ✨ Platt Scaling（確率キャリブレーション）
    """)

    # トレーニング設定
    st.subheader("⚙️ トレーニング設定")

    col1, col2 = st.columns(2)

    with col1:
        train_general = st.checkbox("汎用モデル", value=True)
        train_months = st.slider("学習期間（月）", 3, 12, 8)

    with col2:
        train_venues = st.multiselect(
            "会場別モデル",
            options=['07', '08', '05', '14', '09'],
            default=['07', '08', '05'],
            help="上位5会場から選択"
        )

    # トレーニング実行
    if st.button("🚀 モデルトレーニング開始", type="primary"):
        st.warning("⚠️ トレーニングには時間がかかります（10-30分程度）")

        with st.spinner("モデルトレーニング中..."):
            try:
                # Pythonインタープリターのパス
                python_exe = sys.executable

                # スクリプトパス
                script_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    'scripts',
                    'train_optimized_models.py'
                )

                # 実行
                result = subprocess.run(
                    [python_exe, script_path],
                    capture_output=True,
                    text=True,
                    timeout=1800  # 30分タイムアウト
                )

                if result.returncode == 0:
                    st.success("✅ トレーニング完了！")
                    st.text_area("実行ログ", result.stdout, height=300)

                    # メタデータを読み込んで表示
                    display_training_results()
                else:
                    st.error("❌ トレーニング失敗")
                    st.text_area("エラーログ", result.stderr, height=300)

            except subprocess.TimeoutExpired:
                st.error("⏱️ タイムアウト: 30分以内に完了しませんでした")
            except Exception as e:
                st.error(f"エラー: {e}")


def display_training_results():
    """トレーニング結果を表示"""
    st.subheader("📊 トレーニング結果")

    models_dir = 'models'
    if not os.path.exists(models_dir):
        st.warning("モデルディレクトリが存在しません")
        return

    # メタデータファイルを検索
    meta_files = [f for f in os.listdir(models_dir) if f.endswith('_meta.json')]

    if not meta_files:
        st.warning("トレーニング結果が見つかりません")
        return

    results = []
    for meta_file in meta_files:
        try:
            with open(os.path.join(models_dir, meta_file), 'r', encoding='utf-8') as f:
                meta = json.load(f)
                results.append(meta)
        except:
            pass

    if results:
        # 最新のトレーニング結果のみ表示
        latest_results = sorted(
            results,
            key=lambda x: x.get('trained_at', ''),
            reverse=True
        )[:10]

        for meta in latest_results:
            with st.expander(f"{meta.get('venue_code', meta.get('model_type', 'unknown'))} モデル"):
                st.write(f"**トレーニング日時**: {meta.get('trained_at', 'N/A')}")
                st.write(f"**サンプル数**: {meta.get('n_samples', 0):,}")
                st.write(f"**特徴量数**: {meta.get('n_features', 0)}")

                if 'metrics' in meta:
                    metrics = meta['metrics']
                    st.write(f"**AUC**: {metrics.get('mean_auc', 0):.4f} (±{metrics.get('std_auc', 0):.4f})")
                    st.write(f"**Accuracy**: {metrics.get('mean_accuracy', 0):.4f}")


def render_model_benchmark():
    """モデルベンチマーク画面"""
    st.header("📈 モデル性能ベンチマーク")

    st.info("""
    **新旧モデルの性能比較**:
    - 最近30日分のデータでテスト
    - AUC、Accuracy、Precision、Recall、F1スコアを評価
    - 改善度を可視化
    """)

    # ベンチマーク設定
    st.subheader("⚙️ ベンチマーク設定")

    test_days = st.slider("テスト期間（日）", 7, 60, 30)

    # ベンチマーク実行
    if st.button("📊 ベンチマーク実行", type="primary"):
        with st.spinner("ベンチマーク実行中..."):
            try:
                python_exe = sys.executable
                script_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    'scripts',
                    'benchmark_models.py'
                )

                result = subprocess.run(
                    [python_exe, script_path],
                    capture_output=True,
                    text=True,
                    timeout=600  # 10分タイムアウト
                )

                if result.returncode == 0:
                    st.success("✅ ベンチマーク完了！")
                    st.text_area("実行ログ", result.stdout, height=300)

                    # 結果を表示
                    display_benchmark_results()
                else:
                    st.error("❌ ベンチマーク失敗")
                    st.text_area("エラーログ", result.stderr, height=300)

            except subprocess.TimeoutExpired:
                st.error("⏱️ タイムアウト: 10分以内に完了しませんでした")
            except Exception as e:
                st.error(f"エラー: {e}")


def display_benchmark_results():
    """ベンチマーク結果を表示"""
    st.subheader("📊 ベンチマーク結果")

    benchmarks_dir = 'benchmarks'
    if not os.path.exists(benchmarks_dir):
        st.warning("ベンチマークディレクトリが存在しません")
        return

    # 最新のベンチマークファイルを取得
    benchmark_files = [f for f in os.listdir(benchmarks_dir) if f.endswith('.json')]

    if not benchmark_files:
        st.warning("ベンチマーク結果が見つかりません")
        return

    latest_file = sorted(benchmark_files, reverse=True)[0]

    try:
        with open(os.path.join(benchmarks_dir, latest_file), 'r', encoding='utf-8') as f:
            benchmark_data = json.load(f)

        st.write(f"**実行日時**: {benchmark_data.get('timestamp', 'N/A')}")

        comparisons = benchmark_data.get('comparisons', [])

        if not comparisons:
            st.warning("比較データがありません")
            return

        # 各会場の結果を表示
        for comp in comparisons:
            venue = comp.get('venue_code', 'unknown')

            with st.expander(f"会場: {venue}"):
                col1, col2, col3 = st.columns(3)

                old_model = comp.get('old_model')
                new_model = comp.get('new_model')
                improvements = comp.get('improvements')

                with col1:
                    st.metric(
                        "旧モデル AUC",
                        f"{old_model['auc']:.4f}" if old_model else "N/A"
                    )

                with col2:
                    st.metric(
                        "新モデル AUC",
                        f"{new_model['auc']:.4f}" if new_model else "N/A"
                    )

                with col3:
                    if improvements:
                        delta = improvements['auc_diff']
                        st.metric(
                            "改善度",
                            f"{delta:+.4f}",
                            f"{improvements['auc_improvement_pct']:+.2f}%"
                        )

                # 詳細メトリクス
                if new_model:
                    st.write("**新モデル詳細**:")
                    st.write(f"- Accuracy: {new_model.get('accuracy', 0):.4f}")
                    st.write(f"- Precision: {new_model.get('precision', 0):.4f}")
                    st.write(f"- Recall: {new_model.get('recall', 0):.4f}")
                    st.write(f"- F1 Score: {new_model.get('f1', 0):.4f}")

    except Exception as e:
        st.error(f"結果表示エラー: {e}")
