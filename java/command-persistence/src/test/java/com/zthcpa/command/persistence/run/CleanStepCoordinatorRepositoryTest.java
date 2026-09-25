package com.zthcpa.command.persistence.run;

import com.zthcpa.command.persistence.run.CleanNextStepPlan;
import com.zthcpa.command.persistence.run.CleanStepCoordinatorRepository;

import com.zthcpa.command.contract.DefinitionKey;
import com.zthcpa.command.contract.DefinitionKind;
import com.zthcpa.command.run.TaskStatus;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertThrows;

class CleanStepCoordinatorRepositoryTest {
    @Test
    void rejectsNonSuccessfulAdvanceBeforeOpeningTransaction() {
        var repository = new CleanStepCoordinatorRepository(null, new ObjectMapper());
        assertThrows(IllegalArgumentException.class, () -> repository.completeAndAdvance(
                "task-1", "worker-1", TaskStatus.FAILED, Map.of(), Map.of(), null
        ));
    }

    @Test
    void validatesNextStepPlan() {
        assertThrows(IllegalArgumentException.class, () -> new CleanNextStepPlan(
                "", 1, "step", new DefinitionKey(DefinitionKind.TOOL, "tool", 1),
                Map.of(), "task", 1
        ));
    }
}
