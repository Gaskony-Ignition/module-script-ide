package com.gaskony.scriptide.gateway.lang;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * {@link TtlCache} — the thing that keeps {@link SdkTagBrowser} and
 * {@link SdkDbSchema} off the completion thread. A same-thread executor
 * stands in for the real background pool here: what matters for this class's
 * OWN contract is call counts and timing, not real concurrency, and a fixed
 * clock means no sleep is needed anywhere in this test.
 */
class TtlCacheTest {

    @Test
    @DisplayName("a miss schedules the loader but answers nothing for that call")
    void missAnswersEmptyAndSchedulesLoad() {
        AtomicLong clock = new AtomicLong(0);
        AtomicInteger calls = new AtomicInteger();
        TtlCache<String> cache = new TtlCache<>(60_000, 100, clock::get, Runnable::run);

        Optional<String> first = cache.get("k", () -> {
            calls.incrementAndGet();
            return "v1";
        });

        assertThat(first).isEmpty();
        assertThat(calls.get()).isEqualTo(1);
    }

    @Test
    @DisplayName("a hit within the TTL does not re-call the loader")
    void hitDoesNotReCallLoader() {
        AtomicLong clock = new AtomicLong(0);
        AtomicInteger calls = new AtomicInteger();
        TtlCache<String> cache = new TtlCache<>(60_000, 100, clock::get, Runnable::run);

        // First call is a miss - populates the entry via the same-thread executor.
        cache.get("k", () -> {
            calls.incrementAndGet();
            return "v1";
        });
        clock.addAndGet(1_000);   // still well inside the 60s TTL

        Optional<String> second = cache.get("k", () -> {
            calls.incrementAndGet();
            return "v2";
        });

        assertThat(second).contains("v1");
        assertThat(calls.get()).isEqualTo(1);
    }

    @Test
    @DisplayName("an expired entry re-calls the loader")
    void expiredEntryReCallsLoader() {
        AtomicLong clock = new AtomicLong(0);
        AtomicInteger calls = new AtomicInteger();
        TtlCache<String> cache = new TtlCache<>(60_000, 100, clock::get, Runnable::run);

        cache.get("k", () -> {
            calls.incrementAndGet();
            return "v1";
        });
        clock.addAndGet(60_001);   // past the TTL

        // THIS call is still the miss/expiry that discovers the entry is
        // stale — it schedules the reload and, by contract, answers nothing
        // for its own keystroke even though the executor here happens to run
        // it inline (see missAnswersEmptyAndSchedulesLoad: a miss NEVER
        // returns the freshly computed value on the call that triggered it).
        Optional<String> atExpiry = cache.get("k", () -> {
            calls.incrementAndGet();
            return "v2";
        });
        assertThat(atExpiry).isEmpty();
        assertThat(calls.get()).isEqualTo(2);

        // The NEXT call sees the refreshed entry as an ordinary hit.
        Optional<String> afterRefresh = cache.get("k", () -> {
            calls.incrementAndGet();
            return "v3";
        });
        assertThat(afterRefresh).contains("v2");
        assertThat(calls.get()).isEqualTo(2);
    }

    @Test
    @DisplayName("a key already being refreshed is not queued a second time")
    void refreshInFlightIsNotDuplicated() {
        AtomicLong clock = new AtomicLong(0);
        AtomicInteger calls = new AtomicInteger();
        AtomicInteger scheduled = new AtomicInteger();
        // An executor that records how many refreshes were scheduled without
        // running them, so both get() calls below race against the SAME
        // still-pending refresh rather than each completing before the next starts.
        TtlCache<String> cache = new TtlCache<>(60_000, 100, clock::get, r -> {
            scheduled.incrementAndGet();
            r.run();
        });

        cache.get("k", () -> {
            calls.incrementAndGet();
            return "v1";
        });
        // A second miss on the same key before any TTL has passed would only
        // happen if the entry never landed; here it lands synchronously, so
        // this call is a HIT and must not schedule again.
        cache.get("k", () -> {
            calls.incrementAndGet();
            return "v2";
        });

        assertThat(scheduled.get()).isEqualTo(1);
        assertThat(calls.get()).isEqualTo(1);
    }

    @Test
    @DisplayName("the cache holds at most maxEntries, evicting the least recently used")
    void evictsBeyondCap() {
        AtomicLong clock = new AtomicLong(0);
        TtlCache<String> cache = new TtlCache<>(60_000, 2, clock::get, Runnable::run);

        cache.get("a", () -> "va");
        cache.get("b", () -> "vb");
        // Touch "a" so "b" becomes the least recently used.
        cache.get("a", () -> "should-not-run");
        cache.get("c", () -> "vc");   // pushes the cap; "b" should be evicted

        AtomicInteger reloadsOfB = new AtomicInteger();
        Optional<String> b = cache.get("b", () -> {
            reloadsOfB.incrementAndGet();
            return "vb2";
        });

        assertThat(b).isEmpty();   // evicted, so this is a miss that reschedules
        assertThat(reloadsOfB.get()).isEqualTo(1);
    }
}
