# model_online_list API 接口文档

## 概述
新增的 `model_online_list` 接口用于获取所有在线（未废弃）的模型名称列表。

## 接口信息

### 请求
- **URL**: `/api/model_online_list`
- **方法**: `GET`
- **参数**: 无

### 响应
```json
{
  "code": 200,
  "data": ["model-name-1", "model-name-2", "model-name-3"]
}
```

- `code`: 状态码（200 表示成功）
- `data`: 字符串数组，包含所有 `deprecation` 字段为 `null` 的模型名称

## 实现细节

### 1. Repository 层 (`router/repositories/models.py`)
新增 `list_online()` 方法：
```python
@staticmethod
def list_online() -> list[Model]:
    """List all models that are not deprecated (deprecation is null)."""
    return list(Model.objects.filter(deprecation__isnull=True).order_by("id"))
```

**功能**:
- 查询 `models` 表中所有 `deprecation` 为 `NULL` 的记录
- 按 `id` 排序
- 返回 Model 对象列表

### 2. View 层 (`router/api/views.py`)
新增 `model_online_list()` 视图函数：
```python
@require_http_methods(["GET"])
def model_online_list(request):
    return JsonResponse(
        {
            "code": 200,
            "data": [model.model_name for model in ModelRepository.list_online()],
        }
    )
```

**功能**:
- 调用 `ModelRepository.list_online()` 获取在线模型
- 提取每个模型的 `model_name` 字段
- 返回 JSON 格式的模型名称列表

### 3. URL 路由 (`router/api/urls.py`)
添加路由配置：
```python
path("model_online_list", views.model_online_list),
```

## 使用场景

### 示例 1: 获取所有在线模型
**请求**:
```bash
curl http://localhost:8000/api/model_online_list
```

**响应**（假设数据库中有以下数据）:
| id | model_name | deprecation |
|----|------------|-------------|
| 1  | gpt-4      | NULL        |
| 2  | claude-3   | NULL        |
| 3  | gpt-3.5    | "已废弃"     |

```json
{
  "code": 200,
  "data": ["gpt-4", "claude-3"]
}
```

### 示例 2: 所有模型都已废弃
**响应**:
```json
{
  "code": 200,
  "data": []
}
```

## 与现有接口的区别

### `/api/models` vs `/api/model_online_list`

| 特性 | `/api/models` | `/api/model_online_list` |
|------|---------------|--------------------------|
| 返回字段 | id, model_name, concurrent_limit | 仅 model_name |
| 过滤条件 | 返回所有模型 | 仅返回 deprecation 为 null 的模型 |
| 数据格式 | 对象数组 | 字符串数组 |
| 用途 | 完整的模型信息 | 简洁的在线模型列表 |

## 测试

测试文件位于 `tests/test_model_online_list.py`，包含以下测试用例：

1. **test_model_online_list_returns_only_non_deprecated**: 验证只返回未废弃的模型
2. **test_model_online_list_returns_empty_when_all_deprecated**: 验证全部废弃时返回空数组
3. **test_model_online_list_returns_all_when_none_deprecated**: 验证无废弃时返回所有模型

## 数据库查询

SQL 等效查询：
```sql
SELECT model_name 
FROM models 
WHERE deprecation IS NULL 
ORDER BY id;
```

## 注意事项

1. 该接口不需要任何参数
2. 只返回模型名称，不包含其他字段（如 id、concurrent_limit 等）
3. 过滤逻辑基于 `deprecation` 字段：只要该字段不为 `NULL`（即有任何值），该模型就会被排除
4. 返回结果按模型 ID 排序，保证顺序稳定
