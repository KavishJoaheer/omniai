/**
 * Tooltip — shows a help popover on hover / focus.
 *
 * Usage:
 *   <Tooltip text="Higher = more vector-based, lower = more keyword-based">
 *     <label>Vector weight</label>
 *   </Tooltip>
 *
 * Or inline help icon:
 *   <HelpTip text="This is stored encrypted and never shown again." />
 */
import { useRef, useState } from "react";

interface TooltipProps {
  text: string;
  children: React.ReactNode;
}

export function Tooltip({ text, children }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  return (
    <span
      ref={ref}
      className="tooltip-wrap"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocusCapture={() => setVisible(true)}
      onBlurCapture={() => setVisible(false)}
    >
      {children}
      {visible && (
        <span className="tooltip-bubble" role="tooltip">
          {text}
        </span>
      )}
    </span>
  );
}

/** Standalone "?" icon with a tooltip — drop it next to any label. */
export function HelpTip({ text }: { text: string }) {
  return (
    <Tooltip text={text}>
      <span className="help-tip" aria-label={`Help: ${text}`} tabIndex={0}>
        ?
      </span>
    </Tooltip>
  );
}
