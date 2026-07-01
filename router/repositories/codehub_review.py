from __future__ import annotations

from datetime import datetime
from django.db.models import Count, Q
from router.models import DailyMrReview, CodehubReview


class DailyMrReviewRepository:
    @staticmethod
    def exists_by_hash(issue_hash: str) -> bool:
        return DailyMrReview.objects.filter(issue_hash=issue_hash).exists()

    @staticmethod
    def create(data: dict) -> DailyMrReview:
        return DailyMrReview.objects.create(**data)


class CodehubReviewRepository:
    @staticmethod
    def get_statistics(
        project_name: str | None = None,
        branch_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        """
        获取CodehubReview统计信息。

        Args:
            project_name: 项目名称筛选（可选）
            branch_name: 分支名称筛选（可选）
            start_time: 开始时间（基于scan_date，可选）
            end_time: 结束时间（基于scan_date，可选）

        Returns:
            统计信息字典，包含总数、is_valid_issue统计、is_modified_completed统计、severity统计
        """
        # 构建基础查询
        queryset = CodehubReview.objects.filter(deleted_at__isnull=True)

        # 应用筛选条件
        if project_name:
            queryset = queryset.filter(project_name=project_name)

        if branch_name:
            queryset = queryset.filter(branch_name=branch_name)

        if start_time:
            queryset = queryset.filter(scan_date__gte=start_time)

        if end_time:
            queryset = queryset.filter(scan_date__lte=end_time)

        # 1. 总数据条数
        total_count = queryset.count()

        # 2. is_valid_issue为true的条数
        valid_issue_count = queryset.filter(is_valid_issue=True).count()

        # 3. is_valid_issue为false的条数
        invalid_issue_count = queryset.filter(is_valid_issue=False).count()

        # 4. is_modified_completed为true的条数
        modified_completed_count = queryset.filter(is_modified_completed=True).count()

        # 5. severity各个类型的数量
        severity_stats = {}
        severity_counts = queryset.values('severity').annotate(count=Count('id'))

        for item in severity_counts:
            severity_type = item['severity'] or 'unknown'
            severity_stats[severity_type] = item['count']

        # 6. 获取最新的 scan_commit_id
        latest_record = queryset.order_by('-scan_date').first()
        latest_scan_commit_id = latest_record.scan_commit_id if latest_record else None

        return {
            'total_count': total_count,
            'valid_issue_count': valid_issue_count,
            'invalid_issue_count': invalid_issue_count,
            'modified_completed_count': modified_completed_count,
            'severity': severity_stats,
            'latest_scan_commit_id': latest_scan_commit_id,
        }

    @staticmethod
    def get_issue_category_statistics(
        project_name: str | None = None,
        branch_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        """
        获取CodehubReview的issue_category详细统计信息。

        Args:
            project_name: 项目名称筛选（可选）
            branch_name: 分支名称筛选（可选）
            start_time: 开始时间（基于scan_date，可选）
            end_time: 结束时间（基于scan_date，可选）

        Returns:
            issue_category各个类型的详细数据，包含：
            - count: 各个issue_category类型的数量
            - valid_issue_count: 各个issue_category类型的is_valid_issue为true的条数
            - invalid_issue_count: 各个issue_category类型的is_valid_issue为false的条数
            - modified_completed_count: 各个issue_category类型的is_modified_completed为true的条数
        """
        # 构建基础查询
        queryset = CodehubReview.objects.filter(deleted_at__isnull=True)

        # 应用筛选条件
        if project_name:
            queryset = queryset.filter(project_name=project_name)

        if branch_name:
            queryset = queryset.filter(branch_name=branch_name)

        if start_time:
            queryset = queryset.filter(scan_date__gte=start_time)

        if end_time:
            queryset = queryset.filter(scan_date__lte=end_time)

        # 统计issue_category各个类型的详细数据
        category_counts = queryset.values('issue_category').annotate(
            count=Count('id'),
            valid_issue_count=Count('id', filter=Q(is_valid_issue=True)),
            invalid_issue_count=Count('id', filter=Q(is_valid_issue=False)),
            modified_completed_count=Count('id', filter=Q(is_modified_completed=True)),
        )

        category_detail = {}
        for item in category_counts:
            category_type = item['issue_category'] or 'unknown'
            category_detail[category_type] = {
                'count': item['count'],
                'valid_issue_count': item['valid_issue_count'],
                'invalid_issue_count': item['invalid_issue_count'],
                'modified_completed_count': item['modified_completed_count'],
            }

        return category_detail

    @staticmethod
    def get_severity_detail_statistics(
        project_name: str | None = None,
        branch_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        """
        获取CodehubReview的severity详细统计信息。

        Args:
            project_name: 项目名称筛选（可选）
            branch_name: 分支名称筛选（可选）
            start_time: 开始时间（基于scan_date，可选）
            end_time: 结束时间（基于scan_date，可选）

        Returns:
            severity各个类型的详细数据，包含：
            - count: 各个severity类型的数量
            - valid_issue_count: 各个severity类型的is_valid_issue为true的条数
            - invalid_issue_count: 各个severity类型的is_valid_issue为false的条数
            - modified_completed_count: 各个severity类型的is_modified_completed为true的条数
        """
        # 构建基础查询
        queryset = CodehubReview.objects.filter(deleted_at__isnull=True)

        # 应用筛选条件
        if project_name:
            queryset = queryset.filter(project_name=project_name)

        if branch_name:
            queryset = queryset.filter(branch_name=branch_name)

        if start_time:
            queryset = queryset.filter(scan_date__gte=start_time)

        if end_time:
            queryset = queryset.filter(scan_date__lte=end_time)

        # severity各个类型的数量
        severity_counts = queryset.values('severity').annotate(
            count=Count('id'),
            valid_issue_count=Count('id', filter=Q(is_valid_issue=True)),
            invalid_issue_count=Count('id', filter=Q(is_valid_issue=False)),
            modified_completed_count=Count('id', filter=Q(is_modified_completed=True)),
        )

        severity_detail = {}
        for item in severity_counts:
            severity_type = item['severity'] or 'unknown'
            severity_detail[severity_type] = {
                'count': item['count'],
                'valid_issue_count': item['valid_issue_count'],
                'invalid_issue_count': item['invalid_issue_count'],
                'modified_completed_count': item['modified_completed_count'],
            }

        return severity_detail

    @staticmethod
    def get_filtered_reviews(
        project_name: str | None = None,
        branch_name: str | None = None,
        relative_path: str | list[str] | None = None,
        severity: str | list[str] | None = None,
        issue_category: str | list[str] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> dict:
        """
        获取CodehubReview过滤查询列表（支持分页）。

        Args:
            project_name: 项目名称筛选（可选）
            branch_name: 分支名称筛选（可选）
            relative_path: 相对路径筛选（可选，支持单个值或列表，支持模糊匹配）
            severity: 严重级别筛选（可选，支持单个值或列表）
            issue_category: 问题类别筛选（可选，支持单个值或列表）
            start_time: 开始时间（基于scan_date，可选）
            end_time: 结束时间（基于scan_date，可选）
            page: 页码（默认为1）
            page_size: 每页大小（默认为10）

        Returns:
            包含分页数据和总数的字典
        """
        from django.core.paginator import Paginator

        # 构建基础查询
        queryset = CodehubReview.objects.filter(deleted_at__isnull=True)

        # 应用筛选条件
        if project_name:
            queryset = queryset.filter(project_name=project_name)

        if branch_name:
            queryset = queryset.filter(branch_name=branch_name)

        # relative_path 支持单个值或列表，使用模糊匹配
        if relative_path:
            if isinstance(relative_path, list):
                # 多个值：使用 Q 对象组合多个 icontains 条件
                q_objects = Q()
                for path in relative_path:
                    if path:
                        q_objects |= Q(relative_path__icontains=path)
                queryset = queryset.filter(q_objects)
            else:
                queryset = queryset.filter(relative_path__icontains=relative_path)

        # severity 支持单个值或列表
        if severity:
            if isinstance(severity, list):
                queryset = queryset.filter(severity__in=severity)
            else:
                queryset = queryset.filter(severity=severity)

        # issue_category 支持单个值或列表
        if issue_category:
            if isinstance(issue_category, list):
                queryset = queryset.filter(issue_category__in=issue_category)
            else:
                queryset = queryset.filter(issue_category=issue_category)

        if start_time:
            queryset = queryset.filter(scan_date__gte=start_time)

        if end_time:
            queryset = queryset.filter(scan_date__lte=end_time)

        # 按scan_date降序排序
        queryset = queryset.order_by('-scan_date')

        # 分页
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.page(page)

        # 序列化数据
        items = []
        for review in page_obj.object_list:
            items.append({
                'id': review.id,
                'project_id': review.project_id,
                'project_name': review.project_name,
                'branch_name': review.branch_name,
                'scan_commit_id': review.scan_commit_id,
                'scan_date': review.scan_date.isoformat() if review.scan_date else None,
                'completion_date': review.completion_date.isoformat() if review.completion_date else None,
                'relative_path': review.relative_path,
                'line': review.line,
                'issue_description': review.issue_description,
                'severity': review.severity,
                'issue_category': review.issue_category,
                'module': review.module,
                'first_level_confirmer': review.first_level_confirmer,
                'second_level_confirmer': review.second_level_confirmer,
                'is_modified': review.is_modified,
                'is_valid_issue': review.is_valid_issue,
                'is_modified_completed': review.is_modified_completed,
                'notes': review.notes,
                'created_at': review.created_at.isoformat() if review.created_at else None,
                'updated_at': review.updated_at.isoformat() if review.updated_at else None,
            })

        return {
            'total_count': paginator.count,
            'total_pages': paginator.num_pages,
            'current_page': page,
            'page_size': page_size,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'items': items,
        }

    @staticmethod
    def update_review(
        review_id: int,
        module: str | None = None,
        first_level_confirmer: str | None = None,
        second_level_confirmer: str | None = None,
        is_valid_issue: bool | None = None,
        is_modified: bool | None = None,
        is_modified_completed: bool | None = None,
        notes: str | None = None,
    ) -> CodehubReview | None:
        """
        更新CodehubReview记录。

        Args:
            review_id: 记录ID（必传）
            module: 模块名称（可选）
            first_level_confirmer: 一级确认人（可选）
            second_level_confirmer: 二级确认人（可选）
            is_valid_issue: 是否为有效问题（可选）
            is_modified: 是否已修改（可选）
            is_modified_completed: 是否修改完成（可选）
            notes: 备注（可选）

        Returns:
            更新后的CodehubReview对象，若不存在则返回None
        """
        try:
            review = CodehubReview.objects.get(id=review_id, deleted_at__isnull=True)
        except CodehubReview.DoesNotExist:
            return None

        # 更新字段
        if module is not None:
            review.module = module
        if first_level_confirmer is not None:
            review.first_level_confirmer = first_level_confirmer
        if second_level_confirmer is not None:
            review.second_level_confirmer = second_level_confirmer
        if is_valid_issue is not None:
            review.is_valid_issue = is_valid_issue
        if is_modified is not None:
            review.is_modified = is_modified
        if is_modified_completed is not None:
            review.is_modified_completed = is_modified_completed
        if notes is not None:
            review.notes = notes

        review.save()
        return review

    @staticmethod
    def get_relative_path_list(
        project_name: str | None = None,
        branch_name: str | None = None,
        severity: str | None = None,
        issue_category: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[str]:
        """
        获取CodehubReview中relative_path的去重列表。

        Args:
            project_name: 项目名称筛选（可选）
            branch_name: 分支名称筛选（可选）
            severity: 严重级别筛选（可选）
            issue_category: 问题类别筛选（可选）
            start_time: 开始时间（基于scan_date，可选）
            end_time: 结束时间（基于scan_date，可选）

        Returns:
            relative_path的去重列表
        """
        # 构建基础查询
        queryset = CodehubReview.objects.filter(deleted_at__isnull=True)

        # 应用筛选条件
        if project_name:
            queryset = queryset.filter(project_name=project_name)

        if branch_name:
            queryset = queryset.filter(branch_name=branch_name)

        if severity:
            queryset = queryset.filter(severity=severity)

        if issue_category:
            queryset = queryset.filter(issue_category=issue_category)

        if start_time:
            queryset = queryset.filter(scan_date__gte=start_time)

        if end_time:
            queryset = queryset.filter(scan_date__lte=end_time)

        # 获取去重的relative_path列表，按字母顺序排序
        relative_paths = queryset.values_list('relative_path', flat=True).distinct().order_by('relative_path')

        return list(relative_paths)

    @staticmethod
    def get_severity_list(
        project_name: str | None = None,
        branch_name: str | None = None,
        relative_path: str | None = None,
        issue_category: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[str]:
        """
        获取CodehubReview中severity的去重列表。

        Args:
            project_name: 项目名称筛选（可选）
            branch_name: 分支名称筛选（可选）
            relative_path: 相对路径筛选（可选，支持模糊匹配）
            issue_category: 问题类别筛选（可选）
            start_time: 开始时间（基于scan_date，可选）
            end_time: 结束时间（基于scan_date，可选）

        Returns:
            severity的去重列表
        """
        # 构建基础查询
        queryset = CodehubReview.objects.filter(deleted_at__isnull=True)

        # 应用筛选条件
        if project_name:
            queryset = queryset.filter(project_name=project_name)

        if branch_name:
            queryset = queryset.filter(branch_name=branch_name)

        if relative_path:
            queryset = queryset.filter(relative_path__icontains=relative_path)

        if issue_category:
            queryset = queryset.filter(issue_category=issue_category)

        if start_time:
            queryset = queryset.filter(scan_date__gte=start_time)

        if end_time:
            queryset = queryset.filter(scan_date__lte=end_time)

        # 获取去重的severity列表，按字母顺序排序
        severities = queryset.values_list('severity', flat=True).distinct().order_by('severity')

        return list(severities)

    @staticmethod
    def get_issue_category_list(
        project_name: str | None = None,
        branch_name: str | None = None,
        relative_path: str | None = None,
        severity: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[str]:
        """
        获取CodehubReview中issue_category的去重列表。

        Args:
            project_name: 项目名称筛选（可选）
            branch_name: 分支名称筛选（可选）
            relative_path: 相对路径筛选（可选，支持模糊匹配）
            severity: 严重级别筛选（可选）
            start_time: 开始时间（基于scan_date，可选）
            end_time: 结束时间（基于scan_date，可选）

        Returns:
            issue_category的去重列表
        """
        # 构建基础查询
        queryset = CodehubReview.objects.filter(deleted_at__isnull=True)

        # 应用筛选条件
        if project_name:
            queryset = queryset.filter(project_name=project_name)

        if branch_name:
            queryset = queryset.filter(branch_name=branch_name)

        if relative_path:
            queryset = queryset.filter(relative_path__icontains=relative_path)

        if severity:
            queryset = queryset.filter(severity=severity)

        if start_time:
            queryset = queryset.filter(scan_date__gte=start_time)

        if end_time:
            queryset = queryset.filter(scan_date__lte=end_time)

        # 获取去重的issue_category列表，按字母顺序排序
        issue_categories = queryset.values_list('issue_category', flat=True).distinct().order_by('issue_category')

        return list(issue_categories)
