package com.zthcpa.command;

import com.zthcpa.command.runtime.tool.InProcessToolRuntime;
import com.zthcpa.command.runtime.worker.WorkerEvent;
import com.zthcpa.command.runtime.worker.WorkerJob;
import com.zthcpa.command.runtime.worker.WorkerJobRequest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "command.clean.scheduler.enabled=true",
        "command.clean.scheduler.worker-id=java-tool-runtime-test"
})
@EnabledIfEnvironmentVariable(named = "COMMAND_DB_PASSWORD", matches = ".+")
class JavaToolRuntimeIntegrationTest {
    @Autowired
    private InProcessToolRuntime runtime;

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> "jdbc:postgresql://localhost:5432/command_dev");
        registry.add("spring.datasource.username", () -> "command_dev");
        registry.add("spring.datasource.password", () -> System.getenv("COMMAND_DB_PASSWORD"));
    }

    @Test
    void executesMigratedPureToolsThroughTheJavaJobProtocol() throws Exception {
        WorkerJob merge = runtime.createJob("records.merge.crosspage", new WorkerJobRequest(
                "records.merge.crosspage", 1, "task-merge", 1,
                Map.of("records", List.of(
                        Map.of("项目名称", "甲项目", "金额", "100", "页码", 1),
                        Map.of("金额", "50", "页码", 2)
                ), "key_field", "项目名称", "modes", List.of("join"))));
        WorkerJob dedup = runtime.createJob("text.dedup.values", new WorkerJobRequest(
                "text.dedup.values", 1, "task-dedup", 1,
                Map.of("segments", List.of("2023-11-16 报告", "2023-11-17 报告"))));
        WorkerJob classify = runtime.createJob("table.classify.columns", new WorkerJobRequest(
                "table.classify.columns", 1, "task-classify", 1,
                Map.of("units", List.of(
                        Map.of("unit_id", "table-1", "unit_type", "table", "rows", List.of(
                                List.of("编号", "部门"),
                                List.of("1", "审计部"),
                                List.of("2", "财务部")
                         ))))));
        WorkerJob verify = runtime.createJob("text.verify.fidelity", new WorkerJobRequest(
                "text.verify.fidelity", 1, "task-verify", 1,
                Map.of("sources", List.of("Total 2024", "hello world"),
                        "translations", List.of("总计 2024", "hello world"))));

        WorkerJob mergeResult = await(runtime, merge.jobId());
        WorkerJob dedupResult = await(runtime, dedup.jobId());
        WorkerJob classifyResult = await(runtime, classify.jobId());
        WorkerJob verifyResult = await(runtime, verify.jobId());
        assertEquals("succeeded", mergeResult.status());
        assertEquals("succeeded", dedupResult.status());
        assertEquals("succeeded", classifyResult.status());
        assertEquals("succeeded", verifyResult.status());
        assertEquals(1, ((Number) mergeResult.output().get("records_count")).intValue());
        assertEquals(List.of(0, 0), dedupResult.output().get("index_map"));
        assertEquals("enum", ((List<?>) ((Map<?, ?>) classifyResult.output().get("col_classes"))
                .get("table-1")).get(1).toString().contains("enum") ? "enum" : "missing");
        assertTrue(runtime.listEvents(merge.jobId(), 0).stream().map(WorkerEvent::type).anyMatch("progress"::equals));
        assertTrue(runtime.listEvents(dedup.jobId(), 0).stream().map(WorkerEvent::type).anyMatch("progress"::equals));
        assertTrue(runtime.listEvents(classify.jobId(), 0).stream().map(WorkerEvent::type).anyMatch("progress"::equals));
        assertEquals(List.of("ok", "review"), verifyResult.output().get("statuses"));
        assertTrue(runtime.listEvents(verify.jobId(), 0).stream().map(WorkerEvent::type).anyMatch("progress"::equals));
    }

    private WorkerJob await(InProcessToolRuntime worker, String jobId) throws InterruptedException {
        for (int i = 0; i < 100; i++) {
            WorkerJob job = worker.getJob(jobId);
            if (!"running".equals(job.status()) && !"queued".equals(job.status())) return job;
            Thread.sleep(10);
        }
        throw new AssertionError("Java Tool job did not finish: " + jobId);
    }

}
