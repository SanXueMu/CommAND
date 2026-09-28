package com.zthcpa.command.tools.table;

import org.junit.jupiter.api.Test;
import com.zthcpa.command.tools.spi.ProgressSink;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ClassifyColumnsToolTest {
    @Test
    void classifiesColumnsAndHarvestsInPythonCompatibleOrder() {
        Map<String, Object> output = new ClassifyColumnsTool().execute(Map.of(
                "units", List.of(
                        Map.of("unit_id", "table-1", "unit_type", "table", "rows", List.of(
                                List.of("编号", "部门", "金额"),
                                List.of("1", "审计部", "100"),
                                List.of("2", "财务部", "200")
                        )),
                        Map.of("unit_id", "text-1", "unit_type", "text", "text", "备注")
                )), event -> { });

        assertEquals(List.of(
                Map.of("col", 0, "class", "skip", "unique", 2),
                Map.of("col", 1, "class", "enum", "unique", 2),
                Map.of("col", 2, "class", "skip", "unique", 2)
        ), ((Map<?, ?>) output.get("col_classes")).get("table-1"));
        assertEquals(List.of("编号", "部门", "金额", "审计部", "财务部", "备注"), output.get("segments"));
        assertEquals(List.of(
                Map.of("unit_id", "table-1", "start", 0, "count", 5),
                Map.of("unit_id", "text-1", "start", 5, "count", 1)
        ), output.get("ranges"));
    }
}
