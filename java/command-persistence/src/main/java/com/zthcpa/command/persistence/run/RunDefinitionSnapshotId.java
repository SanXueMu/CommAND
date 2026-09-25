package com.zthcpa.command.persistence.run;

import jakarta.persistence.Embeddable;

import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class RunDefinitionSnapshotId implements Serializable {
    private String runId;
    private String definitionKind;
    private String definitionId;
    private int definitionVersion;

    protected RunDefinitionSnapshotId() {
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof RunDefinitionSnapshotId that)) {
            return false;
        }
        return definitionVersion == that.definitionVersion
                && Objects.equals(runId, that.runId)
                && Objects.equals(definitionKind, that.definitionKind)
                && Objects.equals(definitionId, that.definitionId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(runId, definitionKind, definitionId, definitionVersion);
    }
}
