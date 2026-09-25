package com.zthcpa.command.persistence.task;

import com.zthcpa.command.persistence.task.HibernateCleanTaskRepository;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.zthcpa.command.run.TaskStatus;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertThrows;

class CleanTaskRepositoryTest {
    @Test
    void finishRejectsNonTerminalStatusBeforePersistence() {
        var repository = new HibernateCleanTaskRepository((EntityManager) null, new ObjectMapper());

        assertThrows(IllegalArgumentException.class, () -> repository.finish(
                "task-1", "worker-1", TaskStatus.RUNNING, Map.of(), null
        ));
    }
}
