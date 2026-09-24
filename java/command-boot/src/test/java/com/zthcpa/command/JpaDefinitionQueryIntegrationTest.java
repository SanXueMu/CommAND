package com.zthcpa.command;

import com.zthcpa.command.contract.DefinitionDocument;
import com.zthcpa.command.persistence.DefinitionQueryPort;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import javax.sql.DataSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@EnabledIfEnvironmentVariable(named = "COMMAND_DB_PASSWORD", matches = ".+")
class JpaDefinitionQueryIntegrationTest {
    @Autowired
    private DefinitionQueryPort definitions;

    @Autowired
    private DataSource dataSource;

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> "jdbc:postgresql://localhost:5432/command_dev");
        registry.add("spring.datasource.username", () -> "command_dev");
        registry.add("spring.datasource.password", () -> System.getenv("COMMAND_DB_PASSWORD"));
    }

    @Test
    void readsActiveDefinitionAsContractDocument() {
        try (var connection = dataSource.getConnection();
             var statement = connection.prepareStatement("""
                     INSERT INTO command_runtime.command_definitions (
                         kind, id, definition_version, schema_version, status,
                         document, checksum, owner
                     ) VALUES ('workflow', 'jpa.query.selftest', 1, 1, 'active',
                               CAST(? AS jsonb), ?, 'selftest')
                     ON CONFLICT (kind, id, definition_version) DO UPDATE
                     SET document = EXCLUDED.document, checksum = EXCLUDED.checksum, status = 'active'
                     """)) {
            statement.setString(1, "{\"pipeline\":{\"id\":\"selftest\",\"version\":1}}");
            statement.setString(2, "0".repeat(64));
            statement.executeUpdate();

            DefinitionDocument definition = definitions.findActive("workflow", "jpa.query.selftest")
                    .orElseThrow();
            assertEquals("jpa.query.selftest", definition.key().id());
            assertEquals(1, definition.key().version());
            assertTrue(definition.content().containsKey("pipeline"));
        } catch (Exception exception) {
            throw new IllegalStateException(exception);
        } finally {
            try (var connection = dataSource.getConnection();
                 var statement = connection.prepareStatement("""
                         DELETE FROM command_runtime.command_definitions
                         WHERE kind = 'workflow' AND id = 'jpa.query.selftest'
                         """)) {
                statement.executeUpdate();
            } catch (Exception exception) {
                throw new IllegalStateException(exception);
            }
        }
    }
}
