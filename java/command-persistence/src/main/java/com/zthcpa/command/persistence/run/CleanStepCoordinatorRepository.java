package com.zthcpa.command.persistence.run;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.persistence.support.PostgresJson;
import com.zthcpa.command.persistence.event.RunEventEntity;
import com.zthcpa.command.persistence.event.TaskEventEntity;
import com.zthcpa.command.persistence.step.RunStepEntity;
import com.zthcpa.command.persistence.task.TaskExecutionEntity;
import com.zthcpa.command.run.PipelineRunSubmissionPlan;
import com.zthcpa.command.run.TaskStatus;
import jakarta.persistence.EntityManager;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;

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
        return new CleanNextStepPlan(plan.runId() + ":step:" + nextIndex, nextIndex, step.id(), step.tool(),
                step.input(), plan.taskIds().get(nextIndex), step.maxAttempts());
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " must not be blank");
    }
}
