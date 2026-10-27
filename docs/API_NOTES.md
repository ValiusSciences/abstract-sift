# Verified API notes

Checked against official documentation on 2026-10-26. Both endpoints subsequently passed the two-abstract live demo on 2026-10-26 using the configured account. A subsequent full-corpus run completed in 13.31 seconds on the user’s account; clinical screening accuracy has not been validated.

## Decisions route

The published Decisions guide describes `POST /v1/decisions` with `gpt-6-luna`, typed predicate/choice/score answers, and up to 400 questions per request. Predicates return estimated probabilities. Written explanations require a generative route. The guide lists uncached input at $0.10 per million tokens and no output-token charge, subject to its pricing qualifications. Shared-input caching requires a sufficiently long matching prefix; question content is outside that prefix. The documented speed advantage is a comparison to Responses, not a guarantee for a whole corpus.

Source: [Decisions guide](https://developers.openai.com/api/docs/guides/decisions).

The reference supplies unique question names, question-specific text instructions, usage counters, and per-question refusal answers. The adapter must validate expected names, answer types, and numeric ranges, retaining individual failures. A request's maximum question count does not establish that hundreds of long abstracts will fit or be fast.

Source: [Create a decision](https://developers.openai.com/api/reference/resources/decisions/methods/create).

## Authentication scope

The current product supports OpenAI Decisions and TypeSafe JEV through separate API keys. ChatGPT sign-in is out of scope. The documented plan-funded inference route uses Responses, so it is not a substitute credential for this Decisions integration.

Source: [Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference).

## Operational references

Use account-specific limits and response headers to control request and token throughput; implement bounded retries with jitter and respect retry delays. Concurrency is a tuning parameter, not a way around quotas.

Source: [Rate limits](https://developers.openai.com/api/docs/guides/rate-limits).


## TypeSafe JEV: first-party integration

Use `POST https://api.typesafe.ai/v1/systemone` with `model`, shared `state`, and a map of named questions. JEV's `noul` question supplies a yes/no judgment; `answers.<name>.noul` is the probability of yes. It has no separate confidence field. Align its positive direction with OpenAI's relevance predicate. Keep providers' response shapes distinct in the adapters.

Sources: [System One API](https://docs.typesafe.ai/api/system-one), [Noul semantics](https://docs.typesafe.ai/primitives/noul).

The current official model page lists `jev-1.14.0`, input pricing of $0.042 per million tokens, and free output. Default context limits are 64k tokens for state plus all questions and 32k for state plus one question. There is no independent question-count cap under these limits. Organization quotas use requests/second and tokens/second. Pin a model version for comparisons and record the returned version; keep experimental long context off. Recheck pricing, tokenizer behavior and accessible models during implementation.

Source: [TypeSafe models, limits and pricing](https://docs.typesafe.ai/models).

Search results include many similarly named services with different limits and keys. Those are not the integration target. No unofficial proxy is authorized by this design. The subsequent user-run ESMO benchmark completed 295 OpenAI attempts and 164 JEV attempts for 4,284 abstracts each, with $0.8680 combined usage-derived cost. This is a measured example, not an account-independent speed or billing guarantee.
