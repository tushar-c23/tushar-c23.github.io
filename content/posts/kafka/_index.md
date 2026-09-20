---
title: "Kafka Internals"
date: 2026-09-20T19:30:00+05:30
description: "Reading the Apache Kafka design doc against the actual source, module by module, refusing to believe any claim I haven't measured against a real broker."
---
I'm working through the Apache Kafka design doc with the source open next to it, verifying every claim against the code that implements it and against a single-node KRaft broker running on my laptop. Anything I can't reproduce doesn't go in.

Notes from that, as I go, below.
