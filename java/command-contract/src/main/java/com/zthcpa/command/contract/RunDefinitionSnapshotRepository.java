package com.zthcpa.command.contract;

import java.util.List;

public interface RunDefinitionSnapshotRepository {
    void saveIfAbsent(String runId, DefinitionDocument definition);

    List<RunDefinitionSnapshot> listByRun(String runId);
}
