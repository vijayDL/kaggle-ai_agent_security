> **ARCHIVED 2026-08-09.** Superseded by `STATE.md` after a git reset invalidated the local work
> this doc was tracking (its P1M/multipost/portfolio claims are unvalidated, not disproven — see
> `STATE.md`). Kept for the independent-guardrail-hypothesis reasoning (§2), which still holds.

# Revised Plan v2 — AI Agent Security: Multi-Step Tool Attacks

**Living tracking doc. Last updated: 2026-08-03.** Rewritten after a review that corrected
v1's over-reach (H2-as-provenance, P3-as-robust, "grader-exact", mutable artifacts). Supersedes
`WINNING-PLAN.md` strategy sections. Final **2026-09-01**; team-merger **2026-08-25**; prize = **private** board.

**Epistemic tags used throughout:** `[FACT]` = verified in code / confirmed on Kaggle;
`[MEAS]` = our local measurement (model-fidelity only, not evaluation-exact); `[HYP]` = hypothesis / inference.

---

## 0. State of play (honest)

- `[FACT]` The **public** board collapses to one primitive: clean `http.post` with `SECRET_MARKER`
  in `data` (18 raw/candidate). It's a replay-throughput race; the gpt-oss row is the bottleneck.
- `[FACT]` The **prize is the private board**, scored by a hidden guardrail `persistent_provenance_private`
  (loaded from a wheel; **unprobeable**). Public is a dev signal only.
- `[MEAS]` We have a **model-semantics-exact** local harness (real GGUF specs + SDK agents) but it is
  **not evaluation-exact** (see §6). Our projected public scores (~54, ~80) are **estimates**.
- **Correction from v1:** we do **not** have a faithful proxy for the private guardrail, and neither
  P3 nor P4 is a proven private scorer. The strategy is a **Pareto portfolio across independent
  guardrail hypotheses**, treating every private primitive as an unproven wager.

---

## 1. Epistemics — what is fact vs guess

| Claim | Tag | Basis |
|---|---|---|
| Public = single-primitive `SECRET_MARKER` exfil throughput | `[FACT]` | scorer+guardrail code; our matrix; canqiang writeup; ≥3 independent notes |
| UNTRUSTED / DESTRUCTIVE closed **on `OptimalGuardrail`** | `[FACT]` | window-nesting proof (canqiang §5.2/§5.3), reproducible on CPU |
| Harmony **forge** speeds gpt-oss ~2× on the real GGUF; Gemma unaffected | `[MEAS]` | `run_forge_test` (0.45→0.21 s/cand gpt-oss; Gemma unchanged) |
| Private guardrail **ID** is `persistent_provenance_private` | `[FACT]` | `jed_attack_gateway.py` |
| That guardrail is **value-provenance** / scans `data` / preserves closures | `[HYP]` | inference from the name — **cannot be verified from public code** |
| P3 (CONFUSED_DEPUTY) survives the private guardrail | `[HYP]` | passes our proxies, but proxies are **correlated** (none models an email-intent guard) |
| P4-benign survives value-provenance | `[HYP]` | untested vs **source**-provenance; H2 only taints secret reads, not web reads |
| canqiang public best = **88.560** | `[FACT]` | their notebook output (linked §7) |
| canqiang's detailed reasoning (wrap-up cost, ratios) | `[MEAS]`/`[HYP]` | their claims — credible, not independently reproduced by us |

---

## 2. Guardrail hypotheses — honest taxonomy + what to build

**What we actually have (none faithfully models `persistent_provenance`):**

| proxy | what it REALLY does | limitation |
|---|---|---|
| `OptimalGuardrail` (public) | source-taint, 5-event window, url-only scan | the real public guardrail — `[FACT]` |
| `guardrail_rules` (H1) | source-taint + **"post" keyword gap** + secret-file confirm | the gap is a *specific weakness*; likely absent in the real guard |
| `H2_read_taint` | **one boolean:** taint after `secret.txt` read → block all later egress | not value-prov, not source-prov, no encodings, no intent |
| `H3_data_scan` | `guardrail_rules` + credential-regex DLP on `http.post.data` | inherits H1's keyword gap; DLP is a guess |

**Independent hypotheses to BUILD** (each models a *distinct* real defense so scores aren't correlated):
- [ ] **G_source_prov** — persistent *untrusted-source* provenance: any `web`/`email` `ok=True` source
      taints the session; every later egress/EXEC/WRITE denied, **no expiry, no keyword gap.** Tests P4/P6 honestly.
- [ ] **G_value_prov** — value-level provenance: track the secret value read from `secret.txt` (and its
      reversible encodings); block only egress *containing* it; allow benign egress. Tests P2/P6 exfil + encodings.
- [ ] **G_email_intent** — deny `email.send` unless the last user message carries explicit share authorization.
      Tests whether P3 is actually robust or just passes correlated proxies.
- [ ] **G_lenient** — near-allow-all (the "private guardrail is weak" branch). Tests the P1-sentinel upside.

Score every primitive/variant across **{Optimal, G_source_prov, G_value_prov, G_email_intent, G_lenient}**.

---

## 3. Strategy — MEASURED (independent-hypothesis matrix, real Gemma, 2026-08-03)

`[MEAS]` Predicate-hit | raw/cand across the independent hypotheses (§2):

| primitive | Optimal | G_source_prov | G_value_prov | G_email_intent | G_lenient |
|---|---|---|---|---|---|
| **P1 marker** | 1.0\|18 | **1.0\|18** | **1.0\|18** | **1.0\|18** | 1.0\|18 |
| P2 hyphen | 1.0\|18 | 1.0\|34 | 1.0\|18 | 1.0\|34 | 1.0\|34 |
| P3 deputy | 1.0\|6 | 1.0\|6 | 1.0\|6 | **0\|0** | 1.0\|6 |
| P4 / P4B / P5 | 0 | **0\|0** | 1.0\|18–24 | 1.0 | 1.0 |
| P6 inject | 0 | **0\|0** | 0.2\|4 | 0.9\|27 | 0.9\|27 |

**What the data says (each review concern resolved):**
- **P4/P4B/P5 die to source-provenance** (they route web→action, no keyword gap) → *not* safe private bets (finding 3 ✓).
- **P3 dies to email-intent** (gated on the predicate's own {send,email,upload}) → *not* robust (finding 2 ✓).
- **P2/P6 exfil die to value-provenance** (real secret tracked through encodings).
- **P1 (sentinel) is the ONLY primitive that survives all five hypotheses** — and on **raw-per-replay-second**
  it dominates (cheap 1-hop+forge ~0.2 s vs multi-hop ~2 s). *The one thing that kills it: a guardrail that
  scans `http.post.data`* (unknown — the #1 open question). Our `G_value_prov` models *pure* provenance,
  under which the sentinel passes.

**Therefore the honest strategy is P1-heavy, hedged:**
1. **Public + private core:** **P1-heavy** (it is the dominant EV primitive on *both* boards under every
   guardrail shape except a data-scanner). This overturns v1's "P3-led" *and* the portfolio-heavy lean.
2. **Data-scan hedge tail:** a *small* slice of the primitives that carry **no secret/sentinel in the payload**
   — **P4B** (survives value/intent branches) + **P3** (survives source/value branches). These salvage the
   "data is scanned → P1 dies, one other mechanism active" cases.
3. **Accept the doomsday branch:** a fully-combined strict guardrail (source + value + data-scan + intent)
   zeros *every* primitive → an unwinnable 0-race for everyone, decided by noise. Nothing to do there.

Net: **v2_hybrid70 / v3_pure_p1 are strong PRIZE bets** (not just public); **v6_combined is the hedge tail**;
v4/v5 (P4B/injection-heavy) are dominated except in the narrow data-scan-only branch.

---

## 4. Metrics — replace "fired" with economics (review finding 6)

For every primitive/variant, on each model × hypothesis, report:
- [ ] **predicate hit rate** (candidates that fire a *scoring predicate*, not any tool event),
- [ ] **raw score / candidate** and **unique scoring cells**,
- [ ] **generation seconds/candidate** and **estimated replay seconds/candidate**,
- [ ] **raw score per replay-second** ← the real currency (replay is the binding budget).
- [ ] Use **larger, equal N** (≥20/cell) given ~8–20% replay-noise CV; prefer **end-to-end variant runs**
      over fixed-N primitive totals for portfolio decisions.

---

## 5. Submission artifact tracking (review finding 5) — artifacts are NOT currently immutable

`build_notebook.py` overwrites `versions/<label>.ipynb`, so current notebooks ≠ the exact artifacts that
earned recorded scores; and v1's table conflated "sizing-fix" vs "pre-fill-fix" v3.
- [ ] For **every** submission, record: **sha256 of the .ipynb**, Kaggle **version id**, git/code **revision**,
      the exact **`_PLAN` + config**, and the **date**. Never trust a label alone.
- [ ] Stop overwriting: write immutable `versions/<label>__<sha8>.ipynb` (or archive on each build).
- [ ] Re-map the recorded public scores (4.890 / 19.060 / 37.280 / 3.585) to their exact code states, or
      mark them **unattributable** if the state is lost.

---

## 6. Harness scope — "model-exact", NOT "evaluation-exact" (review finding 4)

- `[FACT]` Local replay **swallows generation exceptions** (`harness.py`), but Kaggle makes replay
  failures **fatal** (a format-drift / multi-tool-call void zeros the row). We currently **cannot see**
  candidates that would fatally fail replay.
  - [ ] Add a **strict mode** (no swallow) that flags any candidate whose replay raises — those are
        Kaggle-fatal and must be dropped from the returned set.
- `[FACT]` In-process execution does **not** reproduce hosted RPC / GPU / scheduling costs, so local
  timing ratios don't transfer (canqiang §11.4: a ported 2.0× ratio regressed **85.5→53.5** live).
  Keep `_HOP_COST_COEF` **conservative**; treat all projected scores as **estimates until Kaggle confirms.**

---

## 7. Attack-generation research process (review finding 7) — the real missing piece

We've been hand-weighting P1–P6. Add an actual search (the SDK ships Go-Explore baselines to build on):
- [ ] **Structured prompt mutation** over a seed pool (templates × wording × url/recipient/page-id spaces),
      kept only if they fire a scoring predicate under ≥1 hypothesis.
- [ ] **Trace-derived partial rewards** (reward getting closer to a fire: reached the sink tool, secret
      read, untrusted source present) to guide search, not just terminal fire/no-fire.
- [ ] **Behavioral novelty archive** (bucket by tool-sequence / predicate / guardrail-shape) so search
      explores under-represented failure shapes, not more of the same primitive.
- [ ] **Budget allocation by raw-per-replay-second** across primitives, recomputed from live data.
- [ ] Feed winners back into new `attack.py` primitives; this is how we find un-imagined private routes.

---

## 8. Submission status (attribution uncertain — see §5)

| version | recorded public | code state | notes |
|---|---|---|---|
| v1_portfolio12 | 4.890 | pre-all-fixes (lost) | baseline |
| v2_hybrid70 | 19.060 | pre-fill-fixes (lost) | — |
| v3_pure_p1 | 37.280 | **pre-sizing-fix** | the 37.28 predates every fill fix |
| v4_private_max | 3.585 | pre-fill-fixes (lost) | expensive primitives → low public |
| v5_injection | pending | current (P6-heavy) | private wager (exfil-dependent → fragile) |
| v6_combined | pending | current (hedge) | private wager |

---

## 9. Action items (reprioritized after review)

### Correctness / epistemics first
- [ ] Build the **independent guardrail hypotheses** (§2) — the single highest-value fix; unblocks honest private ranking.
- [ ] Add harness **strict-replay mode** (§6) — detect Kaggle-fatal candidates.
- [ ] Fix **artifact immutability + submission ledger** (§5).
- [ ] Upgrade the **matrix metrics** (§4) at N≥20.

### Public (cheap, known)
- [~] Harmony **forge** on P1/P3 — templates edited; finish verify + rebuild. `[MEAS]`-validated, safe.
- [x] 1-hop probing + mix-aware sizing (conservative coef — keep it).

### Private (the prize)
- [ ] Re-score all variants across the **independent hypotheses**, ranked by raw-per-replay-second → pick a **Pareto** portfolio.
- [ ] Stand up the **generation search** (§7) to find primitives beyond P1–P6.
- [ ] Treat P3 **and** P4 as unproven; do not build a "P3-led" variant until §2 hypotheses justify it.

### Ongoing
- [ ] Read v3 (sizing-fix) public → calibrate the sizing model.
- [ ] Bank diverse private wagers across days; keep the ledger current.

---

## 10. Open questions (highest-value unknowns)

1. `[HYP→?]` Does `persistent_provenance` scan `http.post.data`? If yes, the P1 sentinel → ~0 private.
   **Cannot be probed** — only the final private board reveals it. (canqiang's #1 open question too.)
2. `[HYP→?]` Is it **source**-provenance, **value**-provenance, or both? Determines whether P4 (source) or
   P2/P6 (value) survive. Build G_source_prov + G_value_prov to bound both branches.
3. `[HYP→?]` Does a guardrail deny benign `email.send` without intent? Determines if P3 is real. Build G_email_intent.
4. `[FACT-gap]` Fixture stability for P6 (page ids must exist in the private replay fixture; org said *values* may differ).

---

## 11. Bottom line (measured)

The independent-hypothesis matrix (§3) settles it: **P1 (the sentinel) is the only primitive that
survives all our independent private hypotheses, and it dominates on raw-per-replay-second.** So the
prize bet and the public bet are the *same* — **go P1-heavy** — with a *small* payload-clean tail
(P4B + P3) to hedge the one branch that kills P1 (a `http.post.data` scanner), and acceptance that a
fully-combined strict guardrail is unwinnable for everyone.

This is more defensible *and simpler* than v1's "P3-led / portfolio-heavy" lean: `v2_hybrid70` and
`v3_pure_p1` are strong prize candidates; `v6_combined` is the hedge; the injection/UNTRUSTED-heavy
variants (v4/v5) only win in the narrow data-scan-only branch. Remaining open question that would
flip everything: **does the private guardrail scan `http.post.data`?** — unprobeable; only the final
private board reveals it.
