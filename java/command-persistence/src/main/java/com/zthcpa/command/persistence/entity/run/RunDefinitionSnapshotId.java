package com.zthcpa.command.persistence.entity.run;

import jakarta.persistence.Embeddable;

import java.io.Serializable;

@Embeddable
public class RunDefinitionSnapshotId implements Serializable {
    private String runId;
    private String definitionKind;
    private String definitionId;
    private int definitionVersion;

    protected RunDefinitionSnapshotId() {
    }
}
