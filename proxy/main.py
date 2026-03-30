import os
import asyncio
import logging
import json
import uuid
from pathlib import Path

# Load .env file if present (and python-dotenv is installed)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from aiohttp import web, ClientSession
from aiohttp_socks import ProxyConnector  # Поддерживает HTTP, HTTPS, SOCKS4, SOCKS5

# Попытка импорта aiofiles для асинхронной записи логов
try:
    import aiofiles
except ImportError:
    aiofiles = None
    logging.warning("aiofiles not installed. Logs will be written synchronously.")

# ---------------------------- Configuration ------------------------------
LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "8080"))

# OpenAI API credentials
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY environment variable or in .env file")

# Base URL for the OpenAI‑compatible API (default: OpenAI official)
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# Proxy URL (optional). Supported schemes: http://, https://, socks4://, socks5://
PROXY_URL = os.getenv("PROXY_URL")  # e.g. "http://user:pass@proxy.example:8080"

# Hop‑by‑hop headers to remove
HOP_BY_HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"
}

# Directory for request/response logs
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# -------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("openai-proxy")


def decode_body(body_bytes: bytes, content_type: str = None):
    """Пытается декодировать тело в JSON или строку."""
    if not body_bytes:
        return None
    try:
        text = body_bytes.decode('utf-8')
        obj = json.loads(text)
        return obj
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body_bytes.decode('utf-8', errors='replace')


async def ensure_dir(dir_path: Path):
    """Асинхронно создаёт директорию, если её нет."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: dir_path.mkdir(parents=True, exist_ok=True))


async def save_request(request_id: str, method: str, url: str, headers: dict, body_bytes: bytes):
    """Асинхронно сохраняет запрос в logs/<uuid>/request.json."""
    safe_headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
    content_type = headers.get("Content-Type")
    body = decode_body(body_bytes, content_type)

    data = {
        "id": request_id,
        "type": "request",
        "method": method,
        "url": url,
        "headers": safe_headers,
        "content_type": content_type,
        "body": body
    }

    dir_path = LOG_DIR / request_id
    await ensure_dir(dir_path)
    file_path = dir_path / "request.json"

    if aiofiles:
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: open(file_path, 'w', encoding='utf-8').write(json.dumps(data, indent=2, ensure_ascii=False))
        )


async def save_response(request_id: str, status: int, headers: dict, body_bytes: bytes):
    """Асинхронно сохраняет ответ в logs/<uuid>/response.json."""
    safe_headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
    content_type = headers.get("Content-Type")
    body = decode_body(body_bytes, content_type)

    data = {
        "id": request_id,
        "type": "response",
        "status": status,
        "headers": safe_headers,
        "content_type": content_type,
        "body": body
    }

    dir_path = LOG_DIR / request_id
    await ensure_dir(dir_path)
    file_path = dir_path / "response.json"

    if aiofiles:
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: open(file_path, 'w', encoding='utf-8').write(json.dumps(data, indent=2, ensure_ascii=False))
        )


async def proxy_handler(request: web.Request) -> web.StreamResponse:
    """Handle all incoming requests and proxy them to the OpenAI‑compatible API."""
    request_id = str(uuid.uuid4())

    # Build target URL
    path = request.path
    # If the base URL already contains "/v1" (e.g. https://api.openai.com/v1),
    # remove a leading "/v1" from the path to avoid duplication.
    if OPENAI_BASE_URL.rstrip('/').endswith('/v1') and path.startswith('/v1/'):
        path = path[3:]  # remove the "/v1" prefix
    target_url = OPENAI_BASE_URL.rstrip('/') + path
    if request.query_string:
        target_url += f"?{request.query_string}"

    log.info(f"[{request_id}] Proxying {request.method} {request.path} -> {target_url}")

    # Read request body
    body_bytes = await request.read()

    # Save request asynchronously
    asyncio.create_task(save_request(
        request_id,
        request.method,
        target_url,
        dict(request.headers),
        body_bytes
    ))

    # Prepare headers for upstream
    headers = dict(request.headers)
    for h in HOP_BY_HOP_HEADERS:
        headers.pop(h, None)
    headers.pop("Host", None)
    headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"

    # Create connector with proxy if needed
    connector = None
    if PROXY_URL:
        connector = ProxyConnector.from_url(PROXY_URL)

    try:
        async with ClientSession(connector=connector) as session:
            async with session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=body_bytes,
                ssl=True
            ) as upstream_resp:
                # Prepare response for client
                resp_headers = {k: v for k, v in upstream_resp.headers.items()
                                if k.lower() not in HOP_BY_HOP_HEADERS}
                resp = web.StreamResponse(status=upstream_resp.status, headers=resp_headers)
                resp.headers.pop("Transfer-Encoding", None)
                await resp.prepare(request)

                response_body = bytearray()

                # Stream response to client and accumulate for logging
                async for chunk in upstream_resp.content.iter_any():
                    response_body.extend(chunk)
                    await resp.write(chunk)

                # Save response asynchronously
                asyncio.create_task(save_response(
                    request_id,
                    upstream_resp.status,
                    upstream_resp.headers,
                    bytes(response_body)
                ))

                return resp

    except Exception as e:
        log.exception(f"[{request_id}] Error forwarding request")
        error_body = f"Proxy error: {e}".encode('utf-8')
        asyncio.create_task(save_response(
            request_id,
            502,
            {"Content-Type": "text/plain"},
            error_body
        ))
        return web.Response(status=502, text=f"Proxy error: {e}")


async def main():
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", proxy_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=LISTEN_HOST, port=LISTEN_PORT)
    await site.start()

    log.info(f"Reverse proxy listening on {LISTEN_HOST}:{LISTEN_PORT}")
    log.info(f"OpenAI API base URL: {OPENAI_BASE_URL}")
    if PROXY_URL:
        log.info(f"Using proxy: {PROXY_URL}")
    else:
        log.info("No proxy configured")
    log.info(f"Logs will be saved in: {LOG_DIR.absolute()}")
    log.info("Press Ctrl+C to stop")

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
