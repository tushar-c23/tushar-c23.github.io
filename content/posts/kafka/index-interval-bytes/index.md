---
title: "Index this, index that. How does Kafka do it?"
date: 2026-09-27T18:30:00+05:30
tags: ["kafka", "distributed-systems", "storage", "performance"]
series: ["Kafka Internals"]
description: "Almost every Kafka topic runs with index.interval.bytes at its default, and the docs tell you not to worry about it. But it tunes the structure every single fetch goes through. What the offset index is, what the config actually changes (less than its name says), what it costs you in production, and when it starts to matter at scale."
---
*Second in the [Kafka Internals](/posts/kafka/) series. Same rules as [the first one](/posts/kafka/batch-is-the-unit/): Kafka trunk (4.5.0-SNAPSHOT, commit `6e4bc7d5c3`), a single-node KRaft broker on my laptop, and nothing goes in that I haven't reproduced.*

Describe any topic you own with all its configs:

```bash
kafka-configs.sh --bootstrap-server $B --entity-type topics --entity-name <topic> --describe --all
```

and somewhere in the output you'll find this:

```
index.interval.bytes=4096 sensitive=false synonyms={DEFAULT_CONFIG:log.index.interval.bytes=4096}
```

`DEFAULT_CONFIG`. You didn't set it. Neither did anyone on your team. Nobody puts it in a topic-creation script, it doesn't come up in capacity reviews, and the official docs more or less tell you to leave it alone:

> This setting controls how frequently Kafka adds entries to its offset index and, conditionally, to its time index. The default setting ensures that we index a message roughly every 4096 bytes. More frequent indexing allows reads to jump closer to the exact position in the log but results in larger index files. **You probably don't need to change this.**

The last sentence is right. One of the others isn't, at least not the way it reads. And "you don't need to change it" isn't the same as "you don't need to understand it", because the index this config tunes sits on the path of **every fetch your cluster serves**. Every consumer poll, every follower replicating a partition, every rewind to yesterday: each one starts with an offset-index lookup.

So this post is about that structure. What the offset index is, how a lookup works, what `index.interval.bytes` really changes (I turned it all the way down to 1 and all the way up to 1 MB), what it costs you, and where it starts to bite as partition counts and traffic grow.

Here's a teaser. At 1, the smallest non-zero value (0 is allowed too, and does the same), I got an index that was **byte-for-byte identical** to the default. By the end of this post that'll be obvious.

## Every fetch goes through the index

Start with why this matters at all. When a broker serves a fetch, whether from a consumer or from a follower, it has to turn "give me offset N" into "start reading this file at byte P". That translation happens in `LogSegment.read`, and the first thing it does is:

```java
LogOffsetPosition startOffsetAndSize = translateOffset(startOffset);
```

There's no cache of "where the last fetch ended" in front of it. Every fetch request, for every partition in it, from every follower and every consumer, pays for one lookup. The index is how that stays cheap, and `index.interval.bytes` is the knob that says how dense it is.

So what is "it"?

## The log has no table of contents

A quick recap from last time. A partition is a directory, and the directory is a list of **segments**. Each segment is a set of files that share one name, the **base offset** (the first offset the segment holds), zero-padded to 20 digits:

```
00000000000000004740.log         the records: batches back to back, nothing between them
00000000000000004740.index       offset    -> byte position   (8-byte entries)
00000000000000004740.timeindex   timestamp -> offset          (12-byte entries)
```

The filename *is* the first lookup. To find the segment for offset 4930, take the greatest base offset ≤ 4930 from an in-memory sorted map (`LogSegments.floorSegment`). No file gets opened.

The second lookup is the hard one. Inside the `.log` there's no framing, no separator and no directory. Each batch starts with a 61-byte header, and the `Length` field at byte 8 is the only way to find the next one: the next batch starts `12 + Length` bytes later. To reach batch *n+1* you have to parse batch *n*. On its own a 1 GB segment can only be read front to back.

<!-- DIAGRAM: .log as back-to-back batches, with 12 + Length stride arrows -->

Without an index, a consumer asking for an offset near the end of a 1 GB segment would make the broker walk every batch header in the file. That's the problem the `.index` file solves.

## The index, byte by byte

Here's a complete rolled index file. This is the whole thing, all 24 bytes:

```
$ xxd -g4 -c8 00000000000000000316.index
00000000: 0000009d 00003fde
00000008: 000000ec 00007fbc
00000010: 0000013b 0000bf9a
```

Each entry is two big-endian `int32`s, a **relative offset** and a **file position** (`OffsetIndex.ENTRY_SIZE = 8`):

```
relative  position        absolute (base 316)
   157     16350    ->     473 at byte 16350
   236     32700    ->     552 at byte 32700
   315     49050    ->     631 at byte 49050
```

Two details, each one a design decision.

**Offsets are relative, and that's the 8-byte trick.** An offset is an `int64`, but the index stores it minus the segment's base offset, so it fits in 4 bytes (`AbstractIndex.toRelative`), and the base gets added back on read. That keeps each entry at 8 bytes instead of 12. It also means the bytes mean nothing without the filename. Here's the first entry of a different segment's index:

```
$ xxd -g4 -c8 -l8 00000000000000004740.index
00000000: 0000009d 00003fde
```

Same 8 bytes. In segment 316 they mean offset 473, and in segment 4740 they mean offset 4897.

**Each entry names a batch's *last* offset and points at that batch's *start*.** The batch at byte 16350 holds 395–473, and the entry says 473. That comes back later in this post as a real quirk.

## How a lookup works

The whole lookup is in `LogSegment.translateOffset`, and it's two lines that do two different things:

```java
OffsetPosition mapping = offsetIndex().lookup(offset);
return log.searchForOffsetFromPosition(offset, Math.max(mapping.position(), startingFilePosition));
```

**Phase 1:** binary search the index for the largest entry ≤ the target. That gives a starting byte position. If no entry qualifies, start at byte 0.

**Phase 2:** from there, walk forward over batch *headers*, jumping each payload using `Length`, until you reach a batch whose last offset is ≥ the target (`FileRecords.searchForOffsetFromPosition`).

Here it is against a real segment. Segment `…4740` holds offsets 4740–4999 in four batches, and a consumer wants offset 4930:

```
index (absolute):  4897 → 16350    4976 → 32700    4999 → 49050

phase 1:  largest entry ≤ 4930 is 4897           → start at byte 16350
phase 2:  byte 16350  batch 4819–4897  last < 4930 → skip (jump 16350 bytes)
          byte 32700  batch 4898–4976  last ≥ 4930 → HIT
```

One binary search over three entries, two 61-byte header reads, done.

This shows exactly where `index.interval.bytes` fits. **Phase 1 is cheap and roughly fixed. Phase 2 is the variable cost, and the index's density decides how long it is.** A denser index means phase 1 lands closer to the target and phase 2 has less to walk. A sparser one means a longer walk. That's the whole trade the config is making.

Note that the lookup returns the batch, not the record: the consumer gets all of 4898–4976 and drops what it didn't ask for ([more on that last time](/posts/kafka/batch-is-the-unit/#the-consumer-is-handed-the-loaf)).

## What the config actually does

The docs say "index a message roughly every 4096 bytes." Here's the code that writes index entries, from `LogSegment.append`:

```java
if (bytesSinceLastIndexEntry > indexIntervalBytes) {
    offsetIndex().append(batchLastOffset, physicalPosition);
    timeIndex().maybeAppend(maxTimestampSoFar(), shallowOffsetOfMaxTimestampSoFar());
    bytesSinceLastIndexEntry = 0;
}
var sizeInBytes = batch.sizeInBytes();
physicalPosition += sizeInBytes;
bytesSinceLastIndexEntry += sizeInBytes;
```

It doesn't index a *message*, and it isn't *every* 4096 bytes. Three things in those lines matter:

1. **The loop runs over batches.** It writes at most one entry per batch, never one per record, so your batch count caps the density. The config can make the index sparser than one entry per batch, but never denser.
2. **The check runs before the increment**, so the first batch of every segment is never indexed. Lookups for offsets before the first entry start at byte 0.
3. **Spacing is measured in bytes, not records.** A topic with large records gets more entries per record than one with small records.

So the real meaning of `index.interval.bytes` is: *add an entry at the next batch boundary once at least this many bytes have gone by since the last one.* It sets a minimum distance, not a spacing.

## Turning the dial from 1 byte to 1 MB

To see what that means, I produced the same 5000 records into four topics, identical except for `index.interval.bytes`, with the same batch layout in every run. Every full batch is 16,350 bytes and each segment holds 4 of them. Then I looked up every offset in every full segment and measured how far phase 2 had to walk:

| `index.interval.bytes` | entries / segment | max bytes scanned | mean bytes scanned |
| --- | --- | --- | --- |
| 1 | 3 | 16,350 | 12,107 |
| 4,096 (default) | 3 | 16,350 | 12,107 |
| 20,000 | 1 | 32,700 | 16,247 |
| 1,048,576 | 0 | 49,050 | 24,525 |

*"Bytes scanned" is how far phase 2 walks: the hit position minus the start position.*

<!-- DIAGRAM/CHART: entries per segment and max scan vs interval — plateau on the left, cliff on the right -->

The table shows three regimes.

**Below the batch size, it's a plateau.** With the interval at 1 or 4096, the counter is already past the interval at the start of every batch after the first, so every batch after the first gets an entry. That's the densest index possible, and setting it to 1 can't add entries that 4096 doesn't already add. That's the teaser explained: the two index files are byte-identical, and they have to be.

**Between the batch size and the segment size, it thins out.** At 20,000, some batches get skipped. I wrote down a prediction for this row before producing anything, by stepping the counter through four 16,350-byte batches:

```
batch  counter at check  > 20000?   action
  1          0             no       counter → 16350
  2      16350             no       counter → 32700
  3      32700             yes      entry (batch 3's last offset → byte 32700), reset, counter → 16350
  4      16350             no
```

That predicts one entry at byte 32,700, and that's what showed up on disk. The quirk from earlier shows up here too: the single entry names batch 3's **last** offset, so any earlier offset in batch 3 is below the entry, can't use it, and falls back to byte 0. The index entry exists, it covers the batch you want, and you still walk the segment from the top.

**Above the segment size, it's a cliff.** At 1 MB on a 64 KB segment, no batch ever crosses the threshold. The index is empty and every lookup is a linear header walk from byte 0. On my toy segment that's 49 KB. On a real 1 GB segment it's a walk across up to a gigabyte of log, one header at a time, on every fetch.

The takeaway that surprised me most: **your producer's batching decides index density more than this config does.** `batch.size`, `linger.ms` and compression decide how many batches land on disk, and the index can't be denser than one entry per batch. On a busy topic with 16 KB batches, the default 4096 is already on the plateau.

## What it costs: the performance model

The design doc says "constant time suffices." Lookup isn't O(1), but the part that touches the log has a bound you can work out.

An entry is written only once *more than* `interval` bytes have passed since the last one, and the check only happens at the start of the next batch. So two consecutive index points are at most `interval` bytes apart, plus the one batch that pushed the counter over:

```
max scan  ≤  min(index.interval.bytes + one batch, segment size)
```

| interval | measured max | bound |
| --- | --- | --- |
| 1 | 16,350 | 16,351 |
| 4,096 | 16,350 | 20,446 |
| 20,000 | 32,700 | 36,350 |
| 1,048,576 | 49,050 | 65,400 (segment cap) |

Every measured max sits under its bound. Note that the bound is **4 KB plus one batch**, not the "a few KB" I claimed in my first post, and a batch can be as large as `max.message.bytes`, about 1 MB by default. In practice the batch size, not the interval, sets the bound.

That sounds worse than it is. Phase 2 reads only 61-byte headers and jumps over the payloads, so "bytes scanned" is distance, not I/O. **The real cost is the number of header hops**, and on a hot partition those pages are usually already in the page cache. The bad case is the reverse of what you'd guess: not big batches, but lots of *tiny* batches under a large interval, which means many hops per lookup.

That's what "constant time suffices" really means. A one-entry-per-record index would need no phase 2, but for a 1 GB segment of small records it would be hundreds of MB and would push everything else out of the page cache. A sparse index stays small enough to stay resident, and the walk it leaves behind is capped by config, however large the partition grows.

### The binary search that isn't textbook

Phase 1 has one more trick. Nearly all lookups come from followers and live consumers asking for the newest offsets, at the tail of the index. Textbook binary search starts in the middle, so every lookup touches a few pages spread across the file, and each time the index grows those pages shift. The ones it shifts onto haven't been read in a long time and may no longer be in the page cache. The comment above `AbstractIndex.warmEntries()` spells out the cost:

> The 1st lookup, after the 1st index entry in page #13 is appended, is likely to have to read page #7 and page #10 from disk (page fault), which can take up to more than a second. In our test, this can cause the at-least-once produce latency to jump to about 1 second from a few ms.

The fix is to search the tail first:

```
if (target > indexEntry[end - N])   // target is in the last N entries
    binarySearch(end - N, end)
else
    binarySearch(begin, end - N)
```

N is `8192 / entrySize()`, so the "warm section" is the last 1024 entries, 8 KB that every tail lookup touches and therefore keeps in memory.

Even that comment falls for the docs' framing. It says the warm section covers "about 4MB ... log messages", which assumes one entry every 4 KB. As we've seen, it's one entry per batch, so with 16 KB batches those 1024 entries cover about 16 MB of log. Consumers within that distance of the tail get the warm path. **A consumer lagging further behind searches index pages nobody else is touching**, and a consumer reading an older segment is using a whole index file nobody else is touching.

## What this means at scale

On one small topic, none of this is visible. It starts to show when you multiply it: thousands of partitions, dozens of consumer groups, replays and backfills. These are the settings involved:

| Config (topic / broker) | Default | What it controls |
| --- | --- | --- |
| `index.interval.bytes` / `log.index.interval.bytes` | 4096 | minimum bytes of log between offset-index entries |
| `segment.bytes` / `log.segment.bytes` | 1 GB | segment roll size |
| `max.message.bytes` | ~1 MB | largest batch, the hidden term in the scan bound |
| producer `batch.size`, `linger.ms`, `compression.type` | 16 KB, 5 ms, none | how many batches exist, which is the real density knob |

And these are the situations where they matter.

**Seek-heavy consumers: replays, rewinds, `offsetsForTimes`.** These are the workloads that land on arbitrary offsets instead of the tail, so they pay the full phase-2 walk. Check your batch size before touching the interval. If batches are already bigger than 4 KB, lowering `index.interval.bytes` does *nothing*: you're on the plateau. It only helps when batches are tiny (low traffic, or `linger.ms=0`), where it adds entries and cuts header hops. Seeks by time go through `.timeindex` first (timestamp → offset) and then do this same offset lookup, so they pay for both.

**Never let the interval approach the segment size.** The index goes empty and every fetch becomes a linear header walk from byte 0. *Measured:* 1,048,576 on a 64 KB segment gave 0 entries. Nobody sets 1 GB on purpose, but a topic with small `segment.bytes` (for fast compaction or retention) and a large copied-in interval can get there without anyone noticing.

**Thousands of partitions: the mmap ceiling.** Each segment's `.index` and `.timeindex` gets its own memory map, so that's **two map areas per segment**. Linux's `vm.max_map_count` defaults to around 65,530, and Kafka's own ops docs warn that 50,000 partitions ≈ 100,000 maps ≈ `OutOfMemoryError (Map failed)`, and that's with a single segment per partition. Anything that multiplies segments per partition, like smaller `segment.bytes` or longer retention, moves you toward that ceiling faster. Your levers are raising `vm.max_map_count`, using fewer and larger segments, or running fewer partitions.

### A tuning checklist

- **Leave `index.interval.bytes` at the default** unless you've measured both tiny batches *and* seek-heavy consumers. On busy topics it's already on the plateau.
- **Tune producer batching first.** It sets index density, compression ratio and the phase-2 bound all at once.
- **Never let the interval approach `segment.bytes`.** An empty index turns every fetch into a scan.
- **Count your maps.** Partitions × segments × 2 against `vm.max_map_count`, and watch it as retention and partition counts grow.

## You can read this yourself

The formats are simple enough that a lookup fits in a screenful of Python using only the standard library. This is trimmed from the script that produced every number above:

```python
import bisect, struct

HEADER = struct.Struct(">qiibIhiqqqhii")   # the 61-byte batch header
ENTRY  = struct.Struct(">ii")              # relative offset, position

def read_index(path, base):
    with open(path, "rb") as f:
        while (buf := f.read(8)) and len(buf) == 8:
            rel, pos = ENTRY.unpack(buf)
            if pos == 0: return            # preallocated zero tail
            yield base + rel, pos

def lookup(log, index, base, target):
    entries = list(read_index(index, base))
    i = bisect.bisect_right([o for o, _ in entries], target) - 1   # phase 1
    pos = entries[i][1] if i >= 0 else 0
    with open(log, "rb") as f:                                     # phase 2
        f.seek(pos)
        while (buf := f.read(61)) and len(buf) == 61:
            base_offset, length, *_, last_delta = HEADER.unpack(buf)[:7]
            if target <= base_offset + last_delta:
                return pos
            pos += 12 + length             # skip the payload
            f.seek(pos)
```

Point it at any rolled segment in your own log directory and it returns the same batch position the broker would.

## Takeaways

1. **Every fetch starts with an offset-index lookup**: a binary search, then a short walk over batch headers. `index.interval.bytes` sets how long that walk can be.
2. **The config sets a minimum distance, not a spacing.** The index is per-batch, so producer batching caps its density. Lowering the interval below your batch size changes nothing: I set it to 1 and got a byte-identical index.
3. **The cost is bounded:** at most `min(interval + one batch, segment size)` of log per lookup, crossed header by header. Big batches stretch the bound; tiny batches add hops.
4. **Tail reads are the cheap path**, by design, via the warm-section search. Lagging consumers read index pages nobody else is keeping warm.
5. **At scale, the index settings that bite** are mmap counts (`vm.max_map_count`) and an interval that's too large. The default interval itself is almost never the problem, but now you know why.

---

*Measured against Apache Kafka trunk (4.5.0-SNAPSHOT, `6e4bc7d5c3`) on a single-node KRaft broker. Source references are to `storage/src/main/java/org/apache/kafka/storage/internals/log/`. Index files are dumped with `xxd`, and lookups are replayed with a stdlib Python reader over every offset in every segment.*
