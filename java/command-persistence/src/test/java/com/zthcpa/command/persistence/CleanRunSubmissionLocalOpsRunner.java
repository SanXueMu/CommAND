package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.definition.ClasspathDefinitionLoader;
import com.zthcpa.command.definition.DefinitionReferenceValidator;
import com.zthcpa.command.definition.DefinitionSetValidator;
import com.zthcpa.command.definition.InMemoryDefinitionRegistry;
import com.zthcpa.command.definition.JsonDefinitionParser;
import com.zthcpa.command.run.RunSubmissionPlan;
import com.zthcpa.command.run.RunSubmissionPlanner;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

public final class CleanRunSubmissionLocalOpsRunner {
    private static final String RUN_ID = "clean-submission-selftest-run";

    public static void main(String[] args) {
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL("jdbc:postgresql://localhost:5432/command_dev");
        dataSource.setUser("command_dev");
        dataSource.setPassword(requiredEnv("COMMAND_DB_PASSWORD"));

        ObjectMapper mapper = new ObjectMapper();
        var parser = new JsonDefinitionParser(mapper);
        var loader = new ClasspathDefinitionLoader(
                CleanRunSubmissionLocalOpsRunner.class.getClassLoader(),
                "definitions/index.txt",
                parser
        );
        List<DefinitionDocument> definitions = loader.load();
        var registry = new InMemoryDefinitionRegistry(
                definitions, new DefinitionSetValidator(), new DefinitionReferenceValidator()
        );
        AtomicInteger ids = new AtomicInteger();
        var planner = new RunSubmissionPlanner(registry, () -> RUN_ID + "-" + ids.incrementAndGet());
        RunSubmissionPlan plan = planner.plan(
                "ocr.extract-document",
                Map.of("file", "clean-selftest.pdf", "template_id", "invoice")
        );

        var jdbc = new NamedParameterJdbcTemplate(dataSource);
        var repository = new CleanRunSubmissionRepository(jdbc, mapper, dataSource);
        try {
            repository.submit(new RunSubmissionPlan(
                    RUN_ID,
                    plan.workflow(),
                    plan.input(),
                    plan.definitions(),
                    new RunSubmissionPlan.TaskPlan(
                            RUN_ID + "-task", plan.firstTask().tool(),
                            plan.firstTask().input(), 0, 1
                    )
            ));
            Map<String, Object> counts = jdbc.getJdbcTemplate().queryForMap("""
                    SELECT
                      (SELECT count(*) FROM command_runtime.runs WHERE id = ?) AS runs,
                      (SELECT count(*) FROM command_runtime.run_definition_snapshots WHERE run_id = ?) AS snapshots,
                      (SELECT count(*) FROM command_runtime.run_steps WHERE run_id = ?) AS steps,
                      (SELECT count(*) FROM command_runtime.task_executions WHERE id = ?) AS tasks
                    """, RUN_ID, RUN_ID, RUN_ID, RUN_ID + "-task");
            System.out.println(counts);
            if (!counts.equals(Map.of("runs", 1L, "snapshots", 2L, "steps", 1L, "tasks", 1L))) {
                throw new IllegalStateException("Clean submission count check failed: " + counts);
            }

            try {
                repository.submit(new RunSubmissionPlan(
                        RUN_ID,
                        plan.workflow(),
                        plan.input(),
                        plan.definitions(),
                        new RunSubmissionPlan.TaskPlan(
                                RUN_ID + "-duplicate-task", plan.firstTask().tool(),
                                plan.firstTask().input(), 0, 1
                        )
                ));
                throw new IllegalStateException("Duplicate run unexpectedly succeeded");
            } catch (RuntimeException expected) {
                System.out.println("duplicate run rolled back: " + expected.getClass().getSimpleName());
            }
        } finally {
            jdbc.getJdbcTemplate().update("DELETE FROM command_runtime.runs WHERE id = ?", RUN_ID);
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must be provided");
        }
        return value;
    }

    private CleanRunSubmissionLocalOpsRunner() {
    }
}
