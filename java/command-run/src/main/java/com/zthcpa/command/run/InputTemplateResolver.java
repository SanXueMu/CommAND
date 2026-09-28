package com.zthcpa.command.run;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class InputTemplateResolver {
    private InputTemplateResolver() {
    }

    public static Map<String, Object> resolve(Map<String, Object> template,
                                              Map<String, Object> runInput,
                                              Map<String, Map<String, Object>> stepOutputs) {
        if (template == null || template.isEmpty()) {
            return Map.copyOf(runInput);
        }
        Object resolved = value(template, runInput, stepOutputs);
        if (!(resolved instanceof Map<?, ?> map)) {
            throw new RunSubmissionException("Resolved step input must be an object");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        map.forEach((key, value) -> result.put(String.valueOf(key), value));
        return Map.copyOf(result);
    }

    private static Object value(Object raw, Map<String, Object> runInput,
                                Map<String, Map<String, Object>> stepOutputs) {
        if (raw instanceof String reference && reference.startsWith("$")) {
            return resolveReference(reference, runInput, stepOutputs);
        }
        if (raw instanceof Map<?, ?> map) {
            Map<String, Object> result = new LinkedHashMap<>();
            map.forEach((key, item) -> result.put(String.valueOf(key), value(item, runInput, stepOutputs)));
            return result;
        }
        if (raw instanceof List<?> list) {
            List<Object> result = new ArrayList<>();
            list.forEach(item -> result.add(value(item, runInput, stepOutputs)));
            return result;
        }
        return raw;
    }

    private static Object resolveReference(String reference, Map<String, Object> runInput,
                                           Map<String, Map<String, Object>> stepOutputs) {
        String[] parts = reference.split("\\.");
        if (parts.length < 2) {
            throw new RunSubmissionException("Invalid input reference: " + reference);
        }
        Object current;
        if ("$run".equals(parts[0])) {
            current = runInput;
        } else if ("$step".equals(parts[0]) && parts.length >= 3) {
            current = stepOutputs.get(parts[1]);
            if (current == null) {
                throw new RunSubmissionException("Step output is not available: " + parts[1]);
            }
        } else {
            throw new RunSubmissionException("Invalid input reference: " + reference);
        }
        for (int index = "$run".equals(parts[0]) ? 1 : 2; index < parts.length; index++) {
            if (current instanceof Map<?, ?> map) {
                if (!map.containsKey(parts[index])) {
                    throw new RunSubmissionException("Input reference does not exist: " + reference);
                }
                current = map.get(parts[index]);
                continue;
            }
            if (current instanceof List<?> list) {
                int itemIndex = parseIndex(parts[index], reference);
                if (itemIndex >= list.size()) {
                    throw new RunSubmissionException("Input reference does not exist: " + reference);
                }
                current = list.get(itemIndex);
                continue;
            }
            throw new RunSubmissionException("Input reference does not exist: " + reference);
        }
        return current;
    }

    private static int parseIndex(String value, String reference) {
        try {
            int index = Integer.parseInt(value);
            if (index < 0) {
                throw new NumberFormatException();
            }
            return index;
        } catch (NumberFormatException exception) {
            throw new RunSubmissionException("Invalid array index in input reference: " + reference);
        }
    }
}
