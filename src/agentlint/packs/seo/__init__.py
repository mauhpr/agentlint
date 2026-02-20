"""SEO rule pack — meta tags, semantic HTML, and structured data rules."""
from agentlint.packs.seo.seo_page_metadata import SeoPageMetadata
from agentlint.packs.seo.seo_open_graph import SeoOpenGraph
from agentlint.packs.seo.seo_semantic_html import SeoSemanticHtml
from agentlint.packs.seo.seo_structured_data import SeoStructuredData

RULES = [
    SeoPageMetadata(),
    SeoOpenGraph(),
    SeoSemanticHtml(),
    SeoStructuredData(),
]
