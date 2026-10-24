'use client';

import React from 'react';
import {
  Download,
  X,
  FileText,
  Database,
  Edit3,
  Package,
  Check,
  ShieldCheck
} from 'lucide-react';
import { Block, DetectedEntity, LegalNote } from '../lib/types';
import { compileProtectedDocument, downloadTextFile } from '../lib/restore';

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  documentName?: string;
  blocks: Block[];
  entities: DetectedEntity[];
  notes: LegalNote[];
}

export const ExportModal: React.FC<ExportModalProps> = ({
  isOpen,
  onClose,
  documentName = 'document',
  blocks,
  entities,
  notes,
}) => {
  if (!isOpen) return null;

  const handleDownloadRedacted = () => {
    const text = compileProtectedDocument(blocks, entities, false);
    downloadTextFile(text, `redacted-${documentName}.txt`);
  };

  const handleDownloadEntitiesCSV = () => {
    const headers = ['Entity ID', 'Original Text', 'Type', 'Jargon Token', 'Status', 'Origin'];
    const rows = entities.map((e) => [
      e.id,
      `"${e.text.replace(/"/g, '""')}"`,
      e.type,
      e.placeholder,
      e.is_active ? 'Active' : 'Unhighlighted',
      e.is_manual ? 'Manual' : 'Auto',
    ]);
    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    downloadTextFile(csvContent, `entities-${documentName}.csv`);
  };

  const handleDownloadNotes = () => {
    if (notes.length === 0) return;
    const compiled = notes
      .map((n) => `# ${n.title} [${n.category || 'General'}]\n*Date: ${n.created_at}*\n\n${n.content}\n\n---\n`)
      .join('\n');
    downloadTextFile(compiled, `case-notes-${documentName}.md`);
  };

  const handleDownloadBundle = () => {
    const redactedText = compileProtectedDocument(blocks, entities, false);
    const activeEntities = entities.filter((e) => e.is_active);

    const bundle = `# LEXGATEWAY LEGAL MATTER BUNDLE
Document: ${documentName}
Export Date: ${new Date().toISOString()}
Status: Redacted with Random Jargon (XXX / XYZ)

---

## 1. REDACTED DOCUMENT TEXT
${redactedText}

---

## 2. PROTECTED PII ENTITIES (${activeEntities.length} active)
${activeEntities.map((e) => `- **${e.type}**: "${e.text}" replaced with \`${e.placeholder}\``).join('\n')}

---

## 3. CASE NOTES & LAWYER WORKSPACE (${notes.length} notes)
${notes.map((n) => `### ${n.title} (${n.category || 'General'})\n*${n.created_at}*\n${n.content}`).join('\n\n')}
`;

    downloadTextFile(bundle, `legal-bundle-${documentName}.md`);
  };

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-2xs flex items-center justify-center z-50 p-4 select-none animate-in fade-in duration-100">
      <div className="bg-white border border-[#e9e9e7] rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 text-[#37352f]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#e9e9e7] pb-3">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#37352f] text-white flex items-center justify-center">
              <Download className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-[#37352f]">Export & Download Hub</h3>
              <p className="text-xs text-[#787774]">Choose files to download to your local machine</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-[#efefed] text-[#787774] cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Export Options Cards */}
        <div className="space-y-2.5">
          {/* 1. Redacted Document */}
          <div className="flex items-center justify-between p-3.5 rounded-xl border border-[#e9e9e7] hover:border-[#37352f] transition-all bg-[#f7f7f5]/40">
            <div className="flex items-center space-x-3 truncate">
              <FileText className="w-5 h-5 text-indigo-600 flex-shrink-0" />
              <div className="truncate">
                <div className="font-semibold text-xs text-[#37352f] truncate">
                  Redacted Document (.txt)
                </div>
                <div className="text-[11px] text-[#787774] truncate">
                  All sensitive PII replaced with XXX / XYZ random jargon
                </div>
              </div>
            </div>

            <button
              onClick={handleDownloadRedacted}
              className="px-3 py-1.5 bg-white border border-[#e9e9e7] hover:bg-[#efefed] text-xs font-semibold rounded-lg shadow-2xs transition-colors cursor-pointer flex-shrink-0 ml-3"
            >
              Download
            </button>
          </div>

          {/* 2. PII Database CSV */}
          <div className="flex items-center justify-between p-3.5 rounded-xl border border-[#e9e9e7] hover:border-[#37352f] transition-all bg-[#f7f7f5]/40">
            <div className="flex items-center space-x-3 truncate">
              <Database className="w-5 h-5 text-emerald-600 flex-shrink-0" />
              <div className="truncate">
                <div className="font-semibold text-xs text-[#37352f] truncate">
                  Entity Database (.csv)
                </div>
                <div className="text-[11px] text-[#787774] truncate">
                  Manifest of all {entities.length} detected & manual tokens
                </div>
              </div>
            </div>

            <button
              onClick={handleDownloadEntitiesCSV}
              className="px-3 py-1.5 bg-white border border-[#e9e9e7] hover:bg-[#efefed] text-xs font-semibold rounded-lg shadow-2xs transition-colors cursor-pointer flex-shrink-0 ml-3"
            >
              Download
            </button>
          </div>

          {/* 3. Case Notes */}
          <div className="flex items-center justify-between p-3.5 rounded-xl border border-[#e9e9e7] hover:border-[#37352f] transition-all bg-[#f7f7f5]/40">
            <div className="flex items-center space-x-3 truncate">
              <Edit3 className="w-5 h-5 text-amber-600 flex-shrink-0" />
              <div className="truncate">
                <div className="font-semibold text-xs text-[#37352f] truncate">
                  Case Notes (.md)
                </div>
                <div className="text-[11px] text-[#787774] truncate">
                  {notes.length} saved legal observation and strategy pages
                </div>
              </div>
            </div>

            <button
              onClick={handleDownloadNotes}
              disabled={notes.length === 0}
              className="px-3 py-1.5 bg-white border border-[#e9e9e7] hover:bg-[#efefed] text-xs font-semibold rounded-lg shadow-2xs transition-colors cursor-pointer flex-shrink-0 ml-3 disabled:opacity-40"
            >
              Download
            </button>
          </div>

          {/* 4. Complete Case Bundle */}
          <div className="flex items-center justify-between p-3.5 rounded-xl border border-indigo-200 bg-indigo-50/30 transition-all">
            <div className="flex items-center space-x-3 truncate">
              <Package className="w-5 h-5 text-indigo-700 flex-shrink-0" />
              <div className="truncate">
                <div className="font-bold text-xs text-indigo-950 truncate">
                  Complete Matter Bundle (.md)
                </div>
                <div className="text-[11px] text-indigo-700 truncate">
                  Full combined archive: Redacted doc + PII manifest + Notes
                </div>
              </div>
            </div>

            <button
              onClick={handleDownloadBundle}
              className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer flex-shrink-0 ml-3"
            >
              Download Bundle
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
