"""RiskMesh — coordinated-abuse-ring detection benchmark (Tier 0).

Tier 0 is the data + evaluation foundation: a synthetic transaction generator,
one shared-device ring injector, one family hard-negative injector, a
relationship graph, a deterministic scorer, a chronological ring-level split, and
an evaluation runner. See implementation_plan.md for scope and PRD.md for intent.

Run the whole benchmark with:  python -m riskmesh
"""

__version__ = "0.1.0"
