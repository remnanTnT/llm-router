from router.services.disconnect import ClientDisconnectTracker


class ClientDisconnectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.client_disconnect_tracker = ClientDisconnectTracker(request.META.get("gunicorn.socket"))
        return self.get_response(request)
