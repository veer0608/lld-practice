# Design note

## The MVP

One learner, three problems, and a loop you can actually go around more than
once:

> choose a problem -> write a design -> submit -> get feedback -> review -> try again

Everything in this build is in service of that second lap. A tool that gives
good feedback once is basically a chat window. A tool where attempt 3 is
measurably better than attempt 1 is an actual product.

## User flow

| Step | Screen | What's happening underneath |
|---|---|---|
| 1 | `/` | Problem catalogue plus your recent attempts |
| 2 | `/problems/{id}` | Statement, requirements, the editor, and your score trend on this problem if you have one |
| 3 | POST submit | A `Submission` gets built from the form and validated, an `Attempt` is created and stored, and evaluation is handed off to a background runner. The request returns right away. |
| 4 | `/attempts/{id}` | Shows `Evaluating` and refreshes itself. The submission is already saved by this point, so it's safe to leave the page. |
| 5 | same page | Overall score, per-dimension bars, feedback sorted worst-first, each item labelled with which evaluator produced it and what evidence it's standing on |
| 6 | Try again | Back to step 2, sparkline now has two points on it |

## The classes that carry the design

```mermaid
classDiagram
    class Attempt {
        +id, learner_id, attempt_no
        +status: AttemptStatus
        +submit(Submission)
        +begin_evaluation()
        +complete_evaluation(Evaluation)
        +fail_evaluation(reason)
        +retry_evaluation()
    }
    class Submission {
        <<abstract>>
        +render_for_evaluation() str
        +symbols() set
        +validate()
    }
    class Evaluator {
        <<abstract>>
        +evaluate(Problem, Submission) Evaluation
        +is_available bool
    }
    class Problem {
        +statement, requirements
        +rubric: RubricCriterion[]
    }
    class Evaluation {
        +items: FeedbackItem[]
        +scores: DimensionScore[]
        +degraded, degraded_reason
        +merge(Evaluation) Evaluation
    }

    Submission <|-- DesignSubmission
    Submission <|-- CodeSubmission
    Submission <|-- TextSubmission
    Evaluator <|-- RubricEvaluator
    Evaluator <|-- LLMEvaluator
    Evaluator <|-- EvaluationPipeline
    EvaluationPipeline o-- Evaluator : required + optional
    Attempt --> Submission
    Attempt --> Evaluation
    Evaluator ..> Problem : reads
    PracticeService --> Attempt
    PracticeService --> Evaluator
    PracticeService --> AttemptRepository
```

Four things do most of the actual work here.

`Submission` is the answer to the first question worth asking about a tool
like this: what does someone actually have to hand over for the attempt to
mean anything? The answer here is named classes, a stated responsibility for
each, stated collaborators, and the trade-off they knowingly made. Every
subclass exposes the same three things, and that's all an evaluator ever
touches: `render_for_evaluation()` gives a flat text view for the model,
`symbols()` and `declared_types()` give the words and the type names for the
checker, and `structural_notes()` reports whatever that format alone can
check about its own shape. That last one used to be an `isinstance` ladder
sitting inside `RubricEvaluator` instead, which meant a fourth format could
register correctly and then silently get no structural checks at all. A
design knows what a god class looks like. Code knows whether it parses.
Prose knows it can't really be checked deeply. The evaluator just asks and
doesn't care who answered, and stamps its own name on whatever comes back so
the learner still knows who's making the claim. `CodeSubmission.symbols()`
walks the actual Python AST instead of matching words, so a class name that
only shows up in a comment doesn't count. That's pinned by a test, not just
something I believe about it.

`Evaluator` is the strategy seam. `evaluate(problem, submission)` returns an
`Evaluation` or raises `EvaluationError`, and it never sees the `Attempt`
itself, so evaluation is a pure function of what was asked and what was
handed in. That's what makes it replayable against an old submission later
if the rubric changes.

`Attempt` owns its own lifecycle. Nothing outside it assigns `status`
directly, it has to ask for a transition and the aggregate decides whether
that's allowed. The whole table is five lines and every illegal edge is
covered by a test:

```
DRAFT --submit--> SUBMITTED --start--> EVALUATING --complete--> EVALUATED
                                           |
                                           +--fail--> FAILED --retry--> EVALUATING
```

And `AttemptRepository` keeps SQL out of everything else. `sqlite_store.py`
is the only file in the whole project that knows any SQL exists.

## How evaluation actually splits

The rule the rest of the product hangs off of: deterministic where the
answer is a fact, a model where the answer is a judgement.

| `RubricEvaluator`, no network | `LLMEvaluator` |
|---|---|
| Is the concept named at all, and named as a type where that's the claim | Does the abstraction earn its place |
| Is a responsibility stated per class | Is it the right responsibility |
| Does the code parse | Is behaviour in the right class |
| Does one class hold most of the methods | Is that class coordinating or actually doing the work |
| Is a trade-off stated | Is it a real trade-off |

Coverage and structure are facts. They cost nothing to check, give the same
answer tomorrow, and hold up if a learner disagrees with them. Whether
`SpotAllocator` earns its place is a judgement, and no keyword list is ever
going to have an opinion about that.

Both sides speak the same `Dimension` and `Severity` vocabulary, which is
what lets `Evaluation.merge` average scores per dimension and concatenate
the feedback items. Items never get deduplicated: if both sources flag the
same thing, that agreement is information worth keeping, not noise to
collapse.

### Making feedback useful when there's more than one right answer

The platform never says a design is correct. There's no reference solution
anywhere in the codebase for it to compare against, on purpose, since the
whole premise here is that there usually isn't a single right one. Every
piece of feedback is instead an observation, tied to a dimension, given a
severity, and backed by a quote.

That evidence requirement is checked, not just requested. Every rubric item
cites the learner's own symbol. Every model item has to carry a quote, and
`LLMEvaluator._evidence_supported` drops anything whose quote doesn't
sufficiently overlap the learner's actual vocabulary, showing how many got
dropped. It runs on our side rather than trusting the model to behave, and
it reliably catches the common failure: critique of a class the learner
never named. Worth being honest about its limit though. It's comparing bags
of words, not doing a real substring match, so a fabricated sentence built
out of the learner's own vocabulary can still slip past it, and anything
under three significant words gets waved through unchecked since it doesn't
carry much signal either way. Matching against the actual rendered
submission would close both gaps, and it's the next thing worth changing
here.

Synonyms count, too: `spot`, `slot`, `bay`, and `space` all satisfy the same
criterion, and multi-word keywords need every word present, so `parking`
alone doesn't earn credit for `parking spot`. Penalizing vocabulary instead
of actual modeling is exactly the failure that makes automated LLD review
worthless.

Criteria also declare where they're allowed to match. `RubricCriterion.scope`
is either `ANYWHERE` or `TYPE_NAME`, because two genuinely different
questions were hiding under "is this concept present," and conflating them
used to credit a god class with a `get_change` method for "making change is
its own responsibility," and a design that just said "opens the doors" for
"the car has an explicit state." A criterion that's really a claim about a
type existing now only matches class and collaborator names, sourced from
`Submission.declared_types()` (and from `ast.ClassDef` for code
submissions). This was found by actually running the Elevator and Vending
Machine problems end to end, not by reading the code and reasoning about it.

And sources stay visible throughout. `rubric` and `llm` are labelled
separately in the UI so a learner can weight a mechanical check differently
from an opinion, which they should.

### Scoring, and why there are two numbers on the page

Within a single evaluator, it's an unweighted mean of dimension scores.
Weighting one LLD axis over another is a claim this product hasn't earned
yet, and a hidden weight makes a score impossible to argue with.

Across evaluators, though, the scores don't get blended into one headline
number. `merge` averages per dimension, which is the right view for the bars
but the wrong one for a single figure: the rubric produces a coverage
fraction, the model produces a judgement, and averaging them gives you a
number that's neither. It also weights badly in practice. `trade_offs` has
no rubric criteria backing it at all, so a single model opinion used to
enter the old headline number at a full sixth of the total, carrying all of
its noise with it. That's exactly what made the merged score move between
82% and 87% across four runs of one completely unchanged submission, while
the rubric half returned 90% every single time.

So `Evaluator` now declares whether it's `reproducible`, the pipeline
records each evaluator's own contribution as a `SourceScore` before
merging, and the attempt page shows something like `rubric 90% - llm 75%
(varies between runs)`. The score trend only ever plots
`Evaluation.trend_percent`, which is the reproducible score and nothing
else.

This is really the concrete version of the product's whole claim. Attempt 3
is only comparable to attempt 1 if the number you're comparing means the
same thing both times, and only the deterministic half actually does. The
model half is still worth reading and still gets shown, it's just not
something you'd plot on a trend line.
`test_a_drifting_model_score_cannot_move_the_trend` is the test that pins
this down.

## What happens when evaluation is slow, or just fails

`PracticeService.submit` stores the attempt and hands evaluation off to a
`TaskRunner`, then returns immediately. `EVALUATING` is a state that gets
persisted rather than just being how long an HTTP request happens to take,
so it's fine to close the tab and come back later. The web app runs this on
a small thread pool; the tests use `InlineRunner` instead, so the whole
suite stays deterministic with no sleeps in it and no `if testing` branch
sitting inside the service.

On the failure side, `EvaluationPipeline` splits evaluators into `required`
and `optional`. The rubric is required and needs no network at all. The
model is optional, and if it fails the learner gets the deterministic result
back with `degraded` set and the reason shown, not an error page. If it
fails hard enough, the attempt moves to `FAILED` and offers a retry that
costs nothing since the submission is already saved. `run_evaluation` also
catches a bare `Exception`, so a bug inside an evaluator produces a failed
attempt instead of one stuck forever reading "evaluating." That behavior has
a test too.

A thread pool doesn't survive a process restart on its own, so
`resume_pending` re-schedules anything still sitting in `SUBMITTED` or
`EVALUATING` when the app comes back up. It's the cheap version of a durable
queue, and it's the exact seam a real queue would slot into later.

And on quota: free-tier model access is limited per model per day, and a 429
response covers two genuinely different situations. `GeminiClient` branches
on the actual response body rather than the status code, walks a ladder of
pinned model ids, and never touches a `-latest` alias, since an alias just
repoints to whatever's newest and the newest model usually has the smallest
free allowance.

## Extending this later

Three concrete extensions, with what they'd actually cost to add.

| Extension | What changes |
|---|---|
| A diagram submission format (Mermaid, PlantUML) | One `Submission` subclass, plus one branch in `web/forms.py` since the form has to know which fields to read. No evaluator changes at all, and there's a test that proves it by defining a fourth format and running it straight through `RubricEvaluator`. |
| A different evaluation strategy (static analysis, a peer review queue, a second model) | One `Evaluator` subclass and one line in `config.build_evaluator`. It joins the merge automatically from there. |
| Postgres instead of SQLite | One `AttemptRepository` implementation. Domain, services, and web layers don't depend on sqlite3 existing at all. |

These seams aren't decorative. `LLMEvaluator` got added after
`RubricEvaluator` was already working end to end, and adding it changed
exactly one line of `config.py`.

## What got traded away

| Decision | What it costs |
|---|---|
| Rubric required, model optional | Feedback a learner might find a bit shallow. Still better than feedback that sometimes doesn't arrive at all. |
| Keyword matching for the deterministic half | Under-rewards an unusual but genuinely good design. Bounded, since it's only half the score, and it's labelled as such. |
| Structured `DesignSubmission` as the main format | Some people think better in prose or in code. Both are still accepted, and told up front they get shallower feedback rather than silently marked down. |
| Unweighted dimension mean | A missing `PricingStrategy` counts the same as a missing `Payment`. Arguable, but at least it's honest about it. |
| Thread pool instead of a queue | Evaluation doesn't survive a restart by itself. `resume_pending` covers it well enough at this scale. |
| No auth, one fixed learner id | No real multi-user story yet. Every service call already takes `learner_id` though, so a real session only has to get added at the web layer. |

## What I deliberately didn't build

Auth and accounts, a diagram editor, a UI for authoring problems, spaced
repetition, anything about scale. The brief asks for LLD, not HLD, and every
one of these would have pulled time away from the domain model, which is
the thing actually being judged here.

## If this needed to handle a lot more people

Keeping this short on purpose. The service is stateless apart from SQLite,
so the first two moves would be putting evaluation on a real queue behind
the existing `TaskRunner` interface, and swapping `AttemptRepository` over
to Postgres. Both are single-class changes. Model latency would dominate
everything else at that point, so the third move would be caching
evaluations by `(problem_id, submission hash)`, which the pure-function
shape of `Evaluator` already allows for free.
