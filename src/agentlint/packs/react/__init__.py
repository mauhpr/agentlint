"""React rule pack — React-specific UX pattern rules."""

from agentlint.packs.react.react_empty_state import ReactEmptyState
from agentlint.packs.react.react_lazy_loading import ReactLazyLoading
from agentlint.packs.react.react_query_loading_state import ReactQueryLoadingState

RULES = [
    ReactQueryLoadingState(),
    ReactEmptyState(),
    ReactLazyLoading(),
]
