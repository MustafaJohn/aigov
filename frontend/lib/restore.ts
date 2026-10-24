import { Block, DetectedEntity } from './types';

/**
 * Generates protected document text with random jargon (XXX / XYZ) replacements.
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
    // Replace with random jargon token (e.g. XXX_1, XYZ_2) - never '[REDACTED]'
    const jargonReplacement = ent.placeholder || 'XXX';
    text = text.substring(0, ent.start) + jargonReplacement + text.substring(ent.end);
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
 * Helper to generate the next unique jargon token (e.g., 'XXX_5' or 'XYZ_6')
 * for newly added manual highlights.
 */
export function generateNextJargon(existingEntities: DetectedEntity[]): string {
  const count = existingEntities.length + 1;
  const prefix = count % 2 !== 0 ? 'XXX' : 'XYZ';
  return `${prefix}_${count}`;
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
