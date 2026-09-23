
package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.definition.ClasspathDefinitionLoader;
import com.zthcpa.command.definition.DefinitionReferenceValidator;
import com.zthcpa.command.definition.DefinitionSetValidator;
import com.zthcpa.command.definition.JsonDefinitionParser;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import java.util.List;

public final class DefinitionLocalOpsRunner {
    public static void main(String[] args) {
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL(env("COMMAND_DB_URL", "jdbc:postgresql://localhost:5432/command_dev"));
        dataSource.setUser(env("COMMAND_DB_USER", "command_dev"));
        dataSource.setPassword(requiredEnv("COMMAND_DB_PASSWORD"));

        ObjectMapper mapper = new ObjectMapper();
        var parser = new JsonDefinitionParser(mapper);
        var loader = new ClasspathDefinitionLoader(
                DefinitionLocalOpsRunner.class.getClassLoader(),
                "definitions/index.txt",
                parser
        );
        List<DefinitionDocument> builtIns = loader.load();
        var repository = new JdbcDefinitionRepository(
                new NamedParameterJdbcTemplate(dataSource),
                mapper
        );
        builtIns.forEach(repository::saveIfAbsent);

        List<DefinitionDocument> stored = repository.list();
        new DefinitionSetValidator().validate(stored);
        new DefinitionReferenceValidator().validate(stored);
        System.out.printf("seeded=%d, stored=%d%n", builtIns.size(), stored.size());
        stored.forEach(definition -> System.out.println(
                definition.key() + " checksum=" + definition.checksum()
        ));
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

    private DefinitionLocalOpsRunner() {
    }
}
