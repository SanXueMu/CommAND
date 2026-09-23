package com.zthcpa.command.persistence;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class JdbcPersistenceConfigurationTest {
    @Test
    void exposesConfigurationTypeWithoutCreatingAConnection() {
        assertNotNull(JdbcPersistenceConfiguration.class.getAnnotation(
                org.springframework.context.annotation.Configuration.class
        ));
    }
}
