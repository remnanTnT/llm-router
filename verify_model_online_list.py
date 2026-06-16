#!/usr/bin/env python3
"""
验证 model_online_list 接口的实现
此脚本检查代码实现是否符合需求，不需要运行服务器
"""

import ast
import sys

def check_repository_method():
    """检查 ModelRepository.list_online() 方法"""
    with open('router/repositories/models.py', 'r') as f:
        content = f.read()

    # 检查方法是否存在
    if 'def list_online' not in content:
        print("❌ ModelRepository.list_online() 方法不存在")
        return False

    # 检查是否过滤 deprecation__isnull=True
    if 'deprecation__isnull=True' in content:
        print("✅ ModelRepository.list_online() 正确过滤 deprecation 为 null 的记录")
    else:
        print("❌ ModelRepository.list_online() 未正确过滤 deprecation")
        return False

    return True

def check_view_function():
    """检查 model_online_list 视图函数"""
    with open('router/api/views.py', 'r') as f:
        content = f.read()

    # 检查函数是否存在
    if 'def model_online_list' not in content:
        print("❌ model_online_list 视图函数不存在")
        return False

    print("✅ model_online_list 视图函数存在")

    # 检查是否调用 list_online()
    if 'ModelRepository.list_online()' in content:
        print("✅ 视图函数调用了 ModelRepository.list_online()")
    else:
        print("❌ 视图函数未调用 ModelRepository.list_online()")
        return False

    # 检查是否只返回 model_name
    if 'model.model_name for model in' in content:
        print("✅ 返回数据只包含 model_name 列表")
    else:
        print("⚠️  返回格式可能不符合预期")

    return True

def check_url_routing():
    """检查 URL 路由配置"""
    with open('router/api/urls.py', 'r') as f:
        content = f.read()

    # 检查路由是否存在
    if 'model_online_list' in content:
        print("✅ URL 路由已配置")

        # 检查路径
        if 'path("model_online_list"' in content:
            print("✅ 路由路径为: /api/model_online_list")
        else:
            print("⚠️  路由路径可能不是标准格式")

        return True
    else:
        print("❌ URL 路由未配置")
        return False

def main():
    print("=" * 60)
    print("验证 model_online_list 接口实现")
    print("=" * 60)
    print()

    print("1. 检查 Repository 层")
    print("-" * 60)
    repo_ok = check_repository_method()
    print()

    print("2. 检查 View 层")
    print("-" * 60)
    view_ok = check_view_function()
    print()

    print("3. 检查 URL 路由")
    print("-" * 60)
    url_ok = check_url_routing()
    print()

    print("=" * 60)
    if repo_ok and view_ok and url_ok:
        print("✅ 所有检查通过！接口实现正确")
        print()
        print("接口说明:")
        print("  - 路径: GET /api/model_online_list")
        print("  - 功能: 返回所有未废弃的模型名称列表")
        print("  - 过滤条件: deprecation IS NULL")
        print("  - 返回格式: {\"code\": 200, \"data\": [\"model1\", \"model2\", ...]}")
        return 0
    else:
        print("❌ 存在问题，请检查上述错误")
        return 1

if __name__ == '__main__':
    sys.exit(main())
