from router.services.opencode import OpencodeVersionService


def test_opencode_blocks_old_versions():
    blocked, version = OpencodeVersionService.should_block("foo opencode/1.2.26 bar")
    assert blocked is True
    assert version == "1.2.26"


def test_opencode_allows_newer_versions():
    blocked, version = OpencodeVersionService.should_block("opencode/1.2.27")
    assert blocked is False
    assert version == "1.2.27"


def test_opencode_delays_400_for_1_2_27_and_below_only():
    assert OpencodeVersionService.should_delay_upstream_400("opencode/1.2.27", 400) is True
    assert OpencodeVersionService.should_delay_upstream_400("opencode/1.2.28", 400) is False
    assert OpencodeVersionService.should_delay_upstream_400("opencode/1.2.27", 500) is False
