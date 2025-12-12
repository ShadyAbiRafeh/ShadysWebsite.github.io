import os
import re
import threading
import socket
import pathlib
import time
import http.server
import socketserver
from urllib.parse import urlparse, unquote

import requests
from bs4 import BeautifulSoup


ROOT = pathlib.Path(__file__).parent.resolve()


def read_html(path: pathlib.Path):
    with open(path, "r", encoding="utf-8") as f:
        return BeautifulSoup(f.read(), "html.parser")


def _is_external(href: str):
    return href.startswith("http://") or href.startswith("https://") or href.startswith("//")


def _is_mailto(href: str):
    return href.startswith("mailto:")


def _resolve_href(href: str, base: pathlib.Path):
    # Normalize and return the Path on disk if it's a relative/local path.
    # strip querystring / fragment
    parsed = urlparse(href)
    href_path = parsed.path
    if href_path.startswith("/"):
        # treat as relative to repo root
        return (ROOT / href_path.lstrip("/")).resolve()
    return (base.parent / href_path).resolve()


def test_index_exists():
    assert (ROOT / "index.html").exists(), "index.html should exist"


def test_basic_head_elements():
    soup = read_html(ROOT / "index.html")
    # Title
    assert soup.title is not None and soup.title.string.strip() != "", "Page should have a non-empty title"
    # Meta viewport
    assert soup.find("meta", attrs={"name": "viewport"}) or soup.find("meta", attrs={"name": "Viewport"}), "Page should include a viewport meta"


def test_css_assets_exist():
    soup = read_html(ROOT / "index.html")
    links = soup.find_all("link", rel="stylesheet")
    assert len(links) > 0, "At least one stylesheet should be linked"
    for l in links:
        href = l.get("href")
        if href and not _is_external(href):
            p = _resolve_href(href, ROOT / "index.html")
            assert p.exists(), f"CSS asset {href} should exist at {p}"


def test_js_assets_exist():
    soup = read_html(ROOT / "index.html")
    scripts = soup.find_all("script")
    assert len(scripts) > 0, "At least one script tag should be present"
    for s in scripts:
        src = s.get("src")
        if src and not _is_external(src):
            p = _resolve_href(src, ROOT / "index.html")
            assert p.exists(), f"JS asset {src} should exist at {p}"


def test_images_exist():
    soup = read_html(ROOT / "index.html")
    imgs = soup.find_all("img")
    for im in imgs:
        src = im.get("src")
        assert src is not None, "Image tags should have a src"
        if not _is_external(src):
            p = _resolve_href(src, ROOT / "index.html")
            assert p.exists(), f"Image {src} not found at {p}"


def test_background_images_in_css():
    # Parse css files for url(...) references and ensure they exist
    css_dir = ROOT / "assets" / "css"
    if not css_dir.exists():
        # no CSS dir: skip
        return
    pattern = re.compile(r"url\(['\"]?([^'\")]+)['\"]?\)")
    for css_file in css_dir.glob("**/*.css"):
        text = css_file.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            href = match.group(1)
            # skip data URIs and fragment-only SVG references
            parsed = urlparse(href)
            # decode percent-encoded chars (e.g. %23 => #)
            decoded_path = unquote(parsed.path or "")
            if href.strip().startswith("data:"):
                continue
            if href.strip().startswith("#") or decoded_path.startswith("#") or (parsed.path == "" and parsed.fragment):
                continue
            if _is_external(href):
                continue
            p = _resolve_href(href, css_file)
            assert p.exists(), f"CSS references image {href} but it does not exist at {p}"


def test_internal_links_exist():
    soup = read_html(ROOT / "index.html")
    anchors = soup.find_all("a", href=True)
    for a in anchors:
        href = a["href"].strip()
        if href == "" or href.startswith("#"):
            continue
        if _is_external(href) or _is_mailto(href):
            continue
        p = _resolve_href(href, ROOT / "index.html")
        assert p.exists() or (
            p.is_file() and p.exists()
        ), f"Link {href} should point to existing file {p}"


def _find_free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


def test_server_serves_assets():
    # Start a lightweight http server and check index and a few assets
    port = _find_free_port()
    handler = http.server.SimpleHTTPRequestHandler
    httpd = ThreadedHTTPServer(("127.0.0.1", port), handler)
    # serve from repo root
    orig_cwd = os.getcwd()
    os.chdir(str(ROOT))

    try:
        server_thread = threading.Thread(target=httpd.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        base_url = f"http://127.0.0.1:{port}"
        rs = requests.get(base_url + "/", timeout=5)
        assert rs.status_code == 200, "Server should return 200 for /"
        # test a small set of assets
        to_test = ["/", "/index.html", "/assets/css/main.css", "/assets/js/main.js"]
        for path in to_test:
            url = base_url + path
            r = requests.get(url, timeout=5)
            assert r.status_code == 200, f"{url} returned {r.status_code}"
    finally:
        httpd.shutdown()
        server_thread.join(timeout=2)
        os.chdir(orig_cwd)
