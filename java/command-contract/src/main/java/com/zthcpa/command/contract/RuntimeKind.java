package com.zthcpa.command.contract;

public enum RuntimeKind {
    INPROC("inproc"),
    SUBPROCESS("subprocess"),
    HTTP("http");

    private final String value;

    RuntimeKind(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }

    public static RuntimeKind fromValue(String value) {
        for (RuntimeKind kind : values()) {
            if (kind.value.equals(value)) {
                return kind;
            }
        }
        throw new IllegalArgumentException("Unknown runtime kind: " + value);
    }
}
