# オリジナル展示収集 UI連携ガイド

## 概要

UIからオリジナル展示データを収集するためのスクリプトとその使用方法を説明します。

---

## ⚠️ 重要: データ利用可能期間について

**オリジナル展示データは「昨日」と「今日」のみ公開されています。**

### データの特性
1. **過去データは取得不可**: 2日前以前のデータは自動的に削除される
2. **日次収集が必須**: データが毎日削除されるため、自動化が必要
3. **全会場が公開しているわけではない**: 約9/24会場のみ公開

### UIでの推奨実装
- 日付選択UIでは「昨日」「今日」のみ選択可能にする
- 過去日付を指定された場合は警告メッセージを表示する
- 自動収集（毎日20:00実行）をセットアップする

**参考ドキュメント**: [DAILY_COLLECTION_SETUP.md](DAILY_COLLECTION_SETUP.md)

---

## 推奨スクリプト

### UI実行向け: `収集_オリジナル展示_日付指定.py`

**特徴:**
- 日付を直接指定（YYYY-MM-DD形式）
- race_detailsが不足している場合は自動で高速版を使って作成
- 戻り値としてJSON互換のdictを返すため、UI側で結果を処理しやすい
- 日付範囲の指定も可能（ただし昨日〜今日のみ推奨）
- 2日前以前の日付には自動的に警告を表示

**基本的な使い方:**

```bash
# 1日分を収集（昨日または今日を推奨）
python 収集_オリジナル展示_日付指定.py 2025-11-18

# 複数日を収集（昨日〜今日を推奨）
python 収集_オリジナル展示_日付指定.py 2025-11-17 2025-11-18

# 注意: 2日前以前のデータは取得できない可能性が高い
python 収集_オリジナル展示_日付指定.py 2025-11-01  # ← 警告表示、データなしの可能性
```

**戻り値の構造:**

```python
{
    'status': 'completed',  # または 'no_races'
    'date': '2025-11-18',
    'success': 43,          # 成功したレース数
    'no_data': 12,          # データが取得できなかったレース数
    'not_found': 0,         # 404エラーのレース数
    'timeout': 0,           # タイムアウトのレース数
    'error': 0              # その他エラーのレース数
}
```

### Python コードから呼び出す場合

```python
import subprocess
import json

# スクリプトを実行
result = subprocess.run(
    ["python", "収集_オリジナル展示_日付指定.py", "2025-11-18"],
    capture_output=True,
    text=True,
    encoding='utf-8'
)

# 結果を確認
if result.returncode == 0:
    print("収集成功")
    # 標準出力から結果をパース（必要に応じて）
else:
    print(f"収集失敗: {result.stderr}")
```

## 処理フロー

```
1. 指定日のracesテーブルを確認
   ↓
   【racesが存在しない場合】
   → 'no_races'ステータスを返して終了

   【racesが存在する場合】
   ↓
2. race_detailsの存在を確認
   ↓
   【race_detailsが0件の場合】
   → 自動で「補完_race_details_INSERT対応_高速版.py」を実行
   → race_detailsを作成（約1.5分で完了）

   【race_detailsが存在する場合】
   ↓
3. オリジナル展示データをスクレイピング
   ↓
4. race_detailsテーブルに保存
   ↓
5. 結果をコンソールに出力して終了
```

## 必要な前提条件

1. **racesテーブルにデータが存在すること**
   - オリジナル展示収集より前に、レース基本データが収集されている必要があります
   - もし未収集の場合は、先に `fetch_historical_data.py` を実行してください

2. **データベースファイル**
   - `data/boatrace.db` が存在すること

3. **依存パッケージ**
   - selenium
   - BeautifulSoup4
   - tqdm
   - requests

## 処理時間の目安

- **1日分（約12場×12R = 144レース）**: 約10分
- **race_details作成が必要な場合**: 追加で約1.5分
- **1レースあたり**: 約4-5秒

## エラーハンドリング

### よくあるエラーとUI側での対処

#### 0. 日付が古すぎる（2日前以前）

**発生条件**: 2日前以前の日付を指定した場合
**スクリプトの動作**: 警告を表示して処理を続行するが、ほとんどのレースでデータが取得できない
**返却値の例**:
```python
{
    'status': 'completed',
    'date': '2025-11-01',
    'success': 0,
    'no_data': 129,
    'not_found': 0,
    'timeout': 0,
    'error': 0
}
```

**UI側での対処例**:
```python
# 成功数が0でno_dataが多い場合
if result['success'] == 0 and result['no_data'] > 50:
    st.warning(f"{target_date} のオリジナル展示データは既に削除されています。")
    st.info("オリジナル展示データは「昨日」と「今日」のみ利用可能です。")
    st.info("データを蓄積するには、毎日20:00に自動収集を実行してください。")
```

#### 1. `'no_races'` ステータス

```python
if result['status'] == 'no_races':
    # UI側でメッセージ表示
    print("指定日のレースデータがありません")
    print("レース基本データを先に収集してください")
```

#### 2. race_details作成の失敗

スクリプト内で自動的に処理されますが、失敗した場合でもオリジナル展示収集は続行されます（WARNINGメッセージが表示されます）。

#### 3. タイムアウトエラー

一部のレースでタイムアウトが発生しても、他のレースの処理は続行されます。最終的な成功率を確認してください。

## UI側での実装例

### シンプルな実装

```python
import subprocess
from datetime import datetime

def collect_original_tenji_ui(date_str):
    """
    UIからオリジナル展示を収集

    Args:
        date_str: 日付文字列 (YYYY-MM-DD)

    Returns:
        dict: 収集結果
    """
    try:
        result = subprocess.run(
            ["python", "収集_オリジナル展示_日付指定.py", date_str],
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=1800  # 30分でタイムアウト
        )

        if result.returncode == 0:
            return {
                'success': True,
                'message': '収集完了',
                'output': result.stdout
            }
        else:
            return {
                'success': False,
                'message': 'エラーが発生しました',
                'error': result.stderr
            }

    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'message': 'タイムアウト（30分以上）',
            'error': 'プロセスがタイムアウトしました'
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'予期しないエラー: {str(e)}',
            'error': str(e)
        }
```

### プログレスバー付き実装（バックグラウンド実行）

```python
import subprocess
import threading
import time

def collect_with_progress(date_str, progress_callback):
    """
    プログレスバー付きで収集

    Args:
        date_str: 日付文字列
        progress_callback: 進捗を受け取るコールバック関数
    """
    process = subprocess.Popen(
        ["python", "収集_オリジナル展示_日付指定.py", date_str],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8'
    )

    # 進捗監視スレッド
    def monitor_progress():
        for line in process.stdout:
            # tqdmの出力から進捗を抽出
            if '%|' in line:
                # プログレスバーの文字列をパース
                progress_callback(line)
            print(line, end='')

    thread = threading.Thread(target=monitor_progress)
    thread.start()

    # 完了を待つ
    process.wait()
    thread.join()

    return process.returncode == 0
```

## トラブルシューティング

### Q0: 過去のデータが取得できない

**原因**: オリジナル展示データは「昨日」と「今日」のみ公開されており、2日前以前のデータは自動的に削除される

**対処**:
- UIで「昨日」「今日」のみ選択可能にする
- 過去のデータは取得不可である旨をユーザーに通知
- 毎日自動収集（20:00実行）をセットアップして日次でデータを蓄積
- 詳細は[DAILY_COLLECTION_SETUP.md](DAILY_COLLECTION_SETUP.md)を参照

### Q1: スクリプトが見つからない

**A:** スクリプトはプロジェクトのルートディレクトリに配置されています。
- `収集_オリジナル展示_日付指定.py`
- `補完_race_details_INSERT対応_高速版.py`

### Q2: race_detailsの自動作成が失敗する

**A:** 手動で先に作成してください：
```bash
python 補完_race_details_INSERT対応_高速版.py 2025-11-18 2025-11-18
```

### Q3: 特定の会場だけ失敗する

**A:** 会場によって公開状況が異なります。約9/24会場のみがオリジナル展示データを公開しています。404エラーやタイムアウトは正常な範囲内です。

### Q4: 処理が遅い

**A:**
- レート制限のため、1レースあたり1秒のスリープを入れています
- SeleniumでブラウザをヘッドレスモードIで起動しているため、ある程度の時間がかかります
- これは公式サイトへの負荷を抑えるための措置です

## その他のスクリプト

### `収集_オリジナル展示_手動実行.py`（従来版）

**用途:** コマンドラインから相対日付で実行する場合

```bash
# 昨日
python 収集_オリジナル展示_手動実行.py -1

# 今日
python 収集_オリジナル展示_手動実行.py 0

# 明日
python 収集_オリジナル展示_手動実行.py 1
```

**特徴:**
- 改善版: race_detailsが不足している場合、自動でfetch_historical_data.pyと高速版を実行
- 依存チェック機能付き

## まとめ

- **UI実行には `収集_オリジナル展示_日付指定.py` を推奨**
- 日付を直接指定できてわかりやすい
- race_detailsの自動作成機能付き
- JSON互換のdictを返すため、結果処理が容易
- エラーハンドリングが充実
- **重要**: データは「昨日」と「今日」のみ利用可能。日次自動収集の設定を推奨
