"""
統合レース一覧画面
今日のレース推奨を一覧表示（的中率重視/期待値重視）
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import List, Dict
import logging

from ui.components.common.widgets import render_confidence_badge
from src.betting import BetTargetEvaluator, BetStatus

logger = logging.getLogger(__name__)


def render_unified_race_list():
    """統合レース一覧画面を表示"""

    # ヘッダーと直前情報取得ボタンを横並び
    col_header, col_btn = st.columns([3, 1])
    with col_header:
        st.header("🔮 レース予想一覧")
    with col_btn:
        st.write("")  # スペーサー
        if st.button("🔄 直前情報取得", type="secondary", use_container_width=True):
            st.session_state.show_beforeinfo_dialog = True

    # 直前情報取得ダイアログ
    if st.session_state.get('show_beforeinfo_dialog', False):
        _render_beforeinfo_dialog()

    # タブ作成：総合 / 的中率重視 / 期待値重視
    tab0, tab1, tab2 = st.tabs(["📊 総合", "🎯 的中率重視", "💰 期待値重視"])

    with tab0:
        _render_bet_targets()

    with tab1:
        _render_accuracy_focused()

    with tab2:
        _render_value_focused()


def _render_next_race_alert(placeholder, target_races: List[Dict]):
    """次の出走時間アラートを表示"""
    from datetime import timedelta

    if not target_races:
        return

    now = datetime.now()

    # 時刻でソート（未確定のみ対象）
    upcoming_races = []
    for t in target_races:
        race_time_str = t.get('race_time')
        if not race_time_str:
            continue

        try:
            # race_timeが "HH:MM:SS" or "HH:MM" 形式の場合の処理
            if len(race_time_str) == 5:  # "HH:MM"
                race_time_str = race_time_str + ":00"
            race_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {race_time_str}", "%Y-%m-%d %H:%M:%S")
            minutes_until = (race_time - now).total_seconds() / 60
            # まだ終わっていないレース（終了5分後まで表示）
            if minutes_until > -5:
                upcoming_races.append({
                    **t,
                    'race_time_dt': race_time,
                    'minutes_until': minutes_until
                })
        except Exception as e:
            # 時刻パースエラーでもスキップ
            continue

    if not upcoming_races:
        with placeholder:
            st.success("✅ 本日の購入対象・候補レースはすべて終了しました")
        return

    # 時刻順にソート
    upcoming_races.sort(key=lambda x: x['race_time_dt'])

    # 最も近いレース
    next_race = upcoming_races[0]
    minutes = next_race['minutes_until']
    target = next_race['target']

    # 直前情報取得のタイミング判定（30分前から取得可能）
    needs_beforeinfo = not next_race['has_beforeinfo'] and target.status != BetStatus.TARGET_CONFIRMED

    with placeholder:
        if minutes <= 0:
            # すでに開始
            st.error(f"🏁 **まもなく発走** | {next_race['venue_name']} {next_race['race_number']}R | 買い目: `{target.combination}`")
        elif minutes <= 10:
            # 10分以内
            if needs_beforeinfo:
                st.error(f"⚠️ **残り{int(minutes)}分** | {next_race['venue_name']} {next_race['race_number']}R | 🔄 **直前情報を取得してください！**")
            else:
                st.warning(f"⏰ **残り{int(minutes)}分** | {next_race['venue_name']} {next_race['race_number']}R | 買い目: `{target.combination}` ({target.odds:.1f}倍)")
        elif minutes <= 30:
            # 30分以内
            if needs_beforeinfo:
                st.warning(f"📢 **残り{int(minutes)}分** | {next_race['venue_name']} {next_race['race_number']}R | 直前情報取得可能です")
            else:
                st.info(f"⏰ **残り{int(minutes)}分** | {next_race['venue_name']} {next_race['race_number']}R | 買い目: `{target.combination}`")
        else:
            # 30分以上
            time_str = next_race['race_time_dt'].strftime('%H:%M')
            st.info(f"📅 次の対象レース: {next_race['venue_name']} {next_race['race_number']}R ({time_str}) | 約{int(minutes)}分後")

        # 今後1時間以内のレースも表示
        races_in_hour = [r for r in upcoming_races[1:] if r['minutes_until'] <= 60]
        if races_in_hour:
            race_list = ", ".join([f"{r['venue_name']}{r['race_number']}R({r['race_time_dt'].strftime('%H:%M')})" for r in races_in_hour[:5]])
            st.caption(f"📋 今後1時間以内: {race_list}")


def _render_bet_targets():
    """総合タブ - 購入対象レースを表示（最終運用戦略に基づく）"""
    from datetime import timedelta

    # 日付選択（コンパクトに）
    col_date, col_help = st.columns([2, 1])
    with col_date:
        target_date = st.date_input(
            "対象日",
            value=datetime.now().date(),
            key="bet_target_date"
        )
    with col_help:
        st.write("")
        with st.popover("❓ 購入戦略"):
            st.markdown("""
            **購入条件（13,413レース検証済み）**

            | 信頼度 | 方式 | オッズ | 1コース | 期待値 |
            |:------:|:----:|:------:|:-------:|:------:|
            | C | 従来 | 30-60倍 | A1級 | 127% |
            | C | 従来 | 50倍+ | A級 | 121% |
            | D | 新方式 | 30倍+ | A級 | 209% |
            | D | 新方式 | 20倍+ | A級 | 179% |
            """)

    try:
        import sqlite3
        from config.settings import DATABASE_PATH, VENUES

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        target_date_str = target_date.strftime('%Y-%m-%d')

        # 会場名マッピング
        venue_name_map = {}
        for venue_id, venue_info in VENUES.items():
            venue_name_map[venue_info['code']] = venue_info['name']

        # レース情報と予想データを取得
        cursor.execute("""
            SELECT
                r.id as race_id,
                r.venue_code,
                r.race_number,
                r.race_time,
                r.race_date,
                rp.confidence,
                rp.prediction_type,
                GROUP_CONCAT(rp.pit_number || ':' || rp.rank_prediction, '|') as predictions_data
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE r.race_date = ? AND rp.rank_prediction <= 6
            GROUP BY r.id, rp.prediction_type
            ORDER BY r.venue_code, r.race_number, rp.prediction_type
        """, (target_date_str,))

        race_rows = cursor.fetchall()

        if not race_rows:
            st.warning(f"{target_date_str} のレース予想が見つかりませんでした")
            st.info("「データ準備」タブで「今日の予測を生成」を実行してください")
            conn.close()
            return

        # 評価器を初期化
        evaluator = BetTargetEvaluator()

        # レースごとにデータをグループ化
        race_data_by_id = {}
        for row in race_rows:
            race_id, venue_code, race_number, race_time, race_date, confidence, prediction_type, predictions_data = row

            if race_id not in race_data_by_id:
                race_data_by_id[race_id] = {
                    'race_id': race_id,
                    'venue_code': venue_code,
                    'race_number': race_number,
                    'race_time': race_time,
                    'race_date': race_date,
                    'venue_name': venue_name_map.get(venue_code, f'会場{venue_code}'),
                    'initial': None,
                    'before': None
                }

            # 予想データをパース
            predictions = []
            for pred_str in predictions_data.split('|'):
                parts = pred_str.split(':')
                if len(parts) == 2:
                    pit_number, rank_pred = parts
                    predictions.append({
                        'pit_number': int(pit_number),
                        'rank': int(rank_pred)
                    })
            predictions.sort(key=lambda x: x['rank'])

            pred_data = {
                'predictions': predictions,
                'confidence': confidence,
                'top3': predictions[:3] if len(predictions) >= 3 else predictions
            }

            if prediction_type == 'before':
                race_data_by_id[race_id]['before'] = pred_data
            else:
                race_data_by_id[race_id]['initial'] = pred_data

        # 1コースの級別を取得（複数点買い用にエントリー情報も取得）
        race_ids = list(race_data_by_id.keys())
        placeholders = ','.join('?' * len(race_ids))
        cursor.execute(f"""
            SELECT race_id, pit_number, racer_rank
            FROM entries
            WHERE race_id IN ({placeholders})
        """, race_ids)
        entries_by_race = {}
        c1_ranks = {}
        for row in cursor.fetchall():
            race_id, pit_number, racer_rank = row
            if race_id not in entries_by_race:
                entries_by_race[race_id] = []
            entries_by_race[race_id].append({'pit_number': pit_number, 'racer_rank': racer_rank})
            if pit_number == 1:
                c1_ranks[race_id] = racer_rank

        # オッズデータを取得
        cursor.execute(f"""
            SELECT race_id, combination, odds
            FROM trifecta_odds
            WHERE race_id IN ({placeholders})
        """, race_ids)
        odds_by_race = {}
        for race_id, combination, odds in cursor.fetchall():
            if race_id not in odds_by_race:
                odds_by_race[race_id] = {}
            odds_by_race[race_id][combination] = odds

        conn.close()

        # 購入対象を評価
        bet_targets = []
        for race_id, data in race_data_by_id.items():
            # 直前情報があるか
            has_beforeinfo = data['before'] is not None
            pred = data['before'] if has_beforeinfo else data['initial']
            if not pred:
                continue

            # 信頼度
            confidence = pred['confidence']
            c1_rank = c1_ranks.get(race_id, 'B1')

            # 買い目
            top3 = pred['top3']
            if len(top3) < 3:
                continue

            # 全予測順位（6位まで）を構築
            all_predictions = pred['predictions']
            full_prediction = [p['pit_number'] for p in sorted(all_predictions, key=lambda x: x['rank'])]
            if len(full_prediction) < 6:
                # 不足分は1-6から補填
                for i in range(1, 7):
                    if i not in full_prediction:
                        full_prediction.append(i)

            old_combo = f"{top3[0]['pit_number']}-{top3[1]['pit_number']}-{top3[2]['pit_number']}"
            new_combo = old_combo  # 新方式予測は後で計算（簡略化のため同じ）

            # オッズ
            odds_data = odds_by_race.get(race_id, {})

            # race_dataを構築（evaluate_race用）
            race_data_for_eval = {
                'venue_code': data['venue_code'],
                'entries': entries_by_race.get(race_id, []),
            }

            # predictions辞書を構築
            predictions_for_eval = {
                'confidence': confidence,
                'old_prediction': [top3[0]['pit_number'], top3[1]['pit_number'], top3[2]['pit_number']],
                'new_prediction': [top3[0]['pit_number'], top3[1]['pit_number'], top3[2]['pit_number']],
                'full_prediction': full_prediction,
            }

            # 評価実行（evaluate_raceで複数点買いも生成）
            target = evaluator.evaluate_race(
                race_data=race_data_for_eval,
                predictions=predictions_for_eval,
                odds_data=odds_data if odds_data else None,
                has_beforeinfo=has_beforeinfo
            )

            bet_targets.append({
                'race_id': race_id,
                'venue_name': data['venue_name'],
                'race_number': data['race_number'],
                'race_time': data['race_time'],
                'race_date': data['race_date'],
                'venue_code': data['venue_code'],
                'has_beforeinfo': has_beforeinfo,
                'target': target
            })

        # ステータス別に分類
        targets_advance = [t for t in bet_targets if t['target'].status == BetStatus.TARGET_ADVANCE]
        candidates = [t for t in bet_targets if t['target'].status == BetStatus.CANDIDATE]
        targets_confirmed = [t for t in bet_targets if t['target'].status == BetStatus.TARGET_CONFIRMED]
        excluded = [t for t in bet_targets if t['target'].status == BetStatus.EXCLUDED]

        # 時間情報を付与して分類
        now = datetime.now()
        is_today = target_date == now.date()

        def parse_race_time(race_time_str):
            """レース時刻をパースしてdatetimeを返す"""
            if not race_time_str:
                return None
            try:
                if len(race_time_str) == 5:
                    race_time_str = race_time_str + ":00"
                return datetime.strptime(f"{target_date.strftime('%Y-%m-%d')} {race_time_str}", "%Y-%m-%d %H:%M:%S")
            except:
                return None

        def classify_by_time(race_list):
            """レースを時間別に分類"""
            finished = []
            active = []
            upcoming = []

            for t in race_list:
                race_time = parse_race_time(t.get('race_time'))
                t['race_time_dt'] = race_time

                if not is_today or not race_time:
                    upcoming.append(t)
                else:
                    minutes_until = (race_time - now).total_seconds() / 60
                    t['minutes_until'] = minutes_until
                    if minutes_until < -10:  # 10分以上前に開始
                        finished.append(t)
                    elif minutes_until <= 5:  # 5分前〜開始後10分
                        active.append(t)
                    else:
                        upcoming.append(t)

            return finished, active, upcoming

        # 購入対象を時間別に分類
        all_buy_targets = targets_confirmed + targets_advance
        finished_targets, active_targets, upcoming_targets = classify_by_time(all_buy_targets)

        # 候補も時間別に分類
        finished_candidates, active_candidates, upcoming_candidates = classify_by_time(candidates)

        # 期待値でソート
        def sort_by_roi(items):
            return sorted(items, key=lambda x: x['target'].expected_roi, reverse=True)

        upcoming_targets = sort_by_roi(upcoming_targets)
        upcoming_candidates = sort_by_roi(upcoming_candidates)

        # ============ メインサマリー ============
        st.markdown("---")

        # 投資サマリー（大きく表示）
        active_and_upcoming = active_targets + upcoming_targets
        if active_and_upcoming:
            # 複数点買い対応の賭け金計算
            def get_bet_amount(target):
                if target.multi_bet_result and hasattr(target.multi_bet_result, 'total_bet_amount'):
                    return target.multi_bet_result.total_bet_amount
                return target.bet_amount

            total_bet = sum(get_bet_amount(t['target']) for t in active_and_upcoming)
            expected_return = sum(get_bet_amount(t['target']) * t['target'].expected_roi / 100 for t in active_and_upcoming)
            avg_roi = expected_return / total_bet * 100 if total_bet > 0 else 0

            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #1e88e5 0%, #1565c0 100%); border-radius: 12px; padding: 20px; margin-bottom: 16px; color: white;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
                    <div>
                        <div style="font-size: 0.9em; opacity: 0.9;">本日の投資予定</div>
                        <div style="font-size: 2em; font-weight: bold;">¥{total_bet:,}</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 2.5em; font-weight: bold;">→</div>
                    </div>
                    <div>
                        <div style="font-size: 0.9em; opacity: 0.9;">期待収益</div>
                        <div style="font-size: 2em; font-weight: bold; color: #81c784;">¥{expected_return:,.0f}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 0.9em; opacity: 0.9;">平均期待回収率</div>
                        <div style="font-size: 1.8em; font-weight: bold; color: #ffeb3b;">{avg_roi:.1f}%</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # ステータスカウント
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            active_count = len(active_targets)
            upcoming_count = len(upcoming_targets)
            st.metric("🎯 購入対象", f"{active_count + upcoming_count}件",
                     delta=f"進行中{active_count}" if active_count > 0 else None,
                     delta_color="normal")
        with col2:
            cand_active = len(active_candidates)
            cand_upcoming = len(upcoming_candidates)
            st.metric("🟡 候補", f"{cand_active + cand_upcoming}件",
                     help="直前情報次第で対象になる可能性")
        with col3:
            st.metric("✅ 終了", f"{len(finished_targets)}件",
                     help="本日終了した購入対象レース")
        with col4:
            st.metric("⚪ 対象外", f"{len(excluded)}件")

        st.markdown("---")

        # ============ 進行中・まもなく開始 ============
        if active_targets or active_candidates:
            st.markdown("### 🔴 まもなく発走・進行中")

            for t in active_targets:
                _render_race_card_enhanced(t, "active", is_active=True)

            if active_candidates:
                st.caption("🟡 候補レース（直前情報を取得すると対象になる可能性）")
                for t in active_candidates:
                    _render_race_card_enhanced(t, "active_cand", is_candidate=True, is_active=True)

        # ============ 今後のレース ============
        if upcoming_targets or upcoming_candidates:
            # 期待値別に分類
            high_roi = [t for t in upcoming_targets if t['target'].expected_roi >= 150]
            normal_roi = [t for t in upcoming_targets if t['target'].expected_roi < 150]

            if high_roi:
                st.markdown("### 💎 高期待値レース（150%以上）")
                for t in high_roi:
                    _render_race_card_enhanced(t, "high_roi")

            if normal_roi:
                st.markdown("### 🎯 購入対象レース")
                for t in normal_roi:
                    _render_race_card_enhanced(t, "normal")

            if upcoming_candidates:
                st.markdown("### 🟡 候補レース")
                st.caption("直前情報を取得するとオッズ次第で購入対象になる可能性があります")
                for t in upcoming_candidates[:10]:  # 最大10件表示
                    _render_race_card_enhanced(t, "candidate", is_candidate=True)

                if len(upcoming_candidates) > 10:
                    with st.expander(f"その他の候補 ({len(upcoming_candidates) - 10}件)"):
                        for t in upcoming_candidates[10:]:
                            _render_race_card_enhanced(t, "candidate_more", is_candidate=True)

        if not active_targets and not upcoming_targets and not active_candidates and not upcoming_candidates:
            st.info("📅 本日の購入対象・候補レースはありません")

        # ============ 終了済みレース ============
        if finished_targets:
            with st.expander(f"✅ 終了済みレース ({len(finished_targets)}件)", expanded=False):
                st.caption("💡 結果・払戻は「直前情報取得」ボタンで自動取得されます")

                # ヘッダー行
                col1, col2, col3, col4, col5, col6 = st.columns([2, 1.5, 1.5, 1.5, 2, 1])
                with col1:
                    st.caption("レース")
                with col2:
                    st.caption("買い目")
                with col3:
                    st.caption("オッズ")
                with col4:
                    st.caption("賭け金")
                with col5:
                    st.caption("結果 / 払戻")
                with col6:
                    st.caption("")
                st.markdown("---")

                for t in finished_targets:
                    _render_race_card_compact(t, "finished")

        # ============ 対象外レース ============
        if excluded:
            with st.expander(f"⚪ 対象外レース ({len(excluded)}件)", expanded=False):
                df_excluded = []
                for t in excluded:
                    target = t['target']
                    df_excluded.append({
                        '会場': t['venue_name'],
                        'R': t['race_number'],
                        '時刻': t['race_time'] or '-',
                        '信頼度': target.confidence,
                        '1コース': target.c1_rank,
                        '理由': target.reason
                    })
                st.dataframe(pd.DataFrame(df_excluded), use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        import traceback
        st.code(traceback.format_exc())


def _render_race_card_enhanced(t: Dict, key_prefix: str, is_candidate: bool = False, is_active: bool = False):
    """改善版レースカード表示"""
    target = t['target']
    race_time = t.get('race_time') or '未定'
    minutes_until = t.get('minutes_until')

    # 時間表示
    if minutes_until is not None:
        if minutes_until <= 0:
            time_badge = f"<span style='background:#e53935;color:white;padding:2px 8px;border-radius:12px;font-size:0.8em;'>発走中</span>"
        elif minutes_until <= 10:
            time_badge = f"<span style='background:#ff5722;color:white;padding:2px 8px;border-radius:12px;font-size:0.8em;'>あと{int(minutes_until)}分</span>"
        elif minutes_until <= 30:
            time_badge = f"<span style='background:#ff9800;color:white;padding:2px 8px;border-radius:12px;font-size:0.8em;'>あと{int(minutes_until)}分</span>"
        else:
            time_badge = f"<span style='color:#666;font-size:0.85em;'>⏰ {race_time}</span>"
    else:
        time_badge = f"<span style='color:#666;font-size:0.85em;'>⏰ {race_time}</span>"

    # スタイル設定
    if is_active:
        border_color = "#e53935"
        bg_gradient = "linear-gradient(135deg, rgba(229, 57, 53, 0.15) 0%, rgba(255,255,255,0.98) 100%)"
        pulse_anim = "animation: pulse 2s infinite;"
    elif is_candidate:
        border_color = "#ffa000"
        bg_gradient = "linear-gradient(135deg, rgba(255, 160, 0, 0.1) 0%, rgba(255,255,255,0.98) 100%)"
        pulse_anim = ""
    elif target.expected_roi >= 150:
        border_color = "#7b1fa2"
        bg_gradient = "linear-gradient(135deg, rgba(123, 31, 162, 0.1) 0%, rgba(255,255,255,0.98) 100%)"
        pulse_anim = ""
    else:
        border_color = "#43a047"
        bg_gradient = "linear-gradient(135deg, rgba(67, 160, 71, 0.08) 0%, rgba(255,255,255,0.98) 100%)"
        pulse_anim = ""

    # 期待値バッジ
    if target.expected_roi >= 200:
        roi_color = "#7b1fa2"
        roi_icon = "💎"
    elif target.expected_roi >= 150:
        roi_color = "#1976d2"
        roi_icon = "⭐"
    elif target.expected_roi >= 120:
        roi_color = "#388e3c"
        roi_icon = "✓"
    else:
        roi_color = "#666"
        roi_icon = ""

    # オッズ表示
    odds_display = f"{target.odds:.1f}倍" if target.odds else target.odds_range

    # 複数点買い情報を取得
    multi_bet = target.multi_bet_result
    has_multi_bet = multi_bet is not None and hasattr(multi_bet, 'bets') and len(multi_bet.bets) > 0

    # 買い目・オッズ・賭け金の表示HTML生成
    if has_multi_bet:
        # パターンH等の複数点買い表示
        bet_lines = []
        for bet in multi_bet.bets:
            bet_lines.append(f"<div style='display:flex; gap:8px; align-items:center; margin-bottom:4px;'>"
                           f"<span style='font-family:monospace; font-weight:bold;'>{bet.combination}</span>"
                           f"<span style='color:#666; font-size:0.85em;'>{bet.odds:.1f}倍</span>"
                           f"<span style='font-weight:bold;'>¥{bet.bet_amount}</span>"
                           f"</div>")
        bet_html = "".join(bet_lines)
        total_bet = multi_bet.total_bet_amount
        multi_bet_badge = f"<span style='background:#1976d2;color:white;padding:2px 6px;border-radius:4px;font-size:0.7em;margin-left:8px;'>パターンH</span>"
    else:
        # 1点買い表示
        bet_html = f"<span style='font-size: 1.4em; font-weight: bold; font-family: monospace;'>{target.combination}</span>"
        total_bet = target.bet_amount
        multi_bet_badge = ""

    # カードHTML
    st.markdown(f"""
    <style>
        @keyframes pulse {{
            0% {{ box-shadow: 0 0 0 0 rgba(229, 57, 53, 0.4); }}
            70% {{ box-shadow: 0 0 0 10px rgba(229, 57, 53, 0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(229, 57, 53, 0); }}
        }}
    </style>
    <div style="
        background: {bg_gradient};
        border-left: 5px solid {border_color};
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        {pulse_anim}
    ">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;">
            <div style="flex: 1;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <span style="font-size: 1.3em; font-weight: bold;">{t['venue_name']} {t['race_number']}R</span>
                    {time_badge}
                    <span style="
                        background: {'#e53935' if t['has_beforeinfo'] else '#bdbdbd'};
                        color: white;
                        padding: 2px 6px;
                        border-radius: 4px;
                        font-size: 0.7em;
                    ">{'直前済' if t['has_beforeinfo'] else '事前'}</span>
                    {multi_bet_badge}
                </div>
                <div style="display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start;">
                    <div>
                        <span style="color: #666; font-size: 0.8em;">買い目{' (3点)' if has_multi_bet else ''}</span><br>
                        {bet_html}
                    </div>
                    {'<div><span style="color: #666; font-size: 0.8em;">オッズ</span><br><span style="font-size: 1.1em; font-weight: bold;">' + odds_display + '</span></div>' if not has_multi_bet else ''}
                    <div>
                        <span style="color: #666; font-size: 0.8em;">{'投資計' if has_multi_bet else '賭け金'}</span><br>
                        <span style="font-size: 1.1em; font-weight: bold;">¥{total_bet}</span>
                    </div>
                </div>
            </div>
            <div style="text-align: right; min-width: 100px;">
                <div style="font-size: 0.8em; color: #666;">期待回収率</div>
                <div style="font-size: 1.8em; font-weight: bold; color: {roi_color};">
                    {roi_icon} {target.expected_roi:.0f}%
                </div>
                <div style="font-size: 0.75em; color: #888; margin-top: 4px;">
                    {target.confidence}級 / 1コース{target.c1_rank}
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 詳細ボタン
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("詳細→", key=f"detail_{key_prefix}_{t['race_id']}", use_container_width=True):
            st.session_state.selected_race = {
                'race_date': t['race_date'],
                'venue_code': t['venue_code'],
                'race_number': t['race_number'],
            }
            st.session_state.show_detail = True
            st.rerun()


def _render_race_card_compact(t: Dict, key_prefix: str):
    """コンパクト版レースカード（終了済み用）- 結果と払戻金表示付き"""
    import sqlite3
    from config.settings import DATABASE_PATH

    target = t['target']
    odds_display = f"{target.odds:.1f}倍" if target.odds else "-"
    race_id = t['race_id']

    # レース結果を取得
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 着順を取得（rankはTEXT型なので文字列比較）
    cursor.execute("""
        SELECT pit_number, rank
        FROM results
        WHERE race_id = ? AND is_invalid = 0 AND rank IN ('1', '2', '3')
        ORDER BY CAST(rank AS INTEGER)
    """, (race_id,))
    result_rows = cursor.fetchall()

    # 払戻金を取得
    cursor.execute("""
        SELECT amount FROM payouts
        WHERE race_id = ? AND bet_type = 'trifecta'
    """, (race_id,))
    payout_row = cursor.fetchone()
    conn.close()

    # 結果を整形
    if len(result_rows) >= 3:
        actual_combo = f"{result_rows[0][0]}-{result_rows[1][0]}-{result_rows[2][0]}"
    else:
        actual_combo = "-"

    payout = int(payout_row[0]) if payout_row else 0

    # 複数点買い対応
    multi_bet = target.multi_bet_result
    has_multi_bet = multi_bet is not None and hasattr(multi_bet, 'bets') and len(multi_bet.bets) > 0

    # 的中判定（複数点買いの場合はどれかに的中）
    if has_multi_bet:
        hit_combos = [bet.combination for bet in multi_bet.bets if bet.combination == actual_combo]
        is_hit = len(hit_combos) > 0
        bet_display = " / ".join([bet.combination for bet in multi_bet.bets])
        bet_amount = multi_bet.total_bet_amount
    else:
        is_hit = target.combination == actual_combo
        bet_display = target.combination
        bet_amount = target.bet_amount

    # 的中判定のアイコン
    if actual_combo == "-":
        hit_icon = ""
        hit_color = "#666"
    elif is_hit:
        hit_icon = "🎉"
        hit_color = "green"
    else:
        hit_icon = "❌"
        hit_color = "red"

    col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 1.5, 1.5, 2, 1])
    with col1:
        st.write(f"**{t['venue_name']} {t['race_number']}R**")
    with col2:
        if has_multi_bet:
            st.caption(bet_display)
        else:
            st.write(f"`{bet_display}`")
    with col3:
        st.write(odds_display if not has_multi_bet else "3点")
    with col4:
        st.write(f"¥{bet_amount}")
    with col5:
        # 結果表示
        if actual_combo != "-":
            st.markdown(f"<span style='color:{hit_color}'>{hit_icon} {actual_combo}</span> ¥{payout:,}", unsafe_allow_html=True)
        else:
            st.write("-")
    with col6:
        if st.button("→", key=f"detail_{key_prefix}_{t['race_id']}", use_container_width=True):
            st.session_state.selected_race = {
                'race_date': t['race_date'],
                'venue_code': t['venue_code'],
                'race_number': t['race_number'],
            }
            st.session_state.show_detail = True
            st.rerun()


def _render_bet_target_cards(targets: List[Dict], key_prefix: str):
    """購入対象レースカードを表示（互換性維持用）"""
    for idx, t in enumerate(targets, 1):
        _render_race_card_enhanced(t, f"{key_prefix}_{idx}")


def _render_accuracy_focused():
    """的中率重視タブ - 保存済み予想から上位20レースを表示"""
    st.subheader("📊 信頼度の高いおすすめレース TOP20")
    st.caption("保存済みの予想データから、信頼度が高い上位20レースを表示します")

    # 日付選択
    target_date = st.date_input(
        "対象日",
        value=datetime.now().date(),
        key="accuracy_date"
    )

    # 保存済み予想データを取得
    try:
        import sqlite3
        from config.settings import DATABASE_PATH, VENUES

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        target_date_str = target_date.strftime('%Y-%m-%d')

        # 会場名マッピング
        venue_name_map = {}
        for venue_id, venue_info in VENUES.items():
            venue_name_map[venue_info['code']] = venue_info['name']

        # レース情報と予想スコアを取得（初期・直前両方）
        cursor.execute("""
            SELECT
                r.id as race_id,
                r.venue_code,
                r.race_number,
                r.race_time,
                r.race_date,
                AVG(rp.total_score) as avg_score,
                MAX(rp.total_score) as max_score,
                MIN(CASE rp.confidence
                    WHEN 'A' THEN 1
                    WHEN 'B' THEN 2
                    WHEN 'C' THEN 3
                    WHEN 'D' THEN 4
                    ELSE 5
                END) as best_confidence_rank,
                GROUP_CONCAT(rp.pit_number || ':' || rp.rank_prediction || ':' || rp.total_score || ':' || rp.confidence, '|') as predictions_data,
                COALESCE(rp.prediction_type, 'initial') as prediction_type
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE r.race_date = ?
            GROUP BY r.id, rp.prediction_type
            ORDER BY r.id, rp.prediction_type
        """, (target_date_str,))

        race_rows = cursor.fetchall()

        if not race_rows:
            st.warning(f"{target_date_str} のレース予想が見つかりませんでした")
            st.info("「データ準備」タブで「今日の予測を生成」を実行してください")
            conn.close()
            return

        # race_idごとに初期・直前をグループ化
        race_data_by_id = {}
        for row in race_rows:
            race_id, venue_code, race_number, race_time, race_date, avg_score, max_score, best_confidence_rank, predictions_data, prediction_type = row

            if race_id not in race_data_by_id:
                race_data_by_id[race_id] = {
                    'race_id': race_id,
                    'venue_code': venue_code,
                    'race_number': race_number,
                    'race_time': race_time,
                    'race_date': race_date,
                    'venue_name': venue_name_map.get(venue_code, f'会場{venue_code}'),
                    'initial': None,
                    'before': None
                }

            # 予想データをパース
            predictions = []
            for pred_str in predictions_data.split('|'):
                parts = pred_str.split(':')
                if len(parts) == 4:
                    pit_number, rank_pred, score, confidence = parts
                    predictions.append({
                        'pit_number': int(pit_number),
                        'rank': int(rank_pred),
                        'score': float(score),
                        'confidence': confidence
                    })
            predictions.sort(key=lambda x: x['rank'])

            # 信頼度計算
            confidence_map = {'A': 100, 'B': 80, 'C': 60, 'D': 40, 'E': 20}
            top3 = predictions[:3]
            top3_confidences = [confidence_map.get(p['confidence'], 50) for p in top3 if 'confidence' in p]
            if top3_confidences:
                weights = [0.5, 0.3, 0.2]
                confidence = sum(c * w for c, w in zip(top3_confidences, weights[:len(top3_confidences)]))
            else:
                confidence = min(100, max(20, avg_score * 8))

            # 買い目生成
            if len(top3) >= 3:
                first, second, third = top3[0]['pit_number'], top3[1]['pit_number'], top3[2]['pit_number']
                trifecta_bets = [f"{first}-{second}-{third}", f"{first}-{third}-{second}",
                                f"{second}-{first}-{third}", f"{second}-{third}-{first}", f"{third}-{first}-{second}"]
                trio_bet = f"{first}={second}={third}"
                main_bet = f"{first}-{second}-{third}"
            else:
                trifecta_bets, trio_bet = [], ""
                main_bet = '-'.join([str(p['pit_number']) for p in top3])

            pred_data = {
                'predictions': predictions,
                'top3': top3,
                'confidence': confidence,
                'avg_score': avg_score,
                'main_bet': main_bet,
                'trifecta_bets': trifecta_bets,
                'trio_bet': trio_bet
            }

            if prediction_type == 'before':
                race_data_by_id[race_id]['before'] = pred_data
            else:
                race_data_by_id[race_id]['initial'] = pred_data

        conn.close()

        # 統合レースリストを作成（直前があれば直前の信頼度でソート）
        recommended_races = []
        for race_id, data in race_data_by_id.items():
            # 直前予想があれば直前の信頼度を使用
            if data['before']:
                sort_confidence = data['before']['confidence']
                primary_pred = data['before']
            elif data['initial']:
                sort_confidence = data['initial']['confidence']
                primary_pred = data['initial']
            else:
                continue

            recommended_races.append({
                'race_id': race_id,
                '会場': data['venue_name'],
                'レース': f"{data['race_number']}R",
                '時刻': data['race_time'] or '未定',
                'race_date': data['race_date'],
                'venue_code': data['venue_code'],
                'race_number': data['race_number'],
                'initial': data['initial'],
                'before': data['before'],
                'sort_confidence': sort_confidence,  # ソート用
                'badge': render_confidence_badge(sort_confidence)
            })

        # 直前があれば直前、なければ初期の信頼度でソート
        recommended_races.sort(key=lambda x: x['sort_confidence'], reverse=True)

        # 実際のレース数をカウント
        unique_races = len(recommended_races)
        st.success(f"📊 本日の予想データ: {unique_races}レース (上位20件をカード表示、全件をテーブル表示)")

        # レースカード表示（上位20件のみ）
        st.subheader("🏆 おすすめレース TOP20")
        _render_race_cards_combined(recommended_races[:20])

        # 全レース一覧テーブル
        st.markdown("---")
        st.subheader(f"📋 全レース一覧 ({len(recommended_races)}件)")

        df_data = []
        for i, r in enumerate(recommended_races, 1):
            initial = r.get('initial')
            before = r.get('before')

            initial_bet = initial['main_bet'] if initial else '-'
            before_bet = before['main_bet'] if before else '-'
            confidence = before['confidence'] if before else (initial['confidence'] if initial else 0)

            df_data.append({
                '順位': i,
                '会場': r['会場'],
                'レース': r['レース'],
                '時刻': r['時刻'],
                '初期予想': initial_bet,
                '直前予想': before_bet if before else '-',
                '信頼度': f"{confidence:.1f}%",
            })

        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        import traceback
        st.code(traceback.format_exc())


def _render_race_cards_combined(race_list: List[Dict], key_prefix: str = "comb"):
    """初期と直前を1つにまとめたレースカードを表示

    Args:
        race_list: レースデータのリスト（initial/beforeを含む）
        key_prefix: ボタンキーのプレフィックス
    """

    for idx, race in enumerate(race_list, 1):
        initial = race.get('initial')
        before = race.get('before')

        # 信頼度（直前があれば直前を使用）
        confidence = race.get('sort_confidence', 0)

        # 信頼度に応じたスタイル
        if confidence >= 80:
            conf_color = "#e53935"  # 赤
            conf_bg = "rgba(229, 57, 53, 0.1)"
        elif confidence >= 70:
            conf_color = "#fb8c00"  # オレンジ
            conf_bg = "rgba(251, 140, 0, 0.1)"
        elif confidence >= 60:
            conf_color = "#43a047"  # 緑
            conf_bg = "rgba(67, 160, 71, 0.1)"
        else:
            conf_color = "#757575"  # グレー
            conf_bg = "rgba(117, 117, 117, 0.1)"

        has_before = before is not None

        # カード全体をコンテナで囲む
        with st.container():
            # カードスタイル（CSS）
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, {conf_bg} 0%, rgba(255,255,255,0.95) 100%);
                border-left: 4px solid {conf_color};
                border-radius: 8px;
                padding: 12px 16px;
                margin-bottom: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            ">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="
                            font-size: 1.5em;
                            font-weight: bold;
                            color: {conf_color};
                            min-width: 32px;
                        ">{idx}</span>
                        <div>
                            <span style="font-size: 1.1em; font-weight: bold;">{race['会場']} {race['レース']}</span>
                            <span style="
                                background: {'#e53935' if has_before else '#9e9e9e'};
                                color: white;
                                padding: 2px 8px;
                                border-radius: 12px;
                                font-size: 0.75em;
                                margin-left: 8px;
                            ">{'直前' if has_before else '初期'}</span>
                            <div style="color: #666; font-size: 0.85em;">⏰ {race['時刻']}</div>
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 1.3em; font-weight: bold; color: {conf_color};">{confidence:.0f}%</div>
                        <div style="font-size: 0.8em; color: #666;">信頼度</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # 買い目表示（初期と直前を横並び）
            pred_col1, pred_col2, btn_col = st.columns([4, 4, 1.5])

            with pred_col1:
                if initial:
                    bets = initial.get('trifecta_bets', [])
                    st.markdown("**⚪ 初期予想** (3連単5点)")
                    if bets:
                        # 5点を見やすく表示
                        bet_text = " / ".join(bets[:5])
                        st.code(bet_text, language=None)
                else:
                    st.caption("初期予想なし")

            with pred_col2:
                if before:
                    bets = before.get('trifecta_bets', [])
                    st.markdown("**🔴 直前予想** (3連単5点)")
                    if bets:
                        bet_text = " / ".join(bets[:5])
                        st.code(bet_text, language=None)
                else:
                    st.caption("直前予想なし")

            with btn_col:
                st.write("")  # スペーサー
                if st.button("詳細→", key=f"detail_{key_prefix}_{idx}", use_container_width=True):
                    st.session_state.selected_race = {
                        'race_date': race['race_date'],
                        'venue_code': race['venue_code'],
                        'race_number': race['race_number'],
                    }
                    st.session_state.show_detail = True
                    st.rerun()

            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)


def _render_value_focused():
    """期待値重視タブ - 保存済み予想(value mode)から上位20レースを表示"""
    st.subheader("💰 期待値重視のおすすめレース TOP20")
    st.caption("保存済みの予想データ（期待値重視モード）から、スコア上位20レースを表示します")

    # 日付選択
    target_date = st.date_input(
        "対象日",
        value=datetime.now().date(),
        key="value_date"
    )

    # 期待値の説明
    with st.expander("📊 期待値重視モードとは？"):
        st.markdown("""
        **期待値重視モードの特徴:**
        - コース有利を過大評価せず、穴馬を狙う
        - モーター・選手の実力を重視

        **重み設定（期待値重視モード）:**
        - コース: 25点（的中率重視は50点）→ コース過大評価を抑制
        - 選手: 35点（的中率重視は30点）
        - モーター: 20点（的中率重視は10点）
        - 決まり手: 15点（的中率重視は5点）
        """)

    # 保存済み予想データを取得（的中率重視と同じロジック）
    try:
        import sqlite3
        from config.settings import DATABASE_PATH, VENUES

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        target_date_str = target_date.strftime('%Y-%m-%d')

        # 会場名マッピング
        venue_name_map = {}
        for venue_id, venue_info in VENUES.items():
            venue_name_map[venue_info['code']] = venue_info['name']

        # レース情報と予想スコアを取得
        # 期待値重視: モーター・選手スコアの合計が高い順（コースに依存しない実力重視）
        # 初期予想と直前予想を別行で取得
        cursor.execute("""
            SELECT
                r.id as race_id,
                r.venue_code,
                r.race_number,
                r.race_time,
                r.race_date,
                AVG(rp.total_score) as avg_score,
                MAX(rp.total_score) as max_score,
                MAX(COALESCE(rp.motor_score, 0) + COALESCE(rp.racer_score, 0)) as value_score,
                MIN(CASE rp.confidence
                    WHEN 'A' THEN 1
                    WHEN 'B' THEN 2
                    WHEN 'C' THEN 3
                    WHEN 'D' THEN 4
                    ELSE 5
                END) as best_confidence_rank,
                GROUP_CONCAT(rp.pit_number || ':' || rp.rank_prediction || ':' || rp.total_score || ':' || rp.confidence, '|') as predictions_data,
                COALESCE(rp.prediction_type, 'initial') as prediction_type
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id
            WHERE r.race_date = ?
            GROUP BY r.id, rp.prediction_type
            ORDER BY value_score DESC, max_score DESC
        """, (target_date_str,))

        race_rows = cursor.fetchall()

        if not race_rows:
            st.warning(f"{target_date_str} の予想データが見つかりませんでした")
            st.info("「データ準備」タブで「今日の予測を生成」を実行してください")
            conn.close()
            return

        st.success(f"📊 本日の予想データ: {len(race_rows)}件 (上位20件をカード表示、全件をテーブル表示)")

        # レースカードデータを作成（的中率重視と同じ形式）
        recommended_races = []

        for row in race_rows:
            race_id, venue_code, race_number, race_time, race_date, avg_score, max_score, value_score, best_confidence_rank, predictions_data, prediction_type = row

            # 予想タイプのラベル
            type_label = '直前' if prediction_type == 'before' else '初期'

            # 予想データをパース
            predictions = []
            for pred_str in predictions_data.split('|'):
                parts = pred_str.split(':')
                if len(parts) == 4:
                    pit_number, rank_pred, score, confidence = parts
                    predictions.append({
                        'pit_number': int(pit_number),
                        'rank': int(rank_pred),
                        'score': float(score),
                        'confidence': confidence
                    })

            # 予想を順位でソート
            predictions.sort(key=lambda x: x['rank'])

            # 上位3艇を抽出
            top3 = predictions[:3]

            # 2段階戦略の買い目を生成
            if len(top3) >= 3:
                first = top3[0]['pit_number']
                second = top3[1]['pit_number']
                third = top3[2]['pit_number']

                # 3連単（5点）: 1着固定、2-3着流し
                trifecta_bets = [
                    f"{first}-{second}-{third}",
                    f"{first}-{third}-{second}",
                    f"{second}-{first}-{third}",
                    f"{second}-{third}-{first}",
                    f"{third}-{first}-{second}",
                ]

                # 3連複（1点）: BOX
                trio_bet = f"{first}={second}={third}"

                # メイン買い目（本命）
                main_bet = f"{first}-{second}-{third}"

                # 表示用テキスト
                bet_display = f"3連単{len(trifecta_bets)}点 + 3連複1点"
            else:
                trifecta_bets = []
                trio_bet = ""
                main_bet = '-'.join([str(p['pit_number']) for p in top3])
                bet_display = main_bet

            # 信頼度の計算: 上位3艇の信頼度レベルから算出
            confidence_map = {'A': 100, 'B': 80, 'C': 60, 'D': 40, 'E': 20}
            top3_confidences = [confidence_map.get(p['confidence'], 50) for p in top3 if 'confidence' in p]

            if top3_confidences:
                weights = [0.5, 0.3, 0.2]
                confidence = sum(c * w for c, w in zip(top3_confidences, weights[:len(top3_confidences)]))
            else:
                confidence = min(100, max(20, avg_score * 8))

            recommended_races.append({
                '会場': venue_name_map.get(venue_code, f'会場{venue_code}'),
                'レース': f"{race_number}R",
                '時刻': race_time or '未定',
                '本命': f"{top3[0]['pit_number']}号艇" if top3 else '-',
                '買い目': main_bet,
                '買い目表示': bet_display,
                '3連単': trifecta_bets,
                '3連複': trio_bet,
                '買い目詳細': [f"{p['pit_number']}号艇" for p in top3],
                '信頼度': confidence,
                '平均スコア': avg_score,
                'badge': render_confidence_badge(confidence),
                'race_id': race_id,
                'race_date': race_date,
                'venue_code': venue_code,
                'race_number': race_number,
                'predictions': predictions,
                'prediction_type': prediction_type,
                'type_label': type_label
            })

        conn.close()

        # 信頼度の降順でソート
        recommended_races.sort(key=lambda x: x['信頼度'], reverse=True)

        # レースカード表示（上位20件のみ、期待値重視タブ用のkey_prefixを指定）
        st.subheader("🏆 おすすめレース TOP20")
        _render_race_cards_v2(recommended_races[:20], key_prefix="val")

        # 全レース一覧テーブル
        st.markdown("---")
        st.subheader(f"📋 全レース一覧 ({len(recommended_races)}件)")

        df_data = []
        for i, r in enumerate(recommended_races, 1):
            df_data.append({
                '順位': i,
                '種別': r.get('type_label', '初期'),
                '会場': r['会場'],
                'レース': r['レース'],
                '時刻': r['時刻'],
                '買い目': r.get('買い目表示', r['買い目']),
                '3連単': ', '.join(r.get('3連単', [])[:3]) if r.get('3連単') else '-',
                '3連複': r.get('3連複', '-'),
                '信頼度': f"{r['信頼度']:.1f}%",
                'スコア': f"{r['平均スコア']:.2f}"
            })

        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        import traceback
        st.code(traceback.format_exc())


def _render_race_cards_v2(race_list: List[Dict], key_prefix: str = "acc"):
    """レースカードを表示（改善版）

    Args:
        race_list: レースデータのリスト
        key_prefix: ボタンキーのプレフィックス（タブ間で重複を避けるため）
    """

    for idx, race in enumerate(race_list, 1):
        confidence = race['信頼度']

        # スコアに応じた背景色
        if confidence >= 80:
            border_color = "#ff6b6b"  # 赤（最高）
            bg_color = "#ffe0e0"
        elif confidence >= 70:
            border_color = "#ffa500"  # オレンジ（高）
            bg_color = "#fff4e0"
        elif confidence >= 60:
            border_color = "#4ecdc4"  # 青緑（中）
            bg_color = "#e0f4f4"
        else:
            border_color = "#95a5a6"  # グレー（低）
            bg_color = "#f0f0f0"

        # カードのスタイル
        with st.container():
            col1, col2, col3, col4, col5 = st.columns([0.5, 2, 2.5, 2, 1])

            with col1:
                st.markdown(f"### {idx}")

            with col2:
                # 種別バッジ（直前予想の場合は🔴を表示）
                type_label = race.get('type_label', '初期')
                type_badge = "🔴直前" if type_label == '直前' else "⚪初期"
                st.markdown(f"**{race['会場']} {race['レース']}** {type_badge}")
                st.caption(f"⏰ {race['時刻']}")

            with col3:
                # 複数買い目を表示
                st.markdown(f"🎯 **買い目: {race['買い目表示']}**")
                # 3連単と3連複を表示
                if race.get('3連単'):
                    trifecta_str = ', '.join(race['3連単'][:3])
                    if len(race['3連単']) > 3:
                        trifecta_str += f" 他{len(race['3連単'])-3}点"
                    st.caption(f"3連単: {trifecta_str}")
                if race.get('3連複'):
                    st.caption(f"3連複: {race['3連複']}")

            with col4:
                st.markdown(f"**{race['badge']}**")
                st.caption(f"信頼度: {confidence:.1f}% | スコア: {race['平均スコア']:.2f}")

            with col5:
                # 詳細ボタン
                if st.button("詳細 →", key=f"detail_{key_prefix}_{idx}", use_container_width=True):
                    # セッションステートに選択レース情報を保存
                    st.session_state.selected_race = {
                        'race_date': race['race_date'],
                        'venue_code': race['venue_code'],
                        'race_number': race['race_number'],
                        'predictions': race.get('predictions')
                    }
                    st.session_state.show_detail = True
                    st.rerun()

            st.markdown("---")


def _render_race_cards(race_list: List[Dict], mode: str = "accuracy"):
    """レースカードを表示（旧版）"""

    for idx, race in enumerate(race_list, 1):
        confidence = race['信頼度']

        # スコアに応じた背景色
        if confidence >= 80:
            border_color = "#ff6b6b"  # 赤（最高）
            bg_color = "#ffe0e0"
        elif confidence >= 70:
            border_color = "#ffa500"  # オレンジ（高）
            bg_color = "#fff4e0"
        elif confidence >= 60:
            border_color = "#4ecdc4"  # 青緑（中）
            bg_color = "#e0f4f4"
        else:
            border_color = "#95a5a6"  # グレー（低）
            bg_color = "#f0f0f0"

        # カードのスタイル
        card_style = f"""
        <style>
        .race-card-{idx} {{
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
            st.markdown(f'<div class="race-card-{idx}">', unsafe_allow_html=True)

            # ヘッダー行
            col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 1])

            with col1:
                st.markdown(f"### #{idx}")

            with col2:
                # 種別バッジ（直前予想の場合は🔴を表示）
                type_label = race.get('type_label', '初期')
                type_badge = "🔴直前" if type_label == '直前' else "⚪初期"
                st.markdown(f"**{race['会場']} {race['レース']}** {type_badge}")
                st.caption(f"⏰ {race['時刻']}")

            with col3:
                # 複数買い目を表示
                if '買い目リスト' in race:
                    bet_list = race['買い目リスト']
                    main_bet = bet_list[0] if bet_list else ''
                    st.markdown(f"🎯 **本命: {main_bet}**")
                    if len(bet_list) > 1:
                        st.caption(f"他{len(bet_list)-1}点: {', '.join(bet_list[1:3])}")
                else:
                    st.markdown(f"🎯 **{race.get('1着', '')}-{race.get('2着', '')}-{race.get('3着', '')}**")

            with col4:
                st.markdown(f"**{race['badge']}**")
                st.caption(f"信頼度: {confidence:.1f}%")

            with col5:
                # 詳細ボタン
                if st.button("詳細", key=f"detail_{idx}"):
                    # セッションステートに選択レース情報を保存
                    st.session_state.selected_race = {
                        'race_date': race['race_date'],
                        'venue_code': race['venue_code'],
                        'race_number': race['race_number'],
                        'predictions': race.get('predictions')
                    }
                    st.session_state.show_detail = True
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("---")


def check_and_show_detail():
    """詳細画面を表示するかチェック"""
    if st.session_state.get('show_detail', False):
        return True
    return False


def get_selected_race():
    """選択されたレース情報を取得"""
    return st.session_state.get('selected_race', None)


def clear_selected_race():
    """選択レース情報をクリア"""
    if 'show_detail' in st.session_state:
        st.session_state.show_detail = False
    if 'selected_race' in st.session_state:
        del st.session_state.selected_race


def _render_beforeinfo_dialog():
    """直前情報取得ダイアログを表示"""
    import sqlite3
    from datetime import datetime
    from config.settings import DATABASE_PATH, VENUES

    st.markdown("---")
    st.subheader("🔄 直前情報取得")

    # サイドバーで選択された会場を取得
    sidebar_selected_venues = list(st.session_state.get('sidebar_selected_venues', set()))

    # 会場名マッピング
    venue_name_map = {}
    venue_code_map = {}  # 名前からコードへ
    for venue_id, venue_info in VENUES.items():
        venue_name_map[venue_info['code']] = venue_info['name']
        venue_code_map[venue_info['name']] = venue_info['code']

    # 本日のレースを取得
    today_str = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # サイドバーで会場が選択されている場合はフィルタリング
    if sidebar_selected_venues:
        placeholders = ','.join('?' * len(sidebar_selected_venues))
        query = f"""
            SELECT r.id, r.venue_code, r.race_number, r.race_time,
                   CASE WHEN ed.exhibition_time IS NOT NULL THEN 1 ELSE 0 END as has_beforeinfo
            FROM races r
            LEFT JOIN exhibition_data ed ON r.id = ed.race_id AND ed.pit_number = 1
            WHERE r.race_date = ? AND r.venue_code IN ({placeholders})
            ORDER BY r.venue_code, r.race_number
        """
        cursor.execute(query, [today_str] + sidebar_selected_venues)
    else:
        cursor.execute("""
            SELECT r.id, r.venue_code, r.race_number, r.race_time,
                   CASE WHEN ed.exhibition_time IS NOT NULL THEN 1 ELSE 0 END as has_beforeinfo
            FROM races r
            LEFT JOIN exhibition_data ed ON r.id = ed.race_id AND ed.pit_number = 1
            WHERE r.race_date = ?
            ORDER BY r.venue_code, r.race_number
        """, (today_str,))

    races = cursor.fetchall()
    conn.close()

    # サイドバーでの選択状態を表示
    if sidebar_selected_venues:
        selected_venue_names = [venue_name_map.get(code, code) for code in sidebar_selected_venues]
        st.info(f"🏟️ 対象会場（サイドバー選択）: {', '.join(selected_venue_names)}")
    else:
        st.info("🏟️ 対象会場: 全場（サイドバーで会場を選択すると絞り込めます）")

    if not races:
        st.warning("本日のレースが見つかりません")
        if st.button("閉じる", key="close_beforeinfo_dialog"):
            st.session_state.show_beforeinfo_dialog = False
            st.rerun()
        return

    # 会場ごとにグループ化
    venues_with_races = {}
    for race_id, venue_code, race_number, race_time, has_beforeinfo in races:
        venue_name = venue_name_map.get(venue_code, f'会場{venue_code}')
        if venue_name not in venues_with_races:
            venues_with_races[venue_name] = []
        venues_with_races[venue_name].append({
            'race_id': race_id,
            'venue_code': venue_code,
            'race_number': race_number,
            'race_time': race_time,
            'has_beforeinfo': has_beforeinfo
        })

    # 取得モード選択
    col1, col2 = st.columns(2)
    with col1:
        fetch_mode = st.radio(
            "取得モード",
            ["全レース取得", "会場・レース指定"],
            key="beforeinfo_fetch_mode",
            horizontal=True
        )

    # 自動スキップロジック（固定）の説明
    with col2:
        st.caption("⚙️ 自動スキップ:")
        st.caption("• 確定済み＆取得済み → スキップ")
        st.caption("• 35分以上先 → スキップ（未公開）")
        st.caption("• 次のレース/まもなく → 取得")

    target_races = []

    if fetch_mode == "会場・レース指定":
        st.markdown("#### 対象レース選択")

        # 会場選択
        selected_venue = st.selectbox(
            "会場を選択",
            list(venues_with_races.keys()),
            key="beforeinfo_venue_select"
        )

        if selected_venue:
            venue_races = venues_with_races[selected_venue]

            # レース一覧表示
            race_options = []
            for race in venue_races:
                status = "✅" if race['has_beforeinfo'] else "⬜"
                time_str = race['race_time'] or '未定'
                race_options.append(f"{status} {race['race_number']}R ({time_str})")

            selected_races = st.multiselect(
                "レースを選択（複数可）",
                race_options,
                key="beforeinfo_race_select"
            )

            # 選択されたレースを抽出
            for race in venue_races:
                for selected in selected_races:
                    if f"{race['race_number']}R" in selected:
                        target_races.append({
                            'race_id': race['race_id'],
                            'venue_code': race['venue_code'],
                            'venue_name': selected_venue,
                            'race_number': race['race_number'],
                            'race_time': race['race_time'],
                            'has_beforeinfo': race['has_beforeinfo']
                        })
                        break

            st.caption(f"選択中: {len(target_races)}レース")

    else:
        # 全レース取得
        for venue_name, venue_races in venues_with_races.items():
            for race in venue_races:
                target_races.append({
                    'race_id': race['race_id'],
                    'venue_code': race['venue_code'],
                    'venue_name': venue_name,
                    'race_number': race['race_number'],
                    'race_time': race['race_time'],
                    'has_beforeinfo': race['has_beforeinfo']
                })

        # 統計表示
        total = len(target_races)
        fetched = sum(1 for r in target_races if r['has_beforeinfo'])
        st.info(f"全{total}レース（取得済み: {fetched}件）")

    # 実行ボタン
    col_exec, col_close = st.columns(2)
    with col_exec:
        if st.button("🔄 取得開始", type="primary", use_container_width=True):
            _fetch_and_update_beforeinfo(target_races)

    with col_close:
        if st.button("❌ 閉じる", use_container_width=True):
            st.session_state.show_beforeinfo_dialog = False
            st.rerun()

    st.markdown("---")


def _fetch_and_update_beforeinfo(target_races: List[Dict]):
    """直前情報とオッズを取得して予想を更新（最適化版：未確定レースのみ更新）"""
    from datetime import datetime, timedelta
    from config.settings import VENUES
    import concurrent.futures
    import threading

    try:
        today_ymd = datetime.now().strftime('%Y%m%d')
        now = datetime.now()

        # 会場名マッピング
        venue_name_map = {}
        for venue_id, venue_info in VENUES.items():
            venue_name_map[venue_info['code']] = venue_info['name']

        # 次のレース番号を会場ごとに特定
        def get_next_race_numbers(races):
            """会場ごとの次のレース番号を取得"""
            next_race_by_venue = {}
            races_by_venue = {}

            # 会場ごとにレースをグループ化
            for race in races:
                venue_code = race['venue_code']
                if venue_code not in races_by_venue:
                    races_by_venue[venue_code] = []
                races_by_venue[venue_code].append(race)

            # 会場ごとに次のレースを特定
            for venue_code, venue_races in races_by_venue.items():
                next_race_num = None
                for race in sorted(venue_races, key=lambda r: r['race_number']):
                    if race.get('race_time'):
                        try:
                            race_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {race['race_time']}", "%Y-%m-%d %H:%M:%S")
                            # レース時刻+10分経過で確定とみなす
                            if now < race_time + timedelta(minutes=10):
                                next_race_num = race['race_number']
                                break
                        except:
                            pass
                next_race_by_venue[venue_code] = next_race_num

            return next_race_by_venue

        next_race_by_venue = get_next_race_numbers(target_races)

        # フィルタリング（賢いスキップロジック）
        races_to_fetch = []
        skipped_finished_fetched = 0
        skipped_future_fetched = 0

        for race in target_races:
            venue_code = race['venue_code']
            race_number = race['race_number']
            has_beforeinfo = race.get('has_beforeinfo', False)
            race_time = race.get('race_time')

            # レース時刻がない場合は取得
            if not race_time:
                races_to_fetch.append(race)
                continue

            try:
                race_time_dt = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {race_time}", "%Y-%m-%d %H:%M:%S")
                is_finished = now > (race_time_dt + timedelta(minutes=10))
            except:
                is_finished = False

            # 次のレース判定（次と次の次まで）
            next_race_num = next_race_by_venue.get(venue_code)
            is_upcoming = (next_race_num is not None and
                          race_number >= next_race_num and
                          race_number <= next_race_num + 1)

            # 直前情報公開判定（レース開始30分前から公開される）
            try:
                is_soon = now > (race_time_dt - timedelta(minutes=35))  # 35分前から対象
            except:
                is_soon = True  # 時刻不明なら取得対象

            # スキップ判定
            if is_finished and has_beforeinfo:
                # 確定済み & 取得済み → スキップ
                skipped_finished_fetched += 1
                continue

            if is_upcoming:
                # 次のレース → 常に取得
                races_to_fetch.append(race)
                continue

            if not has_beforeinfo:
                if is_soon or is_finished:
                    # 未取得 & (まもなく or 終了済み) → 取得
                    races_to_fetch.append(race)
                else:
                    # 未取得 & まだ先 → スキップ（直前情報未公開）
                    skipped_future_fetched += 1
                continue

            # それ以外（未確定 & 取得済み & 次のレースではない）→ スキップ
            skipped_future_fetched += 1

        if not races_to_fetch:
            st.warning("取得対象のレースがありません")
            if skipped_finished_fetched > 0:
                st.info(f"✅ 確定済み＆取得済みスキップ: {skipped_finished_fetched}件")
            if skipped_future_fetched > 0:
                st.info(f"⏭️ 未公開/取得済みスキップ: {skipped_future_fetched}件")
            return

        # スキップ情報表示
        if skipped_finished_fetched > 0 or skipped_future_fetched > 0:
            skip_msg = []
            if skipped_finished_fetched > 0:
                skip_msg.append(f"確定済み: {skipped_finished_fetched}件")
            if skipped_future_fetched > 0:
                skip_msg.append(f"未公開/取得済み: {skipped_future_fetched}件")
            st.info(f"⏭️ スキップ: {', '.join(skip_msg)}")

        # 進捗表示
        progress_bar = st.progress(0)
        status_text = st.empty()

        # BeforeInfoScraper をインポート
        from src.scraper.beforeinfo_scraper import BeforeInfoScraper

        scraper = BeforeInfoScraper(delay=0.2)  # 高速化: 0.5→0.2秒

        total = len(races_to_fetch)
        success_count = 0
        error_count = 0
        no_data_count = 0
        fetched_data = []

        for idx, race in enumerate(races_to_fetch):
            venue_name = race.get('venue_name') or venue_name_map.get(race['venue_code'], f'会場{race["venue_code"]}')
            status_text.text(f"取得中: {venue_name} {race['race_number']}R ({idx + 1}/{total})")

            try:
                # 直前情報を取得
                raw_data = scraper.get_race_beforeinfo(race['venue_code'], today_ymd, race['race_number'])

                if raw_data and raw_data.get('is_published'):
                    # UI形式に変換
                    beforeinfo = scraper.to_ui_format(raw_data)

                    if beforeinfo:
                        # 実際にデータがあるかチェック
                        racers = beforeinfo.get('racers', [])
                        has_actual_data = any(r.get('exhibition_time') for r in racers)

                        if has_actual_data:
                            fetched_data.append({
                                'race_id': race['race_id'],
                                'venue_code': race['venue_code'],
                                'venue_name': venue_name,
                                'race_number': race['race_number'],
                                'beforeinfo': beforeinfo
                            })
                            success_count += 1
                        else:
                            no_data_count += 1
                    else:
                        no_data_count += 1
                else:
                    no_data_count += 1

            except Exception as e:
                logger.error(f"直前情報取得エラー ({venue_name} {race['race_number']}R): {e}")
                error_count += 1

            # 進捗更新
            progress_bar.progress((idx + 1) / total)

        progress_bar.empty()
        status_text.empty()

        # === レース分類（未確定/終了済み） ===
        unfinished_races = []
        finished_races = []
        for race in target_races:
            race_time = race.get('race_time')
            if race_time:
                try:
                    race_time_dt = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {race_time}", "%Y-%m-%d %H:%M:%S")
                    if now < race_time_dt:
                        unfinished_races.append(race)
                    elif now > race_time_dt + timedelta(minutes=10):  # 10分以上経過で終了とみなす
                        finished_races.append(race)
                except:
                    pass

        # === 終了レースの結果取得 ===
        result_success_count = 0
        if finished_races:
            result_status_text = st.empty()
            result_progress_bar = st.progress(0)
            result_status_text.text("終了レースの結果を取得中...")

            result_success_count = _fetch_results_for_finished_races(
                finished_races, today_ymd, venue_name_map, result_progress_bar, result_status_text
            )

            result_progress_bar.empty()
            result_status_text.empty()

        # === オッズ取得処理（未確定レースのみ、並列実行） ===
        odds_status_text = st.empty()
        odds_progress_bar = st.progress(0)
        odds_status_text.text("オッズデータ取得中...")

        odds_success_count = 0
        odds_skip_count = 0

        if unfinished_races:
            from src.scraper.odds_scraper import OddsScraper
            import sqlite3
            from config.settings import DATABASE_PATH

            def fetch_single_odds_optimized(race_info):
                """オッズを取得してDBに保存"""
                try:
                    scraper = OddsScraper(delay=0.1, max_retries=1)
                    odds = scraper.get_trifecta_odds(
                        race_info['venue_code'],
                        today_ymd,
                        race_info['race_number']
                    )
                    scraper.close()

                    if odds and len(odds) > 50:
                        conn = sqlite3.connect(DATABASE_PATH)
                        cursor = conn.cursor()
                        cursor.execute(
                            "DELETE FROM trifecta_odds WHERE race_id = ?",
                            (race_info['race_id'],)
                        )
                        for combo, odds_val in odds.items():
                            cursor.execute(
                                "INSERT INTO trifecta_odds (race_id, combination, odds) VALUES (?, ?, ?)",
                                (race_info['race_id'], combo, odds_val)
                            )
                        conn.commit()
                        conn.close()
                        return True
                    return False
                except Exception:
                    return False

            # 並列実行（最大8スレッド）
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                futures = {executor.submit(fetch_single_odds_optimized, race): race for race in unfinished_races}

                for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
                    if future.result():
                        odds_success_count += 1
                    else:
                        odds_skip_count += 1
                    odds_progress_bar.progress(idx / len(unfinished_races))

        odds_progress_bar.empty()
        odds_status_text.empty()

        # === 結果をまとめて表示 ===
        if success_count > 0 or odds_success_count > 0 or result_success_count > 0:
            # DBに保存（メッセージなしで実行）
            if success_count > 0:
                saved_count = _save_beforeinfo_to_db(fetched_data)

            # 最終結果のみ表示
            result_parts = []
            if success_count > 0:
                result_parts.append(f"直前情報: {success_count}件")
            if odds_success_count > 0:
                result_parts.append(f"オッズ: {odds_success_count}件")
            if result_success_count > 0:
                result_parts.append(f"レース結果: {result_success_count}件")

            result_msg = f"✅ 取得完了: {', '.join(result_parts)}"
            if no_data_count > 0:
                result_msg += f" (直前情報未公開: {no_data_count}件)"
            if odds_skip_count > 0:
                result_msg += f" (オッズ未公開: {odds_skip_count}件)"
            st.success(result_msg)

            # 取得データのサマリーを表示
            with st.expander("📋 取得データの詳細", expanded=False):
                for data in fetched_data[:10]:  # 最初の10件のみ
                    st.markdown(f"**{data['venue_name']} {data['race_number']}R**")

                    weather = data['beforeinfo'].get('weather', {})
                    if any(weather.values()):
                        cols = st.columns(4)
                        cols[0].metric("気温", f"{weather.get('temperature', '-')}℃" if weather.get('temperature') else "-")
                        cols[1].metric("水温", f"{weather.get('water_temp', '-')}℃" if weather.get('water_temp') else "-")
                        cols[2].metric("風速", f"{weather.get('wind_speed', '-')}m" if weather.get('wind_speed') else "-")
                        cols[3].metric("波高", f"{weather.get('wave_height', '-')}cm" if weather.get('wave_height') else "-")

                    racers = data['beforeinfo'].get('racers', [])
                    if racers:
                        racer_data = []
                        for r in racers:
                            racer_data.append({
                                '枠': r.get('pit_number', '-'),
                                '展示タイム': r.get('exhibition_time', '-'),
                                'ST': r.get('start_timing', '-'),
                                'チルト': r.get('tilt', '-')
                            })
                        if racer_data:
                            st.dataframe(pd.DataFrame(racer_data), hide_index=True)

                    st.markdown("---")

                if len(fetched_data) > 10:
                    st.info(f"他 {len(fetched_data) - 10} レースのデータも取得済み")

            # 自動で予想更新を実行（賢いフィルタリング）
            st.markdown("---")
            _update_predictions_with_beforeinfo(fetched_data, all_races=target_races)

        elif no_data_count > 0 and success_count == 0:
            st.info(f"⏳ 直前情報未公開: {no_data_count}件 (レース開始約30分前に公開されます)")
        else:
            st.warning("直前情報を取得できませんでした")

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        import traceback
        st.code(traceback.format_exc())


def _update_predictions_with_beforeinfo(fetched_data: List[Dict], all_races: List[Dict] = None):
    """取得した直前情報で予想を更新（賢いフィルタリング + バッチ処理）"""
    import time

    try:
        from src.analysis.prediction_updater import PredictionUpdater
        from datetime import datetime, timedelta

        # 賢いフィルタリング: 予想更新が必要なレースのみ
        now = datetime.now()
        races_to_update = []
        skipped_finished = 0

        # all_racesが提供されている場合は、確定済みレースをスキップ
        if all_races:
            for data in fetched_data:
                race_id = data['race_id']
                # all_racesから対応するレース情報を取得
                race_info = next((r for r in all_races if r['race_id'] == race_id), None)

                if race_info and race_info.get('race_time'):
                    try:
                        race_time = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {race_info['race_time']}", "%Y-%m-%d %H:%M:%S")
                        is_finished = now > (race_time + timedelta(minutes=10))

                        if is_finished:
                            # 確定済みレース → 予想更新スキップ
                            skipped_finished += 1
                            continue
                    except:
                        pass

                races_to_update.append(data)
        else:
            # all_racesが提供されていない場合は全て更新
            races_to_update = fetched_data

        if skipped_finished > 0:
            st.info(f"⏭️ 確定済みレースをスキップ: {skipped_finished}件")

        # レースIDリストを作成
        race_ids = [data['race_id'] for data in races_to_update]
        total = len(race_ids)

        if total == 0:
            st.warning("予想更新対象のレースがありません（全て確定済み）")
            return

        start_time = time.time()

        # 進捗表示用プレースホルダー（処理完了後にクリア）
        status_placeholder = st.empty()
        progress_bar = st.progress(0)
        detail_placeholder = st.empty()

        status_placeholder.info(f"🔄 予想を更新中... (対象: {total}レース)")

        updater = PredictionUpdater()

        # 進捗コールバック
        def update_progress(current, total_count):
            progress_bar.progress(current / total_count)
            now = time.time()
            elapsed = now - start_time
            per_race = elapsed / current if current > 0 else 0
            eta = per_race * (total_count - current)

            if current <= len(races_to_update):
                data = races_to_update[current - 1]
                detail_placeholder.text(f"{data['venue_name']} {data['race_number']}R ({current}/{total_count}) - 残り約{eta:.0f}秒")

        # 今日の日付
        target_date = datetime.now().strftime('%Y-%m-%d')

        # バッチ更新
        stats = updater.update_batch_before_predictions(
            race_ids=race_ids,
            target_date=target_date,
            progress_callback=update_progress
        )

        total_time = time.time() - start_time

        # 進捗表示をクリア
        status_placeholder.empty()
        progress_bar.empty()
        detail_placeholder.empty()

        updated_count = stats['updated']
        failed_count = stats['failed']

        if updated_count > 0:
            st.success(f"✅ 予想更新完了: {updated_count}件成功 ({total_time:.1f}秒)")
            if failed_count > 0:
                st.warning(f"⚠️ {failed_count}件失敗")
        else:
            st.warning("予想を更新できませんでした")

    except Exception as e:
        st.error(f"予想更新エラー: {e}")
        import traceback
        st.code(traceback.format_exc())


def _save_beforeinfo_to_db(fetched_data: List[Dict]) -> int:
    """
    取得した直前情報をDBに保存 (race_details & weather テーブルに保存)

    Args:
        fetched_data: 取得した直前情報リスト
            [{
                'race_id': int,
                'venue_code': str,
                'venue_name': str,
                'race_number': int,
                'beforeinfo': {
                    'racers': [{
                        'pit_number': int,
                        'exhibition_time': float,
                        'start_timing': float,
                        'tilt': float,
                        'parts_replacement': str,
                        'adjusted_weight': float,
                        'exhibition_course': int,
                        'prev_race_course': int,
                        'prev_race_st': float,
                        'prev_race_rank': int
                        ...
                    }, ...],
                    'weather': {
                        'temperature': float,
                        'water_temp': float,
                        'wind_speed': int,
                        'wave_height': int,
                        'weather_code': int,
                        'wind_dir_code': int
                    }
                }
            }, ...]

    Returns:
        保存したレコード数
    """
    import sqlite3
    from config.settings import DATABASE_PATH
    from datetime import datetime

    saved_count = 0

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        for data in fetched_data:
            race_id = data['race_id']
            venue_code = data['venue_code']
            beforeinfo = data['beforeinfo']
            racers = beforeinfo.get('racers', [])
            weather = beforeinfo.get('weather', {})

            # 天候データを保存（weather テーブル）
            # weather_dateを取得する必要がある
            cursor.execute("SELECT race_date FROM races WHERE id = ?", (race_id,))
            race_row = cursor.fetchone()
            if race_row and any(weather.values()):
                weather_date = race_row[0]

                # 既存レコード確認
                cursor.execute("""
                    SELECT id FROM weather
                    WHERE venue_code = ? AND weather_date = ?
                """, (venue_code, weather_date))

                existing_weather = cursor.fetchone()

                if existing_weather:
                    # 更新
                    cursor.execute("""
                        UPDATE weather
                        SET temperature = COALESCE(?, temperature),
                            water_temperature = COALESCE(?, water_temperature),
                            wind_speed = COALESCE(?, wind_speed),
                            wave_height = COALESCE(?, wave_height),
                            weather_code = COALESCE(?, weather_code),
                            wind_dir_code = COALESCE(?, wind_dir_code)
                        WHERE venue_code = ? AND weather_date = ?
                    """, (
                        weather.get('temperature'),
                        weather.get('water_temp'),
                        weather.get('wind_speed'),
                        weather.get('wave_height'),
                        weather.get('weather_code'),
                        weather.get('wind_dir_code'),
                        venue_code,
                        weather_date
                    ))
                else:
                    # 新規挿入
                    cursor.execute("""
                        INSERT INTO weather
                        (venue_code, weather_date, temperature, water_temperature, wind_speed, wave_height, weather_code, wind_dir_code)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        venue_code,
                        weather_date,
                        weather.get('temperature'),
                        weather.get('water_temp'),
                        weather.get('wind_speed'),
                        weather.get('wave_height'),
                        weather.get('weather_code'),
                        weather.get('wind_dir_code')
                    ))

            # 選手データを保存（race_details テーブル）
            for racer in racers:
                pit_number = racer.get('pit_number')
                if not pit_number:
                    continue

                # 更新する値
                exhibition_time = racer.get('exhibition_time')
                st_time = racer.get('start_timing')
                tilt_angle = racer.get('tilt')
                parts_replacement = racer.get('parts_replacement', '')
                adjusted_weight = racer.get('adjusted_weight')
                exhibition_course = racer.get('exhibition_course')
                prev_race_course = racer.get('prev_race_course')
                prev_race_st = racer.get('prev_race_st')
                prev_race_rank = racer.get('prev_race_rank')

                # race_details の既存レコードを更新
                cursor.execute("""
                    UPDATE race_details
                    SET exhibition_time = COALESCE(?, exhibition_time),
                        st_time = COALESCE(?, st_time),
                        tilt_angle = COALESCE(?, tilt_angle),
                        parts_replacement = COALESCE(?, parts_replacement),
                        adjusted_weight = COALESCE(?, adjusted_weight),
                        exhibition_course = COALESCE(?, exhibition_course),
                        prev_race_course = COALESCE(?, prev_race_course),
                        prev_race_st = COALESCE(?, prev_race_st),
                        prev_race_rank = COALESCE(?, prev_race_rank)
                    WHERE race_id = ? AND pit_number = ?
                """, (
                    exhibition_time,
                    st_time,
                    tilt_angle,
                    parts_replacement,
                    adjusted_weight,
                    exhibition_course,
                    prev_race_course,
                    prev_race_st,
                    prev_race_rank,
                    race_id,
                    pit_number
                ))

                if cursor.rowcount > 0:
                    saved_count += 1

        conn.commit()
        conn.close()
        logger.info(f"直前情報をDBに保存: {saved_count}件")

    except Exception as e:
        logger.error(f"直前情報のDB保存エラー: {e}")
        import traceback
        traceback.print_exc()

    return saved_count


def _fetch_results_for_finished_races(finished_races: List[Dict], date_str: str, venue_name_map: Dict, progress_bar, status_text) -> int:
    """
    終了レースの結果と払戻金を取得してDBに保存（直前情報取得から呼び出される）

    Args:
        finished_races: 終了レースのリスト
        date_str: 日付文字列（YYYYMMDD形式）
        venue_name_map: 会場コード→名前のマッピング
        progress_bar: Streamlit進捗バー
        status_text: Streamlitステータステキスト

    Returns:
        int: 成功件数
    """
    import sqlite3
    from config.settings import DATABASE_PATH
    from src.scraper.result_scraper import ResultScraper

    if not finished_races:
        return 0

    scraper = ResultScraper()
    success_count = 0

    try:
        conn = sqlite3.connect(DATABASE_PATH, timeout=30.0)
        cursor = conn.cursor()

        for idx, race in enumerate(finished_races):
            race_id = race['race_id']
            venue_code = race['venue_code']
            race_number = race['race_number']
            venue_name = venue_name_map.get(venue_code, f'会場{venue_code}')

            status_text.text(f"結果取得中: {venue_name} {race_number}R...")
            progress_bar.progress((idx + 1) / len(finished_races))

            try:
                # 既に結果がある場合はスキップ
                cursor.execute("SELECT COUNT(*) FROM results WHERE race_id = ?", (race_id,))
                if cursor.fetchone()[0] > 0:
                    continue

                # 結果を取得
                result_data = scraper.get_race_result_complete(
                    venue_code=f"{int(venue_code):02d}",
                    race_date=date_str,
                    race_number=race_number
                )

                if not result_data or not result_data.get('results'):
                    continue

                # 結果をDBに保存
                results = result_data.get('results', [])
                is_invalid = result_data.get('is_invalid', False)

                for res in results:
                    pit_number = res.get('pit_number')
                    rank = res.get('rank')

                    if pit_number and rank:
                        rank_str = str(rank) if isinstance(rank, int) else rank
                        cursor.execute("""
                            INSERT OR REPLACE INTO results (race_id, pit_number, rank, is_invalid)
                            VALUES (?, ?, ?, ?)
                        """, (race_id, pit_number, rank_str, 1 if is_invalid else 0))

                # 払戻金をDBに保存
                payouts = result_data.get('payouts', {})
                trifecta_payout = payouts.get('trifecta', [])

                if trifecta_payout:
                    for payout_data in trifecta_payout:
                        combination = payout_data.get('combination', '')
                        amount = payout_data.get('amount', 0)

                        if combination and amount:
                            cursor.execute("""
                                INSERT OR REPLACE INTO payouts (race_id, bet_type, combination, amount)
                                VALUES (?, 'trifecta', ?, ?)
                            """, (race_id, combination, amount))

                # 決まり手を保存
                kimarite = result_data.get('kimarite')
                if kimarite:
                    cursor.execute("""
                        UPDATE races SET winning_technique = ? WHERE id = ?
                    """, (kimarite, race_id))

                success_count += 1

            except Exception as e:
                logger.error(f"結果取得エラー ({venue_name} {race_number}R): {e}")
                continue

        conn.commit()
        conn.close()

    except Exception as e:
        logger.error(f"結果取得処理エラー: {e}")

    return success_count


def _fetch_and_save_results(finished_targets: List[Dict], target_date_str: str):
    """
    終了レースの結果と払戻金を取得してDBに保存

    Args:
        finished_targets: 終了レースのリスト
        target_date_str: 対象日付文字列（YYYY-MM-DD）
    """
    import sqlite3
    from config.settings import DATABASE_PATH
    from src.scraper.result_scraper import ResultScraper

    if not finished_targets:
        st.info("取得対象の終了レースがありません")
        return

    st.info(f"🔄 {len(finished_targets)}件のレース結果を取得中...")
    progress_bar = st.progress(0)
    status_text = st.empty()

    scraper = ResultScraper()
    success_count = 0
    error_count = 0

    # 日付形式変換（YYYY-MM-DD → YYYYMMDD）
    date_str = target_date_str.replace('-', '')

    try:
        conn = sqlite3.connect(DATABASE_PATH, timeout=30.0)
        cursor = conn.cursor()

        for idx, t in enumerate(finished_targets):
            race_id = t['race_id']
            venue_code = t['venue_code']
            race_number = t['race_number']
            venue_name = t['venue_name']

            status_text.text(f"取得中: {venue_name} {race_number}R...")
            progress_bar.progress((idx + 1) / len(finished_targets))

            try:
                # 結果を取得
                result_data = scraper.get_race_result_complete(
                    venue_code=f"{int(venue_code):02d}",
                    race_date=date_str,
                    race_number=race_number
                )

                if not result_data or not result_data.get('results'):
                    error_count += 1
                    continue

                # 結果をDBに保存
                results = result_data.get('results', [])
                is_invalid = result_data.get('is_invalid', False)

                for res in results:
                    pit_number = res.get('pit_number')
                    rank = res.get('rank')

                    if pit_number and rank:
                        # rankをTEXT型に変換（DB定義に合わせる）
                        rank_str = str(rank) if isinstance(rank, int) else rank

                        # 既存データを削除
                        cursor.execute(
                            "DELETE FROM results WHERE race_id = ? AND pit_number = ?",
                            (race_id, pit_number)
                        )
                        # 新規挿入
                        cursor.execute("""
                            INSERT INTO results (race_id, pit_number, rank, is_invalid)
                            VALUES (?, ?, ?, ?)
                        """, (race_id, pit_number, rank_str, 1 if is_invalid else 0))

                # 払戻金をDBに保存
                payouts = result_data.get('payouts', {})
                trifecta_payout = payouts.get('trifecta', [])

                if trifecta_payout:
                    for payout_data in trifecta_payout:
                        combination = payout_data.get('combination', '')
                        amount = payout_data.get('amount', 0)

                        if combination and amount:
                            # 既存データを削除
                            cursor.execute(
                                "DELETE FROM payouts WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?",
                                (race_id, combination)
                            )
                            # 新規挿入
                            cursor.execute("""
                                INSERT INTO payouts (race_id, bet_type, combination, amount)
                                VALUES (?, 'trifecta', ?, ?)
                            """, (race_id, combination, amount))

                # 決まり手を保存
                kimarite = result_data.get('kimarite')
                if kimarite:
                    cursor.execute("""
                        UPDATE races SET winning_technique = ? WHERE id = ?
                    """, (kimarite, race_id))

                success_count += 1

            except Exception as e:
                logger.error(f"結果取得エラー ({venue_name} {race_number}R): {e}")
                error_count += 1
                continue

        conn.commit()
        conn.close()

        progress_bar.empty()
        status_text.empty()

        if success_count > 0:
            st.success(f"✅ 結果取得完了: {success_count}件成功" + (f", {error_count}件失敗" if error_count > 0 else ""))
            st.rerun()  # 結果を反映するためにリロード
        else:
            st.warning("結果を取得できませんでした")

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        import traceback
        st.code(traceback.format_exc())
