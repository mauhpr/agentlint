"""React rule pack — React-specific UX pattern rules."""
from agentlint.packs.react.react_query_loading_state import ReactQueryLoadingState
from agentlint.packs.react.react_empty_state import ReactEmptyState
from agentlint.packs.react.react_lazy_loading import ReactLazyLoading

RULES = [
    ReactQueryLoadingState(),
    ReactEmptyState(),
    ReactLazyLoading(),
]
