import urllib.request, urllib.error


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


op = urllib.request.build_opener(NoRedirect)
for u in [
    "http://127.0.0.1:8010/",
    "http://127.0.0.1:8010/landing/",
    "http://127.0.0.1:8010/dashboard/",
    "http://127.0.0.1:8010/accounts/login/",
]:
    try:
        r = op.open(u, timeout=20)
        body = r.read().decode("utf-8", "replace")
        title = ""
        if "<title>" in body:
            title = body.split("<title>")[1].split("</title>")[0]
        print(f"{u} -> {r.status} len={len(body)} title={title!r}")
    except urllib.error.HTTPError as e:
        print(f"{u} -> {e.code} Location={e.headers.get('Location')}")
