package com.zthcpa.command.persistence.entity.definition;

import jakarta.persistence.Embeddable;

import java.io.Serializable;

@Embeddable
public class CommandDefinitionId implements Serializable {
    private String kind;
    private String id;
    private int definitionVersion;

    protected CommandDefinitionId() {
    }

    public CommandDefinitionId(String kind, String id, int definitionVersion) {
        this.kind = kind;
        this.id = id;
        this.definitionVersion = definitionVersion;
    }

    public String getKind() {
        return kind;
    }

    public String getId() {
        return id;
    }

    public int getDefinitionVersion() {
        return definitionVersion;
    }
}
