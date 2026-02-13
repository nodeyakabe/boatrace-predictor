# PC自動再起動の防止設定ガイド

2日間の長時間データ収集中に、PCが自動再起動しないようにする設定です。

## 1. Windows Updateの自動再起動を無効化

### 方法A: グループポリシー（推奨）

1. **Win + R** → `gpedit.msc` と入力してEnter
2. 「コンピューターの構成」→「管理用テンプレート」→「Windows コンポーネント」→「Windows Update」
3. 「自動更新を構成する」を開く
4. 「有効」を選択
5. オプションで「4 - 自動ダウンロードしてインストール日時を指定」を選択
6. 「スケジュールされた自動更新のインストールで、ログオンしているユーザーがいる場合には自動的に再起動しない」を有効化
7. 「OK」をクリック

### 方法B: レジストリ編集（Home Edition用）

```bash
# PowerShellを管理者権限で実行
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" -Name "NoAutoRebootWithLoggedOnUsers" -Value 1 -Type DWord
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" -Name "AUOptions" -Value 4 -Type DWord
```

### 方法C: 設定アプリ（簡易版）

1. 「設定」→「更新とセキュリティ」→「Windows Update」
2. 「詳細オプション」をクリック
3. 「更新プログラムのインストール時期を選択」で適切な時間を設定
4. 「アクティブ時間の変更」で24時間をカバー

## 2. スリープ・休止状態の無効化

### PowerShellで設定（推奨）

```powershell
# スリープを無効化
powercfg -change -standby-timeout-ac 0
powercfg -change -standby-timeout-dc 0

# ディスプレイオフ時間を延長（必要に応じて）
powercfg -change -monitor-timeout-ac 0

# 休止状態を無効化
powercfg -h off
```

### GUIで設定

1. 「設定」→「システム」→「電源とスリープ」
2. 「スリープ」を「なし」に設定
3. 「電源の追加設定」→「コンピューターをスリープ状態にする」を「なし」

## 3. 自動メンテナンスの無効化

```powershell
# タスクスケジューラで自動メンテナンスを無効化
schtasks /Change /TN "\Microsoft\Windows\TaskScheduler\Regular Maintenance" /DISABLE
schtasks /Change /TN "\Microsoft\Windows\TaskScheduler\Idle Maintenance" /DISABLE
```

## 4. 実行中の確認コマンド

```bash
# Windows Updateの状態確認
wmic qfe list brief /format:table

# 再起動予定の確認
shutdown /a  # キャンセル

# スリープ設定の確認
powercfg /query

# 実行中のメンテナンスタスク確認
schtasks /query /TN "\Microsoft\Windows\TaskScheduler\*"
```

## 5. 実行前チェックリスト

```bash
# スクリプト実行前に以下を確認
echo "=== 実行前チェック ==="
echo ""
echo "1. Windows Update: 手動に設定済み？"
echo "2. スリープ: 無効化済み？"
echo "3. 電源プラン: 高パフォーマンス？"
echo "4. ネットワーク: 有線LAN接続？"
echo "5. ディスク容量: 10GB以上の空き？"
```

## 6. 緊急時の対処

### 再起動が予定されている場合

```bash
# 再起動をキャンセル
shutdown /a

# Windows Updateを一時停止（7日間）
# 設定 → 更新とセキュリティ → Windows Update → 「更新の一時停止」
```

### データ収集の再開

```bash
# 再開可能版スクリプトで自動的に続行
python scripts/data_collection/自動実行_2日間_完全収集_再開可能版.py

# 進捗確認
cat data/.collection_progress.json
```

## 7. 収集完了後の設定復元

```powershell
# スリープを元に戻す（15分）
powercfg -change -standby-timeout-ac 15
powercfg -change -standby-timeout-dc 15

# 休止状態を有効化
powercfg -h on

# Windows Updateを自動に戻す
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" -Name "AUOptions" -Value 3 -Type DWord
```

## トラブルシューティング

### Q: 設定したのに再起動された
A: Windows Updateの強制再起動は完全には防げません。再開可能版スクリプトで続行してください。

### Q: スリープ設定が反映されない
A: 電源プランを「高パフォーマンス」に変更してください。

### Q: ノートPCのバッテリー駆動時は？
A: 必ずACアダプターを接続してください。バッテリー駆動中は設定が異なります。
