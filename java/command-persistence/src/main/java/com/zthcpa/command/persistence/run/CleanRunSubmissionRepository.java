package com.zthcpa.command.persistence.run;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.persistence.step.RunStepEntity;
import com.zthcpa.command.persistence.task.TaskExecutionEntity;
import com.zthcpa.command.run.PipelineRunSubmissionPlan;
import com.zthcpa.command.run.RunSubmissionPlan;
import jakarta.persistence.EntityManager;
import org.springframework.transaction.annotation.Transactional;

@Transactional
public class CleanRunSubmissionRepository {
    private final EntityManager entityManager;

    public CleanRunSubmissionRepository(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    public void submit(RunSubmissionPlan plan) {
        persistRun(plan.runId(), plan.workflow().id(), plan.workflow().version(), plan.input());
        plan.definitions().forEach(definition -> persistSnapshot(plan.runId(), definition));
        var first = plan.firstTask();
        String stepId = plan.runId() + ":step:" + first.stepIndex();
        persistStep(stepId, plan.runId(), first.stepIndex(), first.tool().id(), first.tool().id(),
                first.tool().version(), first.input());
        persistTask(first.handle(), stepId, first.maxAttempts(), first.input());
    }

    public void submit(PipelineRunSubmissionPlan plan) {
        persistRun(plan.runId(), plan.workflow().id(), plan.workflow().version(), plan.input());
        plan.definitions().forEach(definition -> persistSnapshot(plan.runId(), definition));
        var first = plan.execution().steps().get(0);
        String stepId = plan.runId() + ":step:" + first.index();
        persistStep(stepId, plan.runId(), first.index(), first.id(), first.tool().id(),
                first.tool().version(), first.input());
        persistTask(plan.firstTaskId(), stepId, first.maxAttempts(), first.input());
    }

    private void persistRun(String runId, String workflowId, int workflowVersion,
                            java.util.Map<String, Object> input) {
        entityManager.persist(new RunEntity(runId, workflowId, workflowVersion, input));
    }

    private void persistSnapshot(String runId, DefinitionDocument definition) {
        entityManager.persist(new RunDefinitionSnapshotEntity(
                runId,
                definition.key().kind().value(),
                definition.key().id(),
                definition.key().version(),
                definition.schemaVersion(),
                definition.checksum(),
                definition.content()
        ));
    }

    private void persistStep(String stepId, String runId, int index, String stepKey,
                             String definitionId, int definitionVersion,
                             java.util.Map<String, Object> input) {
        entityManager.persist(new RunStepEntity(
                stepId, runId, index, stepKey, definitionId, definitionVersion, input
        ));
    }

    private void persistTask(String taskId, String stepId, int maxAttempts,
                             java.util.Map<String, Object> input) {
        entityManager.persist(new TaskExecutionEntity(taskId, stepId, maxAttempts, input));
    }
}
