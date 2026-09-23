package com.zthcpa.command;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.contract.DefinitionRegistry;
import com.zthcpa.command.contract.DefinitionRepository;
import com.zthcpa.command.definition.ClasspathDefinitionLoader;
import com.zthcpa.command.definition.DefinitionSetValidator;
import com.zthcpa.command.definition.DefinitionReferenceValidator;
import com.zthcpa.command.definition.InMemoryDefinitionRegistry;
import com.zthcpa.command.definition.JsonDefinitionParser;
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
