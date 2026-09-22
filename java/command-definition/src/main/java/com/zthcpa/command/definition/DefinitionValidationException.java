package com.zthcpa.command.definition;

import java.util.List;

public final class DefinitionValidationException extends RuntimeException {
    private final List<String> errors;

    public DefinitionValidationException(List<String> errors) {
        super(String.join("; ", errors));
        this.errors = List.copyOf(errors);
    }

    public List<String> errors() {
        return errors;
    }
}
