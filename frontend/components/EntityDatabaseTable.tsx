'use client';

import React, { useState } from 'react';
import {
  Database,
  Search,
  Filter,
  Plus,
  Trash2,
  Check,
  Download,
  ShieldAlert,
  ArrowUpDown
} from 'lucide-react';
import { DetectedEntity } from '../lib/types';
import { downloadTextFile } from '../lib/restore';

interface EntityDatabaseTableProps {
  entities: DetectedEntity[];
  onToggleEntity: (entityId: string) => void;
  onRemoveEntity: (entityId: string) => void;
  onAddManualEntity: (text: string) => void;
}

export const EntityDatabaseTable: React.FC<EntityDatabaseTableProps> = ({
  entities,
  onToggleEntity,
  onRemoveEntity,
  onAddManualEntity,
}) => {
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedType, setSelectedType] = useState<string>('ALL');
  const [newTerm, setNewTerm] = useState<string>('');

  const types = Array.from(new Set(entities.map((e) => e.type)));

  const filtered = entities.filter((ent) => {
    if (selectedType !== 'ALL' && ent.type !== selectedType) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        ent.text.toLowerCase().includes(q) ||
        ent.placeholder.toLowerCase().includes(q) ||
        ent.type.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTerm.trim()) return;
    onAddManualEntity(newTerm.trim());
    setNewTerm('');
  };

  const handleExportCSV = () => {
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
    downloadTextFile(csvContent, 'pii-entities-database.csv');
  };

  return (
    <div className="space-y-4">
      {/* Table Toolbar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
        <div className="flex items-center space-x-2 w-full sm:w-auto">
          {/* Search */}
          <div className="relative flex-1 sm:w-64">
            <Search className="w-3.5 h-3.5 text-[#787774] absolute left-2.5 top-2.5" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search entities or tokens..."
              className="w-full text-xs pl-8 pr-3 py-1.5 rounded-lg border border-[#e9e9e7] focus:outline-none focus:ring-1 focus:ring-[#37352f] bg-white"
            />
          </div>

          {/* Type Filter */}
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="text-xs px-2.5 py-1.5 rounded-lg border border-[#e9e9e7] bg-white text-[#37352f] focus:outline-none"
          >
            <option value="ALL">All Types ({entities.length})</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center space-x-2 w-full sm:w-auto justify-end">
          {/* Add Custom Redaction Term */}
          <form onSubmit={handleAddSubmit} className="flex items-center space-x-1">
            <input
              type="text"
              value={newTerm}
              onChange={(e) => setNewTerm(e.target.value)}
              placeholder="+ Add redaction term..."
              className="text-xs px-2.5 py-1.5 rounded-lg border border-[#e9e9e7] bg-white focus:outline-none focus:ring-1 focus:ring-[#37352f] w-40 sm:w-48"
            />
            <button
              type="submit"
              disabled={!newTerm.trim()}
              className="p-1.5 bg-[#37352f] text-white rounded-lg hover:bg-[#5f5e5b] disabled:opacity-40 cursor-pointer"
              title="Add term"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </form>

          <button
            onClick={handleExportCSV}
            className="flex items-center space-x-1 px-2.5 py-1.5 rounded-lg border border-[#e9e9e7] hover:bg-[#efefed] text-[#37352f] transition-colors cursor-pointer"
            title="Export CSV"
          >
            <Download className="w-3.5 h-3.5 text-[#787774]" />
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      {/* Notion Database Table */}
      <div className="bg-white border border-[#e9e9e7] rounded-xl overflow-hidden shadow-2xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#f7f7f5] border-b border-[#e9e9e7] text-[#787774] font-semibold">
                <th className="py-2.5 px-3 w-12 text-center">Status</th>
                <th className="py-2.5 px-3">Original Sensitive Value</th>
                <th className="py-2.5 px-3">PII Classification</th>
                <th className="py-2.5 px-3">Jargon Replacement</th>
                <th className="py-2.5 px-3">Confidence</th>
                <th className="py-2.5 px-3">Source</th>
                <th className="py-2.5 px-3 w-16 text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#e9e9e7]/70 font-sans">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-[#787774] text-xs">
                    No entities found matching filters.
                  </td>
                </tr>
              ) : (
                filtered.map((ent) => (
                  <tr
                    key={ent.id}
                    className={`hover:bg-[#f7f7f5]/80 transition-colors ${
                      !ent.is_active ? 'opacity-50 bg-[#fafafa]' : ''
                    }`}
                  >
                    {/* Toggle Status Checkbox */}
                    <td className="py-2 px-3 text-center">
                      <input
                        type="checkbox"
                        checked={ent.is_active}
                        onChange={() => onToggleEntity(ent.id)}
                        className="rounded border-[#e9e9e7] text-indigo-600 focus:ring-0 cursor-pointer w-3.5 h-3.5"
                      />
                    </td>

                    {/* Sensitive Text */}
                    <td className="py-2 px-3 font-medium text-[#37352f] max-w-xs truncate">
                      {ent.text}
                    </td>

                    {/* Type Tag */}
                    <td className="py-2 px-3">
                      <span className="inline-block text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                        {ent.type}
                      </span>
                    </td>

                    {/* Jargon Token */}
                    <td className="py-2 px-3">
                      <span className="font-mono text-xs font-bold text-indigo-700 bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded">
                        {ent.placeholder}
                      </span>
                    </td>

                    {/* Confidence */}
                    <td className="py-2 px-3 font-mono text-[11px] text-[#787774]">
                      {(ent.confidence * 100).toFixed(0)}%
                    </td>

                    {/* Origin */}
                    <td className="py-2 px-3">
                      <span
                        className={`text-[10px] font-medium px-2 py-0.5 rounded ${
                          ent.is_manual
                            ? 'bg-purple-100 text-purple-800'
                            : 'bg-emerald-100 text-emerald-800'
                        }`}
                      >
                        {ent.is_manual ? 'Manual Highlight' : 'Auto Detect'}
                      </span>
                    </td>

                    {/* Delete Action */}
                    <td className="py-2 px-3 text-center">
                      <button
                        onClick={() => onRemoveEntity(ent.id)}
                        className="text-[#787774] hover:text-rose-600 p-1 rounded hover:bg-rose-50 transition-colors cursor-pointer"
                        title="Delete this entity"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Table Footer */}
        <div className="px-4 py-2.5 bg-[#f7f7f5] border-t border-[#e9e9e7] flex items-center justify-between text-xs text-[#787774]">
          <span>
            Showing <strong className="text-[#37352f]">{filtered.length}</strong> of{' '}
            <strong className="text-[#37352f]">{entities.length}</strong> total entities
          </span>
          <span className="font-mono text-[11px]">
            {entities.filter((e) => e.is_active).length} active jargon tokens
          </span>
        </div>
      </div>
    </div>
  );
};
