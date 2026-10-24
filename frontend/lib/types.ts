export interface Span {
  start: number;
  end: number;
  source_ref?: string;
}

export interface Block {
  id: string;
  type: string;
  text: string;
  visibility: 'visible' | 'hidden' | 'deleted' | 'metadata' | 'non_printing';
  locator: Record<string, any>;
  spans?: Span[];
  confidence?: number;
  parent_id?: string | null;
  order: number;
}

export interface MetadataItem {
  key: string;
  value: string;
  source: string;
}

export interface ParseReport {
  status: 'READY' | 'READY_WITH_WARNINGS' | 'BLOCKED';
  summary: string;
  pages_or_sheets: number;
  total_blocks: number;
  warnings: string[];
  hidden_items_count: number;
  gate_reason?: string | null;
}

export interface SourceInfo {
  format: 'docx' | 'xlsx' | 'pdf' | 'txt' | 'unknown';
  filename: string;
  size_bytes: number;
  sha256: string;
  pages_or_sheets: number;
}

export interface DocumentIR {
  doc_id: string;
  source: SourceInfo;
  metadata: MetadataItem[];
  blocks: Block[];
  report: ParseReport;
}

export interface DetectedEntity {
  id: string;
  block_id: string;
  start: number;
  end: number;
  text: string;
  type: string;
  placeholder: string; // e.g. "XXX_1", "XYZ_2"
  confidence: number;
  is_active: boolean;
  is_manual?: boolean;
}

export interface DetectionResult {
  doc_id: string;
  entities: DetectedEntity[];
  total_entities: number;
  entities_by_type: Record<string, number>;
}

export interface LegalNote {
  id: string;
  title: string;
  content: string;
  created_at: string;
  category?: 'General' | 'Risk' | 'Strategy' | 'Obligations' | 'AI Insight';
}

export interface SelfPromptAction {
  id: string;
  title: string;
  badge: string;
  description: string;
  prompt: string;
}

export interface AIChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  promptTitle?: string;
}

export interface AuditRecord {
  id: string;
  doc_id: string;
  doc_sha256: string;
  timestamp: string;
  provider: string;
  model: string;
  entities_protected_count: number;
  outbound_verified: boolean;
}
