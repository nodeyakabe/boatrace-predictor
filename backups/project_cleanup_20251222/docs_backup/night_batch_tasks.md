# 夜間バッチ作業リスト

**目的**: データ収集・分析を夜間に自動実行して、朝には結果が出ている状態にする

---

## 🌙 夜間作業の分類

### A. データ収集系（時間がかかる）
- バックグラウンド実行推奨
- 完了まで数時間かかる可能性

### B. 分析系（中程度）
- データ収集完了後に実行
- 30分～2時間程度

### C. レポート生成系（短時間）
- 分析完了後に実行
- 5～15分程度

---

## 📋 具体的な夜間タスク一覧

### 【優先度A】即座に実行すべきタスク

#### 1. 全期間データ収集（進行中）
**タスク**: 2025年全レース予測再生成
**スクリプト**: `scripts/regenerate_predictions_2025_parallel.py`
**実行コマンド**:
```bash
# 既に実行中（バックグラウンドID: b0b8be）
# 進捗: 189/365日完了、残り約2.3時間
```
**完了条件**: 365/365日完了
**完了後の出力**: `data/boatrace.db`に全予測データが格納

---

### 【優先度B】データ収集完了後に自動実行

#### 2. 全期間信頼度B検証
**タスク**: 1-12月の全データで三連単的中率検証
**スクリプト**: `scripts/validate_confidence_b_trifecta.py`
**実行コマンド**:
```bash
python scripts/validate_confidence_b_trifecta.py --start 2025-01-01 --end 2025-12-31
```
**所要時間**: 約5分
**期待される結果**:
- 三連単的中率（全期間）
- 信頼度A vs B比較
- 統計的有意性検定
- 本番適用判定

**成功基準**:
- 三連単的中率 ≥ 5.0%
- 信頼度Aとの差 ≥ -2.0pt

---

#### 3. 季節変動分析
**タスク**: 月別・四半期別の的中率推移を分析
**スクリプト**: 新規作成が必要 `scripts/analyze_seasonal_trends.py`
**実行コマンド**:
```bash
python scripts/analyze_seasonal_trends.py --confidence B
```
**所要時間**: 約10分

**分析内容**:
- 月別三連単的中率（1月～12月）
- 四半期別比較（Q1～Q4）
- 気温・水温との相関分析（可能なら）
- グラフ生成（matplotlib）

**出力**:
- CSVレポート: `output/seasonal_trends_B.csv`
- グラフ: `output/seasonal_trends_B.png`

---

#### 4. 会場別・条件別詳細分析
**タスク**: 会場・天候・風速などの条件別に的中率を分析
**スクリプト**: 新規作成が必要 `scripts/analyze_conditions.py`
**実行コマンド**:
```bash
python scripts/analyze_conditions.py --confidence B
```
**所要時間**: 約15分

**分析内容**:
- 会場別三連単的中率（24会場）
- 天候別（晴れ・曇り・雨）
- 風速別（0-2m, 3-5m, 6m以上）
- 波高別（データがあれば）
- グレード別（SG, G1, G2, G3, 一般）

**出力**:
- CSVレポート: `output/condition_analysis_B.csv`
- 会場別ヒートマップ: `output/venue_heatmap_B.png`

---

#### 5. 信頼度B細分化検証
**タスク**: B+（70-74点）とB（65-69点）の性能差を検証
**スクリプト**: 新規作成が必要 `scripts/validate_confidence_b_split.py`
**実行コマンド**:
```bash
python scripts/validate_confidence_b_split.py --threshold 70
```
**所要時間**: 約5分

**分析内容**:
- B+（70-74点）の三連単的中率
- B（65-69点）の三連単的中率
- 統計的有意差検定
- 細分化の推奨可否判定

**出力**:
- テキストレポート（標準出力）
- `docs/confidence_b_split_report.md`

---

### 【優先度C】分析完了後の追加タスク

#### 6. 信頼度B専用買い目抽出戦略設計
**タスク**: 戦略C（信頼度C/D）と同様の買い目抽出ロジック設計
**スクリプト**: 新規作成 `scripts/design_strategy_b.py`
**実行コマンド**:
```bash
python scripts/design_strategy_b.py
```
**所要時間**: 約30分（バックテスト含む）

**設計内容**:
1. **最小三連単確率閾値**の決定
   - 現在の戦略C: 確率 > median（中央値以上）
   - 信頼度B用: 確率 > percentile(X)（要検証）

2. **オッズ範囲の最適化**
   - 現在の戦略C: 10倍～70倍
   - 信頼度B用: Y倍～Z倍（要検証）

3. **期待値(EV)フィルター**
   - EV > 1.0（確定）
   - 最小EV閾値の調整（1.1? 1.2?）

4. **買い目数の制限**
   - 1レースあたり最大N点（要検証）

**出力**:
- 推奨パラメータ: `config/strategy_b_params.json`
- バックテスト結果: `output/strategy_b_backtest.csv`
- 設計書: `docs/strategy_b_design.md`

---

#### 7. 2024年データでのバックテスト
**タスク**: 2024年実績データで信頼度B戦略の回収率検証
**スクリプト**: 既存スクリプトの拡張 `scripts/backtest_strategy.py`
**実行コマンド**:
```bash
python scripts/backtest_strategy.py --confidence B --year 2024 --strategy new
```
**所要時間**: 約20分

**検証内容**:
- 的中率
- 回収率
- 最大ドローダウン
- シャープレシオ
- 月別収益推移

**出力**:
- バックテスト結果: `output/backtest_2024_B.csv`
- グラフ: `output/backtest_2024_B_chart.png`

---

#### 8. オッズデータ収集（翌日分）
**タスク**: 明日のレースのオッズデータを事前収集
**スクリプト**: 既存 `scripts/scrape_odds.py`（あれば）
**実行コマンド**:
```bash
python scripts/scrape_odds.py --date tomorrow
```
**所要時間**: 約15分

**収集内容**:
- 三連単オッズ（全買い目）
- 単勝・複勝オッズ
- オッズ更新時刻

**出力**:
- `data/odds/YYYY-MM-DD.json`

---

## 🔄 夜間バッチスクリプトの作成

### マスタースクリプト: `scripts/night_batch.sh`

```bash
#!/bin/bash

LOG_DIR="logs/night_batch"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "========================================" | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
echo "夜間バッチ開始: $(date)" | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
echo "========================================" | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"

# 1. データ収集完了待機（最大4時間）
echo "[1/8] データ収集完了を待機中..." | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
WAIT_COUNT=0
MAX_WAIT=240  # 4時間（1分×240）

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    # 365日完了をチェック（実装は要調整）
    COMPLETED=$(sqlite3 data/boatrace.db "SELECT COUNT(DISTINCT race_date) FROM race_predictions WHERE generated_at >= '2025-12-10'")

    if [ "$COMPLETED" -ge 365 ]; then
        echo "データ収集完了！" | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
        break
    fi

    sleep 60  # 1分待機
    WAIT_COUNT=$((WAIT_COUNT + 1))
done

if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
    echo "タイムアウト: データ収集が完了しませんでした" | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
    exit 1
fi

# 2. 全期間検証
echo "[2/8] 全期間信頼度B検証..." | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
python scripts/validate_confidence_b_trifecta.py --start 2025-01-01 --end 2025-12-31 2>&1 | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"

# 3. 季節変動分析
echo "[3/8] 季節変動分析..." | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
python scripts/analyze_seasonal_trends.py --confidence B 2>&1 | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"

# 4. 会場別分析
echo "[4/8] 会場別・条件別分析..." | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
python scripts/analyze_conditions.py --confidence B 2>&1 | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"

# 5. 信頼度B細分化検証
echo "[5/8] 信頼度B細分化検証..." | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
python scripts/validate_confidence_b_split.py --threshold 70 2>&1 | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"

# 6. 買い目戦略設計
echo "[6/8] 信頼度B買い目戦略設計..." | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
python scripts/design_strategy_b.py 2>&1 | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"

# 7. 2024年バックテスト
echo "[7/8] 2024年バックテスト..." | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
python scripts/backtest_strategy.py --confidence B --year 2024 --strategy new 2>&1 | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"

# 8. 翌日オッズ収集（オプション）
echo "[8/8] 翌日オッズ収集..." | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
python scripts/scrape_odds.py --date tomorrow 2>&1 | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"

echo "========================================" | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
echo "夜間バッチ完了: $(date)" | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
echo "========================================" | tee -a "$LOG_DIR/batch_$TIMESTAMP.log"
echo "ログファイル: $LOG_DIR/batch_$TIMESTAMP.log"
```

### Windowsバッチ版: `scripts/night_batch.bat`

```batch
@echo off
setlocal enabledelayedexpansion

set LOG_DIR=logs\night_batch
mkdir "%LOG_DIR%" 2>nul

set TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TIMESTAMP=%TIMESTAMP: =0%
set LOG_FILE=%LOG_DIR%\batch_%TIMESTAMP%.log

echo ======================================== >> "%LOG_FILE%"
echo 夜間バッチ開始: %date% %time% >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"

REM 以下、Linuxバージョンと同様の処理をWindows向けに実装
REM （簡略化のため省略）

echo ======================================== >> "%LOG_FILE%"
echo 夜間バッチ完了: %date% %time% >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"
echo ログファイル: %LOG_FILE%
```

---

## 📊 夜間バッチの実行スケジュール

### 推奨スケジュール

| 時刻 | タスク | 所要時間 |
|------|--------|----------|
| 22:00 | バッチ起動 | - |
| 22:00-02:00 | データ収集完了待機 | 最大4時間 |
| 02:00-02:05 | 全期間検証 | 5分 |
| 02:05-02:15 | 季節変動分析 | 10分 |
| 02:15-02:30 | 会場別分析 | 15分 |
| 02:30-02:35 | B細分化検証 | 5分 |
| 02:35-03:05 | 買い目戦略設計 | 30分 |
| 03:05-03:25 | 2024年バックテスト | 20分 |
| 03:25-03:40 | 翌日オッズ収集 | 15分 |
| **03:40** | **完了** | **総計約5.5時間** |

### タスクスケジューラへの登録

**Windows**:
```batch
REM タスクスケジューラに登録
schtasks /create /tn "BoatRaceNightBatch" /tr "C:\path\to\scripts\night_batch.bat" /sc daily /st 22:00
```

**Linux/Mac (cron)**:
```bash
# crontabに追加
0 22 * * * /path/to/scripts/night_batch.sh >> /path/to/logs/cron.log 2>&1
```

---

## 🔔 完了通知の設定

### メール通知（オプション）

バッチ完了時にメールで通知:

```python
# scripts/send_notification.py
import smtplib
from email.mime.text import MIMEText
import sys

def send_email(subject, body):
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = 'your-email@example.com'
    msg['To'] = 'your-email@example.com'

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login('your-email@example.com', 'your-password')
        server.send_message(msg)

if __name__ == '__main__':
    subject = sys.argv[1]
    body = sys.argv[2]
    send_email(subject, body)
```

バッチスクリプトの最後に追加:
```bash
python scripts/send_notification.py "夜間バッチ完了" "$(cat $LOG_DIR/batch_$TIMESTAMP.log)"
```

---

## 📝 必要なスクリプトの洗い出し

### 既存スクリプト（そのまま使える）
1. ✅ `scripts/validate_confidence_b_trifecta.py` - 全期間検証

### 新規作成が必要なスクリプト
2. ❌ `scripts/analyze_seasonal_trends.py` - 季節変動分析
3. ❌ `scripts/analyze_conditions.py` - 会場別・条件別分析
4. ❌ `scripts/validate_confidence_b_split.py` - B細分化検証
5. ❌ `scripts/design_strategy_b.py` - 買い目戦略設計
6. ❌ `scripts/night_batch.sh` / `night_batch.bat` - マスタースクリプト
7. ❌ `scripts/send_notification.py` - 通知スクリプト（オプション）

### 拡張が必要な既存スクリプト
8. 🔧 `scripts/backtest_strategy.py` - 信頼度B対応が必要（おそらく）

---

## 🎯 次のアクション

1. **現在のバックグラウンド処理の完了を待つ**（残り約2.3時間）
2. **全期間検証を手動実行**して結果確認
3. **必要なスクリプトを順次作成**
4. **夜間バッチスクリプトを組み立て**
5. **テスト実行**
6. **本番運用開始**

---

**作成日**: 2025-12-10
**最終更新**: 2025-12-10
