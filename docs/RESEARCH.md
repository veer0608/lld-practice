# Research note

## The problem

LLD practice is easy to start and hard to actually finish. Someone sits down
with "design a parking lot," has six classes on the page in twenty minutes,
and then just stops, because nothing tells them whether those six classes
were any good. The loop ends right where the learning was supposed to start.

That's genuinely different from practicing algorithms, and it's the reason
every decision in this project ended up the way it did: an algorithm problem
has one correct output, an LLD problem doesn't. `two_sum` either returns the
right indices or it doesn't, so a test suite is a complete answer key. A
parking lot can be modeled with a `SpotAllocator`, or with allocation living
directly on `Floor`, and both hold up. There's no test you can write to settle
it.

So a learner ends up with three options, none of them great: read someone
else's reference solution and try to guess what they got right, find a person
to review it, or ask a model and get told it looks good. The real failure
here isn't a shortage of problems, there are plenty of those for free. It's
that nothing about one attempt is comparable to anything else, including your
own last attempt.

## What's already out there

This is desk research, not interviews. Two days doesn't leave room for the
latter, and it seemed more honest to say that than to write around it.

| Approach | Example | Where it's strong | Where it stops |
|---|---|---|---|
| Algorithmic autograders | LeetCode, HackerRank | Instant, objective, free to run repeatedly | Only works because the answer is unique. Nothing like it exists for LLD. |
| Curated reference solutions | Grokking the OO Design Interview, various LLD repos | Genuinely well-explained reference designs | Read-only. No submission, no feedback loop. You grade yourself against one answer, which mostly just teaches you to recall that answer. |
| Human mock interviews | Pramp, Exponent, paid mentors | The best feedback available, a person can actually follow your reasoning | Scarce, expensive, has to be scheduled. Not there at 11pm on your fourth attempt, which is usually when the actual practicing happens. |
| Diagram tools | Excalidraw, Whimsical, PlantUML | Capture the design cleanly | Judge nothing at all. A diagram tool has no opinion on what you drew. |
| Direct LLM chat | ChatGPT, Claude, Gemini | The strongest thing available today. Free, instant, no limit, and it can genuinely reason about where responsibility belongs | Three specific problems, below |

Direct LLM chat gets its own paragraph because it's what a motivated learner
is actually using right now, and any new product has to be better than it,
not just different from it.

It has three problems. Nothing carries over between attempts: a fresh chat
has no rubric and no memory, so attempt 2 gets judged by whatever the model
feels like that day, and you can't tell real improvement from the model just
being in a better mood. It's agreeable by default: free-form review tends
toward praise, and if you're optimizing for the response you learn to write
designs that read well rather than designs that hold up. And it's
unfalsifiable: when it tells you "your `PricingStrategy` shouldn't depend on
`Payment`," you have no way to check whether you actually wrote that or the
model just imagined it. Both happen in practice, and invented critique is
worse than no critique because you'll act on it either way.

## Where the actual gaps are

Four things stood out. There's no shared submission format, so prose, code,
and diagrams all get treated the same by a human reviewer but none of them
are comparable to each other or checkable by a machine. There's no stable
rubric per problem, so a score is really just a mood. Feedback usually can't
be traced back to anything specific the learner wrote. And nothing records
improvement over time, which is honestly the only outcome that matters here
and the one thing nobody currently measures.

## Where this points the product

This platform's job isn't to grade an LLD design. Grading implies there's a
right answer, and the whole point above is that there usually isn't one.

The narrower, more honest job is making attempts comparable to each other and
making every piece of feedback something you can check. Four things follow
from that.

The submission gets structured, not the solution. A learner has to name
classes, give each one a stated responsibility, name the collaborators, and
say what trade-off they made. Not a specific design, just that shape. The
structure is what makes comparison possible; what goes inside it is still
entirely theirs. Free prose is still accepted, and it's told up front that
it'll get shallower feedback, since the alternative (scoring it lower without
saying why) is worse.

Each problem gets a fixed rubric, and the rubric is visible. Criteria accept
synonyms, because docking someone for writing `Bay` instead of `Spot` is
exactly the kind of failure that makes automated review pointless. A fixed
rubric is also what actually makes attempt 4 comparable to attempt 1.

Evaluation splits by what kind of question is being asked. Coverage,
presence, structure, parse errors: these are facts, and facts get a
deterministic checker that costs nothing and gives the same answer tomorrow.
Whether an abstraction earns its place is a judgement call, so that goes to a
model. Every piece of feedback says which one produced it, so a learner can
trust them differently, and should.

And evidence is required, not optional. If a model observation's quote
doesn't actually appear in the submission, it gets dropped before the learner
ever sees it, and the count of what got dropped is shown. It's the cheapest
real defense against invented critique there is, and it runs on our side
rather than hoping the model behaves.

Improvement is the thing you actually see. History and a score trend per
problem live on the main screen, not buried in settings, because the whole
claim this product makes is that attempt 3 should beat attempt 1, and that
needs to be the number you're looking at.

## What this costs

An unusual but genuinely excellent design will score lower than it deserves,
because keyword coverage can't recognize originality. That's a real cost. It's
also a bounded one: the deterministic half can only ever say a concept is
present or absent, the model half is the only one allowed to have an opinion,
and a learner can see which is which on every line. Hiding that split would
be claiming more authority than the system actually has.
