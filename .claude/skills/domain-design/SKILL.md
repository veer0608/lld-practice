---
name: domain-design
description: How the domain layer in this project is shaped and what a reviewer should check. Use when adding or changing anything under app/domain, when placing a new behaviour, when deciding whether something deserves its own class or interface, and when reviewing a diff for responsibility drift.
---

# Domain design in this project

The platform teaches Low-Level Design. Its own domain layer is therefore
evidence, and a god class in `PracticeService` costs more here than a missing
feature would. This is the standard the code is held to.

## The layering, and the one rule that keeps it

```
web  ->  services  ->  domain  <-  evaluation
                          ^
                       storage
```

Arrows point at what a layer is allowed to import. The single rule:

**`app/domain` imports nothing from the rest of the app.** No FastAPI, no
sqlite3, no httpx, no service. If a domain module needs one of those, the
design is wrong, not the rule.

Consequences worth knowing before you reach for a shortcut:

- `Attempt` cannot serialise itself. That lives in `app/storage/mapping.py`,
  so a schema change touches storage and not the aggregate.
- `Submission` cannot parse a form. That lives in `app/web/forms.py`.
- Evaluators receive `Problem` and `Submission`, never `Attempt`. Evaluation is
  a pure function of what was asked and what was handed in, which is what makes
  it replayable on an old submission.

## Where behaviour goes

Ask, in this order:

1. **Is this a rule about whether something is legal?** It belongs on the
   aggregate. `Attempt` owns its own state machine; nothing outside it may
   assign `status`. If a service is checking `if attempt.status == ...` before
   calling a method, the check belongs inside the method.
2. **Is this a judgement about a submission?** It belongs in an `Evaluator`.
   See the `lld-evaluator` skill.
3. **Is this about how something is stored or displayed?** Storage or web. Not
   the domain.
4. **Is it orchestration, and only orchestration?** `PracticeService`. That
   class is deliberately thin, and it staying thin is a review criterion.

## When something earns its own type

A new class is justified when it removes a branch, not when it adds a noun.

- `Submission` subclasses exist because every evaluator would otherwise carry
  the same `if format == "code"` ladder. Three formats, one dispatch. The
  behaviour that makes this pay is `structural_notes()`: each format reports
  what can be checked about its own shape, so no evaluator switches on a
  concrete submission type. Do not reintroduce that switch.
- `Dimension` is an enum rather than a string because deterministic and model
  feedback have to be mergeable, and that only works if both speak one closed
  vocabulary.
- `Severity` is separate from `Dimension` because "how bad" and "about what"
  vary independently. Collapsing them was considered and would have produced
  twelve enum members that mean two things.

Counter-example, deliberately not built: there is no `Learner` class. A learner
id is a string passed to service methods. Nothing about the current feature set
needs learner behaviour, and a class that only holds an id is a class that has
to be maintained.

## Checklist for a domain change

- Does `app/domain` still import nothing from the app? `grep -rn "^from app\." app/domain` should only show intra-domain imports.
- Is every illegal state transition covered by a test that asserts it raises?
- Does the new code widen `PracticeService`? If a method there grew a second
  responsibility, split it before it lands.
- Is there a new string where an enum belongs? Free strings crossing the
  evaluator boundary are the failure mode that breaks merging.
- Does a dataclass now carry both data and a persistence concern? Move the
  persistence half to `app/storage/mapping.py`.

## What good looks like here

`app/domain/attempt.py` is the reference. One aggregate, one `ALLOWED`
transition table readable in ten seconds, methods that refuse rather than
correct, and a docstring that says why the state machine exists at all rather
than what the code does.
