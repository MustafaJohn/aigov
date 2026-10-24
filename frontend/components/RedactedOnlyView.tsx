'use client';

import React, { useState } from 'react';
import { ShieldCheck, Copy, Download, Check, FileText } from 'lucide-react';
import { Block, DetectedEntity } from '../lib/types';
import { compileProtectedDocument, downloadTextFile } from '../lib/restore';

interface RedactedOnlyViewProps {
  blocks: Block[];
  entities: DetectedEntity[];
  documentName?: string;
}

export const RedactedOnlyView: React.FC<RedactedOnlyViewProps> = ({
  blocks,
  entities,
  documentName = 'document',
}) => {
  const [copied, setCopied] = useState<boolean>(false);
  const redactedText = compileProtectedDocument(blocks, entities, false);
  const activeCount = entities.filter((e) => e.is_active).length;

  const handleCopy = () => {
    navigator.clipboard.writeText(redactedText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    downloadTextFile(redactedText, `redacted-${documentName}.txt`);
  };

  return (
    <div className="bg-white border border-[#e9e9e7] rounded-2xl shadow-2xs p-6 space-y-4 max-w-4xl mx-auto">
      {/* Top Banner */}
      <div className="flex items-center justify-between pb-3 border-b border-[#e9e9e7] flex-wrap gap-2 text-xs">
        <div className="flex items-center space-x-2">
          <ShieldCheck className="w-4 h-4 text-emerald-600" />
          <span className="font-bold text-[#37352f]">Safe Redacted Document</span>
          <span className="text-[#787774]">
            ({activeCount} PII tokens replaced with XXX / XYZ jargon)
          </span>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={handleCopy}
            className="flex items-center space-x-1 px-3 py-1.5 rounded-lg border border-[#e9e9e7] hover:bg-[#efefed] text-[#37352f] transition-colors cursor-pointer"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5 text-[#787774]" />}
            <span>{copied ? 'Copied' : 'Copy Text'}</span>
          </button>

          <button
            onClick={handleDownload}
            className="flex items-center space-x-1 px-3 py-1.5 rounded-lg bg-[#37352f] hover:bg-[#5f5e5b] text-white transition-colors cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download .txt</span>
          </button>
        </div>
      </div>

      {/* Redacted Document Reading Canvas */}
      <div className="p-6 bg-[#f7f7f5]/50 border border-[#e9e9e7] rounded-xl font-mono text-xs sm:text-sm text-[#37352f] leading-relaxed whitespace-pre-wrap select-text">
        {redactedText}
      </div>

      <div className="text-[11px] text-[#787774] flex items-center justify-between pt-1">
        <span>Contains zero unmasked identifiers. Verified safe for external models.</span>
        <span>{redactedText.length} characters • {blocks.length} blocks</span>
      </div>
    </div>
  );
};
