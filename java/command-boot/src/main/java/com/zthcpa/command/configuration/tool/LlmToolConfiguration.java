package com.zthcpa.command.configuration.tool;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.tools.llm.LlmChatCompleteJsonTool;
import com.zthcpa.command.tools.llm.LlmChatCompleteTool;
import com.zthcpa.command.tools.llm.OpenAiCompatibleLlmClient;
import com.zthcpa.command.contract.LlmConfigurationPort;
import com.zthcpa.command.tools.ocr.OpenAiCompatibleVisionClient;
import com.zthcpa.command.tools.ocr.VisionOcrTool;
import com.zthcpa.command.tools.spi.JavaToolRegistry;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;

@Configuration
@EnableConfigurationProperties(LlmToolProperties.class)
public class LlmToolConfiguration {
    @Bean
    OpenAiCompatibleLlmClient llmClient(ObjectMapper objectMapper, LlmToolProperties properties, LlmConfigurationPort configuration) {
        return new OpenAiCompatibleLlmClient(
                HttpClient.newBuilder().connectTimeout(positive(properties.getConnectTimeout(), "connectTimeout")).build(),
                objectMapper,
                configuration,
                positive(properties.getRequestTimeout(), "requestTimeout")
        );
    }

    @Bean
    LlmChatCompleteTool llmChatCompleteTool(OpenAiCompatibleLlmClient client, ObjectMapper objectMapper) {
        return new LlmChatCompleteTool(client, objectMapper);
    }

    @Bean
    LlmChatCompleteJsonTool llmChatCompleteJsonTool(OpenAiCompatibleLlmClient client, ObjectMapper objectMapper) {
        return new LlmChatCompleteJsonTool(client, objectMapper);
    }

    @Bean
    OpenAiCompatibleVisionClient visionClient(ObjectMapper objectMapper, LlmToolProperties properties, LlmConfigurationPort configuration) {
        return new OpenAiCompatibleVisionClient(
                HttpClient.newHttpClient(), objectMapper, configuration, positive(properties.getRequestTimeout(), "requestTimeout"));
    }

    @Bean
    VisionOcrTool visionOcrTool(OpenAiCompatibleVisionClient client, ObjectMapper objectMapper) {
        return new VisionOcrTool(client, objectMapper);
    }

    @Bean
    JavaToolRegistry javaToolRegistry(List<com.zthcpa.command.tools.spi.JavaTool> tools) {
        return new JavaToolRegistry(tools);
    }

    private String required(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("command.tools.llm." + name + " must be set when LLM tools are enabled");
        }
        return value;
    }

    private Duration positive(Duration value, String name) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalStateException("command.tools.llm." + name + " must be positive");
        }
        return value;
    }
}
