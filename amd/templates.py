from __future__ import annotations

from pathlib import Path
from textwrap import dedent


TIMELINE_BLOCK = """## Timeline
<!-- amd:timeline:start -->
<!-- amd:timeline:end -->"""


def render_template(
    title: str,
    kind: str,
    timeseries_path: str,
    derived_from: str | None = None,
    source_material: dict[str, str] | None = None,
) -> str:
    if kind == "task":
        return _task_template(title, timeseries_path)
    if kind == "report":
        return _report_template(title, timeseries_path)
    if kind == "mental-model":
        return _mental_model_template(title, timeseries_path)
    if kind == "skill-derived":
        return _skill_template(title, timeseries_path, derived_from, source_material or {})
    raise ValueError(f"Unsupported artifact kind: {kind}")


def _task_template(title: str, timeseries_path: str) -> str:
    return dedent(
        """\
        # {title}

        ## Purpose
        Describe the job this artifact is tracking.

        ## Current Context
        Capture facts the agents can trust right now.

        ## Mental Model
        Explain the current working model, constraints, and decision boundaries.

        ## Working Notes
        Add evolving findings here. `amd refresh` fingerprints this section and can flag it as stale.

        {timeline_block}

        ## Caveats
        Add known caveats, assumptions, and soft spots.

        ## Artifacts
        Distinguish persistent outputs from temporary scratch material.

        ## Data References
        - Timeseries sidecar: `{timeseries_path}`
        """
    ).format(title=title, timeseries_path=timeseries_path, timeline_block=TIMELINE_BLOCK)


def _report_template(title: str, timeseries_path: str) -> str:
    return dedent(
        """\
        # {title}

        ## Executive Summary
        State the current thesis in a few lines.

        ## Key Findings
        Keep the durable findings here.

        ## Supporting Evidence
        Link evidence, reports, and heavier data stores instead of inlining everything.

        {timeline_block}

        ## Caveats
        Keep uncertainty explicit.

        ## Data References
        - Timeseries sidecar: `{timeseries_path}`
        """
    ).format(title=title, timeseries_path=timeseries_path, timeline_block=TIMELINE_BLOCK)


def _mental_model_template(title: str, timeseries_path: str) -> str:
    return dedent(
        """\
        # {title}

        ## Domain
        Define the system or area this model covers.

        ## Core Concepts
        List the primitives, invariants, and entities that matter.

        ## Decision Rules
        Record heuristics, escalation rules, and default actions.

        ## Failure Modes
        Note common traps, stale assumptions, and diagnostic signals.

        {timeline_block}

        ## Caveats
        Include exceptions and areas where the model breaks down.

        ## Data References
        - Timeseries sidecar: `{timeseries_path}`
        """
    ).format(title=title, timeseries_path=timeseries_path, timeline_block=TIMELINE_BLOCK)


def _skill_template(
    title: str,
    timeseries_path: str,
    derived_from: str | None,
    source_material: dict[str, str],
) -> str:
    source_ref = derived_from or "<source mental model>"
    triggers = source_material.get("Decision Rules") or "Copy or refine the operational triggers from the source model."
    workflow = source_material.get("Core Concepts") or "Translate the source model into actionable workflow steps."
    guardrails = source_material.get("Failure Modes") or "Carry forward the failure modes and guardrails from the source."
    return dedent(
        """\
        # {title}

        ## Source Model
        - Derived from: `{source_ref}`

        ## Triggers
        {triggers}

        ## Workflow
        {workflow}

        ## Guardrails
        {guardrails}

        {timeline_block}

        ## Caveats
        Carry forward caveats from the source mental model and add skill-specific exceptions.

        ## Data References
        - Timeseries sidecar: `{timeseries_path}`
        """
    ).format(
        title=title,
        source_ref=Path(source_ref),
        triggers=triggers.strip() or "Add trigger rules here.",
        workflow=workflow.strip() or "Add workflow steps here.",
        guardrails=guardrails.strip() or "Add guardrails here.",
        timeline_block=TIMELINE_BLOCK,
        timeseries_path=timeseries_path,
    )
