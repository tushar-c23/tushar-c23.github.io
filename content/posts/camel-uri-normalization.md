---
title: "Camel sorts your URI parameters — except when it doesn't"
date: 2026-08-15T10:00:00+05:30
tags: ["apache-camel", "kafka", "java"]
description: "Apache Camel normalises endpoint URIs by sorting query parameters, so param order shouldn't matter. It does — if any value contains a character that needs encoding. Here's the branch that causes it."
---
We recently shipped a fix at work for a Kafka producer leak: a URI was being built with the record key baked into it, so every distinct key produced a distinct Camel endpoint, and every endpoint got its own `KafkaProducer`, its own network thread, and its own 10-thread worker pool. One string, hundreds of producers.

Fixing it was easy. Understanding *why* Camel behaved that way sent me into `camel-core`, and on the way I tripped over something I haven't seen written down anywhere.

Short version: **Camel normalises endpoint URIs by sorting the query parameters, so parameter order shouldn't matter. It usually doesn't. But if any parameter value contains a character that needs URL-encoding, order suddenly does matter** — and you silently get two endpoints where you meant one.

Every Kafka broker string contains such a character. It's the colon in `host:port`.

## Endpoint identity is the URI string

Some background, if you haven't been inside Camel.

When you call `camelContext.getEndpoint(uri)`, Camel doesn't build a fresh endpoint each time. It normalises the URI, looks it up in an LRU registry keyed by that normalised string, and returns the cached instance if there is one. The endpoint owns the producer, and the producer owns the connections and threads.

{{< analogy >}}
Think of the URI as a room number rather than a description of a room. Two people who write the same room number down get sent to the same room. Two people who write it slightly differently get sent to two different rooms — even if they were describing the same place, and even if the second room has to be built from scratch to accommodate the mistake.
{{< /analogy >}}

So the normalisation step is load-bearing. It's what makes `kafka:t?a=1&b=2` and `kafka:t?b=2&a=1` mean the same thing. That's the whole point of it — the Javadoc says as much:

> normalize uri so we can do endpoint hits with minor mistakes and parameters is not in the same order

## The experiment

Two pairs of URIs. Each pair is the same URI written with the parameters in a different order.

```java
// (A) no unsafe characters in any value
Endpoint a1 = ctx.getEndpoint("kafka:t1?retries=3&clientId=abc");
Endpoint a2 = ctx.getEndpoint("kafka:t1?clientId=abc&retries=3");

// (B) a ':' in one value
Endpoint b1 = ctx.getEndpoint("kafka:t2?retries=3&brokers=localhost:19092");
Endpoint b2 = ctx.getEndpoint("kafka:t2?brokers=localhost:19092&retries=3");
```

Output, on Camel 4.8.5:

```text
A same? true
  kafka://t1?clientId=abc&retries=3
  kafka://t1?clientId=abc&retries=3

B same? false
  kafka://t2?brokers=localhost%3A19092&retries=3
  kafka://t2?brokers=localhost:19092&retries=3

registry: 3
```

Case A behaves exactly as advertised. Case B does not — and look closely at *how* it fails.

The sorting worked. Both B strings have `brokers` before `retries`. The keys are in identical order. The strings still differ, by exactly one character: `%3A` versus `:`.

Three endpoints in a registry where I asked for two.

## The branch

Here's `URISupport.buildReorderingParameters`, the method that does the work (`core/camel-util`, Camel 4.8.5):

```java
private static String buildReorderingParameters(String scheme, String path, String query) {
    Map<String, Object> parameters = null;
    if (query.indexOf('&') != -1) {
        parameters = URISupport.parseQuery(query, false, false);
    }

    if (parameters != null && parameters.size() != 1) {
        final Set<String> entries = parameters.keySet();

        // reorder parameters a..z
        // optimize and only build new query if the keys was resorted
        boolean sort = false;
        String prev = null;
        for (String key : entries) {
            if (prev != null && key.compareTo(prev) < 0) {
                sort = true;
                break;
            }
            prev = key;
        }
        if (sort) {
            final String[] array = entries.toArray(new String[0]);
            Arrays.sort(array);
            query = URISupport.createQueryString(array, parameters, true);
        }
    }
    return buildUri(scheme, path, query);
}
```

The comment tells you the intent: *only build a new query string if the keys were actually resorted*. Sensible optimisation. Rebuilding a string you don't need to rebuild is waste.

The catch is that **rebuilding the query string is also the only thing that applies encoding.** That third argument to `createQueryString(array, parameters, true)` is `encode`. When `sort` stays `false`, the method never runs, and the original query substring is concatenated into the final URI verbatim — never parsed, never encoded.

So sorting and encoding are coupled to the same flag:

| input order | `sort` | query rebuilt? | encoded? |
| --- | --- | --- | --- |
| already alphabetical | `false` | no | **no** |
| needs reordering | `true` | yes | yes |

Two inputs that describe the same endpoint take two different paths and come out as two different strings. Both are "normalised". Neither is wrong on its own terms. They just aren't equal, and equality is what the registry uses.

Note the two other early exits, which have the same effect: a query with no `&` at all (single parameter), and `parameters.size() == 1`. Both skip the block entirely and stay unencoded.

## Why this is worse than it looks

The failure is completely silent. You don't get an exception, a warning, or a log line. You get an extra endpoint, and in the Kafka case that means:

- an extra `KafkaProducer`
- an extra `kafka-producer-network-thread`
- an extra worker thread pool, which in Camel's Kafka component grows to 10 threads under load
- an extra set of TCP connections — and if you're on `SASL_SSL`, an extra TLS and SASL handshake plus roughly 50&nbsp;KB of on-heap buffers per connection

All because two call sites in two different files wrote the same parameters in a different order.

And the trigger isn't exotic. `:` is unsafe in a URI query. Every Kafka bootstrap server is `host:port`. Any URI you hand-assemble by string concatenation is a candidate.

## Why our production code was fine

This is the part that made me stop worrying and start appreciating the endpoint DSL.

We never hand-write Kafka URIs. They're built through Camel's fluent builder:

```kotlin
kafka(topicName).brokers(bootStrapServer)
    .enableIdempotence(true)
    .retries(KAFKA_MAX_RETRIES)
    .requestRequiredAcks(KAFKA_ACKS_ALL)
```

And `AbstractEndpointBuilder.computeUri` does this:

```java
// sort parameters so it can be regarded as normalized
Map<String, Object> params = new TreeMap<>();
```

A `TreeMap`. The DSL emits parameters in alphabetical order **by construction**, so Camel's normaliser always sees an already-sorted query, always takes the pass-through branch, and always produces a byte-identical string. Every call site agrees, deterministically.

That's why a piece of code in our codebase that rebuilds its Kafka URI on *every single invocation* is safe rather than catastrophic. It isn't luck. It's that `TreeMap`.

It also means the safety is a property of the builder, not of Camel's normaliser. Replace one `kafka(topic).brokers(...)` call with a "simpler" string template and you reintroduce the bug in a form that is genuinely hard to see in review — the two URIs look identical to a human, because as descriptions of an endpoint, they are.

## Takeaways

1. **Endpoint identity in Camel is the normalised URI string, not the endpoint's meaning.** Anything that changes the string changes the identity, and identity is what owns your connections and threads.
2. **Never hand-assemble Camel endpoint URIs.** Use the endpoint DSL. The `TreeMap` is doing more for you than readability.
3. **Normalisation is not idempotent across input orderings when values need encoding.** If you must build a URI by hand, sort your parameters alphabetically yourself, or you're relying on a branch that was written as a performance optimisation.
4. When you're debugging "why do I have N of these", print `endpoint.getEndpointUri()` for every entry in the registry and diff them character by character. The difference may be one character wide.

---

*All line references are against the `camel-4.8.5` tag in the [Apache Camel repository](https://github.com/apache/camel). The relevant code is `URISupport.buildReorderingParameters` in `core/camel-util`, and `AbstractEndpointBuilder.computeUri` in `dsl/camel-endpointdsl`.*
