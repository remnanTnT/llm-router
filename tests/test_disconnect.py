import threading

from router.services.disconnect import ClientDisconnectTracker, DisconnectWatcher


class FakeTracker:
    def __init__(self):
        self.calls = 0

    def client_disconnected(self):
        self.calls += 1
        return self.calls >= 2


def test_disconnect_watcher_sets_event_and_calls_callback_once():
    tracker = FakeTracker()
    disconnect_event = threading.Event()
    stop_event = threading.Event()
    calls = []

    watcher = DisconnectWatcher(tracker, disconnect_event, stop_event, lambda: calls.append(None), interval=0.01)
    watcher.start()
    watcher.join(timeout=1)

    assert disconnect_event.is_set()
    assert calls == [None]


def test_disconnect_watcher_stop_event_exits_without_disconnect():
    tracker = FakeTracker()
    disconnect_event = threading.Event()
    stop_event = threading.Event()
    calls = []

    watcher = DisconnectWatcher(tracker, disconnect_event, stop_event, calls.append, interval=0.05)
    watcher.start()
    stop_event.set()
    watcher.join(timeout=1)

    assert not disconnect_event.is_set()
    assert calls == []


def test_client_disconnect_tracker_without_socket_returns_false():
    tracker = ClientDisconnectTracker(None)
    assert tracker.client_disconnected() is False
