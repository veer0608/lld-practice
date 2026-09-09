# Research note

## The learner's actual problem

LLD practice is cheap to start and almost impossible to finish. A learner can
sit down with "design a parking lot", produce six classes in twenty minutes,
and then stop, because there is nothing to tell them whether those six classes
were any good. The loop terminates at the point where learning would begin.

This is different from algorithm practice in one specific way, and every design
decision in this project follows from it: **an algorithm problem has a unique
correct output and an LLD problem does not.** `two_sum` either returns the right
indices or it does not, so a test suite is a complete oracle. A parking lot can
be modelled with a `SpotAllocator` or with allocation on `Floor`, and both can
be defensible. There is no test to write.

So the learner is stuck with three unsatisfying options: read a reference
solution and hope they can tell the difference, ask a person, or ask a model
and be told they did well.

The failure is not a lack of problems. Problems are abundant and free. The
failure is that **nothing about an attempt is comparable to anything else**,
including the learner's own previous attempt.

## What already exists

Desk research, not user interviews. Two days did not allow for the latter, and
saying so is more useful than implying a study happened.

| Approach | Example | What it does well | Where it stops |
|---|---|---|---|
| Algorithmic autograders | LeetCode, HackerRank | Instant, objective, repeatable. The oracle is free. | The oracle only exists because the answer is unique. No LLD equivalent. |
| Curated reference solutions | Grokking the OO Design Interview, educational LLD repos | Genuinely good reference designs, well explained. | Read-only. No submission, no feedback. The learner grades themselves against one answer, which teaches recall of that answer. |
| Human mock interviews | Pramp, Exponent, paid mentors | The best feedback that exists. A person can follow reasoning. | Scarce, expensive, scheduled. Not available at 11pm on the fourth attempt, which is when practice actually happens. |
| Diagram tools | Excalidraw, Whimsical, PlantUML | Capture the artifact cleanly. | Judge nothing. A diagram tool has no opinion. |
| Direct LLM chat | ChatGPT, Claude, Gemini | The strongest current substitute. Free, instant, unlimited, and it can genuinely reason about responsibility placement. | Three specific problems, below. |

Direct LLM chat deserves its own paragraph, because it is what a motivated
learner uses today and any new product has to beat it rather than ignore it.

1. **Nothing is comparable across attempts.** A fresh chat has no rubric and no
   memory. Attempt 2 is judged by different implicit standards than attempt 1,
   so a learner cannot tell improvement from a friendlier reply.
2. **It is agreeable.** Free-form review drifts towards praise. A learner
   optimising for the response learns to write designs that read well.
3. **It is unfalsifiable.** When a model says "your `PricingStrategy` should not
   depend on `Payment`", the learner has no way to check whether they wrote that
   or whether the model imagined it. Both happen. Invented critique is worse
   than no critique, because the learner acts on it.

## The gaps worth building into

1. **No shared submission format.** Prose and code and diagrams are all
   accepted by a human reviewer, and none of them are comparable to each other
   or checkable by a machine.
2. **No stable rubric per problem.** Without one, a score is a mood.
3. **Feedback that cannot be traced back to what the learner wrote.**
4. **No record of improvement**, which is the only outcome that matters and the
   only one nothing currently measures.

## Product direction

The platform's job is not to grade an LLD design. Grading implies a right
answer, and the whole premise is that there is not one.

Its job is narrower and more achievable: **make attempts comparable over time,
and make every piece of feedback checkable.** Four commitments follow.

**Structure the submission, not the solution.** The learner is asked for named
classes, a stated responsibility per class, stated collaborators, and the
trade-off they knowingly made. Not a specific design. The format is what makes
comparison possible; the content stays entirely theirs. Free prose is still
accepted, and the platform says out loud that it will get shallower feedback,
because the alternative is silently scoring it lower.

**Fix a rubric per problem, and show it.** Every problem carries explicit
criteria. Criteria accept synonyms, because penalising a learner for writing
`Bay` instead of `Spot` is exactly the failure that makes automated review
useless. A fixed rubric is what makes attempt 4 comparable to attempt 1.

**Split evaluation by what kind of question it is.** Coverage, presence,
structure and parse errors are facts, and facts get a deterministic checker
that costs nothing and returns the same answer tomorrow. Whether an abstraction
earns its place is a judgement, and judgement gets a model. Every observation is
labelled with which produced it, so a learner can weight them differently, and
should.

**Require evidence, and drop what cannot show it.** A model observation whose
quote does not appear in the submission is discarded before the learner sees it,
and the count of what was withheld is shown. This is the cheapest available
defence against invented critique, and it runs on our side rather than trusting
the model to behave.

**Make improvement the visible outcome.** History and a score trend per problem
are first-class, not a settings page. The product's claim is that attempt 3
should be better than attempt 1, so that number is the one on the screen.

## What this direction gives up

It will under-reward an unusual but excellent design, because keyword coverage
cannot recognise originality. That is a real cost, and it is bounded: the
deterministic half can only ever mark a concept present or absent, the model
half is what is allowed to have an opinion, and the learner can see which is
which. A product that hid that split would be claiming an authority it does not
have.
