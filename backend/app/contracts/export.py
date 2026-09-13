"""Regenerate reviewed schemas after LEAD changes; no provider calls."""
import inspect
import json
from pathlib import Path
from . import models


def export(root: Path):
    schemas={}
    for name,model in vars(models).items():
        if inspect.isclass(model) and issubclass(model,models.StrictModel) and model not in (models.StrictModel,models.Record):
            schema=model.model_json_schema()
            filename=name+'.schema.json'
            (root/filename).write_text(json.dumps(schema,indent=2)+'\n')
            schemas[name]={'file':filename,'sha256':models.content_hash(schema)}
    manifest={'schema_version':models.VERSION,'scope':models.SCOPE,'schemas':schemas,'schema_hash':models.content_hash(schemas),'ownership':'../docs/integration-ledger.md','seams_version':'faultlab-seams/v1'}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

if __name__=='__main__':
    export(Path(__file__).resolve().parents[3]/'contracts')
