"""
予測データ健全性チェック（公式・完全版）
==========================================
このスクリプトが唯一の正確な現状確認手段です。
毎回このスクリプトを実行して結果を確認してください。

汚染タイプ:
  A_fix: st_time旧コード かつ exhibition_timeあり → 再生成可能・要対応
  A_str: st_time旧コード かつ exhibition_timeなし → 再生成不可・バックテスト影響ゼロ（構造的残存）
  P8:    exhibition_buff汚染 (generated_at >= '2026-03-09 14:54' AND < '2026-03-11')
  OK:    正常

使い方:
  python scripts/check_prediction_health.py           # 通常チェック
  python scripts/check_prediction_health.py --fast    # fixable計算スキップ（高速）
"""
import sqlite3
import sys
import os
import calendar

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB_PATH = 'data/boatrace.db'

# 汚染定義（変更禁止）
OLD_ST_CUTOFF = '2026-03-06'
P8_START      = '2026-03-09 14:54:00'
P8_END        = '2026-03-11'


def check(conn, pred_type, years):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT
          strftime('%Y-%m', r.race_date) as month,
          COUNT(*) as total,
          SUM(CASE WHEN p.generated_at < '{OLD_ST_CUTOFF}' THEN 1 ELSE 0 END) as A_old,
          SUM(CASE WHEN p.generated_at >= '{P8_START}' AND p.generated_at < '{P8_END}' THEN 1 ELSE 0 END) as P8,
          SUM(CASE WHEN p.generated_at >= '{P8_END}' THEN 1 ELSE 0 END) as clean,
          MAX(p.generated_at) as newest
        FROM race_predictions p
        JOIN races r ON p.race_id = r.id
        WHERE p.prediction_type='{pred_type}'
          AND ({' OR '.join([f"r.race_date LIKE '{y}%'" for y in years])})
        GROUP BY month ORDER BY month
    """)
    return cur.fetchall()


def check_before_fixable(conn, years):
    """before予測のA_oldをfixable(再生成可能) / structural(再生成不可) に分類。
    exhibition_timeなしのレースはgenerate_before_fast.pyがスキップする仕様のため、
    再生成しても旧予測が上書きされず、かつtrifecta_oddsも存在しないのでバックテスト影響ゼロ。
    """
    cur = conn.cursor()
    cur.execute(f"""
        SELECT
          strftime('%Y-%m', r.race_date) as month,
          SUM(CASE WHEN ex.race_id IS NOT NULL THEN 1 ELSE 0 END) as A_fix,
          SUM(CASE WHEN ex.race_id IS NULL     THEN 1 ELSE 0 END) as A_str
        FROM race_predictions p
        JOIN races r ON p.race_id = r.id
        LEFT JOIN (
          SELECT DISTINCT race_id FROM race_details WHERE exhibition_time IS NOT NULL
        ) ex ON ex.race_id = r.id
        WHERE p.prediction_type='before'
          AND ({' OR '.join([f"r.race_date LIKE '{y}%'" for y in years])})
          AND p.generated_at < '{OLD_ST_CUTOFF}'
        GROUP BY month HAVING A_fix > 0 OR A_str > 0
        ORDER BY month
    """)
    return {month: (a_fix, a_str) for month, a_fix, a_str in cur.fetchall()}


def main():
    fast_mode = '--fast' in sys.argv

    if not os.path.exists(DB_PATH):
        print(f'❌ DBが見つかりません: {DB_PATH}')
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    years = [str(y) for y in range(2020, 2027)]

    needs_action = []

    for pred_type in ['before', 'advance']:
        rows = check(conn, pred_type, years)
        has_a_old = any(row[2] > 0 for row in rows)

        # before予測 かつ A_oldあり かつ 高速モードでない場合 → fixable分類を計算
        fixable_map = {}
        if pred_type == 'before' and has_a_old and not fast_mode:
            print()
            print('  (before予測のA_old内訳を計算中... 約8秒)', flush=True)
            fixable_map = check_before_fixable(conn, years)

        print()
        print(f'{"="*70}')
        print(f'  {pred_type.upper()}予測 汚染チェック（全年度）')
        print(f'{"="*70}')

        if fixable_map:
            print(f'  {"月":<8} {"合計":>6}  {"A_fix":>7}  {"A_str":>7}  {"P8汚染":>7}  {"正常":>7}  状態')
            print(f'  {"-"*68}')
        else:
            print(f'  {"月":<8} {"合計":>6}  {"A(st旧)":>7}  {"P8汚染":>7}  {"正常":>7}  状態')
            print(f'  {"-"*60}')

        total_a = total_p8 = total_ok = total_all = 0
        total_a_fix = total_a_str = 0

        for row in rows:
            month, total, a, p8, clean, newest = row
            issues = []
            structural_only = False

            if fixable_map and a > 0:
                a_fix, a_str = fixable_map.get(month, (0, a))
                total_a_fix += a_fix
                total_a_str += a_str
                if a_fix > 0:
                    issues.append(f'A_fix={a_fix:,}')
                if a_str > 0 and a_fix == 0:
                    structural_only = True  # A_strのみ → 対応不要
                    issues.append(f'A_str={a_str:,}')
                print(f'  {month}  {total:6,}   {a_fix:7,}   {a_str:7,}   {p8:7,}   {clean:7,}  ', end='')
            else:
                if a > 0: issues.append(f'A={a:,}')
                print(f'  {month}  {total:6,}   {a:7,}   {p8:7,}   {clean:7,}  ', end='')

            if p8 > 0: issues.append(f'P8={p8:,}')

            if not issues:
                status = '✅'
            elif structural_only and p8 == 0:
                status = '⚪ ' + ', '.join(issues) + '（構造的残存・対応不要）'
            else:
                status = '❌  ' + ', '.join(issues)

            print(status)
            total_a += a; total_p8 += p8; total_ok += clean; total_all += total

            # needs_actionに追加するのは fixable > 0 か P8 > 0 の月のみ
            if fixable_map:
                a_fix, a_str = fixable_map.get(month, (0, a))
                if a_fix > 0 or p8 > 0:
                    needs_action.append((pred_type, month, a_fix, p8))
            else:
                if a > 0 or p8 > 0:
                    needs_action.append((pred_type, month, a, p8))

        print(f'  {"-"*60}')
        if fixable_map:
            print(f'  {"合計":<8} {total_all:6,}   {total_a_fix:7,}   {total_a_str:7,}   {total_p8:7,}   {total_ok:7,}')
            print()
            print(f'  ℹ️  A_fix={total_a_fix:,}件: 再生成で解消可能')
            print(f'  ℹ️  A_str={total_a_str:,}件: exhibition_timeなし → 再生成不可・バックテスト影響ゼロ（正常）')
        else:
            print(f'  {"合計":<8} {total_all:6,}   {total_a:7,}   {total_p8:7,}   {total_ok:7,}')
            if pred_type == 'before' and has_a_old and fast_mode:
                print()
                print(f'  ⚠️  --fast モード: A_old={total_a:,}件のfixable/structural分類はスキップ')
                print(f'      詳細確認: python scripts/check_prediction_health.py（--fastなし、約8秒追加）')

    conn.close()

    print()
    print('='*70)
    if not needs_action:
        print('  ✅✅✅ 全データ正常。再生成不要。')
        if fixable_map and total_a_str > 0:
            print(f'  ℹ️  A_str {total_a_str:,}件は構造的残存（exhibition_timeなし）のため表示されますが対応不要です。')
    else:
        print('  ❌ 要対応リスト（再生成が必要な月）:')
        print()

        before_issues = [(m, a, p8) for pt, m, a, p8 in needs_action if pt == 'before']
        advance_issues = [(m, a, p8) for pt, m, a, p8 in needs_action if pt == 'advance']

        if before_issues:
            print('  【before予測】バックテストに直接影響:')
            months = [m for m, a, p8 in before_issues]
            years_needed = sorted(set(m[:4] for m in months))
            for yr in years_needed:
                yr_months = [(m, a, p8) for m, a, p8 in before_issues if m.startswith(yr)]
                start = yr_months[0][0] + '-01'
                end_m = yr_months[-1][0]
                y, mo = int(end_m[:4]), int(end_m[5:7])
                last_day = calendar.monthrange(y, mo)[1]
                end = f'{end_m}-{last_day}'
                total_contaminated = sum(a + p8 for _, a, p8 in yr_months)
                print(f'    {yr}年 ({len(yr_months)}ヶ月, {total_contaminated:,}件汚染):')
                print(f'      python scripts/prediction/generate_before_fast.py \\')
                print(f'        --year {yr} --start-date {start} --end-date {end} --force')
                print()

        if advance_issues:
            print('  【advance予測】バックテストへの影響は限定的:')
            a_months = [m for m, a, p8 in advance_issues]
            print(f'    汚染月数: {len(a_months)}ヶ月（優先度低）')

    print('='*70)
    print()


if __name__ == '__main__':
    main()
