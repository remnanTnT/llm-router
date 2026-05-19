CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_requests_concurrent_count
ON requests (ip_id, model_id)
WHERE task_status = 'processing';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_req_proc_model_send
ON requests (model_id, send_time)
WHERE task_status = 'processing';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_requests_processing_target
ON requests (target_pod_ip)
WHERE task_status = 'processing';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_requests_success_send
ON requests (send_time)
WHERE task_status = 'success';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_req_succ_model_send
ON requests (model_id, send_time)
WHERE task_status = 'success';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_requests_model_send_ip
ON requests (model_id, send_time, ip_id)
WHERE ip_id IS NOT NULL;
