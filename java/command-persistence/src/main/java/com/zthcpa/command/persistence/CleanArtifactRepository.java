package com.zthcpa.command.persistence;

import java.util.List;
import java.util.Map;

public interface CleanArtifactRepository {
    boolean register(CleanArtifact artifact);

    CleanArtifact get(String artifactId);

    List<CleanArtifact> listByRun(String runId, int offset, int limit);

    List<CleanArtifact> listByStep(String stepId, int offset, int limit);

    boolean delete(String artifactId);
}
