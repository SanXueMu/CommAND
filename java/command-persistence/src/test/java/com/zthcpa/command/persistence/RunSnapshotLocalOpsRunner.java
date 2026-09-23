package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.contract.RunDefinitionSnapshot;
import com.zthcpa.command.definition.ClasspathDefinitionLoader;
import com.zthcpa.command.definition.JsonDefinitionParser;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.List;

public final class RunSnapshotLocalOpsRunner {
    private static final String PIPELINE_ID = "java-snapshot-selftest";
    private static final String RUN_ID = "java-snapshot-selftest-run";

    public static void main(String[] args) {
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL(env("COMMAND_DB_URL", "jdbc:postgresql://localhost:5432/command_dev"));
        dataSource.setUser(env("COMMAND_DB_USER", "command_dev"));
        dataSource.setPassword(requiredEnv("COMMAND_DB_PASSWORD"));

        ObjectMapper mapper = new ObjectMapper();
        var parser = new JsonDefinitionParser(mapper);
        var loader = new ClasspathDefinitionLoader(
                RunSnapshotLocalOpsRunner.class.getClassLoader(),
                "definitions/index.txt",
                parser
        );
        List<DefinitionDocument> builtIns = loader.load();
        var jdbc = new NamedParameterJdbcTemplate(dataSource);
        var snapshots = new JdbcRunDefinitionSnapshotRepository(jdbc, mapper);

        try {
            createFixture(jdbc);
            builtIns.forEach(definition -> snapshots.saveIfAbsent(RUN_ID, definition));
            builtIns.forEach(definition -> snapshots.saveIfAbsent(RUN_ID, definition));

            List<RunDefinitionSnapshot> stored = snapshots.listByRun(RUN_ID);
            System.out.printf("seeded=%d, stored=%d%n", builtIns.size(), stored.size());
            stored.forEach(snapshot -> System.out.println(
                    snapshot.runId() + " " + snapshot.key() + " checksum=" + snapshot.checksum()
            ));
            if (stored.size() != builtIns.size()) {
                throw new IllegalStateException("Snapshot idempotency check failed");
            }
        } finally {
            dropFixture(jdbc);
        }
    }

    private static void createFixture(NamedParameterJdbcTemplate jdbc) {
        jdbc.getJdbcTemplate().update(
                "INSERT INTO pipelines (id, name, steps) VALUES (?, ?, CAST(? AS jsonb))",
                PIPELINE_ID, "Java 快照自验", "[]"
        );
        jdbc.getJdbcTemplate().update(
                "INSERT INTO pipeline_runs (id, pipeline_id, input) VALUES (?, ?, CAST(? AS jsonb))",
                RUN_ID, PIPELINE_ID, "{}"
        );
    }

    private static void dropFixture(NamedParameterJdbcTemplate jdbc) {
        jdbc.getJdbcTemplate().update("DELETE FROM pipeline_runs WHERE id = ?", RUN_ID);
        jdbc.getJdbcTemplate().update("DELETE FROM pipelines WHERE id = ?", PIPELINE_ID);
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return (value == null || value.isBlank()) ? fallback : value;
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must be provided");
        }
        return value;
    }

    private RunSnapshotLocalOpsRunner() {
    }
}
