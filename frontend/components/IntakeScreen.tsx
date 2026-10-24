'use client';

import React, { useState } from 'react';
import { UploadCloud, FileText, Sparkles, Shield, Loader2 } from 'lucide-react';
import { SYNTHETIC_LEGAL_DOC } from '../lib/syntheticSamples';

interface IntakeScreenProps {
  onFileUpload: (file: File) => Promise<void>;
  onSyntheticLoad: (content: string) => Promise<void>;
  isLoading: boolean;
}

export const IntakeScreen: React.FC<IntakeScreenProps> = ({
  onFileUpload,
  onSyntheticLoad,
  isLoading,
}) => {
  const [dragActive, setDragActive] = useState<boolean>(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setSelectedFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;
    await onFileUpload(selectedFile);
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Title & Introduction */}
      <div className="text-center space-y-2">
        <h2 className="text-2xl font-bold text-slate-900 tracking-tight">
          Document Intake & Redaction Gateway
        </h2>
        <p className="text-sm text-slate-600 max-w-xl mx-auto">
          Upload any legal document (.docx, .xlsx, .pdf, .txt). PII is automatically scanned and masked
          with random jargon (XXX / XYZ) so you can safely use AI.
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl p-6 sm:p-8 shadow-sm space-y-6">
        {/* Drag & Drop Upload Zone */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-xl p-10 text-center transition-all cursor-pointer ${
              dragActive
                ? 'border-indigo-500 bg-indigo-50/50'
                : selectedFile
                ? 'border-emerald-400 bg-emerald-50/20'
                : 'border-slate-300 hover:border-slate-400 bg-slate-50/40'
            }`}
          >
            <input
              type="file"
              id="file-upload"
              accept=".docx,.xlsx,.pdf,.txt"
              onChange={handleFileChange}
              className="sr-only"
            />
            <label htmlFor="file-upload" className="cursor-pointer space-y-3 block">
              <div className="w-14 h-14 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto shadow-2xs">
                <UploadCloud className="w-7 h-7" />
              </div>

              <div>
                <span className="font-semibold text-sm text-slate-800">
                  {selectedFile ? selectedFile.name : 'Choose a legal document or drag & drop here'}
                </span>
                <p className="text-xs text-slate-500 mt-1">
                  Supports Word (.docx), Excel (.xlsx), PDF (.pdf), and Text (.txt) up to 25MB
                </p>
              </div>

              {selectedFile && (
                <div className="inline-flex items-center space-x-1.5 text-xs text-emerald-700 bg-emerald-100/70 px-3 py-1 rounded-full font-medium">
                  <FileText className="w-3.5 h-3.5" />
                  <span>{(selectedFile.size / 1024).toFixed(1)} KB ready for safe intake</span>
                </div>
              )}
            </label>
          </div>

          <button
            type="submit"
            disabled={!selectedFile || isLoading}
            className={`w-full py-3 px-4 rounded-xl font-semibold text-sm shadow-sm transition-all flex items-center justify-center space-x-2 cursor-pointer ${
              selectedFile && !isLoading
                ? 'bg-indigo-600 hover:bg-indigo-700 text-white'
                : 'bg-slate-200 text-slate-400 cursor-not-allowed'
            }`}
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Safely Parsing & Inspecting Document...</span>
              </>
            ) : (
              <span>Proceed to Redaction Studio</span>
            )}
          </button>
        </form>

        {/* 1-Click Synthetic Document Tester */}
        <div className="pt-4 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-50/80 p-4 rounded-xl border border-slate-200">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-amber-100 text-amber-800 flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-xs font-semibold text-slate-900">Try 1-Click Synthetic Case</h4>
              <p className="text-[11px] text-slate-500">
                Instantly load a realistic UK commercial dispute memo with seeded names, bank details & addresses.
              </p>
            </div>
          </div>

          <button
            type="button"
            disabled={isLoading}
            onClick={() => onSyntheticLoad(SYNTHETIC_LEGAL_DOC)}
            className="text-xs font-semibold text-indigo-700 bg-white border border-indigo-200 hover:bg-indigo-50 px-4 py-2 rounded-lg transition-colors flex-shrink-0 shadow-2xs cursor-pointer"
          >
            Load Synthetic Case
          </button>
        </div>

        {/* Governance & Privacy Notice */}
        <div className="flex items-start space-x-2.5 text-xs text-slate-500 pt-1">
          <Shield className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
          <p>
            <strong>Local & Ephemeral:</strong> Raw documents are parsed in ephemeral memory.
            Client identifiers are replaced with random jargon before any AI prompt is sent.
          </p>
        </div>
      </div>
    </div>
  );
};
