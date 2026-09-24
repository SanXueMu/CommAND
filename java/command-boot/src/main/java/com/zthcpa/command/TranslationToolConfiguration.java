package com.zthcpa.command;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.tools.InMemoryTranslationCache;
import com.zthcpa.command.tools.JavaToolRegistry;
import com.zthcpa.command.tools.OpenAiCompatibleTranslationModel;
import com.zthcpa.command.tools.TextLlmTranslateJavaTool;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;

@Configuration
public class TranslationToolConfiguration {
    @Bean
    @ConditionalOnProperty(prefix = "command.tools.translation", name = "enabled", havingValue = "true")
    OpenAiCompatibleTranslationModel translationModel(ObjectMapper objectMapper) {
        String baseUrl = required("COMMAND_TRANSLATION_BASE_URL");
        String apiKey = required("COMMAND_TRANSLATION_API_KEY");
        return new OpenAiCompatibleTranslationModel(
                HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build(),
                objectMapper,
                URI.create(baseUrl),
                apiKey,
                Duration.ofSeconds(120)
        );
    }

    @Bean
    @ConditionalOnProperty(prefix = "command.tools.translation", name = "enabled", havingValue = "true")
    TextLlmTranslateJavaTool textLlmTranslateJavaTool(OpenAiCompatibleTranslationModel model) {
        return new TextLlmTranslateJavaTool(model, new InMemoryTranslationCache());
    }

    @Bean
    @ConditionalOnProperty(prefix = "command.tools.translation", name = "enabled", havingValue = "true")
    JavaToolRegistry javaToolRegistry(TextLlmTranslateJavaTool translationTool) {
        return new JavaToolRegistry(List.of(translationTool));
    }

    private String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(name + " must be set when Java translation is enabled");
        }
        return value;
    }
}
