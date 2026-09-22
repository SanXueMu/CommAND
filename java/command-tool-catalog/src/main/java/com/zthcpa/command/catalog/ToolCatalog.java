package com.zthcpa.command.catalog;

import com.zthcpa.command.contract.ToolDescriptor;
import com.zthcpa.command.contract.ToolKey;

import java.util.List;

public interface ToolCatalog {
    ToolDescriptor get(ToolKey key);

    List<ToolDescriptor> list();
}
