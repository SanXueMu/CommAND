package com.zthcpa.command.configuration.definition;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionRegistry;
import com.zthcpa.command.contract.DefinitionRepository;
import com.zthcpa.command.definition.loader.ClasspathDefinitionLoader;
import com.zthcpa.command.definition.loader.JsonDefinitionParser;
import com.zthcpa.command.definition.registry.InMemoryDefinitionRegistry;
import com.zthcpa.command.definition.validation.DefinitionReferenceValidator;
import com.zthcpa.command.definition.validation.DefinitionSetValidator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Optional;

@Configuration
public class DefinitionConfiguration {
    @Bean
    DefinitionRegistry definitionRegistry(
            ObjectMapper objectMapper,
            Optional<DefinitionRepository> definitionRepository
    ) {
        var parser = new JsonDefinitionParser(objectMapper);
        var loader = new ClasspathDefinitionLoader(
                DefinitionConfiguration.class.getClassLoader(),
                "definitions/index.txt",
                parser
        );
        var builtIns = loader.load();
        if (definitionRepository.isEmpty()) {
            return new InMemoryDefinitionRegistry(
                    builtIns,
                    new DefinitionSetValidator(),
                    new DefinitionReferenceValidator()
            );
        }
        builtIns.forEach(definitionRepository.get()::saveIfAbsent);
        return new InMemoryDefinitionRegistry(
                definitionRepository.get().list(),
                new DefinitionSetValidator(),
                new DefinitionReferenceValidator()
        );
    }
}
