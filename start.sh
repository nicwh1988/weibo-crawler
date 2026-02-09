#!/bin/bash
cd "$(dirname "$0")"

# 只杀死本项目的weibo.py进程
pkill -f "python3 weibo.py" 2>/dev/null
sleep 1
nohup python3 weibo.py > weibo_monitor.log 2>&1 &
echo "weibo-crawler started, pid: $!"
