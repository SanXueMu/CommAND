package com.zthcpa.command.run;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class InputTemplateResolverTest {
    @Test
    void resolvesRunAndStepReferencesRecursively() {
        Map<String, Object> resolved = InputTemplateResolver.resolve(
                Map.of(
                        "file", "$run.file",
                        "pages", List.of("$step.inspect.pages.0", 2),
                        "options", Map.of("mode", "review")
                ),
                Map.of("file", "sample.pdf"),
                Map.of("inspect", Map.of("pages", List.of(1, 3)))
        );

        assertEquals("sample.pdf", resolved.get("file"));
        assertEquals(List.of(1, 2), resolved.get("pages"));
        assertEquals(Map.of("mode", "review"), resolved.get("options"));
    }

    @Test
    void rejectsUnavailableStepOutput() {
        assertThrows(RunSubmissionException.class, () -> InputTemplateResolver.resolve(
                Map.of("pages", "$step.inspect.pages"),
                Map.of(),
                Map.of()
        ));
    }

    @Test
    void keepsInitialInputForStepsWithoutTemplate() {
        Map<String, Object> input = Map.of("file", "sample.pdf");

        assertEquals(input, InputTemplateResolver.resolve(Map.of(), input, Map.of()));
    }

    @Test
    void rejectsInvalidArrayIndex() {
        assertThrows(RunSubmissionException.class, () -> InputTemplateResolver.resolve(
                Map.of("page", "$step.inspect.pages.first"),
                Map.of(),
                Map.of("inspect", Map.of("pages", List.of(1)))
        ));
    }
}
