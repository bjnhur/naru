from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from watchfiles import watch

from naru.config import load_config
from naru.serve import PreviewHandler, is_source_change, serve

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_engine_import_does_not_require_site_environment(self) -> None:
        env = os.environ.copy()
        env.pop("NARU_SITE_ROOT", None)
        env.pop("NARU_OUTPUT_DIR", None)
        env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        result = subprocess.run(
            [sys.executable, "-c", "import naru.engine.build, naru.engine.loader"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        return subprocess.run(
            [sys.executable, "-m", "naru", *args],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_version_option(self) -> None:
        with (PROJECT_ROOT / "pyproject.toml").open("rb") as config:
            version = tomllib.load(config)["project"]["version"]
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), f"naru {version}")

    def test_no_arguments_prints_help(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage: naru", result.stdout)

    def test_build_rejects_missing_site_root(self) -> None:
        result = self.run_cli(
            "build",
            "--site-root",
            str(PROJECT_ROOT / "missing-site"),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("site root does not exist", result.stderr)

    def test_preview_serves_configured_base_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text("hello", encoding="utf-8")
            (root / "page").mkdir()
            (root / "page" / "index.html").write_text("page", encoding="utf-8")
            handler = partial(
                PreviewHandler, directory=str(root), base_path={"value": "/notes"}
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                address = f"http://127.0.0.1:{server.server_port}"
                with urlopen(address + "/notes/") as response:
                    self.assertEqual(response.read(), b"hello")
                with urlopen(address + "/notes/page") as response:
                    self.assertTrue(response.geturl().endswith("/notes/page/"))
                    self.assertEqual(response.read(), b"page")
                with self.assertRaises(HTTPError) as error:
                    urlopen(address + "/")
                self.assertEqual(error.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_preview_rebuilds_sources_and_recovers_after_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.assertTrue(is_source_change(root, str(root / "content" / "post.md")))
            self.assertTrue(is_source_change(root, str(root / "naru.yml")))
            self.assertFalse(is_source_change(root, str(root / "docs" / "index.html")))

            def changes():
                yield {(1, str(root / "docs" / "index.html"))}
                yield {(1, str(root / "content" / "post.md"))}
                yield {(1, str(root / "naru.yml"))}
                raise KeyboardInterrupt

            settings = {"base_url": ""}
            with (
                patch("naru.serve.watch", return_value=changes()),
                patch("naru.serve.load_config", return_value=settings) as load,
                patch(
                    "naru.serve.build", side_effect=[None, ValueError("bad"), None]
                ) as build,
                redirect_stderr(io.StringIO()) as stderr,
                redirect_stdout(io.StringIO()),
            ):
                serve(root, settings, {}, "127.0.0.1", 0, False, False)
            self.assertEqual(load.call_count, 2)
            self.assertEqual(build.call_count, 3)
            self.assertIn("Rebuild failed: bad", stderr.getvalue())

    def test_preview_rebuilds_after_real_file_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "naru.yml").write_text(
                "site_name: Test\nsite_origin: https://example.com\n", encoding="utf-8"
            )
            posts = root / "content" / "posts"
            posts.mkdir(parents=True)
            post = posts / "hello.md"
            post.write_text(
                "---\ntitle: First\nnav_title: First\nslug: hello\n"
                "description: Example\npublished_date: 2020-01-01\n"
                "updated_date: 2020-01-01\ntags: []\n---\n본문\n",
                encoding="utf-8",
            )
            ready = Event()
            stop = Event()
            servers = []

            def observed_watch(path):
                for changes in watch(
                    path, stop_event=stop, yield_on_timeout=True,
                    rust_timeout=500, debounce=100, step=50,
                ):
                    ready.set()
                    yield changes

            def create_server(*args, **kwargs):
                server = ThreadingHTTPServer(*args, **kwargs)
                servers.append(server)
                return server

            thread = Thread(
                target=serve,
                args=(
                    root, load_config(root / "naru.yml"), {}, "127.0.0.1", 0,
                    False, False,
                ),
                daemon=True,
            )
            with (
                patch("naru.serve.watch", observed_watch),
                patch("naru.serve.ThreadingHTTPServer", create_server),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                thread.start()
                try:
                    self.assertTrue(ready.wait(10), "file watcher did not start")
                    address = f"http://127.0.0.1:{servers[0].server_port}/posts/hello/"
                    with urlopen(address) as response:
                        self.assertIn("First", response.read().decode("utf-8"))
                    post.write_text(
                        post.read_text(encoding="utf-8").replace("First", "Second"),
                        encoding="utf-8",
                    )
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        with urlopen(address) as response:
                            if "Second" in response.read().decode("utf-8"):
                                break
                        stop.wait(0.1)
                    else:
                        self.fail("preview did not rebuild after source change")
                finally:
                    stop.set()
                    thread.join(timeout=10)
                self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
