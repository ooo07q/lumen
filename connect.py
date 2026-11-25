"""Connections: the user's own Claude subscription (through Claude Code), their ChatGPT plan (Sign in with ChatGPT,
OpenAI's flow for open-source, locally run apps) and their own Jev key.

Rules this follows (checked 2026-11-25):
- Claude: the app has no login of its own and never touches Claude credentials, login links or codes. It installs
  Claude Code with Anthropic's own installer, starts the unmodified `claude auth login` in the background (output
  discarded: Claude Code opens Anthropic's sign-in page and receives the result itself; no other app is
  controlled), and reads only `claude auth status`. Usage is billed to the user's own plan.
- ChatGPT: OpenAI's documented open-source flow (developers.openai.com/siwc/token-sharing-open-source): PKCE in the
  system browser, redirect to http://127.0.0.1:<port>/auth/callback, tokens kept only on this Mac in a 0600 file,
  requests only to api.openai.com/v1 with store=false and stream=true. The Codex CLI's own login is never reused.
- Jev: the user's own TypeSafe key, kept in a 0600 file in the app data folder.
"""
import base64
import hashlib
import json
import os
import secrets
import shlex
import shutil
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

APP = None          # set by server.py
PORT = None         # the server's port (the ChatGPT redirect URI uses it)
APP_NAME = "Notes app"


def _ssl():
    ctx = ssl.create_default_context()
    if ctx.get_ca_certs() or ssl.get_default_verify_paths().cafile:
        return ctx
    for path in ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"):
        if os.path.exists(path):
            return ssl.create_default_context(cafile=path)
    return ctx


def write_private(path, text):
    """Write a file only this user can read (0600), atomically."""
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def http(url, data=None, headers=None, form=False, timeout=30):
    """(status, parsed JSON or text)."""
    body = None
    h = dict(headers or {})
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            h["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode("utf-8", "replace"), e.code
    try:
        return status, json.loads(raw) if raw.strip() else {}
    except ValueError:
        return status, raw


# ------------------------------------------------------------------ Claude (through Claude Code)

def claude_bin():
    for c in (shutil.which("claude"), os.path.expanduser("~/.local/bin/claude"), "/opt/homebrew/bin/claude",
              "/usr/local/bin/claude", os.path.expanduser("~/.claude/local/claude")):
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


CLAUDE_JOB = {"kind": None, "status": "idle", "out": "", "proc": None, "error": None, "started": 0}


# ------------------------------------------------------------------ one rule for all three: 連接 / 中斷連接
# 中斷連接 means the app stops using it. What the app owns (its ChatGPT sign-in, its Jev key) is deleted too; what it
# doesn't own (your Claude Code login, a Jev key in your environment or ~/.config/typesafe) is left as it is.

def _off_file():
    return os.path.join(APP, "connect_off.json")


def is_off(name):
    try:
        return name in json.load(open(_off_file(), encoding="utf-8"))
    except (OSError, ValueError):
        return False


def set_off(name, off):
    try:
        cur = set(json.load(open(_off_file(), encoding="utf-8")))
    except (OSError, ValueError):
        cur = set()
    (cur.add if off else cur.discard)(name)
    write_private(_off_file(), json.dumps(sorted(cur)))


def claude_status():
    exe = claude_bin()
    out = {"installed": bool(exe), "logged_in": False}
    if exe:
        try:
            v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
            out["version"] = v.stdout.strip().split(" ")[0]
            s = subprocess.run([exe, "auth", "status", "--json"], capture_output=True, text=True, timeout=30)
            d = json.loads(s.stdout or "{}")
            out.update({"logged_in": bool(d.get("loggedIn")), "method": d.get("authMethod"),
                        "plan": d.get("subscriptionType") or d.get("planTier"), "expires": d.get("loginExpiresAt")})
        except Exception as e:                   # noqa: BLE001 - reported to the page
            out["error"] = str(e)[:200]
    out["subscription"] = out.get("method") == "claude.ai"
    out["off"] = is_off("claude")
    out["connected"] = out["logged_in"] and not out["off"]
    j = CLAUDE_JOB
    if j["kind"] == "login" and j["status"] == "waiting":
        p = j.get("proc")
        if out["logged_in"]:
            j["status"] = "done"
            _stop_login()
        elif time.time() - j["started"] > 900:  # gave up in the browser: offer the button again
            _stop_login()
            j["status"] = "idle"
        elif p is not None and p.poll() is not None:
            j.update({"status": "error", "error": "登入沒有完成，請再按一次。", "proc": None})
    out["job"] = {"kind": j["kind"], "status": j["status"], "error": j["error"], "terminal": bool(j.get("terminal")),
                  "tail": j["out"][-300:] if j["kind"] == "install" and j["status"] == "error" else ""}
    return out


def _install():
    """Anthropic's recommended native installer, unmodified (code.claude.com/docs/en/setup); then straight on to
    sign-in, so connecting Claude is one click."""
    j = CLAUDE_JOB
    j.update({"kind": "install", "status": "running", "out": "", "error": None, "started": time.time()})
    try:
        p = subprocess.Popen(["/bin/bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             start_new_session=True)
        j["proc"] = p
        for line in p.stdout:
            j["out"] += line
        p.wait()
        j["proc"] = None
        if p.returncode == 0 and claude_bin():
            j["status"] = "done"
            claude_login()
        else:
            j.update({"status": "error", "error": "安裝沒有完成（代碼 %s）" % p.returncode})
    except Exception as e:                       # noqa: BLE001
        j.update({"status": "error", "error": str(e)[:300], "proc": None})


def claude_connect():
    """The one button: install Claude Code if it isn't there, then sign in."""
    if CLAUDE_JOB["status"] == "running":
        return 409, {"error": "正在安裝 Claude Code，請稍等"}
    set_off("claude", False)
    if claude_bin() and claude_status()["logged_in"]:    # already signed in to Claude Code: just use it again
        return 200, {"ok": True, "step": "done"}
    if not claude_bin():
        threading.Thread(target=_install, daemon=True).start()
        return 200, {"ok": True, "step": "install"}
    return claude_login()


def _stop_login():
    p = CLAUDE_JOB.get("proc")
    if p and CLAUDE_JOB["kind"] == "login" and p.poll() is None:
        import signal
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except OSError:
            p.terminate()
    CLAUDE_JOB["proc"] = None


def claude_login():
    """Sign-in happens entirely in Anthropic's own flow. The app starts the official, unmodified
    `claude auth login` in the background with no input and its output thrown away: Claude Code itself opens
    Anthropic's sign-in page in the browser and itself receives the result on its own local port. The app never
    sees a login link, code or token, and controls no other app (so macOS asks nothing). It only polls
    `claude auth status`."""
    exe = claude_bin()
    if not exe:
        return 400, {"error": "還沒安裝 Claude Code"}
    _stop_login()
    p = subprocess.Popen([exe, "auth", "login", "--claudeai"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    CLAUDE_JOB.update({"kind": "login", "status": "waiting", "error": None, "started": time.time(), "proc": p})
    return 200, {"ok": True, "step": "login"}


def claude_terminal():
    """The fallback when the browser didn't show the sign-in page: the same official command in a Terminal window
    the user works in. The app writes a one-line .command file and opens it (an ordinary file open, so macOS
    asks no permission to control Terminal); it never reads that window."""
    exe = claude_bin()
    if not exe:
        return 400, {"error": "還沒安裝 Claude Code"}
    _stop_login()
    path = os.path.join(APP, "Claude login.command")
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n%s auth login --claudeai\n" % shlex.quote(exe))
    os.chmod(path, 0o700)
    r = subprocess.run(["open", path], capture_output=True, text=True, timeout=30)
    if r.returncode:
        return 500, {"error": "打不開終端機：%s" % r.stderr.strip()[:200]}
    CLAUDE_JOB.update({"kind": "login", "status": "waiting", "error": None, "started": time.time(), "proc": None,
                       "terminal": True})
    return 200, {"ok": True}


def claude_disconnect():
    """The app stops using Claude. Your Claude Code login stays: you may use Claude Code elsewhere."""
    claude_cancel()
    set_off("claude", True)
    return 200, {"ok": True}


def claude_cancel():
    _stop_login()
    p = CLAUDE_JOB.get("proc")
    if p:
        import signal
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except OSError:
            p.terminate()
    CLAUDE_JOB.update({"status": "idle", "proc": None})
    return 200, {"ok": True}


# ------------------------------------------------------------------ ChatGPT (Sign in with ChatGPT, open-source flow)

AUTH = "https://auth.openai.com/api/accounts/authorize"
TOKEN = "https://auth.openai.com/api/accounts/oauth/token"
DISCOVERY = "https://auth.openai.com/.well-known/openid-configuration"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PENDING = {}        # state -> {verifier, nonce, client_id, redirect, started}
REFRESH_LOCK = threading.Lock()
REFRESH_FAIL = {"invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired",
                "refresh_token_invalidated", "refresh_token_reused"}


def b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def gpt_file():
    return os.path.join(APP, "chatgpt.json")


def gpt_load():
    try:
        return json.load(open(gpt_file(), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def gpt_save(d):
    write_private(gpt_file(), json.dumps(d, indent=1))


def host_id():
    """One id per Mac, reused for every sign-in (ext_agent_host_id)."""
    d = gpt_load()
    if not d.get("host_id"):
        import uuid
        d["host_id"] = "urn:uuid:" + str(uuid.uuid4())
        gpt_save(d)
    return d["host_id"]


def auth_url(retry=False):
    """The authorization URL for a fresh attempt (and its PKCE verifier, state and nonce, kept until the
    browser comes back)."""
    d = gpt_load()
    hid = host_id()
    verifier = b64u(secrets.token_bytes(48))
    state, nonce = b64u(secrets.token_bytes(24)), b64u(secrets.token_bytes(24))
    client_id = d.get("client_id") or "dynamic_agent_client"
    redirect = "http://127.0.0.1:%d/auth/callback" % PORT          # "Do not substitute with localhost."
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect, "scope": SCOPES,
         "resource": RESOURCE, "state": state, "nonce": nonce, "code_challenge_method": "S256",
         "code_challenge": b64u(hashlib.sha256(verifier.encode()).digest()), "ext_agent_host_id": hid}
    if client_id == "dynamic_agent_client":
        q["agent_name_hint"] = APP_NAME
    else:
        if d.get("id_token"):
            q["id_token_hint"] = d["id_token"]
    for k in [k for k, v in PENDING.items() if time.time() - v["started"] > 900]:
        PENDING.pop(k, None)
    PENDING[state] = {"verifier": verifier, "nonce": nonce, "client_id": client_id, "redirect": redirect,
                      "started": time.time(), "retry": retry}
    return AUTH + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)


def gpt_start():
    url = auth_url()
    subprocess.run(["open", url])               # the system browser, where the user is signed in to ChatGPT
    return 200, {"ok": True}


def verify_id_token(tok, client_id, nonce):
    """Claims of an ID token after checking its RS256 signature against OpenAI's published keys."""
    h, p, s = tok.split(".")
    header, claims = json.loads(unb64u(h)), json.loads(unb64u(p))
    if header.get("alg") != "RS256":
        raise ValueError("unexpected token algorithm")
    _, disc = http(DISCOVERY)
    _, jwks = http(disc["jwks_uri"])
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == header.get("kid")), None)
    if not key:
        raise ValueError("unknown signing key")
    n, e = int.from_bytes(unb64u(key["n"]), "big"), int.from_bytes(unb64u(key["e"]), "big")
    size = (n.bit_length() + 7) // 8
    em = pow(int.from_bytes(unb64u(s), "big"), e, n).to_bytes(size, "big")
    prefix = bytes.fromhex("3031300d060960864801650304020105000420")       # DigestInfo for SHA-256
    digest = hashlib.sha256((h + "." + p).encode()).digest()
    if em != b"\x00\x01" + b"\xff" * (size - 3 - len(prefix) - 32) + b"\x00" + prefix + digest:
        raise ValueError("bad token signature")
    aud = claims.get("aud")
    if claims.get("iss") != "https://auth.openai.com" or client_id not in (aud if isinstance(aud, list) else [aud]):
        raise ValueError("token not for this app")
    if claims.get("exp", 0) < time.time() or claims.get("nonce") != nonce:
        raise ValueError("token expired or replayed")
    return claims


def gpt_callback(q):
    """The browser comes back here from OpenAI. No cookie (it's a cross-site navigation): the one-time `state`
    is what ties it to the sign-in this app started. Returns (status, html), or (302, url) to send the browser
    straight on to a fresh authorization."""
    state = (q.get("state") or [""])[0]
    pend = PENDING.pop(state, None)
    if not pend:
        return 400, page("連接沒有完成", "這個登入連結已經用過或過期了。回到 app 再按一次「Continue with ChatGPT」。")
    if q.get("error"):
        return 200, page("沒有連接 ChatGPT", "你在 ChatGPT 的頁面沒有同意。回到 app 隨時可以再試。")
    issued = (q.get("client_id") or [""])[0] or pend["client_id"]
    if pend["client_id"] != "dynamic_agent_client" and issued != pend["client_id"]:
        return 400, page("連接沒有完成", "OpenAI 回傳的 app 編號和之前的不一樣，為了安全沒有接受。")
    if issued == "dynamic_agent_client":
        return 400, page("連接沒有完成", "OpenAI 沒有回傳這個 app 的編號。")
    d = gpt_load()
    if d.get("client_id") != issued:              # "retain the issued client_id" (never dynamic_agent_client)
        d["client_id"] = issued
        gpt_save(d)
    status, tok = http(TOKEN, {"grant_type": "authorization_code", "client_id": issued, "code": q["code"][0],
                               "code_verifier": pend["verifier"], "redirect_uri": pend["redirect"],
                               "resource": RESOURCE}, form=True)
    if isinstance(tok, dict) and tok.get("error") == "invalid_grant" and not pend.get("retry"):
        # OpenAI's docs: "discard that code and start a fresh authorization with the issued client ID retained
        # for this attempt". The user is already signed in, so the browser goes straight on.
        return 302, auth_url(retry=True)
    if status != 200 or not isinstance(tok, dict) or "access_token" not in tok:
        return 400, page("連接沒有完成", "換取登入憑證失敗（%s）：%s" % (status, str(tok)[:200]))
    try:
        claims = verify_id_token(tok["id_token"], issued, pend["nonce"]) if tok.get("id_token") else {}
    except Exception as e:                       # noqa: BLE001
        return 400, page("連接沒有完成", "登入憑證檢查失敗：%s" % e)
    d = gpt_load()
    d.update({"client_id": issued, "access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"),
              "id_token": tok.get("id_token"), "scope": tok.get("scope", ""),
              "expires_at": time.time() + int(tok.get("expires_in") or 3600),
              "email": claims.get("email"), "connected_at": time.time(), "welcomed": False})
    gpt_save(d)
    if "chatgpt.tokens.use.direct" not in d["scope"].split():
        return 200, page("已登入，但沒有方案使用權", "你登入了 ChatGPT，但沒有同意讓這個 app 使用你的 ChatGPT 方案。回到 app 可以再連接一次。")
    return 200, page("已連接 ChatGPT", "可以關掉這個分頁，回到 app。")


def page(title, text):
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>%s</title>"
            "<body style='font:16px -apple-system,sans-serif;max-width:520px;margin:80px auto;padding:0 16px;"
            "color:#222;background:#fafafa'><h2>%s</h2><p>%s</p>" % (title, title, text))


def gpt_token():
    """A valid access token, refreshed when near expiry; None when not connected."""
    with REFRESH_LOCK, open(gpt_file() + ".lock", "a") as lk:
        try:                                     # another app process may be refreshing: a refresh token is used once
            import fcntl
            fcntl.flock(lk, fcntl.LOCK_EX)
        except ImportError:                      # Windows: one process at a time is the norm there
            pass
        d = gpt_load()
        if not d.get("access_token"):
            return None
        if time.time() < d.get("expires_at", 0) - 120:
            return d["access_token"]
        if not d.get("refresh_token"):
            return None
        status, tok = http(TOKEN, {"grant_type": "refresh_token", "client_id": d["client_id"],
                                   "refresh_token": d["refresh_token"], "resource": RESOURCE}, form=True)
        if status == 200 and isinstance(tok, dict) and tok.get("access_token"):
            d.update({"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token") or d["refresh_token"],
                      "id_token": tok.get("id_token") or d.get("id_token"), "scope": tok.get("scope") or d.get("scope"),
                      "expires_at": time.time() + int(tok.get("expires_in") or 3600)})
            gpt_save(d)
            return d["access_token"]
        code = tok.get("error") if isinstance(tok, dict) else ""
        if code in REFRESH_FAIL:                 # sign in again with the saved client id
            for k in ("access_token", "refresh_token"):
                d.pop(k, None)
            gpt_save(d)
        return None


def gpt_status():
    d = gpt_load()
    out = {"connected": bool(d.get("access_token") or d.get("refresh_token")), "email": d.get("email"),
           "plan_use": "chatgpt.tokens.use.direct" in (d.get("scope") or "").split(),
           "welcome": bool(d.get("access_token")) and not d.get("welcomed")}
    return out


def gpt_models():
    """Check the connection without spending plan usage: the account's model catalogue."""
    t = gpt_token()
    if not t:
        return 400, {"error": "還沒連接 ChatGPT，或登入過期了"}
    status, r = http(RESOURCE + "/models", headers={"Authorization": "Bearer " + t})
    if status != 200 or not isinstance(r, dict):
        return 502, {"error": "OpenAI 回應 %s：%s" % (status, str(r)[:200])}
    rows = r.get("models") or r.get("data") or []          # the catalogue comes as {"models": [...]}
    models = [m.get("slug") or m.get("id") for m in rows if m.get("visibility", "list") == "list"]
    return 200, {"models": [m for m in models if m]}


def gpt_welcomed():
    d = gpt_load()
    d["welcomed"] = True
    gpt_save(d)
    return 200, {"ok": True}


def gpt_signout():
    d = gpt_load()
    if d.get("refresh_token") and d.get("client_id"):
        try:
            _, disc = http(DISCOVERY)
            if isinstance(disc, dict) and disc.get("revocation_endpoint"):
                http(disc["revocation_endpoint"], {"token": d["refresh_token"], "token_type_hint": "refresh_token",
                                                   "client_id": d["client_id"]}, form=True)
        except Exception:                        # noqa: BLE001 - cleared locally anyway
            pass
    for k in ("access_token", "refresh_token", "id_token", "scope", "expires_at", "email"):
        d.pop(k, None)
    gpt_save(d)                                  # client_id and host_id stay: the next sign-in reuses them
    return 200, {"ok": True}


# ------------------------------------------------------------------ Jev (the user's own TypeSafe key)

JEV_FILE_NAME = "jev_key"
JEV_SHARED = os.path.expanduser("~/.config/typesafe/api_key")


def jev_file():
    return os.path.join(APP, JEV_FILE_NAME)


def jev_load_into_env():
    """At start-up: the app's saved key becomes TYPESAFE_API_KEY for the app and the tools it runs."""
    try:
        k = open(jev_file(), encoding="utf-8").read().strip()
    except OSError:
        return
    if k:
        os.environ["TYPESAFE_API_KEY"] = k


def jev_status():
    if os.path.exists(jev_file()):
        src = "app"
    elif os.environ.get("TYPESAFE_API_KEY"):
        src = "env"
    elif os.path.exists(JEV_SHARED):
        src = "shared"
    else:
        src = None
    off = is_off("jev")
    return {"has_key": bool(src), "source": src, "off": off, "connected": bool(src) and not off}


def jev_test(key):
    status, r = http("https://api.typesafe.ai/v1/systemone",
                     {"model": "jev-latest", "state": "The sky is blue.",
                      "questions": {"t": {"type": "noul", "instructions": "Is the sky blue in the state?",
                                          "criteria": {"true": "Yes.", "false": "No."}}}},
                     headers={"Authorization": "Bearer " + key}, timeout=30)
    return status == 200 and isinstance(r, dict) and "answers" in r, status, r


def jev_save(body):
    key = str(body.get("key") or "").strip()
    if not key or len(key) > 500 or any(c.isspace() for c in key):
        return 400, {"error": "這不像一把金鑰"}
    ok, status, r = jev_test(key)
    if not ok:
        return 400, {"error": "Jev 不接受這把金鑰（%s）" % (status if status != 200 else str(r)[:100])}
    write_private(jev_file(), key)
    os.environ["TYPESAFE_API_KEY"] = key
    set_off("jev", False)
    return 200, {"ok": True}


def jev_connect():
    """連接 with a key already on this computer (environment or ~/.config/typesafe): use it again."""
    st = jev_status()
    if st["source"] in ("env", "shared"):
        set_off("jev", False)
        return 200, {"ok": True}
    return 200, {"ok": True, "need_key": True}


def jev_remove():
    """中斷連接: the app's own key is deleted; a key of yours elsewhere is left, and the app stops using it."""
    try:
        k = open(jev_file(), encoding="utf-8").read().strip()
        os.remove(jev_file())
        if os.environ.get("TYPESAFE_API_KEY") == k:
            del os.environ["TYPESAFE_API_KEY"]
    except OSError:
        pass
    set_off("jev", True)
    return 200, {"ok": True, "status": jev_status()}
