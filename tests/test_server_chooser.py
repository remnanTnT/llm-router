from dataclasses import dataclass

from router.services.server_chooser import LeastConnectionServerChooser, ServerSelectionContext


@dataclass
class Server:
    id: int
    base_url: str
    model_id: int | None = None


def make_server(server_id, base_url):
    return Server(id=server_id, base_url=base_url)


def make_context():
    return ServerSelectionContext(
        request_id=1,
        ip_id=None,
        model_id=None,
        model_name=None,
        path="chat/completions",
        method="POST",
        is_stream=False,
        body=b"{}",
    )


def test_least_connection_chooser_selects_server_with_fewest_processing_requests():
    chooser = LeastConnectionServerChooser(lambda targets: {"http://10.0.0.1:8000": 3, "http://10.0.0.2:8000": 1})
    candidates = [make_server(1, "http://10.0.0.1:8000"), make_server(2, "http://10.0.0.2:8000")]

    selected = chooser.choose(candidates, make_context(), set())

    assert selected.id == 2


def test_least_connection_chooser_skips_attempted_servers():
    chooser = LeastConnectionServerChooser(lambda targets: {"http://10.0.0.1:8000": 0, "http://10.0.0.2:8000": 1})
    candidates = [make_server(1, "http://10.0.0.1:8000"), make_server(2, "http://10.0.0.2:8000")]

    selected = chooser.choose(candidates, make_context(), {1})

    assert selected.id == 2


def test_least_connection_chooser_returns_none_when_all_attempted():
    chooser = LeastConnectionServerChooser(lambda targets: {})
    candidates = [make_server(1, "http://10.0.0.1:8000"), make_server(2, "http://10.0.0.2:8000")]

    assert chooser.choose(candidates, make_context(), {1, 2}) is None
