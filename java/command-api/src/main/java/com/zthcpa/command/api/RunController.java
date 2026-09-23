package com.zthcpa.command.api;

import com.zthcpa.command.run.RunSubmissionException;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static com.zthcpa.command.api.RunApiModels.ErrorResponse;
import static com.zthcpa.command.api.RunApiModels.RunResponse;
import static com.zthcpa.command.api.RunApiModels.SubmitRunRequest;
import static com.zthcpa.command.api.RunApiModels.SubmitRunResponse;

@RestController
@Profile("database")
@RequestMapping("/api/runs")
public final class RunController {
    private final RunApplicationService service;

    public RunController(RunApplicationService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<SubmitRunResponse> submit(@RequestBody SubmitRunRequest request) {
        if (request == null || request.workflowId() == null || request.workflowId().isBlank()) {
            throw new RunSubmissionException("workflowId must not be blank");
        }
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.submit(request.workflowId(), request.workflowVersion(), request.input()));
    }

    @GetMapping("/{runId}")
    public ResponseEntity<RunResponse> get(@PathVariable String runId) {
        RunResponse response = service.get(runId);
        return response == null ? ResponseEntity.notFound().build() : ResponseEntity.ok(response);
    }

    @ExceptionHandler(RunSubmissionException.class)
    ResponseEntity<ErrorResponse> handleSubmission(RunSubmissionException exception) {
        return ResponseEntity.badRequest().body(new ErrorResponse("RUN_SUBMISSION_INVALID", exception.getMessage()));
    }
}
