package com.zthcpa.command.persistence.run;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.persistence.support.PostgresJson;
import com.zthcpa.command.persistence.event.RunEventEntity;
import com.zthcpa.command.persistence.event.TaskEventEntity;
import com.zthcpa.command.persistence.step.RunStepEntity;
import com.zthcpa.command.persistence.task.TaskExecutionEntity;
import com.zthcpa.command.run.PipelineRunSubmissionPlan;
import com.zthcpa.command.run.PipelineExecutionIdentifiers;
import com.zthcpa.command.run.InputTemplateResolver;
import com.zthcpa.command.run.TaskStatus;
import jakarta.persistence.EntityManager;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;
import java.util.LinkedHashMap;
import java.util.List;

@Transactional
public class CleanStepCoordinatorRepository {
    private final EntityManager entityManager;
    private final ObjectMapper mapper;

    public CleanStepCoordinatorRepository(EntityManager entityManager, ObjectMapper mapper) {
        this.entityManager = entityManager;
        this.mapper = mapper;
    }

    public boolean completeAndAdvance(String taskId, String workerId, TaskStatus status,
                                      Map<String, Object> output, Map<String, Object> error,
                                      CleanNextStepPlan nextStep) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        if (status != TaskStatus.SUCCEEDED) {
            throw new IllegalArgumentException("Only successful tasks can advance to a next step");
        }
        Object stepId = completeTask(taskId, workerId, output);
        if (stepId == null) return false;
        Object runId = runId(stepId);
        markStepSucceeded(stepId);
        if (nextStep == null) {
            markRunSucceeded(runId);
            appendRunEvent(runId, stepId, "run.succeeded", Map.of());
        } else {
            persistNextStep(runId.toString(), nextStep);
            appendRunEvent(runId, stepId, "step.advanced", Map.of("next_step_id", nextStep.stepId()));
        }
        appendTaskEvent(taskId, "task.succeeded", output);
        return true;
    }

    public boolean completeAndAdvance(String taskId, String workerId, Map<String, Object> output,
                                      PipelineRunSubmissionPlan plan) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        if (plan == null) throw new IllegalArgumentException("Pipeline submission plan must not be null");
        Object stepId = completeTask(taskId, workerId, output);
        if (stepId == null) return false;
        Object[] current = (Object[]) entityManager.createNativeQuery(
                        "SELECT run_id, step_index FROM command_runtime.run_steps WHERE id=:id")
                .setParameter("id", stepId).getSingleResult();
        if (!plan.runId().equals(current[0].toString())) {
            throw new IllegalArgumentException("Frozen submission plan belongs to another run");
        }
        markStepSucceeded(stepId);
        CleanNextStepPlan next = nextStep(plan, Integer.parseInt(current[1].toString()));
        if (next == null) {
            markRunSucceeded(current[0]);
            appendRunEvent(current[0], stepId, "run.succeeded", Map.of());
        } else {
            persistNextStep(current[0].toString(), next);
            appendRunEvent(current[0], stepId, "step.advanced", Map.of("next_step_id", next.stepId()));
        }
        appendTaskEvent(taskId, "task.succeeded", output);
        return true;
    }

    /**
     * Advances a persisted pipeline without passing an in-memory submission plan
     * through the scheduler. The immutable definition snapshot is the source of
     * the next step and its input mapping.
     */
    public boolean completeAndAdvance(String taskId, String workerId, Map<String, Object> output) {
        require(taskId, "Task id");
        require(workerId, "Worker id");
        Object stepId = completeTask(taskId, workerId, output);
        if (stepId == null) return false;

        Object[] current = (Object[]) entityManager.createNativeQuery(
                        "SELECT run_id, step_index FROM command_runtime.run_steps WHERE id=:id")
                .setParameter("id", stepId).getSingleResult();
        String runId = current[0].toString();
        int currentIndex = Integer.parseInt(current[1].toString());
        markStepSucceeded(stepId);

        Map<String, Object> runInput = jsonObject(entityManager.createNativeQuery(
                        "SELECT input::text FROM command_runtime.runs WHERE id=:id")
                .setParameter("id", runId).getSingleResult());
        Map<String, Map<String, Object>> stepOutputs = completedOutputs(runId);
        Map<String, Object> pipeline = jsonObject(entityManager.createNativeQuery("""
                SELECT document::text FROM command_runtime.run_definition_snapshots
                WHERE run_id=:runId AND definition_kind='capability_pipeline'
                """).setParameter("runId", runId).getSingleResult());
        List<?> steps = (List<?>) pipeline.get("steps");
        if (currentIndex + 1 >= steps.size()) {
            markRunSucceeded(runId);
            appendRunEvent(runId, stepId, "run.succeeded", Map.of());
        } else {
            Map<?, ?> next = (Map<?, ?>) steps.get(currentIndex + 1);
            Map<?, ?> reference = (Map<?, ?>) next.get("definition_ref");
            Map<String, Object> template = next.get("input") instanceof Map<?, ?> value
                    ? toMap(value) : Map.of();
            Map<String, Object> input = InputTemplateResolver.resolve(template, runInput, stepOutputs);
            String nextStepId = PipelineExecutionIdentifiers.stepId(runId, currentIndex + 1);
            String nextTaskId = PipelineExecutionIdentifiers.taskId(runId, currentIndex + 1);
            CleanNextStepPlan plan = new CleanNextStepPlan(
                    nextStepId, currentIndex + 1,
                    next.get("id").toString(),
                    new com.zthcpa.command.contract.DefinitionKey(
                            com.zthcpa.command.contract.DefinitionKind.TOOL,
                            reference.get("id").toString(), ((Number) reference.get("version")).intValue()),
                    input, nextTaskId, 1);
            persistNextStep(runId, plan);
            appendRunEvent(runId, stepId, "step.advanced", Map.of("next_step_id", plan.stepId()));
        }
        appendTaskEvent(taskId, "task.succeeded", output);
        return true;
    }

    public boolean isPipelineTask(String taskId) {
        require(taskId, "Task id");
        Number count = (Number) entityManager.createNativeQuery("""
                SELECT COUNT(*)
                FROM command_runtime.task_executions t
                JOIN command_runtime.run_steps s ON s.id=t.step_id
                JOIN command_runtime.run_definition_snapshots d ON d.run_id=s.run_id
                WHERE t.id=:taskId AND d.definition_kind='capability_pipeline'
                """).setParameter("taskId", taskId).getSingleResult();
        return count.longValue() > 0;
    }

    private Map<String, Map<String, Object>> completedOutputs(String runId) {
        @SuppressWarnings("unchecked")
        List<Object[]> rows = entityManager.createNativeQuery("""
                SELECT s.step_key, t.output::text
                FROM command_runtime.run_steps s
                JOIN command_runtime.task_executions t ON t.step_id=s.id
                WHERE s.run_id=:runId AND t.status='succeeded'
                ORDER BY s.step_index, t.attempt
                """).setParameter("runId", runId).getResultList();
        Map<String, Map<String, Object>> result = new LinkedHashMap<>();
        for (Object[] row : rows) result.put(row[0].toString(), jsonObject(row[1]));
        return result;
    }

    private Map<String, Object> jsonObject(Object value) {
        try {
            return mapper.readValue(value.toString(), mapper.getTypeFactory()
                    .constructMapType(Map.class, String.class, Object.class));
        } catch (Exception exception) {
            throw new IllegalStateException("Stored JSON object is invalid", exception);
        }
    }

    private Map<String, Object> toMap(Map<?, ?> source) {
        Map<String, Object> result = new LinkedHashMap<>();
        source.forEach((key, value) -> result.put(key.toString(), value));
        return result;
    }

    private Object completeTask(String taskId, String workerId, Map<String, Object> output) {
        int updated = entityManager.createNativeQuery("""
                UPDATE command_runtime.task_executions
                SET status='succeeded', output=CAST(:output AS jsonb), finished_at=CURRENT_TIMESTAMP
                WHERE id=:taskId AND worker_id=:workerId AND status='running'
                """).setParameter("output", PostgresJson.write(mapper, output == null ? Map.of() : output))
                .setParameter("taskId", taskId).setParameter("workerId", workerId).executeUpdate();
        if (updated != 1) return null;
        return entityManager.createNativeQuery("SELECT step_id FROM command_runtime.task_executions WHERE id=:id")
                .setParameter("id", taskId).getSingleResult();
    }

    private Object runId(Object stepId) {
        return entityManager.createNativeQuery("SELECT run_id FROM command_runtime.run_steps WHERE id=:id")
                .setParameter("id", stepId).getSingleResult();
    }

    private void markStepSucceeded(Object stepId) {
        entityManager.createNativeQuery("UPDATE command_runtime.run_steps SET status='succeeded', finished_at=CURRENT_TIMESTAMP WHERE id=:id")
                .setParameter("id", stepId).executeUpdate();
    }

    private void markRunSucceeded(Object runId) {
        entityManager.createNativeQuery("UPDATE command_runtime.runs SET status='succeeded', finished_at=CURRENT_TIMESTAMP WHERE id=:id AND status='running'")
                .setParameter("id", runId).executeUpdate();
    }

    private void persistNextStep(String runId, CleanNextStepPlan next) {
        entityManager.persist(new RunStepEntity(next.stepId(), runId, next.stepIndex(), next.stepKey(),
                next.tool().id(), next.tool().version(), next.input()));
        entityManager.persist(new TaskExecutionEntity(next.taskId(), next.stepId(), next.maxAttempts(), next.input()));
        appendTaskEvent(next.taskId(), "task.queued", Map.of("step_index", next.stepIndex()));
    }

    private void appendTaskEvent(String taskId, String kind, Map<String, Object> detail) {
        entityManager.persist(new TaskEventEntity(taskId, kind, detail == null ? Map.of() : detail));
    }

    private void appendRunEvent(Object runId, Object stepId, String kind, Map<String, Object> detail) {
        entityManager.persist(new RunEventEntity(runId.toString(), stepId.toString(), kind, "system", detail));
    }

    private CleanNextStepPlan nextStep(PipelineRunSubmissionPlan plan, int currentIndex) {
        int nextIndex = currentIndex + 1;
        if (nextIndex >= plan.execution().steps().size()) return null;
        var step = plan.execution().steps().get(nextIndex);
        return new CleanNextStepPlan(PipelineExecutionIdentifiers.stepId(plan.runId(), nextIndex),
                nextIndex, step.id(), step.tool(),
                step.input(), plan.taskIds().get(nextIndex), step.maxAttempts());
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " must not be blank");
    }
}
