# Patterns reference — Python design-pattern advisor

Self-contained essentials for design-pattern advice. Historical content
lives in git history under `.claude/skills/python-pattern-advisor/`.

## Catalog highlights

| Pattern | Pythonic form | When |
|---------|---------------|------|
| Registry | dict at module scope + register decorator | new shape / new model / new migration |
| Borg | shared `__dict__` instance state | rare; explicit shared-state need |
| Flyweight via Metaclass | `__init_subclass__` cache | many-instance, shared identity |
| Pub/Sub | `weakref.WeakSet` of callbacks | event observers |
| `lazy_property` descriptor | `__set_name__` + cache | expensive memoization |
| Specification | composable predicate objects | declarative case-spec selectors |
| Delegation | `__getattr__` fallback | proxy / decorator stacks |
| Catalog | dataclass-like records keyed by str | what `MODEL_REGISTRY` is |

## python-stream contract additions

The codebase already follows several patterns; the advisor's job is to
prevent re-invention. The patterns currently in active use:

- **Registry**: `MODEL_REGISTRY`, `MIGRATIONS`. Add to these, don't
  parallel-implement.
- **Specification**: `CaseSpec` / `CaseFamily` (declarative case
  catalog). New cases are records, not new code paths.
- **Match dispatch**: discriminator-keyed `match`/`case` over if/elif
  chains. Enforced by `enforce-match-dispatch.sh`.

If the advisor surfaces a pattern that conflicts with the above (e.g.
"use a strategy class hierarchy" when the codebase wants a registry),
the codebase convention wins — record the rejection in `DECISIONS.md`.

## Stuck-mode entry

Pattern-introduction stucks are usually rung-2 (reframe — is the
problem the wrong shape for any pattern?) or rung-3 (council — is the
abstraction at the wrong altitude?).
