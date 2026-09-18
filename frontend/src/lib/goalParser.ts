import type { components } from '@/api/types.gen';

type GoalFieldSpec = components['schemas']['GoalFieldSpec'];

const STOP_WORDS = new Set([
  'loan',
  'card',
  'policy',
  'cover',
  'account',
  'investment',
  'update',
  'status',
  'verification',
  'plan',
  'option',
  'paytm',
  'pro',
  'max',
  'elite',
  'with',
  'from',
  'need',
  'want',
  'open',
  'apply',
]);

/**
 * Extracts structured goal values from free-form natural language text deterministically.
 * Matches backend MockAI.parse_goal extraction semantics across all 6 financial journeys.
 */
export function parseGoalFromNaturalLanguage(
  naturalLanguage: string,
  goalSchema: GoalFieldSpec[]
): Record<string, unknown> {
  const rawText = naturalLanguage.toLowerCase().trim();
  if (!rawText || !goalSchema || goalSchema.length === 0) return {};

  // Normalize commas in formatted numbers e.g. "2,50,000" -> "250000"
  const text = rawText.replace(/(\d),(\d)/g, '$1$2');
  const extracted: Record<string, unknown> = {};

  // 1. Extract all numbers and unit-scaled numbers (lakhs, crores, thousands)
  const numbers = (text.match(/\b\d+\b/g) || []).map((n) => parseInt(n, 10));
  const croreMatches = text.match(/(\d+(?:\.\d+)?)\s*(?:crore|cr)\b/i);
  const lakhMatches = text.match(/(\d+(?:\.\d+)?)\s*(?:lakh|lac|l)\b/i);
  const kMatches = text.match(/(\d+(?:\.\d+)?)\s*k\b/i);

  let parsedAmount: number | undefined;
  if (croreMatches) {
    parsedAmount = Math.round(parseFloat(croreMatches[1]) * 10000000);
  } else if (lakhMatches) {
    parsedAmount = Math.round(parseFloat(lakhMatches[1]) * 100000);
  } else if (kMatches) {
    parsedAmount = Math.round(parseFloat(kMatches[1]) * 1000);
  } else if (numbers.length > 0) {
    parsedAmount = numbers.find((n) => n >= 500) ?? numbers[0];
  }

  for (const spec of goalSchema) {
    const k = spec.key;

    if (
      spec.type === 'money' ||
      (spec.type === 'number' &&
        (k.includes('amount') ||
          k.includes('limit') ||
          k.includes('deposit') ||
          k.includes('sum') ||
          k.includes('insured') ||
          k.includes('sip') ||
          k.includes('balance') ||
          k.includes('target')))
    ) {
      if (parsedAmount !== undefined) {
        let val = parsedAmount;
        if (spec.min !== undefined && spec.min !== null) val = Math.max(val, spec.min);
        if (spec.max !== undefined && spec.max !== null) val = Math.min(val, spec.max);
        extracted[k] = val;
      }
    } else if (
      spec.type === 'number' &&
      (k.includes('tenure') || k.includes('duration') || k.includes('term') || k.includes('year') || k.includes('month'))
    ) {
      const yearMatches = text.match(/(\d+)\s*(?:years?|yrs?)\b/i);
      const monthMatches = text.match(/(\d+)\s*(?:months?|mos?|m)\b/i);

      if (k.includes('year') && yearMatches) {
        extracted[k] = parseInt(yearMatches[1], 10);
      } else if (k.includes('month') && monthMatches) {
        extracted[k] = parseInt(monthMatches[1], 10);
      } else if (k.includes('tenure') && yearMatches) {
        extracted[k] = parseInt(yearMatches[1], 10) * 12;
      } else {
        const candidate = numbers.find(
          (n) => n >= (spec.min ?? 1) && n <= (spec.max ?? 84) && n !== parsedAmount
        );
        if (candidate !== undefined) {
          extracted[k] = candidate;
        }
      }
    } else if (spec.type === 'enum' && spec.options) {
      let chosenOpt: unknown;

      // 1. Check high-priority journey-specific domain aliases
      if (text.includes('lump') || text.includes('lumpsum') || text.includes('one time') || text.includes('one-time')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('LUMP'))?.value;
      } else if (text.includes('sip') || text.includes('monthly sip') || text.includes('per month')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('SIP'))?.value;
      } else if (text.includes('medic') || text.includes('health') || text.includes('hospital') || text.includes('doctor')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('MEDIC') || String(o.value).includes('HEALTH'))?.value;
      } else if (text.includes('renovat') || text.includes('home') || text.includes('house')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('HOME') || String(o.value).includes('RENOVAT'))?.value;
      } else if (text.includes('educat') || text.includes('study') || text.includes('college') || text.includes('school')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('EDUCAT'))?.value;
      } else if (text.includes('cashback')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('CASHBACK'))?.value;
      } else if (text.includes('reward')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('REWARD'))?.value;
      } else if (text.includes('travel') || text.includes('flight') || text.includes('trip')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('TRAVEL'))?.value;
      } else if (text.includes('family') || text.includes('floater') || text.includes('parents')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('FAMILY'))?.value;
      } else if (text.includes('individual') || text.includes('self') || text.includes('single')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('INDIVIDUAL'))?.value;
      } else if (text.includes('salary') || text.includes('corporate') || text.includes('payroll')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('SALARY'))?.value;
      } else if (text.includes('saving') || text.includes('digital') || text.includes('zero balance')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('SAVING'))?.value;
      } else if (text.includes('upgrade') || text.includes('limit') || text.includes('increase')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('UPGRADE') || String(o.value).includes('LIMIT'))?.value;
      } else if (text.includes('address') || text.includes('location') || text.includes('shifting')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('ADDRESS'))?.value;
      } else if (text.includes('periodic') || text.includes('rekyc') || text.includes('re-kyc')) {
        chosenOpt = spec.options.find((o) => String(o.value).includes('PERIODIC'))?.value;
      }

      // 2. Direct string containment
      if (chosenOpt === undefined) {
        for (const opt of spec.options) {
          const valStr = String(opt.value ?? '');
          const optVal = valStr.toLowerCase().replace(/_/g, ' ');
          const optLabel = opt.label.toLowerCase();
          if (
            text.includes(valStr.toLowerCase()) ||
            text.includes(optVal) ||
            text.includes(optLabel) ||
            optLabel
              .split(/\s+/)
              .filter((w) => !STOP_WORDS.has(w) && w.length > 3)
              .some((w) => text.includes(w))
          ) {
            chosenOpt = opt.value;
            break;
          }
        }
      }

      if (chosenOpt !== undefined) {
        extracted[k] = chosenOpt;
      }
    } else if (spec.type === 'boolean') {
      if (
        text.includes('yes') ||
        text.includes('true') ||
        text.includes('with') ||
        text.includes('agree') ||
        text.includes('co-applicant')
      ) {
        extracted[k] = true;
      } else if (text.includes('no') || text.includes('false') || text.includes('without')) {
        extracted[k] = false;
      }
    } else if (spec.type === 'text') {
      if (!extracted[k] && text.length > 0) {
        extracted[k] = 'Standard Application';
      }
    }
  }

  return extracted;
}
