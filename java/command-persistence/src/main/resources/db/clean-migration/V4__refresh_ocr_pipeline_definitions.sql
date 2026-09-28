UPDATE command_runtime.command_definitions
SET document = $$
{
  "schema_version": 1,
  "kind": "capability_pipeline",
  "id": "ocr.extract-by-template",
  "version": 1,
  "status": "active",
  "title": "Extract pages with a resolved template",
  "steps": [
    {"id":"inspect","definition_ref":{"kind":"tool","id":"file.inspect","version":1}},
    {"id":"pages","definition_ref":{"kind":"tool","id":"pdf.pages.to.images","version":1},"input":{"file":"$run.file"}},
    {"id":"extract","definition_ref":{"kind":"tool","id":"ocr.vision.extract","version":1},"input":{"file":"$step.pages.pages.0.file","fields":"$run.fields","model":"$run.model","prompt":"$run.prompt"}},
    {"id":"persist","definition_ref":{"kind":"tool","id":"ocrdb.write.records","version":1},"input":{"records":"$step.extract.records","source_path":"$run.file","name":"$run.result_name"}}
  ]
}
$$::jsonb,
    checksum = repeat('0', 64),
    updated_at = now()
WHERE kind = 'capability_pipeline' AND id = 'ocr.extract-by-template' AND definition_version = 1;

UPDATE command_runtime.command_definitions
SET document = $$
{
  "schema_version": 1,
  "kind": "workflow",
  "id": "ocr.extract-document",
  "version": 1,
  "status": "active",
  "title": "Extract document with a template",
  "capability_pipeline_ref":{"kind":"capability_pipeline","id":"ocr.extract-by-template","version":1},
  "input_schema":{"type":"object","required":["file","template_id"],"properties":{"file":{"type":"string"},"template_id":{"type":"string","minLength":1},"fields":{"type":"array","items":{"type":"string"}},"model":{"type":"string"},"prompt":{"type":"string"},"result_name":{"type":"string"}},"additionalProperties":false},
  "output":{"result_kind":"ocr_result_dataset","optional_artifacts":["records.xlsx"]}
}
$$::jsonb,
    checksum = repeat('0', 64),
    updated_at = now()
WHERE kind = 'workflow' AND id = 'ocr.extract-document' AND definition_version = 1;
