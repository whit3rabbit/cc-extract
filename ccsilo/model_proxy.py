"""Architect Mode-only local model proxy for OAuth-backed Claude Code setups.

This proxy refuses every mode except ``architect``. It also requires a Claude
Code account: Claude model requests still rely on the user's normal Claude Code
OAuth/session path, while non-Claude model requests are forwarded to the
configured backend provider credential.
"""

import argparse
import http.client
import json
import os
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import urlsplit


ANTHROPIC_FALLBACK = "https://api.anthropic.com"
MODEL_PROXY_MODE = "architect"
MODEL_PATHS = {"/v1/messages"}
REQUEST_TIMEOUT_SECONDS = 300
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


@dataclass(frozen=True)
class ModelProxyConfig:
    mode: str
    backend_url: str
    backend_auth: str
    anthropic_url: str = ANTHROPIC_FALLBACK


class ModelProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, handler, *, config: ModelProxyConfig, api_key: str):
        super().__init__(server_address, handler)
        self.config = config
        self.api_key = api_key
        self.had_backend_session = False
        self.state_lock = threading.Lock()


def load_config(path: os.PathLike) -> ModelProxyConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("model proxy config must be a JSON object")
    config = ModelProxyConfig(
        mode=str(payload.get("mode") or ""),
        backend_url=str(payload.get("backendUrl") or payload.get("backend_url") or ""),
        backend_auth=str(payload.get("backendAuth") or payload.get("backend_auth") or ""),
        anthropic_url=str(payload.get("anthropicUrl") or payload.get("anthropic_url") or ANTHROPIC_FALLBACK),
    )
    validate_config(config)
    return config


def validate_config(config: ModelProxyConfig) -> None:
    if config.mode != MODEL_PROXY_MODE:
        raise ValueError("model proxy mode must be architect; this proxy is only for Architect Mode setups")
    if not config.backend_url:
        raise ValueError("model proxy backend_url is required")
    if config.backend_auth not in {"x-api-key", "bearer"}:
        raise ValueError("model proxy backend_auth must be x-api-key or bearer")
    for label, value in (("backend_url", config.backend_url), ("anthropic_url", config.anthropic_url)):
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"model proxy {label} must be an http(s) URL")


def start_model_proxy(
    config: ModelProxyConfig,
    *,
    api_key: str,
    host: str = "127.0.0.1",
    port: int = 0,
) -> ModelProxyServer:
    validate_config(config)
    if not api_key:
        raise ValueError("model proxy api key is required")
    return ModelProxyServer((host, port), _ModelProxyHandler, config=config, api_key=api_key)


def strip_all_thinking_blocks(body: Dict) -> None:
    messages = body.get("messages")
    if not isinstance(messages, list):
        return
    for message in messages:
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue
        message["content"] = [
            block
            for block in message["content"]
            if not (isinstance(block, dict) and block.get("type") == "thinking")
        ]


def strip_unsigned_thinking_blocks(body: Dict) -> None:
    messages = body.get("messages")
    if not isinstance(messages, list):
        return
    for message in messages:
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue
        message["content"] = [
            block
            for block in message["content"]
            if not (
                isinstance(block, dict)
                and block.get("type") == "thinking"
                and not block.get("signature")
            )
        ]


def normalize_json_body(data: bytes) -> bytes:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return data
    if isinstance(payload, dict) and payload.get("type") == "message" and not payload.get("usage"):
        payload["usage"] = {"input_tokens": 0, "output_tokens": 0}
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return data


class SseUsageNormalizer:
    def __init__(self):
        self.buffer = ""

    def feed(self, chunk: bytes) -> Iterable[bytes]:
        self.buffer += chunk.decode("utf-8", "replace")
        parts = self.buffer.split("\n\n")
        self.buffer = parts.pop()
        for part in parts:
            yield (self._fix_event(part) + "\n\n").encode("utf-8")

    def flush(self) -> Iterable[bytes]:
        if self.buffer.strip():
            yield (self._fix_event(self.buffer) + "\n\n").encode("utf-8")
        self.buffer = ""

    def _fix_event(self, event: str) -> str:
        for line in event.splitlines():
            if not line.startswith("data: "):
                continue
            raw = line[6:]
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return event
            if not isinstance(payload, dict):
                return event
            changed = False
            if payload.get("type") == "message_start" and isinstance(payload.get("message"), dict):
                message = payload["message"]
                if not isinstance(message.get("usage"), dict):
                    message["usage"] = {"input_tokens": 0, "output_tokens": 0}
                    changed = True
            if payload.get("type") == "message_delta" and not isinstance(payload.get("usage"), dict):
                payload["usage"] = {"output_tokens": 0}
                changed = True
            if changed:
                fixed = json.dumps(payload, separators=(",", ":"))
                return event.replace(raw, fixed, 1)
            return event
        return event


class _ModelProxyHandler(BaseHTTPRequestHandler):
    server: ModelProxyServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # pragma: no cover - keeps wrapper logs quiet
        return

    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def _proxy(self) -> None:
        path = urlsplit(self.path).path
        body = self._read_body()
        try:
            target_url, use_backend, body = self._prepare_target(path, body)
            self._forward(target_url, use_backend, body)
        except Exception as exc:
            self._send_json(502, {"error": {"message": f"model proxy upstream error: {exc}"}})

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("content-length") or "0")
        except ValueError:
            length = 0
        return self.rfile.read(length) if length else b""

    def _prepare_target(self, path: str, body: bytes) -> Tuple[str, bool, bytes]:
        is_model_call = path in MODEL_PATHS
        use_backend = False
        parsed_body = None
        if is_model_call and body:
            try:
                parsed_body = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed_body = None
            if isinstance(parsed_body, dict):
                model = str(parsed_body.get("model") or "")
                use_backend = bool(model and not model.startswith("claude-"))

        if use_backend:
            strip_all_thinking_blocks(parsed_body)
            body = json.dumps(parsed_body, separators=(",", ":")).encode("utf-8")
            with self.server.state_lock:
                self.server.had_backend_session = True
            return self.server.config.backend_url, True, body

        if is_model_call and isinstance(parsed_body, dict):
            with self.server.state_lock:
                had_backend_session = self.server.had_backend_session
            if had_backend_session:
                strip_all_thinking_blocks(parsed_body)
            else:
                strip_unsigned_thinking_blocks(parsed_body)
            body = json.dumps(parsed_body, separators=(",", ":")).encode("utf-8")
        return self.server.config.anthropic_url, False, body

    def _forward(self, target_url: str, use_backend: bool, body: bytes) -> None:
        target = urlsplit(target_url)
        upstream_path = _upstream_path(target.path, self.path)
        headers = _upstream_headers(self.headers.items(), target.netloc)
        if use_backend:
            headers.pop("authorization", None)
            headers.pop("x-api-key", None)
            if self.server.config.backend_auth == "bearer":
                headers["authorization"] = f"Bearer {self.server.api_key}"
            else:
                headers["x-api-key"] = self.server.api_key
        headers["content-length"] = str(len(body))

        conn_cls = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(target.hostname, target.port, timeout=REQUEST_TIMEOUT_SECONDS)
        try:
            conn.request(self.command, upstream_path, body=body, headers=headers)
            response = conn.getresponse()
            self._relay_response(response, use_backend)
        finally:
            conn.close()

    def _relay_response(self, response: http.client.HTTPResponse, use_backend: bool) -> None:
        content_type = response.getheader("content-type", "")
        if use_backend and "text/event-stream" in content_type:
            headers = _response_headers(response.getheaders(), omit_content_length=True)
            self._send_headers(response.status, response.reason, headers)
            normalizer = SseUsageNormalizer()
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                for fixed in normalizer.feed(chunk):
                    self.wfile.write(fixed)
                    self.wfile.flush()
            for fixed in normalizer.flush():
                self.wfile.write(fixed)
                self.wfile.flush()
            self.close_connection = True
            return

        raw = response.read()
        if use_backend and "application/json" in content_type:
            raw = normalize_json_body(raw)
        headers = _response_headers(response.getheaders(), content_length=len(raw))
        self._send_headers(response.status, response.reason, headers)
        self.wfile.write(raw)

    def _send_headers(self, status: int, reason: str, headers: Dict[str, str]) -> None:
        self.send_response(status, reason)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()

    def _send_json(self, status: int, payload: Dict) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _upstream_path(base_path: str, client_path: str) -> str:
    parsed_client = urlsplit(client_path)
    request_path = parsed_client.path or "/"
    base = (base_path or "").rstrip("/")
    if not base:
        full = request_path
    else:
        overlap = ""
        max_len = min(len(base), len(request_path))
        for size in range(1, max_len + 1):
            candidate = request_path[:size]
            if base.endswith(candidate):
                overlap = candidate
        full = base + request_path[len(overlap):] if overlap else base + request_path
    if parsed_client.query:
        full += "?" + parsed_client.query
    return full


def _upstream_headers(items, host: str) -> Dict[str, str]:
    headers = {}
    for key, value in items:
        lower = key.lower()
        if lower in HOP_BY_HOP_HEADERS:
            continue
        headers[lower] = value
    headers["host"] = host
    headers["accept-encoding"] = "identity"
    return headers


def _response_headers(items, *, content_length: Optional[int] = None, omit_content_length: bool = False) -> Dict[str, str]:
    headers = {}
    for key, value in items:
        lower = key.lower()
        if lower in HOP_BY_HOP_HEADERS:
            continue
        headers[key] = value
    if omit_content_length:
        headers.pop("content-length", None)
        headers.pop("Content-Length", None)
    elif content_length is not None:
        headers["content-length"] = str(content_length)
    return headers


def _parse_port(value: str) -> int:
    if value in {"", "auto"}:
        return 0
    port = int(value)
    if port < 1 or port > 65535:
        raise ValueError("port must be auto or an integer between 1 and 65535")
    return port


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the ccsilo Architect Mode-only local model proxy",
        epilog=(
            "Requires an architect config and a Claude Code account. Claude "
            "model calls continue through Claude Code OAuth/session auth; "
            "non-Claude model aliases are forwarded to the configured backend "
            "provider."
        ),
    )
    parser.add_argument("--config", required=True, help="Path to model proxy JSON config")
    parser.add_argument("--port", default="auto", help="Port number or auto")
    parser.add_argument("--port-file", required=True, help="File to write the selected port into")
    parser.add_argument("--api-key-env", default="CCSILO_MODEL_PROXY_API_KEY", help="Environment variable containing the backend API key")
    args = parser.parse_args(list(argv) if argv is not None else None)

    config = load_config(args.config)
    api_key = os.environ.get(args.api_key_env, "")
    server = start_model_proxy(config, api_key=api_key, port=_parse_port(args.port))
    port = int(server.server_address[1])
    port_file = Path(args.port_file)
    port_file.parent.mkdir(parents=True, exist_ok=True)
    port_file.write_text(f"{port}\n", encoding="utf-8")
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        time.sleep(0.05)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
