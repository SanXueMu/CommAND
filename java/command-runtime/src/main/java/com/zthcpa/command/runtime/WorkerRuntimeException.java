package com.zthcpa.command.runtime;

public final class WorkerRuntimeException extends RuntimeException {
    public WorkerRuntimeException(String message) {
        super(message);
    }

    public WorkerRuntimeException(String message, Throwable cause) {
        super(message, cause);
    }
}
