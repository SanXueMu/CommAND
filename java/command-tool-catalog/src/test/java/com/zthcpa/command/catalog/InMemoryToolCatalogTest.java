package com.zthcpa.command.catalog;

import com.zthcpa.command.contract.RuntimeKind;
import com.zthcpa.command.contract.ToolDescriptor;
import com.zthcpa.command.contract.ToolKey;
import com.zthcpa.command.contract.ToolNotFoundException;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class InMemoryToolCatalogTest {
    @Test
    void resolvesToolByStableKey() {
        ToolDescriptor descriptor = descriptor("ocr.page.extract", 1);
        InMemoryToolCatalog catalog = new InMemoryToolCatalog(List.of(descriptor));

        assertEquals(descriptor, catalog.get(new ToolKey("ocr.page.extract", 1)));
    }

    @Test
    void rejectsDuplicateAndMissingTools() {
        ToolDescriptor descriptor = descriptor("ocr.page.extract", 1);
        assertThrows(
                IllegalArgumentException.class,
                () -> new InMemoryToolCatalog(List.of(descriptor, descriptor))
        );

        InMemoryToolCatalog catalog = new InMemoryToolCatalog(List.of(descriptor));
        assertThrows(
                ToolNotFoundException.class,
                () -> catalog.get(new ToolKey("missing", 1))
        );
    }

    private ToolDescriptor descriptor(String id, int version) {
        return new ToolDescriptor(
                new ToolKey(id, version),
                RuntimeKind.HTTP,
                "active",
                Map.of("id", id, "version", version)
        );
    }
}
