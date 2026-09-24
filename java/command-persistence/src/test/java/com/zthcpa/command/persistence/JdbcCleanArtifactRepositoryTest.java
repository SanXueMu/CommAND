package com.zthcpa.command.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertThrows;

class HibernateCleanArtifactRepositoryTest {
    @Test
    void rejectsInvalidArtifactMetadata() {
        var repository = new HibernateCleanArtifactRepository(null);
        var artifact = new CleanArtifact("id", "run", null, "file", "key", null,
                -1L, null, Map.of(), null);
        assertThrows(IllegalArgumentException.class, () -> repository.register(artifact));
    }

    @Test
    void rejectsInvalidChecksum() {
        var repository = new HibernateCleanArtifactRepository(null);
        var artifact = new CleanArtifact("id", "run", null, "file", "key", null,
                1L, "BAD", Map.of(), null);
        assertThrows(IllegalArgumentException.class, () -> repository.register(artifact));
    }
}
