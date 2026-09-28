package com.zthcpa.command.configuration.tool;

import com.zthcpa.command.tools.records.MergeCrosspageTool;
import com.zthcpa.command.tools.table.ClassifyColumnsTool;
import com.zthcpa.command.tools.text.DedupValuesTool;
import com.zthcpa.command.tools.text.VerifyFidelityTool;
import com.zthcpa.command.tools.txt.TxtExtractTextTool;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PureDataToolConfiguration {
    @Bean
    MergeCrosspageTool mergeCrosspageTool() {
        return new MergeCrosspageTool();
    }

    @Bean
    DedupValuesTool dedupValuesTool() {
        return new DedupValuesTool();
    }

    @Bean
    VerifyFidelityTool verifyFidelityTool() {
        return new VerifyFidelityTool();
    }

    @Bean
    TxtExtractTextTool txtExtractTextTool() {
        return new TxtExtractTextTool();
    }

    @Bean
    ClassifyColumnsTool classifyColumnsTool() {
        return new ClassifyColumnsTool();
    }
}
