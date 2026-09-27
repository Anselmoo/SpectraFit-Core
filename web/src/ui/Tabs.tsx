/**
 * Tabs — underline-only destination switcher.
 *
 * Ported from the design handbook's navigation Tabs component (DesignSync
 * project 055588fe-eb37-44e5-a211-7226ba4b5f4c, components/navigation/Tabs).
 * Tabs.prompt.md's own usage example is a Standing/Evidence two-tab
 * switcher and its Anatomy section is explicit: "A row of mono,
 * letter-spaced labels over a hairline, with a 2px accent underline marking
 * the active tab — no pill/segmented-control background; the underline
 * alone carries state." This file is that visual spec, applied to real
 * markup — nothing here invents a look the handbook didn't already spell out.
 *
 * Two deliberate extensions beyond the handbook source (both called out so
 * they read as documented additions, not silent drift):
 *
 *  1. Real ARIA tab semantics. The handbook's Tabs.jsx is plain unlabelled
 *     `<button>`s, and Tabs.prompt.md flags this itself: "for real
 *     screen-reader tab semantics, the call site should add
 *     role="tablist"/"tab"/aria-selected/role="tabpanel" wiring before this
 *     ships in a page that needs it; flag if you want that baked into the
 *     component itself." This is exactly such a page (top-level app nav),
 *     so it's baked in here: role="tablist" on the container, role="tab" +
 *     aria-selected + roving tabindex + arrow/Home/End key navigation on
 *     each button, and a companion <TabPanel> for role="tabpanel".
 *  2. `blurb?: string` per tab. The handbook's TabItem has no slot for a
 *     secondary description line; this app's nav shows a one-line blurb
 *     under each destination label, so the prop is added here as a
 *     documented, optional extension.
 */
import { useRef } from "react";
import type { CSSProperties, KeyboardEvent, ReactElement, ReactNode } from "react";

export interface TabItem<T extends string = string> {
  id: T;
  label: string;
  /** Optional one-line description rendered under the label (handbook extension, not present in the source Tabs.jsx). */
  blurb?: string;
}

export interface TabsProps<T extends string = string> {
  tabs: TabItem<T>[];
  /** Currently active tab id — Tabs is a controlled component; the caller owns the state (e.g. hash-routed nav). */
  activeId: T;
  onChange: (id: T) => void;
  /** Accessible name for the tablist landmark, e.g. "Narrative navigation". */
  "aria-label"?: string;
  /** Prefix for the generated tab/panel ids used to pair aria-controls with aria-labelledby. */
  idBase?: string;
}

/** Stable id for a tab's `<button role="tab">`, shared with TabPanel's aria-labelledby. */
export function tabElementId(idBase: string, id: string): string {
  return `${idBase}-tab-${id}`;
}

/** Stable id for a tab's `role="tabpanel"`, shared with Tabs' aria-controls. */
export function tabPanelElementId(idBase: string, id: string): string {
  return `${idBase}-panel-${id}`;
}

export function Tabs<T extends string = string>({
  tabs,
  activeId,
  onChange,
  idBase = "tabs",
  ...ariaProps
}: TabsProps<T>): ReactElement {
  const buttonRefs = useRef<Array<HTMLButtonElement | null>>([]);

  function activate(index: number) {
    const wrapped = (index + tabs.length) % tabs.length;
    const target = tabs[wrapped];
    buttonRefs.current[wrapped]?.focus();
    onChange(target.id);
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    switch (event.key) {
      case "ArrowRight":
        event.preventDefault();
        activate(index + 1);
        break;
      case "ArrowLeft":
        event.preventDefault();
        activate(index - 1);
        break;
      case "Home":
        event.preventDefault();
        activate(0);
        break;
      case "End":
        event.preventDefault();
        activate(tabs.length - 1);
        break;
      default:
        break;
    }
  }

  return (
    <div
      role="tablist"
      aria-label={ariaProps["aria-label"]}
      style={{
        display: "flex",
        gap: "var(--space-1)",
        borderBottom: "1px solid var(--border-subtle)",
        width: "100%",
      }}
    >
      {tabs.map((tab, index) => {
        const active = tab.id === activeId;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              buttonRefs.current[index] = el;
            }}
            id={tabElementId(idBase, tab.id)}
            role="tab"
            type="button"
            aria-selected={active}
            aria-controls={tabPanelElementId(idBase, tab.id)}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 2,
              padding: "var(--space-2) var(--space-3)",
              background: "transparent",
              border: "none",
              borderBottom: active ? "2px solid var(--system-blue)" : "2px solid transparent",
              marginBottom: "-1px",
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              fontSize: "0.78rem",
              fontWeight: 600,
              letterSpacing: "0.03em",
              color: active ? "var(--system-blue)" : "var(--text-secondary)",
              transition: "color var(--motion-fast), border-color var(--motion-fast)",
            }}
          >
            <span>{tab.label}</span>
            {tab.blurb ? (
              <span
                style={{
                  fontFamily: "var(--font-body)",
                  fontSize: "0.72rem",
                  fontWeight: 400,
                  letterSpacing: "normal",
                  opacity: active ? 0.85 : 0.65,
                  color: active ? "var(--system-blue)" : "var(--text-secondary)",
                }}
              >
                {tab.blurb}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({
  id,
  idBase = "tabs",
  style,
  children,
}: {
  id: string;
  idBase?: string;
  style?: CSSProperties;
  children: ReactNode;
}): ReactElement {
  return (
    <div id={tabPanelElementId(idBase, id)} role="tabpanel" aria-labelledby={tabElementId(idBase, id)} tabIndex={0} style={style}>
      {children}
    </div>
  );
}
