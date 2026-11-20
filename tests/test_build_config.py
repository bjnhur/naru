from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as etree

import yaml

from naru.cli import main
from naru.config import BuildConfig, ConfigError, load_config
from naru.engine.ads import render_ad, render_infeed_ad
from naru.engine.config import use_config
from naru.engine.templates import current_templates, use_templates

EXAMPLE_CONFIG = (
    Path(__file__).resolve().parents[1] / "examples" / "basic-site" / "naru.yml"
)


class BuildConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "site"
        self.root.mkdir()
        self.config = self.root / "naru.yml"
        data = yaml.safe_load(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
        data["site_origin"] = "https://example.com"
        self.config.write_text(yaml.safe_dump(data), encoding="utf-8")
        for path in (
            self.root / "content" / "posts",
            self.root / "templates",
            self.root / "static" / "tools",
        ):
            path.mkdir(parents=True)

    def test_invalid_or_unknown_configuration_is_rejected(self) -> None:
        data = yaml.safe_load(self.config.read_text(encoding="utf-8"))
        data["site_origin"] = "https://example.com/a-path"
        self.config.write_text(yaml.safe_dump(data), encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "site_origin"):
            load_config(self.config)
        data["site_origin"] = "https://example.com"
        data["typo"] = True
        self.config.write_text(yaml.safe_dump(data), encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "unknown fields: typo"):
            load_config(self.config)

    def test_minimal_configuration_uses_site_specific_defaults(self) -> None:
        self.config.write_text(
            "site_name: Test Site\nsite_origin: https://example.com\n",
            encoding="utf-8",
        )
        data = load_config(self.config)
        self.assertEqual(data["site_tagline"], "Test Site")
        self.assertEqual(data["rss_title"], "Test Site")
        self.assertEqual(data["author_name"], "Test Site")
        self.assertEqual(data["home_max_ads"], 0)
        self.assertEqual(data["posts_url_prefix"], "/posts")
        self.config.write_text("site_name: Test Site\n", encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "missing fields: site_origin"):
            load_config(self.config)
        self.config.write_text(
            "site_name: Test Site\nsite_origin: https://example.com\n"
            "posts_per_page: null\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ConfigError, "posts_per_page"):
            load_config(self.config)

    def test_build_url_overrides_are_validated(self) -> None:
        settings = load_config(
            self.config,
            overrides={"site_origin": "https://pages.example", "base_url": "/project"},
        )
        self.assertEqual(settings["site_origin"], "https://pages.example")
        self.assertEqual(settings["base_url"], "/project")
        with self.assertRaisesRegex(ConfigError, "site_origin"):
            load_config(
                self.config, overrides={"site_origin": "https://example.com/path"}
            )

    def test_theme_defaults_and_token_overrides(self) -> None:
        self.config.write_text(
            "site_name: Test\nsite_origin: https://example.com\n", encoding="utf-8"
        )
        self.assertEqual(load_config(self.config)["theme"]["preset"], "default")
        theme = load_config(self.config, overrides={"theme": {
            "preset": "docs", "accent_color": "#123456", "content_width": "60rem",
        }})["theme"]
        self.assertEqual(theme["accent_color"], "#123456")
        self.assertEqual(theme["accent_hover"], "#065f59")
        self.assertEqual(theme["content_width"], "60rem")

    def test_invalid_theme_settings_are_rejected(self) -> None:
        for theme in (
            None, [], {"preset": []}, {"preset": "missing"}, {"typo": "red"},
            {"accent_color": "red; } body { display: none"},
            {"font_family": "sans-serif; color: red"},
            {"content_width": "100%"}, {"custom_css": "extra.css"},
            {"custom_css": ["../outside.css"]}, {"custom_css": ["missing.css"]},
            {"custom_css": ["https://example.com/style.css"]},
        ):
            with (
                self.subTest(theme=theme),
                self.assertRaisesRegex(ConfigError, "theme"),
            ):
                load_config(self.config, overrides={"theme": theme})

    def test_theme_stylesheets_are_ordered_versioned_and_rebuilt(self) -> None:
        (self.root / "static" / "tools").rmdir()
        styles = self.root / "static" / "styles"
        styles.mkdir()
        custom = styles / "site style.css"
        custom.write_text("a { text-decoration: none; }", encoding="utf-8")
        self.config.write_text(
            "site_name: Test\nsite_origin: https://example.com\nbase_url: /notes\n"
            "theme:\n  preset: docs\n  accent_color: '#123456'\n"
            "  custom_css:\n    - styles/site style.css\n",
            encoding="utf-8",
        )
        args = ["build", "--site-root", str(self.root), "--output", "output"]
        self.assertEqual(main(args), 0)
        output = self.root / "output"
        home = (output / "index.html").read_text(encoding="utf-8")
        themed = (output / "assets" / "naru-theme.css").read_text(encoding="utf-8")
        self.assertIn("--naru-accent-color: #123456;", themed)
        self.assertIn("--naru-content-width: 64rem;", themed)
        urls = ["/notes/assets/naru.css?v=", "/notes/assets/naru-theme.css?v=",
                "/notes/styles/site%20style.css?v="]
        self.assertLess(home.index(urls[0]), home.index(urls[1]))
        self.assertLess(home.index(urls[1]), home.index(urls[2]))
        old_version = hashlib.sha256(custom.read_bytes()).hexdigest()[:12]
        self.assertIn(f"{urls[2]}{old_version}", home)
        custom.write_text("a { text-decoration: underline; }", encoding="utf-8")
        self.assertEqual(main(args), 0)
        rebuilt = (output / "index.html").read_text(encoding="utf-8")
        self.assertNotIn(f"{urls[2]}{old_version}", rebuilt)
        self.assertEqual(
            (output / "styles" / custom.name).read_bytes(), custom.read_bytes()
        )
        self.config.write_text(
            "site_name: Test\nsite_origin: https://example.com\n", encoding="utf-8"
        )
        self.assertEqual(main(args), 0)
        reset = (output / "assets" / "naru-theme.css").read_text(encoding="utf-8")
        self.assertIn("--naru-accent-color: #2459a6;", reset)
        self.assertNotIn("site%20style.css", (output / "index.html").read_text("utf-8"))

    def test_check_validates_without_changing_site_output(self) -> None:
        (self.root / "static" / "tools").rmdir()
        output = self.root / "docs"
        output.mkdir()
        sentinel = output / "index.html"
        sentinel.write_text("keep", encoding="utf-8")
        self.assertEqual(main(["check", "--site-root", str(self.root)]), 0)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
        self.assertFalse((output / ".naru-output").exists())

    def test_casper_example_builds_with_project_paths(self) -> None:
        site = EXAMPLE_CONFIG.parents[1] / "casper-site"
        output = self.root / "casper-output"
        self.assertEqual(main([
            "build", "--site-root", str(site), "--output", str(output),
            "--site-origin", "https://example.com", "--base-url", "/journal",
        ]), 0)
        home = (output / "index.html").read_text(encoding="utf-8")
        self.assertIn("journal-featured", home)
        self.assertEqual(home.count('class="journal-story-body"'), 3)
        self.assertIn("/journal/images/notebook.jpg", home)
        self.assertIn("/journal/styles/casper.css?v=", home)
        self.assertIn("/journal/posts/a-place-to-begin/", home)
        post = (output / "posts" / "a-place-to-begin" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('class="journal-prose"', post)
        self.assertIn("/journal/images/notebook.jpg", post)
        for name in ("notebook.jpg", "writing.jpg", "workspace.jpg"):
            self.assertTrue((output / "images" / name).is_file())

    def test_korean_addresses_and_publication_policy(self) -> None:
        self.config.write_text(
            "site_name: Test\nsite_origin: https://example.com\nbase_url: /notes\n"
            "category_redirects:\n  notes: 개발\n",
            encoding="utf-8",
        )
        (self.root / "static" / "tools").rmdir()
        posts = self.root / "content" / "posts" / "개발"
        posts.mkdir()
        template = (
            "---\ntitle: {title}\nnav_title: {title}\nslug: {slug}\n"
            "description: 설명\npublished_date: {date}\nupdated_date: {date}\n"
            "tags: []\n{extra}---\n본문\n"
        )
        for slug, date, extra in (
            ("한글-문서", "2020-01-01", ""),
            ("draft", "2020-01-01", "draft: true\n"),
            ("future", "9999-01-01", ""),
        ):
            (posts / f"{slug}.md").write_text(
                template.format(title=slug, slug=slug, date=date, extra=extra),
                encoding="utf-8",
            )
        self.assertEqual(
            main(["build", "--site-root", str(self.root), "--output", "output"]), 0
        )
        output = self.root / "output"
        self.assertTrue((output / "posts" / "한글-문서" / "index.html").is_file())
        self.assertTrue((output / "category" / "개발" / "index.html").is_file())
        redirect = (output / "category" / "notes" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("/notes/category/%EA%B0%9C%EB%B0%9C/", redirect)
        self.assertFalse((output / "posts" / "draft").exists())
        self.assertFalse((output / "posts" / "future").exists())
        sitemap = (output / "sitemap.xml").read_text(encoding="utf-8")
        feed = (output / "rss.xml").read_text(encoding="utf-8")
        self.assertIn("/notes/posts/%ED%95%9C%EA%B8%80-%EB%AC%B8%EC%84%9C/", sitemap)
        self.assertNotIn("/draft/", sitemap)
        self.assertNotIn("/future/", sitemap)
        self.assertNotIn("/draft/", feed)
        self.assertNotIn("/future/", feed)
        self.assertEqual(
            main([
                "build", "--site-root", str(self.root), "--output", "preview",
                "--include-drafts", "--include-future",
            ]),
            0,
        )
        preview = self.root / "preview"
        self.assertTrue((preview / "posts" / "draft" / "index.html").is_file())
        self.assertTrue((preview / "posts" / "future" / "index.html").is_file())
        preview_feed = (preview / "rss.xml").read_text(encoding="utf-8")
        self.assertIn("/draft/", preview_feed)
        self.assertIn("/future/", preview_feed)

    def test_home_and_archive_partials_can_be_customized(self) -> None:
        (self.root / "static" / "tools").rmdir()
        post = self.root / "content" / "posts" / "hello.md"
        post.write_text(
            "---\ntitle: 'Hello <world>'\nnav_title: Hello\nslug: hello\n"
            "description: Example\npublished_date: 2020-01-01\n"
            "updated_date: 2020-01-01\ncategory: blog\ntags: []\n---\n본문\n",
            encoding="utf-8",
        )
        templates = self.root / "templates"
        (templates / "template_index.html").write_text(
            "{{ HOME_CONTENT_SECTIONS }}", encoding="utf-8"
        )
        (templates / "partial_home_groups.html").write_text(
            "{% for group in home_groups %}{% for category in group.categories %}"
            "{% for item in category['items'] %}<strong>{{ item.title }}</strong>"
            "{% endfor %}{% endfor %}{% endfor %}",
            encoding="utf-8",
        )
        (templates / "partial_archive_items.html").write_text(
            "{% for entry in archive_entries %}"
            "<b>{{ entry.item.title }}</b>{% endfor %}",
            encoding="utf-8",
        )
        self.assertEqual(
            main(["build", "--site-root", str(self.root), "--output", "output"]), 0
        )
        output = self.root / "output"
        home = (output / "index.html").read_text(encoding="utf-8")
        archive = (output / "posts" / "index.html").read_text(encoding="utf-8")
        self.assertIn("<strong>Hello &lt;world&gt;</strong>", home)
        self.assertIn("<b>Hello &lt;world&gt;</b>", archive)

    def test_post_metadata_is_escaped_and_can_be_customized(self) -> None:
        (self.root / "static" / "tools").rmdir()
        data = yaml.safe_load(self.config.read_text(encoding="utf-8"))
        data["author_name"] = "Writer <b>"
        data["author_note_default"] = "Note <i>"
        self.config.write_text(yaml.safe_dump(data), encoding="utf-8")
        (self.root / "content" / "posts" / "hello.md").write_text(
            "---\ntitle: 'Hello <world>'\nnav_title: Hello\nslug: hello\n"
            "description: Example\npublished_date: 2020-01-01\n"
            "updated_date: 2020-01-01\ncategory: blog\ntags: ['A <tag>']\n"
            "---\nBody\n\n## A heading\n", encoding="utf-8",
        )
        (self.root / "content" / "posts" / "other.md").write_text(
            "---\ntitle: 'Other <world>'\nnav_title: Other\nslug: other\n"
            "description: Example\npublished_date: 2020-01-01\n"
            "updated_date: 2020-01-01\ncategory: blog\ntags: []\n---\nOther\n",
            encoding="utf-8",
        )
        args = ["build", "--site-root", str(self.root), "--output", "output"]
        self.assertEqual(main(args), 0)
        output = self.root / "output" / "posts" / "hello" / "index.html"
        rendered = output.read_text(encoding="utf-8")
        self.assertIn("작성: Writer &lt;b&gt;", rendered)
        self.assertIn("A &lt;tag&gt;</a>", rendered)
        self.assertNotIn("A &amp;lt;tag&amp;gt;", rendered)
        self.assertIn("<p>Body</p>", rendered)
        self.assertIn("Other &lt;world&gt;</span>", rendered)
        (self.root / "templates" / "partial_post_meta.html").write_text(
            "<b>{{ category_label }}:{{ reading_minutes }}:{{ page.title }}</b>",
            encoding="utf-8",
        )
        for name, source in (
            ("partial_author_box.html", "<aside>{{ note }}</aside>"),
            ("partial_post_byline.html", "<small>{{ AUTHOR_NAME }}</small>"),
            ("partial_related_posts.html",
             "<section>{% for entry in related_entries %}"
             "{{ entry.item.title }}{% endfor %}</section>"),
        ):
            (self.root / "templates" / name).write_text(source, encoding="utf-8")
        self.assertEqual(main(args), 0)
        customized = output.read_text(encoding="utf-8")
        self.assertIn("<b>Blog:1:Hello &lt;world&gt;</b>", customized)
        self.assertIn("<aside>Note &lt;i&gt;</aside>", customized)
        self.assertIn("<small>Writer &lt;b&gt;</small>", customized)
        self.assertIn("<section>Other &lt;world&gt;</section>", customized)

    def test_ad_templates_preserve_and_escape_attributes(self) -> None:
        settings = load_config(self.config)
        settings["adsense_pub_id"] = 'pub"<&'
        slot = 'slot" data-unexpected="true'
        config = BuildConfig(self.root, self.root / "output", settings)
        with use_config(config), use_templates(settings):
            standard = etree.fromstring("<root>" + render_ad(slot) + "</root>")
            ad = standard.find("ins")
            self.assertEqual(ad.get("data-ad-client"), settings["adsense_pub_id"])
            self.assertEqual(ad.get("data-ad-slot"), slot)
            self.assertIsNone(ad.get("data-unexpected"))
            self.assertEqual(ad.get("data-full-width-responsive"), "true")
            infeed = etree.fromstring(
                "<root>" + render_infeed_ad(slot, 'layout"<&') + "</root>"
            ).find("ins")
            self.assertEqual(infeed.get("data-ad-layout-key"), 'layout"<&')
            self.assertIsNone(infeed.get("data-ad-format"))
            fluid = etree.fromstring(
                "<root>" + render_infeed_ad(slot) + "</root>"
            ).find("ins")
            self.assertEqual(fluid.get("data-ad-format"), "fluid")
            self.assertEqual(render_ad(""), "")
        with self.assertRaises(LookupError):
            current_templates()

    def test_seo_templates_and_xml_escape_data(self) -> None:
        (self.root / "static" / "tools").rmdir()
        settings = yaml.safe_load(self.config.read_text(encoding="utf-8"))
        settings["site_name"] = "Site <name> &"
        self.config.write_text(yaml.safe_dump(settings), encoding="utf-8")
        title = "</script><b>&"
        metadata = {
            "title": title, "nav_title": title, "slug": "escaping",
            "description": "A & <description>", "published_date": "2020-01-01",
            "updated_date": "2020-01-01", "tags": [],
        }
        (self.root / "content" / "posts" / "escaping.md").write_text(
            "---\n" + yaml.safe_dump(metadata) + "---\nBody\n", encoding="utf-8"
        )
        args = ["build", "--site-root", str(self.root), "--output", "output"]
        self.assertEqual(main(args), 0)
        output = self.root / "output"
        post = (output / "posts" / "escaping" / "index.html").read_text("utf-8")
        payload = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', post, re.DOTALL
        ).group(1)
        self.assertEqual(json.loads(payload)["headline"], title)
        self.assertNotIn("</script>", payload)
        rss = etree.parse(output / "rss.xml")
        self.assertEqual(rss.findtext("channel/item/title"), title)
        self.assertEqual(
            rss.findtext("channel/item/description"), metadata["description"]
        )
        self.assertEqual(
            (output / "rss.xml").read_bytes(), (output / "feed.xml").read_bytes()
        )
        sitemap = etree.parse(output / "sitemap.xml")
        self.assertTrue(sitemap.findall("{*}url/{*}loc"))
        svg = etree.parse(output / "assets" / "og-escaping.svg")
        self.assertIn(title, "".join(svg.getroot().itertext()))
        custom_svg = self.root / "templates" / "image_og.svg"
        custom_svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" id="custom-og">'
            '<text>{{ title_line1 }}</text></svg>', encoding="utf-8",
        )
        self.assertEqual(main(args), 0)
        customized = etree.parse(output / "assets" / "og-escaping.svg")
        self.assertEqual(customized.getroot().get("id"), "custom-og")
        previous = (output / "index.html").read_bytes()
        custom_svg.write_text("{% if %}", encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as result:
            main(args)
        self.assertEqual(result.exception.code, 2)
        self.assertIn("image_og.svg", stderr.getvalue())
        self.assertEqual((output / "index.html").read_bytes(), previous)

    def test_build_cli_uses_explicit_pages_url(self) -> None:
        self.config.write_text(
            "site_name: Test Site\nsite_origin: ''\n",
            encoding="utf-8",
        )
        (self.root / "static" / "tools").rmdir()
        with self.assertRaises(SystemExit) as result:
            main(["build", "--site-root", str(self.root), "--output", "output"])
        self.assertEqual(result.exception.code, 2)
        self.assertFalse((self.root / "output").exists())
        args = [
            "build", "--site-root", str(self.root), "--output", "output",
            "--site-origin", "https://pages.example", "--base-url", "/project",
        ]
        self.assertEqual(main(args), 0)
        output = self.root / "output"
        self.assertIn(
            "https://pages.example/project/",
            (output / "sitemap.xml").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "/project/assets/naru.css",
            (output / "index.html").read_text(encoding="utf-8"),
        )

    def test_sequential_builds_do_not_share_settings(self) -> None:
        (self.root / "static" / "tools").rmdir()
        for name, origin in (("First", "https://first.example"),
                             ("Second", "https://second.example")):
            self.config.write_text(
                f"site_name: {name}\nsite_origin: {origin}\n", encoding="utf-8"
            )
            self.assertEqual(
                main(["build", "--site-root", str(self.root), "--output", name]), 0
            )
            home = (self.root / name / "index.html").read_text(encoding="utf-8")
            feed = (self.root / name / "rss.xml").read_text(encoding="utf-8")
            self.assertIn(name, home)
            self.assertIn(origin, feed)
            other = "Second" if name == "First" else "First"
            self.assertNotIn(other, home)

    def test_invalid_markdown_preserves_previous_output(self) -> None:
        (self.root / "static" / "tools").rmdir()
        args = ["build", "--site-root", str(self.root), "--output", "output"]
        self.assertEqual(main(args), 0)
        home = self.root / "output" / "index.html"
        previous = home.read_bytes()
        (self.root / "content" / "posts" / "broken.md").write_text(
            "---\ntitle: [broken\n---\n본문\n", encoding="utf-8"
        )
        with self.assertRaises(SystemExit) as result:
            main(args)
        self.assertEqual(result.exception.code, 2)
        self.assertEqual(home.read_bytes(), previous)

    def test_removed_post_images_are_cleaned_without_removing_other_files(self) -> None:
        (self.root / "static" / "tools").rmdir()
        posts = self.root / "content" / "posts"
        post = posts / "hello.md"
        post.write_text(
            "---\ntitle: Hello\nnav_title: Hello\nslug: hello\n"
            "description: Example\npublished_date: 2026-01-01\n"
            "updated_date: 2026-01-01\ntags: []\n---\n![image](image.png)\n",
            encoding="utf-8",
        )
        (posts / "image.png").write_bytes(b"first image")
        args = ["build", "--site-root", str(self.root), "--output", "output"]
        self.assertEqual(main(args), 0)
        output = self.root / "output"
        generated = output / "assets" / "posts" / "hello" / "image.png"
        self.assertEqual(generated.read_bytes(), b"first image")
        other = generated.parent / "unmanaged.png"
        other.write_bytes(b"keep")
        post.unlink()
        self.assertEqual(main(args), 0)
        self.assertFalse(generated.exists())
        self.assertEqual(other.read_bytes(), b"keep")

    def test_modified_generated_image_is_preserved_when_post_is_removed(self) -> None:
        (self.root / "static" / "tools").rmdir()
        posts = self.root / "content" / "posts"
        post = posts / "hello.md"
        post.write_text(
            "---\ntitle: Hello\nnav_title: Hello\nslug: hello\n"
            "description: Example\npublished_date: 2026-01-01\n"
            "updated_date: 2026-01-01\ntags: []\n---\n![image](image.png)\n",
            encoding="utf-8",
        )
        (posts / "image.png").write_bytes(b"first image")
        args = ["build", "--site-root", str(self.root), "--output", "output"]
        self.assertEqual(main(args), 0)
        generated = self.root / "output" / "assets" / "posts" / "hello" / "image.png"
        generated.write_bytes(b"manually modified")
        post.unlink()
        self.assertEqual(main(args), 0)
        self.assertEqual(generated.read_bytes(), b"manually modified")

    def test_duplicate_slug_preserves_previous_output(self) -> None:
        (self.root / "static" / "tools").rmdir()
        args = ["build", "--site-root", str(self.root), "--output", "output"]
        self.assertEqual(main(args), 0)
        output = self.root / "output" / "index.html"
        previous = output.read_bytes()
        content = (
            "---\ntitle: Hello\nnav_title: Hello\nslug: hello\n"
            "description: Example\npublished_date: 2026-01-01\n"
            "updated_date: 2026-01-01\ntags: []\n---\n본문\n"
        )
        posts = self.root / "content" / "posts"
        (posts / "first.md").write_text(content, encoding="utf-8")
        (posts / "second.md").write_text(content, encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as result:
            main(args)
        self.assertEqual(result.exception.code, 2)
        self.assertIn("first.md", stderr.getvalue())
        self.assertIn("second.md", stderr.getvalue())
        self.assertEqual(output.read_bytes(), previous)

    def test_static_file_conflicting_with_post_is_rejected(self) -> None:
        (self.root / "static" / "tools").rmdir()
        post = self.root / "content" / "posts" / "hello.md"
        post.write_text(
            "---\ntitle: Hello\nnav_title: Hello\nslug: hello\n"
            "description: Example\npublished_date: 2026-01-01\n"
            "updated_date: 2026-01-01\ntags: []\n---\n본문\n",
            encoding="utf-8",
        )
        static = self.root / "static" / "posts" / "hello" / "index.html"
        static.parent.mkdir(parents=True)
        static.write_text("static content", encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as result:
            main(["build", "--site-root", str(self.root), "--output", "output"])
        self.assertEqual(result.exception.code, 2)
        self.assertIn("conflicts", stderr.getvalue())
        self.assertIn(str(static), stderr.getvalue())
        self.assertIn(str(post), stderr.getvalue())
        self.assertEqual(static.read_text(encoding="utf-8"), "static content")

    def test_static_robots_file_overrides_generated_robots(self) -> None:
        (self.root / "static" / "tools").rmdir()
        robots = self.root / "static" / "robots.txt"
        robots.write_text(
            "User-agent: *\nAllow: /\nDisallow: /private/\n",
            encoding="utf-8",
        )

        self.assertEqual(
            main(["build", "--site-root", str(self.root), "--output", "output"]), 0
        )

        self.assertEqual(
            (self.root / "output" / "robots.txt").read_bytes(),
            robots.read_bytes(),
        )

    def test_archive_collision_preserves_previous_output(self) -> None:
        (self.root / "static" / "tools").rmdir()
        args = ["build", "--site-root", str(self.root), "--output", "output"]
        self.assertEqual(main(args), 0)
        output = self.root / "output" / "index.html"
        previous = output.read_bytes()
        pages = self.root / "content" / "pages"
        pages.mkdir()
        page = pages / "posts.md"
        page.write_text(
            "---\ntitle: Posts\nnav_title: Posts\nslug: posts\n"
            "description: Example\npublished_date: 2026-01-01\n"
            "updated_date: 2026-01-01\ntags: []\n---\n본문\n",
            encoding="utf-8",
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as result:
            main(args)
        self.assertEqual(result.exception.code, 2)
        self.assertIn("archive", stderr.getvalue())
        self.assertIn(str(page), stderr.getvalue())
        self.assertEqual(output.read_bytes(), previous)

    def test_static_files_cannot_overwrite_generated_outputs(self) -> None:
        (self.root / "static" / "tools").rmdir()
        args = ["build", "--site-root", str(self.root), "--output", "output"]
        self.assertEqual(main(args), 0)
        output = self.root / "output" / "index.html"
        previous = output.read_bytes()
        for name in ("index.html", "rss.xml", "assets/og-home.svg"):
            with self.subTest(name=name):
                static = self.root / "static" / name
                static.parent.mkdir(parents=True, exist_ok=True)
                static.write_text("custom content", encoding="utf-8")
                stderr = io.StringIO()
                with redirect_stderr(stderr), self.assertRaises(SystemExit):
                    main(args)
                self.assertIn("conflicts", stderr.getvalue())
                self.assertIn(str(static), stderr.getvalue())
                self.assertEqual(output.read_bytes(), previous)
                static.unlink()

    def test_assets_and_static_assets_preserve_distinct_files(self) -> None:
        (self.root / "static" / "tools").rmdir()
        assets = self.root / "assets"
        assets.mkdir()
        (assets / "custom.css").write_text("custom", encoding="utf-8")
        static_assets = self.root / "static" / "assets"
        static_assets.mkdir()
        (static_assets / "image.png").write_bytes(b"static")
        self.assertEqual(
            main(["build", "--site-root", str(self.root), "--output", "output"]), 0
        )
        output = self.root / "output" / "assets"
        self.assertEqual((output / "custom.css").read_text(encoding="utf-8"), "custom")
        self.assertEqual((output / "image.png").read_bytes(), b"static")

    def test_paginated_archive_conflicting_with_post_is_rejected(self) -> None:
        self.config.write_text(
            "site_name: Test\nsite_origin: https://example.com\nposts_per_page: 1\n",
            encoding="utf-8",
        )
        (self.root / "static" / "tools").rmdir()
        posts = self.root / "content" / "posts"
        for slug in ("first", "2"):
            (posts / f"{slug}.md").write_text(
                f"---\ntitle: '{slug}'\nnav_title: '{slug}'\nslug: '{slug}'\n"
                "description: Example\npublished_date: 2026-01-01\n"
                "updated_date: 2026-01-01\ntags: []\n---\n본문\n",
                encoding="utf-8",
            )
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            main(["build", "--site-root", str(self.root), "--output", "output"])
        self.assertIn("archive", stderr.getvalue())
        self.assertIn("2.md", stderr.getvalue())

    def test_category_redirect_conflicting_with_category_is_rejected(self) -> None:
        self.config.write_text(
            "site_name: Test\nsite_origin: https://example.com\n"
            "category_redirects:\n  blog: other\n",
            encoding="utf-8",
        )
        (self.root / "static" / "tools").rmdir()
        (self.root / "content" / "posts" / "first.md").write_text(
            "---\ntitle: First\nnav_title: First\nslug: first\n"
            "description: Example\npublished_date: 2026-01-01\n"
            "updated_date: 2026-01-01\ncategory: blog\ntags: []\n---\n본문\n",
            encoding="utf-8",
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            main(["build", "--site-root", str(self.root), "--output", "output"])
        self.assertIn("category redirect blog", stderr.getvalue())
        self.assertIn("category blog", stderr.getvalue())

    def test_subpath_build_resolves_markdown_links_and_images(self) -> None:
        self.config.write_text(
            "site_name: Test\nsite_origin: https://example.com\nbase_url: /notes\n",
            encoding="utf-8",
        )
        (self.root / "static" / "tools").rmdir()
        posts = self.root / "content" / "posts"
        metadata = (
            "---\ntitle: Hello\nnav_title: Hello\nslug: {slug}\n"
            "description: Example\npublished_date: 2026-01-01\n"
            "updated_date: 2026-01-01\ntags: []\n---\n{body}\n"
        )
        (posts / "first.md").write_text(
            metadata.format(
                slug="first", body="[두 번째](second.md#part)\n\n![그림](image.png)"
            ),
            encoding="utf-8",
        )
        (posts / "second.md").write_text(
            metadata.format(slug="other-slug", body="## Part"), encoding="utf-8"
        )
        (posts / "image.png").write_bytes(b"image")
        self.assertEqual(
            main(["build", "--site-root", str(self.root), "--output", "output"]), 0
        )
        output = self.root / "output"
        html = (output / "posts" / "first" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/notes/posts/other-slug/#part"', html)
        self.assertIn('src="/notes/assets/posts/first/image.png"', html)
        self.assertTrue((output / "assets" / "posts" / "first" / "image.png").is_file())

    def test_broken_links_are_logged_without_changing_page(self) -> None:
        (self.root / "static" / "tools").rmdir()
        posts = self.root / "content" / "posts"
        post = posts / "first.md"
        post.write_text(
            "---\ntitle: First\nnav_title: First\nslug: first\n"
            "description: Example\npublished_date: 2026-01-01\n"
            "updated_date: 2026-01-01\ntags: []\n---\n"
            "## 한글 제목\n\n[정상](#한글-제목) [없음](#없는-제목) "
            "[문서 없음](missing.md) [정상 문서](second.md#다른-제목) "
            "[없는 앵커](second.md#없는-앵커)\n",
            encoding="utf-8",
        )
        (posts / "second.md").write_text(
            "---\ntitle: Second\nnav_title: Second\nslug: second\n"
            "description: Example\npublished_date: 2026-01-01\n"
            "updated_date: 2026-01-01\ntags: []\n---\n## 다른 제목\n",
            encoding="utf-8",
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = main(
                ["build", "--site-root", str(self.root), "--output", "output"]
            )
        self.assertEqual(result, 0)
        self.assertIn(str(post), stderr.getvalue())
        self.assertIn("missing.md", stderr.getvalue())
        self.assertIn("#없는-제목", stderr.getvalue())
        self.assertIn("#없는-앵커", stderr.getvalue())
        self.assertNotIn("#한글-제목", stderr.getvalue())
        self.assertNotIn("#다른-제목", stderr.getvalue())
        html = (self.root / "output" / "posts" / "first" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('href="#없는-제목"', html)
        self.assertIn('href="missing.md"', html)
        self.assertNotIn("[WARNING]", html)

    def test_output_is_restored_if_replacement_fails(self) -> None:
        (self.root / "static" / "tools").rmdir()
        args = ["build", "--site-root", str(self.root), "--output", "output"]
        self.assertEqual(main(args), 0)
        output = self.root / "output" / "index.html"
        previous = output.read_bytes()
        original_rename = Path.rename

        def fail_staged_rename(path, target):
            if path.name == "output" and path.parent.name.startswith(".naru-build-"):
                raise PermissionError("output is locked")
            return original_rename(path, target)

        stdout = io.StringIO()
        with (
            patch.object(Path, "rename", fail_staged_rename),
            redirect_stdout(stdout),
            redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            main(args)
        self.assertEqual(output.read_bytes(), previous)
        self.assertNotIn("[DONE]", stdout.getvalue())

    def test_minimal_site_and_template_override_build(self) -> None:
        self.config.write_text(
            "site_name: Test Site\nsite_origin: https://example.com\n"
            "base_url: /journal\n",
            encoding="utf-8",
        )
        post = self.root / "content" / "posts" / "hello.md"
        post.write_text(
            "---\ntitle: Hello\nnav_title: Hello\nslug: hello\n"
            "description: First post\npublished_date: '2026-01-01'\n"
            "updated_date: '2026-01-01'\ncategory: blog\ntags: [Example]\n"
            "---\n\nWelcome to the site.\n",
            encoding="utf-8",
        )
        (self.root / "static" / "tools").rmdir()
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONPATH"] = str(EXAMPLE_CONFIG.parents[2] / "src")

        def build(output: str) -> None:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "naru",
                    "build",
                    "--site-root",
                    str(self.root),
                    "--output",
                    output,
                ],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        build("output")
        output = self.root / "output"
        home = (output / "index.html").read_text(encoding="utf-8")
        post_html = (output / "posts" / "hello" / "index.html").read_text(
            encoding="utf-8"
        )
        sitemap = (output / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("/journal/posts/hello/", home)
        self.assertIn("/journal/assets/naru.css", home)
        css_version = hashlib.sha256(
            (output / "assets" / "naru.css").read_bytes()
        ).hexdigest()[:12]
        self.assertIn(
            f"/journal/assets/naru.css?v={css_version}",
            home,
        )
        self.assertIn("Welcome to the site.", post_html)
        self.assertTrue((output / "assets" / "naru.css").is_file())
        self.assertNotIn("/tools/", sitemap)
        assets = self.root / "assets"
        assets.mkdir()
        (assets / "naru.css").write_text("/* custom */", encoding="utf-8")
        build("custom-css-output")
        self.assertEqual(
            (self.root / "custom-css-output" / "assets" / "naru.css").read_text(
                encoding="utf-8"
            ),
            "/* custom */",
        )
        (self.root / "templates" / "partial_head.html").write_text(
            "<title>Custom {{ TITLE }}</title>", encoding="utf-8"
        )
        build("custom-output")
        custom_home = (self.root / "custom-output" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("<title>Custom Test Site</title>", custom_home)
        self.assertIn("/journal/posts/hello/", custom_home)

    def test_empty_site_builds_without_optional_source_directories(self) -> None:
        self.config.write_text(
            "site_name: Empty Site\nsite_origin: https://example.com\n",
            encoding="utf-8",
        )
        for path in (
            self.root / "content" / "posts",
            self.root / "content",
            self.root / "templates",
            self.root / "static" / "tools",
            self.root / "static",
        ):
            path.rmdir()
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONPATH"] = str(EXAMPLE_CONFIG.parents[2] / "src")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "naru",
                "build",
                "--site-root",
                str(self.root),
                "--output",
                "output",
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "output" / "index.html").is_file())
        self.assertTrue((self.root / "output" / "assets" / "naru.css").is_file())
        self.assertFalse((self.root / "static").exists())

    def test_python_ssg_catalog_example_builds_as_a_catalog_page(self) -> None:
        self.config.write_text(
            "site_name: Catalog Site\nsite_origin: https://example.com\n"
            "category_labels:\n  BLOG: Blog\n  BOOKMARK: Bookmarks\n",
            encoding="utf-8",
        )
        example_dir = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "basic-site"
            / "content"
            / "posts"
        )
        bookmark_dir = self.root / "content" / "posts" / "bookmark"
        bookmark_dir.mkdir()
        for name in ("python-ssg.md", "python-ssg.sites.yml"):
            (bookmark_dir / name).write_text(
                (example_dir / "bookmark" / name).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        blog_dir = self.root / "content" / "posts" / "blog"
        blog_dir.mkdir()
        for name in ("welcome.md", "naru-introduction.md"):
            (blog_dir / name).write_text(
                (example_dir / "blog" / name).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        (self.root / "static" / "tools").rmdir()

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONPATH"] = str(EXAMPLE_CONFIG.parents[2] / "src")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "naru",
                "build",
                "--site-root",
                str(self.root),
                "--output",
                "output",
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        output = self.root / "output"
        home = (output / "index.html").read_text(encoding="utf-8")
        catalog = (output / "python-ssg" / "index.html").read_text(
            encoding="utf-8"
        )
        post = (output / "posts" / "markdown-basics" / "index.html").read_text(
            encoding="utf-8"
        )
        bookmark_category = (
            output / "category" / "bookmark" / "index.html"
        ).read_text(encoding="utf-8")
        all_content = (output / "posts" / "index.html").read_text(
            encoding="utf-8"
        )
        blog_category = (output / "category" / "blog" / "index.html").read_text(
            encoding="utf-8"
        )
        sitemap = (output / "sitemap.xml").read_text(encoding="utf-8")
        feed = (output / "rss.xml").read_text(encoding="utf-8")
        self.assertIn("최근 콘텐츠", home)
        self.assertIn("Naru 소개", home)
        self.assertIn("Python 정적 사이트 생성기(SSG) 모음", home)
        self.assertIn("Markdown 기본 문법", home)
        self.assertIn("Bookmarks", home)
        self.assertIn("Blog", home)
        self.assertIn("<h1>Python 정적 사이트 생성기(SSG) 모음</h1>", catalog)
        self.assertIn("<dd>2026-11-16</dd>", catalog)
        self.assertIn("공식 사이트 링크와 프로젝트 소개를 확인했습니다.", catalog)
        self.assertIn("catalog-guide-section", catalog)
        self.assertIn('"@type": "CollectionPage"', catalog)
        self.assertIn("Pelican", catalog)
        self.assertIn("https://getpelican.com/", catalog)
        self.assertIn("MkDocs", catalog)
        self.assertNotIn('class="ad-row"', catalog)
        self.assertIn("example.com/python-ssg/", sitemap)
        self.assertIn("<strong>두 개의 별표</strong>", post)
        self.assertRegex(
            post, r"<pre\b[^>]*>(?:<span></span>)?<code\b[^>]*>[^\n]*greet"
        )
        self.assertIn("Markdown 기본 문법", blog_category)
        self.assertIn("Naru 소개", blog_category)
        self.assertIn("Python 정적 사이트 생성기(SSG) 모음", bookmark_category)
        self.assertIn("<h1>글 목록</h1>", all_content)
        self.assertIn("Markdown 기본 문법", all_content)
        self.assertIn("Python 정적 사이트 생성기(SSG) 모음", all_content)
        self.assertIn(">Blog</span>", all_content)
        self.assertIn(">Bookmarks</span>", all_content)
        self.assertIn("https://example.com/python-ssg/", feed)
        introduction = (
            output / "posts" / "naru-introduction" / "index.html"
        ).read_text(encoding="utf-8")
        self.assertIn("Markdown으로 작성한 글과 페이지", introduction)
        self.assertIn('href="/posts/markdown-basics/"', introduction)
        self.assertIn('href="/python-ssg/"', introduction)
        self.assertIn("https://example.com/posts/naru-introduction/", feed)

    def test_markdown_catalog_uses_the_catalog_template(self) -> None:
        markdown_example = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "basic-site"
            / "content"
            / "posts"
            / "bookmark"
            / "python-ssg.md"
        )
        (self.root / "content" / "posts" / markdown_example.name).write_text(
            markdown_example.read_text(encoding="utf-8"), encoding="utf-8"
        )
        sites_example = markdown_example.with_suffix(".sites.yml")
        (self.root / "content" / "posts" / sites_example.name).write_text(
            sites_example.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (self.root / "static" / "tools").rmdir()
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONPATH"] = str(EXAMPLE_CONFIG.parents[2] / "src")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "naru",
                "build",
                "--site-root",
                str(self.root),
                "--output",
                "output",
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        output = self.root / "output"
        catalog = (output / "python-ssg" / "index.html").read_text(
            encoding="utf-8"
        )
        archive = (output / "posts" / "index.html").read_text(encoding="utf-8")
        bookmark_category = (
            output / "category" / "bookmark" / "index.html"
        ).read_text(encoding="utf-8")
        self.assertIn("<dl class=\"catalog-meta\">", catalog)
        self.assertIn('<div class="catalog-table-wrap">', catalog)
        self.assertIn('<table class="catalog-table">', catalog)
        self.assertIn("용도에 따라 선택하기", catalog)
        self.assertIn(
            "2026-11-16 공식 사이트 링크와 프로젝트 소개를 확인했습니다.",
            catalog,
        )
        self.assertIn("https://getpelican.com/", catalog)
        self.assertIn("Python 정적 사이트 생성기(SSG) 모음", archive)
        self.assertIn("Python 정적 사이트 생성기(SSG) 모음", bookmark_category)
        self.assertFalse((output / "posts" / "python-ssg" / "index.html").exists())

    def test_catalog_override_supports_jinja_and_escapes_site_data(self) -> None:
        post = self.root / "content" / "posts" / "catalog.md"
        post.write_text(
            "---\nlayout: catalog\ntitle: 목록\nnav_title: 목록\nslug: list\n"
            "description: 목록 설명\npublished_date: 2026-01-01\n"
            "updated_date: 2026-01-01\ntags: []\n---\n본문\n",
            encoding="utf-8",
        )
        post.with_suffix(".sites.yml").write_text(
            '- id: example\n  name: "<Example>"\n'
            '  url: "https://example.com/"\n  description: "사이트"\n',
            encoding="utf-8",
        )
        (self.root / "templates" / "template_catalog.html").write_text(
            "{{ HEAD_HTML }}{% for site in sites %}"
            "{% if site.name %}<p>{{ site.name }}</p>{% endif %}"
            "{% endfor %}{{ INTRO_GUIDE_HTML }}",
            encoding="utf-8",
        )
        (self.root / "static" / "tools").rmdir()
        self.assertEqual(
            main(["build", "--site-root", str(self.root), "--output", "output"]), 0
        )
        html = (self.root / "output" / "list" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("<p>&lt;Example&gt;</p>", html)
        self.assertIn("<p>본문</p>", html)
        self.assertIn("<meta", html)

    def test_jinja_inheritance_and_include_use_site_templates(self) -> None:
        self.config.write_text(
            "site_name: 'Test <Site>'\nsite_origin: https://example.com\n",
            encoding="utf-8",
        )
        templates = self.root / "templates"
        (templates / "base.html").write_text(
            "<main>{% block content %}{% endblock %}</main>", encoding="utf-8"
        )
        (templates / "shared.html").write_text(
            "<strong>{{ site.site_name }}</strong>", encoding="utf-8"
        )
        (templates / "template_index.html").write_text(
            "{% extends 'base.html' %}{% block content %}"
            "{% include 'shared.html' %}{% include 'optional.html' ignore missing %}"
            "{% endblock %}", encoding="utf-8"
        )
        (self.root / "static" / "tools").rmdir()
        self.assertEqual(
            main(["build", "--site-root", str(self.root), "--output", "output"]), 0
        )
        html = (self.root / "output" / "index.html").read_text(encoding="utf-8")
        self.assertIn("<main><strong>Test &lt;Site&gt;</strong></main>", html)

    def test_jinja_undefined_variable_reports_template_location(self) -> None:
        template = self.root / "templates" / "template_index.html"
        (self.root / "static" / "tools").rmdir()
        args = ["build", "--site-root", str(self.root), "--output", "output"]
        self.assertEqual(main(args), 0)
        output = self.root / "output" / "index.html"
        previous = output.read_bytes()
        template.write_text("<p>{{ missing_name }}</p>", encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as result:
            main(args)
        self.assertEqual(result.exception.code, 2)
        self.assertIn(str(template), stderr.getvalue())
        self.assertIn("missing_name", stderr.getvalue())
        self.assertIn(":1:", stderr.getvalue())
        self.assertEqual(output.read_bytes(), previous)

    def test_jinja_syntax_error_preserves_previous_output(self) -> None:
        (self.root / "static" / "tools").rmdir()
        args = ["build", "--site-root", str(self.root), "--output", "output"]
        self.assertEqual(main(args), 0)
        output = self.root / "output" / "index.html"
        previous = output.read_bytes()
        template = self.root / "templates" / "template_index.html"
        template.write_text("{% if %}", encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            main(args)
        self.assertIn(str(template), stderr.getvalue())
        self.assertEqual(output.read_bytes(), previous)

    def test_included_template_syntax_error_preserves_previous_output(self) -> None:
        (self.root / "static" / "tools").rmdir()
        args = ["build", "--site-root", str(self.root), "--output", "output"]
        self.assertEqual(main(args), 0)
        output = self.root / "output" / "index.html"
        previous = output.read_bytes()
        templates = self.root / "templates"
        (templates / "template_index.html").write_text(
            "{% include 'shared.html' %}", encoding="utf-8"
        )
        shared = templates / "shared.html"
        shared.write_text("{% if %}", encoding="utf-8")
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            main(args)
        self.assertIn(str(shared), stderr.getvalue())
        self.assertEqual(output.read_bytes(), previous)

    def test_legacy_catalog_entries_placeholder_renders(self) -> None:
        post = self.root / "content" / "posts" / "catalog.md"
        post.write_text(
            "---\nlayout: catalog\ntitle: 목록\nnav_title: 목록\nslug: list\n"
            "description: 목록 설명\npublished_date: 2026-01-01\n"
            "updated_date: 2026-01-01\ntags: []\n---\n본문\n",
            encoding="utf-8",
        )
        post.with_suffix(".sites.yml").write_text(
            "- id: example\n  name: Example\n  url: https://example.com/\n"
            "  description: Test\n",
            encoding="utf-8",
        )
        (self.root / "templates" / "template_catalog.html").write_text(
            "<table>{{ ENTRIES_HTML }}</table>", encoding="utf-8"
        )
        (self.root / "static" / "tools").rmdir()
        self.assertEqual(
            main(["build", "--site-root", str(self.root), "--output", "output"]), 0
        )
        html = (self.root / "output" / "list" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('<tr class="site-table-row" id="sec-example">', html)
        self.assertIn("Example", html)

    def test_default_catalog_escapes_site_data(self) -> None:
        post = self.root / "content" / "posts" / "catalog.md"
        post.write_text(
            "---\nlayout: catalog\ntitle: 목록\nnav_title: 목록\nslug: list\n"
            "description: 목록 설명\npublished_date: 2026-01-01\n"
            "updated_date: 2026-01-01\ntags: []\n---\n본문\n",
            encoding="utf-8",
        )
        sites = [{
            "id": "example",
            "name": 'Name "<test>',
            "url": "https://example.com/?a=1&b=2",
            "description": "<script>alert(1)</script>",
        }]
        post.with_suffix(".sites.yml").write_text(
            yaml.safe_dump(sites, allow_unicode=True), encoding="utf-8"
        )
        (self.root / "static" / "tools").rmdir()
        self.assertEqual(
            main(["build", "--site-root", str(self.root), "--output", "output"]), 0
        )
        html = (self.root / "output" / "list" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("Name &#34;&lt;test&gt;", html)
        self.assertIn("?a=1&amp;b=2", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_existing_unmanaged_output_is_preserved(self) -> None:
        output = self.root / "output"
        output.mkdir()
        sentinel = output / "important.html"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaises(SystemExit) as result:
            main(["build", "--site-root", str(self.root), "--output", str(output)])
        self.assertEqual(result.exception.code, 2)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_source_directory_cannot_be_used_as_output(self) -> None:
        with self.assertRaises(SystemExit) as result:
            main(["build", "--site-root", str(self.root), "--output", "content"])
        self.assertEqual(result.exception.code, 2)
        self.assertTrue((self.root / "content" / "posts").is_dir())

    @patch("naru.engine.build.build")
    def test_build_passes_config_and_preserves_output_ownership(self, build) -> None:
        output = self.root / "output"
        args = ["build", "--site-root", str(self.root), "--output", str(output)]
        self.assertEqual(main(args), 0)
        self.assertEqual(
            (output / ".naru-output").read_text(encoding="utf-8"), str(self.root)
        )
        config = build.call_args.args[0]
        self.assertEqual(config.site_root, self.root)
        self.assertEqual(config.output_dir, output)
        self.assertEqual(config.settings["site_origin"], "https://example.com")
        self.assertEqual(main(args), 0)

    def test_build_uses_each_sites_origin_for_generated_cname_and_feed(self) -> None:
        (self.root / "assets").mkdir()
        (self.root / "static" / "CNAME").write_text("stale.example", encoding="utf-8")
        (self.root / "static" / "tools" / "index.html").write_text(
            "{{ NAV_HTML }} {{ FOOTER_HTML }}", encoding="utf-8"
        )
        for name in (
            "template_index.html",
            "template_catalog.html",
            "template_post.html",
            "template_archive.html",
        ):
            (self.root / "templates" / name).write_text(
                "{{ HEAD_HTML }} {{ SITE_ORIGIN }} {{ SITE_NAME }}", encoding="utf-8"
            )
        (self.root / "templates" / "partial_head.html").write_text(
            '<meta name="keywords" content="{{ KEYWORDS }}">', encoding="utf-8"
        )
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONPATH"] = str(EXAMPLE_CONFIG.parents[2] / "src")
        data = yaml.safe_load(self.config.read_text(encoding="utf-8"))
        for origin, name, directory in (
            ("https://first.example", "First Site", "first"),
            ("https://second.example", "Second Site", "second"),
        ):
            data["site_origin"] = origin
            data["site_name"] = name
            self.config.write_text(yaml.safe_dump(data), encoding="utf-8")
            output = self.root / directory
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "naru",
                    "build",
                    "--site-root",
                    str(self.root),
                    "--output",
                    str(output),
                ],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (output / "CNAME").read_text(encoding="utf-8"),
                origin.removeprefix("https://"),
            )
            self.assertIn(origin, (output / "rss.xml").read_text(encoding="utf-8"))
            home = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn(f'content="{name}, 기술 기록, IT, 문화, 스포츠"', home)


if __name__ == "__main__":
    unittest.main()
