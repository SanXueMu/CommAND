package com.zthcpa.command.persistence;

public record TaskClaim(String workerId) {
    public TaskClaim {
        if (workerId == null || workerId.isBlank()) {
            throw new IllegalArgumentException("Worker id must not be blank");
        }
    }
}
