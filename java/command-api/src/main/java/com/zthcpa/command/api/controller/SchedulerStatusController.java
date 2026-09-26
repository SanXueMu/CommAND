package com.zthcpa.command.api.controller;

import com.zthcpa.command.api.port.SchedulerStatusPort;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/system/scheduler")
public final class SchedulerStatusController {
    private final SchedulerStatusPort status;

    public SchedulerStatusController(SchedulerStatusPort status) {
        this.status = status;
    }

    @GetMapping
    public SchedulerStatusPort.Status get() {
        return status.status();
    }
}
