"""Frontend rule pack — accessibility, mobile, and style rules."""
from agentlint.packs.frontend.a11y_image_alt import A11yImageAlt
from agentlint.packs.frontend.a11y_form_labels import A11yFormLabels
from agentlint.packs.frontend.a11y_interactive_elements import A11yInteractiveElements
from agentlint.packs.frontend.a11y_heading_hierarchy import A11yHeadingHierarchy
from agentlint.packs.frontend.mobile_touch_targets import MobileTouchTargets
from agentlint.packs.frontend.mobile_responsive_patterns import MobileResponsivePatterns
from agentlint.packs.frontend.style_no_arbitrary_values import StyleNoArbitraryValues
from agentlint.packs.frontend.style_focus_visible import StyleFocusVisible

RULES = [
    A11yImageAlt(),
    A11yFormLabels(),
    A11yInteractiveElements(),
    A11yHeadingHierarchy(),
    MobileTouchTargets(),
    MobileResponsivePatterns(),
    StyleNoArbitraryValues(),
    StyleFocusVisible(),
]
