package com.zthcpa.command.persistence.support;

import com.zthcpa.command.run.RunStatus;
import com.zthcpa.command.run.TaskStatus;

public final class StatusValueMapper {
    private StatusValueMapper() {
    }

    public static String toDatabase(RunStatus status) {
        return status.name().toLowerCase();
    }

    public static RunStatus toRunStatus(String value) {
        return RunStatus.valueOf(value.toUpperCase());
    }

    public static String toDatabase(TaskStatus status) {
        return status.name().toLowerCase();
    }

    public static TaskStatus toTaskStatus(String value) {
        return TaskStatus.valueOf(value.toUpperCase());
    }
}
