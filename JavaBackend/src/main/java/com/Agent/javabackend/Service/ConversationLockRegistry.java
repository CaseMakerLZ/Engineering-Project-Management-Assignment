package com.Agent.javabackend.Service;

import org.springframework.stereotype.Component;

import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.Supplier;

/**
 * 只串行化同一个对话的提交，不再锁住整个 ConversationService。
 *
 * 引用计数在 ConcurrentHashMap.compute 中增减，最后一个等待者离开时移除条目，
 * 因此不会为每个 UUID 永久保留一把锁。不同对话、不同用户之间可以并行提交。
 */
@Component
public class ConversationLockRegistry {
    private final ConcurrentHashMap<String, LockEntry> locks = new ConcurrentHashMap<>();

    public <T> T withLock(String conversationId, Supplier<T> action) {
        String key = Objects.requireNonNull(conversationId, "conversationId");
        LockEntry entry = locks.compute(key, (ignored, existing) -> {
            LockEntry result = existing == null ? new LockEntry() : existing;
            result.references.incrementAndGet();
            return result;
        });

        entry.lock.lock();
        try {
            return action.get();
        } finally {
            entry.lock.unlock();
            locks.compute(key, (ignored, existing) -> {
                if (existing != entry) {
                    return existing;
                }
                return entry.references.decrementAndGet() == 0 ? null : existing;
            });
        }
    }

    int trackedLocks() {
        return locks.size();
    }

    private static final class LockEntry {
        private final ReentrantLock lock = new ReentrantLock();
        private final AtomicInteger references = new AtomicInteger();
    }
}
