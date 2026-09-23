package com.zthcpa.command.api;

import com.zthcpa.command.contract.DefinitionRegistry;
import com.zthcpa.command.persistence.CleanRunQueryRepository;
import com.zthcpa.command.persistence.CleanRunSnapshot;
import com.zthcpa.command.persistence.CleanRunSubmissionRepository;
import com.zthcpa.command.persistence.CleanStepSnapshot;
import com.zthcpa.command.persistence.CleanTaskSnapshot;
import com.zthcpa.command.run.PipelineRunSubmissionPlan;
import com.zthcpa.command.run.RunSubmissionException;
import com.zthcpa.command.run.RunSubmissionPlanner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.UUID;

import static com.zthcpa.command.api.RunApiModels.RunResponse;
import static com.zthcpa.command.api.RunApiModels.StepResponse;
import static com.zthcpa.command.api.RunApiModels.SubmitRunResponse;
import static com.zthcpa.command.api.RunApiModels.TaskResponse;

@Service
@Profile("database")
public final class RunApplicationService {
    private final DefinitionRegistry definitions;
    private final CleanRunSubmissionRepository submissions;
    private final CleanRunQueryRepository queries;

    public RunApplicationService(
            DefinitionRegistry definitions,
            CleanRunSubmissionRepository submissions,
            CleanRunQueryRepository queries
    ) {
        this.definitions = definitions;
        this.submissions = submissions;
        this.queries = queries;
    }

    public SubmitRunResponse submit(String workflowId, Integer workflowVersion, Map<String, Object> input) {
        PipelineRunSubmissionPlan plan = new RunSubmissionPlanner(
                definitions,
                () -> UUID.randomUUID().toString()
        ).planPipeline(workflowId, workflowVersion, input == null ? Map.of() : input);
        submissions.submit(plan);
        return new SubmitRunResponse(plan.runId(), "running", plan.firstTaskId());
    }

    public RunResponse get(String runId) {
        CleanRunSnapshot snapshot = queries.get(runId);
        if (snapshot == null) {
            return null;
        }
        return new RunResponse(
                snapshot.id(),
                snapshot.workflowId(),
                snapshot.workflowVersion(),
                snapshot.status(),
                snapshot.createdAt(),
                snapshot.finishedAt(),
                snapshot.steps().stream().map(this::toStep).toList()
        );
    }

    private StepResponse toStep(CleanStepSnapshot step) {
        CleanTaskSnapshot task = step.latestTask();
        return new StepResponse(step.index(), step.status(), task == null ? null : new TaskResponse(
                task.attempt(), task.maxAttempts(), task.status(), task.startedAt(), task.finishedAt()
        ));
    }
}
