package com.zthcpa.command.persistence.ocr;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;
import org.springframework.stereotype.Service;
import com.zthcpa.command.contract.OcrResultStore;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
public class OcrPersistenceService implements OcrResultStore {
    private final EntityManager entityManager;
    private final ObjectMapper mapper;

    public OcrPersistenceService(EntityManager entityManager, ObjectMapper mapper) {
        this.entityManager = entityManager;
        this.mapper = mapper;
    }

    public List<Map<String, Object>> templates() {
        return rows("select id, version, status, name, document::text from command_runtime.ocr_templates order by name, version desc", List.of("id", "version", "status", "name", "document"));
    }

    @Transactional
    public Map<String, Object> saveTemplate(Map<String, Object> input) {
        String id = required(input, "id");
        int version = number(input.getOrDefault("version", 1));
        String name = required(input, "name");
        String status = String.valueOf(input.getOrDefault("status", "draft"));
        entityManager.createNativeQuery("insert into command_runtime.ocr_templates(id, version, status, name, document) values (:id,:version,:status,:name,cast(:document as jsonb)) on conflict (id,version) do update set status=excluded.status,name=excluded.name,document=excluded.document,updated_at=now()")
                .setParameter("id", id).setParameter("version", version).setParameter("status", status).setParameter("name", name)
                .setParameter("document", json(input)).executeUpdate();
        return Map.of("id", id, "version", version, "status", status, "name", name, "document", input);
    }

    @Transactional
    public void deleteTemplate(String id, int version) {
        entityManager.createNativeQuery("delete from command_runtime.ocr_templates where id=:id and version=:version")
                .setParameter("id", id).setParameter("version", version).executeUpdate();
    }

    public List<Map<String, Object>> resultSets() {
        return rows("select id, source_path, source_hash, template_id, template_version, status, metadata::text from command_runtime.ocr_result_sets order by created_at desc", List.of("id", "source_path", "source_hash", "template_id", "template_version", "status", "metadata"));
    }

    public List<Map<String, Object>> records(String resultSetId) {
        String sql = "select id, result_set_id, page_no, record_index, payload::text from command_runtime.ocr_records" + (resultSetId == null ? " order by created_at desc" : " where result_set_id=:resultSetId order by page_no nulls first, record_index");
        var query = entityManager.createNativeQuery(sql);
        if (resultSetId != null) query.setParameter("resultSetId", resultSetId);
        return mapRows(query.getResultList(), List.of("id", "result_set_id", "page_no", "record_index", "payload"));
    }

    public List<Map<String, Object>> views() {
        return rows("select id, name, spec::text from command_runtime.ocr_views order by name", List.of("id", "name", "spec"));
    }

    @Transactional
    public Map<String, Object> saveView(Map<String, Object> input) {
        String id = String.valueOf(input.getOrDefault("id", UUID.randomUUID()));
        String name = required(input, "name");
        entityManager.createNativeQuery("insert into command_runtime.ocr_views(id,name,spec) values (:id,:name,cast(:spec as jsonb)) on conflict(id) do update set name=excluded.name,spec=excluded.spec,updated_at=now()")
                .setParameter("id", id).setParameter("name", name).setParameter("spec", json(input.getOrDefault("spec", Map.of()))).executeUpdate();
        return Map.of("id", id, "name", name, "spec", input.getOrDefault("spec", Map.of()));
    }

    @Transactional
    public void deleteView(String id) {
        entityManager.createNativeQuery("delete from command_runtime.ocr_views where id=:id").setParameter("id", id).executeUpdate();
    }

    @Transactional
    @Override
    public String save(String sourcePath, String sourceHash, String templateId, int templateVersion, List<Map<String, Object>> records) {
        String id = UUID.randomUUID().toString();
        entityManager.createNativeQuery("insert into command_runtime.ocr_result_sets(id,source_path,source_hash,template_id,template_version,status) values (:id,:path,:hash,:template,:version,'succeeded')")
                .setParameter("id", id).setParameter("path", sourcePath).setParameter("hash", sourceHash).setParameter("template", templateId).setParameter("version", templateVersion).executeUpdate();
        int index = 0;
        for (Map<String, Object> record : records) {
            entityManager.createNativeQuery("insert into command_runtime.ocr_records(id,result_set_id,record_index,payload) values (:id,:result,:idx,cast(:payload as jsonb))")
                    .setParameter("id", UUID.randomUUID().toString()).setParameter("result", id).setParameter("idx", index++) .setParameter("payload", json(record)).executeUpdate();
        }
        return id;
    }

    private List<Map<String, Object>> rows(String sql, List<String> columns) { return mapRows(entityManager.createNativeQuery(sql).getResultList(), columns); }
    private List<Map<String, Object>> mapRows(List<?> raw, List<String> columns) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object value : raw) {
            Object[] row = (Object[]) value;
            Map<String, Object> item = new LinkedHashMap<>();
            for (int i = 0; i < row.length; i++) item.put(columns.get(i), parse(row[i]));
            result.add(item);
        }
        return result;
    }
    private Object parse(Object value) { if (!(value instanceof String text)) return value; try { return mapper.readValue(text, Object.class); } catch (Exception ignored) { return value; } }
    private String json(Object value) { try { return mapper.writeValueAsString(value); } catch (JsonProcessingException e) { throw new IllegalArgumentException("Invalid JSON", e); } }
    private static String required(Map<String, Object> input, String key) { Object value = input.get(key); if (value == null || String.valueOf(value).isBlank()) throw new IllegalArgumentException(key + " must not be blank"); return String.valueOf(value); }
    private static int number(Object value) { int number = Integer.parseInt(String.valueOf(value)); if (number < 1) throw new IllegalArgumentException("version must be positive"); return number; }
}
