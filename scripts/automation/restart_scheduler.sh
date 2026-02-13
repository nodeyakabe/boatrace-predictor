#!/bin/bash
# daily_scheduler 安全再起動スクリプト

echo "=========================================="
echo "daily_scheduler 再起動スクリプト"
echo "=========================================="
echo ""

# 1. 現在のプロセス確認
echo "Step 1: 現在のプロセス確認..."
OLD_PID=$(cat data/daily_scheduler.lock 2>/dev/null)
if [ -n "$OLD_PID" ]; then
    echo "  現在のPID: $OLD_PID"
    ps -p $OLD_PID > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "  プロセスは稼働中です"
    else
        echo "  プロセスは既に終了しています"
    fi
else
    echo "  ロックファイルが見つかりません"
fi
echo ""

# 2. 停止
echo "Step 2: daily_schedulerを停止..."
if [ -n "$OLD_PID" ]; then
    kill $OLD_PID 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "  停止シグナル送信: OK"
        sleep 2
        ps -p $OLD_PID > /dev/null 2>&1
        if [ $? -ne 0 ]; then
            echo "  プロセス終了確認: OK"
        else
            echo "  プロセスがまだ動いています。強制終了します..."
            kill -9 $OLD_PID 2>/dev/null
            sleep 1
        fi
    else
        echo "  プロセスは既に終了しています"
    fi
fi
echo ""

# 3. ロックファイル削除
echo "Step 3: ロックファイル削除..."
if [ -f data/daily_scheduler.lock ]; then
    rm data/daily_scheduler.lock
    echo "  削除: OK"
else
    echo "  ロックファイルなし: OK"
fi
echo ""

# 4. 新しいschedulerを起動
echo "Step 4: 新しいdaily_schedulerを起動..."
nohup python scripts/automation/daily_scheduler.py > logs/daily_scheduler.log 2>&1 &
NEW_PID=$!
echo "  起動: OK"
echo "  新しいPID: $NEW_PID"
echo ""

# 5. 起動確認
sleep 2
ps -p $NEW_PID > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "=========================================="
    echo "再起動完了！"
    echo "=========================================="
    echo ""
    echo "新しいPID: $NEW_PID"
    echo "ログファイル: logs/daily_scheduler.log"
    echo ""
    echo "ログ確認:"
    echo "  tail -f logs/daily_scheduler.log"
else
    echo "=========================================="
    echo "エラー: 起動に失敗しました"
    echo "=========================================="
    echo ""
    echo "ログを確認してください:"
    echo "  cat logs/daily_scheduler.log"
fi
