#!/bin/bash
# 自動モニタリングのcronジョブ設定スクリプト（Linux/Mac用）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "自動モニタリング cronジョブ設定"
echo "========================================="
echo ""

# Pythonパス検出
PYTHON_CMD=$(which python3 || which python)

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ Pythonが見つかりません"
    exit 1
fi

echo "Python: $PYTHON_CMD"
echo "プロジェクトルート: $PROJECT_ROOT"
echo ""

# cronジョブエントリ
CRON_ENTRY_WEEKLY="0 9 * * 1 cd $PROJECT_ROOT && $PYTHON_CMD scripts/monitor_pattern_performance.py --days 7 >> logs/monitoring_weekly.log 2>&1"
CRON_ENTRY_MONTHLY="0 1 1 * * cd $PROJECT_ROOT && $PYTHON_CMD scripts/auto_pattern_update.py --days 30 >> logs/monitoring_monthly.log 2>&1"
CRON_ENTRY_AUTOMATED="0 8 * * * cd $PROJECT_ROOT && $PYTHON_CMD scripts/automated_monitoring.py >> logs/monitoring_automated.log 2>&1"

echo "以下のcronジョブを設定します:"
echo ""
echo "【週次モニタリング】毎週月曜日 9:00"
echo "$CRON_ENTRY_WEEKLY"
echo ""
echo "【月次パターン更新】毎月1日 1:00"
echo "$CRON_ENTRY_MONTHLY"
echo ""
echo "【自動監視】毎日 8:00"
echo "$CRON_ENTRY_AUTOMATED"
echo ""

read -p "cronジョブを追加しますか？ (y/n): " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # ログディレクトリ作成
    mkdir -p "$PROJECT_ROOT/logs"

    # 既存のcrontabを取得
    crontab -l > /tmp/current_cron 2>/dev/null || true

    # 重複チェック
    if grep -q "monitor_pattern_performance.py" /tmp/current_cron 2>/dev/null; then
        echo "⚠️ 週次モニタリングのエントリが既に存在します（スキップ）"
    else
        echo "$CRON_ENTRY_WEEKLY" >> /tmp/current_cron
        echo "✓ 週次モニタリング追加"
    fi

    if grep -q "auto_pattern_update.py" /tmp/current_cron 2>/dev/null; then
        echo "⚠️ 月次パターン更新のエントリが既に存在します（スキップ）"
    else
        echo "$CRON_ENTRY_MONTHLY" >> /tmp/current_cron
        echo "✓ 月次パターン更新追加"
    fi

    if grep -q "automated_monitoring.py" /tmp/current_cron 2>/dev/null; then
        echo "⚠️ 自動監視のエントリが既に存在します（スキップ）"
    else
        echo "$CRON_ENTRY_AUTOMATED" >> /tmp/current_cron
        echo "✓ 自動監視追加"
    fi

    # crontabを更新
    crontab /tmp/current_cron
    rm /tmp/current_cron

    echo ""
    echo "✅ cronジョブ設定完了"
    echo ""
    echo "現在のcrontab:"
    crontab -l | grep "boatrace"
else
    echo "キャンセルしました"
    exit 1
fi

echo ""
echo "========================================="
echo "手動でログを確認する場合:"
echo "  tail -f logs/monitoring_weekly.log"
echo "  tail -f logs/monitoring_monthly.log"
echo "  tail -f logs/monitoring_automated.log"
echo "========================================="
