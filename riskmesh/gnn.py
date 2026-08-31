"""Hand-rolled GraphSAGE-style scorer over each component's own graph, gated
identically to `riskmesh.ml`'s XGBoost scorer.

The protocol is described in `graphsage_protocol.md`, written and committed
before this module ran against real data, exactly as `xgboost_protocol.md`
preceded `riskmesh/ml.py`. This module mirrors `riskmesh/ml.py`'s shape
closely -- same author, same discipline, a third model family.

Why the gate matters at least as much here as it did for XGBoost: a 2-layer,
hidden-dim-32 message-passing network has comparable or greater capacity than
a 300-tree unregularised gradient-boosted ensemble to find a way to make the
*benchmark* look easier rather than to genuinely discriminate rings from
families -- and, per `task_today.md`, a GNN typically needs MORE data to
train stably than a tree ensemble does, not less, on a ~30-row train split.
`bugs.md` L2 already showed this failure mode on a linear scorer twice; a
network that learns its own feature combinations is a strictly easier way to
find it than either a hand-set weight vector or a tree ensemble.

So this module reuses `costmodel.panel_verdict()` and its two difficulty
bounds UNCHANGED -- no new, more permissive bar for GraphSAGE's candidates.
`costmodel.gated_expected_loss()` still raises `PanelGateFailure` or
`DifficultyGateFailure` instead of returning a number; an infeasible
candidate here gets no F1, exactly as an infeasible weight vector or XGBoost
configuration gets none.

Two further guarantees, both structural rather than remembered:

* `select_gnn_model()` takes design candidates and asserts it received
  nothing else, exactly as `select_weights()` / `select_xgboost_model()` do.
  Fitting for selection uses TRAIN rows only; the threshold sweep inside it
  uses VALIDATION rows only.
* `evaluate_frozen_gnn_policy()` refuses to touch the test split until the
  winning configuration has been written to disk, raising
  `GNNPolicyNotFrozen` -- including when the frozen record names no winner,
  the same `winner is None` refusal `riskmesh.ml.MLPolicyNotFrozen` already
  enforces.

Reproducibility note (see `requirements.txt` and `graphsage_protocol.md` §2.3):
neural-network training has run-to-run variance beyond what a fixed seed
alone controls in general. `torch.manual_seed(cfg.seed)` plus
`torch.use_deterministic_algorithms(True)` control for it as far as CPU-only,
single-process execution allows -- the same way `config.py` scopes Python's
own `random` module to "one interpreter version". `torch.__version__` is
recorded in every frozen record this module produces, the same way
`xgboost.__version__` already is for `riskmesh/ml.py`.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from .config import Config
from .costmodel import (
    DESIGN_SPLITS,
    MIN_HARD_NEGATIVES_IN_RANGE,
    MIN_POSITIVES_BELOW_MAX_NEGATIVE,
    PanelGateFailure,
    gated_expected_loss,
    panel_verdict,
)
from .evaluate import Candidate
from .graph import LINKING_ATTRS, Component, Graph

DESIGN_SPLIT = "validation"
FIT_SPLIT = "train"

# One-hot node-type order, plus one degree feature -- see graphsage_protocol.md
# §2.1. Deliberately NOT the linear scorer's 8 signals: this phase's question
# is whether structure alone, learned by message passing, adds anything a flat
# feature vector cannot -- reusing Candidate.signals would just re-answer
# Tier 2's question with a different optimiser.
NODE_TYPES = ("account", "device", "ip", "instrument")
N_FEATURES = len(NODE_TYPES) + 1


class GNNPolicyNotFrozen(AssertionError):
    """Raised when the held-out split is read before a GNN policy is on disk."""


# --------------------------------------------------------------------------
# per-component graph -- built from riskmesh.graph.Component, the same
# structure __main__._write_graph_edges() already turns into
# out/graph_edges.json. Not a new graph construction path.
# --------------------------------------------------------------------------


@dataclass
class ComponentGraph:
    x: Tensor  # (n_nodes, N_FEATURES)
    neighbors: list[list[int]]  # adjacency: node index -> neighbour indices
    account_mask: Tensor  # (n_nodes,) bool -- which rows are account nodes


def _clip(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _account_degree_cap(cfg: Config) -> int:
    """No per-account degree cap is declared in config.py -- accounts are not
    capped, only individual attribute values are (graph.py rule 2). The
    largest of the three existing attribute caps is reused for the account
    node's degree normalisation, keeping it a global constant from config.py
    (score.py's own rule: never normalise by component size) without
    inventing a fourth config knob for one node-feature formula. Declared in
    graphsage_protocol.md §2.1 before any candidate was scored.
    """
    return max(cfg.max_device_degree, cfg.max_ip_degree, cfg.max_instrument_degree)


def build_component_graph(cfg: Config, comp: Component) -> ComponentGraph:
    """One component's node/edge structure.

    Mirrors `__main__._write_graph_edges()` exactly: group the component's
    transactions by attribute value, keep a node only when `>= 2` accounts
    touch it -- restricted to `graph.LINKING_ATTRS` (device/ip/instrument)
    rather than `__main__.GRAPH_LINKS`, so merchants never become nodes, per
    `graph.py` rule 1.
    """
    account_ids = sorted(comp.accounts)
    index = {a: i for i, a in enumerate(account_ids)}
    kinds: list[str] = ["account"] * len(account_ids)
    degrees: list[float] = [0.0] * len(account_ids)
    edges: list[tuple[int, int]] = []
    account_degree: dict[str, int] = defaultdict(int)

    for attr, cap_name in LINKING_ATTRS.items():
        kind = attr.removesuffix("_id")
        cap = getattr(cfg, cap_name)
        per_value: dict[str, set[str]] = defaultdict(set)
        for t in comp.txns:
            per_value[getattr(t, attr)].add(t.account_id)
        for value, accounts in sorted(per_value.items()):
            k = len(accounts)
            if k < 2:
                continue
            node_idx = len(kinds)
            kinds.append(kind)
            degrees.append(_clip((k - 1) / max(1, cap - 1)))
            for account in sorted(accounts):
                edges.append((index[account], node_idx))
                account_degree[account] += 1

    acct_cap = _account_degree_cap(cfg)
    for account, i in index.items():
        degrees[i] = _clip((account_degree[account] - 1) / max(1, acct_cap - 1))

    n = len(kinds)
    x = torch.zeros((n, N_FEATURES))
    for i, kind in enumerate(kinds):
        x[i, NODE_TYPES.index(kind)] = 1.0
        x[i, len(NODE_TYPES)] = degrees[i]

    neighbors: list[list[int]] = [[] for _ in range(n)]
    for a, b in edges:
        neighbors[a].append(b)
        neighbors[b].append(a)

    account_mask = torch.zeros(n, dtype=torch.bool)
    account_mask[: len(account_ids)] = True

    return ComponentGraph(x=x, neighbors=neighbors, account_mask=account_mask)


def build_component_graphs(cfg: Config, graph: Graph) -> dict[str, ComponentGraph]:
    """Every component's graph, built once -- independent of which candidate
    is being fit, since the representation (§2.1) is shared across all three.
    """
    return {c.component_id: build_component_graph(cfg, c) for c in graph.components}


# --------------------------------------------------------------------------
# model -- hand-rolled GraphSAGE, plain torch tensor operations only.
# No torch_geometric, no dgl: graph.py's own stated preference ("Union-find
# is ~15 lines; networkx would be a dependency for the same result") applies
# here too -- these components have at most a handful of nodes.
# --------------------------------------------------------------------------


class GraphSAGE(nn.Module):
    """Sample-and-aggregate becomes mean-over-all-neighbours (these
    components have at most a handful of nodes per value, so "sample a fixed
    number" and "use all of them" coincide), concatenated with the node's own
    features from the previous layer, one linear layer, ReLU, repeated for
    `num_layers`. Final embeddings are mean-pooled over ACCOUNT nodes only
    (device/IP/instrument nodes contribute through message passing, not
    directly to the pooled vector), then one linear layer to a single logit.
    """

    def __init__(self, in_dim: int, hidden_dim: int, num_layers: int) -> None:
        super().__init__()
        self.layers = nn.ModuleList()
        dim = in_dim
        for _ in range(num_layers):
            self.layers.append(nn.Linear(2 * dim, hidden_dim))
            dim = hidden_dim
        self.classifier = nn.Linear(dim, 1)

    def _embed(self, x: Tensor, neighbors: list[list[int]]) -> Tensor:
        h = x
        for layer in self.layers:
            agg = torch.stack([
                h[idxs].mean(dim=0) if idxs else torch.zeros(h.shape[1])
                for idxs in neighbors
            ])
            h = F.relu(layer(torch.cat([h, agg], dim=1)))
        return h

    def forward(self, cg: ComponentGraph) -> Tensor:
        """One component's logit (0-d tensor)."""
        h = self._embed(cg.x, cg.neighbors)
        pooled = h[cg.account_mask].mean(dim=0)
        return self.classifier(pooled).squeeze(-1)


# --------------------------------------------------------------------------
# candidates -- a fixed list, declared in advance, with no search space
# --------------------------------------------------------------------------

CANDIDATES: dict[str, dict[str, Any]] = {
    "G1_single_layer": dict(
        num_layers=1, hidden_dim=4, weight_decay=1e-2, epochs=50, lr=0.05,
    ),
    "G2_two_layer": dict(
        num_layers=2, hidden_dim=8, weight_decay=1e-3, epochs=100, lr=0.02,
    ),
    "G3_unregularised": dict(
        num_layers=2, hidden_dim=32, weight_decay=0.0, epochs=300, lr=0.05,
    ),
}


def fit_model(cfg: Config, hyperparams: dict[str, Any], fit_on: list[Candidate],
              graphs: dict[str, ComponentGraph]) -> GraphSAGE:
    """Fit one hyperparameter configuration on exactly the given rows.

    A thin wrapper so both the selection fit (train only) and the final
    refit (train+validation) go through one code path -- see §4 of
    `graphsage_protocol.md` for why they must never be the same call.
    Freshly initialised from `cfg.seed` every call, per §2.3/§4.
    """
    torch.manual_seed(cfg.seed)
    torch.use_deterministic_algorithms(True)
    model = GraphSAGE(N_FEATURES, hyperparams["hidden_dim"], hyperparams["num_layers"])
    opt = torch.optim.Adam(
        model.parameters(), lr=hyperparams["lr"], weight_decay=hyperparams["weight_decay"],
    )
    cgs = [graphs[c.component_id] for c in fit_on]
    targets = torch.tensor([float(c.is_positive) for c in fit_on])

    model.train()
    for _ in range(hyperparams["epochs"]):
        opt.zero_grad()
        logits = torch.stack([model(cg) for cg in cgs])
        loss = F.binary_cross_entropy_with_logits(logits, targets)
        loss.backward()
        opt.step()
    model.eval()
    return model


def _score_with(model: GraphSAGE, cands: list[Candidate],
                graphs: dict[str, ComponentGraph]) -> list[Candidate]:
    """Replace `.score` with the model's predicted probability of positive."""
    with torch.no_grad():
        preds = [float(torch.sigmoid(model(graphs[c.component_id]))) for c in cands]
    return [replace(c, score=p) for c, p in zip(cands, preds)]


# --------------------------------------------------------------------------
# protocol
# --------------------------------------------------------------------------


def select_gnn_model(cfg: Config, design: list[Candidate], graph: Graph,
                     costs: dict[str, Any]) -> dict[str, Any]:
    """Score every candidate configuration behind all three gates.

    Takes design candidates as its whole input and asserts it received
    nothing else, in the same shape as `select_xgboost_model()`. Each
    candidate is FIT on train rows only (never validation, never test) and
    then scored OUT-OF-SAMPLE on validation rows only for both the
    feasibility gates and the threshold sweep. In-sample train predictions
    are never mixed into either. No path through this function reaches the
    test split, and no fit inside it ever sees a validation or test label.

    `graph` supplies the per-component structure (§2.1) that the linear
    scorer's `Candidate.signals` deliberately does not carry -- it is the
    same `Graph` `build_graph()` already produces, not label-bearing.

    Feasibility is checked before expected loss, not alongside it: an
    infeasible candidate never receives a number to be compared against.
    """
    assert all(c.split in DESIGN_SPLITS for c in design), (
        "select_gnn_model received non-design candidates -- "
        "this would be model fitting on held-out data"
    )
    train = [c for c in design if c.split == FIT_SPLIT]
    assert train, "no train-split candidates to fit on"

    graphs = build_component_graphs(cfg, graph)

    results: list[dict[str, Any]] = []
    for name, hyperparams in CANDIDATES.items():
        model = fit_model(cfg, hyperparams, train, graphs)
        validation = _score_with(
            model, [c for c in design if c.split == DESIGN_SPLIT], graphs
        )
        v = panel_verdict(cfg, validation)
        n_unique_preds = len({round(c.score, 6) for c in validation})
        row: dict[str, Any] = {
            "policy": name,
            "hyperparameters": dict(hyperparams),
            "panel_verdict": v["verdict"],
            "panel_failing_checks": v["failing_checks"],
            "positives_below_max_negative": v["positives_below_max_negative"],
            "hard_negatives_inside_positive_range":
                v["hard_negatives_inside_positive_range"],
            # Same diagnostic riskmesh.ml records: a degenerate constant
            # predictor and genuine over-separation both drive
            # positives_below_max_negative to the same low number for
            # opposite reasons. This field makes the distinction visible.
            "n_unique_validation_predictions": n_unique_preds,
        }
        best: dict[str, Any] | None = None
        try:
            for i in range(101):
                t = i / 100.0
                loss = gated_expected_loss(cfg, validation, t, costs)
                if best is None or loss["expected_loss"] < best["expected_loss"]:
                    best = {**loss, "threshold": t}
        except PanelGateFailure as exc:
            row["feasible"] = False
            row["refused_by"] = type(exc).__name__
            row["reason"] = str(exc)
        else:
            assert best is not None
            row["feasible"] = True
            row.update(best)
        results.append(row)

    feasible = [r for r in results if r["feasible"]]
    # Ties break toward the earlier-declared (and by construction more
    # conservative) candidate -- G1 before G2 before G3 -- never toward the
    # more complex configuration.
    order = {name: i for i, name in enumerate(CANDIDATES)}
    winner = min(
        feasible, key=lambda r: (r["expected_loss"], order[r["policy"]]),
    ) if feasible else None

    return {
        "protocol": "graphsage_protocol.md",
        "torch_version": torch.__version__,
        "gates": {
            "panel_verdict": "PASS",
            "hard_negatives_inside_positive_range":
                f">= {MIN_HARD_NEGATIVES_IN_RANGE}",
            "positives_below_max_negative":
                f">= {MIN_POSITIVES_BELOW_MAX_NEGATIVE}",
            "declared": (
                "Reused UNCHANGED from costmodel.py / weight_search_protocol.md "
                "/ xgboost_protocol.md. Not redeclared for GraphSAGE -- the "
                "whole point of this phase is that GraphSAGE's candidates are "
                "held to the identical bar the weight vectors and XGBoost's "
                "candidates were."
            ),
            "enforcement": (
                "gated_expected_loss() raises PanelGateFailure or "
                "DifficultyGateFailure instead of returning a number. An "
                "infeasible candidate has no expected loss at all."
            ),
        },
        "node_features": (
            "one-hot node type (account/device/ip/instrument) + degree "
            "within the component graph, normalised by the matching global "
            "cap from config.py -- structural only, deliberately not the "
            "linear scorer's 8 signals. See graphsage_protocol.md §2.1."
        ),
        "costs": costs,
        "fit_on": "train only (selection); gates and threshold sweep both "
                  "computed on validation predictions only, out-of-sample "
                  "for every candidate -- train's in-sample scores are never "
                  "mixed in",
        "candidates": results,
        "feasible": [r["policy"] for r in feasible],
        "infeasible": [r["policy"] for r in results if not r["feasible"]],
        "winner": winner["policy"] if winner else None,
        "winner_hyperparameters": (
            dict(CANDIDATES[winner["policy"]]) if winner else None
        ),
        "winner_threshold": winner["threshold"] if winner else None,
        "winner_expected_loss": winner["expected_loss"] if winner else None,
        "seed": cfg.seed,
        "config_fingerprint": cfg.fingerprint(),
        "python_version": sys.version.split()[0],
    }


def refit_final_model(cfg: Config, design: list[Candidate], graph: Graph,
                      hyperparameters: dict[str, Any]) -> GraphSAGE:
    """Refit the selected hyperparameters on ALL design data (train+validation).

    Standard practice once a configuration is chosen: the selection fit
    (train only) never saw validation, so the model that scores the held-out
    test split should use every design row available. Does not leak -- design
    is disjoint from test throughout, before and after this refit. Fresh
    initialisation from `cfg.seed`, same as every fit in this module.
    """
    assert all(c.split in DESIGN_SPLITS for c in design), (
        "refit_final_model received non-design candidates"
    )
    graphs = build_component_graphs(cfg, graph)
    return fit_model(cfg, hyperparameters, design, graphs)


def evaluate_frozen_gnn_policy(cfg: Config, design: list[Candidate],
                               test: list[Candidate], graph: Graph,
                               policy_path: Path) -> list[Candidate]:
    """Test rows -- available only once the winning configuration is on disk.

    Refits the frozen hyperparameters on train+validation (§4.4 of
    `graphsage_protocol.md`) and scores the test rows with that refit. The
    refit never touches a test feature or label; it is disjoint design data,
    the same guarantee `costmodel.evaluate_frozen_policy()` relies on.

    Also raises `GNNPolicyNotFrozen` when the frozen record exists but names
    no winner (every candidate was refused). No candidate to refit means
    nothing the protocol permits reading the held-out split with -- see
    `graphsage_protocol.md` §6: "if no candidate is feasible ... that is the
    finding," not a reason to read the test split against an ungated model.
    """
    if not policy_path.exists():
        raise GNNPolicyNotFrozen(
            f"{policy_path.name} has not been frozen. The selected GraphSAGE "
            "configuration, its validation expected loss and its panel "
            "verdict must be recorded before the test split is read, or the "
            "comparison is not held out."
        )
    frozen = json.loads(policy_path.read_text(encoding="utf-8"))
    if frozen.get("winner") is None:
        raise GNNPolicyNotFrozen(
            f"{policy_path.name} records no feasible candidate (every "
            "candidate was refused by the gate) -- there is no winning "
            "configuration to refit, so the held-out split must not be read."
        )
    hyperparameters = frozen["winner_hyperparameters"]
    model = refit_final_model(cfg, design, graph, hyperparameters)
    graphs = build_component_graphs(cfg, graph)
    return _score_with(model, test, graphs)


def freeze_gnn_policy(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
