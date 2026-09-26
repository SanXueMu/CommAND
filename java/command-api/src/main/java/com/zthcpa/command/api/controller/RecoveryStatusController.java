package com.zthcpa.command.api.controller;

import com.zthcpa.command.api.port.RecoveryStatusPort;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/system/recovery")
public final class RecoveryStatusController {
    private final RecoveryStatusPort status;

    public RecoveryStatusController(RecoveryStatusPort status) {
        this.status = status;
    }

    @GetMapping
    public RecoveryStatusPort.Status get() {
        return status.status();
    }
}
