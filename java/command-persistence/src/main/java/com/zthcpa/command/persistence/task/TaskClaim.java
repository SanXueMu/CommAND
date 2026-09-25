package com.zthcpa.command.persistence.task;

public record TaskClaim(String workerId) {
    public TaskClaim {
        if (workerId == null || workerId.isBlank()) {
            throw new IllegalArgumentException("Worker id must not be blank");
        }
    }
}
