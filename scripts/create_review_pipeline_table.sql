-- 创建 review_pipeline 表
CREATE TABLE IF NOT EXISTS review_pipeline (
    id SERIAL PRIMARY KEY,
    project_name VARCHAR(200) NOT NULL,
    merge_requests_id INTEGER NOT NULL,
    merge_url TEXT NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    expert_model_id INTEGER NOT NULL,
    reflactor_model_id INTEGER NOT NULL,
    review_file_num INTEGER DEFAULT 0,
    diff_part_num INTEGER DEFAULT 0,
    review_num INTEGER DEFAULT 0,
    CONSTRAINT fk_expert_model FOREIGN KEY (expert_model_id) REFERENCES models(id),
    CONSTRAINT fk_reflactor_model FOREIGN KEY (reflactor_model_id) REFERENCES models(id)
);

-- 添加索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_review_pipeline_project ON review_pipeline(project_name);
CREATE INDEX IF NOT EXISTS idx_review_pipeline_mr_id ON review_pipeline(merge_requests_id);
CREATE INDEX IF NOT EXISTS idx_review_pipeline_start_time ON review_pipeline(start_time);
CREATE INDEX IF NOT EXISTS idx_review_pipeline_expert_model ON review_pipeline(expert_model_id);
CREATE INDEX IF NOT EXISTS idx_review_pipeline_reflactor_model ON review_pipeline(reflactor_model_id);

-- 添加注释
COMMENT ON TABLE review_pipeline IS 'Review pipeline 执行记录表';
COMMENT ON COLUMN review_pipeline.id IS '自增主键';
COMMENT ON COLUMN review_pipeline.project_name IS '项目名称';
COMMENT ON COLUMN review_pipeline.merge_requests_id IS 'MR ID';
COMMENT ON COLUMN review_pipeline.merge_url IS 'MR URL';
COMMENT ON COLUMN review_pipeline.start_time IS '开始时间';
COMMENT ON COLUMN review_pipeline.end_time IS '结束时间';
COMMENT ON COLUMN review_pipeline.expert_model_id IS '专家模型ID，关联models表';
COMMENT ON COLUMN review_pipeline.reflactor_model_id IS '重构模型ID，关联models表';
COMMENT ON COLUMN review_pipeline.review_file_num IS '评审文件数量';
COMMENT ON COLUMN review_pipeline.diff_part_num IS 'Diff部分数量';
COMMENT ON COLUMN review_pipeline.review_num IS '评审次数';
