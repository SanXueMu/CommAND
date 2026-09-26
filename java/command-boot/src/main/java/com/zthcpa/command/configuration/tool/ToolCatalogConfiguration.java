package com.zthcpa.command.configuration.tool;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.catalog.ToolCatalog;
import com.zthcpa.command.catalog.loader.ToolManifestLoader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ToolCatalogConfiguration {
    @Bean
    ToolCatalog toolCatalog(ObjectMapper objectMapper) {
        return new ToolManifestLoader(
                ToolCatalogConfiguration.class.getClassLoader(),
                objectMapper
        ).load("tools/index.txt");
    }
}
