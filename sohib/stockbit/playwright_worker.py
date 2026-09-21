"""Own one attached-browser operation. Only allowlisted API responses leave this process."""

import argparse
import asyncio
import json
import re
import signal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .api_routes import ORIGIN, citation, validate_api_path
from .contracts import ToolError

SEARCH = 'Search for brand, symbol or username...'
# Fixed literal. The route and body travel as data; the bearer is read inside the page from
# the SPA's own cookie store and never leaves the browser process.
FETCH_JSON = """async ([base, path, method, body, cookieName, tokenPath]) => {
  const headers = {'Accept': 'application/json'};
  const part = document.cookie.split(';').map(s => s.trim()).find(s => s.startsWith(cookieName + '='));
  if (part) {
    try {
      let value = part.slice(cookieName.length + 1);
      try { value = decodeURIComponent(value); } catch (e) {}
      let node = JSON.parse(value);
      for (const key of tokenPath) node = node == null ? null : node[key];
      if (typeof node === 'string' && node) headers['Authorization'] = 'Bearer ' + node;
    } catch (e) {}
  }
  const init = {method, headers, credentials: 'omit'};
  if (body !== null) { headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
  const res = await fetch(base + path, init);
  const text = await res.text();
  return {status: res.status, contentType: res.headers.get('content-type') || '',
          redirected: res.redirected, host: new URL(res.url).host,
          body: text.length > 2000000 ? null : text};
}"""
TOKEN_COOKIE = 'credentialStorage'
TOKEN_PATH = ['state', 'access', 'token']
STATUS_CODES = {400: 'NO_DATA', 401: 'AUTH_EXPIRED', 404: 'NO_DATA', 429: 'RATE_LIMITED'}
PROBE = """() => ({url:location.href,
login:!!document.querySelector('input[type=password]'),
challenge:/trusted-device|verification|verify|captcha|challenge/i.test(location.pathname) ||
 /verify you are human|verification code|kode verifikasi/i.test(document.body.innerText)})"""


def route(path):
    url = urlsplit(path)
    if url.scheme or url.netloc or url.fragment:
        raise ToolError('UNSUPPORTED_INPUT', 'Only internal research routes are accepted.')
    query = parse_qs(url.query)
    if url.path == '/search' and len(query.get('keyword', [])) == 1:
        return 'https://stockbit.com/stream', query['keyword'][0]
    if re.fullmatch(r'/keystats/ratio/v1/[A-Z0-9.-]{1,32}', url.path):
        return 'https://stockbit.com/symbol/' + url.path.rsplit('/', 1)[1] + '/keystats', None
    if path == '/screener/metric':
        return 'https://stockbit.com/screener', None
    raise ToolError('UNSUPPORTED_INPUT', 'Unsupported browser research route.')


def matches(response, path):
    expected, actual = urlsplit(path), urlsplit(response.url)
    return (
        response.request.method == 'GET'
        and actual.scheme == 'https'
        and actual.netloc == 'exodus.stockbit.com'
        and actual.path == expected.path
        and all(parse_qs(actual.query).get(k) == v for k, v in parse_qs(expected.query).items())
    )


async def check_page(page):
    state = await page.evaluate(PROBE)
    if state['challenge']:
        raise ToolError(
            'AUTH_CHALLENGE',
            'Complete Stockbit verification in the SohiB browser window, then retry.',
        )
    url = urlsplit(state['url'])
    if state['login'] or url.path.startswith('/login') or url.netloc != 'stockbit.com':
        raise ToolError(
            'AUTH_REQUIRED', 'Sign in to Stockbit in the SohiB browser window (sohib connect).'
        )


async def retrieve(page, path):
    target, query = route(path)
    responses = asyncio.Queue(maxsize=8)

    def observe(response):
        if matches(response, path) and not responses.full():
            responses.put_nowait(response)

    page.on('response', observe)
    try:
        if getattr(page, 'url', None) != target:
            await page.goto(target, wait_until='domcontentloaded', timeout=20000)
        elif query is None:
            # Statistics/taxonomy load with the page, unlike search's input action.
            await page.reload(wait_until='domcontentloaded', timeout=20000)
        await page.wait_for_function(
            'window.next && window.next.router && window.next.router.isReady', timeout=20000
        )
        await check_page(page)
        if query is not None:
            search = page.get_by_placeholder(SEARCH, exact=True)
            if await search.count() != 1:
                raise ToolError('SCHEMA_CHANGED', 'The Stockbit company search control changed.')
            await search.fill('')
            await search.fill(query)
        while True:
            await check_page(page)
            try:
                response = await asyncio.wait_for(responses.get(), timeout=0.25)
            except TimeoutError:
                continue
            if response.status != 200:
                code = {401: 'AUTH_EXPIRED', 403: 'FORBIDDEN', 429: 'RATE_LIMITED'}.get(
                    response.status, 'UPSTREAM_ERROR'
                )
                raise ToolError(code, 'Stockbit rejected the browser research request.')
            body = await response.body()
            if len(body) > 2_000_000:
                raise ToolError(
                    'SCHEMA_CHANGED', 'Browser research body exceeds the capture budget.'
                )
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ToolError('SCHEMA_CHANGED', 'Unexpected research response structure.')
            return {'payload': payload, 'source_url': target}
    finally:
        page.remove_listener('response', observe)


def classify(result):
    """Map an in-page response to the shared error taxonomy without echoing bodies."""
    status, content_type = result['status'], result['contentType'].lower()
    if result['redirected'] and result['host'] != urlsplit(ORIGIN).netloc:
        raise ToolError('AUTH_EXPIRED', 'Unexpected redirect; sign in again.')
    if status == 403:
        rejection = None
        if 'application/json' in content_type and result['body'] is not None:
            try:
                rejection = json.loads(result['body'])
            except ValueError:
                rejection = None
        if (
            isinstance(rejection, dict)
            and rejection.get('cloudflare_error') is True
            and rejection.get('error_code') == 1010
        ):
            raise ToolError(
                'FORBIDDEN',
                'Provider blocked the browser signature (Cloudflare 1010); no bypass is attempted.',
            )
        if 'text/html' in content_type:
            raise ToolError(
                'AUTH_CHALLENGE', 'Complete the provider verification shown in the browser.'
            )
        raise ToolError('FORBIDDEN', 'Provider rejected the research request.')
    if status != 200:
        code = STATUS_CODES.get(status, 'UPSTREAM_ERROR')
        detail = (
            'Provider reported no data for this request'
            if code == 'NO_DATA'
            else 'Provider rejected the research request'
        )
        raise ToolError(code, f'{detail} (HTTP {status}).')
    if result['body'] is None:
        raise ToolError('SCHEMA_CHANGED', 'Browser research body exceeds the capture budget.')
    if 'application/json' not in content_type:
        raise ToolError('AUTH_EXPIRED', 'Expected JSON; session may require sign-in.')
    payload = json.loads(result['body'])
    if not isinstance(payload, dict):
        raise ToolError('SCHEMA_CHANGED', 'Unexpected research response structure.')
    return payload


async def fetch_json(page, path, body=None):
    """Issue one allowlisted exodus request from the signed-in page's own JavaScript context."""
    from playwright.async_api import Error as BrowserError

    method = 'GET' if body is None else 'POST'
    path = validate_api_path(path, method)
    try:
        result = await page.evaluate(
            FETCH_JSON, [ORIGIN, path, method, body, TOKEN_COOKIE, TOKEN_PATH]
        )
    except BrowserError:
        # Network-level failure (CORS, offline, aborted). Its text is not research data.
        raise ToolError(
            'UPSTREAM_ERROR', 'In-page research request failed before a response arrived.'
        ) from None
    return classify(result)


async def run(args):
    return await attached_retrieve(args)


def connection_endpoint(path):
    try:
        settings = json.loads(Path(path).read_text())
        if 'devtools_file' in settings:
            port = Path(settings['devtools_file']).read_text().splitlines()[0]
            endpoint = 'http://127.0.0.1:' + str(int(port))
        else:
            endpoint = settings['endpoint']
        url = urlsplit(endpoint)
        if (
            url.scheme != 'http'
            or url.hostname not in {'127.0.0.1', 'localhost', '::1'}
            or not url.port
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {'', '/'}
        ):
            raise ValueError
        return endpoint
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        raise ToolError(
            'UPSTREAM_ERROR',
            'Existing browser connection is unavailable. Configure STOCKBIT_BROWSER_CONNECTION_FILE; no browser or login was started.',
        ) from None


async def attached_retrieve(args):
    from playwright.async_api import async_playwright

    endpoint = connection_endpoint(args.connection_file)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(endpoint, timeout=10000)
        pages = [
            page
            for context in browser.contexts
            for page in context.pages
            if urlsplit(page.url).scheme == 'https' and urlsplit(page.url).netloc == 'stockbit.com'
        ]
        if len(pages) != 1:
            raise ToolError(
                'UPSTREAM_ERROR',
                'Expected one existing Stockbit tab. Select a single Stockbit tab; no browser or login was started.',
            )
        await check_page(pages[0])
        # Playwright disconnects when its driver stops. Never close the user's browser/context.
        if not args.fetch:
            return await retrieve(pages[0], args.path[0])
        payloads = []
        for index, path in enumerate(args.path):
            body = args.body if index == 0 else None
            payloads.append(await fetch_json(pages[0], path, body))
        return {'payload': payloads[0], 'payloads': payloads, 'source_url': citation(args.path[0])}


async def bounded(args):
    from playwright.async_api import TimeoutError as BrowserTimeout

    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    try:
        loop.add_signal_handler(signal.SIGTERM, task.cancel)
    except (NotImplementedError, RuntimeError):
        pass  # Windows: the parent terminates the whole process tree instead.
    try:
        async with asyncio.timeout(args.timeout):
            return await run(args)
    except BrowserTimeout:
        raise ToolError(
            'TIMEOUT', 'Browser page or response did not become ready before the deadline.'
        ) from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--timeout', type=float, default=40)
    parser.add_argument('--path', action='append', required=True)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--body')
    parser.add_argument('--connection-file', required=True)
    args = parser.parse_args()
    try:
        args.body = json.loads(args.body) if args.body else None
        result = asyncio.run(bounded(args))
    except ToolError as error:
        result = {'error': {'code': error.code, 'message': str(error)}}
    except (asyncio.CancelledError, KeyboardInterrupt):
        result = {'error': {'code': 'CANCELLED', 'message': 'Browser operation cancelled.'}}
    except TimeoutError:
        result = {
            'error': {
                'code': 'TIMEOUT',
                'message': 'Browser operation exceeded its time budget; inspect login or page changes.',
            }
        }
    except (ValueError, KeyError, TypeError):
        result = {
            'error': {
                'code': 'SCHEMA_CHANGED',
                'message': 'Browser research response structure changed.',
            }
        }
    except Exception:
        result = {
            'error': {
                'code': 'UPSTREAM_ERROR',
                'message': 'Browser operation failed. Verify Playwright and Google Chrome are installed and inspect the browser.',
            }
        }
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
