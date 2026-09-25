package com.zthcpa.command.runtime.recovery;

import java.time.Instant;

@FunctionalInterface
public interface StaleTaskRecoveryPort {
    int recoverStaleTasks(Instant staleBefore, int limit);
}
