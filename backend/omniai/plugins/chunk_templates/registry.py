from __future__ import annotations

from omniai.plugins.chunk_templates.general import GeneralChunkTemplate
from omniai.plugins.chunk_templates.qa import QaChunkTemplate
from omniai.plugins.chunk_templates.small_to_big import SmallToBigChunkTemplate
from omniai.ports.chunk_template import ChunkTemplatePort


class ChunkTemplateRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, ChunkTemplatePort] = {}

    def register(self, template: ChunkTemplatePort) -> None:
        self._templates[template.name] = template

    def get(self, name: str) -> ChunkTemplatePort:
        template = self._templates.get(name) or self._templates.get("general")
        if template is None:
            raise KeyError(f"No chunk template registered for {name!r}.")
        return template

    def names(self) -> list[str]:
        return sorted(self._templates.keys())


def build_default_registry() -> ChunkTemplateRegistry:
    registry = ChunkTemplateRegistry()
    registry.register(GeneralChunkTemplate())
    registry.register(QaChunkTemplate())
    registry.register(SmallToBigChunkTemplate())
    return registry
