"""
スマート予想レコメンドUI

Phase 1-3の統合予測機能を活用した買い目推奨システムのUI
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from typing import Dict, List, Optional, Tuple
import sys
from pathlib import Path

# プロジェクトのルートディレクトリを追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.betting.bet_generator import BetGenerator, BetTicket
from src.betting.race_scorer import RaceScorer, RaceScore
from src.prediction.integrated_predictor import IntegratedPredictor
from src.scraper.odds_fetcher import OddsFetcher
from src.database.fast_data_manager import FastDataManager
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class SmartRecommendationsUI:
    """スマート予想レコメンドUIクラス"""

    def __init__(self):
        """初期化"""
        self.bet_generator = BetGenerator()
        self.race_scorer = RaceScorer()
        self.predictor = IntegratedPredictor()
        self.odds_fetcher = OddsFetcher()
        self.data_manager = FastDataManager()

    def render(self):
        """UIをレンダリング"""
        st.header("🎯 スマート予想レコメンド")

        # タブを作成
        tab1, tab2, tab3 = st.tabs([
            "📊 的中率重視",
            "💰 期待値重視",
            "⚙️ 設定"
        ])

        with tab1:
            self._render_accuracy_focused()

        with tab2:
            self._render_value_focused()

        with tab3:
            self._render_settings()

    def _render_accuracy_focused(self):
        """的中率重視タブ"""
        st.subheader("的中率重視のおすすめレース")
        st.caption("本命の勝率が高く、安定して当たりやすいレースを推奨します")

        # 日付選択
        col1, col2 = st.columns([1, 2])
        with col1:
            target_date = st.date_input(
                "対象日",
                value=datetime.now().date(),
                key="accuracy_date"
            )

        # レース取得とスコアリング
        with st.spinner("レースを分析中..."):
            race_scores = self._get_race_scores(target_date, mode="accuracy")

        if not race_scores:
            st.warning("対象日のレースデータがありません")
            return

        # TOP10レースを表示
        top_races = race_scores[:10]

        for idx, race_score in enumerate(top_races, 1):
            self._render_race_card(race_score, idx, mode="accuracy")

    def _render_value_focused(self):
        """期待値重視タブ"""
        st.subheader("期待値重視のおすすめレース")
        st.caption("オッズと予測確率の乖離があり、期待値が高いレースを推奨します")

        # 日付選択
        col1, col2 = st.columns([1, 2])
        with col1:
            target_date = st.date_input(
                "対象日",
                value=datetime.now().date(),
                key="value_date"
            )

        # レース取得とスコアリング
        with st.spinner("レースを分析中..."):
            race_scores = self._get_race_scores(target_date, mode="value")

        if not race_scores:
            st.warning("対象日のレースデータがありません")
            return

        # TOP10レースを表示
        top_races = race_scores[:10]

        for idx, race_score in enumerate(top_races, 1):
            self._render_race_card(race_score, idx, mode="value")

    def _render_race_card(self, race_score: RaceScore, rank: int, mode: str):
        """レースカードを表示"""
        # スコアに応じた背景色
        if mode == "accuracy":
            score = race_score.accuracy_score * 0.7 + race_score.stability_score * 0.3
        else:
            score = race_score.value_score * 0.6 + race_score.accuracy_score * 0.4

        if score >= 80:
            border_color = "#ff6b6b"  # 赤（最高）
            bg_color = "#ffe0e0"
        elif score >= 65:
            border_color = "#ffa500"  # オレンジ（高）
            bg_color = "#fff4e0"
        elif score >= 50:
            border_color = "#4ecdc4"  # 青緑（中）
            bg_color = "#e0f4f4"
        else:
            border_color = "#95a5a6"  # グレー（低）
            bg_color = "#f0f0f0"

        # カードのスタイル
        card_style = f"""
        <style>
        .race-card-{rank} {{
            border: 2px solid {border_color};
            border-radius: 10px;
            padding: 15px;
            margin: 10px 0;
            background-color: {bg_color};
        }}
        </style>
        """
        st.markdown(card_style, unsafe_allow_html=True)

        # カード内容
        with st.container():
            st.markdown(f'<div class="race-card-{rank}">', unsafe_allow_html=True)

            # ヘッダー行
            col1, col2, col3, col4 = st.columns([1, 2, 2, 2])
            with col1:
                st.metric("順位", f"#{rank}")
            with col2:
                st.metric("レース", f"{race_score.venue} {race_score.race_no}R")
            with col3:
                if mode == "accuracy":
                    st.metric("信頼度", f"{score:.1f}%")
                else:
                    st.metric("期待値", f"{race_score.expected_return:.2f}")
            with col4:
                stars = "⭐" * self._get_stars(score)
                st.markdown(f"### {stars}")

            # 予測情報
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"**本命**: {race_score.favorite_boat}号艇")
            with col2:
                st.markdown(f"**勝率**: {race_score.favorite_prob:.1%}")
            with col3:
                st.markdown(f"**信頼度**: {race_score.confidence_level:.1%}")

            # 展開可能な詳細セクション
            with st.expander("🎯 推奨買い目を見る"):
                self._render_bet_recommendations(race_score)

            # 予測理由
            with st.expander("📊 予測の根拠"):
                for reason in race_score.prediction_reasons[:3]:
                    st.markdown(f"- {reason}")

            st.markdown('</div>', unsafe_allow_html=True)

    def _render_bet_recommendations(self, race_score: RaceScore):
        """買い目推奨を表示"""
        # ダミーの予測データを使用（実際は race_score から取得）
        predictions = self._get_race_predictions(race_score.race_id)
        if not predictions:
            st.warning("予測データが取得できません")
            return

        # オッズデータを取得
        odds_data = self._get_odds_data(race_score.race_id)

        # 買い目を生成
        bets = self.bet_generator.generate_bets(predictions, odds_data)

        if not bets:
            st.warning("推奨買い目がありません")
            return

        # 買い目テーブル
        bet_data = []
        for bet in bets:
            stars = "⭐" * bet.recommendation_level
            bet_data.append({
                "舟券": bet.bet_type,
                "買い目": bet.format_combination(),
                "信頼度": f"{bet.confidence:.1%}",
                "期待値": f"{bet.expected_value:.2f}",
                "推定オッズ": f"{bet.estimated_odds:.1f}倍",
                "推奨度": stars
            })

        df = pd.DataFrame(bet_data)
        st.dataframe(df, hide_index=True)

        # 購入金額シミュレーション
        st.markdown("### 💴 購入金額シミュレーション")
        col1, col2, col3 = st.columns(3)
        with col1:
            budget = st.number_input(
                "予算（円）",
                min_value=100,
                max_value=100000,
                value=1000,
                step=100,
                key=f"budget_{race_score.race_id}"
            )
        with col2:
            bet_count = st.slider(
                "購入点数",
                min_value=1,
                max_value=len(bets),
                value=min(3, len(bets)),
                key=f"bet_count_{race_score.race_id}"
            )

        # 購入配分を計算
        selected_bets = bets[:bet_count]
        total_confidence = sum(bet.confidence for bet in selected_bets)

        if total_confidence > 0:
            allocation_data = []
            for bet in selected_bets:
                amount = int(budget * bet.confidence / total_confidence / 100) * 100
                if amount > 0:
                    allocation_data.append({
                        "買い目": f"{bet.bet_type} {bet.format_combination()}",
                        "購入金額": f"{amount}円",
                        "期待リターン": f"{amount * bet.expected_value:.0f}円"
                    })

            if allocation_data:
                st.dataframe(pd.DataFrame(allocation_data), hide_index=True)

                # 合計期待リターン
                total_return = sum(
                    int(d["購入金額"].replace("円", "")) * selected_bets[i].expected_value
                    for i, d in enumerate(allocation_data)
                )
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("投資額", f"{budget}円")
                with col2:
                    color = "green" if total_return > budget else "red"
                    st.markdown(
                        f'<p style="color: {color}; font-size: 20px; font-weight: bold;">'
                        f'期待リターン: {total_return:.0f}円</p>',
                        unsafe_allow_html=True
                    )

    def _render_settings(self):
        """設定タブ"""
        st.subheader("⚙️ レコメンド設定")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### 的中率重視の設定")

            accuracy_weight_favorite = st.slider(
                "本命重視度",
                min_value=0.0,
                max_value=1.0,
                value=0.5,
                step=0.1,
                key="accuracy_weight_favorite"
            )

            accuracy_weight_stability = st.slider(
                "安定性重視度",
                min_value=0.0,
                max_value=1.0,
                value=0.3,
                step=0.1,
                key="accuracy_weight_stability"
            )

            accuracy_min_confidence = st.slider(
                "最低信頼度",
                min_value=0.0,
                max_value=1.0,
                value=0.3,
                step=0.05,
                key="accuracy_min_confidence"
            )

        with col2:
            st.markdown("### 期待値重視の設定")

            value_weight_return = st.slider(
                "リターン重視度",
                min_value=0.0,
                max_value=1.0,
                value=0.6,
                step=0.1,
                key="value_weight_return"
            )

            value_weight_discrepancy = st.slider(
                "オッズ乖離重視度",
                min_value=0.0,
                max_value=1.0,
                value=0.3,
                step=0.1,
                key="value_weight_discrepancy"
            )

            value_min_expected = st.slider(
                "最低期待値",
                min_value=0.5,
                max_value=2.0,
                value=1.0,
                step=0.1,
                key="value_min_expected"
            )

        st.markdown("### 買い目生成設定")

        col1, col2, col3 = st.columns(3)

        with col1:
            max_tickets = st.number_input(
                "最大買い目数",
                min_value=1,
                max_value=20,
                value=10,
                key="max_tickets"
            )

        with col2:
            trifecta_max = st.number_input(
                "3連単最大数",
                min_value=0,
                max_value=10,
                value=6,
                key="trifecta_max"
            )

        with col3:
            trio_max = st.number_input(
                "3連複最大数",
                min_value=0,
                max_value=10,
                value=3,
                key="trio_max"
            )

        # 設定保存ボタン
        if st.button("設定を保存", type="primary"):
            st.success("設定を保存しました")
            # TODO: 実際の設定保存処理

    def _get_race_scores(self,
                        target_date: datetime.date,
                        mode: str = "accuracy") -> List[RaceScore]:
        """レーススコアを取得"""
        try:
            # 対象日のレース一覧を取得
            races = self._get_races_for_date(target_date)
            if not races:
                return []

            race_scores = []

            for race_info in races:
                race_id = race_info["race_id"]

                # 予測を実行
                prediction_result = self.predictor.predict_race(
                    race_id=race_id,
                    beforeinfo_data=race_info.get("beforeinfo"),
                    historical_data=race_info.get("historical"),
                    include_xai=True
                )

                if not prediction_result["success"]:
                    continue

                # スコアリング
                race_score = self.race_scorer.score_race(
                    race_id=race_id,
                    predictions=prediction_result["win_probabilities"],
                    feature_importance=prediction_result["feature_importance"],
                    odds_data=race_info.get("odds"),
                    xai_explanations=prediction_result.get("xai_explanations")
                )

                race_scores.append(race_score)

            # ランキング
            return self.race_scorer.rank_races(race_scores, mode=mode)

        except Exception as e:
            logger.error(f"レーススコア取得エラー: {e}")
            return []

    def _get_races_for_date(self, target_date: datetime.date) -> List[Dict]:
        """指定日のレース情報を取得"""
        # ダミーデータ（実際はデータベースから取得）
        venues = ["桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖",
                 "蒲郡", "常滑", "津", "三国", "びわこ", "住之江",
                 "尼崎", "鳴門", "丸亀", "児島", "宮島", "徳山",
                 "下関", "若松", "芦屋", "福岡", "唐津", "大村"]

        races = []
        for venue in venues[:6]:  # テスト用に6場のみ
            for race_no in range(1, 13):
                race_id = f"{target_date}_{venue}_{race_no}R"
                races.append({
                    "race_id": race_id,
                    "venue": venue,
                    "race_no": race_no,
                    "beforeinfo": None,
                    "historical": None,
                    "odds": None
                })

        return races

    def _get_race_predictions(self, race_id: str) -> Optional[Dict[str, float]]:
        """レースの予測結果を取得"""
        # ダミー予測（実際は IntegratedPredictor から取得）
        import random
        random.seed(hash(race_id))

        probs = [random.random() for _ in range(6)]
        total = sum(probs)
        predictions = {str(i+1): p/total for i, p in enumerate(probs)}

        return predictions

    def _get_odds_data(self, race_id: str) -> Optional[Dict]:
        """オッズデータを取得"""
        # ダミーオッズ（実際は OddsFetcher から取得）
        import random
        random.seed(hash(race_id))

        return {
            "単勝": {
                "1": random.uniform(1.5, 10.0),
                "2": random.uniform(2.0, 15.0),
                "3": random.uniform(3.0, 20.0),
                "4": random.uniform(4.0, 30.0),
                "5": random.uniform(5.0, 40.0),
                "6": random.uniform(6.0, 50.0)
            }
        }

    def _get_stars(self, score: float) -> int:
        """スコアから星の数を取得"""
        if score >= 80:
            return 5
        elif score >= 65:
            return 4
        elif score >= 50:
            return 3
        elif score >= 35:
            return 2
        else:
            return 1