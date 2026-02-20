"""Tests for frontend pack rules."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.frontend.a11y_image_alt import A11yImageAlt
from agentlint.packs.frontend.a11y_form_labels import A11yFormLabels
from agentlint.packs.frontend.a11y_interactive_elements import A11yInteractiveElements
from agentlint.packs.frontend.a11y_heading_hierarchy import A11yHeadingHierarchy
from agentlint.packs.frontend.mobile_touch_targets import MobileTouchTargets
from agentlint.packs.frontend.mobile_responsive_patterns import MobileResponsivePatterns
from agentlint.packs.frontend.style_no_arbitrary_values import StyleNoArbitraryValues
from agentlint.packs.frontend.style_focus_visible import StyleFocusVisible


def _ctx(tool_name: str, tool_input: dict, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/tmp/project",
        config=config or {},
    )


# ---------------------------------------------------------------------------
# A11yImageAlt
# ---------------------------------------------------------------------------


class TestA11yImageAlt:
    rule = A11yImageAlt()

    def test_detects_img_without_alt(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": '<img src="/photo.jpg" />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_allows_img_with_alt(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": '<img src="/photo.jpg" alt="A sunset" />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_decorative_alt(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": '<img src="/divider.png" alt="" />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_detects_image_component(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": '<Image src="/photo.jpg" width={100} />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_extra_components_config(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": '<Avatar src="/user.jpg" />',
        }, config={"extra_components": ["Avatar"]})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ignores_non_frontend_files(self):
        ctx = _ctx("Write", {
            "file_path": "app/models.py",
            "content": '<img src="/photo.jpg" />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_write_tools(self):
        ctx = _ctx("Read", {"file_path": "components/Card.tsx"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_works_with_jsx(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.jsx",
            "content": '<img src={photo} className="rounded" />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_works_with_vue(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.vue",
            "content": '<img :src="photo" />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# A11yFormLabels
# ---------------------------------------------------------------------------


class TestA11yFormLabels:
    rule = A11yFormLabels()

    def test_detects_input_without_label(self):
        ctx = _ctx("Write", {
            "file_path": "components/Form.tsx",
            "content": '<input type="text" name="email" />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_input_with_aria_label(self):
        ctx = _ctx("Write", {
            "file_path": "components/Form.tsx",
            "content": '<input type="text" aria-label="Email" />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_input_with_aria_labelledby(self):
        ctx = _ctx("Write", {
            "file_path": "components/Form.tsx",
            "content": '<input type="text" aria-labelledby="email-label" />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_input_with_id_and_label(self):
        ctx = _ctx("Write", {
            "file_path": "components/Form.tsx",
            "content": '<label for="email">Email</label>\n<input type="text" id="email" />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_hidden_inputs(self):
        ctx = _ctx("Write", {
            "file_path": "components/Form.tsx",
            "content": '<input type="hidden" name="csrf" />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_submit_buttons(self):
        ctx = _ctx("Write", {
            "file_path": "components/Form.tsx",
            "content": '<input type="submit" value="Send" />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_detects_select_without_label(self):
        ctx = _ctx("Write", {
            "file_path": "components/Form.tsx",
            "content": '<select name="country"><option>US</option></select>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_detects_textarea_without_label(self):
        ctx = _ctx("Write", {
            "file_path": "components/Form.tsx",
            "content": '<textarea name="bio" />',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# A11yInteractiveElements
# ---------------------------------------------------------------------------


class TestA11yInteractiveElements:
    rule = A11yInteractiveElements()

    def test_detects_div_with_onclick_no_role(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": '<div onClick={handleClick} className="btn">Click</div>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "role" in violations[0].message

    def test_allows_div_with_role_and_tabindex(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": '<div onClick={handleClick} role="button" tabIndex={0}>Click</div>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_detects_span_with_onclick(self):
        ctx = _ctx("Write", {
            "file_path": "components/Tag.tsx",
            "content": '<span onClick={remove} className="tag">x</span>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_detects_link_anti_pattern_click_here(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": '<a href="/docs">click here</a>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "click here" in violations[0].message

    def test_detects_link_anti_pattern_read_more(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": '<a href="/blog/post">read more</a>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_descriptive_link(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": '<a href="/docs">View documentation</a>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_frontend(self):
        ctx = _ctx("Write", {
            "file_path": "app.py",
            "content": '<div onClick={handleClick}>Click</div>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# A11yHeadingHierarchy
# ---------------------------------------------------------------------------


class TestA11yHeadingHierarchy:
    rule = A11yHeadingHierarchy()

    def test_detects_multiple_h1(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": "<h1>Title</h1>\n<h1>Subtitle</h1>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "Multiple <h1>" in violations[0].message

    def test_allows_single_h1(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": "<h1>Title</h1>\n<h2>Section</h2>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_detects_skipped_level(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": "<h1>Title</h1>\n<h3>Subsection</h3>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "Skipped heading level" in violations[0].message

    def test_allows_sequential_levels(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": "<h1>A</h1>\n<h2>B</h2>\n<h3>C</h3>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_going_back_up(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": "<h1>A</h1>\n<h2>B</h2>\n<h3>C</h3>\n<h2>D</h2>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_custom_max_h1(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Home.tsx",
            "content": "<h1>A</h1>\n<h1>B</h1>\n<h1>C</h1>",
        }, config={"max_h1": 2})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ignores_non_frontend(self):
        ctx = _ctx("Write", {
            "file_path": "README.md",
            "content": "<h1>Title</h1>\n<h1>Another</h1>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# MobileTouchTargets
# ---------------------------------------------------------------------------


class TestMobileTouchTargets:
    rule = MobileTouchTargets()

    def test_detects_small_button(self):
        ctx = _ctx("Write", {
            "file_path": "components/Icon.tsx",
            "content": '<button className="w-6 h-6 p-1">X</button>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_allows_button_with_min_size(self):
        ctx = _ctx("Write", {
            "file_path": "components/Icon.tsx",
            "content": '<button className="w-6 h-6 min-w-11 min-h-11">X</button>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_normal_buttons(self):
        ctx = _ctx("Write", {
            "file_path": "components/Button.tsx",
            "content": '<button className="px-4 py-2">Submit</button>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# MobileResponsivePatterns
# ---------------------------------------------------------------------------


class TestMobileResponsivePatterns:
    rule = MobileResponsivePatterns()

    def test_detects_large_grid_without_responsive(self):
        ctx = _ctx("Write", {
            "file_path": "components/Grid.tsx",
            "content": '<div className="grid grid-cols-4 gap-4">',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1
        assert "grid-cols-4" in violations[0].message

    def test_allows_grid_with_responsive(self):
        ctx = _ctx("Write", {
            "file_path": "components/Grid.tsx",
            "content": '<div className="grid grid-cols-2 md:grid-cols-4 gap-4">',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_small_grid(self):
        ctx = _ctx("Write", {
            "file_path": "components/Grid.tsx",
            "content": '<div className="grid grid-cols-2 gap-4">',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_detects_fixed_large_width(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": '<div className="w-[500px]">',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "500px" in violations[0].message

    def test_allows_small_fixed_width(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": '<div className="w-[200px]">',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_detects_hover_only(self):
        ctx = _ctx("Write", {
            "file_path": "components/Menu.tsx",
            "content": '<div onMouseEnter={show}>Hover me</div>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "Hover-only" in violations[0].message

    def test_allows_hover_with_click(self):
        ctx = _ctx("Write", {
            "file_path": "components/Menu.tsx",
            "content": '<div onMouseEnter={show} onClick={toggle}>Hover me</div>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# StyleNoArbitraryValues
# ---------------------------------------------------------------------------


class TestStyleNoArbitraryValues:
    rule = StyleNoArbitraryValues()

    def test_detects_hex_color(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": '<div className="bg-[#ff0000]">',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "hex color" in violations[0].message.lower()

    def test_detects_text_hex_color(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": '<p className="text-[#333]">Hello</p>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_detects_pixel_spacing(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": '<div className="p-[24px] m-[16px]">',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 2

    def test_allows_design_tokens(self):
        ctx = _ctx("Write", {
            "file_path": "components/Card.tsx",
            "content": '<div className="bg-primary text-gray-500 p-4 m-6">',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_frontend(self):
        ctx = _ctx("Write", {
            "file_path": "styles.py",
            "content": "bg-[#ff0000]",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# StyleFocusVisible
# ---------------------------------------------------------------------------


class TestStyleFocusVisible:
    rule = StyleFocusVisible()

    def test_detects_outline_none_without_ring(self):
        ctx = _ctx("Write", {
            "file_path": "components/Button.tsx",
            "content": '<button className="outline-none">Click</button>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_allows_outline_none_with_focus_ring(self):
        ctx = _ctx("Write", {
            "file_path": "components/Button.tsx",
            "content": '<button className="outline-none focus:ring-2 focus:ring-blue-500">Click</button>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_outline_none_with_focus_visible_ring(self):
        ctx = _ctx("Write", {
            "file_path": "components/Button.tsx",
            "content": '<button className="outline-none focus-visible:ring-2">Click</button>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_no_outline_none(self):
        ctx = _ctx("Write", {
            "file_path": "components/Button.tsx",
            "content": '<button className="bg-blue-500 text-white">Click</button>',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# Pack loader
# ---------------------------------------------------------------------------


class TestFrontendPackLoader:
    def test_load_frontend_pack(self):
        from agentlint.packs import load_rules

        rules = load_rules(["frontend"])
        assert len(rules) == 8
        ids = {r.id for r in rules}
        assert "a11y-image-alt" in ids
        assert "a11y-form-labels" in ids
        assert "a11y-interactive-elements" in ids
        assert "a11y-heading-hierarchy" in ids
        assert "mobile-touch-targets" in ids
        assert "mobile-responsive-patterns" in ids
        assert "style-no-arbitrary-values" in ids
        assert "style-focus-visible" in ids

    def test_all_rules_have_frontend_pack(self):
        from agentlint.packs import load_rules

        rules = load_rules(["frontend"])
        for rule in rules:
            assert rule.pack == "frontend"
