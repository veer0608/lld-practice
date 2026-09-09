# AI usage

Built with Claude Code as a pair. Six decisions where the AI's suggestion and
my judgement actually diverged, or where trusting it would have shipped a bug.

## 1. LLM-only feedback, rejected in favour of a required deterministic floor

**Suggested.** The obvious build: send the design to a model, show what comes
back. Simplest thing that demonstrates the loop.

**Rejected.** It makes the product's core promise depend on a free-tier quota.
Gemini's free tier is a per-model, per-day request ceiling, so on the day a
reviewer opens the demo the feedback could be an error page. Worse, a model's
score for the same submission drifts between calls, which destroys the one
thing the product claims to offer: attempt 3 being comparable to attempt 1.

**Built instead.** `EvaluationPipeline` with `required` and `optional` lists.
The rubric is required, costs nothing and is reproducible. The model is
optional. When it fails the learner gets rubric feedback flagged `degraded`
with the reason, never an error page. This turned out to be the spine of the
whole design and it is what makes the "what if evaluation fails" answer real
rather than a paragraph.

## 2. A tokeniser bug the AI wrote and I caught by running it

**Suggested.** A `split_words` helper that lowercases each token and then splits
CamelCase, so `PricingStrategy` would match the rubric keyword `pricing
strategy`.

**What actually happened.** It lowercased first, so the CamelCase split ran over
`pricingstrategy` and found no capitals to split on. The function looked
correct, read correctly, and silently never matched a single multi-word
criterion. A design that explicitly named `PricingStrategy` scored 70% with
"pricing is a separate collaborator" marked as a gap.

**Caught by** running an end-to-end smoke script before writing tests and
reading the output rather than the code. The fix is four lines: keep original
case until after the split.

`tests/test_submission.py::test_camel_case_is_split_as_well_as_kept_whole` pins
it, with a comment naming the bug. This is the entry I would point at: reviewing
AI code by reading it would not have found this.

## 3. Made the model prove its claims, rather than asking it to behave

**Suggested.** Handle model invention with prompt instructions: tell it not to
make things up, tell it to quote the submission.

**Partly accepted.** The instruction is in the prompt, and it helps. But a
prompt is a request, not a guarantee, and the failure mode here is specific: a
learner acting on a critique of a class they never wrote is worse off than a
learner with no critique.

**Added.** `LLMEvaluator._evidence_supported` checks every returned quote
against the submission's own symbols and drops items that do not overlap, then
reports the withheld count in the summary. It fires in practice: the live run
in the README withheld two observations out of seven. The check is ours, runs
locally, and costs nothing.

## 4. Rejected the AI's model id, using what this machine has actually measured

**Suggested.** `gemini-2.5-flash`, and later a `-latest` alias as a "always
current" convenience.

**Rejected on evidence.** `gemini-2.5-flash` returns 404 on this key, retired.
And `-latest` aliases are a trap: an alias repoints to whatever is newest, and
newest carries the *smallest* free-tier allowance. A `gemini-flash-latest` that
resolved to a 20-requests-per-day model would be exhausted by three demo runs.

**Built instead.** A pinned ladder of explicit model ids that falls through on a
quota failure, and `_is_daily_wall`, which branches on the response body rather
than the status code, because a 429 covers both a per-minute burst worth waiting
on and a per-day wall that is not. Both behaviours have tests.

## 5. A failing test where the code was right and the test was wrong

**What happened.** `test_a_missing_required_concept_is_a_gap_not_a_suggestion`
failed: it removed the `PricingStrategy` class from a fixture and expected the
rubric to report a gap, but no gap appeared. The reflex, and the AI's first
instinct, is to loosen the checker.

**Actually.** Another class in the fixture still listed `PricingStrategy` as a
collaborator. The submission genuinely did mention it, so the checker was
correct and the fixture was incoherent. I fixed the test.

**Why it is here.** A failing test is a hypothesis about the code, not a verdict
on it, and the cheapest way to ruin an evaluator is to relax it every time a
test disagrees.

## 6. Running the other two problems, rather than assuming one generalises

**The situation.** Parking Lot worked well: 73% for a design missing pricing,
92% once it was added. It would have been reasonable to stop there and write the
submission.

**Ran the other two anyway**, with a deliberately weak god-class design as well
as a strong one, to see whether the rubrics separated them. They did, but not
by enough: the weak Elevator scored 27% and the weak Vending Machine 20%, which
is too generous for designs with one class doing everything and no stated
trade-off.

**The cause was a real bug, not tuning.** Four criteria were being satisfied by
method names. `check_money` satisfied "money is a domain type". `get_change`
satisfied "making change is its own responsibility". "Opens the doors"
satisfied "the car has an explicit state". `up` and `down` in "goes up and
down" satisfied "direction is modelled". Every one of them credited a god class
for having modelled a concept it had not modelled at all.

**Fixed at the model layer, not by editing keywords.** `RubricCriterion` now
carries a `scope`. Criteria that are claims about a type existing match only
against class and collaborator names, which `Submission.declared_types()`
supplies and `CodeSubmission` reads from `ast.ClassDef`. Editing the keyword
lists would have papered over the same bug in every future problem.

Weak scores after the fix: 8%, 14%, 9%. Strong scores unchanged or slightly
higher. Five regression tests pin the specific false positives.

**Why it is here.** The AI wrote the original rubrics and they read as
perfectly sensible. The defect was only visible by running an adversarial input
through all three problems and being suspicious of a number that was merely
plausible.

## Two skills written for this repo

`.claude/skills/domain-design` and `.claude/skills/lld-evaluator` encode the
rules above so the next session enforces them instead of rediscovering them:
the layering rule, where behaviour goes, the deterministic-versus-judgement
split, and the evidence requirement. Written after the code, from what the
build actually taught, rather than as speculation up front.

## Where AI did the most work with the least argument

Boilerplate and volume: the SQLite mapper, the Jinja templates and CSS, the
`__init__` plumbing, and the first draft of the problem catalogue's rubric
keywords, which I then edited heavily to accept synonyms. Roughly speaking it
wrote most of the lines and I made most of the decisions, which is the split
that seemed to produce good code rather than a lot of it.
