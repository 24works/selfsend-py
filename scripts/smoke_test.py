import http.client
import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PORT = 8799
SMTP_PORT = 11025
KEY = "re_smoketest_key_0123456789abcdef"

os.environ.update(
    {
        "SELFSEND_HOST": "127.0.0.1",
        "SELFSEND_PORT": str(PORT),
        "SELFSEND_LOG_LEVEL": "ERROR",
        "SELFSEND_API_KEYS": KEY,
        "SELFSEND_ALLOWED_FROM_DOMAINS": "example.com",
        "SELFSEND_RATE_LIMIT_PER_MINUTE": "6",
        "SMTP_HOST": "127.0.0.1",
        "SMTP_PORT": str(SMTP_PORT),
        "SMTP_STARTTLS": "false",
        "SMTP_SSL": "false",
    }
)


def _request(method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=15)
    payload = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers=headers or {})
    response = conn.getresponse()
    raw = response.read()
    conn.close()
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {"raw": raw.decode(errors="replace")}
    return response.status, data


def main():
    from aiosmtpd.controller import Controller

    envelopes = []

    class Sink:
        async def handle_DATA(self, server, session, envelope):
            envelopes.append(envelope)
            return "250 OK"

    controller = Controller(Sink(), hostname="127.0.0.1", port=SMTP_PORT)
    controller.start()

    import uvicorn

    from app.main import app

    config = uvicorn.Config(
        app, host="127.0.0.1", port=PORT, log_level="error", server_header=False
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        print("FAIL: uvicorn did not start")
        sys.exit(1)

    auth = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    valid_body = {
        "from": "Auth Service <noreply@example.com>",
        "to": ["receiver@destination.org"],
        "subject": "Smoke test",
        "html": "<p>hello from selfsend</p>",
    }

    results = []

    def check(name, condition, detail=""):
        results.append((name, bool(condition), detail))

    status, body = _request("GET", "/health")
    check("health 200", status == 200 and body.get("status") == "ok", f"{status} {body}")

    status, body = _request("POST", "/emails", valid_body)
    check("no auth -> 401", status == 401 and body.get("name") == "missing_api_key", f"{status} {body}")

    status, body = _request(
        "POST", "/emails", valid_body, {"Authorization": "Bearer re_wrong_key", "Content-Type": "application/json"}
    )
    check("wrong key -> 401", status == 401 and body.get("name") == "invalid_api_key", f"{status} {body}")

    status, body = _request(
        "POST", "/emails", valid_body, {"Authorization": "Token abc", "Content-Type": "application/json"}
    )
    check("bad scheme -> 401", status == 401, f"{status} {body}")

    status, body = _request("POST", "/emails", {"from": "a@example.com", "to": ["b@x.com"], "subject": "s"}, auth)
    check("no body -> 422", status == 422 and body.get("name") == "validation_error", f"{status} {body}")

    bad_to = dict(valid_body, to=["not-an-email"])
    status, body = _request("POST", "/emails", bad_to, auth)
    check("bad address -> 422", status == 422, f"{status} {body}")

    evil = dict(valid_body, **{"from": "Hacker <me@evil.com>"})
    status, body = _request("POST", "/emails", evil, auth)
    check("spoofed domain -> 403", status == 403 and body.get("name") == "sender_not_allowed", f"{status} {body}")

    status, body = _request("POST", "/emails", valid_body, {**auth, "Authorization": f"bearer {KEY}"})
    check("melody-auth style send -> 200", status == 200 and "id" in body, f"{status} {body}")

    time.sleep(0.5)
    if envelopes:
        env = envelopes[-1]
        content = env.content.decode(errors="replace") if isinstance(env.content, bytes) else str(env.content)
        check(
            "sink received message",
            env.mail_from == "noreply@example.com"
            and "receiver@destination.org" in env.rcpt_tos
            and "Smoke test" in content
            and "hello from selfsend" in content,
            f"from={env.mail_from} to={env.rcpt_tos}",
        )
    else:
        check("sink received message", False, "no envelope captured")

    status, body = _request("POST", "/emails", valid_body, auth)
    check("2nd send -> 200", status == 200, f"{status} {body}")
    for _ in range(4):
        status, body = _request("POST", "/emails", valid_body, auth)
    check("rate limit -> 429", status == 429 and body.get("name") == "rate_limit_exceeded", f"{status} {body}")

    server.should_exit = True
    controller.stop()

    failed = [name for name, ok, _ in results if not ok]
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}: {name} {detail if not ok else ''}")
    if failed:
        print(f"\n{len(failed)} check(s) failed")
        sys.exit(1)
    print(f"\nAll {len(results)} checks passed")


if __name__ == "__main__":
    main()
