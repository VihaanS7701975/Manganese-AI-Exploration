import React from 'react';
import { X, Home } from 'lucide-react';

// Compact per-feature button dock for the left side of the map. Purely
// presentational/generic: App.jsx supplies each feature's exact existing
// content unchanged via `sections` ({ key, emoji, label, tooltip,
// description, content, width? } for a togglable panel, or { key, emoji,
// label, tooltip, isAction, onAction, disabled } for an instant action like
// the Download export) -- this component owns none of that business logic,
// only the button column, which single section is open, and the polished
// flyout panel chrome (title/description/close). `width` optionally
// overrides the default flyout width (e.g. a narrower panel for a compact
// list). Only one panel renders at a time, and the map stays visible
// everywhere else.
export default function SidebarMenu({ sections, activeKey, onToggle, onHome }) {
  const active = sections.find((s) => !s.isAction && s.key === activeKey);

  return (
    <div className="absolute top-20 left-4 z-30 flex items-start gap-2">
      {/* BUTTON COLUMN -- fixed compact width, consistent height/spacing.
          Label left-aligned, icon right-aligned (justify-between). */}
      <div className="pointer-events-auto flex flex-col gap-1.5 w-40 shrink-0">
        {/* HOME -- returns to the landing/entry screen via the app's
            existing entered/landing state (no reload, no data change). */}
        {onHome && (
          <button
            onClick={onHome}
            title="Return to home / landing page"
            className="group flex items-center justify-between gap-1.5 w-full rounded-lg border px-2.5 py-1.5 text-[10px] font-semibold text-left shadow-md transition-all duration-150 ease-out cursor-pointer bg-black/60 border-amber-400/50 text-amber-300 hover:bg-amber-400/10 hover:border-amber-300/80 hover:text-amber-100 hover:shadow-[0_0_12px_rgba(250,204,21,0.25)] hover:-translate-y-0.5"
          >
            <span className="truncate">Home</span>
            <Home className="w-3.5 h-3.5 shrink-0" />
          </button>
        )}
        {sections.map((section) => {
          const isActive = !section.isAction && section.key === activeKey;
          const dimmed = activeKey && !isActive;
          return (
            <button
              key={section.key}
              onClick={() => (section.isAction ? section.onAction?.() : onToggle(section.key))}
              disabled={section.disabled}
              title={section.tooltip ?? section.label}
              className={`group flex items-center justify-between gap-1.5 w-full rounded-lg border px-2.5 py-1.5 text-[10px] font-semibold text-left shadow-md transition-all duration-150 ease-out cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed disabled:translate-y-0 disabled:hover:translate-y-0 ${
                isActive
                  ? 'bg-black/70 border-amber-300 text-amber-200 shadow-[0_0_14px_rgba(250,204,21,0.35)]'
                  : `bg-black/60 border-amber-400/50 text-amber-300 hover:bg-amber-400/10 hover:border-amber-300/80 hover:text-amber-100 hover:shadow-[0_0_12px_rgba(250,204,21,0.25)] hover:-translate-y-0.5 ${
                      dimmed ? 'opacity-70' : 'opacity-100'
                    }`
              }`}
            >
              <span className="truncate">{section.label}</span>
              <span className="text-sm leading-none shrink-0">{section.emoji}</span>
            </button>
          );
        })}
      </div>

      {/* FLYOUT PANEL -- one polished GIS card beside the buttons, map stays
          visible everywhere else. Re-mounts (and briefly animates in) each
          time a different section opens; closing just unmounts. */}
      {active && (
        <div
          key={active.key}
          className={`pointer-events-auto ${active.width ?? 'w-80 md:w-[22rem]'} max-w-[calc(100vw-14rem)] max-h-[75vh] flex flex-col gis-lavender-card shadow-2xl overflow-hidden`}
          style={{ animation: 'menu-panel-in 220ms ease-out' }}
        >
          <div className="flex items-start justify-between gap-2 px-3.5 py-2.5 border-b border-purple-500/20 shrink-0">
            <div className="min-w-0">
              <h2 className="flex items-center gap-1.5 text-xs font-bold font-sans uppercase tracking-wider text-white">
                <span>{active.emoji}</span>
                <span className="truncate">{active.label}</span>
              </h2>
              {active.description && (
                <p className="text-[10px] font-sans text-slate-300 mt-0.5 leading-snug">
                  {active.description}
                </p>
              )}
            </div>
            <button
              onClick={() => onToggle(active.key)}
              className="shrink-0 p-1 rounded-full bg-slate-950/80 hover:bg-purple-500/30 text-slate-300 hover:text-white border border-purple-500/30 transition-colors duration-150 cursor-pointer"
              title="Close"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar p-3 flex flex-col gap-2.5">
            {active.content}
          </div>
        </div>
      )}
    </div>
  );
}
