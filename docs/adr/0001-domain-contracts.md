# ADR 0001: Pydantic domain contracts

Status: accepted for Issue 1.

PlayerVoice uses Pydantic v2 models in `gamepulse/models.py` for the logical contracts in
`DATA_SCHEMA.md`. Strict extra-field rejection and explicit cross-field validators keep persisted
records from silently widening. The same models generate the checked-in JSON Schemas under
`schemas/`, avoiding a second hand-maintained contract.

The legacy normalized voice table remains unchanged. `gamepulse/compatibility.py` maps its rows
into `EvidenceItem` at the boundary so collectors and reports keep their current behaviour.

Two small contract clarifications implement requirements already stated in `DATA_SCHEMA.md`:

- public evidence cannot carry a private `dataset_id`;
- an `opportunity` insight records whether it came from an explicit request or inferred need.
