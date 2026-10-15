package com.zthcpa.command.api.controller;

import com.zthcpa.command.api.application.CustomWorkflowApplicationService;
import com.zthcpa.command.api.application.CustomWorkflowApplicationService.CustomWorkflowRequest;
import com.zthcpa.command.api.application.CustomWorkflowApplicationService.CustomWorkflowResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/workflows")
public class CustomWorkflowController {
    private final CustomWorkflowApplicationService service;

    public CustomWorkflowController(CustomWorkflowApplicationService service) {
        this.service = service;
    }

    @PostMapping("/custom")
    public ResponseEntity<CustomWorkflowResponse> create(@RequestBody CustomWorkflowRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.create(request));
    }
}
