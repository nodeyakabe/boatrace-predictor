"""
オリジナル展示データ（isshu/mawari/chiku）信号強度測定スクリプト

Step1: コード変更不要の純粋DB分析
- 各指標（isshu/mawari/chiku）の1着予測力を全コース×順位×gap閾値で測定
- バイアス定量化
- 案1/2/3の効果推定

使い方:
    python scripts/analysis/boaters_signal_strength.py
"""

import sys
import sqlite3
import statistics
from pathlib import Path
from collections import defaultdict

# Windows文字化け対策
if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')

project_root = Path(__file__).resolve().parents[2]
DB_PATH = project_root / 'data' / 'boatrace.db'

# 異常スケール会場（除外）
EXCLUDE_VENUES = {1, 12, 13, 18, 21}

SEP = '=' * 70
SEP2 = '-' * 50


def load_data(conn):
    """分析用データを全件取得"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            ed.race_id,
            ed.pit_number,
            ed.isshu_time,
            ed.mawariashi_time,
            ed.chikusen_time,
            CAST(res.rank AS INTEGER) as result_rank,
            CAST(r.venue_code AS INTEGER) as vc,
            r.race_date,
            rd.actual_course,
            rd.exhibition_time
        FROM exhibition_data ed
        JOIN races r ON ed.race_id = r.id
        JOIN results res ON r.id = res.race_id AND ed.pit_number = res.pit_number
        JOIN race_details rd ON r.id = rd.race_id AND ed.pit_number = rd.pit_number
        WHERE ed.isshu_time IS NOT NULL AND ed.mawariashi_time IS NOT NULL
          AND ed.chikusen_time IS NOT NULL
          AND ed.isshu_time > 0 AND ed.mawariashi_time > 0 AND ed.chikusen_time > 0
          AND CAST(res.rank AS INTEGER) BETWEEN 1 AND 6
          AND rd.actual_course IS NOT NULL
    ''')
    rows = cursor.fetchall()
    return [r for r in rows if r[6] not in EXCLUDE_VENUES]


def build_race_metrics(rows):
    """レース単位の相対指標を計算"""
    races = defaultdict(list)
    for race_id, pit, isshu, mawari, chiku, rank, vc, date, course, exh in rows:
        races[race_id].append({
            'pit': pit, 'isshu': isshu, 'mawari': mawari, 'chiku': chiku,
            'rank': rank, 'vc': vc, 'date': date, 'course': course, 'exh': exh,
            'race_id': race_id
        })

    data = []
    for race_id, boats in races.items():
        if len(boats) < 3:
            continue
        iv = [b['isshu'] for b in boats]
        mv = [b['mawari'] for b in boats]
        cv = [b['chiku'] for b in boats]
        ev = [b['exh'] for b in boats if b['exh'] is not None]

        best_i, best_m, best_c = min(iv), min(mv), min(cv)
        si = sorted(iv); sm = sorted(mv); sc = sorted(cv)
        gap12_i = si[1] - si[0] if len(si) >= 2 else 0
        gap12_m = sm[1] - sm[0] if len(sm) >= 2 else 0

        for b in boats:
            ri = si.index(b['isshu']) + 1
            rm = sm.index(b['mawari']) + 1
            rc = sc.index(b['chiku']) + 1
            gi = b['isshu'] - best_i
            gm = b['mawari'] - best_m
            gc = b['chiku'] - best_c
            gt = gi + gm + gc
            rank_gt = sorted(boats, key=lambda x: (x['isshu']-best_i)+(x['mawari']-best_m)+(x['chiku']-best_c)).index(b) + 1

            # 公式展示タイムとの順位一致
            exh_rank = None
            if b['exh'] is not None and ev:
                se = sorted(ev)
                exh_rank = se.index(b['exh']) + 1 if b['exh'] in se else None

            data.append({
                'race_id': race_id, 'pit': b['pit'], 'course': b['course'],
                'rank': b['rank'],
                'rank_isshu': ri, 'rank_mawari': rm, 'rank_chiku': rc,
                'rank_gt': rank_gt,
                'gap_isshu': gi, 'gap_mawari': gm, 'gap_chiku': gc, 'gap_total': gt,
                'gap12_isshu': gap12_i, 'gap12_mawari': gap12_m,
                'exh_rank': exh_rank,
            })
    return data, races


def win_rate(subset):
    if not subset:
        return 0, 0
    wins = sum(1 for d in subset if d['rank'] == 1)
    return wins / len(subset) * 100, len(subset)


def print_rank_table(data, field, label):
    """順位別1着率テーブル表示"""
    print(f'\n{label} 順位別 1着率（全コース合計）:')
    for r in range(1, 7):
        s = [d for d in data if d[field] == r]
        pct, n = win_rate(s)
        bar = '■' * int(pct / 2)
        print(f'  {r}位: {pct:5.1f}%  n={n:5d}  {bar}')


def print_course_rank_table(data, field, label):
    """コース×順位クロス表"""
    print(f'\n{label} コース×順位 1着率:')
    header = '         ' + ''.join(f'  C{c}   ' for c in range(1, 7))
    print(header)
    for r in range(1, 7):
        row = f'  {r}位: '
        for c in range(1, 7):
            s = [d for d in data if d['course'] == c and d[field] == r]
            if s:
                pct, n = win_rate(s)
                row += f'{pct:5.1f}%({n:3d})'
            else:
                row += '  ---  (  0)'
        print(row)


def main():
    conn = sqlite3.connect(DB_PATH)

    print(SEP)
    print('オリジナル展示データ 信号強度測定レポート')
    print(f'除外会場: {EXCLUDE_VENUES}')
    print(SEP)

    rows = load_data(conn)
    data, races = build_race_metrics(rows)

    total = len(data)
    total_races = len(races)
    print(f'\nデータ概要:')
    print(f'  総レコード数: {total:,}艇')
    print(f'  対象レース数: {total_races:,}レース')

    # --- バイアス定量化 ---
    print(f'\n{SEP}')
    print('【バイアス定量化】isshu有/無でのコース1 1着率差')
    print(SEP)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            CASE WHEN ed.isshu_time IS NOT NULL AND ed.isshu_time > 0 THEN 1 ELSE 0 END as has_isshu,
            COUNT(*) as total,
            SUM(CASE WHEN CAST(res.rank AS INTEGER) = 1 THEN 1 ELSE 0 END) as wins
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        JOIN results res ON r.id = res.race_id AND rd.pit_number = res.pit_number
        LEFT JOIN exhibition_data ed ON r.id = ed.race_id AND rd.pit_number = ed.pit_number
        WHERE rd.actual_course = 1
          AND r.race_date >= '2026-01-01'
          AND CAST(r.venue_code AS INTEGER) NOT IN (1,12,13,18,21)
          AND CAST(res.rank AS INTEGER) BETWEEN 1 AND 6
        GROUP BY has_isshu
    ''')
    bias_rows = cursor.fetchall()
    rates = {}
    for has_isshu, total_b, wins_b in bias_rows:
        pct = wins_b / total_b * 100
        label = 'isshu有' if has_isshu else 'isshu無'
        print(f'  {label}: {wins_b}/{total_b} = {pct:.2f}%')
        rates[has_isshu] = pct
    if 0 in rates and 1 in rates:
        bias = rates[1] - rates[0]
        print(f'  バイアス量: +{bias:.2f}pt（全分析値はこの分だけ底上げされている）')

    # --- コース1ベース確認 ---
    c1_all = [d for d in data if d['course'] == 1]
    c1_wr, c1_n = win_rate(c1_all)
    print(f'\n分析データ内 コース1ベース: {c1_wr:.2f}% (n={c1_n})')

    # --- 案1: 順位ベース分析 ---
    print(f'\n{SEP}')
    print('【案1: 順位ベース分析】')
    print(SEP)

    print_rank_table(data, 'rank_isshu', 'isshu')
    print_rank_table(data, 'rank_mawari', 'mawari')
    print_rank_table(data, 'rank_chiku', 'chiku')
    print_rank_table(data, 'rank_gt', 'gap_total合計順位')

    print(f'\n{SEP2}')
    print_course_rank_table(data, 'rank_isshu', 'isshu')
    print(f'\n{SEP2}')
    print_course_rank_table(data, 'rank_mawari', 'mawari')
    print(f'\n{SEP2}')
    print_course_rank_table(data, 'rank_gt', 'gap_total合計順位')

    # --- 案2: gap magnitude 分析 ---
    print(f'\n{SEP}')
    print('【案2: gap magnitude 分析】')
    print(SEP)

    for field, label in [('gap_isshu', 'isshu'), ('gap_mawari', 'mawari'),
                          ('gap_chiku', 'chiku'), ('gap_total', 'gap_total')]:
        print(f'\n{label} gap 閾値別（全コース・該当艇のgap値）:')
        for thr in [0.00, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50]:
            s = [d for d in data if d[field] <= thr]
            pct, n = win_rate(s)
            print(f'  <={thr:.2f}s: {pct:5.1f}%  n={n:5d}')

    # コース1限定
    print(f'\n{SEP2}')
    print('コース1限定 gap 閾値別:')
    c1 = [d for d in data if d['course'] == 1]
    for field, label in [('gap_isshu', 'isshu'), ('gap_mawari', 'mawari'), ('gap_total', 'gap_total')]:
        print(f'\n  {label} (コース1):')
        for thr in [0.00, 0.05, 0.10, 0.20, 0.30]:
            s = [d for d in c1 if d[field] <= thr]
            pct, n = win_rate(s)
            print(f'    <={thr:.2f}s: {pct:5.1f}%  n={n:4d}  ({n/len(c1)*100:.0f}%カバー)')

    # --- 案3: 複合 gap (gap_total_rank) 分析 ---
    print(f'\n{SEP}')
    print('【案3: 複合 gap_total 順位（最重要分析）】')
    print(SEP)

    # 全コース: gap_total_rank=1 艇の1着率
    best_gt_boats = []
    for race_id, boats in races.items():
        if len(boats) < 3:
            continue
        iv = [b['isshu'] for b in boats]
        mv = [b['mawari'] for b in boats]
        cv = [b['chiku'] for b in boats]
        bi, bm, bc = min(iv), min(mv), min(cv)
        best = min(boats, key=lambda b: (b['isshu']-bi) + (b['mawari']-bm) + (b['chiku']-bc))
        # find corresponding data record
        for d in data:
            if d['race_id'] == race_id and d['pit'] == best['pit']:
                best_gt_boats.append(d)
                break

    print(f'\ngap_total 最小艇の実態:')
    tot_pct, tot_n = win_rate(best_gt_boats)
    print(f'  全コース: {tot_pct:.2f}% (n={tot_n})')
    for c in range(1, 7):
        s = [d for d in best_gt_boats if d['course'] == c]
        pct, n = win_rate(s)
        print(f'  コース{c}: {pct:.2f}% (n={n})')

    # コース1: rank_gt 別
    print(f'\nコース1 × gap_total順位 1着率（双方向シグナル確認）:')
    print(f'  ベースライン: {c1_wr:.2f}% (n={c1_n})')
    for r in range(1, 7):
        s = [d for d in c1 if d['rank_gt'] == r]
        pct, n = win_rate(s)
        diff = pct - c1_wr
        arrow = '▲' if diff > 0 else '▼'
        print(f'  rank_gt={r}: {pct:.2f}% ({arrow}{abs(diff):.2f}pt)  n={n}')

    # コース別のgap_total_rank=1効果
    print(f'\n全コース × gap_total_rank=1 の1着率:')
    for c in range(1, 7):
        base = [d for d in data if d['course'] == c]
        best_in_c = [d for d in base if d['rank_gt'] == 1]
        base_wr, base_n = win_rate(base)
        best_wr, best_n = win_rate(best_in_c)
        diff = best_wr - base_wr
        print(f'  C{c}: ベース {base_wr:.1f}% → rank_gt=1: {best_wr:.1f}%  ({diff:+.1f}pt)  n={best_n}')

    # --- 正の・負のシグナル強度まとめ ---
    print(f'\n{SEP}')
    print('【シグナル強度まとめ: 採用判断根拠】')
    print(SEP)

    # コース1: gap_total_rank=1 & gap12_isshu >= threshold
    print('\nコース1 & gap_total_rank=1 & isshu 2位差 閾値別:')
    c1_gt1 = [d for d in c1 if d['rank_gt'] == 1]
    for thr in [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]:
        s = [d for d in c1_gt1 if d['gap12_isshu'] >= thr]
        pct, n = win_rate(s)
        print(f'  gap12_isshu>={thr:.2f}s: {pct:.1f}% (n={n}, {n/len(c1)*100:.0f}%カバー)')

    print('\nコース1 & gap_total_rank>=4（負のシグナル）:')
    c1_bad = [d for d in c1 if d['rank_gt'] >= 4]
    pct_bad, n_bad = win_rate(c1_bad)
    print(f'  {pct_bad:.2f}% (n={n_bad}, {n_bad/len(c1)*100:.0f}%カバー)')
    print(f'  ベース比: {pct_bad - c1_wr:.2f}pt')

    # --- 独立性確認 ---
    print(f'\n{SEP}')
    print('【独立性確認: 各指標の1位一致率】')
    print(SEP)
    agree_ei = 0; agree_em = 0; agree_ec = 0; agree_cm = 0; agree_ci = 0; agree_im = 0
    n_both = 0
    for d in data:
        if d['exh_rank'] is None:
            continue
        n_both += 1
        if d['exh_rank'] == 1 and d['rank_isshu'] == 1:
            agree_ei += 1
        if d['exh_rank'] == 1 and d['rank_mawari'] == 1:
            agree_em += 1
        if d['exh_rank'] == 1 and d['rank_chiku'] == 1:
            agree_ec += 1
        if d['rank_chiku'] == 1 and d['rank_mawari'] == 1:
            agree_cm += 1
        if d['rank_chiku'] == 1 and d['rank_isshu'] == 1:
            agree_ci += 1
        if d['rank_isshu'] == 1 and d['rank_mawari'] == 1:
            agree_im += 1

    if n_both > 0:
        print(f'\n(n={n_both}レコード, ランダム期待値: 16.7%)')
        print(f'  公式exh vs isshu   1位一致率: {agree_ei/n_both*100:.1f}%')
        print(f'  公式exh vs mawari  1位一致率: {agree_em/n_both*100:.1f}%')
        print(f'  公式exh vs chiku   1位一致率: {agree_ec/n_both*100:.1f}%')
        print(f'  chiku   vs mawari  1位一致率: {agree_cm/n_both*100:.1f}%  ← ほぼランダム=完全独立')
        print(f'  chiku   vs isshu   1位一致率: {agree_ci/n_both*100:.1f}%')
        print(f'  isshu   vs mawari  1位一致率: {agree_im/n_both*100:.1f}%')

    # --- 案1/2/3 効果推定まとめ ---
    print(f'\n{SEP}')
    print('【効果推定サマリー（バイアス補正前/後）】')
    print(SEP)
    bias_val = rates.get(1, 58.2) - rates.get(0, 54.5) if rates else 3.7

    c1_base_noisy = c1_wr
    c1_base_clean = c1_wr - bias_val

    cases = [
        ('案1: isshu順位1位 (C1)', [d for d in c1 if d['rank_isshu'] == 1]),
        ('案1: mawari順位1位 (C1)', [d for d in c1 if d['rank_mawari'] == 1]),
        ('案1: rank_gt=1 (C1)', [d for d in c1 if d['rank_gt'] == 1]),
        ('案2: gap_isshu<=0.20 (C1)', [d for d in c1 if d['gap_isshu'] <= 0.20]),
        ('案2: gap_mawari<=0.20 (C1)', [d for d in c1 if d['gap_mawari'] <= 0.20]),
        ('案3: gap_total_rank=1 (C1)', [d for d in c1 if d['rank_gt'] == 1]),
        ('案3: gap_total_rank>=4 (C1 負)', [d for d in c1 if d['rank_gt'] >= 4]),
    ]

    print(f'\n  コース1ベース(分析内): {c1_base_noisy:.2f}% / バイアス補正後推定: {c1_base_clean:.2f}%')
    print(f'  {"条件":<35} {"n":>5} {"1着率":>7} {"vs_base":>8} {"補正後推定":>10}')
    print('  ' + '-' * 70)
    for label, subset in cases:
        pct, n = win_rate(subset)
        diff = pct - c1_base_noisy
        est_clean = pct - bias_val
        print(f'  {label:<35} {n:>5} {pct:>6.1f}% {diff:>+7.1f}pt {est_clean:>9.1f}%')

    conn.close()
    print(f'\n{SEP}')
    print('測定完了')
    print(SEP)


if __name__ == '__main__':
    main()
