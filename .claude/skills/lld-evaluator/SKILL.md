---
name: lld-evaluator
description: The rules for adding, changing or reviewing anything that judges a submission in this project - the deterministic-versus-LLM split, the evidence requirement, the degradation contract, and how to add a new evaluator or a new problem rubric. Use when touching app/evaluation, writing rubric criteria, changing the review prompt, or debugging feedback that looks wrong.
---

# Evaluators

Everything that judges a design implements `Evaluator` in
`app/evaluation/evaluator.py`: one method, `evaluate(problem, submission) ->
Evaluation`, raising `EvaluationError` on failure. Nothing above the seam knows
which evaluators exist.

## The split, which is the whole design

**Deterministic where the answer is a fact. A model where the answer is a
judgement.**

| Fact, so it goes in `RubricEvaluator` | Judgement, so it goes to the model |
|---|---|
| Is the concept named at all | Does the abstraction earn its place |
| Is a responsibility stated per class | Is the responsibility the right one |
| Does the code parse | Is the behaviour in the right class |
| Does one class hold most of the methods | Is that class coordinating or doing |
| Is a trade-off stated | Is it a real trade-off |

If you are about to add a keyword check that needs an opinion, you are on the
wrong side of the table. If you are about to ask the model something a `set`
membership test answers, likewise, and it will cost a request from a daily
quota to get a less reliable answer.

## Three rules that are not negotiable

**1. Rubric is required, the model is optional.** `EvaluationPipeline` takes
`required` and `optional` lists. A required evaluator failing fails the attempt;
an optional one failing sets `degraded` with a reason and the learner still gets
feedback. Never move `RubricEvaluator` to optional, and never move
`LLMEvaluator` to required. The property this buys is that a learner cannot
watch a spinner that ends in nothing.

**2. Every model observation must carry evidence found in the submission.**
`LLMEvaluator._evidence_supported` drops items whose quote does not overlap the
submission's own symbols, and the withheld count goes in the summary. If you
loosen `EVIDENCE_OVERLAP`, you are trading the one defence against invented
critique for slightly more feedback. Do not do it without a measurement.

**3. Feedback keeps its `source`.** `rubric` and `llm` are shown separately in
the UI on purpose. A learner should weight a mechanical check and a model's
opinion differently, and can only do that if they can tell them apart.

## Adding a new evaluator

1. Subclass `Evaluator`, set `name`, implement `evaluate`.
2. Return `Evaluation` with `sources=[self.name]` and a `DimensionScore` per
   `Dimension` you have an opinion about. Do not invent dimensions; the enum is
   closed so results stay mergeable.
3. Override `is_available` if it can be unconfigured. The pipeline skips an
   unavailable optional evaluator without calling it and says so in
   `degraded_reason`.
4. Wire it in `app/config.py:build_evaluator`, nowhere else.
5. Test it with a fake, not a network. `tests/test_llm_evaluator.py` is the
   pattern: the class under test is our handling of a response, so the response
   is a fixture.

## Writing rubric criteria for a new problem

Criteria live on the `Problem` in `app/content/problems.py`, not inside an
evaluator, which is what lets a second strategy be added without touching
content.

- **Keywords are alternatives a reasonable design would use**, never the one
  right name. `spot`, `slot`, `bay`, `space` all satisfy the same criterion.
  Penalising vocabulary instead of modelling is the failure that makes
  automated LLD review useless.
- **Multi-word keywords require every word.** `"parking spot"` is not satisfied
  by `parking`. This is load-bearing and has a test.
- **Set `scope=MatchScope.TYPE_NAME` when the criterion is a claim about a
  type existing.** "Money is a domain type" and "making change is its own
  responsibility" are questions about class names, and matching them anywhere
  credits a god class for having a `check_money` method. `ANYWHERE` is right
  for concepts a design may legitimately express in prose or a method name,
  like "doors are modelled". Getting this wrong is not theoretical: four
  criteria shipped with it wrong and were caught by running two problems end
  to end.
- **Avoid bare common words as keywords.** `up` and `down` matched "goes up and
  down" and credited "direction is modelled". If a keyword would appear in an
  offhand sentence, it is not evidence.
- **`required=True` means a gap, not a suggestion.** Reserve it for concepts a
  design genuinely cannot omit. Everything required is a red mark on the page.
- **`description` is shown to the learner verbatim**, prefixed by "Covered:" or
  "Not found in your design:". Write it as the thing you want them to read.

## Debugging feedback that looks wrong

- A criterion that should have matched but did not: check the tokeniser first.
  `python -c "from app.domain.submission import split_words; print(sorted(split_words('YourText')))"`.
  CamelCase must survive until after the split, and it has been broken once.
- A criterion matching something the learner did not write: the symbol probably
  came from a collaborator reference or a comment. `CodeSubmission.symbols()`
  reads the AST for exactly this reason, so comments do not count.
- Model output rejected: the failure is in `_parse` or `_items_from`. Both raise
  or drop rather than guessing, and both are retryable, so the learner sees a
  retry rather than a wrong answer.

## Quota, because it will bite

Free-tier Gemini is per model per day, and a 429 covers two unrelated things.
`GeminiClient._is_daily_wall` branches on the body: a per-minute burst is worth
waiting on, a per-day ceiling is not and moves to the next model in the pinned
ladder. Never pin a `-latest` alias; an alias repoints to whatever is newest and
newest carries the smallest allowance.

The platform is designed so that all of this degrades to rubric-only feedback
rather than an outage. Keep it that way.
