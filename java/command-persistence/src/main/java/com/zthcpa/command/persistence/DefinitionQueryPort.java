package com.zthcpa.command.persistence;

import com.zthcpa.command.contract.DefinitionDocument;

import java.util.List;
import java.util.Optional;

public interface DefinitionQueryPort {
    Optional<DefinitionDocument> findActive(String kind, String id);

    List<DefinitionDocument> listActive(String kind);
}
