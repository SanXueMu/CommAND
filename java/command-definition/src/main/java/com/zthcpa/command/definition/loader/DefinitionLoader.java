package com.zthcpa.command.definition.loader;

import com.zthcpa.command.contract.DefinitionDocument;

import java.util.List;

public interface DefinitionLoader {
    List<DefinitionDocument> load();
}
