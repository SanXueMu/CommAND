package com.zthcpa.command.persistence.config;

import com.zthcpa.command.persistence.config.HibernatePersistenceConfiguration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class HibernatePersistenceConfigurationTest {
    @Test
    void exposesConfigurationTypeWithoutCreatingAConnection() {
        assertNotNull(HibernatePersistenceConfiguration.class.getAnnotation(
                org.springframework.context.annotation.Configuration.class
        ));
    }
}
