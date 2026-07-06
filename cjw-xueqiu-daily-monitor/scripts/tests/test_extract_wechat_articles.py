from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ExtractWechatArticlesScriptTests(unittest.TestCase):
    def run_node_module_json(self, script: str) -> dict[str, object]:
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_help_succeeds(self) -> None:
        script_path = PROJECT_ROOT / "scripts" / "extract_wechat_articles.mjs"

        result = subprocess.run(
            ["node", str(script_path), "--help"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--article-url", result.stdout)
        self.assertIn("--history-url", result.stdout)
        self.assertIn("--input-file", result.stdout)

    def test_url_helper_accepts_wechat_article_links_only(self) -> None:
        script_path = (PROJECT_ROOT / "scripts" / "extract_wechat_articles.mjs").as_uri()
        payload = self.run_node_module_json(
            f"""
import {{ isWechatArticleUrl }} from {json.dumps(script_path)};
console.log(JSON.stringify({{
  slashArticle: isWechatArticleUrl("https://mp.weixin.qq.com/s/abc123"),
  queryArticle: isWechatArticleUrl("https://mp.weixin.qq.com/s?__biz=MzA&mid=1&idx=1&sn=abc"),
  album: isWechatArticleUrl("https://mp.weixin.qq.com/mp/appmsgalbum?action=getalbum"),
  xueqiu: isWechatArticleUrl("https://xueqiu.com/123/456")
}}));
"""
        )

        self.assertTrue(payload["slashArticle"])
        self.assertTrue(payload["queryArticle"])
        self.assertFalse(payload["album"])
        self.assertFalse(payload["xueqiu"])

    def test_extracts_article_payload_from_wechat_html(self) -> None:
        script_path = (PROJECT_ROOT / "scripts" / "extract_wechat_articles.mjs").as_uri()
        html = """
<!doctype html>
<html>
  <head><script>
    var msg_title = '样例标题';
    var nickname = '样例公众号';
    var ct = '1770120000';
  </script></head>
  <body>
    <h1 id="activity-name">样例标题</h1>
    <a id="js_name">样例公众号</a>
    <span id="publish_time">2026年02月05日 10:40</span>
    <div id="js_content">
      <p>第一段&nbsp;正文</p>
      <p>第二段<strong>重点</strong></p>
    </div>
  </body>
</html>
"""
        payload = self.run_node_module_json(
            f"""
import {{ extractWechatArticleFromHtml }} from {json.dumps(script_path)};
const article = extractWechatArticleFromHtml({json.dumps(html)}, "https://mp.weixin.qq.com/s/abc123");
console.log(JSON.stringify(article));
"""
        )

        self.assertEqual(payload["title"], "样例标题")
        self.assertEqual(payload["author_name"], "样例公众号")
        self.assertEqual(payload["published_at"], "2026-02-05 10:40:00")
        self.assertEqual(payload["url"], "https://mp.weixin.qq.com/s/abc123")
        self.assertEqual(payload["content_id"], "abc123")
        self.assertIn("第一段 正文", payload["content"])
        self.assertIn("第二段重点", payload["content"])

    def test_extracts_publish_time_from_encoded_wechat_metadata(self) -> None:
        script_path = (PROJECT_ROOT / "scripts" / "extract_wechat_articles.mjs").as_uri()
        html = """
<html><body>
  <h1 id="activity-name">编码时间文章</h1>
  <a id="js_name">编码公众号</a>
  <em id="publish_time" class="rich_media_meta rich_media_meta_text"></em>
  <div data-meta="doc_info%22%3A%7B%22publish_time%22%3A1770259200%7D"></div>
  <div id="js_content"><p>正文</p></div>
</body></html>
"""
        payload = self.run_node_module_json(
            f"""
import {{ extractWechatArticleFromHtml }} from {json.dumps(script_path)};
const article = extractWechatArticleFromHtml({json.dumps(html)}, "https://mp.weixin.qq.com/s/encoded");
console.log(JSON.stringify(article));
"""
        )

        self.assertEqual(payload["published_at"], "2026-02-05 10:40:00")

    def test_discovers_article_urls_from_history_html(self) -> None:
        script_path = (PROJECT_ROOT / "scripts" / "extract_wechat_articles.mjs").as_uri()
        history_html = """
<html><body>
  <a href="https://mp.weixin.qq.com/s/first">第一篇</a>
  <a href="/s/second?from=timeline">第二篇</a>
  <script>
    window.payload = "https%3A%2F%2Fmp.weixin.qq.com%2Fs%2Fthird%3F__biz%3Dabc%26mid%3D1";
  </script>
  <a href="https://mp.weixin.qq.com/mp/appmsgalbum?action=getalbum">合集</a>
  <a href="https://xueqiu.com/1/2">非微信文章</a>
</body></html>
"""
        payload = self.run_node_module_json(
            f"""
import {{ extractWechatArticleUrlsFromHistoryHtml }} from {json.dumps(script_path)};
const urls = extractWechatArticleUrlsFromHistoryHtml(
  {json.dumps(history_html)},
  "https://mp.weixin.qq.com/mp/profile_ext?action=home"
);
console.log(JSON.stringify({{ urls }}));
"""
        )

        self.assertEqual(
            payload["urls"],
            [
                "https://mp.weixin.qq.com/s/first",
                "https://mp.weixin.qq.com/s/second?from=timeline",
                "https://mp.weixin.qq.com/s/third?__biz=abc&mid=1",
            ],
        )

    def test_cli_reads_urls_from_file_and_writes_compatible_json(self) -> None:
        script_path = PROJECT_ROOT / "scripts" / "extract_wechat_articles.mjs"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            html_file = tmp_path / "article.html"
            input_file = tmp_path / "urls.txt"
            output_file = tmp_path / "articles.json"
            html_file.write_text(
                """
<html><body>
  <h1 id="activity-name">离线文章</h1>
  <a id="js_name">离线公众号</a>
  <span id="publish_time">2026-02-05 09:00</span>
  <div id="js_content"><p>离线正文</p></div>
</body></html>
""",
                encoding="utf-8",
            )
            input_file.write_text("https://mp.weixin.qq.com/s/offline\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "node",
                    str(script_path),
                    "--input-file",
                    str(input_file),
                    "--html-file",
                    str(html_file),
                    "--output-file",
                    str(output_file),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            items = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["title"], "离线文章")
            self.assertEqual(items[0]["author_name"], "离线公众号")
            self.assertEqual(items[0]["content"], "离线正文")

    def test_cli_discovers_history_url_and_filters_by_date(self) -> None:
        script_path = PROJECT_ROOT / "scripts" / "extract_wechat_articles.mjs"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            history_file = tmp_path / "history.html"
            article_file = tmp_path / "article.html"
            output_file = tmp_path / "articles.json"
            history_file.write_text(
                '<html><body><a href="https://mp.weixin.qq.com/s/from-history">当天文章</a></body></html>',
                encoding="utf-8",
            )
            article_file.write_text(
                """
<html><body>
  <h1 id="activity-name">当天文章</h1>
  <a id="js_name">历史公众号</a>
  <span id="publish_time">2026-02-05 09:00</span>
  <div id="js_content"><p>当天正文</p></div>
</body></html>
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "node",
                    str(script_path),
                    "--history-url",
                    "https://mp.weixin.qq.com/mp/profile_ext?action=home",
                    "--history-html-file",
                    str(history_file),
                    "--html-file",
                    str(article_file),
                    "--date",
                    "2026-02-05",
                    "--output-file",
                    str(output_file),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            items = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["url"], "https://mp.weixin.qq.com/s/from-history")
            self.assertEqual(items[0]["title"], "当天文章")


if __name__ == "__main__":
    unittest.main()
