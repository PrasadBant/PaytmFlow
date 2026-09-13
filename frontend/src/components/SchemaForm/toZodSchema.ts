import { z } from 'zod';
import type { components } from '@/api/types.gen';
import { formatIndianCurrency } from '@/lib/utils';

export type GoalFieldSpec = components['schemas']['GoalFieldSpec'];

export function buildFieldSchema(field: GoalFieldSpec): z.ZodTypeAny {
  switch (field.type) {
    case 'enum': {
      const options = field.options || [];
      const optionValues = options.map((opt) =>
        typeof opt === 'string' ? opt : String(opt.value)
      );

      if (optionValues.length === 0) {
        return field.required
          ? z.string({ required_error: `${field.label} is required` }).min(1, `${field.label} is required`)
          : z.string().optional().or(z.literal(''));
      }

      const enumSchema = z.enum([optionValues[0], ...optionValues.slice(1)] as [string, ...string[]], {
        errorMap: () => ({ message: `${field.label} is required` }),
      });

      if (field.required) {
        return enumSchema;
      }
      return enumSchema.optional().nullable().or(z.literal(''));
    }

    case 'money':
    case 'number': {
      const isMoney = field.type === 'money';
      const formatBound = (val: number): string =>
        isMoney ? `₹${formatIndianCurrency(val)}` : String(val);

      let numSchema = z.number({
        required_error: `${field.label} is required`,
        invalid_type_error: `${field.label} must be a valid number`,
      });

      if (field.min !== undefined) {
        numSchema = numSchema.min(
          field.min,
          `${field.label} must be at least ${formatBound(field.min)}`
        );
      }

      if (field.max !== undefined) {
        numSchema = numSchema.max(
          field.max,
          `${field.label} must be at most ${formatBound(field.max)}`
        );
      }

      if (field.required) {
        return z.preprocess((val) => {
          if (val === '' || val === null || val === undefined) return undefined;
          const num = typeof val === 'number' ? val : Number(val);
          return isNaN(num) ? val : num;
        }, numSchema);
      }

      return z.preprocess((val) => {
        if (val === '' || val === null || val === undefined) return undefined;
        const num = typeof val === 'number' ? val : Number(val);
        return isNaN(num) ? val : num;
      }, numSchema.optional().nullable());
    }

    case 'date': {
      if (field.required) {
        return z
          .string({ required_error: `${field.label} is required` })
          .trim()
          .min(1, `${field.label} is required`);
      }
      return z.string().optional().nullable().or(z.literal(''));
    }

    case 'boolean': {
      if (field.required) {
        return z.boolean({
          required_error: `${field.label} is required`,
          invalid_type_error: `${field.label} must be a boolean`,
        });
      }
      return z.boolean().optional().default(false);
    }

    case 'text':
    default: {
      if (field.required) {
        return z
          .string({ required_error: `${field.label} is required` })
          .trim()
          .min(1, `${field.label} is required`);
      }
      return z.string().optional().nullable().or(z.literal(''));
    }
  }
}

export function toZodSchema(fields: GoalFieldSpec[]): z.ZodObject<Record<string, z.ZodTypeAny>> {
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const field of fields) {
    shape[field.key] = buildFieldSchema(field);
  }
  return z.object(shape);
}
