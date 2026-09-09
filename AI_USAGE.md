# AI usage

Built with Claude Code as a pair. Five decisions where the AI's suggestion and
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

## 5. Not trusting a result that merely looked plausible

Twice, the thing that caught a defect was refusing to accept a number or a
failure that looked reasonable.

**A failing test where the code was right.**
`test_a_missing_required_concept_is_a_gap_not_a_suggestion` failed: it removed
the `PricingStrategy` class from a fixture and expected a gap, and no gap
appeared. The reflex, and the AI's first instinct, is to loosen the checker.
In fact another class in the fixture still named `PricingStrategy` as a
collaborator, so the submission did mention it and the checker was right. I
fixed the test. A failing test is a hypothesis about the code, not a verdict on
it, and the cheapest way to ruin an evaluator is to relax it whenever a test
disagrees.

**A score that was merely plausible.** Parking Lot worked well, so it would have
been reasonable to stop and write this up. Running the other two problems with a
deliberately weak god-class design showed the rubrics did separate strong from
weak, but not by enough: the weak Elevator scored 27% and the weak Vending
Machine 20%.

The cause was a bug, not miscalibration. Four criteria were being satisfied by
method names. `check_money` satisfied "money is a domain type". `get_change`
satisfied "making change is its own responsibility". "Opens the doors" satisfied
"the car has an explicit state". `up` and `down` in "goes up and down" satisfied
"direction is modelled". Every one credited a god class with modelling a concept
it had not modelled.

Fixed at the model layer rather than by editing keywords: `RubricCriterion` now
carries a `scope`, so criteria that are claims about a type existing match only
class and collaborator names, which `Submission.declared_types()` supplies and
`CodeSubmission` reads from `ast.ClassDef`. Rewriting the keyword lists would
have left the same defect waiting in every future problem. Weak scores after the
fix: 8%, 14%, 9%, with strong scores unchanged. Five regression tests pin the
specific false positives.

**Why it is here.** The AI wrote those rubrics and they read as perfectly
sensible. Both defects were visible only by running adversarial input and being
suspicious of output that was plausible rather than verified. The same
discipline later found three more, all now fixed and pinned by tests: a headline
score that blended a coverage fraction with a model judgement into a number that
was neither, a merge that silently discarded the rubric's summary whenever the
model succeeded, and a fourth submission format that registered correctly and
then received no structural checks at all.

## Where AI did the most work, and where it needed the least argument

Boilerplate and volume: the SQLite mapper, the templates and CSS, the `__init__`
plumbing, and the first draft of the rubric keywords, which I then edited heavily
to accept synonyms. It wrote most of the lines and I made most of the decisions.

Two repo skills, `.claude/skills/domain-design` and `.claude/skills/lld-evaluator`,
encode the rules the build actually taught so a later session enforces them
rather than rediscovering them: the layering rule, where behaviour goes, the
deterministic-versus-judgement split, and the evidence requirement.
