class FakeJsonHttpClient:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get_json(self, url, *, params=None, headers=None):
        call = {"url": url, "params": params or {}, "headers": headers or {}}
        self.calls.append(call)
        return self.handler(url, params or {}, headers or {})
