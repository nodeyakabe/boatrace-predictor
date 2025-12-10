# 夜間バッチ実行ガイド

**作成日**: 2025-12-10
**更新日**: 2025-12-10

---

## 🌙 夜間バッチの目的

データ収集・分析を夜間に自動実行して、朝には全ての分析結果が揃っている状態にする。

---

## 📝 実行手順

### 1. 夜間バッチの起動

```batch
cd c:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\scripts
night_batch.bat
```

### 2. 自動実行される7つのタスク

| # | タスク | スクリプト | 所要時間 |
|---|--------|-----------|----------|
| 1 | データ収集完了待機 | - | 最大4時間 |
| 2 | 全期間信頼度B三連単的中率検証 | `validate_confidence_b_trifecta.py` | 5分 |
| 3 | 季節変動分析（信頼度B） | `analyze_seasonal_trends.py` | 10分 |
| 4 | 会場別・条件別分析（信頼度B） | `analyze_conditions.py` | 15分 |
| 5 | 信頼度B細分化検証 | `validate_confidence_b_split.py` | 5分 |
| 6 | 信頼度別総合精度レポート | `analyze_comprehensive_accuracy.py` | 10分 |
| 7 | 季節変動分析（信頼度C） | `analyze_seasonal_trends.py` | 10分 |

**総所要時間**: 約1時間（データ収集待機除く）

---

## 📊 生成されるレポート一覧

### 1. 信頼度B三連単的中率検証
- **出力**: コンソール出力のみ
- **内容**: 信頼度A/B/Cの三連単的中率、統計的有意性検定

### 2. 季節変動分析（信頼度B）
- **CSV**: `output/seasonal_trends_B.csv`
- **グラフ**: `output/seasonal_trends_B.png`
- **内容**: 月別・四半期別の三連単的中率推移

### 3. 会場別・条件別分析（信頼度B）
- **CSV**: `output/condition_analysis_B.csv`
- **グラフ**: `output/venue_heatmap_B.png`
- **内容**: 24会場別の三連単的中率、ヒートマップ

### 4. 信頼度B細分化検証
- **出力**: コンソール出力のみ
- **内容**: B+（70-74点）とB（65-69点）の性能差、細分化推奨判定

### 5. 信頼度別総合精度レポート（新規）
- **CSV**: `output/comprehensive_accuracy.csv`
- **グラフ**: `output/comprehensive_accuracy.png`
- **Markdown**: `output/comprehensive_accuracy_report.md`
- **内容**:
  - 信頼度A/B/C/D/Eの全体比較
  - 三連単的中率、1-3着個別的中率
  - 月別推移（信頼度B）
  - 信頼度分布

### 6. 季節変動分析（信頼度C）
- **CSV**: `output/seasonal_trends_C.csv`
- **グラフ**: `output/seasonal_trends_C.png`
- **内容**: 信頼度Cの月別・四半期別推移

---

## 🛡️ ネットワーク対策

### 問題: ネット環境が不安定
**対策**:
- ✅ **全タスクがローカルDB専用** - ネットワーク接続不要
- ✅ **エラーハンドリング** - 個別タスクが失敗しても後続タスクを継続
- ✅ **タイムアウト処理** - データ収集を最大4時間待機、その後は収集済みデータで分析実行

### バッチスクリプトの安全機能

```batch
REM 個別タスクのエラーハンドリング
python scripts/validate_confidence_b_trifecta.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [エラー] タスク2でエラーが発生しましたが続行します | tee -a "%LOG_FILE%"
) else (
    echo [OK] タスク2完了 | tee -a "%LOG_FILE%"
)
```

---

## 📝 ログファイル

### 保存場所
```
logs/night_batch/batch_YYYYMMDD_HHMMSS.log
```

### ログ内容
- 各タスクの開始・終了時刻
- エラーメッセージ
- 生成されたファイル一覧

### ログ確認方法
```batch
REM 最新のログを表示
type logs\night_batch\batch_*.log | more
```

---

## ⚠️ トラブルシューティング

### 問題1: データ収集が365日完了していない

**症状**:
```
[警告] タイムアウト: データ収集が完了しませんでした（189/365日）
収集済みデータで分析を続行します...
```

**対応**:
- 収集済みデータで分析は実行される
- 翌日もう一度バッチを実行すればより多くのデータで再分析可能
- 365日完了まで待つ必要はない

### 問題2: 個別タスクでエラー発生

**症状**:
```
[エラー] タスク3でエラーが発生しましたが続行します
```

**対応**:
- 後続タスクは実行される
- ログファイルでエラー内容を確認
- 該当スクリプトを手動で再実行可能

### 問題3: グラフが生成されない

**原因**: matplotlib の日本語フォント設定
**対応**:
- CSVファイルは正常に生成される
- グラフなしでもデータ分析は可能

---

## 🎯 実行タイミング

### 推奨スケジュール

| 時刻 | アクション |
|------|-----------|
| 22:00 | 夜間バッチ起動 |
| 22:00-02:00 | データ収集完了待機 |
| 02:00-03:00 | 分析タスク実行（7タスク） |
| 03:00 | 完了 |

### タスクスケジューラへの登録（オプション）

```batch
REM Windows タスクスケジューラに登録
schtasks /create /tn "BoatRaceNightBatch" ^
  /tr "C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032\scripts\night_batch.bat" ^
  /sc daily /st 22:00
```

---

## 📈 期待される成果

### 翌朝までに入手できる情報

1. **信頼度Bの本番適用判定**
   - 三連単的中率が5%以上か？
   - 信頼度Aとの差は許容範囲か？
   - → 戦略Aへの組み込み可否を判断

2. **季節・会場による傾向把握**
   - どの月・会場で的中率が高いか？
   - 避けるべき条件は？
   - → リスク管理に活用

3. **全信頼度の性能比較**
   - 信頼度A/B/C/D/Eの実力序列
   - 信頼度Eの意外な高パフォーマンス発見
   - → 追加検証の方向性決定

---

## 🔄 次回以降の改善

### 将来追加したい分析（ネットワーク必要）

- **オッズデータ収集** - 翌日レースのオッズ事前取得
- **収支実績分析** - オッズと的中の組み合わせでROI算出
- **直前情報影響度分析** - 風・波・気温の影響度分析（DBに既にデータあり）

これらは次のフェーズで実装予定。

---

## 📞 完了通知（オプション）

### メール通知の設定

```python
# scripts/send_notification.py を作成
import smtplib
from email.mime.text import MIMEText

def send_email(subject, body):
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = 'your-email@example.com'
    msg['To'] = 'your-email@example.com'

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login('your-email@example.com', 'your-password')
        server.send_message(msg)
```

バッチスクリプト最後に追加:
```batch
python scripts/send_notification.py "夜間バッチ完了" "全7タスクが完了しました"
```

---

**作成者**: Claude Sonnet 4.5
**最終更新**: 2025-12-10
