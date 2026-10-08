# Issue 13 Implementation Review — Public-corpus Analyst Mode

- Status: completed under the current phase scope.
- Files: `gamepulse/modes/analyst.py`, shared router/CLI updates,
  `gamepulse/intelligence.py`, `tests/test_modes_analyst.py`, additional
  intelligence regression tests, regenerated Issue 10 artifacts, and
  `examples/modes/analyst/infinity-nikki/*`.
- Functionality: traceable chain from raw statement to inferred topic and pain
  point, inferred underlying need, expressed-intent behaviour signal, possible
  business-relevance hypothesis, explicit request/inferred opportunity, and
  transparent decision-support priority.
- Epistemic labels: raw text and explicit requests are `observed`; taxonomy,
  pain points, needs, and derived opportunities are `inferred`; behaviour
  signals are `expressed_intent`; business relevance is `hypothesis`.
  `observed_behaviour_data_available=false` is explicit.
- Language guard: `churn_risk` is rendered as `expressed_churn_intent`; the
  output never says a player churned or that a topic causes churn. Priorities
  retain the non-causal decision-support disclaimer.
- Dependency fixes: the underlying-need map now covers stable story, gacha,
  fair-play, difficulty, and account-service pain points. Chinese feature
  request matching was narrowed after live output exposed false positives from
  “抱有希望” and download advice; only actual request constructions remain.
- Tests added: 7 Analyst tests plus 3 annotation-quality regressions. Full
  result after Issue 13: 140/140 passing.
- Real example: Infinity Nikki produces public-only chains for story pain,
  freeze/crash reports, gacha value concern, and one genuine “一键跳过” request.
  Retention/satisfaction relevance remains explicitly a hypothesis requiring
  authorised first-party validation.
- Known limitation: this baseline works evidence-by-evidence and does not yet
  implement segmentation, private joins, causal models, or enterprise BI.
- Deferred: Compare remains disabled until Issue 14. Patch Intelligence and
  Private Data remain Issue 15+ / interface-only.
