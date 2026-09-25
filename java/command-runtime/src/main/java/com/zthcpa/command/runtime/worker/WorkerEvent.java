package com.zthcpa.command.runtime.worker;

import java.util.Map;

public record WorkerEvent(
        long sequence,
        String type,
        Map<String, Object> data
) {
}
