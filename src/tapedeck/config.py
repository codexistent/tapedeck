"""tapedeck.yaml: where the agent, cases, tapes, simulators and model live."""

from __future__ import annotations

import importlib
import os
import sys
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .backends import Backend, OpenAIBackend
from .matcher import MatcherConfig
from .simulators import Simulator

AgentFn = Callable[[str, dict[str, Any], str], str]


class BackendConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["openai", "python"] = "openai"
    # kind: openai
    model: str | None = None
    model_env: str = "TAPEDECK_MODEL"
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    # kind: python -- "module:function", called as function(seed=int) -> Backend
    factory: str | None = None


class CaseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: str
    checks: str
    simulators: str | None = None
    cases: str = "cases.yaml"
    tapes: str = "tapes"
    baseline: str = "tapedeck-baseline.json"
    prompt: str = "prompts/v1.txt"
    backends: dict[str, BackendConfig]
    backend: str = "live"
    runs: int = 10
    workers: int = 4
    alpha: float = 0.05
    min_effect: float = 0.2
    budget_usd: float = 2.0
    prices: dict[str, tuple[float, float]] = Field(default_factory=dict)
    matchers: MatcherConfig = Field(default_factory=MatcherConfig)
    pythonpath: list[str] = Field(default_factory=lambda: ["."])

    root: Path = Field(default=Path("."), exclude=True)

    # -- loading -----------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path = "tapedeck.yaml") -> Config:
        file = Path(path).resolve()
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        config = cls.model_validate(data)
        config.root = file.parent
        for entry in reversed(config.pythonpath):
            resolved = str((config.root / entry).resolve())
            if resolved not in sys.path:
                sys.path.insert(0, resolved)
        env_backend = os.environ.get("TAPEDECK_BACKEND")
        if env_backend:
            config.backend = env_backend
        if config.backend not in config.backends:
            raise ValueError(
                f"backend {config.backend!r} not in backends: {sorted(config.backends)}"
            )
        return config

    def path(self, relative: str) -> Path:
        return self.root / relative

    # -- resolved pieces ----------------------------------------------------

    def load_cases(self) -> list[CaseSpec]:
        raw = yaml.safe_load(self.path(self.cases).read_text(encoding="utf-8")) or []
        cases = [CaseSpec.model_validate(item) for item in raw]
        ids = [c.id for c in cases]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate case ids in cases file")
        return cases

    def tape_path(self, case_id: str) -> Path:
        return self.path(self.tapes) / f"{case_id}.jsonl"

    def agent_fn(self) -> AgentFn:
        fn: AgentFn = _resolve(self.agent)
        return fn

    def load_checks(self) -> None:
        importlib.import_module(self.checks)

    def make_simulators(self) -> list[Simulator]:
        if self.simulators is None:
            return []
        factory: Callable[[], list[Simulator]] = _resolve(self.simulators)
        return list(factory())

    def make_backend(self, seed: int = 0) -> Backend:
        spec = self.backends[self.backend]
        if spec.kind == "python":
            if not spec.factory:
                raise ValueError(f"backend {self.backend!r}: kind python needs a factory")
            factory: Callable[..., Backend] = _resolve(spec.factory)
            return factory(seed=seed)
        model = spec.model or os.environ.get(spec.model_env)
        if not model:
            raise RuntimeError(f"no model: set {spec.model_env} (e.g. in .env)")
        return OpenAIBackend(model, base_url=spec.base_url, api_key_env=spec.api_key_env)

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        price_in, price_out = self.prices.get(model, (0.0, 0.0))
        return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def _resolve(target: str) -> Any:
    module_name, _, attr = target.partition(":")
    if not attr:
        raise ValueError(f"{target!r}: expected 'module:attribute'")
    module = importlib.import_module(module_name)
    try:
        return getattr(module, attr)
    except AttributeError:
        raise ValueError(f"{module_name} has no attribute {attr!r}") from None


def stable_seed(*parts: object) -> int:
    """A seed that is the same on every machine and Python run (unlike hash())."""
    return zlib.crc32("|".join(map(str, parts)).encode("utf-8"))
