# UI統合ガイド - レース情報取得ボタン

## 概要

[fetch_all_data_comprehensive.py](fetch_all_data_comprehensive.py)をStreamlit UIに統合し、「レース情報取得」ボタンを実装するガイドです。

---

## 実装方法

### 1. ui/app.pyへのボタン追加例

```python
import streamlit as st
import subprocess
import sqlite3
from datetime import datetime, timedelta
import threading

# データベースから最終保存日を取得
def get_last_saved_date():
    try:
        conn = sqlite3.connect('data/boatrace.db')
        cursor = conn.cursor()
        cursor.execute('SELECT MAX(race_date) FROM races')
        result = cursor.fetchone()
        conn.close()

        if result and result[0]:
            return result[0]
        else:
            return (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    except Exception as e:
        st.error(f"最終保存日取得エラー: {e}")
        return (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

# バックグラウンドでデータ取得を実行
def fetch_data_background(start_date, end_date, workers=3):
    """
    バックグラウンドでデータ取得スクリプトを実行
    """
    cmd = [
        'python',
        'fetch_all_data_comprehensive.py',
        '--start', start_date,
        '--end', end_date,
        '--workers', str(workers)
    ]

    try:
        # サブプロセスとして実行（非同期）
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # プロセスIDをセッションステートに保存
        return process
    except Exception as e:
        st.error(f"データ取得開始エラー: {e}")
        return None

# Streamlitアプリに追加するセクション
def render_data_fetch_section():
    """
    データ取得セクションを描画
    """
    st.header("レース情報取得")

    # 最終保存日を表示
    last_date = get_last_saved_date()
    st.info(f"最終保存日: {last_date}")

    # 取得日付範囲を選択
    col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input(
            "開始日",
            value=datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=1),
            max_value=datetime.now()
        )

    with col2:
        end_date = st.date_input(
            "終了日",
            value=datetime.now(),
            max_value=datetime.now()
        )

    # 並列ワーカー数
    workers = st.slider("並列ワーカー数", min_value=1, max_value=10, value=3)

    # オプション
    col1, col2 = st.columns(2)
    with col1:
        skip_original_tenji = st.checkbox("オリジナル展示をスキップ", value=False)
    with col2:
        skip_tide = st.checkbox("潮位データをスキップ", value=False)

    # ボタン
    if st.button("レース情報取得", type="primary"):
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')

        # 確認メッセージ
        st.info(f"データ取得を開始します: {start_str} ～ {end_str}")

        # コマンド構築
        cmd = [
            'python',
            'fetch_all_data_comprehensive.py',
            '--start', start_str,
            '--end', end_str,
            '--workers', str(workers)
        ]

        if skip_original_tenji:
            cmd.append('--skip-original-tenji')
        if skip_tide:
            cmd.append('--skip-tide')

        # 実行
        with st.spinner('データ取得中...'):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1時間タイムアウト
                )

                if result.returncode == 0:
                    st.success("データ取得完了！")
                    st.text(result.stdout)
                else:
                    st.error("データ取得エラー")
                    st.text(result.stderr)
            except subprocess.TimeoutExpired:
                st.error("データ取得がタイムアウトしました")
            except Exception as e:
                st.error(f"エラー: {e}")

    # 取得状況表示
    st.subheader("取得予定データ")
    st.markdown("""
    - レース結果（公式）
    - 展示タイム・チルト角・部品交換（公式）
    - STタイム・進入コース（公式）
    - オリジナル展示データ（公式・Selenium）
    - 潮位データ（気象庁・Selenium）
    - 天気データ（公式）
    - 払戻金（公式）
    - 決まり手（公式）
    """)

# メインアプリに統合
# ui/app.pyのメイン処理に以下を追加:

# サイドバーにデータ取得セクションを追加
with st.sidebar:
    st.title("データ管理")

    # データ取得セクション
    with st.expander("レース情報取得", expanded=False):
        render_data_fetch_section()
```

---

## 使用方法

### 1. コマンドラインから直接実行

```bash
# デフォルト: DBの最終保存日から当日まで
python fetch_all_data_comprehensive.py

# 日付範囲を明示的に指定
python fetch_all_data_comprehensive.py --start 2025-11-05 --end 2025-11-12

# 並列数を変更
python fetch_all_data_comprehensive.py --start 2025-11-05 --end 2025-11-12 --workers 5

# テストモード（DB保存なし）
python fetch_all_data_comprehensive.py --test --limit 10

# オリジナル展示・潮位をスキップ（高速化）
python fetch_all_data_comprehensive.py --skip-original-tenji --skip-tide
```

### 2. UIから実行

1. Streamlitアプリを起動
```bash
streamlit run ui/app.py
```

2. サイドバーの「レース情報取得」セクションを開く

3. 日付範囲を選択

4. 「レース情報取得」ボタンをクリック

5. 進捗状況を確認

---

## 取得データ詳細

### 公式サイトから取得（HTTP）

1. **レース結果**
   - 着順
   - タイム
   - 決まり手

2. **展示タイム**
   - 展示航走タイム
   - チルト角
   - 部品交換情報

3. **STタイム**
   - 6艇のスタートタイミング
   - F（フライング）・L（遅れ）ステータス

4. **進入コース**
   - 実際の進入コース（1-6）

5. **天気データ**
   - 気温
   - 風速・風向
   - 天候

6. **払戻金**
   - 3連単
   - 3連複
   - 2連単
   - 2連複
   - 拡連複
   - 単勝・複勝

### Seleniumで取得（ブラウザ自動化）

7. **オリジナル展示データ**（公式サイト）
   - 直線タイム
   - 一周タイム
   - まわり足タイム

8. **潮位データ**（気象庁）
   - 満潮・干潮時刻
   - 潮位レベル（海水場のみ）

---

## パフォーマンス

### 処理速度

- **並列ワーカー数3**: 約20レース/分
- **並列ワーカー数5**: 約30レース/分
- **並列ワーカー数10**: 約50レース/分

### 推定実行時間

| 日数 | レース数 | 並列3 | 並列5 | 並列10 |
|-----|---------|------|------|-------|
| 1日 | 約120 | 6分 | 4分 | 2.4分 |
| 1週間 | 約840 | 42分 | 28分 | 17分 |
| 1ヶ月 | 約3,600 | 3時間 | 2時間 | 1.2時間 |

※オリジナル展示・潮位データを含む場合は約1.5倍の時間

---

## エラーハンドリング

### 一般的なエラー

1. **レース中止**
   - メッセージ: "No race card"
   - 対処: 自動スキップ（エラーとしてカウントしない）

2. **データ不在**
   - メッセージ: "データ取得失敗"
   - 対処: 自動スキップ

3. **ネットワークエラー**
   - メッセージ: "Connection timeout"
   - 対処: 自動リトライ（3回まで）

4. **データベースロック**
   - メッセージ: "Database is locked"
   - 対処: 自動リトライ（待機時間付き）

---

## 注意事項

### 1. レート制限

- 公式サイトへの負荷を考慮
- 各スクレイパーに0.3秒のディレイ設定済み
- 並列ワーカー数は10以下推奨

### 2. Seleniumブラウザ

- オリジナル展示・潮位データ取得時にChromeブラウザを使用
- ヘッドレスモードで動作（画面表示なし）
- ChromeDriverは自動インストール

### 3. メモリ使用量

- 並列ワーカー数が多いほどメモリ使用量増加
- 推奨: 4GB以上のRAM

### 4. 実行時間

- 長期間のデータ取得は時間がかかる
- バックグラウンド実行推奨
- Ctrl+Cで中断可能（安全に停止）

---

## トラブルシューティング

### Q: データ取得が遅い

**A**: 以下を試してください:
- 並列ワーカー数を増やす（`--workers 5`）
- オリジナル展示・潮位をスキップ（`--skip-original-tenji --skip-tide`）

### Q: "Database is locked" エラー

**A**: 以下を確認してください:
- 他のプロセスがDBを使用していないか
- Streamlitアプリを一時停止
- しばらく待ってから再実行

### Q: Selenium関連のエラー

**A**: ChromeDriverを再インストール:
```bash
pip uninstall selenium
pip install selenium webdriver-manager
```

### Q: メモリ不足エラー

**A**: 並列ワーカー数を減らす:
```bash
python fetch_all_data_comprehensive.py --workers 2
```

---

## 今後の拡張案

### 1. 定期実行設定

Windows Task Schedulerで毎日自動実行:
```bash
# バッチファイル: daily_fetch.bat
cd C:\Users\seizo\Desktop\BoatRace
python fetch_all_data_comprehensive.py
```

### 2. 通知機能

- 完了時にメール通知
- Slack通知
- LINE通知

### 3. 進捗可視化

- Streamlitリアルタイム進捗バー
- 取得済みレース数の表示
- エラー詳細の表示

### 4. データ検証機能

- 取得データの整合性チェック
- 欠損データの検出
- 異常値の検出

---

## まとめ

`fetch_all_data_comprehensive.py`は、全データ種類を包括的に取得できるスクリプトです。

### 主な特徴

- DBの最終保存日から自動取得
- 8種類のデータを一括取得
- 並列処理で高速化
- エラーハンドリング完備
- UI統合可能

### 実行手順

1. コマンドライン実行またはUI統合
2. 日付範囲を指定（デフォルトは最終保存日～当日）
3. 並列ワーカー数を選択
4. 実行して完了を待つ

これにより、データ取得作業が大幅に効率化されます。

---

**作成日**: 2025年11月13日
**対応スクリプト**: fetch_all_data_comprehensive.py
**対応UI**: ui/app.py（Streamlit）
