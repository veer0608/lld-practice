# AI usage

I built this with Claude Code, mostly for the boilerplate and the first draft
of anything (the SQLite mapper, templates, rubric keyword lists), and did the
actual design and review myself. Below are the five places where its first
answer and my second look genuinely diverged, plus what that cost or saved.

## 1. It wanted to skip the rubric and just call the model

The fast way to build this is: send the design to Gemini, show whatever comes
back. I said no, because it ties the product's core promise to a free-tier
quota. Gemini's limit is per model per day, so on the wrong day a reviewer
opening the demo just sees an error. Worse, the model doesn't give the same
score twice for the same input, which quietly breaks the one thing this
platform is supposed to prove: that attempt 3 is actually better than attempt
1.

So evaluation runs through a pipeline with a required rubric checker (free,
deterministic) and an optional model call. If the model fails, the learner
still gets rubric feedback with a note saying it's degraded, not a blank
screen. That split ended up being the backbone of the whole design, not a
fallback bolted on afterward.

## 2. A tokeniser bug that looked completely fine

Claude wrote a `split_words` helper: lowercase each token, then split
CamelCase so `PricingStrategy` would match the rubric keyword "pricing
strategy". Except it lowercased *first*, so by the time the CamelCase splitter
ran there was nothing left to split: `pricingstrategy` has no capitals in it.
Every multi-word rubric criterion silently stopped matching. A design that
correctly named `PricingStrategy` scored 70% and got told "pricing is a
separate collaborator" was missing.

I only found this because I ran an end-to-end script before writing any tests
and actually read the output instead of skimming the diff. The fix is four
lines: keep the original casing until after the split. It's pinned now in
`test_camel_case_is_split_as_well_as_kept_whole`, with a comment explaining
what broke. This is the one I'd point to if someone asked whether reading AI
code carefully is enough. It isn't. Here it wasn't even close.

## 3. Telling the model not to lie isn't the same as checking it didn't

My first instinct was to just instruct the model in the prompt: don't invent
detail, quote the submission. That's a request, not a guarantee, and the
failure mode is nasty: a learner reading a critique of a class they never
wrote is worse off than a learner who got no critique at all.

So there's a check on our side: `LLMEvaluator._evidence_supported` looks at
every quote the model returns and drops anything that doesn't actually overlap
words in the submission, then tells the learner how many were withheld. In the
sample run in the README, two of seven observations got dropped this way. It
costs nothing and needs no trust in the model behaving.

## 4. It suggested a model id that doesn't work, then a worse one

First suggestion was `gemini-2.5-flash`, which 404s. Retired on this key.
Second suggestion, once I pushed back, was a `-latest` alias, framed as the
safe "always current" choice. That's backwards: `-latest` aliases repoint to
whatever's newest, and the newest model usually has the smallest free-tier
quota. `gemini-flash-latest` resolves to a model capped at 20 requests a day,
which three demo runs would burn through.

I ended up pinning explicit model ids in a fallback ladder, and wrote
`_is_daily_wall` to read the actual response body instead of trusting the
status code. A 429 can mean "wait a few seconds" or "come back tomorrow," and
those need very different handling. Both cases have tests.

## 5. Twice, a plausible-looking result was wrong

One was a test failure. `test_a_missing_required_concept_is_a_gap_not_a_suggestion`
started failing after I dropped a `PricingStrategy` class from a test fixture,
expecting a gap that never showed up. The obvious move is to assume the
checker regressed and loosen it. It hadn't. Another class in the same fixture
still listed `PricingStrategy` as a collaborator, so the submission genuinely
did mention it, and the checker was right. I fixed the fixture, not the code.

The other was a score. Parking Lot was working well (73% for a design missing
pricing, 92% once it was added), and it would've been easy to call that done.
Running the same test against the other two problems, with a
deliberately bad god-class design, showed the rubric wasn't actually strict
enough: the weak Elevator scored 27%, the weak Vending Machine 20%. That's
too generous for a design that's one class doing everything with no stated
trade-off.

The cause wasn't miscalibration, it was a bug. Four criteria were passing
because of method names, not real design: `check_money` satisfied "money is a
domain type," `get_change` satisfied "making change is its own
responsibility," even the phrase "opens the doors" satisfied "the car has an
explicit state." Editing the keyword lists would've just moved the bug
somewhere else, so instead `RubricCriterion` got a `scope`: a criterion that
claims a type exists now only matches actual class and collaborator names,
sourced from `Submission.declared_types()` (and from `ast.ClassDef` for code
submissions). Weak scores dropped to 8%, 14%, 9%. Five regression tests pin
the specific cases that used to slip through.

What ties both of these together: nothing was obviously broken until I went
looking for it. That same instinct, not trusting a number just because it's
plausible, later caught three more issues after this section was first
written: a headline score that blended a coverage percentage with a model
opinion into a number that meant neither, a merge step that silently dropped
the rubric's own summary whenever the model succeeded, and a submission format
that registered fine but got no structural checks at all. All three are fixed
and covered by tests.

---

Two things came out of this build that aren't code: `.claude/skills/domain-design`
and `.claude/skills/lld-evaluator`, which write down the rules the bugs above
taught (where behaviour belongs, the deterministic/judgement split, why
evidence has to be checked and not just requested) so the next session
doesn't have to relearn them the hard way.
