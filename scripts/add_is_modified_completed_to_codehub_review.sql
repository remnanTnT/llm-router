-- 为 codehub_review 表新增 is_modified_completed 字段
-- 默认值为 false

ALTER TABLE codehub_review
ADD COLUMN is_modified_completed BOOLEAN DEFAULT FALSE;

-- 为已存在的记录设置默认值
UPDATE codehub_review
SET is_modified_completed = FALSE
WHERE is_modified_completed IS NULL;
