#!/usr/bin/env python3
"""测试时区处理逻辑"""
import os
import django
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'router_project.settings')
django.setup()

from django.utils import timezone
from router.api.stats import parse_beijing_datetime, BEIJING_TZ, format_bucket
from router.models import RequestRecord

print("=" * 60)
print("1. 测试时间解析逻辑")
print("=" * 60)

# 测试输入：北京时间字符串
input_time = "2026-04-15 11:49:00"
parsed = parse_beijing_datetime(input_time, "test_time")
print(f"输入字符串: {input_time} (用户期望这是北京时间)")
print(f"解析结果: {parsed}")
print(f"时区信息: {parsed.tzinfo}")
print(f"转为UTC: {parsed.astimezone(ZoneInfo('UTC'))}")
print()

print("=" * 60)
print("2. 检查数据库中的实际时间")
print("=" * 60)

# 查询一条记录
record = RequestRecord.objects.filter(task_status='success').order_by('-send_time').first()
if record:
    print(f"数据库 send_time 原始值: {record.send_time}")
    print(f"时区信息: {record.send_time.tzinfo}")
    print(f"转为北京时间: {record.send_time.astimezone(BEIJING_TZ)}")
    print(f"转为UTC时间: {record.send_time.astimezone(ZoneInfo('UTC'))}")
    print()

    # 测试查询逻辑
    print("=" * 60)
    print("3. 测试查询逻辑")
    print("=" * 60)

    # 假设用户输入北京时间查询
    user_input_beijing = "2026-04-15 10:00:00"
    start = parse_beijing_datetime(user_input_beijing, "start_time")
    print(f"用户输入 start_time: {user_input_beijing} (北京时间)")
    print(f"解析后用于查询: {start}")
    print(f"查询条件转UTC: {start.astimezone(ZoneInfo('UTC'))}")
    print()

    # 检查这条记录是否会被匹配
    would_match = record.send_time >= start
    print(f"数据库记录时间 >= 查询开始时间: {would_match}")
    print(f"  数据库: {record.send_time}")
    print(f"  查询条件: {start}")
    print()

print("=" * 60)
print("4. 测试输出格式化")
print("=" * 60)

if record:
    # 测试 format_bucket
    formatted_hour = format_bucket(record.send_time, "hour")
    formatted_day = format_bucket(record.send_time, "day")
    print(f"数据库时间: {record.send_time}")
    print(f"格式化(hour): {formatted_hour}")
    print(f"格式化(day): {formatted_day}")
    print(f"转为北京时间字符串: {record.send_time.astimezone(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}")

print()
print("=" * 60)
print("5. 测试 bucket_expression 的时区处理")
print("=" * 60)

from router.api.stats import bucket_expression
from django.db.models.functions import TruncHour

# 检查 TruncHour 使用的时区
trunc_expr = bucket_expression("send_time", "hour")
print(f"Trunc表达式类型: {type(trunc_expr)}")
print(f"使用的时区: {trunc_expr.tzinfo if hasattr(trunc_expr, 'tzinfo') else 'N/A'}")
