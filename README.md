# LLD Practice Platform

A focused prototype of a Low-Level Design practice tool: choose a problem,
write a design, submit it, get feedback you can check, and try again with the
previous score still on the screen.

Built for the CipherSchools 2-day engineering assignment.

- [Research note](docs/RESEARCH.md) - the learner problem, what already exists, and where the gaps are
- [Design note](docs/DESIGN.md) - MVP, class model, evaluation approach, trade-offs
- [AI usage](AI_USAGE.md) - six decisions where AI and judgement diverged

## Run it

Python 3.11 or newer.

```bash
python -m venv .venv && .venv/Scripts/activate && pip install -r requirements.txt
```

On macOS or Linux, `source .venv/bin/activate` instead.

```bash
python -m uvicorn main:app --reload --port 8000
```

Open http://localhost:8000.

### The model is optional

It runs without an API key. With none configured you get deterministic rubric
feedback, and the UI says so on the attempt page rather than failing.

To enable model feedback, copy `.env.example` to `.env` and put a Google Gemini
API key in `GEMINI_API_KEY`. `GET /healthz` reports which evaluators are wired:

```json
{"ok": true, "problems": 3, "evaluators": {"required": ["rubric"], "optional": ["llm"]}}
```

## Tests

```bash
python -m pytest -q
```

69 tests, about 1.3 seconds, no network and no database. The LLM evaluator is
tested against a fake client, so what is under test is our handling of what a
model returns: fenced JSON, prose around the object, invented evidence, unknown
dimension names, an exhausted quota.

## What it does

**Three problems** (Parking Lot, Elevator Controller, Vending Machine), each
with requirements and an explicit rubric.

**Three submission formats.** A structured class design is the primary one:
class name, responsibility, methods, collaborators, one per line, plus the
trade-off you made. Python code is accepted and read through the AST, so a
class named only in a comment does not count. Free prose is accepted and told
it will get shallower feedback.

**Two evaluators, kept apart where it matters.** A deterministic rubric checker
and a model. Observations are merged and each is labelled with its source, but
the scores are not blended into one headline: the page shows
`rubric 90% - llm 75% (varies between runs)`, and the trend plots the
reproducible score alone.

**Attempt history and a score trend per problem**, because the product's claim
is that the second attempt is better than the first.

## A real run

A first design for the Parking Lot omitting pricing and payment scored 73%. The
same design with `PricingStrategy` and `Payment` added scored 92%. Feedback from
the first attempt, abbreviated:

```
gap        · Extensibility        · rubric
  Not found in your design: pricing is a separate collaborator, so a new rule
  does not edit the lot
  evidence: no mention of pricing strategy / fee strategy / rate

suggestion · Relationships        · llm
  The Ticket class currently collaborates with ParkingSpot, but it should likely
  collaborate with a PricingStrategy to calculate the fee upon exit.
  evidence: class Ticket ... collaborates with: ParkingSpot

strength   · Responsibility       · llm
  Separating the allocation logic into a dedicated SpotAllocator class keeps the
  ParkingLot and Floor classes focused on their primary data management roles.
  evidence: class SpotAllocator responsibility: picks which spot a vehicle gets
```

Two further model observations were withheld because their quotes did not
appear in the submission. The summary says so.

### Checking the rubrics separate good from bad

A strong and a deliberately weak design were run through all three problems.
The weak ones are god-class designs with no stated trade-off.

| Problem | Weak | Strong |
|---|---|---|
| Parking Lot | 8% | 92% |
| Elevator Controller | 14% | 92% |
| Vending Machine | 9% | 87% |

The first run of this exercise scored the weak designs 27% and 20%, which was
too generous, and the reason was a real bug: criteria like "money is a domain
type" were matching a `check_money` method on the god class. `RubricCriterion`
now carries a `scope`, so criteria that are claims about a type existing match
only class and collaborator names. Five regression tests pin the specific
false positives.

## Layout

```
app/
  domain/        Problem, Submission, Attempt, Evaluation. Imports nothing else in the app.
  evaluation/    The Evaluator seam: rubric, LLM, and the pipeline that merges them.
  storage/       Repository interfaces, SQLite and in-memory, and the row mapping.
  services/      PracticeService, the practice loop. Orchestrates, does not decide.
  content/       The problem catalogue and its rubrics.
  web/           FastAPI routes, form parsing, Jinja templates.
tests/           69 tests
docs/            Research and design notes
.claude/skills/  Two repo skills: domain-design, lld-evaluator
```

The dependency rule: `app/domain` imports nothing from the rest of the app. No
FastAPI, no sqlite3, no HTTP client. `storage/sqlite_store.py` is the only file
that knows SQL.

## Key decisions

**Deterministic where the answer is a fact, a model where it is a judgement.**
Whether a concept is named is a fact and gets a checker that costs nothing and
returns the same answer tomorrow. Whether an abstraction earns its place is a
judgement and gets a model.

**The rubric is required, the model is optional.** A required evaluator failing
fails the attempt; an optional one failing degrades it with a reason shown. A
learner never watches a spinner that ends in nothing.

**Model observations must be grounded in the submission's own vocabulary.** `_evidence_supported` drops any item whose quoted evidence does not sufficiently overlap the words the learner actually wrote, and reports the withheld count. It reliably catches critique of classes the learner never named, which is the common failure. It is a word-overlap test rather than a substring match, so a fabricated sentence assembled from the learner's own vocabulary can still pass, and a quote of fewer than three significant words is waved through unchecked on the grounds that it carries no signal either way. Substring matching against the rendered submission would close both, and is the next thing to change here.

**Evaluation is off the request thread.** `EVALUATING` is a persisted state, not
the duration of an HTTP request, so the page is safe to leave. A failed
evaluation keeps the submission and offers a retry that costs nothing.

## Limitations

- **Single learner.** The id is fixed at the web layer. Every service call
  already takes `learner_id`, so a real session drops in there and nowhere else.
- **Keyword matching under-rewards unusual designs.** It is half the score, and
  which half is labelled on every item.
- **A thread pool, not a queue.** Evaluation does not survive a restart;
  `resume_pending` re-schedules stranded attempts at startup instead.
- **Python only for code submissions.** Other languages fall back to word
  matching rather than AST symbols.
- **The rubric was written by me**, not validated against how experienced
  reviewers actually grade. That is the first thing worth measuring.
- **No problem authoring UI.** Problems are data in `app/content/problems.py`.
- **The rubric half is gameable.** A design that names every rubric keyword as a
  class scores 100% on the deterministic half with nonsense responsibilities.
  Keyword presence is evidence of coverage, never of quality, and only the model
  half reads what the responsibilities actually say.
- **Prose submissions bypass the `TYPE_NAME` scope.** `TextSubmission` cannot
  tell a type from a verb, so `declared_types()` falls back to every word and a
  paragraph mentioning the right nouns scores far higher than it should. Design
  and code submissions are unaffected.
- **The god-class check needs listed methods.** Omitting the methods column
  silences it, because it measures method distribution and has nothing to count.
- **The model half of the score drifts between runs**, by a few points on an
  unchanged submission. This no longer reaches the trend: the headline and the
  sparkline use the reproducible score alone, and the model score is shown
  beside it labelled `varies between runs`. What remains is that model feedback
  *text* still varies, so two runs of the same design can raise different points.
