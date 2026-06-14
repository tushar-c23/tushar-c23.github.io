---
title: "How jemalloc solves SMP — simplified"
date: 2026-06-14T10:00:00+05:30
tags: ["jemalloc", "c", "redis-internals"]
description: "A simplified explanation of how jemalloc's arenas and thread caches solve the SMP scalability problem that plagues classic malloc."
---
Lately I've been going through Redis internals, trying to figure out how Redis works under the hood and implement the same brick by brick locally myself. During this I found out that Redis re-implements `malloc` for its own use case, and further that Redis uses `jemalloc` instead of `malloc`.

I got curious as to why? What `jemalloc` was, what it does, and how it improves over our all-knowing classic `malloc`.

As I dug deeper into `jemalloc` I found this really great [talk on jemalloc by its creator](https://www.youtube.com/watch?v=RcWp5vwGlYU). Give it a watch if you're curious about `jemalloc` as well. Although that talk was more focused on dirty page management and how there was a time they thought async clock-based dirty page purging could improve `jemalloc`. But that's a discussion for some other day.

In this write-up I want to simplify the solution that `jemalloc` comes up with for the SMP scalability issue with `malloc`.

## What is SMP scalability?

To quote the standard explanation:

> Symmetric Multiprocessing (SMP) refers to computer architectures where two or more identical processors connect to a single shared main memory and are controlled by a single operating system. SMP scalability is the measure of how well an application's performance improves as you add more of these processors (or cores) to the system.

Now onto the SMP scalability issue. In a perfectly scalable system, running a program on 16 cores would be exactly 16 times faster than running it on 1 core. In reality, software rarely scales perfectly. As you add more cores, the threads running on them inevitably have to share resources or communicate with one another. To prevent data corruption, software uses locks, mutexes, or atomic operations to ensure only one thread modifies a shared resource at a time.

The SMP scalability issue arises when contention occurs. Multiple active processors sit idle, waiting in line for a lock to be released by another processor. As you add more cores, the line gets longer, the waiting increases exponentially, and the system can actually slow down despite having more hardware.

## So how does malloc suffer from the SMP scalability issue?

In older operating systems, standard `malloc` implementations acted like a single, massive pool of memory. If you had a heavily multi-threaded application, every single thread essentially had to wait in line for a global lock just to ask for memory. This lack of SMP scalability meant that as you added more cores, the system would actually grind to a halt due to constant contention.

{{< analogy >}}
Think of it this way: there is a large shelf and one custodian for the shelf, who fetches blocks or stores blocks on the shelf on behalf of the people who want to get or keep blocks there. The custodian can work for one person at a time, so everyone else needs to wait in line for the previous person's task to be completed before they can ask the custodian to do theirs. The people here are a corollary for **threads** and the custodian is a corollary for **locks**. Now every thread (person) is in a rush, but if they can't get their task done in time because they're stuck waiting in the queue, a problem arises; think of it as a rage issue. The threads get angry, and rage is never good for a system.
{{< /analogy >}}

![jemalloc SMP illustration](malloc_vs_jemalloc_smp.svg)

## Okay, how does jemalloc solve this then?

To fix this, `jemalloc` introduces **arenas**. Arenas are completely disjoint, independent memory allocators. Instead of fighting over one global lock, `jemalloc` can route different threads to different arenas, allowing multiple CPUs to allocate and free memory simultaneously.

Furthermore, threads don't even talk directly to the arena for every allocation. They pull batches of memory into their own private **thread caches**. In its steady state, `jemalloc` can handle most allocations entirely lock-free without any atomic operations, an absolute necessity for high-performance servers.

{{< analogy label="Analogy, continued" >}}
Continuing with our previous corollary: imagine the shelf is now distributed into parts, and each part has a custodian of its own. Each person can talk to any custodian, and having multiple custodians ensures that multiple people's requests are served in parallel. To add to it, imagine each person also has a sack (thread cache) to carry their blocks, and they periodically get a new sack from the custodians (arenas). So, now they don't even have to talk to a custodian every time they want to keep or get a block. This is essentially how `jemalloc` solves the SMP scalability issue.
{{< /analogy >}}

This write-up does not go into the depth of how arenas are managed, or the structure of an arena and how it acts independently as a memory allocator, but it tries to simplify the concept for easier understanding.

---

*Source & further reading: the [jemalloc repository on GitHub](https://github.com/jemalloc/jemalloc).*
