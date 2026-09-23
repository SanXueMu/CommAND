package com.zthcpa.command.runtime;

import java.time.Instant;

@FunctionalInterface
public interface StaleTaskRecoveryPort {
    int recoverStaleTasks(Instant staleBefore, int limit);
}
