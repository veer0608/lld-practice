# LLD Practice Platform

A focused prototype of a Low-Level Design practice tool: choose a problem,
write a design, submit it, get feedback you can check, and try again with the
previous score still on the screen.

Built for the CipherSchools 2-day engineering assignment.

- [Research note](docs/RESEARCH.md) - the learner problem, what already exists, and where the gaps are
- [Design note](docs/DESIGN.md) - MVP, class model, evaluation approach, trade-offs
- [AI usage](AI_USAGE.md) - five places Claude's first answer and mine diverged

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

87 tests, under 2 seconds, no network and no database. The LLM evaluator is
tested against a fake client rather than the real API, so what's actually
under test is our handling of what a model returns: fenced JSON, prose around
the object, invented evidence, unknown dimension names, an exhausted quota.

## What it does

Three problems ship: Parking Lot, Elevator Controller, Vending Machine. Each
has requirements and an explicit rubric behind it.

You submit in one of three formats. The main one is a structured class
design: name, responsibility, methods, collaborators, one class per line,
plus the trade-off you made. Python code is also accepted and read through
the AST, so a class name in a comment doesn't count as having named it. Free
prose works too, but it's told up front that it gets shallower feedback.

Two evaluators look at what you submit: a deterministic rubric checker and a
model. Their observations get merged and each one is labelled with where it
came from, but the scores themselves aren't blended into a single headline.
The page shows `rubric 90% - llm 75% (varies between runs)`, and the trend
line only ever plots the reproducible half.

There's attempt history and a score trend per problem, because the whole
point of the product is that your second attempt should be better than your
first, and that has to be something you can actually see.

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
tests/           87 tests
docs/            Research and design notes
.claude/skills/  Two repo skills: domain-design, lld-evaluator
```

The dependency rule: `app/domain` imports nothing from the rest of the app. No
FastAPI, no sqlite3, no HTTP client. `storage/sqlite_store.py` is the only file
that knows SQL.

## Key decisions

The split that everything else follows from: whether a concept is named at
all is a fact, and facts get a checker that costs nothing and gives the same
answer tomorrow. Whether an abstraction actually earns its place is a
judgement call, so that's the model's job.

Because of that split, the rubric is required and the model is optional. If a
required evaluator fails, the attempt fails. If the optional one fails, the
result just gets marked degraded with a reason attached. A learner should
never be staring at a spinner that's never going to resolve.

Model output gets checked, not trusted outright. `_evidence_supported` drops
any observation whose quoted evidence doesn't overlap enough with words the
learner actually wrote, and tells the learner how many got dropped. It's
reliable at catching the common failure, critique of a class that was never
named, but it's honestly a word-overlap check rather than a real quote match,
so a sentence assembled from the learner's own vocabulary can slip through,
and anything under three significant words is waved through unchecked because
it carries no signal either way. Substring matching against the rendered
submission would fix both and is the next thing I'd change.

And evaluation runs off the request thread. `EVALUATING` is a state that gets
persisted, not just however long the HTTP request happens to take, so the
page is safe to close and come back to. A failed evaluation keeps the
submission around and a retry costs nothing.

## Limitations

- Single learner. The id is hardcoded at the web layer, though every service
  call already takes `learner_id`, so a real session only needs adding there.
- Keyword matching under-rewards an unusual design. It's half the score, and
  which half is labelled on every item, but it's still a real gap, and the
  next one down is worse: a design that names every rubric keyword as a
  class, with nonsense written for each responsibility, scores 100% on the
  deterministic half. Keyword presence tells you coverage, never quality.
- Prose submissions get around the `TYPE_NAME` scope, since free text can't
  tell a type from a verb, so `declared_types()` falls back to matching every
  word. A paragraph that happens to mention the right nouns scores higher
  than it should. Design and code submissions don't have this problem.
- The god-class check needs the methods column filled in. Leave it blank and
  the check has nothing to measure, so it stays quiet.
- The model's half of the score still drifts a few points between runs on an
  identical submission. That no longer reaches the number that matters (the
  headline and trend line both use the reproducible score only, with the
  model's score shown next to it labelled `varies between runs`), but the
  model's feedback *text* can still change, so rereading the same design
  twice can surface different points.
- It's a thread pool, not a queue, so evaluation doesn't survive a restart on
  its own. `resume_pending` picks up stranded attempts at startup instead.
- Code submissions only really work for Python. Other languages fall back to
  plain word matching instead of reading actual AST symbols.
- No UI for authoring problems, they're just data in `app/content/problems.py`.
- I wrote the rubric myself and haven't checked it against how an experienced
  reviewer would actually grade these designs. That's the first thing I'd
  want to measure next.
