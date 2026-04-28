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

    from src.betting.evaluator_helpers import create_standard_evaluator
    evaluator = create_standard_evaluator(db_path=DATABASE_PATH)

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

        # 予測データを取得（generate_daily_predictions.pyと同じ形式）
        predictions = _get_predictions(cursor, race_id, prediction_type)
        if not predictions:
            continue

        # オッズデータを取得（全組み合わせ）
        odds_data = _get_odds_data_all(cursor, race_id)

        # 直前情報の有無
        has_beforeinfo = prediction_type == 'before'

        # advance予測のtop3を取得（advance/beforeフィルタ用・before時のみ意味あり）
        advance_top3 = _get_advance_top3(cursor, race_id) if has_beforeinfo else None

        # BetTargetEvaluatorで判定
        try:
            bet_target = evaluator.evaluate_race(
                race_data=race_data,
                predictions=predictions,
                odds_data=odds_data if odds_data else None,
                has_beforeinfo=has_beforeinfo,
                advance_top3=advance_top3,
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
    """予測データを取得（generate_daily_predictions.pyと同じ形式）"""
    cursor.execute("""
        SELECT pit_number, rank_prediction, confidence, total_score
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = ?
        ORDER BY rank_prediction
    """, (race_id, prediction_type))

    rows = cursor.fetchall()
    if len(rows) < 3:
        return None

    all_pred = [row['pit_number'] for row in rows]  # 全件（パターンH用に5位以上が必要）

    # 1着予測選手の登録番号を取得（逃げ率/バイアスフィルター用）
    first_racer_number = None
    if all_pred:
        cursor.execute(
            "SELECT racer_number FROM entries WHERE race_id = ? AND pit_number = ?",
            (race_id, all_pred[0])
        )
        row = cursor.fetchone()
        if row:
            first_racer_number = row['racer_number']

    return {
        'confidence': rows[0]['confidence'] if rows[0]['confidence'] else 'D',
        'total_score': rows[0]['total_score'] if rows[0]['total_score'] else None,  # スコアフィルター用
        'old_prediction': all_pred,  # 全6位まで（p143/p142等の4位以上参照に必要）
        'new_prediction': all_pred,
        'first_racer_number': first_racer_number,  # 逃げ率/バイアスフィルター用
    }


def _get_odds_data_all(cursor, race_id: int) -> Dict:
    """オッズデータを取得（全組み合わせ - パターンH用）"""
    cursor.execute(
        "SELECT combination, odds FROM trifecta_odds WHERE race_id = ?",
        (race_id,)
    )
    result = {row['combination']: row['odds'] for row in cursor.fetchall() if row['odds']}
    return result if result else None


def _get_advance_top3(cursor, race_id: int):
    """advance予測の1-2-3位ピット番号を取得（advance/beforeフィルタ用）"""
    cursor.execute("""
        SELECT pit_number, rank_prediction
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'advance' AND rank_prediction IN (1, 2, 3)
        ORDER BY rank_prediction
    """, (race_id,))
    rows = cursor.fetchall()
    if len(rows) < 3:
        return None
    rank_to_pit = {row['rank_prediction']: row['pit_number'] for row in rows}
    if 1 in rank_to_pit and 2 in rank_to_pit and 3 in rank_to_pit:
        return [rank_to_pit[1], rank_to_pit[2], rank_to_pit[3]]
    return None


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
            st.session_state['perf_analysis_start'] = start_date.strftime("%Y-%m-%d")
            st.session_state['perf_analysis_end'] = end_date.strftime("%Y-%m-%d")

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

    # ============ 条件別月次収支サマリー ============
    st.markdown("---")
    _analysis_start = st.session_state.get('perf_analysis_start', start_date.strftime("%Y-%m-%d"))
    _analysis_end = st.session_state.get('perf_analysis_end', end_date.strftime("%Y-%m-%d"))
    render_monthly_condition_summary(_analysis_start, _analysis_end)

    # ============ 的中レース詳細リスト ============
    st.markdown("---")
    render_hit_races_detail(_analysis_start, _analysis_end)


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


# ============================================================
# 条件別月次収支サマリー
# ============================================================

# 組み合わせ式マップ（SQLで使用）
_COMBO_SQL_EXPRS = {
    'p123': "CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)",
    'p124': "CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)",
    'p132': "CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)",
    'p142': "CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)||'-'||CAST(rp2.pit_number AS TEXT)",
    'p143': "CAST(rp1.pit_number AS TEXT)||'-'||CAST(rp4.pit_number AS TEXT)||'-'||CAST(rp3.pit_number AS TEXT)",
}


def _get_cond_patterns(cond: Dict) -> List[Tuple[str, int]]:
    """条件から (買い目パターンキー, ベット金額) のリストを返す"""
    if cond.get('use_pattern_h'):
        # PATTERN_H2 (pattern_h_exclude_p5=True) → p1-p2-p3 (200円) + p1-p2-p4 (100円)
        # multi_bet_generator.py: PATTERN_H2 は bet_amounts=[200, 100]
        return [('p123', 200), ('p124', 100)]
    elif cond.get('use_pattern_p142'):
        return [('p142', 100)]
    elif cond.get('use_pattern_p132'):
        return [('p132', 100)]
    elif cond.get('use_pattern_p143'):
        return [('p143', 100)]
    elif cond.get('use_pattern_p124'):
        return [('p124', 100)]
    else:
        return [('p123', 100)]


def _build_cond_where(cond: Dict, start_date: str, end_date: str, gvme: List[Tuple]) -> Tuple[str, list]:
    """条件のWHERE句とパラメータを生成"""
    where_parts = ["r.race_date BETWEEN ? AND ?"]
    params = [start_date, end_date]

    if cond.get('venue_filter'):
        # venue_code はDB上ゼロパディング文字列（例: '07'）なので整数は変換する
        venue_strs = [f"{v:02d}" if isinstance(v, int) else str(v).zfill(2)
                      for v in cond['venue_filter']]
        phs = ','.join('?' * len(venue_strs))
        where_parts.append(f"r.venue_code IN ({phs})")
        params.extend(venue_strs)

    if cond.get('month_exclude'):
        phs = ','.join('?' * len(cond['month_exclude']))
        where_parts.append(
            f"CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN ({phs})"
        )
        params.extend(cond['month_exclude'])

    for vc, mo in gvme:
        # GLOBAL_VENUE_MONTH_EXCLUDES の venue_code も整数なのでゼロパディング変換
        vc_str = f"{vc:02d}" if isinstance(vc, int) else str(vc).zfill(2)
        where_parts.append(
            "NOT (r.venue_code=? AND CAST(strftime('%m', r.race_date) AS INTEGER)=?)"
        )
        params.extend([vc_str, mo])

    if cond.get('confidence'):
        where_parts.append("rp1.confidence=?")
        params.append(cond['confidence'])

    if cond.get('c1_rank'):
        phs = ','.join('?' * len(cond['c1_rank']))
        where_parts.append(f"e1.racer_rank IN ({phs})")
        params.extend(cond['c1_rank'])

    if cond.get('odds_min') is not None:
        where_parts.append("t.odds>=?")
        params.append(cond['odds_min'])
    if cond.get('odds_max') is not None:
        # バックテストと合わせて「未満（<）」を使用
        where_parts.append("t.odds<?")
        params.append(cond['odds_max'])

    if cond.get('score_min') is not None:
        where_parts.append("rp1.total_score>=?")
        params.append(cond['score_min'])
    if cond.get('score_max') is not None:
        # バックテストと合わせて「未満（<）」を使用
        where_parts.append("rp1.total_score<?")
        params.append(cond['score_max'])

    return " AND ".join(where_parts), params


@st.cache_data(ttl=600)
def _load_condition_monthly_stats(start_date: str, end_date: str) -> Dict:
    """条件別×月の収支データをSQLで集計（近似値・advance/before一致フィルタ未適用）"""
    from config.bet_conditions import STANDARD_BET_CONDITIONS, GLOBAL_VENUE_MONTH_EXCLUDES

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    all_results = {}

    for cond in STANDARD_BET_CONDITIONS:
        cond_id = cond['id']
        patterns = _get_cond_patterns(cond)
        month_stats: Dict[str, Dict] = {}

        for combo_key, bet_amount in patterns:
            combo_expr = _COMBO_SQL_EXPRS[combo_key]
            needs_rp4 = combo_key in ('p124', 'p142', 'p143')

            rp4_join = (
                "LEFT JOIN race_predictions rp4 "
                "ON r.id=rp4.race_id AND rp4.prediction_type='before' AND rp4.rank_prediction=4"
            ) if needs_rp4 else ""

            where_sql, params = _build_cond_where(
                cond, start_date, end_date, GLOBAL_VENUE_MONTH_EXCLUDES
            )

            sql = f"""
                SELECT
                    strftime('%Y-%m', r.race_date) AS ym,
                    COUNT(*) AS bets,
                    SUM(CASE WHEN pay.amount IS NOT NULL THEN 1 ELSE 0 END) AS hits,
                    SUM(COALESCE(pay.amount, 0) * ? / 100) AS total_return
                FROM races r
                JOIN race_predictions rp1
                    ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
                JOIN race_predictions rp2
                    ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
                JOIN race_predictions rp3
                    ON r.id=rp3.race_id AND rp3.prediction_type='before' AND rp3.rank_prediction=3
                {rp4_join}
                JOIN entries e1 ON r.id=e1.race_id AND e1.pit_number=1
                JOIN trifecta_odds t
                    ON r.id=t.race_id AND t.combination=({combo_expr})
                LEFT JOIN payouts pay
                    ON r.id=pay.race_id AND pay.bet_type='trifecta'
                    AND pay.combination=({combo_expr})
                WHERE {where_sql}
                GROUP BY strftime('%Y-%m', r.race_date)
                ORDER BY ym
            """

            try:
                # bet_amount を先頭パラメータに追加（SUM内の * ? / 100 用）
                cursor.execute(sql, [bet_amount] + list(params))
                for row in cursor.fetchall():
                    ym, bets, hits, total_return = row
                    if ym not in month_stats:
                        month_stats[ym] = {'bets': 0, 'hits': 0, 'invest': 0, 'return': 0}
                    month_stats[ym]['bets'] += bets
                    month_stats[ym]['hits'] += hits
                    month_stats[ym]['invest'] += bets * bet_amount
                    month_stats[ym]['return'] += total_return
            except Exception:
                pass

        all_results[cond_id] = {
            'name': cond.get('name', cond_id),
            'monthly': month_stats,
        }

    conn.close()
    return all_results


def render_monthly_condition_summary(start_date: str, end_date: str):
    """条件別月次収支サマリーを表示"""
    st.markdown("### 📅 条件別月次収支サマリー")
    st.caption(
        "各条件・月のROI（100円ベット基準）を色分け表示。"
        "🟢 ≥150% ／ 🟩 ≥100% ／ 🟨 黒字 ／ 🟥 赤字　"
        "※SQLベース近似値（advance/before一致フィルタ未適用）"
    )

    with st.spinner("月次データ集計中..."):
        data = _load_condition_monthly_stats(start_date, end_date)

    all_months = sorted(set(
        m for cd in data.values() for m in cd['monthly'].keys()
    ))

    if not all_months:
        st.info("期間内に対象データがありません")
        return

    # 表示月数選択
    month_options = [12, 24, 36]
    if len(all_months) not in month_options:
        month_options.append(len(all_months))
    month_options = sorted(set(month_options))

    col_sel, _ = st.columns([1, 3])
    with col_sel:
        max_months = st.selectbox(
            "表示月数",
            month_options,
            format_func=lambda x: f"直近{x}ヶ月" if x < len(all_months) else f"全期間（{x}ヶ月）",
            key="monthly_cond_max_months"
        )
    display_months = all_months[-max_months:]

    # ピボットテーブル作成
    rows = []
    for cond_id, cond_data in data.items():
        row: Dict = {'条件': cond_id}
        t_invest = t_return = t_bets = t_hits = 0

        for m in display_months:
            md = cond_data['monthly'].get(m)
            if md and md['invest'] > 0:
                roi = md['return'] / md['invest'] * 100
                row[m] = round(roi, 1)
                t_invest += md['invest']
                t_return += md['return']
                t_bets += md['bets']
                t_hits += md['hits']
            else:
                row[m] = float('nan')

        if t_invest > 0:
            row['全ROI'] = round(t_return / t_invest * 100, 1)
            row['収支'] = int(t_return - t_invest)
            row['件数'] = t_bets
            row['的中'] = t_hits
        else:
            row['全ROI'] = float('nan')
            row['収支'] = 0
            row['件数'] = 0
            row['的中'] = 0
        rows.append(row)

    df = pd.DataFrame(rows)

    # セル色付け（ROI値ベース）
    def _color_roi_col(col):
        styles = []
        for val in col:
            try:
                v = float(val)
                if v != v:  # NaN check
                    styles.append('color: #bbbbbb')
                elif v >= 150:
                    styles.append('background-color: #66bb6a; color: white; font-weight: bold')
                elif v >= 100:
                    styles.append('background-color: #c8e6c9')
                elif v > 0:
                    styles.append('background-color: #fff9c4')
                else:
                    styles.append('background-color: #ffcdd2')
            except (TypeError, ValueError):
                styles.append('color: #bbbbbb')
        return styles

    roi_cols = display_months + ['全ROI']
    styled = df.style.apply(_color_roi_col, subset=roi_cols)

    # フォーマット
    fmt: Dict = {m: lambda x: f"{int(x)}%" if x == x else '-' for m in display_months}
    fmt['全ROI'] = lambda x: f"{x:.1f}%" if x == x else '-'
    fmt['収支'] = lambda x: f"{x:+,}円"
    styled = styled.format(fmt, na_rep='-')

    st.dataframe(styled, use_container_width=True,
                 height=min(500, 60 + len(rows) * 38))
    st.caption(
        f"表示期間: {display_months[0]} ～ {display_months[-1]}　"
        f"条件数: {len(rows)}件"
    )


# ============================================================
# 的中レース詳細リスト
# ============================================================

@st.cache_data(ttl=600)
def _load_hit_races_detail(start_date: str, end_date: str) -> List[Dict]:
    """全条件の的中レースを一覧取得し払戻降順で返す"""
    from config.bet_conditions import STANDARD_BET_CONDITIONS, GLOBAL_VENUE_MONTH_EXCLUDES

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    hit_races = []

    for cond in STANDARD_BET_CONDITIONS:
        cond_id = cond['id']
        patterns = _get_cond_patterns(cond)

        for combo_key, _bet_amount in patterns:
            combo_expr = _COMBO_SQL_EXPRS[combo_key]
            needs_rp4 = combo_key in ('p124', 'p142', 'p143')

            rp4_join = (
                "LEFT JOIN race_predictions rp4 "
                "ON r.id=rp4.race_id AND rp4.prediction_type='before' AND rp4.rank_prediction=4"
            ) if needs_rp4 else ""

            where_sql, params = _build_cond_where(
                cond, start_date, end_date, GLOBAL_VENUE_MONTH_EXCLUDES
            )

            # INNER JOIN payouts → 的中のみ
            sql = f"""
                SELECT
                    r.race_date,
                    r.venue_code,
                    r.race_number,
                    r.id AS race_id,
                    ({combo_expr}) AS combination,
                    t.odds,
                    pay.amount AS payout
                FROM races r
                JOIN race_predictions rp1
                    ON r.id=rp1.race_id AND rp1.prediction_type='before' AND rp1.rank_prediction=1
                JOIN race_predictions rp2
                    ON r.id=rp2.race_id AND rp2.prediction_type='before' AND rp2.rank_prediction=2
                JOIN race_predictions rp3
                    ON r.id=rp3.race_id AND rp3.prediction_type='before' AND rp3.rank_prediction=3
                {rp4_join}
                JOIN entries e1 ON r.id=e1.race_id AND e1.pit_number=1
                JOIN trifecta_odds t
                    ON r.id=t.race_id AND t.combination=({combo_expr})
                JOIN payouts pay
                    ON r.id=pay.race_id AND pay.bet_type='trifecta'
                    AND pay.combination=({combo_expr})
                WHERE {where_sql}
                ORDER BY r.race_date, r.venue_code, r.race_number
            """

            try:
                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    race_date, venue_code, race_number, race_id, combination, odds, payout = row
                    hit_races.append({
                        'condition_id': cond_id,
                        'race_date': race_date,
                        'venue_code': venue_code,
                        'venue_name': get_venue_name(venue_code),
                        'race_number': race_number,
                        'race_id': race_id,
                        'combination': combination,
                        'odds': odds,
                        'payout': payout or 0,
                    })
            except Exception:
                pass

    conn.close()
    hit_races.sort(key=lambda x: x['payout'], reverse=True)
    return hit_races


def render_hit_races_detail(start_date: str, end_date: str):
    """的中レース詳細リスト（払戻降順）"""
    st.markdown("### 🏆 的中レース詳細リスト")
    st.caption(
        "全条件の的中レースを払戻金額の高い順に表示。"
        "🥇 ≥30,000円 ／ 🟢 ≥10,000円　※SQLベース近似値"
    )

    with st.spinner("的中データ取得中..."):
        hits = _load_hit_races_detail(start_date, end_date)

    if not hits:
        st.info("期間内に的中レースはありません")
        return

    total_hits = len(hits)
    total_payout = sum(h['payout'] for h in hits)
    max_payout = max(h['payout'] for h in hits)
    avg_payout = total_payout / total_hits if total_hits > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("的中件数", f"{total_hits}件")
    col2.metric("最高払戻", f"{max_payout:,.0f}円")
    col3.metric("平均払戻", f"{avg_payout:,.0f}円")
    col4.metric("総払戻合計", f"{total_payout:,.0f}円")

    df = pd.DataFrame(hits)
    # _payout_num は数値列として保持（色付け判定に使用）
    display_df = pd.DataFrame({
        '日付': df['race_date'],
        '会場': df['venue_name'],
        'R': df['race_number'],
        '条件': df['condition_id'],
        '買い目': df['combination'],
        'オッズ': df['odds'].apply(lambda x: f"{x:.1f}倍" if x else '-'),
        '払戻': df['payout'].apply(lambda x: f"{x:,.0f}円"),
        '_payout_num': df['payout'],  # 色付け用数値列
    })

    def _color_hit_row(row):
        try:
            p = float(row['_payout_num'])
        except (TypeError, ValueError):
            return [''] * len(row)
        if p >= 30000:
            return ['background-color: #ffd700; font-weight: bold'] * len(row)
        elif p >= 10000:
            return ['background-color: #c8e6c9'] * len(row)
        return [''] * len(row)

    styled = display_df.style.apply(_color_hit_row, axis=1).hide(axis='columns', subset=['_payout_num'])

    st.dataframe(styled, use_container_width=True,
                 height=min(600, 60 + total_hits * 36))
