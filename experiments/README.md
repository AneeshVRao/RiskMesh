# Frozen experiment records

Rejected-alternative provenance for RISK-003. `out/` is gitignored, so these are
the durable copies — the E1 and E3 records are kept permanently even though both
were rejected, because they are the evidence for why the adopted design (E2)
looks the way it does.

Each record was written *before* the held-out split was read; `held_out_view()`
in `riskmesh/experiment.py` refuses to hand over test components until the file
exists on disk.

| file | change | ring-family | pos-below-max-neg | held-out F1 | outcome |
|---|---|---|---|---|---|
| `experiment_e1.json` | household co-burst removed | +0.2422 | 0.2500 | 0.800 | rejected — destroys the hard negative |
| `experiment_e2.json` | household co-burst at independent merchants | +0.1953 | 0.5625 | 0.800 | **adopted** |
| `experiment_e3.json` | overlapping household merchant pools | +0.2188 | 0.2500 | 0.7619 | rejected — fails criterion 4 |
| `experiment_e4.json` | ring instrument overlap scales with ring size (RISK-004) | -0.0391 | 0.6875 | 0.800 | rejected — fails criteria 1 and 2 |
| `experiment_e5.json` | component-relative instrument concentration (RISK-004 option 1) | -0.2263 | 0.5625 | 0.800 | rejected — worse than the definition it replaces |
| `experiment_e6.json` | ring funding pool + accounts-per-card feature (RISK-004 option 2) | +0.1576 | 0.0625 | 0.8889 | rejected — over-separates, panel FAILS |

The `ring-family` column is the delta on the signal each experiment targets:
`temporal_burst` for E1-E3, `instrument_sharing` for E4.

`ablation_temporal_burst.json` is not an experiment -- it is the Tier 1
ablation gate, a single measurement with no acceptance band. It found
`temporal_burst` **redundant**: removing it and renormalising the other six
leaves held-out precision, recall, F1 and FPR unchanged and flags the same 12
components. See `implementation_plan.md`.

`weight_policy.json` and `abstention_policy.json` are frozen *policy* records
rather than experiments: each was written to disk before its single held-out
read, and each carries that read's result in a `held_out` block.

| file | selects | protocol | held-out result |
|---|---|---|---|
| `weight_policy.json` | one weight vector from five pre-declared candidates | `weight_search_protocol.md` | A_baseline retained; F1 0.8000, expected loss 9,392.92 at threshold 0.23 |
| `abstention_policy.json` | the review band `(t_lo, t_hi)` over the frozen A_baseline scorer | `abstention_protocol.md` | `t_lo` 0.23 / `t_hi` 0.33; expected loss 6,000.00 against the binary 9,392.92, **zero escalated false positives** |

The abstention record's `held_out.d3_sensitivity` block reports the same
comparison under a corrected `C_fp`, because the improvement's magnitude
(36.1% vs 18.8%) depends on `deferred_decisions.md` D3 while its direction and
the zero-false-positive finding do not.

Full reasoning in `bugs.md`, RISK-003 and RISK-004.

Regenerate any of them with `python -m riskmesh.experiment {e1,e2,e3,e4}`. Note that
E2 is now the default config, so `run_e2`'s baseline-vs-experiment comparison
reads differently than it did when the record was first frozen; the frozen file
is the record of the original run.
