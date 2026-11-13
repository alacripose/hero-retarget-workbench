"""What the workbench should ask for next.

The Popit model shows one hub and a small set of tools, not every control at
once. This resolver turns the scene's state into that one line, so the panel can
name the next unanswered step instead of printing a hint under every control.

Pure data in, pure data out: the addon passes plain values and the tests do too.
"""
from __future__ import annotations

from typing import NamedTuple


class Step(NamedTuple):
    key: str
    label: str
    icon: str
    detail: str


# Labels stay short: the sidebar names one line, and the detail column says which
# panel the line belongs to.
STEPS: tuple[Step, ...] = (
    Step("setup", "Set the game folders", "SETTINGS", "Setup"),
    Step("build", "Detect the live build", "WORLD", "Source"),
    Step("hero", "Choose a hero", "OUTLINER_OB_ARMATURE", "Source"),
    Step("extract", "Extract the hero", "EXPORT", "Source"),
    Step("import", "Import the skeleton", "ARMATURE_DATA", "Source"),
    Step("model", "Import your model", "MESH_DATA", "Source"),
    Step("fit", "Fit the model", "TRANSFORM_ORIGINS", "Source"),
    Step("parts", "Choose the parts", "GROUP", "Parts & Materials"),
    Step("weights", "Solve weights", "MOD_VERTEX_WEIGHT", "Weights & Proof"),
    Step("proof", "Mint the proof", "CHECKMARK", "Weights & Proof"),
    Step("stage", "Export & stage", "PACKAGE", "CSDK Addon"),
    Step("compile", "Compile the addon", "PLAY", "CSDK Addon"),
)

DONE = Step("done", "Everything answered", "CHECKMARK", "")


def next_step(state: dict) -> Step:
    """The first step whose flag is false, in workflow order."""
    for step in STEPS:
        if not state.get(step.key, False):
            return step
    return DONE


def progress(state: dict) -> tuple[int, int]:
    """Answered steps against the total, for the compact stage line."""
    answered = sum(1 for step in STEPS if state.get(step.key, False))
    return answered, len(STEPS)
