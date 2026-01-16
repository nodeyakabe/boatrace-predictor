"""
購入対象レース・候補レースのパフォーマンス分析コンポーネント

購入判定ロジックと同じ基準で過去レースを分類し、
それぞれの的中率・回収率を可視化
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import sqlite3
from typing import Dict, List, Tuple

from config.settings import DATABASE_PATH, VENUES
from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus
from src.betting.multi_bet_generator import MultiBetPattern


def get_venue_name(venue_code: str) -> str:
    """会場コードから会場名を取得"""
    venue_map = {
        '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
        '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
        '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
        '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
        '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
        '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
    }
    venue_code_str = str(venue_code).zfill(2) if isinstance(venue_code, int) else str(venue_code)
    return venue_map.get(venue_code_str, f'会場{venue_code}')


def analyze_bet_performance(
    start_date: str,
    end_date: str,
    prediction_type: str = 'before',
    venue_codes: List[str] = None
) -> Dict:
    """
    期間内のレースを購入対象・候補に分類し、パフォーマンスを集計

    Args:
        start_date: 開始日 (YYYY-MM-DD)
        end_date: 終了日 (YYYY-MM-DD)
        prediction_type: 予測タイプ ('advance' or 'before')
        venue_codes: 会場コード絞り込み（Noneなら全会場）

    Returns:
        {
            'target_races': [...],  # 購入対象レースのリスト
            'candidate_races': [...],  # 候補レースのリスト
            'target_stats': {...},  # 購入対象の統計
            'candidate_stats': {...},  # 候補の統計
            'all_candidates_stats': {...}  # 全候補（フィルタ前）の統計
        }
    """

    evaluator = BetTargetEvaluator(
        use_multi_bet=True,
        multi_bet_pattern=MultiBetPattern.PATTERN_H,
        enable_venue_wind_filter=True,
        enable_venue_course_adjustment=True,
        db_path=DATABASE_PATH
    )

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 期間内のレースを取得
    query = """
        SELECT r.id, r.venue_code, r.race_number, r.race_date, r.race_time
        FROM races r
        WHERE r.race_date BETWEEN ? AND ?
    """
    params = [start_date, end_date]

    if venue_codes:
        placeholders = ','.join('?' * len(venue_codes))
        query += f" AND r.venue_code IN ({placeholders})"
        params.extend(venue_codes)

    query += " ORDER BY r.race_date, r.venue_code, r.race_number"

    cursor.execute(query, params)
    races = cursor.fetchall()

    target_races = []
    candidate_races = []
    all_candidates = []  # フィルタ前の全候補

    for race in races:
        race_id = race['id']
        venue_code = race['venue_code']
        race_number = race['race_number']
        race_date = race['race_date']
        race_time = race['race_time']

        # レースデータを取得
        race_data = _get_race_data(cursor, race_id)
        if not race_data:
            continue

        # 予測データを取得
        predictions = _get_predictions(cursor, race_id, prediction_type)
        if not predictions:
            continue

        # オッズデータを取得
        odds_data = _get_odds_data(cursor, race_id, predictions)

        # 直前情報の有無
        has_beforeinfo = _check_beforeinfo(cursor, race_id)

        # BetTargetEvaluatorで判定
        try:
            bet_target = evaluator.evaluate_race(
                race_data=race_data,
                predictions=predictions,
                odds_data=odds_data,
                has_beforeinfo=has_beforeinfo
            )

            # 結果を取得
            result = _get_race_result(cursor, race_id)
            if not result:
                continue

            # 払戻金を取得
            payout = _get_payout(cursor, race_id, bet_target.combination)

            # レース情報を整形
            race_info = {
                'race_id': race_id,
                'venue_code': venue_code,
                'venue_name': get_venue_name(venue_code),
                'race_number': race_number,
                'race_date': race_date,
                'race_time': race_time,
                'combination': bet_target.combination,
                'odds': bet_target.odds,
                'confidence': bet_target.confidence,
                'result': result,
                'payout': payout,
                'hit': result == bet_target.combination,
                'status': bet_target.status.value,
                'reason': bet_target.reason,
                'odds_range': bet_target.odds_range
            }

            # ステータスで分類
            if bet_target.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                target_races.append(race_info)
            elif bet_target.status == BetStatus.CANDIDATE:
                all_candidates.append(race_info)

                # 候補レースフィルタリング（オッズ条件の80%以上）
                if bet_target.odds is None:
                    candidate_races.append(race_info)
                else:
                    try:
                        min_odds = float(bet_target.odds_range.split('-')[0])
                        threshold = min_odds * 0.8
                        if bet_target.odds >= threshold:
                            candidate_races.append(race_info)
                    except:
                        candidate_races.append(race_info)

        except Exception as e:
            continue

    conn.close()

    # 統計を計算
    target_stats = _calculate_stats(target_races)
    candidate_stats = _calculate_stats(candidate_races)
    all_candidates_stats = _calculate_stats(all_candidates)

    return {
        'target_races': target_races,
        'candidate_races': candidate_races,
        'all_candidates': all_candidates,
        'target_stats': target_stats,
        'candidate_stats': candidate_stats,
        'all_candidates_stats': all_candidates_stats
    }


def _get_race_data(cursor, race_id: int) -> Dict:
    """レースデータを取得（entries含む）"""
    cursor.execute("""
        SELECT
            r.*,
            rc.wind_speed, rc.wind_direction, rc.wave_height,
            rc.temperature, rc.water_temperature, rc.weather
        FROM races r
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.id = ?
    """, (race_id,))

    row = cursor.fetchone()
    if not row:
        return None

    race_data = dict(row)

    # entriesを取得
    cursor.execute("""
        SELECT
            e.pit_number,
            e.racer_number,
            e.racer_rank,
            e.motor_number,
            e.boat_number,
            e.win_rate,
            e.second_rate,
            e.local_win_rate,
            e.local_second_rate,
            e.motor_second_rate,
            e.boat_second_rate
        FROM entries e
        WHERE e.race_id = ?
        ORDER BY e.pit_number
    """, (race_id,))

    entries = []
    for entry_row in cursor.fetchall():
        entries.append(dict(entry_row))

    race_data['entries'] = entries

    return race_data


def _get_predictions(cursor, race_id: int, prediction_type: str) -> Dict:
    """予測データを取得（BetTargetEvaluator形式）"""
    cursor.execute("""
        SELECT pit_number, rank_prediction, confidence, total_score
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = ?
        ORDER BY rank_prediction
    """, (race_id, prediction_type))

    rows = cursor.fetchall()
    if len(rows) < 3:
        return None

    # BetTargetEvaluatorが期待する形式に変換
    # confidence: 信頼度ランク (A+, A, B, C, D)
    # old_pred/new_pred: 予測順位の辞書 {pit_number: rank}

    # 信頼度を取得（1位予想の信頼度を使用）
    confidence = rows[0]['confidence'] if rows[0]['confidence'] else 'D'

    # 予測順位の辞書を作成
    pred_dict = {}
    for row in rows:
        pred_dict[row['pit_number']] = row['rank_prediction']

    return {
        'confidence': confidence,
        'old_pred': pred_dict,  # advance予測として使用
        'new_pred': pred_dict if prediction_type == 'before' else None  # before予測
    }


def _get_odds_data(cursor, race_id: int, predictions: Dict) -> Dict:
    """オッズデータを取得"""
    if not predictions or 'old_pred' not in predictions:
        return {}

    # 予測順位から1-2-3位の枠番を取得
    pred_dict = predictions['old_pred']
    sorted_pits = sorted(pred_dict.items(), key=lambda x: x[1])

    if len(sorted_pits) < 3:
        return {}

    pred_1 = sorted_pits[0][0]  # 1位予想
    pred_2 = sorted_pits[1][0]  # 2位予想
    pred_3 = sorted_pits[2][0]  # 3位予想
    combination = f"{pred_1}-{pred_2}-{pred_3}"

    cursor.execute("""
        SELECT odds FROM trifecta_odds
        WHERE race_id = ? AND combination = ?
    """, (race_id, combination))

    row = cursor.fetchone()
    if row:
        return {combination: row['odds']}
    return {}


def _check_beforeinfo(cursor, race_id: int) -> bool:
    """直前情報の有無をチェック"""
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM race_details
        WHERE race_id = ? AND exhibition_time IS NOT NULL
    """, (race_id,))

    row = cursor.fetchone()
    return row['cnt'] > 0 if row else False


def _get_race_result(cursor, race_id: int) -> str:
    """レース結果を取得（三連単形式）"""
    cursor.execute("""
        SELECT pit_number, rank
        FROM results
        WHERE race_id = ? AND rank <= 3
        ORDER BY rank
    """, (race_id,))

    results = cursor.fetchall()
    if len(results) < 3:
        return None

    return f"{results[0]['pit_number']}-{results[1]['pit_number']}-{results[2]['pit_number']}"


def _get_payout(cursor, race_id: int, combination: str) -> float:
    """払戻金を取得"""
    cursor.execute("""
        SELECT amount FROM payouts
        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
    """, (race_id, combination))

    row = cursor.fetchone()
    return row['amount'] if row else 0.0


def _calculate_stats(races: List[Dict]) -> Dict:
    """統計を計算"""
    if not races:
        return {
            'total_races': 0,
            'hit_count': 0,
            'hit_rate': 0.0,
            'total_investment': 0,
            'total_return': 0,
            'net_profit': 0,
            'roi': 0.0,
            'avg_odds': 0.0,
            'avg_payout': 0.0
        }

    total_races = len(races)
    hit_count = sum(1 for r in races if r['hit'])
    hit_rate = hit_count / total_races if total_races > 0 else 0.0

    # 購入額は1レース1000円と仮定
    bet_amount = 1000
    total_investment = total_races * bet_amount
    total_return = sum(r['payout'] for r in races if r['hit'])
    net_profit = total_return - total_investment
    roi = (total_return / total_investment * 100) if total_investment > 0 else 0.0

    # オッズ平均（Noneを除外）
    odds_list = [r['odds'] for r in races if r['odds'] is not None]
    avg_odds = sum(odds_list) / len(odds_list) if odds_list else 0.0

    # 的中時払戻金平均
    payout_list = [r['payout'] for r in races if r['hit']]
    avg_payout = sum(payout_list) / len(payout_list) if payout_list else 0.0

    return {
        'total_races': total_races,
        'hit_count': hit_count,
        'hit_rate': hit_rate,
        'total_investment': total_investment,
        'total_return': total_return,
        'net_profit': net_profit,
        'roi': roi,
        'avg_odds': avg_odds,
        'avg_payout': avg_payout
    }


def render_bet_performance_analyzer():
    """購入対象・候補レースのパフォーマンス分析UI"""

    st.subheader("🎯 購入対象・候補レースのパフォーマンス分析")
    st.caption("総合タブで表示される購入対象と候補レースの過去実績を分析します")

    # 期間選択
    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input(
            "開始日",
            value=datetime.now().date() - timedelta(days=30),
            key="perf_start"
        )
    with col2:
        end_date = st.date_input(
            "終了日",
            value=datetime.now().date(),
            key="perf_end"
        )
    with col3:
        prediction_type = st.selectbox(
            "予測タイプ",
            ["before", "advance"],
            format_func=lambda x: "直前予測（実運用）" if x == "before" else "事前予測（バックテスト）",
            key="perf_pred_type"
        )

    if st.button("📊 分析実行", type="primary", use_container_width=True):
        with st.spinner("分析中..."):
            result = analyze_bet_performance(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                prediction_type=prediction_type
            )

            # セッションステートに保存
            st.session_state['perf_analysis_result'] = result

    # 分析結果が存在する場合のみ表示
    if 'perf_analysis_result' not in st.session_state:
        st.info("👆 「分析実行」ボタンを押して分析を開始してください")
        return

    result = st.session_state['perf_analysis_result']
    target_stats = result['target_stats']
    candidate_stats = result['candidate_stats']
    all_candidates_stats = result['all_candidates_stats']

    # ============ サマリーメトリクス ============
    st.markdown("### 📊 総合サマリー")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "🎯 購入対象レース",
            f"{target_stats['total_races']}レース",
            f"的中率 {target_stats['hit_rate']:.1%}"
        )
        st.metric(
            "回収率",
            f"{target_stats['roi']:.1f}%",
            f"{target_stats['net_profit']:+,.0f}円",
            delta_color="normal" if target_stats['net_profit'] >= 0 else "inverse"
        )

    with col2:
        st.metric(
            "🟡 候補レース（表示対象）",
            f"{candidate_stats['total_races']}レース",
            f"的中率 {candidate_stats['hit_rate']:.1%}"
        )
        st.metric(
            "回収率",
            f"{candidate_stats['roi']:.1f}%",
            f"{candidate_stats['net_profit']:+,.0f}円",
            delta_color="normal" if candidate_stats['net_profit'] >= 0 else "inverse"
        )

    with col3:
        st.metric(
            "⚪ 全候補（フィルタ前）",
            f"{all_candidates_stats['total_races']}レース",
            f"的中率 {all_candidates_stats['hit_rate']:.1%}"
        )
        st.metric(
            "回収率",
            f"{all_candidates_stats['roi']:.1f}%",
            f"{all_candidates_stats['net_profit']:+,.0f}円",
            delta_color="normal" if all_candidates_stats['net_profit'] >= 0 else "inverse"
        )

    st.caption(f"💡 候補レースは「オッズが条件の80%以上」のものだけを表示しています（{all_candidates_stats['total_races']}件 → {candidate_stats['total_races']}件）")

    # ============ グラフ表示 ============
    st.markdown("---")
    st.markdown("### 📈 パフォーマンスグラフ")

    # 比較グラフ
    tab1, tab2, tab3 = st.tabs(["的中率・回収率", "累計損益", "日別推移"])

    with tab1:
        _render_comparison_chart(target_stats, candidate_stats, all_candidates_stats)

    with tab2:
        _render_cumulative_profit_chart(result['target_races'], result['candidate_races'])

    with tab3:
        _render_daily_performance_chart(result['target_races'], result['candidate_races'])

    # ============ 詳細テーブル ============
    st.markdown("---")
    st.markdown("### 📋 詳細レース一覧")

    detail_tab1, detail_tab2 = st.tabs(["🎯 購入対象レース", "🟡 候補レース"])

    with detail_tab1:
        _render_race_detail_table(result['target_races'], "購入対象")

    with detail_tab2:
        _render_race_detail_table(result['candidate_races'], "候補")


def _render_comparison_chart(target_stats: Dict, candidate_stats: Dict, all_candidates_stats: Dict):
    """的中率・回収率の比較チャート"""

    fig = go.Figure()

    categories = ['購入対象', '候補（表示）', '候補（全体）']
    hit_rates = [
        target_stats['hit_rate'] * 100,
        candidate_stats['hit_rate'] * 100,
        all_candidates_stats['hit_rate'] * 100
    ]
    rois = [
        target_stats['roi'],
        candidate_stats['roi'],
        all_candidates_stats['roi']
    ]

    # 的中率
    fig.add_trace(go.Bar(
        name='的中率 (%)',
        x=categories,
        y=hit_rates,
        marker_color='lightblue',
        text=[f"{v:.1f}%" for v in hit_rates],
        textposition='outside'
    ))

    # 回収率
    fig.add_trace(go.Bar(
        name='回収率 (%)',
        x=categories,
        y=rois,
        marker_color='lightgreen',
        text=[f"{v:.1f}%" for v in rois],
        textposition='outside'
    ))

    fig.update_layout(
        title="的中率・回収率の比較",
        xaxis_title="レース分類",
        yaxis_title="割合 (%)",
        barmode='group',
        height=400
    )

    st.plotly_chart(fig, use_container_width=True)


def _render_cumulative_profit_chart(target_races: List[Dict], candidate_races: List[Dict]):
    """累計損益チャート"""

    # 日付順にソート
    target_sorted = sorted(target_races, key=lambda x: (x['race_date'], x['race_time']))
    candidate_sorted = sorted(candidate_races, key=lambda x: (x['race_date'], x['race_time']))

    # 累計損益を計算
    bet_amount = 1000

    target_cumulative = []
    cumulative_profit = 0
    for race in target_sorted:
        cumulative_profit += (race['payout'] - bet_amount) if race['hit'] else -bet_amount
        target_cumulative.append({
            'date': race['race_date'],
            'profit': cumulative_profit
        })

    candidate_cumulative = []
    cumulative_profit = 0
    for race in candidate_sorted:
        cumulative_profit += (race['payout'] - bet_amount) if race['hit'] else -bet_amount
        candidate_cumulative.append({
            'date': race['race_date'],
            'profit': cumulative_profit
        })

    fig = go.Figure()

    if target_cumulative:
        fig.add_trace(go.Scatter(
            x=[r['date'] for r in target_cumulative],
            y=[r['profit'] for r in target_cumulative],
            mode='lines+markers',
            name='購入対象',
            line=dict(color='blue', width=2),
            marker=dict(size=4)
        ))

    if candidate_cumulative:
        fig.add_trace(go.Scatter(
            x=[r['date'] for r in candidate_cumulative],
            y=[r['profit'] for r in candidate_cumulative],
            mode='lines+markers',
            name='候補',
            line=dict(color='orange', width=2),
            marker=dict(size=4)
        ))

    fig.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="損益分岐点")

    fig.update_layout(
        title="累計損益の推移",
        xaxis_title="日付",
        yaxis_title="累計損益 (円)",
        height=400,
        hovermode='x unified'
    )

    st.plotly_chart(fig, use_container_width=True)


def _render_daily_performance_chart(target_races: List[Dict], candidate_races: List[Dict]):
    """日別パフォーマンスチャート"""

    # 日別集計
    from collections import defaultdict

    target_daily = defaultdict(lambda: {'total': 0, 'hit': 0, 'profit': 0})
    for race in target_races:
        date = race['race_date']
        target_daily[date]['total'] += 1
        if race['hit']:
            target_daily[date]['hit'] += 1
            target_daily[date]['profit'] += race['payout'] - 1000
        else:
            target_daily[date]['profit'] -= 1000

    candidate_daily = defaultdict(lambda: {'total': 0, 'hit': 0, 'profit': 0})
    for race in candidate_races:
        date = race['race_date']
        candidate_daily[date]['total'] += 1
        if race['hit']:
            candidate_daily[date]['hit'] += 1
            candidate_daily[date]['profit'] += race['payout'] - 1000
        else:
            candidate_daily[date]['profit'] -= 1000

    # DataFrameに変換
    target_df = pd.DataFrame([
        {
            'date': date,
            'hit_rate': (data['hit'] / data['total'] * 100) if data['total'] > 0 else 0,
            'profit': data['profit'],
            'type': '購入対象'
        }
        for date, data in target_daily.items()
    ])

    candidate_df = pd.DataFrame([
        {
            'date': date,
            'hit_rate': (data['hit'] / data['total'] * 100) if data['total'] > 0 else 0,
            'profit': data['profit'],
            'type': '候補'
        }
        for date, data in candidate_daily.items()
    ])

    combined_df = pd.concat([target_df, candidate_df], ignore_index=True)

    if not combined_df.empty:
        fig = px.scatter(
            combined_df,
            x='hit_rate',
            y='profit',
            color='type',
            size=[10] * len(combined_df),
            hover_data=['date'],
            title="日別パフォーマンス（的中率 vs 損益）",
            labels={'hit_rate': '的中率 (%)', 'profit': '日別損益 (円)', 'type': '分類'}
        )

        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("グラフ表示に十分なデータがありません")


def _render_race_detail_table(races: List[Dict], title: str):
    """レース詳細テーブル"""

    if not races:
        st.info(f"{title}レースがありません")
        return

    # DataFrameに変換
    df = pd.DataFrame(races)

    # 表示用に整形
    display_df = pd.DataFrame({
        '日付': df['race_date'],
        '会場': df['venue_name'],
        'R': df['race_number'],
        '買い目': df['combination'],
        '結果': df['result'],
        '的中': df['hit'].apply(lambda x: '⭕' if x else '❌'),
        'オッズ': df['odds'].apply(lambda x: f"{x:.1f}倍" if x else '-'),
        '払戻': df.apply(lambda r: f"{r['payout']:,.0f}円" if r['hit'] else '-', axis=1),
        '理由': df['reason']
    })

    # 的中レースをハイライト
    def highlight_hit(row):
        if row['的中'] == '⭕':
            return ['background-color: #e8f5e9'] * len(row)
        return [''] * len(row)

    styled_df = display_df.style.apply(highlight_hit, axis=1)

    st.dataframe(styled_df, use_container_width=True, height=400)

    # サマリー
    hit_count = df['hit'].sum()
    total = len(df)
    total_payout = df[df['hit']]['payout'].sum()
    total_investment = total * 1000

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("総レース数", f"{total}レース")
    with col2:
        st.metric("的中数", f"{hit_count}レース", f"{hit_count/total:.1%}")
    with col3:
        st.metric("総投資額", f"{total_investment:,.0f}円")
    with col4:
        st.metric("総払戻額", f"{total_payout:,.0f}円", f"{total_payout-total_investment:+,.0f}円")
