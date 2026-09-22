package com.zthcpa.command;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionRegistry;
import com.zthcpa.command.definition.ClasspathDefinitionLoader;
import com.zthcpa.command.definition.DefinitionSetValidator;
import com.zthcpa.command.definition.InMemoryDefinitionRegistry;
import com.zthcpa.command.definition.JsonDefinitionParser;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DefinitionConfiguration {
    @Bean
    DefinitionRegistry builtInDefinitionRegistry(ObjectMapper objectMapper) {
        var parser = new JsonDefinitionParser(objectMapper);
        var loader = new ClasspathDefinitionLoader(
                DefinitionConfiguration.class.getClassLoader(),
                "definitions/index.txt",
                parser
        );
        return new InMemoryDefinitionRegistry(loader.load(), new DefinitionSetValidator());
    }
}
