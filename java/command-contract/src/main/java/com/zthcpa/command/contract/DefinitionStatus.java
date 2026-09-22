package com.zthcpa.command.contract;

public enum DefinitionStatus {
    DRAFT("draft"),
    ACTIVE("active"),
    DEPRECATED("deprecated"),
    RETIRED("retired");

    private final String value;

    DefinitionStatus(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }

    public static DefinitionStatus fromValue(String value) {
        for (DefinitionStatus status : values()) {
            if (status.value.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown definition status: " + value);
    }
}
