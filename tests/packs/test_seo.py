"""Tests for SEO pack rules."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.seo.seo_page_metadata import SeoPageMetadata
from agentlint.packs.seo.seo_open_graph import SeoOpenGraph
from agentlint.packs.seo.seo_semantic_html import SeoSemanticHtml
from agentlint.packs.seo.seo_structured_data import SeoStructuredData


def _ctx(tool_name: str, tool_input: dict, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/tmp/project",
        config=config or {},
    )


# ---------------------------------------------------------------------------
# SeoPageMetadata
# ---------------------------------------------------------------------------


class TestSeoPageMetadata:
    rule = SeoPageMetadata()

    def test_detects_page_without_metadata(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": "export default function Home() { return <div>Hello</div> }",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_allows_page_with_head(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": "return <><Head><title>Home</title></Head><div>Hello</div></>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_page_with_helmet(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": "<Helmet><title>Home</title></Helmet>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_page_with_generate_metadata(self):
        ctx = _ctx("Write", {
            "file_path": "app/page.tsx",
            "content": "export const generateMetadata = async () => ({ title: 'Home' })",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_page_files(self):
        ctx = _ctx("Write", {
            "file_path": "components/Button.tsx",
            "content": "export default function Button() { return <button /> }",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_frontend_extensions(self):
        ctx = _ctx("Write", {
            "file_path": "pages/api/users.ts",
            "content": "export default handler",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_custom_page_patterns(self):
        ctx = _ctx("Write", {
            "file_path": "views/Home.tsx",
            "content": "export default function Home() { return <div /> }",
        }, config={"page_patterns": ["views/"]})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_custom_metadata_components(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": "<SEO title='Home' />",
        }, config={"metadata_components": ["<SEO"]})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# SeoOpenGraph
# ---------------------------------------------------------------------------


class TestSeoOpenGraph:
    rule = SeoOpenGraph()

    def test_detects_metadata_without_og(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": "<Head><title>Home</title></Head>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "og:title" in violations[0].message

    def test_allows_metadata_with_all_og(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": '<Head><title>Home</title><meta property="og:title" /><meta property="og:description" /><meta property="og:image" /></Head>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_pages_without_metadata(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": "export default function Home() { return <div /> }",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_page_files(self):
        ctx = _ctx("Write", {
            "file_path": "components/Header.tsx",
            "content": "<Head><title>Site</title></Head>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_custom_required_properties(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": '<Head><title>Home</title><meta property="og:title" /></Head>',
        }, config={"required_properties": ["og:title"]})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# SeoSemanticHtml
# ---------------------------------------------------------------------------


class TestSeoSemanticHtml:
    rule = SeoSemanticHtml()

    def test_detects_div_soup(self):
        divs = "\n".join(f"<div>Block {i}</div>" for i in range(12))
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": divs,
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "12" in violations[0].message

    def test_allows_divs_with_semantic(self):
        divs = "\n".join(f"<div>Block {i}</div>" for i in range(12))
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": f"<main>\n{divs}\n</main>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_few_divs(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": "<div>One</div>\n<div>Two</div>\n<div>Three</div>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_page_files(self):
        divs = "\n".join(f"<div>Block {i}</div>" for i in range(15))
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": divs,
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_custom_min_threshold(self):
        divs = "\n".join(f"<div>Block {i}</div>" for i in range(6))
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": divs,
        }, config={"min_div_threshold": 5})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# SeoStructuredData
# ---------------------------------------------------------------------------


class TestSeoStructuredData:
    rule = SeoStructuredData()

    def test_detects_product_page_without_jsonld(self):
        ctx = _ctx("Write", {
            "file_path": "pages/product/[id].tsx",
            "content": "export default function Product() { return <div /> }",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_product_page_with_jsonld(self):
        ctx = _ctx("Write", {
            "file_path": "pages/product/[id].tsx",
            "content": '<script type="application/ld+json">{}</script>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_detects_blog_post_without_jsonld(self):
        ctx = _ctx("Write", {
            "file_path": "pages/blog/post.tsx",
            "content": "export default function Post() { return <article /> }",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ignores_non_content_pages(self):
        ctx = _ctx("Write", {
            "file_path": "pages/settings.tsx",
            "content": "export default function Settings() { return <div /> }",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_frontend_files(self):
        ctx = _ctx("Write", {
            "file_path": "api/product.ts",
            "content": "export default handler",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_custom_content_patterns(self):
        ctx = _ctx("Write", {
            "file_path": "pages/listing/item.tsx",
            "content": "export default function Item() { return <div /> }",
        }, config={"content_path_patterns": ["listing"]})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# Pack loader
# ---------------------------------------------------------------------------


class TestSeoPackLoader:
    def test_load_seo_pack(self):
        from agentlint.packs import load_rules

        rules = load_rules(["seo"])
        assert len(rules) == 4
        ids = {r.id for r in rules}
        assert "seo-page-metadata" in ids
        assert "seo-open-graph" in ids
        assert "seo-semantic-html" in ids
        assert "seo-structured-data" in ids

    def test_all_rules_have_seo_pack(self):
        from agentlint.packs import load_rules

        rules = load_rules(["seo"])
        for rule in rules:
            assert rule.pack == "seo"
