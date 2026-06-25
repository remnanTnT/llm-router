"""
测试access_stats_by_department接口
"""
import pytest
from datetime import datetime, timedelta
from django.utils import timezone
from router.repositories.requests import RequestRepository


class TestAccessStatsByDepartment:
    """测试按部门统计访问数据的接口"""

    def test_count_success_by_ip_with_user_info_basic(self, db):
        """测试基本的统计功能"""
        # 设置时间范围
        now = timezone.now()
        start = now - timedelta(hours=1)
        end = now

        # 调用方法
        results = RequestRepository.count_success_by_ip_with_user_info(
            start=start,
            end=end,
        )

        # 验证返回结果是列表
        assert isinstance(results, list)

    def test_count_success_by_ip_with_user_info_dept_filter(self, db):
        """测试部门过滤功能"""
        now = timezone.now()
        start = now - timedelta(hours=1)
        end = now

        # 测试单个部门过滤
        results = RequestRepository.count_success_by_ip_with_user_info(
            start=start,
            end=end,
            dept1="测试部门",
        )

        assert isinstance(results, list)

        # 测试多个部门过滤
        results = RequestRepository.count_success_by_ip_with_user_info(
            start=start,
            end=end,
            dept1="测试部门1",
            dept2="测试部门2",
        )

        assert isinstance(results, list)

    def test_count_success_by_ip_with_user_info_empty_result(self, db):
        """测试空结果"""
        # 使用未来的时间范围，应该没有数据
        now = timezone.now()
        start = now + timedelta(days=1)
        end = now + timedelta(days=2)

        results = RequestRepository.count_success_by_ip_with_user_info(
            start=start,
            end=end,
        )

        assert results == []

    def test_count_success_by_ip_with_user_info_result_structure(self, db):
        """测试返回结果的结构"""
        now = timezone.now()
        start = now - timedelta(hours=24)
        end = now

        results = RequestRepository.count_success_by_ip_with_user_info(
            start=start,
            end=end,
        )

        # 如果有结果，验证结构
        if results:
            result = results[0]
            assert "ip" in result
            assert "access_count" in result
            assert "user_name" in result
            assert "user_charge" in result
            assert "employee_no" in result
            assert "dept1" in result
            assert "dept2" in result
            assert "dept3" in result
            assert "dept4" in result

            # 验证access_count是整数
            assert isinstance(result["access_count"], int)
            assert result["access_count"] > 0
