type Schema = {
  $ref?: string; $defs?: Record<string, Schema>; type?: string; const?: unknown;
  enum?: unknown[]; anyOf?: Schema[]; oneOf?: Schema[]; allOf?: Schema[];
  required?: string[]; properties?: Record<string, Schema>; additionalProperties?: boolean | Schema;
  items?: Schema; prefixItems?: Schema[]; minItems?: number; maxItems?: number;
  minimum?: number; maximum?: number; exclusiveMinimum?: number; exclusiveMaximum?: number;
  minLength?: number; maxLength?: number; pattern?: string; format?: string;
}
const schemas = import.meta.glob('../../../contracts/*.schema.json', { eager: true, import: 'default' }) as Record<string, Schema>

function conforms(value: unknown, schema: Schema, root: Schema): boolean {
  if (schema.$ref) {
    const name = schema.$ref.replace('#/$defs/', '')
    return !!root.$defs?.[name] && conforms(value, root.$defs[name], root)
  }
  if (schema.anyOf && !schema.anyOf.some(s => conforms(value, s, root))) return false
  if (schema.oneOf && schema.oneOf.filter(s => conforms(value, s, root)).length !== 1) return false
  if (schema.allOf && !schema.allOf.every(s => conforms(value, s, root))) return false
  if ('const' in schema && value !== schema.const) return false
  if (schema.enum && !schema.enum.includes(value)) return false
  if (schema.type === 'null') return value === null
  if (schema.type === 'boolean' && typeof value !== 'boolean') return false
  if (schema.type === 'string') {
    if (typeof value !== 'string') return false
    if (schema.minLength !== undefined && value.length < schema.minLength) return false
    if (schema.maxLength !== undefined && value.length > schema.maxLength) return false
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) return false
    if (schema.format === 'date-time' && (!/T.*(?:Z|[+-]\d\d:\d\d)$/.test(value) || !Number.isFinite(Date.parse(value)))) return false
  }
  if (schema.type === 'number' || schema.type === 'integer') {
    if (typeof value !== 'number' || !Number.isFinite(value)) return false
    if (schema.type === 'integer' && !Number.isInteger(value)) return false
    if (schema.minimum !== undefined && value < schema.minimum) return false
    if (schema.maximum !== undefined && value > schema.maximum) return false
    if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum) return false
    if (schema.exclusiveMaximum !== undefined && value >= schema.exclusiveMaximum) return false
  }
  if (schema.type === 'array') {
    if (!Array.isArray(value)) return false
    if (schema.minItems !== undefined && value.length < schema.minItems) return false
    if (schema.maxItems !== undefined && value.length > schema.maxItems) return false
    if (schema.prefixItems && !schema.prefixItems.every((s, i) => conforms(value[i], s, root))) return false
    if (schema.items && !value.every(v => conforms(v, schema.items!, root))) return false
  }
  if (schema.type === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false
    const obj = value as Record<string, unknown>
    if (schema.required?.some(key => !(key in obj))) return false
    for (const [key, entry] of Object.entries(obj)) {
      const property = schema.properties?.[key]
      if (property && !conforms(entry, property, root)) return false
      if (!property && schema.additionalProperties === false) return false
      if (!property && typeof schema.additionalProperties === 'object' && !conforms(entry, schema.additionalProperties, root)) return false
    }
  }
  return true
}

export function validateContract<T>(name: string, value: unknown): T {
  const schema = schemas[`../../../contracts/${name}.schema.json`]
  if (!schema || !conforms(value, schema, schema)) throw new Error(`Malformed ${name} response. The last verified data is retained.`)
  return value as T
}
export function validateList<T>(name: string, value: unknown): T[] {
  if (!Array.isArray(value)) throw new Error(`Malformed ${name} list response.`)
  return value.map(item => validateContract<T>(name, item))
}
