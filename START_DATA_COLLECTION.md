# 安全版データ取得 - 実行ガイド

## ✅ 準備完了！

安全性を高めたデータ取得スクリプトが完成しました。

### 実装済み安全対策
1. ✅ **User-Agentランダム化** - 6種類のブラウザからランダム選択
2. ✅ **アクセス間隔ランダム化** - 2-5秒のランダム待機
3. ✅ **429エラー対応** - レート制限時の自動待機・リトライ
4. ✅ **503エラー対応** - サーバービジー時の段階的待機
5. ✅ **タイムアウト処理** - 3回までの自動リトライ
6. ✅ **詳細な進捗表示** - リアルタイム進捗・速度表示

---

## 実行方法

### パターン1: 全期間フル実行（推奨）

```bash
# バックグラウンドで実行
venv\Scripts\python.exe fetch_historical_data_safe.py --start 2024-01-01 --end 2024-12-31 > historical_log.txt 2>&1 &

# ログ監視
powershell -Command "Get-Content historical_log.txt -Wait -Tail 20"
```

**推定所要時間**: 20-30時間
**推定取得レース数**: 約50,000-80,000レース

### パターン2: 期間分割実行（より安全）

```bash
# 2024年1-3月
venv\Scripts\python.exe fetch_historical_data_safe.py --start 2024-01-01 --end 2024-03-31 > log_Q1.txt 2>&1 &

# 翌日: 2024年4-6月
venv\Scripts\python.exe fetch_historical_data_safe.py --start 2024-04-01 --end 2024-06-30 > log_Q2.txt 2>&1 &

# 以下同様...
```

### パターン3: 特定競艇場のみ

```bash
# 住之江と蒲郡のみ
venv\Scripts\python.exe fetch_historical_data_safe.py --start 2024-01-01 --end 2024-12-31 --venues 12 07 > log_selected.txt 2>&1 &
```

### パターン4: 待機時間をカスタマイズ

```bash
# より慎重に（3-8秒待機）
venv\Scripts\python.exe fetch_historical_data_safe.py --start 2024-01-01 --end 2024-12-31 --min-delay 3.0 --max-delay 8.0 > log_slow.txt 2>&1 &

# より高速に（1-3秒待機、リスク高）
venv\Scripts\python.exe fetch_historical_data_safe.py --start 2024-01-01 --end 2024-12-31 --min-delay 1.0 --max-delay 3.0 > log_fast.txt 2>&1 &
```

---

## コマンドライン引数

| 引数 | デフォルト | 説明 |
|-----|-----------|------|
| `--start` | 2024-01-01 | 開始日（YYYY-MM-DD） |
| `--end` | 2024-12-31 | 終了日（YYYY-MM-DD） |
| `--venues` | 全24場 | 対象競艇場コード（スペース区切り） |
| `--min-delay` | 2.0 | 最小待機時間（秒） |
| `--max-delay` | 5.0 | 最大待機時間（秒） |

---

## 進捗確認

### リアルタイムでログを見る
```bash
powershell -Command "Get-Content historical_log.txt -Wait -Tail 20"
```

### データベースの状況確認
```bash
venv\Scripts\python.exe check_db_status.py
```

### データ品質レポート生成
```bash
venv\Scripts\python.exe generate_data_quality_report.py
```

---

## 進捗表示の見方

```
[1/24]
====================================================================================================
住之江（12）
====================================================================================================

  2024-01-03 ............
  2024-01-04 ............
  2024-01-05 ............

  完了: 成功=36, 失敗=0, スキップ=0

  【進捗】 試行:36 成功:36(100.0%) 失敗:0 スキップ:0 | 経過:0:02:15 速度:16.0レース/分
```

**記号の意味**:
- `.` = 成功
- `F` = 失敗
- `-` = スキップ（開催なし）

---

## 推定実行時間・データ量

### 全期間（2024年1-12月）
- **対象日数**: 366日
- **推定開催日**: 約180日/場
- **推定レース数**: 50,000-80,000レース
- **推定アクセス数**: 150,000-240,000回
- **推定所要時間**: 20-30時間

### 1ヶ月分
- **推定レース数**: 4,000-7,000レース
- **推定所要時間**: 2-3時間

### 1週間分
- **推定レース数**: 1,000-1,500レース
- **推定所要時間**: 30-45分

---

## リスク評価

### 現在の設定（デフォルト）
| 項目 | 設定 | リスクレベル |
|-----|------|------------|
| User-Agent | ランダム化（6種類） | ✅ 低 |
| アクセス間隔 | 2-5秒ランダム | ✅ 低 |
| リトライ | 3回まで自動 | ✅ 低 |
| エラー対応 | 429/503対応済み | ✅ 低 |
| **総合リスク** | | **✅ 低** |

### より安全な設定
```bash
# 3-8秒待機
venv\Scripts\python.exe fetch_historical_data_safe.py --min-delay 3.0 --max-delay 8.0
```

---

## トラブルシューティング

### エラー: Too Many Requests (429)
- **対応**: 自動的に待機してリトライします
- **手動対応**: より長い待機時間に変更（`--min-delay 5.0 --max-delay 10.0`）

### エラー: Service Unavailable (503)
- **対応**: 自動的に段階的に待機時間を増やしてリトライします
- **手動対応**: しばらく時間をおいて再実行

### データが取得できない
- **確認事項**:
  1. インターネット接続
  2. 日付が正しいか（過去の日付）
  3. 競艇場コードが正しいか

### 進捗が止まっている
- ログを確認して最後のメッセージを見る
- エラーログがあればそれに対応

---

## 実行例

### 例1: まずは1週間分でテスト
```bash
venv\Scripts\python.exe fetch_historical_data_safe.py --start 2024-12-01 --end 2024-12-07 > log_test.txt 2>&1 &
```

### 例2: 問題なければ全期間実行
```bash
venv\Scripts\python.exe fetch_historical_data_safe.py --start 2024-01-01 --end 2024-12-31 > log_full.txt 2>&1 &
```

### 例3: 夜間に実行開始（翌朝確認）
```bash
# 就寝前に実行開始
venv\Scripts\python.exe fetch_historical_data_safe.py > log_overnight.txt 2>&1 &

# 翌朝確認
venv\Scripts\python.exe check_db_status.py
```

---

## 推奨実行プラン

### プラン A: 一気に取得（推奨）
```bash
venv\Scripts\python.exe fetch_historical_data_safe.py --start 2024-01-01 --end 2024-12-31 > historical_log.txt 2>&1 &
```
- PCをつけたまま20-30時間
- 最も効率的

### プラン B: 分割実行（より安全）
```bash
# Day 1: Q1 (1-3月)
venv\Scripts\python.exe fetch_historical_data_safe.py --start 2024-01-01 --end 2024-03-31 > log_Q1.txt 2>&1 &

# Day 2: Q2 (4-6月)
venv\Scripts\python.exe fetch_historical_data_safe.py --start 2024-04-01 --end 2024-06-30 > log_Q2.txt 2>&1 &

# Day 3: Q3 (7-9月)
venv\Scripts\python.exe fetch_historical_data_safe.py --start 2024-07-01 --end 2024-09-30 > log_Q3.txt 2>&1 &

# Day 4: Q4 (10-12月)
venv\Scripts\python.exe fetch_historical_data_safe.py --start 2024-10-01 --end 2024-12-31 > log_Q4.txt 2>&1 &
```
- 4日に分けて実行
- 各日5-8時間
- リスク最小化

---

## 次のステップ

1. **データ取得開始**
   ```bash
   venv\Scripts\python.exe fetch_historical_data_safe.py > historical_log.txt 2>&1 &
   ```

2. **進捗監視**（別のターミナル/コマンドプロンプトで）
   ```bash
   powershell -Command "Get-Content historical_log.txt -Wait -Tail 20"
   ```

3. **完了後の確認**
   ```bash
   venv\Scripts\python.exe check_db_status.py
   venv\Scripts\python.exe generate_data_quality_report.py
   ```

4. **バックテスト開始**
   データが100レース以上揃ったら予想精度検証

---

**準備完了です！実行を開始してください！**
