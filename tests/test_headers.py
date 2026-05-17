from router.utils.headers import filter_request_headers


def test_filter_request_headers_removes_hop_by_hop_and_proxy_invalid_headers():
    headers = {
        "Host": "example.com",
        "Connection": "keep-alive",
        "Authorization": "Bearer token",
        "Content-Length": "10",
        "Content-Encoding": "gzip",
        "Content-Type": "application/json",
    }
    filtered = filter_request_headers(headers, "POST")
    assert filtered == {"Authorization": "Bearer token", "Content-Type": "application/json"}


def test_filter_request_headers_removes_content_type_for_get():
    filtered = filter_request_headers({"Content-Type": "application/json", "Accept": "application/json"}, "GET")
    assert filtered == {"Accept": "application/json"}
