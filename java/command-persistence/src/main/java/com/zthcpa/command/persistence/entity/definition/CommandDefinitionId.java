package com.zthcpa.command.persistence.entity.definition;

import jakarta.persistence.Embeddable;

import java.io.Serializable;
import java.util.Objects;

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

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof CommandDefinitionId that)) {
            return false;
        }
        return definitionVersion == that.definitionVersion
                && Objects.equals(kind, that.kind)
                && Objects.equals(id, that.id);
    }

    @Override
    public int hashCode() {
        return Objects.hash(kind, id, definitionVersion);
    }
}
