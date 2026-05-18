from router.repositories.requests import RequestRepository


def test_record_attempt_persists_prefix_cache_and_last_match():
    record = RequestRepository.create_processing(
        ip_id=1,
        model_id=7,
        is_stream=False,
        user_agent="pytest",
    )

    RequestRepository.record_attempt(
        record,
        target_pod_ip="http://10.0.0.1:8000",
        attempt_count=1,
        prefix_cache=0.75,
        last_match=12345,
    )

    record.refresh_from_db()

    assert record.target_pod_ip == "http://10.0.0.1:8000"
    assert record.attempt_count == 1
    assert record.prefix_cache == 0.75
    assert record.last_match == 12345


def test_record_attempt_clears_last_match_when_no_match():
    record = RequestRepository.create_processing(
        ip_id=1,
        model_id=7,
        is_stream=False,
        user_agent="pytest",
    )
    record.last_match = 12345
    record.save(update_fields=["last_match"])

    RequestRepository.record_attempt(
        record,
        target_pod_ip="http://10.0.0.1:8000",
        attempt_count=1,
        prefix_cache=0.0,
        last_match=None,
    )

    record.refresh_from_db()

    assert record.last_match is None
