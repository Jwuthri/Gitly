"""Label each slice with a single-sentence intent and a clean PR title.

`HeuristicLabeler` (default, no network) keeps the planner's structural titles and writes a
terse intent from the slice's symbols/files. `ClaudeLabeler` (optional) sends all slice
diffs in one cached call and asks the model for a title + one-sentence intent per slice.

The labeler never changes hunk membership — only titles/intents — so it cannot affect
completeness.
"""
from __future__ import annotations

import json
import os
from typing import Protocol

from ..diff.materialize import slice_patch_text
from ..diff.models import Diff, SlicePlan

_SYSTEM = (
    "You label code-change slices for a PR-splitting tool. For each slice you are given its "
    "diff. Return a single-sentence imperative intent and a concise PR title (<60 chars). "
    "If a slice mixes unrelated purposes, set \"muddy\": true. Respond ONLY with a JSON array "
    "of objects {\"order\": int, \"title\": str, \"intent\": str, \"muddy\": bool}."
)


class Labeler(Protocol):
    def label(self, diff: Diff, plan: SlicePlan) -> SlicePlan: ...


class HeuristicLabeler:
    def label(self, diff: Diff, plan: SlicePlan) -> SlicePlan:
        hunks = diff.hunk_by_id()
        for s in plan.slices:
            files = sorted({hunks[h].file_path for h in s.hunk_ids if h in hunks} | set(s.atomic_paths))
            defs = sorted({sym for h in s.hunk_ids if h in hunks for sym in hunks[h].symbols_defined})
            bits: list[str] = []
            if defs:
                bits.append("introduces " + ", ".join(defs[:3]) + ("…" if len(defs) > 3 else ""))
            bits.append(f"touches {len(files)} file(s)")
            s.intent = s.intent or f"{s.title} — {'; '.join(bits)}."
        return plan


class ClaudeLabeler:
    """Optional. Requires ANTHROPIC_API_KEY and the `anthropic` package.

    Note: diffs are sent to the model. The gitly secret firewall should redact slice
    patches before this call in any hosted deployment.
    """

    def __init__(self, model: str = "claude-sonnet-4-6", max_diff_chars: int = 6000):
        self.model = model
        self.max_diff_chars = max_diff_chars

    def available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GITLY_ANTHROPIC_API_KEY"))

    def label(self, diff: Diff, plan: SlicePlan) -> SlicePlan:
        if not self.available():
            return HeuristicLabeler().label(diff, plan)
        try:
            import anthropic
        except ImportError:
            return HeuristicLabeler().label(diff, plan)

        payload = []
        for s in plan.slices:
            patch = slice_patch_text(diff, s.hunk_ids)[: self.max_diff_chars]
            atomic = f"\n(atomic files: {', '.join(s.atomic_paths)})" if s.atomic_paths else ""
            payload.append(f"=== SLICE {s.order} ===\n{patch}{atomic}")
        user = "Label these slices:\n\n" + "\n\n".join(payload)

        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        try:
            labels = json.loads(text[text.index("[") : text.rindex("]") + 1])
        except (ValueError, json.JSONDecodeError):
            return HeuristicLabeler().label(diff, plan)

        by_order = {item["order"]: item for item in labels if "order" in item}
        for s in plan.slices:
            item = by_order.get(s.order)
            if item:
                s.title = item.get("title", s.title)
                s.intent = item.get("intent", s.intent)
                if item.get("muddy"):
                    plan.notes.append(f"Slice {s.order} ('{s.title}') may mix multiple purposes.")
        return plan


def get_labeler(prefer_llm: bool = True) -> Labeler:
    if prefer_llm:
        claude = ClaudeLabeler()
        if claude.available():
            return claude
    return HeuristicLabeler()
