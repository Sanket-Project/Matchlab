import React from "react";
import { Globe, Flag, Trophy } from "lucide-react";

export type NavTab = "world" | "f1" | "matches";

interface NavigationProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  matchesCount?: number;
  liveMatchesCount?: number;
}

export const Navigation: React.FC<NavigationProps> = ({
  currentTab,
  onSelectTab,
  liveMatchesCount = 0,
}) => {
  const tabs = [
    {
      id: "world" as NavTab,
      label: "WORLD",
      icon: Globe,
      description: "Markets, AI briefing, events & news",
    },
    {
      id: "f1" as NavTab,
      label: "FORMULA 1",
      icon: Flag,
      description: "Standings, Las Vegas GP & calendar",
    },
    {
      id: "matches" as NavTab,
      label: "MATCHES",
      icon: Trophy,
      description: "Football & Cricket scores",
      badge: liveMatchesCount > 0 ? `${liveMatchesCount} LIVE` : undefined,
    },
  ];

  return (
    <>
      {/* Desktop Top Tabs */}
      <nav
        aria-label="Primary sections"
        className="hidden md:flex items-center gap-2 border-b border-border bg-surface/80 backdrop-blur-md px-6 py-2 sticky top-[65px] z-30"
      >
        <div className="max-w-7xl mx-auto w-full flex items-center justify-between">
          <div className="flex items-center gap-1">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = currentTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => onSelectTab(tab.id)}
                  className={`touch-target-44 px-4 py-2 rounded-md font-semibold text-xs tracking-wider transition-all flex items-center gap-2 relative ${
                    isActive
                      ? "bg-accent text-white shadow-sm"
                      : "text-text-secondary hover:text-text-primary hover:bg-muted/60"
                  }`}
                  aria-current={isActive ? "page" : undefined}
                >
                  <Icon className="w-4 h-4" />
                  <span>{tab.label}</span>
                  {tab.badge && (
                    <span
                      className={`text-[10px] font-bold px-1.5 py-0.2 rounded-full uppercase ${
                        isActive ? "bg-white text-accent" : "bg-red-500 text-white animate-pulse"
                      }`}
                    >
                      {tab.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <div className="text-xs text-text-tertiary hidden lg:block">
            {tabs.find((t) => t.id === currentTab)?.description}
          </div>
        </div>
      </nav>

      {/* Mobile Bottom Tab Bar (Fixed, 44px min touch targets, safe area inset) */}
      <nav
        aria-label="Mobile primary navigation"
        className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-surface/95 backdrop-blur-lg border-t border-border shadow-lg safe-area-bottom"
      >
        <div className="grid grid-cols-3 gap-1 px-2 py-1">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = currentTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => onSelectTab(tab.id)}
                className={`touch-target-44 flex flex-col items-center justify-center gap-1 rounded-lg transition-colors relative ${
                  isActive ? "text-accent font-bold" : "text-text-secondary hover:text-text-primary"
                }`}
                aria-current={isActive ? "page" : undefined}
              >
                <div className="relative">
                  <Icon className={`w-5 h-5 ${isActive ? "stroke-[2.5]" : "stroke-[1.75]"}`} />
                  {tab.badge && (
                    <span className="absolute -top-1 -right-2 w-2 h-2 rounded-full bg-red-500" />
                  )}
                </div>
                <span className="text-[11px] tracking-wide">{tab.label}</span>
                {isActive && (
                  <span className="w-8 h-0.5 rounded-full bg-accent absolute top-0" />
                )}
              </button>
            );
          })}
        </div>
      </nav>
    </>
  );
};
