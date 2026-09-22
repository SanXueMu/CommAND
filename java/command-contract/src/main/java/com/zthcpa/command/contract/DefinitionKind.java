package com.zthcpa.command.contract;

public enum DefinitionKind {
    TOOL("tool"),
    CAPABILITY_PIPELINE("capability_pipeline"),
    WORKFLOW("workflow"),
    WORKBENCH_VIEW("workbench_view");

    private final String value;

    DefinitionKind(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }

    public static DefinitionKind fromValue(String value) {
        for (DefinitionKind kind : values()) {
            if (kind.value.equals(value)) {
                return kind;
            }
        }
        throw new IllegalArgumentException("Unknown definition kind: " + value);
    }
}
