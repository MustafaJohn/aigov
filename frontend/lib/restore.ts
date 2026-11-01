import { Block, DetectedEntity } from './types';

export interface RestoreResult {
  restoredText: string;
  totalPlaceholders: number;
  restoredCount: number;
  unrestoredTokens: string[];
}

/**
 * Generates protected document text with typed semantic placeholders (e.g. [PERSON 1], [ORG 2]).
 * Replaces active entities from right to left so substring indices remain valid.
 */
export function generateProtectedBlockText(
  block: Block,
  entities: DetectedEntity[]
): string {
  const blockEntities = entities
    .filter((e) => e.block_id === block.id && e.is_active)
    .sort((a, b) => b.start - a.start);

  let text = block.text;

  for (const ent of blockEntities) {
    const replacement = ent.placeholder || '[PROTECTED]';
    text = text.substring(0, ent.start) + replacement + text.substring(ent.end);
  }

  return text;
}

/**
 * Builds the full redacted document text to be transmitted to the AI Assistant or downloaded.
 * Excludes hidden blocks unless lawyer opted in.
 */
export function compileProtectedDocument(
  blocks: Block[],
  entities: DetectedEntity[],
  includeHidden: boolean = false
): string {
  const eligibleBlocks = blocks.filter((b) => {
    if (b.visibility === 'visible') return true;
    if (includeHidden && (b.visibility === 'hidden' || b.visibility === 'metadata')) {
      return true;
    }
    return false;
  });

  return eligibleBlocks
    .map((b) => generateProtectedBlockText(b, entities))
    .join('\n\n');
}

/**
 * Generates the next sequential typed placeholder for newly added manual highlights.
 * Universal fallback: works for any standard or custom legal entity type.
 */
export function generateTypedPlaceholder(
  entityType: string = 'PERSON',
  existingEntities: DetectedEntity[] = []
): string {
  let prefix = entityType.replace(/_/g, ' ').toUpperCase();
  if (prefix === 'ORGANISATION' || prefix === 'ORGANIZATION') prefix = 'ORG';
  else if (prefix === 'ACCOUNT NUMBER') prefix = 'ACCOUNT';
  else if (prefix === 'MONETARY AMOUNT') prefix = 'AMOUNT';
  else if (prefix === 'PHYSICAL ADDRESS') prefix = 'ADDRESS';
  else if (prefix === 'UK POSTCODE') prefix = 'POSTCODE';
  else if (prefix === 'MATTER REF') prefix = 'MATTER';
  else if (prefix === 'DATE OF BIRTH') prefix = 'DATE';

  const sameTypeCount = existingEntities.filter((e) => {
    const ph = e.placeholder || '';
    return ph.startsWith(`[${prefix} `) || e.type.toUpperCase() === entityType.toUpperCase();
  }).length;

  return `[${prefix} ${sameTypeCount + 1}]`;
}

/**
 * Backwards compatibility helper for existing manual highlight triggers.
 */
export function generateNextJargon(existingEntities: DetectedEntity[]): string {
  return generateTypedPlaceholder('PERSON', existingEntities);
}

/**
 * Restores AI-generated text containing typed placeholders back to original legal entities.
 * Returns the restored text, count of restored tokens, and list of any unrestored tokens.
 */
export function restoreProtectedText(
  aiText: string,
  entities: DetectedEntity[]
): RestoreResult {
  if (!aiText) {
    return { restoredText: '', totalPlaceholders: 0, restoredCount: 0, unrestoredTokens: [] };
  }

  // Find all placeholder tokens present in the AI text
  const placeholderRegex = /(?:\[[A-Z_\s0-9]+\]|XXX_\d+|XYZ_\d+)/g;
  const matches = aiText.match(placeholderRegex) || [];
  const totalPlaceholders = matches.length;

  let restoredText = aiText;
  let restoredCount = 0;

  // Build a unique map of placeholder -> original text for active entities
  const placeholderMap = new Map<string, string>();
  for (const ent of entities) {
    if (ent.is_active && ent.placeholder && ent.text) {
      if (!placeholderMap.has(ent.placeholder)) {
        placeholderMap.set(ent.placeholder, ent.text);
      }
    }
  }

  // Sort placeholders by length descending to prevent partial substring collisions
  const sortedPlaceholders = Array.from(placeholderMap.keys()).sort((a, b) => b.length - a.length);

  for (const ph of sortedPlaceholders) {
    const originalText = placeholderMap.get(ph)!;
    if (restoredText.includes(ph)) {
      const occurrences = (restoredText.match(new RegExp(escapeRegExp(ph), 'g')) || []).length;
      restoredCount += occurrences;
      restoredText = restoredText.split(ph).join(originalText);
    }
  }

  // Check for any remaining unrestored tokens
  const remainingMatches = restoredText.match(placeholderRegex) || [];
  const unrestoredTokens = Array.from(new Set(remainingMatches));

  return {
    restoredText,
    totalPlaceholders,
    restoredCount,
    unrestoredTokens,
  };
}

function escapeRegExp(string: string): string {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Browser download helper for text/markdown files.
 */
export function downloadTextFile(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
