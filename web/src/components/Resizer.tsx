/**
 * A draggable divider between two panes.
 *
 * Pointer events rather than mouse events, so a trackpad, a pen and a touch
 * screen all work from one code path, with pointer capture so a fast drag that
 * leaves the 4px hit area does not drop the gesture — which is the usual reason
 * a hand-rolled splitter feels broken.
 *
 * It is also a `separator` with arrow-key support. A resizable panel that can
 * only be sized with a mouse is not resizable for everyone, and the keyboard
 * path costs six lines.
 */
import { useCallback, useRef } from 'react';
import './Resizer.css';

export interface ResizerProps {
  /** Current width in px, for the accessible value and keyboard steps. */
  value: number;
  min: number;
  max: number;
  /**
   * Which side the panel being sized is on, relative to this divider.
   *
   * `top` makes the divider horizontal — the bottom panel is sized by the edge
   * ABOVE it, so dragging up grows it, which is the opposite sign from a
   * left-hand panel.
   */
  side: 'left' | 'right' | 'top';
  label: string;
  onChange: (width: number) => void;
}

const KEY_STEP = 16;

export default function Resizer({ value, min, max, side, label, onChange }: ResizerProps) {
  const startRef = useRef({ x: 0, width: 0 });

  const clamp = useCallback(
    (width: number) => Math.min(max, Math.max(min, width)),
    [max, min]
  );

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    // Ignore anything but the primary button; a right-click drag would
    // otherwise start a resize the user cannot see they began.
    if (event.button !== 0) return;
    startRef.current = {
      x: side === 'top' ? event.clientY : event.clientX,
      width: value,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
    const delta = (side === 'top' ? event.clientY : event.clientX) - startRef.current.x;
    // Dragging right grows a left-hand panel and shrinks a right-hand one;
    // dragging DOWN shrinks a bottom panel, so `top` shares the sign of `right`.
    const next = side === 'left'
      ? startRef.current.width + delta
      : startRef.current.width - delta;
    onChange(clamp(next));
  }

  function onPointerUp(event: React.PointerEvent<HTMLDivElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const grow = side === 'top' ? 'ArrowUp' : side === 'left' ? 'ArrowRight' : 'ArrowLeft';
    const shrink = side === 'top' ? 'ArrowDown' : side === 'left' ? 'ArrowLeft' : 'ArrowRight';
    if (event.key === grow) {
      event.preventDefault();
      onChange(clamp(value + KEY_STEP));
    } else if (event.key === shrink) {
      event.preventDefault();
      onChange(clamp(value - KEY_STEP));
    } else if (event.key === 'Home') {
      event.preventDefault();
      onChange(min);
    } else if (event.key === 'End') {
      event.preventDefault();
      onChange(max);
    }
  }

  return (
    <div
      className={side === 'top' ? 'resizer resizer-horizontal' : 'resizer'}
      role="separator"
      aria-orientation={side === 'top' ? 'horizontal' : 'vertical'}
      aria-label={label}
      aria-valuenow={Math.round(value)}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onKeyDown={onKeyDown}
    />
  );
}
