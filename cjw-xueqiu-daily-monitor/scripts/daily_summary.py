#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


MARKET_KEYWORDS = [
    "恒指",
    "恒生指数",
    "港股",
    "流动性",
    "回购",
    "新股",
    "IPO",
    "做空",
    "年报",
    "一季报",
    "美团",
    "泡泡玛特",
    "小米",
    "labubu",
]

TRADE_PATTERNS = {
    "继续持有": ["没动", "继续持有", "持有", "一股都没动"],
    "加仓观察": ["加仓", "买入", "建仓"],
    "减仓卖出": ["减仓", "清仓", "卖出"],
    "回购信号": ["回购"],
    "做空压力": ["做空", "承压"],
}

BACKGROUND_PATTERNS = {
    "业绩披露": ["年报", "财报", "业绩会", "一季报", "指引"],
    "价格波动": ["大跌", "下跌", "反弹", "承压", "新高", "低位"],
    "市场流动性": ["流动性", "回购", "新股", "IPO"],
    "交易情绪": ["情绪", "信心", "空头", "多头"],
}

SPEC_CANDIDATE_MARKERS = [
    "一旦",
    "如果",
    "当",
    "意味着",
    "开始反弹",
    "开始",
    "会",
    "低位",
    "新高",
    "回购",
    "流动性",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate end-of-day Markdown summaries from raw Xueqiu post files.")
    parser.add_argument("--date", required=True, help="Target date in YYYY-MM-DD format")
    parser.add_argument("--output-dir", default="./output", help="Output root containing raw capture directories")
    return parser.parse_args()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(value: str) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", value.strip(), flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\u00a0", " ")).strip()


def normalize_account_name(value: str) -> str:
    normalized = normalize_text(value)
    normalized = re.sub(r"(?:\s*[-_]\s*雪球|的雪球)$", "", normalized)
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip(" -_")
    return normalized


def discover_author_dirs(output_root: Path, date_slug: str) -> list[Path]:
    matches: list[Path] = []
    for path in sorted(output_root.iterdir()):
        if not path.is_dir():
            continue
        if path.name in {"processing", "summaries"}:
            continue
        if re.search(rf"_{date_slug}$", path.name):
            matches.append(path)
    return matches


def parse_post_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    metadata: dict[str, str] = {}
    body_lines: list[str] = []
    in_body = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line == "正文：":
            in_body = True
            continue
        if not in_body and "：" in line:
            key, value = line.split("：", 1)
            metadata[key.strip()] = value.strip()
            continue
        if in_body:
            cleaned = line.strip()
            if cleaned:
                body_lines.append(cleaned)

    return {
        "source_file": str(path),
        "title": metadata.get("标题", ""),
        "content_id": metadata.get("内容ID", ""),
        "publish_time": metadata.get("发布时间", ""),
        "publish_date": metadata.get("发布日期", ""),
        "url": metadata.get("原始链接", ""),
        "author_name": metadata.get("作者名称", ""),
        "fetched_at": metadata.get("抓取时间", ""),
        "content_lines": body_lines,
        "content": " ".join(body_lines).strip(),
    }


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[。！？!?])\s*", normalized)
    return [part.strip(" ，,") for part in parts if part.strip(" ，,")]


def extract_mentions(text: str) -> list[str]:
    mentions = []
    for matched in re.findall(r"\$([^$]+)\$", text):
        mentions.append(matched.strip())
    for keyword in MARKET_KEYWORDS:
        if keyword in text and keyword not in mentions:
            mentions.append(keyword)
    return mentions


def classify_matches(text: str, patterns: dict[str, list[str]]) -> list[str]:
    matched: list[str] = []
    for label, keywords in patterns.items():
        if any(keyword in text for keyword in keywords):
            matched.append(label)
    return matched


def is_spec_candidate(text: str) -> bool:
    return any(marker in text for marker in SPEC_CANDIDATE_MARKERS)


def build_core_summary(content: str, title: str) -> str:
    sentences = split_sentences(content)
    if sentences:
        summary = " ".join(sentences[:2]).strip()
        if len(summary) > 140:
            return summary[:140].rstrip() + "..."
        return summary
    fallback = title.strip() or content[:120].strip()
    return fallback[:140]


def analyze_post(post: dict[str, Any]) -> dict[str, Any]:
    text = f"{post['title']} {post['content']}".strip()
    mentions = extract_mentions(text)
    trade_signals = classify_matches(text, TRADE_PATTERNS)
    background_tags = classify_matches(text, BACKGROUND_PATTERNS)
    core_summary = build_core_summary(post["content"], post["title"])
    spec_candidate = None
    if is_spec_candidate(text):
        reason_parts = []
        if any(word in text for word in ["流动性", "回购", "新股", "IPO"]):
            reason_parts.append("出现宏观流动性或回购相关表述")
        if any(word in text for word in ["如果", "一旦", "当", "意味着"]):
            reason_parts.append("出现条件触发式表达")
        if any(word in text for word in ["反弹", "新高", "低位"]):
            reason_parts.append("出现潜在交易或规则触发表述")
        spec_candidate = {
            "reason": "；".join(reason_parts) or "出现规则候选表达",
            "evidence": core_summary,
        }

    return {
        "content_id": post["content_id"],
        "title": post["title"],
        "publish_time": post["publish_time"],
        "publish_date": post["publish_date"],
        "url": post["url"],
        "author_name": post["author_name"],
        "source_file": post["source_file"],
        "core_summary": core_summary,
        "mentions": mentions,
        "trade_signals": trade_signals,
        "background_tags": background_tags,
        "spec_candidate": spec_candidate,
    }


def parse_extend_accounts(extend_file: Path) -> list[dict[str, str]]:
    if not extend_file.exists():
        return []
    text = extend_file.read_text(encoding="utf-8")
    pattern = re.compile(
        r"- \[(enabled|disabled)\] name: (?P<name>.+?)\n\s+url: (?P<url>https?://[^\s]+)",
        flags=re.MULTILINE,
    )
    accounts = []
    for match in pattern.finditer(text):
        accounts.append(
            {
                "enabled": match.group(1),
                "name": match.group("name").strip(),
                "url": match.group("url").strip(),
            }
        )
    return accounts


def match_extend_account(
    author_key: str,
    author_name: str,
    enabled_accounts: list[dict[str, str]],
) -> dict[str, str] | None:
    if not enabled_accounts:
        return None

    author_variants = {
        normalize_account_name(author_key),
        normalize_account_name(author_name),
        normalize_account_name(author_key.replace("_", " ")),
    }
    author_variants.discard("")

    for account in enabled_accounts:
        if account["enabled"] != "enabled":
            continue
        account_name = normalize_account_name(account["name"])
        if account_name and account_name in author_variants:
            return account
    return None


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def build_author_markdown(
    author_key: str,
    author_name: str,
    author_url: str,
    date_text: str,
    posts: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
) -> str:
    mention_counter = Counter()
    trade_counter = Counter()
    background_counter = Counter()
    candidate_related: list[dict[str, str]] = []

    for analysis in analyses:
        mention_counter.update(analysis["mentions"])
        trade_counter.update(analysis["trade_signals"])
        background_counter.update(analysis["background_tags"])
        if analysis["spec_candidate"]:
            candidate_related.append(
                {
                    "publish_time": analysis["publish_time"],
                    "reason": analysis["spec_candidate"]["reason"],
                    "evidence": analysis["spec_candidate"]["evidence"],
                    "url": analysis["url"],
                }
            )

    core_points = [f"- {analysis['publish_time']}：{analysis['core_summary']}" for analysis in analyses[:8]]
    mention_points = [f"- {item}（{count}）" for item, count in mention_counter.most_common(8)] or ["- 无明显高频标的或事件"]
    trade_points = [f"- {item}（{count}）" for item, count in trade_counter.most_common(6)] or ["- 无明确交易表态"]
    background_points = [f"- {item}（{count}）" for item, count in background_counter.most_common(6)] or ["- 无明显统一背景语境"]
    explicit_related = ["- 暂无与现有 spec 的明确命中项"]
    candidate_points = [
        "\n".join(
            [
                f"- 候选观察点：{item['reason']}",
                f"  证据：{item['publish_time']} {item['evidence']}",
                f"  原帖：{item['url']}",
            ]
        )
        for item in candidate_related[:8]
    ] or ["- 暂无候选相关内容"]
    appendix = [f"- {post['publish_time']}｜{post['title']}｜{post['url']}" for post in posts]

    lines = [
        f"# {author_name} - {date_text} 日报",
        "",
        "## 基本信息",
        f"- 博主标识：{author_key}",
        f"- 博主名称：{author_name}",
        f"- 账号主页：{author_url or '未知'}",
        f"- 抓取日期：{date_text}",
        f"- 抓取帖子数：{len(posts)}",
        f"- 成功纳入汇总数：{len(analyses)}",
        f"- 异常说明：无",
        "",
        "## 1. 核心内容",
        "### 今日主要观点",
        *core_points,
        "",
        "### 重点提及标的 / 指数 / 事件",
        *mention_points,
        "",
        "### 明确交易表态",
        *trade_points,
        "",
        "## 2. 背景语境",
        "### 今日观点出现的触发因素",
        *background_points,
        "",
        "### 上下文补充",
        "- 以当日抓取到的原始帖子为准，未纳入跨日历史扩展解释。",
        "",
        "### 需要注意的语气与立场变化",
        "- 当前版本仅保留结构化观察，语气变化需人工复核。",
        "",
        "## 3. Spec相关",
        "### 明确相关",
        *explicit_related,
        "",
        "### 候选相关",
        *candidate_points,
        "",
        "## 附录",
        "### 原始帖子索引",
        *appendix,
        "",
    ]
    return "\n".join(lines)


def build_market_markdown(
    date_text: str,
    author_summaries: list[dict[str, Any]],
    enabled_accounts: list[dict[str, str]],
) -> str:
    mention_counter = Counter()
    trade_counter = Counter()
    background_counter = Counter()
    candidate_related: list[dict[str, str]] = []

    for summary in author_summaries:
        mention_counter.update(summary["mention_counter"])
        trade_counter.update(summary["trade_counter"])
        background_counter.update(summary["background_counter"])
        candidate_related.extend(summary["candidate_related"])

    expected_accounts = [item for item in enabled_accounts if item["enabled"] == "enabled"]
    actual_names = {
        normalize_account_name(summary["matched_account_name"] or summary["author_name"])
        for summary in author_summaries
    }
    missing = [item["name"] for item in expected_accounts if normalize_account_name(item["name"]) not in actual_names]

    high_theme_points = [f"- {item}（{count}）" for item, count in background_counter.most_common(8)] or ["- 无明显高频主题"]
    high_mention_points = [f"- {item}（{count}）" for item, count in mention_counter.most_common(8)] or ["- 无明显高频标的"]
    common_view_points = [f"- {item}（{count}）" for item, count in trade_counter.most_common(6)] or ["- 无明确共同交易表态"]
    explicit_related = ["- 暂无与现有 spec 的明确命中项"]
    candidate_points = [
        "\n".join(
            [
                f"- 候选观察点：{item['reason']}",
                f"  来源博主：{item['author_name']}",
                f"  证据：{item['evidence']}",
                f"  原帖：{item['url']}",
            ]
        )
        for item in candidate_related[:12]
    ] or ["- 暂无候选相关内容"]

    lines = [
        f"# 全博主总汇总 - {date_text}",
        "",
        "## 基本信息",
        f"- 覆盖博主数：{len(author_summaries)}",
        f"- 成功汇总博主数：{len(author_summaries)}",
        f"- 缺失/异常博主：{', '.join(missing) if missing else '无'}",
        "",
        "## 1. 核心内容",
        "### 今日高频主题",
        *high_theme_points,
        "",
        "### 今日高频标的 / 指数 / 事件",
        *high_mention_points,
        "",
        "### 今日最重要的共同观点",
        *common_view_points,
        "",
        "## 2. 背景语境",
        "### 今日市场触发因素",
        *high_theme_points,
        "",
        "### 共识形成背景",
        "- 当前版本按关键词聚合，需结合单博主日报做人工复核。",
        "",
        "### 分歧形成背景",
        "- 当前版本不自动推断分歧，仅保留候选观察点供复核。",
        "",
        "## 3. Spec相关",
        "### 明确相关",
        *explicit_related,
        "",
        "### 候选相关",
        *candidate_points,
        "",
        "## 附录",
        "### 博主日报索引",
        *[f"- {summary['author_name']}｜{summary['summary_path']}" for summary in author_summaries],
        "",
    ]
    return "\n".join(lines)


def generate_daily_summary(
    target_date: str,
    output_root: str | Path,
    extend_file: str | Path | None = None,
) -> dict[str, Any]:
    date_obj = datetime.strptime(target_date, "%Y-%m-%d")
    date_slug = date_obj.strftime("%Y%m%d")
    output_root = Path(output_root).expanduser().resolve()
    processing_root = ensure_dir(output_root / "processing" / date_slug)
    summary_root = ensure_dir(output_root / "summaries" / date_slug)

    for layer in ("raw_index", "normalized", "extracted", "post_analysis", "author_daily", "market_daily"):
        ensure_dir(processing_root / layer)

    author_dirs = discover_author_dirs(output_root, date_slug)
    enabled_accounts = parse_extend_accounts(Path(extend_file)) if extend_file else []
    author_summaries: list[dict[str, Any]] = []

    for author_dir in author_dirs:
        raw_files = sorted(author_dir.glob("*.txt"))
        posts = [parse_post_file(path) for path in raw_files]
        if not posts:
            continue

        author_key_match = re.match(rf"(.+)_{date_slug}$", author_dir.name)
        author_key = author_key_match.group(1) if author_key_match else author_dir.name
        author_name = posts[0]["author_name"] or author_key.replace("_", " ")
        matched_account = match_extend_account(author_key, author_name, enabled_accounts)
        author_url = matched_account["url"] if matched_account else ""

        write_json(
            processing_root / "raw_index" / f"{author_key}.json",
            {"author_key": author_key, "date": target_date, "files": [str(path) for path in raw_files]},
        )

        analyses: list[dict[str, Any]] = []
        for post in posts:
            normalized_path = processing_root / "normalized" / author_key / f"{post['content_id'] or slugify(post['title'])}.json"
            write_json(normalized_path, post)

            analysis = analyze_post(post)
            analyses.append(analysis)
            extracted_path = processing_root / "extracted" / author_key / f"{analysis['content_id'] or slugify(analysis['title'])}.json"
            write_json(extracted_path, analysis)

            post_md = "\n".join(
                [
                    f"# {analysis['title'] or analysis['content_id']}",
                    "",
                    f"- 发布时间：{analysis['publish_time']}",
                    f"- 原始链接：{analysis['url']}",
                    f"- 核心摘要：{analysis['core_summary']}",
                    f"- 提及标的/事件：{', '.join(analysis['mentions']) if analysis['mentions'] else '无'}",
                    f"- 交易表态：{', '.join(analysis['trade_signals']) if analysis['trade_signals'] else '无'}",
                    f"- 背景标签：{', '.join(analysis['background_tags']) if analysis['background_tags'] else '无'}",
                    f"- Spec候选：{analysis['spec_candidate']['reason'] if analysis['spec_candidate'] else '无'}",
                    "",
                ]
            )
            write_text(
                processing_root / "post_analysis" / author_key / f"{analysis['content_id'] or slugify(analysis['title'])}.md",
                post_md,
            )

        analyses.sort(key=lambda item: item["publish_time"])
        author_markdown = build_author_markdown(author_key, author_name, author_url, target_date, posts, analyses)
        final_author_path = summary_root / f"{author_key}.md"
        write_text(final_author_path, author_markdown)

        author_aggregate = {
            "author_key": author_key,
            "author_name": author_name,
            "matched_account_name": matched_account["name"] if matched_account else "",
            "author_url": author_url,
            "date": target_date,
            "post_count": len(posts),
            "mention_counter": Counter(item for analysis in analyses for item in analysis["mentions"]),
            "trade_counter": Counter(item for analysis in analyses for item in analysis["trade_signals"]),
            "background_counter": Counter(item for analysis in analyses for item in analysis["background_tags"]),
            "candidate_related": [
                {
                    "author_name": author_name,
                    "reason": analysis["spec_candidate"]["reason"],
                    "evidence": analysis["spec_candidate"]["evidence"],
                    "url": analysis["url"],
                }
                for analysis in analyses
                if analysis["spec_candidate"]
            ],
            "summary_path": str(final_author_path),
        }
        write_json(processing_root / "author_daily" / f"{author_key}.json", author_aggregate)
        author_summaries.append(author_aggregate)

    market_payload = {
        "date": target_date,
        "author_count": len(author_summaries),
        "authors": author_summaries,
    }
    write_json(processing_root / "market_daily" / "overview.json", market_payload)
    market_markdown = build_market_markdown(target_date, author_summaries, enabled_accounts)
    write_text(summary_root / "daily_summary.md", market_markdown)

    return {
        "date": target_date,
        "author_count": len(author_summaries),
        "summary_dir": str(summary_root),
        "processing_dir": str(processing_root),
    }


def main() -> int:
    args = parse_args()
    extend_path = Path(__file__).resolve().parent.parent / "EXTEND.md"
    result = generate_daily_summary(args.date, Path(args.output_dir), extend_file=extend_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
