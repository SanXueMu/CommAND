package com.zthcpa.command.persistence.event;

import java.util.List;
import java.util.Map;

public interface CleanEventRepository {
    long appendRunEvent(String runId, String stepId, String kind, String actor, Map<String, Object> detail);

    long appendTaskEvent(String taskId, String kind, Map<String, Object> detail);

    List<CleanRunEvent> listRunEvents(String runId, long afterId, int limit);

    List<CleanTaskEvent> listTaskEvents(String taskId, long afterId, int limit);
}
