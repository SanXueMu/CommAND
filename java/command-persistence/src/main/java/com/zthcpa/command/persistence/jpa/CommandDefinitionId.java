package com.zthcpa.command.persistence.jpa;

import java.io.Serializable;

public record CommandDefinitionId(String kind, String id, int definitionVersion) implements Serializable {
}
