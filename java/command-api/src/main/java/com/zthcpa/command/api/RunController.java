package com.zthcpa.command.api;

import com.zthcpa.command.run.RunSubmissionException;
import org.springframework.context.annotation.Conditional;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;

import static com.zthcpa.command.api.RunApiModels.ErrorResponse;
import static com.zthcpa.command.api.RunApiModels.RunResponse;
import static com.zthcpa.command.api.RunApiModels.RunEventResponse;
import static com.zthcpa.command.api.RunApiModels.SubmitRunRequest;
import static com.zthcpa.command.api.RunApiModels.SubmitRunResponse;

@RestController
@Conditional(DataSourcePresentCondition.class)
@RequestMapping("/api/runs")
public final class RunController {
    private final RunApplicationService service;
    private final RunEventStreamService eventStreams;

    public RunController(RunApplicationService service, RunEventStreamService eventStreams) {
        this.service = service;
        this.eventStreams = eventStreams;
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

    @GetMapping("/{runId}/events")
    public ResponseEntity<List<RunEventResponse>> events(
            @PathVariable String runId,
            @RequestParam(defaultValue = "0") long afterId,
            @RequestParam(defaultValue = "100") int limit
    ) {
        if (afterId < 0 || limit < 1 || limit > 1000) {
            throw new RunSubmissionException("afterId must be non-negative and limit must be between 1 and 1000");
        }
        List<RunEventResponse> events = service.events(runId, afterId, limit);
        return events == null ? ResponseEntity.notFound().build() : ResponseEntity.ok(events);
    }

    @GetMapping(value = "/{runId}/events/stream", produces = "text/event-stream")
    public ResponseEntity<SseEmitter> eventStream(
            @PathVariable String runId,
            @RequestParam(defaultValue = "0") long afterId
    ) {
        SseEmitter emitter = eventStreams.open(runId, afterId);
        return emitter == null ? ResponseEntity.notFound().build() : ResponseEntity.ok(emitter);
    }

    @ExceptionHandler(RunSubmissionException.class)
    ResponseEntity<ErrorResponse> handleSubmission(RunSubmissionException exception) {
        return ResponseEntity.badRequest().body(new ErrorResponse("RUN_SUBMISSION_INVALID", exception.getMessage()));
    }
}
